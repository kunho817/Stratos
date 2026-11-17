"""Tests for task T051: report.replay_summary(events), how each model did in `stratos replay` (T049/T050).

events are the telemetry events of .stratos/replay.jsonl, in file order: "call" events (call_id, task, attempt, model,
effort, seconds) and "outcome" events (call_id, result). Other kinds are ignored.

A run is one replay of one task by one model: it starts at a call with attempt 1, and each later call of the same
(model, effort, task) with attempt > 1 belongs to the latest run of that (model, effort, task). A call with attempt > 1
and no run to join starts a run of its own. A run passed when one of its calls has an outcome "passed". A call
without an outcome still counts as an attempt.

replay_summary(events) -> {f"{model} effort={effort}": {"runs", "passed", "attempts", "seconds",
                                                         "tasks": {task: {"runs", "passed", "attempts", "seconds"}}}}
attempts = number of calls, seconds = the sum of the calls' seconds (a missing value counts 0). {} for no calls.
"""
from stratos import report


def call(cid, task, attempt, model="m", effort="none", seconds=10.0):
    return {"kind": "call", "call_id": cid, "task": task, "attempt": attempt, "model": model, "effort": effort,
            "seconds": seconds}


def outcome(cid, result):
    return {"kind": "outcome", "call_id": cid, "result": result}


def test_empty():
    assert report.replay_summary([]) == {}
    assert report.replay_summary([{"kind": "switch", "model": "m", "seconds": 3}]) == {}


def test_runs_attempts_and_passes():
    ev = [
        call("a1", "T1", 1), outcome("a1", "failed"), call("a2", "T1", 2), outcome("a2", "passed"),   # run 1: passed
        call("b1", "T1", 1, seconds=5.0), outcome("b1", "no_files"),                                     # run 2: failed
        call("c1", "T2", 1), outcome("c1", "passed"),                                                  # T2 passed
        {"kind": "switch", "model": "m", "seconds": 30},
    ]
    s = report.replay_summary(ev)
    assert list(s) == ["m effort=none"]
    m = s["m effort=none"]
    assert (m["runs"], m["passed"], m["attempts"], m["seconds"]) == (3, 2, 4, 35.0)
    assert m["tasks"]["T1"] == {"runs": 2, "passed": 1, "attempts": 3, "seconds": 25.0}
    assert m["tasks"]["T2"] == {"runs": 1, "passed": 1, "attempts": 1, "seconds": 10.0}


def test_models_and_efforts_are_kept_apart():
    ev = [call("a", "T1", 1, model="x"), outcome("a", "passed"),
          call("b", "T1", 1, model="x", effort="low"), outcome("b", "failed"),
          call("c", "T1", 2, model="y"), outcome("c", "passed"),          # no run to join: a run of its own
          call("d", "T1", 2, model="x", effort="low", seconds=None)]      # joins x low's run; no outcome
    s = report.replay_summary(ev)
    assert sorted(s) == ["x effort=low", "x effort=none", "y effort=none"]
    assert (s["x effort=none"]["runs"], s["x effort=none"]["passed"]) == (1, 1)
    low = s["x effort=low"]
    assert (low["runs"], low["passed"], low["attempts"], low["seconds"]) == (1, 0, 2, 10.0)
    assert (s["y effort=none"]["runs"], s["y effort=none"]["passed"]) == (1, 1)


def test_interleaved_tasks():
    ev = [call("a1", "T1", 1), call("b1", "T2", 1), outcome("a1", "failed"), outcome("b1", "failed"),
          call("a2", "T1", 2), outcome("a2", "passed"), call("b2", "T2", 2), outcome("b2", "failed")]
    t = report.replay_summary(ev)["m effort=none"]["tasks"]
    assert (t["T1"]["passed"], t["T1"]["attempts"], t["T2"]["passed"], t["T2"]["runs"]) == (1, 2, 0, 1)
