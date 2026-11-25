"""Tests for task plan-add-protect-tests: cmd_plan_add does not protect a test file the task writes.

In stratos/__main__.py cmd_plan_add, when building the protected list for each plan task:
- Start with prot = list(t.get("protected", [])).
- Remove from prot any path that is also in t["files"] (files win).
- For each path p in t["tests"]: append p to prot only when p is NOT in t["files"] and p is NOT already in prot.
- The task is added with that prot; files, tests, goal, after, role and everything else in cmd_plan_add stay.

Example: plan task files ["stratos/facts.py", "tests/test_facts.py"], tests ["tests/test_new.py", "tests/test_facts.py"],
protected ["stratos/config.py"] → added with protected ["stratos/config.py", "tests/test_new.py"] and
files ["stratos/facts.py", "tests/test_facts.py"].
"""
import json

import pytest

from stratos import __main__ as cli
from stratos import config
from stratos.plan import save_plan, load_plan
from stratos.state import Store


def _setup(tmp_path, monkeypatch):
    state = tmp_path / "state"
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", repo)
    monkeypatch.setattr(config, "JEV_SHADOW", False)
    return state


def test_test_in_files_is_not_protected(tmp_path, monkeypatch):
    """A test path that is also in files is NOT appended to prot."""
    state = _setup(tmp_path, monkeypatch)
    task = {"key": "a", "title": "A", "goal": "g",
            "files": ["stratos/facts.py", "tests/test_facts.py"],
            "tests": ["tests/test_new.py", "tests/test_facts.py"],
            "protected": ["stratos/config.py"],
            "after": [], "role": "coder"}
    pid = save_plan(state, "FEATURE", [task])
    assert cli.main(["plan-add", pid]) == 0
    t = Store(state).get("T001")
    # Step: files unchanged from plan
    assert t["files"] == ["stratos/facts.py", "tests/test_facts.py"]
    # Step: prot starts as ["stratos/config.py"]
    # Step: remove from prot anything in files: "stratos/config.py" not in files → stays
    # Step: "tests/test_facts.py" in tests AND in files → skip
    # Step: "tests/test_new.py" in tests, NOT in files, NOT in prot → append
    # Expected prot: ["stratos/config.py", "tests/test_new.py"]
    assert t["protected"] == ["stratos/config.py", "tests/test_new.py"]


def test_protected_path_in_files_is_removed(tmp_path, monkeypatch):
    """A path in both the plan task's protected list and its files list is removed from prot (files win)."""
    state = _setup(tmp_path, monkeypatch)
    task = {"key": "a", "title": "A", "goal": "g",
            "files": ["pkg/x.py", "pkg/y.py"],
            "tests": ["tests/test_x.py"],
            "protected": ["pkg/y.py", "pkg/z.py"],
            "after": [], "role": "coder"}
    pid = save_plan(state, "FEATURE", [task])
    assert cli.main(["plan-add", pid]) == 0
    t = Store(state).get("T001")
    # Step: prot starts as ["pkg/y.py", "pkg/z.py"]
    # Step: "pkg/y.py" is in files → remove from prot; prot = ["pkg/z.py"]
    # Step: "pkg/z.py" not in files → stays
    # Step: "tests/test_x.py" in tests, not in files, not in prot → append
    # Expected: ["pkg/z.py", "tests/test_x.py"]
    assert t["protected"] == ["pkg/z.py", "tests/test_x.py"]


def test_all_tests_appended_when_none_in_files(tmp_path, monkeypatch):
    """When no test path is in files, all tests are appended to prot."""
    state = _setup(tmp_path, monkeypatch)
    task = {"key": "a", "title": "A", "goal": "g",
            "files": ["pkg/x.py"],
            "tests": ["tests/test_a.py", "tests/test_b.py"],
            "protected": [],
            "after": [], "role": "coder"}
    pid = save_plan(state, "FEATURE", [task])
    assert cli.main(["plan-add", pid]) == 0
    t = Store(state).get("T001")
    # Step: prot starts as []
    # Step: "tests/test_a.py" not in files, not in prot → append
    # Step: "tests/test_b.py" not in files, not in prot → append
    # Expected: ["tests/test_a.py", "tests/test_b.py"]
    assert t["protected"] == ["tests/test_a.py", "tests/test_b.py"]


def test_test_already_in_protected_not_duplicated(tmp_path, monkeypatch):
    """A test path already in prot (and not in files) is not appended again."""
    state = _setup(tmp_path, monkeypatch)
    task = {"key": "a", "title": "A", "goal": "g",
            "files": ["pkg/x.py"],
            "tests": ["tests/test_a.py", "tests/test_b.py"],
            "protected": ["tests/test_a.py"],
            "after": [], "role": "coder"}
    pid = save_plan(state, "FEATURE", [task])
    assert cli.main(["plan-add", pid]) == 0
    t = Store(state).get("T001")
    # Step: prot starts as ["tests/test_a.py"]
    # Step: "tests/test_a.py" in tests, not in files, already in prot → skip
    # Step: "tests/test_b.py" in tests, not in files, not in prot → append
    # Expected: ["tests/test_a.py", "tests/test_b.py"]
    assert t["protected"] == ["tests/test_a.py", "tests/test_b.py"]


def test_the_example_from_the_task(tmp_path, monkeypatch):
    """The task's example: files ["stratos/facts.py", "tests/test_facts.py"],
    tests ["tests/test_new.py", "tests/test_facts.py"], protected ["stratos/config.py"]
    → stored protected ["stratos/config.py", "tests/test_new.py"]."""
    state = _setup(tmp_path, monkeypatch)
    task = {"key": "a", "title": "A", "goal": "g",
            "files": ["stratos/facts.py", "tests/test_facts.py"],
            "tests": ["tests/test_new.py", "tests/test_facts.py"],
            "protected": ["stratos/config.py"],
            "after": [], "role": "coder"}
    pid = save_plan(state, "FEATURE", [task])
    assert cli.main(["plan-add", pid]) == 0
    t = Store(state).get("T001")
    # Step: files unchanged
    assert t["files"] == ["stratos/facts.py", "tests/test_facts.py"]
    # Step: prot = ["stratos/config.py", "tests/test_new.py"]
    # Step: "stratos/config.py" not in files → stays
    # Step: "tests/test_facts.py" in tests AND in files → skip
    # Step: "tests/test_new.py" in tests, not in files, not in prot → append
    assert t["protected"] == ["stratos/config.py", "tests/test_new.py"]


def test_files_list_is_unchanged(tmp_path, monkeypatch):
    """The stored task's files list equals the plan task's files list."""
    state = _setup(tmp_path, monkeypatch)
    task = {"key": "a", "title": "A", "goal": "g",
            "files": ["pkg/x.py", "pkg/y.py", "pkg/z.py"],
            "tests": ["tests/test_x.py", "pkg/y.py"],
            "protected": ["pkg/w.py"],
            "after": [], "role": "coder"}
    pid = save_plan(state, "FEATURE", [task])
    assert cli.main(["plan-add", pid]) == 0
    t = Store(state).get("T001")
    # Step: files = plan task files
    assert t["files"] == ["pkg/x.py", "pkg/y.py", "pkg/z.py"]
    # Step: prot starts as ["pkg/w.py"]
    # Step: "pkg/w.py" not in files → stays
    # Step: "tests/test_x.py" in tests, not in files, not in prot → append
    # Step: "pkg/y.py" in tests AND in files → skip
    # Expected: ["pkg/w.py", "tests/test_x.py"]
    assert t["protected"] == ["pkg/w.py", "tests/test_x.py"]


def test_two_tasks_independent_protected(tmp_path, monkeypatch):
    """Two tasks: each gets its own prot built from its own files/tests/protected."""
    state = _setup(tmp_path, monkeypatch)
    t1 = {"key": "a", "title": "A", "goal": "g1",
          "files": ["pkg/a.py", "tests/test_a.py"],
          "tests": ["tests/test_a.py", "tests/test_new_a.py"],
          "protected": ["pkg/shared.py"],
          "after": [], "role": "coder"}
    t2 = {"key": "b", "title": "B", "goal": "g2",
          "files": ["pkg/b.py"],
          "tests": ["tests/test_b.py"],
          "protected": ["pkg/a.py"],
          "after": ["a"], "role": "coder"}
    pid = save_plan(state, "FEATURE", [t1, t2])
    assert cli.main(["plan-add", pid]) == 0
    s = Store(state)
    # Step: T001 prot starts as ["pkg/shared.py"]
    # Step: "tests/test_a.py" in tests AND files → skip
    # Step: "tests/test_new_a.py" in tests, not in files, not in prot → append
    # Expected T001 prot: ["pkg/shared.py", "tests/test_new_a.py"]
    assert s.get("T001")["protected"] == ["pkg/shared.py", "tests/test_new_a.py"]
    # Step: T002 prot starts as ["pkg/a.py"]
    # Step: "pkg/a.py" not in files → stays
    # Step: "tests/test_b.py" not in files, not in prot → append
    # Expected T002 prot: ["pkg/a.py", "tests/test_b.py"]
    assert s.get("T002")["protected"] == ["pkg/a.py", "tests/test_b.py"]


def test_every_test_in_files_means_empty_prot(tmp_path, monkeypatch):
    """When every test is also in files, prot stays empty."""
    state = _setup(tmp_path, monkeypatch)
    task = {"key": "a", "title": "A", "goal": "g",
            "files": ["tests/test_x.py", "tests/test_y.py", "pkg/x.py"],
            "tests": ["tests/test_x.py", "tests/test_y.py"],
            "protected": [],
            "after": [], "role": "coder"}
    pid = save_plan(state, "FEATURE", [task])
    assert cli.main(["plan-add", pid]) == 0
    t = Store(state).get("T001")
    # Step: prot starts as []
    # Step: "tests/test_x.py" in files → skip; "tests/test_y.py" in files → skip
    # Expected: []
    assert t["protected"] == []


def test_no_overlap_all_tests_appended(tmp_path, monkeypatch):
    """When no test path overlaps files, all tests are appended as before."""
    state = _setup(tmp_path, monkeypatch)
    task = {"key": "a", "title": "A", "goal": "g",
            "files": ["pkg/x.py"],
            "tests": ["tests/test_a.py"],
            "protected": ["pkg/y.py"],
            "after": [], "role": "coder"}
    pid = save_plan(state, "FEATURE", [task])
    assert cli.main(["plan-add", pid]) == 0
    t = Store(state).get("T001")
    # Step: prot = ["pkg/y.py"]
    # Step: "pkg/y.py" not in files → stays
    # Step: "tests/test_a.py" not in files, not in prot → append
    # Expected: ["pkg/y.py", "tests/test_a.py"]
    assert t["protected"] == ["pkg/y.py", "tests/test_a.py"]


def test_plan_status_check_still_works(tmp_path, monkeypatch, capsys):
    """plan-add on an already-added plan returns 1; the protected change does not affect status check."""
    state = _setup(tmp_path, monkeypatch)
    task = {"key": "a", "title": "A", "goal": "g",
            "files": ["pkg/x.py"], "tests": ["tests/test_x.py"],
            "protected": [], "after": [], "role": "coder"}
    pid = save_plan(state, "FEATURE", [task])
    assert cli.main(["plan-add", pid]) == 0
    assert cli.main(["plan-add", pid]) == 1
    # Step: stderr says "was already added"
    assert "was already added" in capsys.readouterr().err


def test_mark_added_still_called(tmp_path, monkeypatch):
    """After plan-add the plan is marked added with key-to-id mapping."""
    state = _setup(tmp_path, monkeypatch)
    task = {"key": "a", "title": "A", "goal": "g",
            "files": ["pkg/x.py"], "tests": ["tests/test_x.py"],
            "protected": [], "after": [], "role": "coder"}
    pid = save_plan(state, "FEATURE", [task])
    assert cli.main(["plan-add", pid]) == 0
    p = load_plan(state, pid)
    # Step: status is "added"
    assert p["status"] == "added"
    # Step: task_ids maps key "a" to "T001"
    assert p["task_ids"] == {"a": "T001"}


def test_telemetry_plan_event_recorded(tmp_path, monkeypatch):
    """The telemetry 'plan' event is recorded with plan, tasks, edited."""
    state = _setup(tmp_path, monkeypatch)
    task = {"key": "a", "title": "A", "goal": "g",
            "files": ["pkg/x.py"], "tests": ["tests/test_x.py"],
            "protected": [], "after": [], "role": "coder"}
    pid = save_plan(state, "FEATURE", [task])
    assert cli.main(["plan-add", pid]) == 0
    events = [json.loads(x) for x in
              (state / "telemetry.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    plan_events = [e for e in events if e["kind"] == "plan"]
    # Step: exactly one plan event with plan=pid, tasks=1
    assert len(plan_events) == 1
    assert plan_events[0]["plan"] == pid
    assert plan_events[0]["tasks"] == 1


def test_after_ids_still_resolved(tmp_path, monkeypatch):
    """After ids are resolved from plan keys to task ids as before."""
    state = _setup(tmp_path, monkeypatch)
    t1 = {"key": "a", "title": "A", "goal": "g",
          "files": ["pkg/a.py"], "tests": ["tests/test_a.py"],
          "protected": [], "after": [], "role": "coder"}
    t2 = {"key": "b", "title": "B", "goal": "g2",
          "files": ["pkg/b.py"], "tests": ["tests/test_b.py"],
          "protected": [], "after": ["a"], "role": "coder"}
    pid = save_plan(state, "FEATURE", [t1, t2])
    assert cli.main(["plan-add", pid]) == 0
    s = Store(state)
    # Step: T002 after = ["T001"]
    assert s.get("T002")["after"] == ["T001"]


def test_tests_list_stays_as_the_plan(tmp_path, monkeypatch):
    """The stored task's tests list equals the plan task's tests list unchanged."""
    state = _setup(tmp_path, monkeypatch)
    task = {"key": "a", "title": "A", "goal": "g",
            "files": ["pkg/x.py", "tests/test_facts.py"],
            "tests": ["tests/test_new.py", "tests/test_facts.py"],
            "protected": ["pkg/y.py"],
            "after": [], "role": "coder"}
    pid = save_plan(state, "FEATURE", [task])
    assert cli.main(["plan-add", pid]) == 0
    t = Store(state).get("T001")
    # Step: tests unchanged
    assert t["tests"] == ["tests/test_new.py", "tests/test_facts.py"]
    # Step: prot: "pkg/y.py" not in files → stays
    # Step: "tests/test_new.py" not in files, not in prot → append
    # Step: "tests/test_facts.py" in files → skip
    # Expected prot: ["pkg/y.py", "tests/test_new.py"]
    assert t["protected"] == ["pkg/y.py", "tests/test_new.py"]
