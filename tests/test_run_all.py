"""Tests for task T004: tasks get a role and dependencies, and `python -m stratos run-all` runs every todo task in
the order stratos.scheduler.plan gives (fewest model switches). No GPU needed: the gateway and the task loop are
replaced by fakes."""
import pytest

from stratos import __main__ as cli
from stratos import config, loop
from stratos.state import Store

TIEL = config.ROLES["coder"]["model"]


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    return Store(tmp_path)


class FakeGateway:
    model = TIEL
    down = False

    def __init__(self, telemetry, *a, **k):
        self.telemetry = telemetry

    def health(self):
        if FakeGateway.down:
            raise OSError("server not running")
        return {"model": FakeGateway.model}


def fake_loop(results, calls):
    def run_task(store, gw, task_id, log=print):
        calls.append(task_id)
        result = results.get(task_id, "done")
        store.update(task_id, status=result)
        return result
    return run_task


def add(*extra):
    return cli.main(["add", "--title", "t", "--goal", "g", "--tests", "tests/x.py", *extra])


def test_add_stores_role_and_after(state):
    add()
    add("--role", "coder_hard", "--after", "T001")
    t1, t2 = state.tasks()
    assert t1["role"] == "coder" and t1["after"] == []
    assert t2["role"] == "coder_hard" and t2["after"] == ["T001"]


def test_add_rejects_an_unknown_role(state):
    with pytest.raises(SystemExit):
        add("--role", "painter")


def test_store_add_task_keeps_working_without_role(state):
    t = state.add_task("t", "g", [], [], ["x"])
    assert t["role"] == "coder" and t["after"] == []


def test_run_all_follows_the_plan(state, monkeypatch, capsys):
    add("--role", "coder_hard")          # T001 flint
    add()                                # T002 tiel
    add("--after", "T001")               # T003 tiel, after T001
    calls = []
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    monkeypatch.setattr(cli, "run_task", fake_loop({}, calls))
    FakeGateway.model, FakeGateway.down = TIEL, False
    code = cli.main(["run-all"])
    out = capsys.readouterr().out
    assert calls == ["T002", "T001", "T003"]
    assert "plan: T002 T001 T003" in out
    assert code == 0
    assert [t["status"] for t in state.tasks()] == ["done", "done", "done"]


def test_run_all_skips_tasks_whose_dependency_failed(state, monkeypatch, capsys):
    add("--role", "coder_hard")          # T001 fails
    add("--after", "T001")               # T002 must be skipped
    add()                                # T003 runs
    calls = []
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    monkeypatch.setattr(cli, "run_task", fake_loop({"T001": "needs_human"}, calls))
    FakeGateway.model, FakeGateway.down = TIEL, False
    code = cli.main(["run-all"])
    out = capsys.readouterr().out
    assert "T002" not in calls and "T001" in calls and "T003" in calls
    assert "skipped T002" in out
    assert code == 1
    assert state.get("T002")["status"] == "todo"


def test_run_all_reports_blocked_tasks(state, monkeypatch, capsys):
    add("--after", "T009")               # unknown dependency
    add()
    calls = []
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    monkeypatch.setattr(cli, "run_task", fake_loop({}, calls))
    FakeGateway.model, FakeGateway.down = TIEL, False
    code = cli.main(["run-all"])
    out = capsys.readouterr().out
    assert calls == ["T002"]
    assert "blocked: T001" in out
    assert code == 1


def test_run_all_works_when_the_server_does_not_answer_health(state, monkeypatch, capsys):
    add("--role", "coder_hard")
    add()
    calls = []
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    monkeypatch.setattr(cli, "run_task", fake_loop({}, calls))
    FakeGateway.down = True
    try:
        assert cli.main(["run-all"]) == 0
    finally:
        FakeGateway.down = False
    assert calls == ["T001", "T002"]      # no model known: lowest id first


def test_nothing_to_run(state, monkeypatch, capsys):
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    monkeypatch.setattr(cli, "run_task", fake_loop({}, []))
    assert cli.main(["run-all"]) == 0
    assert "nothing to run" in capsys.readouterr().out


def test_loop_uses_the_task_roles_attempt_plan():
    assert loop.attempt_plan({"role": "coder_hard"}) == config.ATTEMPT_PLANS["coder_hard"]
    assert loop.attempt_plan({}) == config.ATTEMPT_PLANS["coder"]
