"""Tests for task T055: report.replay_summary keeps runs with a reasoning budget apart.

A "call" event may hold reasoning_budget (T054). Runs are then grouped by (model, effort, reasoning_budget, task)
instead of (model, effort, task), and the summary key of a call with a reasoning_budget that is not None is
f"{model} effort={effort} budget={reasoning_budget}". Calls without the field (or with None) keep the key
f"{model} effort={effort}", so older replay.jsonl files read as before."""
from stratos import report


def call(cid, task, attempt, budget=None, seconds=10.0):
    e = {"kind": "call", "call_id": cid, "task": task, "attempt": attempt, "model": "m", "effort": "low",
         "seconds": seconds}
    if budget is not None:
        e["reasoning_budget"] = budget
    return e


def outcome(cid, result):
    return {"kind": "outcome", "call_id": cid, "result": result}


def test_budget_runs_get_their_own_key():
    events = [call("a", "T1", 1), outcome("a", "passed"),
              call("b", "T1", 1, budget=300, seconds=3.0), outcome("b", "failed"),
              call("c", "T1", 2, budget=300, seconds=4.0), outcome("c", "passed"),
              call("d", "T1", 1, budget=1000, seconds=5.0), outcome("d", "failed")]
    s = report.replay_summary(events)
    assert set(s) == {"m effort=low", "m effort=low budget=300", "m effort=low budget=1000"}
    assert (s["m effort=low"]["runs"], s["m effort=low"]["passed"]) == (1, 1)
    b = s["m effort=low budget=300"]
    assert (b["runs"], b["passed"], b["attempts"], b["seconds"]) == (1, 1, 2, 7.0)
    assert b["tasks"]["T1"] == {"runs": 1, "passed": 1, "attempts": 2, "seconds": 7.0}
    assert (s["m effort=low budget=1000"]["runs"], s["m effort=low budget=1000"]["passed"]) == (1, 0)


def test_a_later_attempt_joins_the_run_with_the_same_budget():
    events = [call("a", "T1", 1, budget=300), call("b", "T1", 1), call("c", "T1", 2, budget=300),
              outcome("c", "passed")]
    s = report.replay_summary(events)
    assert s["m effort=low budget=300"]["attempts"] == 2 and s["m effort=low budget=300"]["passed"] == 1
    assert s["m effort=low"]["attempts"] == 1 and s["m effort=low"]["passed"] == 0


def test_none_budget_is_the_plain_key():
    events = [dict(call("a", "T1", 1), reasoning_budget=None), outcome("a", "passed")]
    assert set(report.replay_summary(events)) == {"m effort=low"}
