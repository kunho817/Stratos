"""Tests for task T061: stratos/plan.py, the planner's pure parts: the prompt, reading and checking a plan, keeping
plans on disk. A plan splits a feature goal into Stratos tasks; a person checks it before it is added (T062).

SYSTEM: the planner's system prompt (a str). It asks for JSON only, describes the task fields below, and says each
    task should be small (one function or one file), name its test files under tests/, and list in "after" the keys
    of earlier tasks it builds on.
repo_summary(root) -> str
    One line per .py file directly in root/"stratos", sorted by name: "stratos/<name> - <first line of its module
    docstring>" (ast.get_docstring), or "stratos/<name>" when it has none; then one line per .py file directly in
    root/"tests", sorted: "tests/<name>". Lines joined with "\n".
build_messages(goal, summary) -> [{"role": "system", "content": SYSTEM},
                                  {"role": "user", "content": f"PROJECT FILES:\n{summary}\n\nFEATURE GOAL:\n{goal}"}]
parse_plan(text) -> list of task dicts; raises PlanError (a ValueError) with a readable reason.
    The JSON is the last ```json fenced block in text when there is one, else the text from the first "{" to the
    last "}". It must be an object whose "tasks" is a non-empty list. Each task: "title" and "goal" non-empty strings;
    "files" a non-empty list of strings; "tests" a non-empty list of strings that start with "tests/" and end with
    ".py"; optional "protected" (list of strings, default []), "after" (list of keys of EARLIER tasks, default []),
    "role" ("coder", "coder_hard" or null; default None), "key" (string; default str(position), counting from 1).
    Keys must be unique. A reason names the task's key when one task is wrong. Returned dicts have exactly the keys
    key, title, goal, files, tests, protected, after, role.
PlanError
plan_hash(tasks) -> hashlib.sha256(json.dumps(tasks, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
save_plan(state_dir, goal, tasks) -> plan id
    Writes state_dir/"plans"/f"{pid}.json" (folder made when missing), pid = f"P{n:03d}" with n = number of .json
    files already there + 1, content {"id", "goal", "tasks", "status": "draft", "hash": plan_hash(tasks)} as UTF-8
    JSON (indent 1, ensure_ascii False).
load_plan(state_dir, pid) -> the dict; KeyError(pid) when the file does not exist.
edited(plan) -> plan_hash(plan["tasks"]) != plan["hash"]  (a person changed the tasks after the planner wrote them)
mark_added(state_dir, pid, task_ids) -> sets "status": "added" and "task_ids": task_ids (key -> task id) in the file."""
import json

import pytest

from stratos import plan

GOOD = {"tasks": [
    {"key": "a", "title": "Add f", "goal": "Add f to x.", "files": ["stratos/x.py"], "tests": ["tests/test_x.py"]},
    {"key": "b", "title": "Use f", "goal": "Call f in y.", "files": ["stratos/y.py"], "tests": ["tests/test_y.py"],
     "protected": ["stratos/x.py"], "after": ["a"], "role": "coder_hard"},
]}


def test_system_prompt():
    assert isinstance(plan.SYSTEM, str) and "JSON" in plan.SYSTEM
    for word in ("title", "goal", "files", "tests", "after", "tests/"):
        assert word in plan.SYSTEM


def test_repo_summary(tmp_path):
    (tmp_path / "stratos").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "stratos" / "b.py").write_text('"""Bee module.\n\nMore text."""\nX = 1\n', encoding="utf-8")
    (tmp_path / "stratos" / "a.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "stratos" / "notes.txt").write_text("not python", encoding="utf-8")
    (tmp_path / "tests" / "test_b.py").write_text("", encoding="utf-8")
    (tmp_path / "tests" / "test_a.py").write_text("", encoding="utf-8")
    assert plan.repo_summary(tmp_path) == "stratos/a.py\nstratos/b.py - Bee module.\ntests/test_a.py\ntests/test_b.py"


def test_build_messages():
    msgs = plan.build_messages("Make it fly.", "stratos/a.py")
    assert msgs == [{"role": "system", "content": plan.SYSTEM},
                    {"role": "user", "content": "PROJECT FILES:\nstratos/a.py\n\nFEATURE GOAL:\nMake it fly."}]


def test_parse_a_fenced_plan_and_defaults():
    text = "Here is the plan.\n```json\n" + json.dumps(GOOD) + "\n```\n"
    tasks = plan.parse_plan(text)
    assert tasks[0] == {"key": "a", "title": "Add f", "goal": "Add f to x.", "files": ["stratos/x.py"],
                        "tests": ["tests/test_x.py"], "protected": [], "after": [], "role": None}
    assert tasks[1]["after"] == ["a"] and tasks[1]["role"] == "coder_hard" and tasks[1]["protected"] == ["stratos/x.py"]


def test_last_fenced_block_wins_and_bare_json_works():
    draft = {"tasks": [{"title": "Old", "goal": "g", "files": ["f.py"], "tests": ["tests/t.py"]}]}
    text = "```json\n" + json.dumps(draft) + "\n```\nBetter:\n```json\n" + json.dumps(GOOD) + "\n```"
    assert [t["key"] for t in plan.parse_plan(text)] == ["a", "b"]
    bare = "Sure! " + json.dumps({"tasks": [{"title": "T", "goal": "g", "files": ["f.py"], "tests": ["tests/t.py"]},
                                            {"title": "U", "goal": "h", "files": ["g.py"], "tests": ["tests/u.py"],
                                             "after": ["1"]}]}) + " Done."
    tasks = plan.parse_plan(bare)
    assert [t["key"] for t in tasks] == ["1", "2"] and tasks[1]["after"] == ["1"]


@pytest.mark.parametrize("change, word", [
    (lambda p: p.update(tasks=[]), "tasks"),
    (lambda p: p["tasks"][0].update(title=""), "a"),
    (lambda p: p["tasks"][0].pop("goal"), "a"),
    (lambda p: p["tasks"][1].update(files=[]), "b"),
    (lambda p: p["tasks"][1].update(tests=["test_y.py"]), "b"),
    (lambda p: p["tasks"][1].update(tests=["tests/test_y.txt"]), "b"),
    (lambda p: p["tasks"][1].update(after=["zz"]), "b"),
    (lambda p: p["tasks"][0].update(after=["b"]), "a"),
    (lambda p: p["tasks"][1].update(role="reviewer"), "b"),
    (lambda p: p["tasks"][1].update(key="a"), "a"),
])
def test_bad_plans_are_refused(change, word):
    bad = json.loads(json.dumps(GOOD))
    change(bad)
    with pytest.raises(plan.PlanError) as e:
        plan.parse_plan(json.dumps(bad))
    assert word in str(e.value)
    assert isinstance(e.value, ValueError)


def test_no_json_at_all():
    with pytest.raises(plan.PlanError):
        plan.parse_plan("I cannot plan this.")
    with pytest.raises(plan.PlanError):
        plan.parse_plan("```json\n{not json}\n```")
    with pytest.raises(plan.PlanError):
        plan.parse_plan("[1, 2]")


def test_save_load_edit_and_mark(tmp_path):
    tasks = plan.parse_plan(json.dumps(GOOD))
    pid = plan.save_plan(tmp_path, "Make it fly.", tasks)
    assert pid == "P001"
    assert plan.save_plan(tmp_path, "Another.", tasks[:1]) == "P002"
    p = plan.load_plan(tmp_path, "P001")
    assert p["id"] == "P001" and p["goal"] == "Make it fly." and p["tasks"] == tasks and p["status"] == "draft"
    assert p["hash"] == plan.plan_hash(tasks) and not plan.edited(p)
    path = tmp_path / "plans" / "P001.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tasks"][0]["title"] = "Add f, carefully"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert plan.edited(plan.load_plan(tmp_path, "P001"))
    plan.mark_added(tmp_path, "P001", {"a": "T010", "b": "T011"})
    p = plan.load_plan(tmp_path, "P001")
    assert p["status"] == "added" and p["task_ids"] == {"a": "T010", "b": "T011"}
    assert p["tasks"][0]["title"] == "Add f, carefully"
    with pytest.raises(KeyError):
        plan.load_plan(tmp_path, "P009")


def test_plan_hash():
    import hashlib
    tasks = [{"key": "1", "title": "한글"}]
    want = hashlib.sha256(json.dumps(tasks, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    assert plan.plan_hash(tasks) == want
