"""Tests for task main_use_steps: _main calls steps.use(Telemetry(config.STATE_DIR / "telemetry.jsonl"))
right after creating the Store, so steps timed outside a task are recorded with task=None.
The conftest no_network fixture resets steps._telemetry and steps._task to None between tests.

Fakes stand in for Gateway, memindex.refresh, embed.Embedder, scheduler_plan, run_all;
no GPU, model, network, or real .stratos is touched."""
import json

import pytest

from stratos import __main__ as cli
from stratos import config, embed, memindex, steps
from stratos.state import Store


def read_telemetry(state_dir):
    """Read every JSON line from the telemetry file; empty list when it does not exist."""
    p = state_dir / "telemetry.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def step_events(state_dir):
    """Events whose kind is 'step', in the order recorded."""
    return [e for e in read_telemetry(state_dir) if e["kind"] == "step"]


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


def test_conftest_resets_steps_telemetry():
    # The no_network fixture does monkeypatch.setattr(steps, "_telemetry", None),
    # so before every test steps._telemetry is None.
    # Expect: steps._telemetry is None at the start of this test.
    assert steps._telemetry is None


def test_conftest_resets_steps_task():
    # The no_network fixture does monkeypatch.setattr(steps, "_task", None),
    # so before every test steps._task is None.
    # Expect: steps._task is None at the start of this test.
    assert steps._task is None


def test_main_installs_steps_telemetry(tmp_path, monkeypatch, capsys):
    # cli.main(["status"]) runs _main, which calls steps.use(Telemetry(...)) after Store.
    # Before the call, steps._telemetry is None (conftest reset).
    # After, it must be a Telemetry instance pointing at STATE_DIR/telemetry.jsonl.
    assert steps._telemetry is None
    # step 1: run the status command; _main creates Store, then steps.use(Telemetry(...)).
    assert cli.main(["status"]) == 0
    # step 2: steps._telemetry is not None — _main installed it.
    assert steps._telemetry is not None
    # step 3: the path is exactly config.STATE_DIR / "telemetry.jsonl".
    expected = config.STATE_DIR / "telemetry.jsonl"
    assert steps._telemetry.path == expected
    # step 4: the parent directory was created by Telemetry.__init__ (mkdir parents=True).
    assert steps._telemetry.path.parent == config.STATE_DIR


def test_telemetry_file_not_created_by_steps_use(tmp_path, monkeypatch, capsys):
    # steps.use() creates a Telemetry object (mkdir on parent) but writes no events.
    # cmd_status has no timed block, so the file is not created.
    cli.main(["status"])
    # Expect: telemetry.jsonl does not exist (no record() call).
    assert not (config.STATE_DIR / "telemetry.jsonl").exists()
    # Expect: no step events.
    assert step_events(config.STATE_DIR) == []


def test_run_all_records_memory_step(tmp_path, monkeypatch, capsys):
    # cmd_run_all calls refresh_memory() first; refresh_memory is wrapped
    # in steps.timed("memory"). _main installs steps.use(Telemetry(...))
    # right after creating Store, so the step is recorded to that telemetry.
    monkeypatch.setattr(config, "MEMORY", True)
    monkeypatch.setattr(config, "REPO", tmp_path)
    monkeypatch.setattr(config, "WORKTREES", tmp_path / "wt")
    # fakes: no real embedding model, no real index refresh.
    monkeypatch.setattr(embed, "Embedder", lambda: None)
    monkeypatch.setattr(memindex, "refresh", lambda repo, state, emb: {"changed": 0, "embedded": 0})
    monkeypatch.setattr(cli, "Gateway", lambda tel: FakeGateway(tel))
    # scheduler returns empty order and no blocked tasks → cmd_run_all returns 0.
    monkeypatch.setattr(cli, "scheduler_plan", lambda tasks, roles, current: ([], []))
    # step 1: run-all with an empty store: refresh_memory runs, then order=[]
    #   → "nothing to run", return 0.
    assert cli.main(["run-all"]) == 0
    # step 2: exactly one step event.
    se = step_events(config.STATE_DIR)
    assert len(se) == 1, f"expected 1 step event, got {len(se)}: {se}"
    # step 3: kind is "step".
    assert se[0]["kind"] == "step"
    # step 4: name is "memory" (refresh_memory's timed label).
    assert se[0]["name"] == "memory"
    # step 5: task is None (steps.use(telemetry) in _main passes no task).
    assert se[0]["task"] is None
    # step 6: seconds is present and a float (from time.monotonic delta).
    assert "seconds" in se[0]
    assert isinstance(se[0]["seconds"], float)


def test_step_task_is_none_outside_task(tmp_path, monkeypatch, capsys):
    # _main calls steps.use(telemetry) with task=None, so steps._task is None
    # for every timed block during command dispatch.
    monkeypatch.setattr(config, "MEMORY", True)
    monkeypatch.setattr(config, "REPO", tmp_path)
    monkeypatch.setattr(config, "WORKTREES", tmp_path / "wt")
    monkeypatch.setattr(embed, "Embedder", lambda: None)
    monkeypatch.setattr(memindex, "refresh", lambda repo, state, emb: {"changed": 0, "embedded": 0})
    monkeypatch.setattr(cli, "Gateway", lambda tel: FakeGateway(tel))
    monkeypatch.setattr(cli, "scheduler_plan", lambda tasks, roles, current: ([], []))
    cli.main(["run-all"])
    # step 1: the recorded step event has task=None.
    se = step_events(config.STATE_DIR)
    assert se[0]["task"] is None
    # step 2: steps._task was None during the timed block.
    assert steps._task is None


def test_status_records_no_step(tmp_path, monkeypatch, capsys):
    # cmd_status does not call any timed block.
    # steps.use(Telemetry(...)) is installed by _main, so _telemetry is set,
    # but no record() call happens, so no step event.
    cli.main(["status"])
    # step 1: steps._telemetry is installed.
    assert steps._telemetry is not None
    # step 2: no step events.
    se = step_events(config.STATE_DIR)
    assert se == []


def test_step_event_is_one_json_line(tmp_path, monkeypatch, capsys):
    # Each telemetry record is exactly one JSON line in the file.
    # The step from refresh_memory's timed("memory") in run-all.
    monkeypatch.setattr(config, "MEMORY", True)
    monkeypatch.setattr(config, "REPO", tmp_path)
    monkeypatch.setattr(config, "WORKTREES", tmp_path / "wt")
    monkeypatch.setattr(embed, "Embedder", lambda: None)
    monkeypatch.setattr(memindex, "refresh", lambda repo, state, emb: {"changed": 0, "embedded": 0})
    monkeypatch.setattr(cli, "Gateway", lambda tel: FakeGateway(tel))
    monkeypatch.setattr(cli, "scheduler_plan", lambda tasks, roles, current: ([], []))
    cli.main(["run-all"])
    # step 1: telemetry.jsonl has exactly 1 line.
    p = config.STATE_DIR / "telemetry.jsonl"
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    # step 2: the line is valid JSON with the expected fields.
    event = json.loads(lines[0])
    # step 3: kind == "step", name == "memory", task == None.
    assert event["kind"] == "step"
    assert event["name"] == "memory"
    assert event["task"] is None
    # step 4: "ts" (timestamp) and "seconds" are present.
    assert "ts" in event
    assert "seconds" in event


def test_conftest_reset_is_visible_before_next_test(tmp_path, monkeypatch, capsys):
    # Within one test: start _telemetry=None, after cli.main(["status"]) it is
    # a Telemetry. The conftest monkeypatch undoes it for the next test.
    # step 1: at the start, _telemetry is None.
    assert steps._telemetry is None
    # step 2: after the command, it is set.
    cli.main(["status"])
    assert steps._telemetry is not None
    # step 3: _task is None (steps.use passes task=None by default).
    assert steps._task is None


def test_steps_use_path_matches_state_dir(tmp_path, monkeypatch, capsys):
    # _main passes config.STATE_DIR / "telemetry.jsonl" to Telemetry.
    # The conftest sets STATE_DIR to a tmp folder, so the path must be
    # that folder / "telemetry.jsonl".
    cli.main(["status"])
    # step 1: expected path.
    expected = config.STATE_DIR / "telemetry.jsonl"
    # step 2: steps._telemetry.path equals expected.
    assert steps._telemetry.path == expected
    # step 3: expected is inside STATE_DIR (not the real .stratos).
    assert steps._telemetry.path.parent == config.STATE_DIR
```

FILE: tests/conftest.py
```python
"""Shared test setup: no test reaches the network. Jev's shadow decisions, the diagnosis A/B, text planning, the preflight check, the draft check and the plan critique are off unless a test turns them on, and
the real HTTP sender fails loudly if anything calls it. config.STATE_DIR is a fresh temporary folder unless a test sets
its own, so nothing a test writes reaches the real .stratos (2026-11-19). The steps module's _telemetry and _task
are reset to None so no test leaks a telemetry for the next one."""
import pytest

from stratos import config, jev, steps


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path_factory):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path_factory.mktemp("state"))
    monkeypatch.setattr(config, "JEV_SHADOW", False)
    monkeypatch.setattr(config, "DIAGNOSE_AB", False)
    monkeypatch.setattr(config, "DIAGNOSE_ALWAYS", False, raising=False)
    # the loop tests check the loop's mechanics with the attempt plan they were written for (3 Tiel tries, then 1
    # Swift try); tests/test_p4_policy.py checks the real policy in config.py's source
    monkeypatch.setattr(config, "ATTEMPT_PLANS", {"coder": [("coder", 3), ("coder_hard", 1)],
                                                  "coder_hard": [("coder_hard", 2), ("coder", 1)]})
    monkeypatch.setattr(config, "PLAN_AS_TEXT", False)
    monkeypatch.setattr(config, "PLAN_CONVERTER", None)
    monkeypatch.setattr(config, "TRIAGE", False, raising=False)
    monkeypatch.setattr(config, "PREFLIGHT", False, raising=False)
    monkeypatch.setattr(config, "PLAN_CRITIQUE", False, raising=False)
    monkeypatch.setattr(config, "LINT", False, raising=False)
    monkeypatch.setattr(config, "REF_CHECK", False, raising=False)
    monkeypatch.setattr(config, "MUTATION", False, raising=False)   # T241: mutants run the tests many times
    monkeypatch.setattr(config, "MEMORY", False, raising=False)
    monkeypatch.setattr(config, "STREAM", False, raising=False)   # task gateway_stream: old fakes replace _req
    monkeypatch.setattr(config, "AUTO_LEARN", False, raising=False)   # task upkeep
    monkeypatch.setattr(config, "AUTO_WIKI", False, raising=False)
    monkeypatch.setattr(config, "CHECK", False, raising=False)   # task loop_checker: no real pyright in the tests
    monkeypatch.setattr(config, "LESSONS", tmp_path_factory.mktemp("lessons") / "LESSONS.md", raising=False)

    # Reset the steps module so no test's telemetry leaks into the next.
    monkeypatch.setattr(steps, "_telemetry", None)
    monkeypatch.setattr(steps, "_task", None)

    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to call the real Jev API")

    monkeypatch.setattr(jev, "_default_post", refuse)

