"""T006: review step helpers (no model required).

build_messages(task, diff) -> chat messages asking a reviewer model for a JSON verdict
parse(text)                -> {"verdict": "approve" | "changes" | "unparsed", "issues": [...]}
is_blocking(review)        -> True when any issue is "high" or "medium"
format_issues(review)      -> the issues as lines for the next attempt's prompt
"""
import ast
import json
import re

REVIEW_SYSTEM = (
    "You review the diff against the task. "
    "Answer ONLY with a JSON object, optionally inside a json code block, "
    "of the form {\"verdict\": \"approve\" or \"changes\", \"issues\": [{\"severity\": \"high\" | \"medium\" | \"low\", \"file\": \"path\", \"problem\": \"one sentence\"}]} "
    "(real JSON uses double quotes). "
    "high = wrong behaviour, a bug or a security problem; "
    "medium = misleading or redundant logic (for example a condition that is always true), "
    "needless repeated work, or a missing edge case; "
    "low = style only. "
    "Use approve when there are no high or medium issues."
)


def build_messages(task, diff):
    task_id = task.get("id", "")
    title = task.get("title", "")
    goal = task.get("goal", "")
    user = (
        "Task id: {id}\n"
        "Title: {title}\n"
        "Goal: {goal}\n\n"
        "Diff:\n"
        "```diff\n"
        "{diff}\n"
        "```"
    ).format(id=task_id, title=title, goal=goal, diff=diff)
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
