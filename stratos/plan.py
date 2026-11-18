"""Planner's pure parts: prompt, parsing, checking and storing plans."""

import ast
import hashlib
import json
import re
from pathlib import Path

SYSTEM = (
    "You are a planner. Answer with JSON only, no prose. Format:\n"
    '{"tasks": [{"key", "title", "goal", "files", "tests", "protected", "after", "role"}]}\n'
    "Each task should be small (one function or one file). "
    "Each task names its test files under tests/. "
    "after lists keys of earlier tasks it builds on. "
    "protected lists files it may read but not change. "
    "role is \"coder\" for new functions and small additions, "
    "or \"coder_hard\" for changes of existing control flow."
)


def repo_summary(root):
    root = Path(root)
    lines = []
    stratos_dir = root / "stratos"
    if stratos_dir.is_dir():
        py_files = sorted(stratos_dir.glob("*.py"))
        for f in py_files:
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
                doc = ast.get_docstring(tree)
            except (SyntaxError, UnicodeDecodeError):
                doc = None
            if doc:
                first_line = doc.split("\n")[0]
                lines.append(f"stratos/{f.name} - {first_line}")
            else:
                lines.append(f"stratos/{f.name}")
    tests_dir = root / "tests"
    if tests_dir.is_dir():
        py_files = sorted(tests_dir.glob("*.py"))
        for f in py_files:
            lines.append(f"tests/{f.name}")
    return "\n".join(lines)


def build_messages(goal, summary):
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"PROJECT FILES:\n{summary}\n\nFEATURE GOAL:\n{goal}"},
    ]


class PlanError(ValueError):
    pass


def parse_plan(text):
    raw = _extract_json(text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise PlanError("No valid JSON found in the response.")
    if not isinstance(data, dict):
        raise PlanError("Plan must be a JSON object, not a list or other type.")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or len(tasks) == 0:
        raise PlanError("tasks must be a non-empty list.")

    seen_keys = []
    result = []
    for i, t in enumerate(tasks):
        if not isinstance(t, dict):
            raise PlanError(f"Task {i+1} is not an object.")
        key = t.get("key", str(i + 1))
        title = t.get("title")
        goal = t.get("goal")
        files = t.get("files")
        tests = t.get("tests")
        protected = t.get("protected", [])
        after = t.get("after", [])
        role = t.get("role", None)

        if not isinstance(title, str) or not title.strip():
            raise PlanError(f"Task {key}: title must be a non-empty string.")
        if not isinstance(goal, str) or not goal.strip():
            raise PlanError(f"Task {key}: goal must be a non-empty string.")
        if not isinstance(files, list) or len(files) == 0:
            raise PlanError(f"Task {key}: files must be a non-empty list of strings.")
        if not all(isinstance(f, str) for f in files):
            raise PlanError(f"Task {key}: files must be a non-empty list of strings.")
        if not isinstance(tests, list) or len(tests) == 0:
            raise PlanError(f"Task {key}: tests must be a non-empty list of strings.")
        if not all(isinstance(t_str, str) and t_str.startswith("tests/") and t_str.endswith(".py") for t_str in tests):
            raise PlanError(f"Task {key}: tests must be strings starting with 'tests/' and ending with '.py'.")
        if not isinstance(protected, list):
            raise PlanError(f"Task {key}: protected must be a list of strings.")
        if not all(isinstance(p, str) for p in protected):
            raise PlanError(f"Task {key}: protected must be a list of strings.")
        if not isinstance(after, list):
            raise PlanError(f"Task {key}: after must be a list of keys of earlier tasks.")
        if not all(isinstance(a, str) for a in after):
            raise PlanError(f"Task {key}: after must be a list of keys of earlier tasks.")
        # after must reference only earlier keys
        for a in after:
            if a not in seen_keys:
                raise PlanError(f"Task {key}: after references '{a}' which is not an earlier task key.")
        if role is not None and role not in ("coder", "coder_hard"):
            raise PlanError(f"Task {key}: role must be 'coder', 'coder_hard' or null.")

        if key in seen_keys:
            raise PlanError(f"Task {key}: key '{key}' is duplicated.")
        seen_keys.append(key)

        result.append({
            "key": key,
            "title": title,
            "goal": goal,
            "files": files,
            "tests": tests,
            "protected": protected,
            "after": after,
            "role": role,
        })
    return result


def _extract_json(text):
    blocks = re.findall(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if blocks:
        return blocks[-1]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or start >= end:
        raise PlanError("No JSON object found in the response.")
    return text[start:end + 1]


def plan_hash(tasks):
    return hashlib.sha256(
        json.dumps(tasks, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def save_plan(state_dir, goal, tasks):
    state_dir = Path(state_dir)
    plans_dir = state_dir / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    n = len(list(plans_dir.glob("*.json"))) + 1
    pid = f"P{n:03d}"
    content = {
        "id": pid,
        "goal": goal,
        "tasks": tasks,
        "status": "draft",
        "hash": plan_hash(tasks),
    }
    path = plans_dir / f"{pid}.json"
    path.write_text(json.dumps(content, indent=1, ensure_ascii=False), encoding="utf-8")
    return pid


def load_plan(state_dir, pid):
    state_dir = Path(state_dir)
    path = state_dir / "plans" / f"{pid}.json"
    if not path.exists():
        raise KeyError(pid)
    return json.loads(path.read_text(encoding="utf-8"))


def edited(plan):
    return plan_hash(plan["tasks"]) != plan["hash"]


def mark_added(state_dir, pid, task_ids):
    state_dir = Path(state_dir)
    path = state_dir / "plans" / f"{pid}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["status"] = "added"
    data["task_ids"] = task_ids
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
