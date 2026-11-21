"""refcheck: an independent reference implementation checks drafted tests."""

import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from stratos import config, decide, langs, mutate, patch, verify

SYSTEM = (
    "You write the source files of one task of a project from its goal alone "
    "(you do not see its tests). For a file that already exists, answer with edit blocks:\n"
    "FILE: <path>\n"
    "<<<<<<< SEARCH\n"
    "<lines copied exactly from the file as shown>\n"
    "=======\n"
    "<the lines that replace them>\n"
    ">>>>>>> REPLACE\n"
    "For a new file, answer with the whole file:\n"
    "FILE: <path>\n"
    "```\n"
    "<content>\n"
    "```\n"
    "Answer with nothing else."
)


def build_messages(task, root):
    parts = ["GOAL:\n" + task["goal"], "WRITE THESE FILES: " + ", ".join(task["files"])]
    task_files_set = set(task["files"])
    for path in task["files"]:
        f = Path(root) / path
        if f.is_file():
            text = f.read_text(encoding="utf-8")
            parts.append(f"FILE YOU MAY CHANGE {path}:\n```\n{text}\n```")
    existing = []
    for d in config.PROJECT["source_dirs"]:
        dir_path = Path(root) / d
        if not dir_path.is_dir():
            continue
        for f in dir_path.rglob("*"):
            if not f.is_file():
                continue
            if "__pycache__" in f.parts or "bin" in f.parts or "obj" in f.parts:
                continue
            # (Claude, 2026-11-21, Settle) only source files the project writes - C#'s bin/obj hold .dll files
            if f.suffix not in config.PROJECT.get("writable_suffixes", [f.suffix]):
                continue
            rel = str(Path(f).relative_to(root)).replace("\\", "/")
            if rel in task_files_set:
                continue
            existing.append((rel, f))
    existing.sort(key=lambda x: x[0])
    for rel, f in existing:
        text = f.read_text(encoding="utf-8")
        parts.append(f"EXISTING FILE {rel}:\n```\n{text}\n```")
    conv_path = Path(root) / "CONVENTIONS.md"
    if conv_path.exists():
        parts.append("CONVENTIONS:\n" + conv_path.read_text(encoding="utf-8"))
    user_content = "\n\n".join(parts)
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_content},
    ]


def crash_line(output, files):
    wanted = {f.replace("\\", "/") for f in files}
    crash_lines = []
    for line in output.splitlines():
        m = re.match(r"^\s*(\S+\.py):(\d+): (\w+)\s*$", line)
        if m:
            path = m.group(1).replace("\\", "/")
            n = m.group(2)
            error = m.group(3)
            if path in wanted and error != "AssertionError":
                crash_lines.append((path, n, error))
    total, failing = count_tests(output)
    if not failing:
        return ""
    if len(crash_lines) >= len(failing):
        path, n, error = crash_lines[0]
        return f"{path}:{n}: {error}"
    return ""


def count_tests(output):
    tap = re.findall(r"^\s*(not ok|ok) \d+ - (.+)$", output, re.M)
    if tap:
        total = len(tap)
        failing = [name.strip() for ok, name in tap if ok == "not ok"]
        return (total, failing)
    totals = re.findall(r"Total(?: tests)?:\s*(\d+)", output)
    if totals:
        return (int(totals[-1]), decide._extract_ids(output))
    lines = output.splitlines()
    last_line = None
    for line in lines:
        if re.search(r"\d+\s+(passed|failed|errors?)\b", line):
            last_line = line
    if last_line is not None:
        nums = re.findall(r"(\d+) (passed|failed|errors?)\b", last_line)
        total = sum(int(n) for n, _ in nums)
    else:
        total = 0
    failing = decide._extract_ids(output)
    return (total, failing)


def judge(total, failing):
    if not failing:
        return "agree"
    if len(failing) * 2 > total:
        return "interface"
    return "flagged"


def check(gw, plan_id, task, root, tests, extra=None):
    tmp = Path(tempfile.mkdtemp())
    try:
        copy = tmp / "p"
        shutil.copytree(
            root,
            copy,
            ignore=shutil.ignore_patterns(".git", ".stratos", "node_modules", "__pycache__",
                                          ".venv", "venv", "*-wt", "bin", "obj"),
        )
        cfg = config.REF_WRITER
        gw.ensure_model(cfg["model"])
        chat_kwargs = dict(
            task=f"{plan_id}-{task['key']}",
            role="reference",
            attempt=1,
            model=cfg["model"],
            effort=cfg["effort"],
            max_tokens=cfg["max_tokens"],
        )
        if "reasoning_budget" in cfg:
            chat_kwargs["reasoning_budget"] = cfg["reasoning_budget"]
        _, answer = gw.chat(build_messages(task, root), **chat_kwargs)
        answers_dir = config.STATE_DIR / "answers"
        answers_dir.mkdir(parents=True, exist_ok=True)
        (answers_dir / f"{plan_id}-{task['key']}-reference.md").write_text(answer, encoding="utf-8")
        r = patch.read_answer(copy, answer, task["files"])
        if not r["edits"] and not r["whole"]:
            return {"status": "error", "total": 0, "failing": [], "first_error": "no file in the answer",
                    "files": []}
        if r["error"] is not None:
            return {"status": "error", "total": 0, "failing": [], "first_error": str(r["error"]), "files": []}
        files = r["files"]
        if extra:
            for path, content in extra:
                dest = Path(copy) / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
        for path, content in files:
            dest = Path(copy) / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        errors = verify.syntax_errors(copy, [p for p, _ in files])
        if errors:
            return {"status": "error", "total": 0, "failing": [],
                    "first_error": "the reference does not compile: " + errors[0], "files": []}
        cmd = verify.test_cmd(tests)
        try:
            with verify.dotnet_scope(copy, tests):
                r = subprocess.run(
                    cmd,
                    cwd=str(copy),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=config.TEST_TIMEOUT_S,
                    env=langs.child_env(),
                )
        except subprocess.TimeoutExpired:
            return {"status": "error", "total": 0, "failing": [], "first_error": "tests timed out",
                    "files": []}
        out = r.stdout + r.stderr
        total, failing = count_tests(out)
        if total == 0 and not failing:
            first = next((ln.strip()[:200] for ln in out.splitlines() if "rror" in ln), out.strip()[-200:])
            return {"status": "error", "total": 0, "failing": [], "first_error": "no test ran: " + first,
                    "files": []}
        crash = crash_line(out, [p for p, _ in files])
        if crash:
            return {"status": "crashed", "total": total, "failing": failing,
                    "first_error": crash, "files": files}
        first_error = ""
        for line in out.splitlines():
            if "Error" in line or "assert" in line:
                first_error = line.strip()[:200]
                break
        result = {"status": judge(total, failing), "total": total, "failing": failing,
                  "first_error": first_error, "files": files}
        if result["status"] == "agree" and config.MUTATION:
            result["mutation"] = mutation(copy, files, tests)
        return result
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def mutation(copy, files, tests, limit=None):
    if limit is None:
        limit = config.MUTANTS
    if not files:
        return {"total": 0, "killed": 0, "survivors": []}
    per_file = max(1, math.ceil(limit / len(files)))
    all_mutants = []
    orig = {path: content for path, content in files}
    for path, content in files:
        for m in mutate.mutants(content, per_file):
            all_mutants.append((path, m))
    all_mutants = all_mutants[:limit]

    total = 0
    killed = 0
    survivors = []

    for path, m in all_mutants:
        dest = Path(copy) / path
        dest.write_text(m["source"], encoding="utf-8")
        try:
            if path.endswith((".py", ".js")):
                if verify.syntax_errors(copy, [path]):
                    continue
            try:
                with verify.dotnet_scope(copy, tests):
                    r = subprocess.run(
                        verify.test_cmd(tests),
                        cwd=str(copy),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=config.MUTANT_TIMEOUT_S,
                        env=langs.child_env(),
                    )
            except subprocess.TimeoutExpired:
                total += 1
                killed += 1
                continue
            out = r.stdout + r.stderr
            t, failing = count_tests(out)
            if t == 0:
                continue
            total += 1
            if failing or r.returncode != 0:
                killed += 1
            else:
                survivors.append(f"{path}:{m['line']}: {m['old'].strip()} -> {m['new'].strip()}")
        finally:
            dest.write_text(orig[path], encoding="utf-8")

    return {"total": total, "killed": killed, "survivors": survivors}
