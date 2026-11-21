"""Tests for task plan_notfound: stratos/plan.py gains PlanNotFound(KeyError) and load_plan fills optional keys.

PlanNotFound is a subclass of KeyError. load_plan(state_dir, pid) raises PlanNotFound(pid) when the plan file
is missing (the old bare KeyError stays compatible because PlanNotFound is a KeyError). After loading the JSON,
each task dict in the plan's "tasks" list gets setdefault("protected", []), setdefault("after", []),
setdefault("role", "coder"); existing values (including role None) are left untouched. Required keys
(key, title, goal, files, tests) are NOT setdefault'd."""

import json

import pytest

from stratos import plan


def test_plan_not_found_is_key_error():
    assert issubclass(plan.PlanNotFound, KeyError)
    e = plan.PlanNotFound("P404")
    assert isinstance(e, KeyError)
    # str(KeyError("P404")) is "'P404'"
    assert str(e) == "'P404'"
    assert e.args[0] == "P404"


def test_load_plan_raises_plan_not_found(tmp_path):
    """Missing plan file raises PlanNotFound(pid), not a bare KeyError."""
    with pytest.raises(plan.PlanNotFound) as exc_info:
        plan.load_plan(tmp_path, "P404")
    # The pid is the argument
    assert exc_info.value.args[0] == "P404"


def test_plan_not_found_still_works_with_key_error_catch(tmp_path):
    """Code that catches KeyError (the CLI) still catches PlanNotFound."""
    with pytest.raises(KeyError):
        plan.load_plan(tmp_path, "P404")


def test_load_plan_setdefaults_missing_optional_keys(tmp_path):
    """A task with no "protected", "after", "role" keys gets them filled."""
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    task = {"key": "a", "title": "T", "goal": "g", "files": ["stratos/a.py"],
            "tests": ["tests/test_a.py"]}
    plan_data = {"id": "P001", "goal": "G", "tasks": [task], "status": "draft", "hash": "x"}
    (plans_dir / "P001.json").write_text(json.dumps(plan_data), encoding="utf-8")
    p = plan.load_plan(tmp_path, "P001")
    t = p["tasks"][0]
    # setdefault adds these three
    assert t["protected"] == []
    assert t["after"] == []
    assert t["role"] == "coder"


def test_load_plan_does_not_overwrite_existing_values(tmp_path):
    """Existing protected/after/role values are not changed by setdefault."""
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    task = {"key": "a", "title": "T", "goal": "g", "files": ["stratos/a.py"],
            "tests": ["tests/test_a.py"], "protected": ["x.py"], "after": ["b"],
            "role": "coder_hard"}
    plan_data = {"id": "P001", "goal": "G", "tasks": [task], "status": "draft", "hash": "x"}
    (plans_dir / "P001.json").write_text(json.dumps(plan_data), encoding="utf-8")
    p = plan.load_plan(tmp_path, "P001")
    t = p["tasks"][0]
    # Key exists, so setdefault leaves it alone
    assert t["protected"] == ["x.py"]
    assert t["after"] == ["b"]
    assert t["role"] == "coder_hard"


def test_load_plan_preserves_role_none(tmp_path):
    """role: None stays None; setdefault does not overwrite an existing key."""
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    task = {"key": "a", "title": "T", "goal": "g", "files": ["stratos/a.py"],
            "tests": ["tests/test_a.py"], "role": None}
    plan_data = {"id": "P001", "goal": "G", "tasks": [task], "status": "draft", "hash": "x"}
    (plans_dir / "P001.json").write_text(json.dumps(plan_data), encoding="utf-8")
    p = plan.load_plan(tmp_path, "P001")
    t = p["tasks"][0]
    # The key is present (value None), so setdefault("role", "coder") does nothing
    assert t["role"] is None


def test_load_plan_does_not_setdefault_required_keys(tmp_path):
    """Missing required keys (key, title, goal, files, tests) are NOT added by load_plan."""
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    # Build a task that is missing "title" and "goal"
    task = {"key": "a", "files": ["stratos/a.py"], "tests": ["tests/test_a.py"]}
    plan_data = {"id": "P001", "goal": "G", "tasks": [task], "status": "draft", "hash": "x"}
    (plans_dir / "P001.json").write_text(json.dumps(plan_data), encoding="utf-8")
    p = plan.load_plan(tmp_path, "P001")
    t = p["tasks"][0]
    # Required keys must NOT be setdefault'd
    assert "title" not in t
    assert "goal" not in t
    # Optional keys ARE added
    assert t["protected"] == []
    assert t["after"] == []
    assert t["role"] == "coder"


def test_load_plan_on_parse_plan_tasks_is_unchanged(tmp_path):
    """A plan saved from parse_plan output has all 8 keys; load_plan changes nothing."""
    tasks = plan.parse_plan(json.dumps({"tasks": [
        {"key": "a", "title": "Add f", "goal": "Add f to x.", "files": ["stratos/x.py"],
         "tests": ["tests/test_x.py"]}
    ]}))
    # parse_plan gives: protected=[], after=[], role=None
    pid = plan.save_plan(tmp_path, "Make it fly.", tasks)
    p = plan.load_plan(tmp_path, pid)
    t = p["tasks"][0]
    # All keys exist, so setdefault leaves them: protected=[], after=[], role=None
    assert t["protected"] == []
    assert t["after"] == []
    assert t["role"] is None


def test_load_plan_setdefaults_each_task_independently(tmp_path):
    """Every task in the list gets its own defaults; one task's value does not affect another."""
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    t1 = {"key": "a", "title": "A", "goal": "g1", "files": ["a.py"], "tests": ["tests/test_a.py"]}
    t2 = {"key": "b", "title": "B", "goal": "g2", "files": ["b.py"], "tests": ["tests/test_b.py"],
          "protected": ["a.py"]}
    plan_data = {"id": "P001", "goal": "G", "tasks": [t1, t2], "status": "draft", "hash": "x"}
    (plans_dir / "P001.json").write_text(json.dumps(plan_data), encoding="utf-8")
    p = plan.load_plan(tmp_path, "P001")
    # t1 gets all three defaults
    assert p["tasks"][0]["protected"] == []
    assert p["tasks"][0]["after"] == []
    assert p["tasks"][0]["role"] == "coder"
    # t2 keeps its protected; after and role get defaults
    assert p["tasks"][1]["protected"] == ["a.py"]
    assert p["tasks"][1]["after"] == []
    assert p["tasks"][1]["role"] == "coder"
