"""Tests for task plan-add-feature: cmd_plan_add appends the whole feature goal to each task.

In stratos/__main__.py cmd_plan_add, when calling add_one for each task, the goal string passed to
add_one is: task["goal"] + "\n\nTHE WHOLE FEATURE (this task is one part of it; its exact formats
and numbers hold):\n" + plan["goal"]. The plan's goal is read from load_plan(state_dir, pid).
The "added T00N: title" print, mark_added, telemetry "plan" event, and the draft-status check all
stay as they were.

OUTDATED: tests/test_cli_plan.py::test_plan_add_stores_goals - stored goals now include the feature
block appended by plan-add; test_plan_add_stores_goals checks the bare task goal, which is no longer
the full stored goal.
"""
import json

import pytest

from stratos import __main__ as cli
from stratos import config
from stratos.plan import save_plan, load_plan
from stratos.state import Store

FEATURE = "Levels must be 1-5; score = sum(level) * 10; grid 10x10."
PREFIX = "\n\nTHE WHOLE FEATURE (this task is one part of it; its exact formats and numbers hold):\n"

T1 = {"key": "a", "title": "Add f", "goal": "Add f to x.py.",
      "files": ["pkg/x.py"], "tests": ["tests/test_x.py"],
      "protected": [], "after": [], "role": "coder"}

T2 = {"key": "b", "title": "Use f", "goal": "Call f in y.py.",
      "files": ["pkg/y.py"], "tests": ["tests/test_y.py"],
      "protected": [], "after": ["a"], "role": "coder"}


def _setup(tmp_path, monkeypatch):
    """Point config at tmp_path; disable jev shadow."""
    state = tmp_path / "state"
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", repo)
    monkeypatch.setattr(config, "JEV_SHADOW", False)
    return state


def test_feature_appended_to_single_task(tmp_path, monkeypatch):
    """One task: stored goal = task goal + prefix + plan goal."""
    state = _setup(tmp_path, monkeypatch)
    # save_plan creates P001 with goal=FEATURE and tasks=[T1].
    pid = save_plan(state, FEATURE, [T1])
    assert cli.main(["plan-add", pid]) == 0
    store = Store(state)
    t = store.get("T001")
    # Expected: "Add f to x.py." + PREFIX + FEATURE
    expected = "Add f to x.py." + PREFIX + FEATURE
    assert t["goal"] == expected


def test_feature_appended_to_two_tasks(tmp_path, monkeypatch):
    """Two tasks: both stored goals have the feature appended."""
    state = _setup(tmp_path, monkeypatch)
    pid = save_plan(state, FEATURE, [T1, T2])
    assert cli.main(["plan-add", pid]) == 0
    store = Store(state)
    t1 = store.get("T001")
    t2 = store.get("T002")
    # Step: T001 goal = task goal + prefix + feature
    assert t1["goal"] == "Add f to x.py." + PREFIX + FEATURE
    # Step: T002 goal = task goal + prefix + feature
    assert t2["goal"] == "Call f in y.py." + PREFIX + FEATURE


def test_exact_format_of_feature_block(tmp_path, monkeypatch):
    """Split the stored goal: parts[0] is the task goal; parts[1] is the header + plan goal."""
    state = _setup(tmp_path, monkeypatch)
    pid = save_plan(state, FEATURE, [T1])
    cli.main(["plan-add", pid])
    goal = Store(state).get("T001")["goal"]
    marker = "THE WHOLE FEATURE (this task is one part of it; its exact formats and numbers hold):\n"
    # Step: splitting on "\n\n" gives task goal as parts[0].
    parts = goal.split("\n\n")
    # Step: parts[0] = "Add f to x.py."
    assert parts[0] == "Add f to x.py."
    # Step: parts[1] = header + "\n" + FEATURE
    assert parts[1] == marker + FEATURE


def test_empty_plan_goal_still_appends(tmp_path, monkeypatch):
    """Plan goal = "" → the prefix is appended with nothing after it."""
    state = _setup(tmp_path, monkeypatch)
    pid = save_plan(state, "", [T1])
    cli.main(["plan-add", pid])
    goal = Store(state).get("T001")["goal"]
    # Step: goal = task goal + PREFIX + ""
    assert goal == "Add f to x.py." + PREFIX


def test_feature_from_plan_goal_not_task_goal(tmp_path, monkeypatch):
    """The appended feature text is p["goal"], not any task's own goal."""
    state = _setup(tmp_path, monkeypatch)
    feature = "Grid is 8x8; levels 1-3."
    # save_plan stores the plan goal as feature; task goal is "Add f to x.py."
    pid = save_plan(state, feature, [T1])
    cli.main(["plan-add", pid])
    stored = Store(state).get("T001")["goal"]
    # Step: stored = task goal + PREFIX + feature
    assert stored == "Add f to x.py." + PREFIX + feature
    # Step: the feature part equals the plan goal, not the task goal.
    feature_part = stored[len("Add f to x.py.") + len(PREFIX):]
    assert feature_part == feature
    # Step: the task goal "Add f to x.py." does NOT appear inside the feature part.
    assert "Add f to x.py." not in feature_part


def test_added_messages_still_printed(tmp_path, monkeypatch, capsys):
    """Each add_one call prints 'added T00N: title' as before."""
    state = _setup(tmp_path, monkeypatch)
    pid = save_plan(state, FEATURE, [T1, T2])
    cli.main(["plan-add", pid])
    out = capsys.readouterr().out
    # Step: T1 title "Add f" → "added T001: Add f"
    assert "added T001: Add f" in out
    # Step: T2 title "Use f" → "added T002: Use f"
    assert "added T002: Use f" in out


def test_plan_status_check_still_works(tmp_path, monkeypatch, capsys):
    """Second plan-add on the same plan returns 1: 'was already added'."""
    state = _setup(tmp_path, monkeypatch)
    pid = save_plan(state, FEATURE, [T1])
    # Step: first add succeeds.
    assert cli.main(["plan-add", pid]) == 0
    # Step: second add refuses.
    assert cli.main(["plan-add", pid]) == 1
    # Step: stderr says "was already added".
    assert "was already added" in capsys.readouterr().err


def test_mark_added_still_called(tmp_path, monkeypatch):
    """After plan-add, plan status is 'added' and task_ids maps keys to ids."""
    state = _setup(tmp_path, monkeypatch)
    pid = save_plan(state, FEATURE, [T1, T2])
    cli.main(["plan-add", pid])
    p = load_plan(state, pid)
    # Step: status is "added"
    assert p["status"] == "added"
    # Step: task_ids maps plan keys to task ids in order.
    assert p["task_ids"] == {"a": "T001", "b": "T002"}


def test_telemetry_plan_event_recorded(tmp_path, monkeypatch):
    """A telemetry 'plan' event is recorded with plan, tasks count, edited."""
    state = _setup(tmp_path, monkeypatch)
    pid = save_plan(state, FEATURE, [T1])
    cli.main(["plan-add", pid])
    events = [json.loads(x) for x in
              (state / "telemetry.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    plan_events = [e for e in events if e["kind"] == "plan"]
    # Step: exactly one plan event
    assert len(plan_events) == 1
    # Step: plan event fields: plan=pid, tasks=1
    assert plan_events[0]["plan"] == pid
    assert plan_events[0]["tasks"] == 1


def test_after_ids_resolved_with_feature_goal(tmp_path, monkeypatch):
    """T002's after list uses T001's id, and its goal includes the feature."""
    state = _setup(tmp_path, monkeypatch)
    pid = save_plan(state, FEATURE, [T1, T2])
    cli.main(["plan-add", pid])
    t2 = Store(state).get("T002")
    # Step: key "a" mapped to T001, so after = ["T001"]
    assert t2["after"] == ["T001"]
    # Step: goal includes the feature
    assert t2["goal"] == "Call f in y.py." + PREFIX + FEATURE


def test_plan_notfound_still_handled(tmp_path, monkeypatch, capsys):
    """A nonexistent plan prints 'no such plan' and returns 1."""
    state = _setup(tmp_path, monkeypatch)
    assert cli.main(["plan-add", "P404"]) == 1
    # Step: stderr contains "no such plan: P404"
    assert "no such plan: P404" in capsys.readouterr().err
