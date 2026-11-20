"""T006: review step helpers (no model required).

build_messages(task, diff) -> chat messages asking a reviewer model for a JSON verdict
parse(text)                -> {"verdict": "approve" | "changes" | "unparsed", "issues": [...]}
is_blocking(review)        -> True when any issue is "high" or "medium"
format_issues(review)      -> the issues as lines for the next attempt's prompt
"""
import ast
import json
import re
from pathlib import Path

from stratos import config

REVIEW_SYSTEM = (
    "You review the diff against the task. "
    "Answer ONLY with a JSON object, optionally inside a json code block, "
    "of the form {\"verdict\": \"approve\" or \"changes\", \"issues\": [{\"severity\": \"high\" | \"medium\" | \"low\", \"file\": \"path\", \"problem\": \"one sentence\"}]} "
    "(real JSON uses double quotes). "
    "Check every changed line against the goal. "
    "high = wrong behaviour, a bug or a security problem; "
    "medium = misleading or redundant logic (for example a condition that is always true), "
    "work that grows with the input inside a loop (for example redrawing everything once per item), "
    "a missing edge case, "
    "or code that is never used (an unused variable, import or function); "
    "a change the goal did not ask for (a renamed name, reworded text or a prompt, any edit outside what the goal "
    "describes) is ALWAYS medium, even when it looks small or harmless, never low; "
    "a repeated call that costs a fixed small amount is low unless the goal is about speed; "
    "low = style only, in lines the goal asked to change. "
    "Use approve when there are no high or medium issues."
)


def project_files(root, settings=None):
    if settings is None:
        settings = config.PROJECT
    root = Path(root)
    paths = []
    for rel in settings["source_dirs"]:
        base = root / rel
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            rel_path = path.relative_to(root)
            if "__pycache__" in rel_path.parts:
                continue
            if path.suffix == ".pyc":
                continue
            paths.append(rel_path.as_posix())
    return sorted(paths)


def changed_paths(diff):
    seen = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[len("+++ b/"):].strip()
            if path not in seen:
                seen.append(path)
    return seen


def import_lines(root, paths):
    root = Path(root)
    blocks = []
    for path in paths:
        p = root / path
        if not p.is_file():
            continue
        suffix = p.suffix.lower()
        if suffix not in (".py", ".js", ".mjs"):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = []
        for line in text.splitlines():
            if suffix == ".py":
                if line.startswith("import ") or line.startswith("from "):
                    lines.append(line)
            else:
                if line.startswith("import "):
                    lines.append(line)
        if lines:
            blocks.append(f"{path}:\n" + "\n".join(lines))
        else:
            blocks.append(f"{path}:\n(no imports)")
    return "\n\n".join(blocks)


def build_messages(task, diff, files=None, imports=None):
    task_id = task.get("id", "")
    title = task.get("title", "")
    goal = task.get("goal", "")
    files_part = ""
    if files:
        files_part = (
            "PROJECT FILES (every module that exists; a name that is not here is not a module):\n"
            + "\n".join(files) + "\n\n"
        )
    imports_part = ""
    if imports:
        imports_part = (
            "IMPORTS OF THE CHANGED FILES (after the change; lines outside the diff exist too):\n"
            + imports + "\n\n"
        )
    user = (
        "Task id: " + task_id + "\n"
        "Title: " + title + "\n"
        "Goal: " + goal + "\n\n"
        + files_part +
        imports_part +
        "Diff:\n"
        "```diff\n"
        + diff + "\n"
        "```"
    )
    return [
        {"role": "system", "content": REVIEW_SYSTEM},
        {"role": "user", "content": user},
    ]


def _extract_json(text):
    if not text:
        return None
    for m in reversed(list(re.finditer(r"```(?:json)?\s*(.*?)```", text, re.DOTALL))):
        candidate = m.group(1).strip()
        if candidate:
            return candidate
    decoder = json.JSONDecoder()
    for i, char in enumerate(text):
        if char == "{":
            try:
                data, end = decoder.raw_decode(text, i)
            except (ValueError, TypeError):
                continue
            if isinstance(data, dict):
                return text[i:end]
    return None


def _find_bare_object(text):
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = None
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in ("'", '"'):
            in_str = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    return None


def _try_load(raw):
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        pass
    try:
        data = ast.literal_eval(raw)
    except (ValueError, TypeError, SyntaxError, RecursionError):
        return None
    return data


def parse(text):
    raw = _extract_json(text)
    if raw is None:
        raw = _find_bare_object(text)
    if raw is None:
        return {"verdict": "unparsed", "issues": []}
    data = _try_load(raw)
    if not isinstance(data, dict):
        return {"verdict": "unparsed", "issues": []}
    verdict = data.get("verdict")
    if not isinstance(verdict, str):
        return {"verdict": "unparsed", "issues": []}
    verdict = verdict.strip().lower()
    if verdict not in ("approve", "changes"):
        return {"verdict": "unparsed", "issues": []}
    issues = []
    for item in data.get("issues", []) or []:
        if not isinstance(item, dict):
            continue
        severity = item.get("severity")
        if not isinstance(severity, str):
            severity = "medium"
        severity = severity.strip().lower()
        if severity not in ("high", "medium", "low"):
            severity = "medium"
        file = item.get("file")
        file = "" if file is None else str(file)
        problem = item.get("problem")
        problem = "" if problem is None else str(problem)
        issues.append({"severity": severity, "file": file, "problem": problem})
    return {"verdict": verdict, "issues": issues}


def is_blocking(review):
    for issue in review.get("issues", []) or []:
        severity = issue.get("severity")
        if isinstance(severity, str) and severity.lower() in ("high", "medium"):
            return True
    return False


def format_issues(review):
    lines = []
    for issue in review.get("issues", []) or []:
        severity = issue.get("severity", "")
        file = issue.get("file", "") or ""
        problem = issue.get("problem", "") or ""
        if file:
            lines.append("- [{0}] {1}: {2}".format(severity, file, problem))
        else:
            lines.append("- [{0}] {1}".format(severity, problem))
    return "\n".join(lines)
