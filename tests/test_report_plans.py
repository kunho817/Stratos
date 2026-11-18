"""Tests for plans_summary(plans, events) in stratos/report.py.

plans_summary takes a list of plan dicts (each with "id", "tasks", "status", "hash") and a list of telemetry
events. For each plan it returns a dict:
  - id: the plan's id
  - tasks_count: len(plan["tasks"])
  - status: the plan's status
  - edited: True if any "plan" telemetry event for that plan has edited==True, else False
  - drafts: a dict counting "test_draft" events for that plan by status keys
    collected, import_error, syntax_error, error, exists, missing
Returns a list of these dicts in plan order."""

import pytest

from stratos.report import plans_summary


def _plan(id, tasks, status="draft", hash="abc"):
    return {"id": id, "tasks": tasks, "status": status, "hash": hash}


def _plan_event(plan_id, edited):
    return {"ts": 1, "kind": "plan", "plan": plan_id, "tasks": 1, "edited": edited}


def _draft_event(plan_id, status, key="k1", file="tests/test_x.py"):
    return {"ts": 2, "kind": "test_draft", "plan": plan_id, "key": key, "file": file, "status": status}


def test_empty_plans_returns_empty_list():
    assert plans_summary([], []) == []


def test_single_plan_no_events():
    plans = [_plan("P001", [1, 2, 3], "draft")]
    result = plans_summary(plans, [])
    assert result == [
        {
            "id": "P001",
            "tasks_count": 3,
            "status": "draft",
            "edited": False,
            "drafts": {
                "collected": 0,
                "import_error": 0,
                "syntax_error": 0,
                "error": 0,
                "exists": 0,
                "missing": 0,
            },
        }
    ]


def test_single_plan_tasks_count_is_length():
    plans = [_plan("P002", [], "added")]
    result = plans_summary(plans, [])
    assert result[0]["tasks_count"] == 0
    assert result[0]["status"] == "added"


def test_plan_event_edited_true():
    plans = [_plan("P001", ["a"], "draft")]
    events = [_plan_event("P001", True)]
    result = plans_summary(plans, events)
    assert result[0]["edited"] is True


def test_plan_event_edited_false():
    plans = [_plan("P001", ["a"], "draft")]
    events = [_plan_event("P001", False)]
    result = plans_summary(plans, events)
    assert result[0]["edited"] is False


def test_plan_event_for_different_plan_does_not_match():
    plans = [_plan("P001", ["a"], "draft")]
    events = [_plan_event("P999", True)]
    result = plans_summary(plans, events)
    assert result[0]["edited"] is False


def test_multiple_plan_events_any_edited_true():
    plans = [_plan("P001", ["a"], "draft")]
    events = [_plan_event("P001", False), _plan_event("P001", True)]
    result = plans_summary(plans, events)
    assert result[0]["edited"] is True


def test_multiple_plan_events_all_false():
    plans = [_plan("P001", ["a"], "draft")]
    events = [_plan_event("P001", False), _plan_event("P001", False)]
    result = plans_summary(plans, events)
    assert result[0]["edited"] is False


def test_draft_events_counted_by_status():
    plans = [_plan("P001", ["a", "b"], "draft")]
    events = [
        _draft_event("P001", "collected"),
        _draft_event("P001", "collected"),
        _draft_event("P001", "import_error"),
        _draft_event("P001", "syntax_error"),
        _draft_event("P001", "error"),
        _draft_event("P001", "exists"),
        _draft_event("P001", "missing"),
    ]
    result = plans_summary(plans, events)
    assert result[0]["drafts"] == {
        "collected": 2,
        "import_error": 1,
        "syntax_error": 1,
        "error": 1,
        "exists": 1,
        "missing": 1,
    }


def test_draft_events_for_different_plan_ignored():
    plans = [_plan("P001", ["a"], "draft")]
    events = [_draft_event("P999", "collected")]
    result = plans_summary(plans, events)
    assert result[0]["drafts"] == {
        "collected": 0,
        "import_error": 0,
        "syntax_error": 0,
        "error": 0,
        "exists": 0,
        "missing": 0,
    }


def test_draft_events_missing_statuses_are_zero():
    plans = [_plan("P001", ["a"], "draft")]
    events = [_draft_event("P001", "collected")]
    result = plans_summary(plans, events)
    assert result[0]["drafts"] == {
        "collected": 1,
        "import_error": 0,
        "syntax_error": 0,
        "error": 0,
        "exists": 0,
        "missing": 0,
    }


def test_multiple_plans_preserve_order():
    plans = [
        _plan("P002", ["x", "y"], "added"),
        _plan("P001", ["a"], "draft"),
    ]
    events = [
        _plan_event("P001", True),
        _plan_event("P002", False),
        _draft_event("P001", "collected"),
        _draft_event("P002", "exists"),
        _draft_event("P002", "missing"),
    ]
    result = plans_summary(plans, events)
    assert len(result) == 2
    assert result[0]["id"] == "P002"
    assert result[0]["tasks_count"] == 2
    assert result[0]["status"] == "added"
    assert result[0]["edited"] is False
    assert result[0]["drafts"] == {
        "collected": 0,
        "import_error": 0,
        "syntax_error": 0,
        "error": 0,
        "exists": 1,
        "missing": 1,
    }
    assert result[1]["id"] == "P001"
    assert result[1]["tasks_count"] == 1
    assert result[1]["status"] == "draft"
    assert result[1]["edited"] is True
    assert result[1]["drafts"] == {
        "collected": 1,
        "import_error": 0,
        "syntax_error": 0,
        "error": 0,
        "exists": 0,
        "missing": 0,
    }


def test_non_matching_event_kinds_ignored():
    plans = [_plan("P001", ["a"], "draft")]
    events = [
        {"ts": 1, "kind": "call", "plan": "P001", "edited": True},
        {"ts": 2, "kind": "outcome", "plan": "P001", "status": "collected"},
    ]
    result = plans_summary(plans, events)
    assert result[0]["edited"] is False
    assert all(v == 0 for v in result[0]["drafts"].values())


def test_result_has_exactly_the_expected_keys():
    plans = [_plan("P001", [], "draft")]
    result = plans_summary(plans, [])
    assert set(result[0].keys()) == {"id", "tasks_count", "status", "edited", "drafts"}
    assert set(result[0]["drafts"].keys()) == {
        "collected",
        "import_error",
        "syntax_error",
        "error",
        "exists",
        "missing",
    }
