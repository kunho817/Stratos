"""Planner's pure parts: prompt, parsing, checking and storing plans."""

import ast
import copy
import hashlib
import json
import re
from pathlib import Path

from stratos import config

SYSTEM = (
    "You are a planner. Answer with JSON only, no prose. Format:\n"
    '{"tasks": [{"key", "title", "goal", "files", "tests", "protected", "after", "role"}]}\n'
    "Each task should be small (one function or one file). "
    "Each task names its test files under tests/. "
    "after lists keys of earlier tasks it builds on. "
    "protected lists files it may read but not change. "
    "role is \"coder\" for new functions and small additions, "
    "or \"coder_hard\" for changes of existing control flow.\n"
    "Tasks that write the same file must be chained: each one lists the previous one in \"after\".\n"
    "The tests of a task are written before the task runs, so never make a task whose files are only test files.\n"
    "Keep related small functions of one module in one task; a task should be worth a model call and a review.\n"
    "A function that calls a model takes the gateway as a parameter (gw), so tests can pass a fake.\n"
    "Prefer 2 to 6 tasks for a feature."
    " When a task holds an algorithm (a search, a schedule, a simulation, an ordering with tie-breaks), end its goal with a line METHOD: the steps that meet the rules (the data kept, the order things are tried in, what is skipped) - no code."
)

_RULES = SYSTEM[SYSTEM.index("Tasks that write the same file"):]

TEXT_SYSTEM = (
    "You are a planner. Answer with plain text, no JSON. "
    "Write one block per task, with these lines:\n"
    "Key: <short key>\n"
    "Title: <short title>\n"
    "Goal: <what to do>\n"
    "Files: <paths this task writes>\n"
    "Tests: <paths under tests/ that cover this task>\n"
    "Protected: <files this task reads but does not change>\n"
    "After: <keys of earlier tasks this task builds on>\n"
    "Role: coder for new functions and small additions, or coder_hard for changes of existing control flow\n"
    "\n"
    "Field explanations:\n"
    "Each task should be small (one function or one file). "
    "Each task names its test files under tests/. "
    "after lists keys of earlier tasks it builds on. "
    "protected lists files it may read but not change. "
    "role is \"coder\" for new functions and small additions, "
    "or \"coder_hard\" for changes of existing control flow.\n"
    "\n"
    "Rules:\n"
    + _RULES
)

CONVERT_SYSTEM = (
    "You are a converter. The user gives a plan written as plain text. "
    "Convert it to JSON only, no prose. Output format:\n"
    '{"tasks": [{"key", "title", "goal", "files", "tests", "protected", "after", "role"}]}\n'
    "Fields: key, title, goal, files, tests, protected, after, role.\n"
    "Copy every goal word for word. Answer with JSON only."
)


_JS_EXPORT_FUNCTION_RE = re.compile(r"export\s+function\s+([A-Za-z0-9_$]+)\s*\(([^)]*)\)")
_JS_EXPORT_CLASS_RE = re.compile(r"export\s+class\s+([A-Za-z0-9_$]+)")


def _js_summary(path):
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    lines = [f"{path.parent.name}/{path.name}"]
    for m in _JS_EXPORT_FUNCTION_RE.finditer(text):
        args = m.group(2).strip()
        lines.append(f"  export function {m.group(1)}({args})")
    for m in _JS_EXPORT_CLASS_RE.finditer(text):
        lines.append(f"  export class {m.group(1)}")
    return lines


def _py_summary(path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        doc = ast.get_docstring(tree)
    except (SyntaxError, UnicodeDecodeError):
        doc = None
        return [f"{path.parent.name}/{path.name}"]
    if doc:
        first_line = doc.split("\n")[0]
        lines = [f"{path.parent.name}/{path.name} - {first_line}"]
    else:
        lines = [f"{path.parent.name}/{path.name}"]
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if node.name.startswith("_"):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines.append(f"  def {node.name}({ast.unparse(node.args)})")
        else:
            lines.append(f"  class {node.name}")
    return lines


def repo_summary(root, settings=None):
    if settings is None:
        settings = config.PROJECT
    root = Path(root)
    lines = []
    for d in settings["source_dirs"]:
        src_dir = root / d
        if not src_dir.is_dir():
            continue
        for f in sorted(src_dir.iterdir()):
            if not f.is_file():
                continue
            suffix = f.suffix.lower()
            if suffix in (".js", ".mjs"):
                lines.extend(_js_summary(f))
            elif suffix == ".py":
                lines.extend(_py_summary(f))
    test_dir = root / settings["test_dir"]
    if test_dir.is_dir():
        for f in sorted(test_dir.iterdir()):
            if not f.is_file():
                continue
            if any(f.name.endswith(s) for s in settings["test_suffixes"]):
                lines.append(f"{settings['test_dir']}/{f.name}")
    return "\n".join(lines)


_USES_HEADER = "WHO USES WHAT (when a task changes a name, every user listed here must be changed or checked too):\n"
_MEMORY_HEADER = "MEMORY (found for this goal in the project's code, tests, past tasks and people's corrections):\n"


def build_messages(goal, summary, conventions=None, system=None, uses=None, memory=None):
    sys_content = system if system is not None else SYSTEM
    parts = [f"PROJECT FILES:\n{summary}"]
    try:
        proj = config.PROJECT
        test_dir = proj["test_dir"]
        suffixes = proj["test_suffixes"]
        if suffixes:
            test_line = f"TEST FILES: every test file path starts with {test_dir}/ and ends with {suffixes[0]}."
        else:
            test_line = None
    except (AttributeError, KeyError, TypeError, IndexError):
        test_line = None
    if test_line:
        parts.append("\n\n" + test_line)
    if uses:
        parts.append("\n\n" + _USES_HEADER + uses)
    if memory:
        parts.append("\n\n" + _MEMORY_HEADER + memory)
    if conventions is not None:
        parts.append("\n\nPROJECT CONVENTIONS:\n" + conventions)
    parts.append("\n\nFEATURE GOAL:\n" + goal)
    user_content = "".join(parts)
    return [
        {"role": "system", "content": sys_content},
        {"role": "user", "content": user_content},
    ]


class PlanError(ValueError):
    pass


class PlanFormatError(PlanError):
    pass


class PlanNotFound(KeyError):
    pass


_FIELD_RE = re.compile(
    r'^\s*[-*#\s]*\**\s*(Key|Title|Goal|Files|Tests|Protected|After|Role)\**\s*:\**\s*(.*)$'
)

_LIST_FIELDS = {"Files", "Tests", "Protected", "After"}

_NONE_WORDS = {"none", "(none)", "-", "n/a", "nothing", "[]"}


def fix_new_tests(tasks, root, settings=None):
    if settings is None:
        settings = config.PROJECT
    test_dir = settings["test_dir"]
    suffix = settings["test_suffixes"][0]
    root = Path(root)
    taken = set()
    for task in tasks:
        for t in task["tests"]:
            taken.add(t)
    firsts = {}
    messages = []
    for task in tasks:
        key = task["key"]
        first = task["tests"][0]
        reason = None
        if first in firsts:
            reason = f"{first} is task {firsts[first]}'s first test file"
        elif Path(root, first).exists():
            reason = f"{first} already existed"
        if reason:
            slug = re.sub(r"[^a-z0-9]+", "_", task["key"].lower()).strip("_")
            if suffix == ".py":
                base_name = f"{test_dir}/test_{slug}.py"
            else:
                base_name = f"{test_dir}/{slug}{suffix}"
            name = base_name
            i = 2
            while Path(root, name).exists() or name in taken:
                if suffix == ".py":
                    name = f"{test_dir}/test_{slug}_{i}.py"
                else:
                    name = f"{test_dir}/{slug}_{i}{suffix}"
                i += 1
            task["tests"].insert(0, name)
            taken.add(name)
            messages.append(f"Task {key}: added the new test file {name} ({reason})")
        firsts[task["tests"][0]] = key
    return messages


def parse_text_plan(text):
    lines = text.split("\n")
    tasks = []
    current_fields = {}
    current_field_name = None
    seen_key = False

    for line in lines:
        match = _FIELD_RE.match(line)
        if match:
            field_name = match.group(1)
            value = match.group(2)
            if field_name == "Key":
                if seen_key:
                    tasks.append(current_fields)
                seen_key = True
                current_fields = {}
                current_field_name = "Key"
                current_fields["Key"] = value
            else:
                if not seen_key:
                    continue
                current_field_name = field_name
                current_fields[field_name] = value
        else:
            if current_field_name is not None:
                current_fields[current_field_name] += "\n" + line
                # blank line: current_field_name stays the same (blank lines end nothing)

    if not seen_key:
        raise PlanFormatError("No 'Key:' line found in the text.")

    tasks.append(current_fields)

    result_tasks = []
    for fields in tasks:
        task = {}
        all_notes = []
        for name, val in fields.items():
            val = val.strip()
            if name == "Key":
                task["key"] = val
            elif name == "Title":
                task["title"] = val
            elif name == "Goal":
                task["goal"] = val
            elif name in _LIST_FIELDS:
                # Walk parenthesised notes in order
                for m in re.finditer(r"\s*\(([^)]*)\)", val):
                    note = m.group(1).strip()
                    if note.lower() in ("new", "new file"):
                        continue
                    before = val[:m.start()]
                    last_comma = before.rfind(",")
                    if last_comma != -1:
                        item = before[last_comma + 1:].strip()
                    else:
                        item = before.strip()
                    item = item.strip("`")
                    all_notes.append((item, note))
                val = re.sub(r"\s*\([^)]*\)", "", val)

                items = [v.strip() for v in val.split(",")]
                items = [v.strip("`") for v in items]
                items = [v for v in items if v and v.lower() not in _NONE_WORDS]
                key_name = name.lower()
                task[key_name] = items
            elif name == "Role":
                r = val.strip("`")
                if r in ("coder", "coder_hard"):
                    task["role"] = r
                else:
                    task["role"] = None

        # Append recorded notes to goal
        if all_notes and "goal" in task:
            task["goal"] += "\n\nNotes from the plan:\n" + "\n".join(
                f"- {item}: {note}" for item, note in all_notes
            )

        # Remove test files from files
        if "files" in task:
            task["files"] = [f for f in task["files"] if f not in task.get("tests", [])]
        if "protected" in task and "files" in task:
            task["protected"] = [p for p in task["protected"] if p not in task["files"]]

        result_tasks.append(task)

    # Filter After items: drop ^T\d+$ that are not keys of earlier tasks
    earlier_keys = set()
    for task in result_tasks:
        new_after = []
        for item in task.get("after", []):
            if item in earlier_keys:
                new_after.append(item)
            elif re.match(r"^T\d+$", item):
                continue
            else:
                new_after.append(item)
        task["after"] = new_after
        if "key" in task:
            earlier_keys.add(task["key"])

    return parse_plan(json.dumps({"tasks": result_tasks}))


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
        test_dir = config.PROJECT["test_dir"]
        test_suffixes = config.PROJECT["test_suffixes"]
        is_go = config.PROJECT.get("test_runner") == "go test"
        if is_go:
            if not all(isinstance(t_str, str) and any(t_str.endswith(s) for s in test_suffixes) for t_str in tests):
                raise PlanError(f"Task {key}: tests must end with one of {test_suffixes}.")
        else:
            if not all(isinstance(t_str, str) and t_str.startswith(test_dir + "/") and any(t_str.endswith(s) for s in test_suffixes) for t_str in tests):
                raise PlanError(f"Task {key}: tests must start with '{test_dir}/' and end with one of {test_suffixes}.")
        if not isinstance(protected, list):
            raise PlanError(f"Task {key}: protected must be a list of strings.")
        if not all(isinstance(p, str) for p in protected):
            raise PlanError(f"Task {key}: protected must be a list of strings.")
        if not isinstance(after, list):
            raise PlanError(f"Task {key}: after must be a list of keys of earlier tasks.")
        if not all(isinstance(a, str) for a in after):
            raise PlanError(f"Task {key}: after must be a list of keys of earlier tasks.")
        for a in after:
            if a not in seen_keys:
                raise PlanError(f"Task {key}: after references '{a}' which is not an earlier task key.")
        if role is not None and role not in ("coder", "coder_hard"):
            raise PlanError(f"Task {key}: role must be 'coder', 'coder_hard' or null.")

        if key in seen_keys:
            raise PlanError(f"Task {key}: key '{key}' is duplicated.")
        seen_keys.append(key)

        # A task whose files are all under tests/ is invalid.
        if not is_go and all(f.startswith(test_dir + "/") for f in files):
            raise PlanError(f"Task {key}: files are all under '{test_dir}/', which is not allowed.")

        # A task cannot write to its own test files.
        test_set = set(tests)
        for f in files:
            if f in test_set:
                raise PlanError(f"Task {key}: file '{f}' is in both 'files' and 'tests'.")

        overlap = {f for f in files if f in set(protected)}
        if overlap:
            for path in sorted(overlap):
                raise PlanError(f"Task {key}: path '{path}' is listed in both 'files' and 'protected'.")

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
        "original": copy.deepcopy(tasks),
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
        raise PlanNotFound(pid)
    p = json.loads(path.read_text(encoding="utf-8"))
    for t in p.get("tasks", []):
        t.setdefault("protected", [])
        t.setdefault("after", [])
        t.setdefault("role", "coder")
    return p


def save_critique(state_dir, plan_id, problems):
    p = load_plan(state_dir, plan_id)
    p["critique"] = problems
    state_dir = Path(state_dir)
    path = state_dir / "plans" / f"{plan_id}.json"
    path.write_text(json.dumps(p, indent=1, ensure_ascii=False), encoding="utf-8")


def edited(plan):
    return plan_hash(plan["tasks"]) != plan["hash"]


def mark_added(state_dir, pid, task_ids):
    state_dir = Path(state_dir)
    path = state_dir / "plans" / f"{pid}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["status"] = "added"
    data["task_ids"] = task_ids
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def convert_messages(text):
    return [
        {"role": "system", "content": CONVERT_SYSTEM},
        {"role": "user", "content": text},
    ]
