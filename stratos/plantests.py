"""The planner model drafts the test files of every task in a plan, for a person to read, fix and commit
before the tasks run."""

import ast
import re
import subprocess
from pathlib import Path

from . import codemap, config, context, decide, embed, lint, memstore, plan, patch, recall, refcheck
from . import cases


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


TEST_SYSTEM = system_prompt(config.PROJECT["language"], config.PROJECT["test_runner"])


def _has_file_marker(text):
    for line in text.splitlines():
        if patch.HEADER_RE.match(line):
            return True
    return False


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


def build_messages(task, root, example=None, earlier=(), memory=None, old=()):
    if example is None:
        example = config.PROJECT["example_test"]
    parts = [f"TASK {task['key']}: {task['title']}", task["goal"]]
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
    for p in old:
        if Path(root, p).exists():
            parts.append(context.show_file(root, p,
                "EXISTING TEST THAT USES THESE FILES (it must keep passing unless the goal changes what it checks)"))
    final = "WRITE THESE TEST FILES: " + ", ".join(new or task["tests"])
    if old or any(Path(root, p).exists() for p in task["tests"]):
        final += ("\nIf the goal makes a test in those existing files wrong, name it at the top of your new file "
                  "in a comment line: OUTDATED: <path>::<test name> - <reason>")
    parts.append(final)
    return [{"role": "system", "content": TEST_SYSTEM},
            {"role": "user", "content": "\n\n".join(parts)}]


def draft_problems(root, path):
    return lint.check(root, [path], codes=("F811", "F821", "F822", "F823"))


def check_draft(root, path):
    p = Path(root, path)
    if path.endswith(".py"):
        try:
            ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as e:
            return ("syntax_error", str(e))
    if config.PROJECT["test_runner"] == "dotnet":
        cmd = list(config.PROJECT["draft_check_command"])
    else:
        cmd = config.PROJECT["draft_check_command"] + [path]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
        )
    except subprocess.TimeoutExpired:
        return ("error", "draft check timed out")
    if result.returncode == 0:
        return ("collected", "")
    output = result.stdout + result.stderr
    if "ModuleNotFoundError" in output or "ImportError" in output:
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


def draft_tests(gw, plan_id, root, state_dir, log=print):
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
                    messages = build_messages(task, root, earlier=p["tasks"][:i], memory=memory, old=old)
                    messages[1]["content"] += "\n\nCASES (write one test for each, with exactly these values):\n" + "\n".join(lines)
                    files = _ask_test_writer(gw, plan_id, task, messages, model_cfg, answers_dir, root)
            else:
                old = old_tests(cmap, task)
                messages = build_messages(task, root, earlier=p["tasks"][:i], memory=memory, old=old)
                files = _ask_test_writer(gw, plan_id, task, messages, model_cfg, answers_dir, root)

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
            paths = task_written.get(key, [])
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
            elif r["status"] == "error":
                log(f"{key}: reference check: {r['first_error']}")
            gw.telemetry.record("ref_check", plan=plan_id, key=key, status=r["status"],
                                total=r["total"], failing=r["failing"])
            for entry in task_entries[key]:
                entry["refcheck"] = r

    return results
