"""Tests for task command_telemetry: main() records start/end command events in telemetry for LOGGED commands.

In stratos/__main__.py, main() finds the command name from argv. When it is in runlog.LOGGED,
Telemetry(config.STATE_DIR/"telemetry.jsonl").record("command", name=cmd, phase="start") is written
before running the command, and record("command", name=cmd, phase="end") is written after
(including when the command raises). Non-LOGGED commands (like status) record no command events.

Tests call cli.main([...]) with fakes for Gateway and the command handler; no network, GPU, or real model.
Every expected value is computed step by step in a comment above its assertion."""
import json

import pytest

from stratos import __main__ as cli
from stratos import config, runlog
from stratos.state import Store


def all_events(state_dir):
    """Read every JSON line from the telemetry file; empty list when it does not exist."""
    p = state_dir / "telemetry.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def command_events(state_dir):
    """Events whose kind is "command", in the order recorded."""
    return [e for e in all_events(state_dir) if e["kind"] == "command"]


class FakeGateway:
    """Stands in for stratos.gateway.Gateway: no network, no model."""
    def __init__(self, telemetry):
        self.telemetry = telemetry

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        return "c1", "x"

    def health(self):
        return {"model": "x"}


def _setup(tmp_path, monkeypatch):
    """Point config.STATE_DIR/REPO/WORKTREES at tmp_path so nothing touches the real project."""
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(config, "WORKTREES", tmp_path / "wt")
    return state


def test_logged_command_records_start_and_end(tmp_path, monkeypatch):
    # "run" is in runlog.LOGGED. The command handler calls run_task; we fake Gateway
    # (no network) and run_task (returns "done"), so main() succeeds.
    state = _setup(tmp_path, monkeypatch)
    store = Store(state)
    store.add_task("t", "g", [], [], ["x"])
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    monkeypatch.setattr(cli, "run_task", lambda store, gw, tid: "done")
    # main(["run","T001"]) -> cmd is "run" -> in LOGGED -> start recorded, _main runs, end recorded.
    # cmd_run prints "running T001" and "T001: done", returns 0.
    assert cli.main(["run", "T001"]) == 0
    # Expect: exactly 2 command events.
    #   step 1: first event kind="command", name="run", phase="start"
    #   step 2: second event kind="command", name="run", phase="end"
    ce = command_events(state)
    assert len(ce) == 2, f"expected 2 command events, got {len(ce)}: {ce}"
    assert ce[0]["kind"] == "command"
    assert ce[0]["name"] == "run"
    assert ce[0]["phase"] == "start"
    assert ce[1]["kind"] == "command"
    assert ce[1]["name"] == "run"
    assert ce[1]["phase"] == "end"


def test_end_recorded_when_command_raises(tmp_path, monkeypatch):
    # "run" is in runlog.LOGGED. run_task raises RuntimeError; main() must record
    # "end" in a finally block so the event is written even when the exception
    # propagates out of main().
    state = _setup(tmp_path, monkeypatch)
    store = Store(state)
    store.add_task("t", "g", [], [], ["x"])
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    monkeypatch.setattr(cli, "run_task", lambda store, gw, tid: (_ for _ in ()).throw(RuntimeError("model down")))
    # main(["run","T001"]) -> start recorded -> run_task raises -> end recorded -> RuntimeError
    # propagates. The test catches it.
    with pytest.raises(RuntimeError, match="model down"):
        cli.main(["run", "T001"])
    # Expect: start recorded before the exception, end recorded in the finally.
    #   step 1: ce[0] has phase "start" (recorded before _main runs)
    #   step 2: ce[1] has phase "end" (recorded in finally, after the exception)
    ce = command_events(state)
    assert len(ce) == 2, f"expected 2 command events (start+end), got {len(ce)}: {ce}"
    assert ce[0]["phase"] == "start"
    assert ce[0]["name"] == "run"
    assert ce[1]["phase"] == "end"
    assert ce[1]["name"] == "run"


def test_non_logged_command_records_no_command_events(tmp_path, monkeypatch):
    # "status" is NOT in runlog.LOGGED (LOGGED = {run, run-all, plan, plan-tests,
    # plan-add, plan-critique, review, memory, push}). main() takes the else branch
    # and calls _main directly: no start, no end.
    state = _setup(tmp_path, monkeypatch)
    # An empty store: status prints nothing and returns 0.
    assert cli.main(["status"]) == 0
    # Expect: zero command events in telemetry.
    ce = command_events(state)
    assert ce == [], f"status is not in LOGGED, so no command events expected, got {ce}"
    # Expect: no telemetry file at all (nothing was recorded), or an empty file.
    # The file should not exist, since record() was never called.
    assert not (state / "telemetry.jsonl").exists()
