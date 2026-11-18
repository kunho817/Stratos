"""The planner model drafts the test files of every task in a plan, for a person to read, fix and commit
before the tasks run."""

import ast
import re
import subprocess
import sys
from pathlib import Path

from . import config, context, plan, patch


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
        "in a comment above its assertion. The tests should fail "
        "until the task is done."
    )


TEST_SYSTEM = system_prompt(config.PROJECT["language"], config.PROJECT["test_runner"])

_HEADER_RE = re.compile(r"^\s*FILE:\s*`?([^\s`]+)`?\s*$")


def _has_file_marker(text):
    for line in text.splitlines():
        if _HEADER_RE.match(line):
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


def build_messages(task, root, example=None):
    if example is None:
        example = config.PROJECT["example_test"]
    parts = [f"TASK {task['key']}: {task['title']}", task["goal"]]
    parts.append("PROJECT FILES:\n" + plan.repo_summary(root))
    conventions = Path(root, "CONVENTIONS.md")
    if conventions.exists():
        parts.append("PROJECT CONVENTIONS:\n" + conventions.read_text(encoding="utf-8"))
    for p in task["files"]:
        parts.append(context.show_file(root, p, "FILE THE TASK WILL WRITE"))
    for p in task["protected"]:
        if p not in task["tests"]:
            parts.append(context.show_file(root, p, "READ-ONLY"))
    example_path = Path(root, example)
    if example_path.exists():
        parts.append(context.show_file(root, example, "EXAMPLE OF THE TEST STYLE"))
    parts.append("WRITE THESE TEST FILES: " + ", ".join(task["tests"]))
    return [{"role": "system", "content": TEST_SYSTEM},
            {"role": "user", "content": "\n\n".join(parts)}]


def check_draft(root, path):
    p = Path(root, path)
    if path.endswith(".py"):
        try:
            ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as e:
            return ("syntax_error", str(e))
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


def draft_tests(gw, plan_id, root, state_dir, log=print):
    p = plan.load_plan(state_dir, plan_id)
    model_cfg = config.PLANNER
    gw.ensure_model(model_cfg["model"])
    answers_dir = Path(state_dir) / "answers"
    answers_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for task in p["tasks"]:
        key = task["key"]
        messages = build_messages(task, root)
        kw = {"task": f"{plan_id}-{key}", "role": "test_writer", "attempt": 1,
              "model": model_cfg["model"], "effort": model_cfg["effort"],
              "max_tokens": model_cfg["max_tokens"]}
        if model_cfg.get("reasoning_budget") is not None:
            kw["reasoning_budget"] = model_cfg["reasoning_budget"]
        call_id, answer = gw.chat(messages, **kw)
        answer_path = answers_dir / f"{plan_id}-{key}-tests.md"
        answer_path.write_text(answer, encoding="utf-8")
        files = patch.parse_files(answer, allowed=task["tests"])
        if len(task["tests"]) == 1 and not files and not _has_file_marker(answer):
            inner = _strip_lone_fence(answer)
            if inner is not None:
                files = [(task["tests"][0], inner)]
            else:
                first_line = answer.splitlines()[0] if answer else ""
                if not first_line.lstrip().startswith("```"):
                    files = [(task["tests"][0], answer)]
                else:
                    lines = answer.splitlines(keepends=True)
                    fences = [i for i, line in enumerate(lines)
                              if line.lstrip().startswith("```")]
                    if fences:
                        files = [(task["tests"][0], "".join(lines[fences[0] + 1:]))]
        written = {}
        for fpath, fcontent in files:
            written[fpath] = fcontent
        for tpath in task["tests"]:
            if tpath not in written:
                status = "missing"
            elif Path(root, tpath).exists():
                status = "exists"
                log(f"{tpath} already exists, not overwritten")
            else:
                dest = Path(root, tpath)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(written[tpath], encoding="utf-8")
                status = check_draft(root, tpath)[0]
            gw.telemetry.record("test_draft", plan=plan_id, key=key, file=tpath, status=status)
            results.append({"key": key, "file": tpath, "status": status})
    return results
