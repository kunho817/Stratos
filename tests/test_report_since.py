"""Tests for task T014: summarize(events, since=None) counts only events whose 'ts' is at least `since`.
Without `since` every event counts (events without a 'ts' too); with `since`, events without a 'ts' are left out."""
from stratos.report import summarize

EVENTS = [
    {"ts": 100.0, "kind": "switch", "model": "m", "seconds": 5.0},
    {"ts": 200.0, "kind": "call", "call_id": "a", "model": "m", "prompt_tokens": 10, "completion_tokens": 5,
     "seconds": 1.0},
    {"ts": 300.0, "kind": "outcome", "call_id": "a", "result": "passed"},
    {"ts": 300.0, "kind": "switch", "model": "n", "seconds": 7.0},
]


def test_since_keeps_only_later_events():
    s = summarize(EVENTS, since=150)
    assert s["switches"] == 1 and s["switch_seconds"] == 7.0
    assert s["calls"] == 1 and s["outcomes"] == {"passed": 1}


def test_since_is_inclusive():
    assert summarize(EVENTS, since=300)["switches"] == 1


def test_without_since_everything_counts():
    s = summarize(EVENTS)
    assert s["switches"] == 2 and s["calls"] == 1


def test_events_without_ts():
    ev = [{"kind": "switch", "model": "m", "seconds": 1.0}]
    assert summarize(ev)["switches"] == 1
    assert summarize(ev, since=0)["switches"] == 0
