"""Tests for task main_use_steps: _main sets telemetry for steps; conftest resets

In stratos/__main__.py, _main calls steps.use(Telemetry(config.STATE_DIR / "telemetry.jsonl"))
right after creating the store, so steps timed outside a task are recorded with task=None.
In tests/conftest.py, the no_network fixture resets steps._telemetry and steps._task to None
so no test leaks state to the next one.

Fakes stand in for git, models, and the real .stratos directory; no GPU, network, or real model.
Expected values are worked out step by step in comments above each assertion."""

import json

import pytest

from stratos import __main__ as cli
from stratos import config, steps


def read_telemetry(state_dir):
    p = state_dir / "telemetry.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def step_events(state_dir):
    return [e for e in read_telemetry(state_dir) if e["kind"] == "step"]


def test_main_sets_telemetry_for_steps(tmp_path, monkeypatch):
    """_main calls steps.use(telemetry) right after Store, so a steps.timed inside
    a command handler writes a step event to the telemetry file.
    We monkeypatch COMMANDS["status"] to include a timed block."""
    def fake_status(args, store, parser):
        with steps.timed("status"):
            pass
        return 0
    monkeypatch.setitem(cli.COMMANDS, "status", fake_status)
    # _main calls steps.use(Telemetry(STATE_DIR / "telemetry.jsonl"))
    # cmd_status calls steps.timed("status"), which records a step event
    assert cli.main(["status"]) == 0
    events = step_events(config.STATE_DIR)
    # Expect: exactly 1 step event.
    #   step 1: len(events) == 1
    assert len(events) == 1, f"expected 1 step event, got {len(events)}: {events}"
    #   step 2: kind is "step"
    assert events[0]["kind"] == "step"
    #   step 3: name is "status"
    assert events[0]["name"] == "status"
    #   step 4: task is None because use(telemetry) was called with no task argument
    assert events[0]["task"] is None, f"task must be None, got {events[0]['task']}"
    #   step 5: seconds is a non-negative float (the timed block ran, recording duration)
    assert isinstance(events[0]["seconds"], float), f"seconds must be float, got {type(events[0]['seconds'])}"
    assert events[0]["seconds"] >= 0.0, f"seconds must be >= 0, got {events[0]['seconds']}"


def test_telemetry_path_matches_state_dir(tmp_path, monkeypatch):
    """_main calls steps.use(Telemetry(config.STATE_DIR / "telemetry.jsonl")),
    so the telemetry file is written at the expected location."""
    seen = []
    def fake_status(args, store, parser):
        seen.append(steps._telemetry)
        return 0
    monkeypatch.setitem(cli.COMMANDS, "status", fake_status)
    cli.main(["status"])
    # Expect: steps.use was called inside _main.
    #   step 1: _telemetry is not None (use(telemetry) installed a Telemetry instance)
    assert len(seen) == 1
    assert seen[0] is not None, "steps.use must have been called in _main"
    #   step 2: its path is STATE_DIR / "telemetry.jsonl"
    expected_path = str(config.STATE_DIR / "telemetry.jsonl")
    assert str(seen[0].path) == expected_path, f"expected {expected_path}, got {seen[0].path}"


def test_conftest_resets_telemetry_and_task():
    """At the start of each test, the autouse no_network fixture must have set
    steps._telemetry and steps._task to None, so no test leaks state to the next.
    This test checks that the reset is in place before any other test runs."""
    # The conftest fixture is autouse, so it ran before this test starts.
    #   step 1: _telemetry must be None
    assert steps._telemetry is None, (
        f"conftest must reset _telemetry to None, got {steps._telemetry!r}"
    )
    #   step 2: _task must be None
    assert steps._task is None, (
        f"conftest must reset _task to None, got {steps._task!r}"
    )
