"""Tests for task T001, the first feature Stratos writes for itself: a summary of its own telemetry.
stratos/report.py does not exist yet; the coding model writes it."""
from stratos.report import summarize

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
