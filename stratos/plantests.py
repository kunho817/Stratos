"""The planner model drafts the test files of every task in a plan, for a person to read, fix and commit
before the tasks run."""

import re
import subprocess
import urllib.error
from pathlib import Path

from . import codemap, config, context, decide, embed, lint, memstore, plan, patch, recall, refcheck
from . import cases
from . import verify
from stratos import langs, steps


def system_prompt(language, test_runner):
    lower = language.lower()
    if lower == "python":
        top_comment = "a module docstring"
    else:
        top_comment = "a // comment"
    return (
        f"Write {test_runner} test files for the {language} project. Answer with FILE blocks "
        '("FILE: tests/test_x.py" then a fenced block). Include a top comment '
        f"({top_comment}) that describes the behaviour, then test functions. Use fakes (monkeypatch) "
        "instead of the network, the GPU and real models. Work out every expected value step by step "
        "in a comment above its assertion. At most 15 tests per file, one per behaviour; keep each file "
        "under 300 lines. When the code under test reads data that another task writes (levels, settings, "
        "tables), do not assume its contents: build your own small inputs or take cases from the data at "
        "run time. The tests should fail until the task is done."
    )


APPENDED = (' monkeypatch.setattr takes an object, the attribute name and the value, '
            'or one "module.attribute" string and the value; to give a program a file, '
            'write a real file in tmp_path instead of faking open.')

TEST_SYSTEM = system_prompt(config.PROJECT["language"], config.PROJECT["test_runner"]) + APPENDED


def _has_file_marker(text):
    for line in text.splitlines():
        if patch.HEADER_RE.match(line):
            return True
    return False


def _cut_at_file_marker(content):
    """Cut content at the first line starting with "FILE: ", removing a trailing "```" line right before."""
    lines = content.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("FILE: "):
            if i > 0 and lines[i - 1].strip() == "```":
                return "".join(lines[:i - 1])
            return "".join(lines[:i])
    return content


def _strip_lone_fence(answer):
    """Return the inner text of a lone fenced block, stripping the language tag.
    Returns None if the answer is not a lone fenced block."""
    lines = answer.splitlines(keepends=True)
    fences = [i for i, line in enumerate(lines) if line.lstrip().startswith("```")]
    if len(fences) != 2 or lines[fences[1]].strip() != "```":
        return None
    return "".join(lines[fences[0] + 1:fences[1]])


def _fenced_blocks(answer):
    """Return the inner texts of the fenced blocks of answer. A line starting with ``` opens a block, the
    next line whose stripped text is exactly ``` closes it; an unclosed block is not counted."""
    blocks = []
    lines = answer.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("```"):
            j = i + 1
            while j < len(lines) and lines[j].strip() != "```":
                j += 1
            if j < len(lines):
                blocks.append("".join(lines[i + 1:j]))
                i = j + 1
            else:
                break
        else:
            i += 1
    return blocks


def _ask_test_writer(gw, plan_id, task, messages, model_cfg, answers_dir, root):
    key = task["key"]
    kw = {"task": f"{plan_id}-{key}", "role": "test_writer", "attempt": 1,
          "model": model_cfg["model"], "effort": model_cfg["effort"],
          "max_tokens": model_cfg["max_tokens"]}
    if model_cfg.get("reasoning_budget") is not None:
        kw["reasoning_budget"] = model_cfg["reasoning_budget"]
    call_id, answer = gw.chat(messages, **kw)
    answer_path = answers_dir / f"{plan_id}-{key}-tests.md"
    answer_path.write_text(answer, encoding="utf-8")
    files = patch.parse_files(answer, allowed=task["tests"])
    files = [(p, _cut_at_file_marker(c)) for p, c in files]
    new_tests = [t for t in task["tests"] if not Path(root, t).exists()]
    if len(new_tests) == 1 and not files and not _has_file_marker(answer):
        inner = _strip_lone_fence(answer)
        if inner is not None:
            files = [(new_tests[0], inner)]
        else:
            blocks = _fenced_blocks(answer)
            if len(blocks) >= 2:
                files = [(new_tests[0], max(blocks, key=len))]
            else:
                first_line = answer.splitlines()[0] if answer else ""
                if not first_line.lstrip().startswith("```"):
                    files = [(new_tests[0], answer)]
    return files


def old_tests(cmap, task):
    files = cmap.get("files")
    imports = cmap.get("imports")
    if files is None or imports is None:
        return []
    test_dir = cmap.get("test_dir", "tests")
    prefix = test_dir + "/"
    task_tests = set(task["tests"])
    module_names = [codemap.module_name(f) for f in task["files"]]
    result = []
    for p in files:
        if not p.startswith(prefix):
            continue
        if p in task_tests:
            continue
        file_imports = imports.get(p, [])
        if any(mn in file_imports for mn in module_names):
            result.append(p)
    return sorted(result)


def outdated(text):
    return [{"test": m.group(1), "reason": m.group(2).strip()}
            for m in re.finditer(r"OUTDATED:\s*(\S+?::.+?)\s+-\s+(.+)$", text, re.M)]


def build_messages(task, root, example=None, earlier=(), memory=None, old=(), feature=None):
    if example is None:
        example = config.PROJECT["example_test"]
    parts = [f"TASK {task['key']}: {task['title']}", task["goal"]]
    if feature:
        parts.append("THE WHOLE FEATURE (this task is one part of it; its exact formats and numbers hold):\n" + feature)
    if earlier:
        parts.append(
            "EARLIER TASKS OF THIS PLAN (done before this one; use their functions, names and numbers exactly as "
            "they say):")
        for t in earlier:
            parts.append(f"{t['key']}: {t['title']}\n{t['goal']}")
        for t in earlier:
            first = t["tests"][0]
            if Path(root, first).exists():
                parts.append(context.show_file(root, first, "TEST OF AN EARLIER TASK"))
    parts.append("PROJECT FILES:\n" + plan.repo_summary(root))
    conventions = Path(root, "CONVENTIONS.md")
    if conventions.exists():
        parts.append("PROJECT CONVENTIONS:\n" + conventions.read_text(encoding="utf-8"))
    if memory:
        parts.append("MEMORY (found for this task in the project's code, tests, past tasks and people's corrections):\n" + memory)
    for p in task["files"]:
        parts.append(context.show_file(root, p, "FILE THE TASK WILL WRITE"))
    for p in task["protected"]:
        if p not in task["tests"]:
            parts.append(context.show_file(root, p, "READ-ONLY"))
    example_path = Path(root, example)
    if example_path.exists():
        parts.append(context.show_file(root, example, "EXAMPLE OF THE TEST STYLE"))
    new = [p for p in task["tests"] if not Path(root, p).exists()]
    for p in task["tests"]:
        if Path(root, p).exists():
            parts.append(context.show_file(root, p, "EXISTING TEST, DO NOT REWRITE"))
    parts.extend(_old_test_parts(task, root, old))
    final = "WRITE THESE TEST FILES: " + ", ".join(new or task["tests"])
    if old or any(Path(root, p).exists() for p in task["tests"]):
        final += ("\nIf the goal makes a test in those existing files wrong, name it at the top of your new file "
                  "in a comment line: OUTDATED: <path>::<test name> - <reason>")
    parts.append(final)
    return [{"role": "system", "content": TEST_SYSTEM},
            {"role": "user", "content": "\n\n".join(parts)}]


_DEFS = (re.compile(r"^(?:def|class)\s+([A-Za-z_]\w*)|^([A-Za-z_]\w*)\s*=", re.M),
         re.compile(r"^export\s+(?:async\s+)?(?:function\*?|class|const|let|var)\s+([A-Za-z_$][\w$]*)", re.M))


def goal_names(root, task):
    """Top-level names of the task's changed files that the goal names as whole words, sorted."""
    goal = task.get("goal", "")
    names = set()
    for path in task.get("files", []):
        try:
            text = Path(root, path).read_text(encoding="utf-8")
        except OSError:
            continue
        for rx in _DEFS:
            for m in rx.finditer(text):
                name = next(g for g in m.groups() if g)
                if re.search(r"(?<![\w$])" + re.escape(name) + r"(?![\w$])", goal):
                    names.add(name)
    return sorted(names)


def _old_test_parts(task, root, old):
    """(Claude, 2026-11-22) the old tests that import a changed file, within config.OLD_TESTS_CHARS: 42 of them
    (~69k tokens) for __main__.py made a prompt over Swift's context. When all fit, as before."""
    label = "EXISTING TEST THAT USES THESE FILES (it must keep passing unless the goal changes what it checks)"
    texts = {}
    for p in old:
        try:
            texts[p] = Path(root, p).read_text(encoding="utf-8")
        except OSError:
            continue
    if sum(len(t) for t in texts.values()) <= config.OLD_TESTS_CHARS:
        return [context.show_file(root, p, label) for p in texts]
    names = goal_names(root, task)

    def used(text):
        return [n for n in names if re.search(r"(?<![\w$])" + re.escape(n) + r"(?![\w$])", text)]
    ordered = sorted(texts, key=lambda p: (-len(used(texts[p])), p))
    total, parts = 0, []
    for p in ordered:
        if total + len(texts[p]) <= config.OLD_TESTS_CHARS:
            total += len(texts[p])
            parts.append(context.show_file(root, p, label))
        else:
            u = used(texts[p])
            parts.append(f"OLD TEST {p} (not shown, {len(texts[p].splitlines())} lines; uses: "
                         f"{', '.join(u) if u else 'none of the goal' + chr(39) + 's names'})")
    return parts


def draft_problems(root, path):
    return lint.check(root, [path], codes=("F811", "F821", "F822", "F823"))


def check_draft(root, path):
    if path.endswith(".py"):
        lines = verify.syntax_errors(str(root), [path])
        if lines:
            return ("syntax_error", lines[0])
    cmd = langs.runner().with_paths(config.PROJECT["draft_check_command"], [path])
    try:
        with steps.timed("draft_check"):
            result = subprocess.run(
                cmd,
                cwd=str(root), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
                env=langs.child_env(),
            )
    except subprocess.TimeoutExpired:
        return ("error", "draft check timed out")
    if result.returncode == 0:
        return ("collected", "")
    output = result.stdout + result.stderr
    if langs.runner().missing_import(output):
        return ("import_error", output[-2000:])
    return ("error", output[-2000:])


def suite_leaks(root, path, ignore=()):
    """Run the full suite with the draft in it and return the failing ids outside the draft path and ignore."""
    if not path.endswith(".py"):
        return []
    try:
        result = subprocess.run(
            config.PROJECT["test_command"] + [config.PROJECT["test_dir"]],
            cwd=str(root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=600,
        )
    except subprocess.TimeoutExpired:
        return []
    ids = decide._extract_ids(result.stdout + result.stderr)
    return sorted([i for i in ids if i.split("::")[0] not in (path, *ignore)])


RISKY_LABELS = [
    ("importlib.reload", re.compile(r"importlib\.reload\(|from\s+importlib\s+import\s+reload")),
    ("sys.modules", re.compile(r"sys\.modules\s*\[[^\]]*\]\s*=(?!=)|del\s+sys\.modules|sys\.modules\.(pop|update|setdefault|clear)\(")),
    ("os.environ assignment", re.compile(r"os\.environ\s*\[[^\]]*\]\s*=(?!=)|del\s+os\.environ|os\.environ\.(pop|update|setdefault|clear)\(")),
    ("config assignment", re.compile(r"^\s*config\.\w+(\[[^\]]*\])*\s*=(?!=)")),
    ("own MonkeyPatch", re.compile(r"MonkeyPatch\(\)")),
]


def risky_patterns(text):
    """Return labels of risky global-state patterns found in text, each at most once, in fixed order."""
    found = set()
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        for label, pattern in RISKY_LABELS:
            if label not in found and pattern.search(line):
                found.add(label)
    return [label for label, _ in RISKY_LABELS if label in found]


def mutation_lines(key, mutation):
    if mutation is None or mutation["total"] == 0:
        return []
    killed = mutation["killed"]
    total = mutation["total"]
    lines = [f"{key}: the tests caught {killed} of {total} small bugs put into the reference"]
    if killed / total < config.MUTATION_WEAK:
        survivors = mutation["survivors"][:5]
        lines.append(f"{key}: weak tests - these bugs went unnoticed: " + "; ".join(survivors))
    return lines


def draft_tests(gw, plan_id, root, state_dir, log=print):
    steps.use(gw.telemetry, plan_id)
    p = plan.load_plan(state_dir, plan_id)
    model_cfg = config.PLANNER
    gw.ensure_model(model_cfg["model"])
    answers_dir = Path(state_dir) / "answers"
    answers_dir.mkdir(parents=True, exist_ok=True)
    results = []
    written_so_far = []

    cmap = codemap.build(root)

    store = None
    if config.MEMORY and (Path(state_dir) / "memory.db").exists():
        try:
            store = memstore.Store(Path(state_dir) / "memory.db")
            embedder = embed.Embedder()
        except Exception as e:
            log(f"memory: {e}")
            store = None

    task_written = {}
    task_entries = {}

    try:
        for i, task in enumerate(p["tasks"]):
            key = task["key"]
            memory = None
            if store is not None:
                try:
                    memory = recall.pack(store, task["title"] + "\n" + task["goal"], embedder, cmap, budget=8000,
                                         always_tags={"tests"})
                except Exception as e:
                    log(f"memory: {e}")
            lines = task.get("cases") or []
            files = None

            if lines:
                parsed = cases.parse("\n".join(lines))
                if not parsed["other"]:
                    files = [(task["tests"][0], cases.render(parsed, language="javascript" if config.PROJECT["language"] == "javascript" else "python"))]
                    log(f"{task['tests'][0]}: written from {len(parsed['plain'])} cases (no model)")
                else:
                    old = old_tests(cmap, task)
                    messages = build_messages(task, root, earlier=p["tasks"][:i], memory=memory, old=old, feature=p["goal"])
                    messages[1]["content"] += "\n\nCASES (write one test for each, with exactly these values):\n" + "\n".join(lines)
                    try:
                        files = _ask_test_writer(gw, plan_id, task, messages, model_cfg, answers_dir, root)
                    except urllib.error.HTTPError as e:
                        detail = e.read().decode("utf-8", errors="replace")[:500]
                        for tpath in task["tests"]:
                            results.append({"key": key, "file": tpath, "status": "call_error", "detail": detail})
                        task_written[key] = []
                        task_entries[key] = []
                        continue
            else:
                old = old_tests(cmap, task)
                messages = build_messages(task, root, earlier=p["tasks"][:i], memory=memory, old=old, feature=p["goal"])
                try:
                    files = _ask_test_writer(gw, plan_id, task, messages, model_cfg, answers_dir, root)
                except urllib.error.HTTPError as e:
                    detail = e.read().decode("utf-8", errors="replace")[:500]
                    for tpath in task["tests"]:
                        results.append({"key": key, "file": tpath, "status": "call_error", "detail": detail})
                    task_written[key] = []
                    task_entries[key] = []
                    continue

            written = {}
            for fpath, fcontent in files:
                written[fpath] = fcontent
            task_written[key] = []
            task_entries[key] = []
            for tpath in task["tests"]:
                problems = []
                if tpath not in written:
                    if Path(root, tpath).exists():
                        status = "old"
                    else:
                        status = "missing"
                elif Path(root, tpath).exists():
                    status = "exists"
                    log(f"{tpath} already exists, not overwritten")
                else:
                    dest = Path(root, tpath)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(written[tpath], encoding="utf-8")
                    status = check_draft(root, tpath)[0]
                    if tpath.endswith(".py") and status == "collected":
                        labels = risky_patterns(written[tpath])
                        if labels:
                            status = "risky"
                            log(f"{tpath}: risky: {', '.join(labels)}")
                    if tpath.endswith(".py") and status == "collected":
                        ids = suite_leaks(root, tpath, ignore=list(written_so_far))
                        if ids:
                            status = "leaks"
                            log(f"{tpath}: leaks into: {', '.join(ids[:5])}")
                    if tpath.endswith(".py") and status == "collected":
                        problems = draft_problems(root, tpath)
                        if problems:
                            for line in problems:
                                log(f"{tpath}: lint: {line}")
                    written_so_far.append(tpath)
                if status == "risky":
                    gw.telemetry.record("test_draft", plan=plan_id, key=key, file=tpath,
                                        status=status, risks=labels)
                elif status == "leaks":
                    gw.telemetry.record("test_draft", plan=plan_id, key=key, file=tpath,
                                        status=status, leaks=ids[:10])
                else:
                    gw.telemetry.record("test_draft", plan=plan_id, key=key, file=tpath,
                                        status=status)
                entry = {"key": key, "file": tpath, "status": status}
                if problems:
                    entry["lint"] = problems
                if status not in ("missing", "exists", "old"):
                    task_written[key].append(tpath)
                    found = outdated(written[tpath])
                    if found:
                        for o in found:
                            log(f"{tpath}: outdated {o['test']}: {o['reason']}")
                        gw.telemetry.record("test_outdated", plan=plan_id, key=key, file=tpath,
                                            tests=[o["test"] for o in found])
                        entry["outdated"] = found
                results.append(entry)
                task_entries[key].append(entry)
    finally:
        if store is not None:
            store.close()

    refs = []
    if config.REF_CHECK:
        for i, task in enumerate(p["tasks"]):
            key = task["key"]
            paths = list(task_written.get(key, []))
            for entry in task_entries.get(key, []):
                if entry["status"] == "exists":
                    paths.append(entry["file"])
            if not paths:
                continue
            try:
                r = refcheck.check(gw, plan_id, task, root, paths, extra=list(refs))
            except Exception as e:
                log(f"{key}: reference check failed: {e}")
                continue
            refs.extend(r.get("files", []))
            if r["status"] == "flagged":
                log(f"{key}: reference implementation fails {len(r['failing'])} of {r['total']} tests: {', '.join(r['failing'])}")
            elif r["status"] == "interface":
                log(f"{key}: reference implementation fails {len(r['failing'])} of {r['total']} tests - the goal may leave the interface open: {r['first_error']}")
            elif r["status"] == "crashed":
                log(f"{key}: the reference implementation crashed ({r['first_error']}) - this says nothing about the tests")
            elif r["status"] == "agree":
                log(f"{key}: reference implementation passes all {r['total']} tests")
                for line in mutation_lines(key, r.get("mutation")):
                    log(line)
            elif r["status"] == "error":
                log(f"{key}: reference check: {r['first_error']}")
            gw.telemetry.record("ref_check", plan=plan_id, key=key, status=r["status"],
                                total=r["total"], failing=r["failing"],
                                mutation_total=(r.get("mutation") or {}).get("total"),
                                mutation_killed=(r.get("mutation") or {}).get("killed"))

            if r["status"] == "flagged" and config.REF_SECOND:
                try:
                    r2 = refcheck.check(gw, plan_id, task, root, paths,
                                        extra=list(refs), writer=config.ROLES["coder"])
                except Exception as e:
                    log(f"{key}: second reference check failed: {e}")
                    for entry in task_entries[key]:
                        entry["refcheck"] = r
                    continue
                refs.extend(r2.get("files", []))
                gw.telemetry.record("ref_check", plan=plan_id, key=key, status=r2["status"],
                                    total=r2["total"], failing=r2["failing"],
                                    mutation_total=(r2.get("mutation") or {}).get("total"),
                                    mutation_killed=(r2.get("mutation") or {}).get("killed"))
                suspect = sorted(set(r["failing"]) & set(r2["failing"]))
                if suspect:
                    for entry in task_entries[key]:
                        entry["refcheck"] = r
                        entry["suspect"] = suspect
                    names = ", ".join(suspect)
                    log(f"{key}: two independent references fail: {names} - these tests are likely wrong")
                    gw.telemetry.record("ref_suspect", plan=plan_id, key=key, tests=suspect)

                    # repair round
                    old = old_tests(cmap, task)
                    repair_messages = build_messages(task, root, earlier=p["tasks"][:i],
                                                     memory=None, old=old, feature=p["goal"])
                    draft_text = ""
                    for tpath in paths:
                        try:
                            draft_text += Path(root, tpath).read_text(encoding="utf-8")
                        except OSError:
                            pass
                    first_output = r.get("output", "")
                    repair_part = ("\n\nREPAIR ROUND: rewrite only these suspect tests: "
                                   + ", ".join(suspect)
                                   + ". Take expected values from the facts and the rules, "
                                     "not from a head calculation.\n"
                                     "The earlier draft:\n" + draft_text + "\n"
                                     "The first reference's test output:\n" + first_output)
                    repair_messages[1]["content"] += repair_part
                    try:
                        new_files = _ask_test_writer(gw, plan_id, task, repair_messages,
                                                     config.PLANNER, answers_dir, root)
                    except Exception:
                        for entry in task_entries[key]:
                            entry["refcheck"] = r
                        continue

                    repaired = False
                    if new_files:
                        new_path, new_content = new_files[0]
                        dest = Path(root, new_path)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_text(new_content, encoding="utf-8")
                        status = check_draft(root, new_path)[0]
                        if status == "collected":
                            repaired = True

                    if repaired:
                        try:
                            r3 = refcheck.check(gw, plan_id, task, root, paths,
                                                extra=list(refs))
                        except Exception as e:
                            log(f"{key}: repair reference check failed: {e}")
                            for entry in task_entries[key]:
                                entry["refcheck"] = r
                            continue
                        refs.extend(r3.get("files", []))
                        gw.telemetry.record("ref_check", plan=plan_id, key=key, status=r3["status"],
                                            total=r3["total"], failing=r3["failing"],
                                            mutation_total=(r3.get("mutation") or {}).get("total"),
                                            mutation_killed=(r3.get("mutation") or {}).get("killed"))
                        for entry in task_entries[key]:
                            entry["refcheck"] = r3
                            entry["repaired"] = True
                    else:
                        for entry in task_entries[key]:
                            entry["refcheck"] = r
                else:
                    for entry in task_entries[key]:
                        entry["refcheck"] = r
            else:
                for entry in task_entries[key]:
                    entry["refcheck"] = r

    return results
