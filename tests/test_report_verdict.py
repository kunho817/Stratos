"""Tests for task T023: summarize() understands 'verdict' events, a person's judgment on a task's result.

A verdict event looks like {"kind": "verdict", "task": "T001", "result": "reset_by_human", "reason": "..."}.
Every 'passed' outcome of that task that comes BEFORE the verdict in the event list (and after the task's previous
verdict, if any) is counted as 'discarded' instead of 'passed', and its call's tokens count as wasted tokens.
Outcomes after the verdict, and outcomes of other tasks, are not affected. summarize() also returns
'human_verdicts': the number of verdict events (0 when there are none). The `since` filter applies to verdict
events like any other event."""
from stratos.report import summarize


def call(cid, task, p, c):
    return {"kind": "call", "call_id": cid, "task": task, "model": "m", "prompt_tokens": p, "completion_tokens": c,
            "seconds": 1.0}


def outcome(cid, task, result):
    return {"kind": "outcome", "call_id": cid, "task": task, "result": result}


def verdict(task):
    return {"kind": "verdict", "task": task, "result": "reset_by_human", "reason": "harness bug"}


def test_verdict_turns_earlier_passes_into_discards():
    ev = [call("a", "T1", 100, 10), outcome("a", "T1", "failed"),
          call("b", "T1", 200, 20), outcome("b", "T1", "passed"),
          verdict("T1")]
    s = summarize(ev)
    assert s["outcomes"] == {"failed": 1, "discarded": 1}
    assert s["wasted_tokens"] == 110 + 220
    assert s["human_verdicts"] == 1


def test_passes_after_the_verdict_stay_passed():
    ev = [call("a", "T1", 100, 10), outcome("a", "T1", "passed"),
          verdict("T1"),
          call("b", "T1", 200, 20), outcome("b", "T1", "passed")]
    s = summarize(ev)
    assert s["outcomes"] == {"discarded": 1, "passed": 1}
    assert s["wasted_tokens"] == 110


def test_other_tasks_are_not_affected():
    ev = [call("a", "T1", 100, 10), outcome("a", "T1", "passed"),
          call("b", "T2", 200, 20), outcome("b", "T2", "passed"),
          verdict("T1")]
    s = summarize(ev)
    assert s["outcomes"] == {"discarded": 1, "passed": 1}
    assert s["wasted_tokens"] == 110


def test_a_second_verdict_only_takes_passes_since_the_first():
    ev = [call("a", "T1", 100, 10), outcome("a", "T1", "passed"), verdict("T1"),
          call("b", "T1", 200, 20), outcome("b", "T1", "passed"), verdict("T1"),
          call("c", "T1", 300, 30), outcome("c", "T1", "passed")]
    s = summarize(ev)
    assert s["outcomes"] == {"discarded": 2, "passed": 1}
    assert s["wasted_tokens"] == 110 + 220
    assert s["human_verdicts"] == 2


def test_no_verdicts():
    ev = [call("a", "T1", 100, 10), outcome("a", "T1", "passed")]
    s = summarize(ev)
    assert s["outcomes"] == {"passed": 1}
    assert s["human_verdicts"] == 0
    assert s["wasted_tokens"] == 0


def test_verdict_with_no_passes_changes_no_outcome():
    ev = [call("a", "T1", 100, 10), outcome("a", "T1", "failed"), verdict("T1")]
    s = summarize(ev)
    assert s["outcomes"] == {"failed": 1}
    assert s["wasted_tokens"] == 110
    assert s["human_verdicts"] == 1


def test_since_filters_verdicts_too():
    ev = [dict(call("a", "T1", 100, 10), ts=10.0), dict(outcome("a", "T1", "passed"), ts=11.0),
          dict(verdict("T1"), ts=5.0)]
    s = summarize(ev, since=8.0)
    assert s["outcomes"] == {"passed": 1}
    assert s["human_verdicts"] == 0
