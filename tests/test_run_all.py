"""Tests for `python -m stratos run-all` (tasks T004 and T012): roles and dependencies on tasks, and running every
todo task in the order stratos.scheduler.plan gives through stratos.loop.run_all (rounds: write all, then review all).
No GPU needed: the gateway and loop.run_all are replaced by fakes.

run-all prints 'plan: <ids>', 'blocked: <ids>' when some can never run, then one line per planned task:
'<id>: <final status>', or 'skipped <id> (waits on <dep>)' when it is still todo because a dependency is not done.
It returns 0 when every planned task is done and nothing is blocked, else 1."""
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


def fake_run_all(results, calls):
    def run_all(store, gw, task_ids, log=print):
        calls.extend(task_ids)
        for tid in task_ids:
            store.update(tid, status=results.get(tid, "done"))
        return {tid: store.get(tid)["status"] for tid in task_ids}
    return run_all


def add(*extra):
    return cli.main(["add", "--title", "t", "--goal", "g", "--tests", "tests/x.py", *extra])


def use_fakes(monkeypatch, results=None, calls=None):
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    monkeypatch.setattr(cli, "run_all", fake_run_all(results or {}, calls if calls is not None else []))
    FakeGateway.model, FakeGateway.down = TIEL, False


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


def test_run_all_passes_the_plan_to_the_loop(state, monkeypatch, capsys):
    add("--role", "coder_hard")          # T001 flint
    add()                                # T002 tiel
    add("--after", "T001")               # T003 tiel, after T001
    calls = []
    use_fakes(monkeypatch, calls=calls)
    code = cli.main(["run-all"])
    out = capsys.readouterr().out
    assert calls == ["T002", "T001", "T003"]
    assert "plan: T002 T001 T003" in out
    assert "T001: done" in out and "T002: done" in out and "T003: done" in out
    assert code == 0


def test_run_all_reports_tasks_left_waiting(state, monkeypatch, capsys):
    add("--role", "coder_hard")          # T001 fails
    add("--after", "T001")               # T002 is left todo by the loop
    add()                                # T003 runs
    use_fakes(monkeypatch, results={"T001": "needs_human", "T002": "todo"})
    code = cli.main(["run-all"])
    out = capsys.readouterr().out
    assert "T001: needs_human" in out
    assert "skipped T002 (waits on T001)" in out
    assert "T003: done" in out
    assert code == 1


def test_run_all_reports_blocked_tasks(state, monkeypatch, capsys):
    add("--after", "T009")               # unknown dependency
    add()
    calls = []
    use_fakes(monkeypatch, calls=calls)
    code = cli.main(["run-all"])
    out = capsys.readouterr().out
    assert calls == ["T002"]
    assert "blocked: T001" in out
    assert code == 1


def test_run_all_works_when_the_server_does_not_answer_health(state, monkeypatch, capsys):
    add("--role", "coder_hard")
    add()
    calls = []
    use_fakes(monkeypatch, calls=calls)
    FakeGateway.down = True
    try:
        assert cli.main(["run-all"]) == 0
    finally:
        FakeGateway.down = False
    assert calls == ["T001", "T002"]      # no model known: lowest id first


def test_nothing_to_run(state, monkeypatch, capsys):
    use_fakes(monkeypatch)
    assert cli.main(["run-all"]) == 0
    assert "nothing to run" in capsys.readouterr().out


def test_loop_uses_the_task_roles_attempt_plan():
    assert loop.attempt_plan({"role": "coder_hard"}) == config.ATTEMPT_PLANS["coder_hard"]
    assert loop.attempt_plan({}) == config.ATTEMPT_PLANS["coder"]
