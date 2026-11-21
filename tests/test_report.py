"""Tests for task T001, the first feature Stratos writes for itself: a summary of its own telemetry.
stratos/report.py does not exist yet; the coding model writes it."""
import pytest

from stratos import __main__ as cli, config, report
from stratos.report import plans_summary, summarize
from stratos.telemetry import Telemetry


EVENTS = [
    {"kind": "switch", "model": "tiel", "from_model": "gemma", "seconds": 8.0},
    {"kind": "call", "call_id": "a", "task": "T001", "model": "tiel", "prompt_tokens": 1000, "completion_tokens": 200,
     "seconds": 4.0},
    {"kind": "outcome", "call_id": "a", "task": "T001", "result": "failed"},
    {"kind": "call", "call_id": "b", "task": "T001", "model": "tiel", "prompt_tokens": 1200, "completion_tokens": 300,
     "seconds": 5.0},
    {"kind": "outcome", "call_id": "b", "task": "T001", "result": "passed"},
    {"kind": "switch", "model": "flint", "from_model": "tiel", "seconds": 30.5},
    {"kind": "call", "call_id": "c", "task": "T002", "model": "flint", "prompt_tokens": 800, "completion_tokens": None,
     "seconds": 20.0},
    {"kind": "outcome", "call_id": "c", "task": "T002", "result": "no_files"},
]


def test_totals():
    s = summarize(EVENTS)
    assert s["calls"] == 3
    assert s["prompt_tokens"] == 3000
    assert s["completion_tokens"] == 500          # a missing count (None) adds nothing
    assert s["switches"] == 2
    assert s["switch_seconds"] == 38.5


def test_per_model():
    m = summarize(EVENTS)["by_model"]
    assert set(m) == {"tiel", "flint"}
    assert m["tiel"] == {"calls": 2, "prompt_tokens": 2200, "completion_tokens": 500, "seconds": 9.0}
    assert m["flint"] == {"calls": 1, "prompt_tokens": 800, "completion_tokens": 0, "seconds": 20.0}


def test_outcomes_and_tokens_spent_on_failures():
    s = summarize(EVENTS)
    assert s["outcomes"] == {"failed": 1, "passed": 1, "no_files": 1}
    # tokens of calls whose outcome was not "passed" (prompt + completion): a = 1200, c = 800
    assert s["wasted_tokens"] == 2000


def test_empty():
    s = summarize([])
    assert s["calls"] == 0 and s["by_model"] == {} and s["outcomes"] == {} and s["wasted_tokens"] == 0


# ---- was test_report_diagnosis.py ----
# Tests for task T059: report.diagnosis_ab(events) and its line in `python -m stratos report`.
#
# diagnosis_ab(events) -> {"hinted": {"retries": n, "passed": k}, "plain": {"retries": n, "passed": k}}
#     For each "diagnosis" event (task, attempt, used; T058), in order: the first later "call" event with the same task
#     and attempt is that retry; its "outcome" event (same call_id) decides passed (result "passed") or not. used True
#     counts in "hinted", False in "plain". A diagnosis whose call or outcome is missing is not counted. Both keys are
#     always present (0/0 when empty).
# report: when there is at least one counted retry it prints
#     "diagnosis A/B: with diagnosis <k>/<n> retries passed, without <k>/<n>"
#     and nothing about it otherwise.


def diag(task, attempt, used):
    return {"kind": "diagnosis", "task": task, "attempt": attempt, "used": used, "chars": 10 if used else 0}


def call(cid, task, attempt):
    return {"kind": "call", "call_id": cid, "task": task, "attempt": attempt, "role": "coder", "model": "tiel"}


def outcome(cid, result):
    return {"kind": "outcome", "call_id": cid, "task": "x", "result": result}


def test_counts_both_halves():
    events = [call("a", "T1", 1), outcome("a", "failed"), diag("T1", 2, True), call("b", "T1", 2), outcome("b", "passed"),
              call("c", "T2", 1), outcome("c", "failed"), diag("T2", 2, False), call("d", "T2", 2), outcome("d", "failed"),
              diag("T2", 3, True), call("e", "T2", 3), outcome("e", "failed"),
              diag("T3", 2, False), call("f", "T3", 2), outcome("f", "passed")]
    assert report.diagnosis_ab(events) == {"hinted": {"retries": 2, "passed": 1}, "plain": {"retries": 2, "passed": 1}}


def test_matches_the_call_after_the_diagnosis():
    events = [call("old", "T1", 2), outcome("old", "passed"),          # an earlier run of the task: not this retry
              diag("T1", 2, True), call("x", "T9", 2), outcome("x", "passed"), call("new", "T1", 2), outcome("new", "failed")]
    assert report.diagnosis_ab(events)["hinted"] == {"retries": 1, "passed": 0}


def test_missing_call_or_outcome_is_skipped():
    events = [diag("T1", 2, True), diag("T2", 2, False), call("b", "T2", 2)]
    empty = {"hinted": {"retries": 0, "passed": 0}, "plain": {"retries": 0, "passed": 0}}
    assert report.diagnosis_ab(events) == empty
    assert report.diagnosis_ab([]) == empty


def record_all(t, events):
    for e in events:
        e = dict(e)
        kind = e.pop("kind")
        t.record(kind, **e)


def test_report_prints_the_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    record_all(Telemetry(tmp_path / "telemetry.jsonl"),
               [diag("T1", 2, True), call("b", "T1", 2), outcome("b", "passed"),
                diag("T2", 2, False), call("d", "T2", 2), outcome("d", "failed")])
    assert cli.main(["report"]) == 0
    assert "diagnosis A/B: with diagnosis 1/1 retries passed, without 0/1" in capsys.readouterr().out


def test_report_is_silent_without_diagnoses(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    t = Telemetry(tmp_path / "telemetry.jsonl")
    t.record("call", call_id="a", task="T1", attempt=1, role="coder", model="tiel", seconds=1.0)
    t.record("outcome", call_id="a", task="T1", result="passed")
    assert cli.main(["report"]) == 0
    assert "diagnosis" not in capsys.readouterr().out


# ---- was test_report_plans.py ----
# Tests for plans_summary(plans, events) in stratos/report.py.
#
# plans_summary takes a list of plan dicts (each with "id", "tasks", "status", "hash") and a list of telemetry
# events. For each plan it returns a dict:
#   - id: the plan's id
#   - tasks_count: len(plan["tasks"])
#   - status: the plan's status
#   - edited: True if any "plan" telemetry event for that plan has edited==True, else False
#   - drafts: a dict counting "test_draft" events for that plan by status keys
#     collected, import_error, syntax_error, error, exists, missing
# Returns a list of these dicts in plan order.


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
