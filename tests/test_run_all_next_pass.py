"""Tests for task next_pass: run-all runs again the tasks whose dependency finished in the last round.

loop.run_all leaves a task todo when its dependency was not done yet when the task's round came; when the dependency
is done by the end (it passed review in the last round), the task used to stay todo until the next `run-all` (T007,
T094). Now, after run_all returns, run-all collects again = the planned tasks (in plan order) that are still "todo"
and whose "after" tasks are all "done". When again is not empty and differs from the list of the pass before, it
prints f"next pass: {' '.join(again)}" and calls run_all(store, gw, again) once more, and repeats. The final lines
and the return code are as before, from the tasks' final statuses."""
import pytest

from stratos import __main__ as cli
from stratos import config
from stratos.state import Store

TIEL = config.ROLES["coder"]["model"]


class FakeGateway:
    def __init__(self, telemetry, *a, **k):
        self.telemetry = telemetry

    def health(self):
        return {"model": TIEL}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    store = Store(tmp_path)
    store.add_task("a", "g", ["a.py"], [], ["tests/a.py"], role="coder")
    store.add_task("b", "g", ["b.py"], [], ["tests/b.py"], role="coder", after=["T001"])
    store.add_task("c", "g", ["c.py"], [], ["tests/c.py"], role="coder")
    calls = []

    def use(passes):
        """passes: one {task id: status} per run_all call; a task not named keeps its status."""
        script = list(passes)

        def run_all(store, gw, task_ids, log=print):
            calls.append(list(task_ids))
            results = script.pop(0) if script else {}
            for tid in task_ids:
                if tid in results:
                    store.update(tid, status=results[tid])
            return {tid: store.get(tid)["status"] for tid in task_ids}
        monkeypatch.setattr(cli, "run_all", run_all)
    return store, calls, use


def test_a_second_pass_for_the_waiting_task(env, capsys):
    store, calls, use = env
    use([{"T001": "done", "T003": "done"}, {"T002": "done"}])
    assert cli.main(["run-all"]) == 0
    out = capsys.readouterr().out
    assert len(calls) == 2 and calls[1] == ["T002"]
    assert "next pass: T002" in out
    assert "T002: done" in out and "skipped" not in out


def test_no_second_pass_when_the_dependency_failed(env, capsys):
    store, calls, use = env
    use([{"T001": "needs_human", "T003": "done"}])
    assert cli.main(["run-all"]) == 1
    out = capsys.readouterr().out
    assert len(calls) == 1 and "next pass" not in out
    assert "skipped T002 (waits on T001)" in out


def test_it_stops_when_a_pass_changes_nothing(env, capsys):
    store, calls, use = env
    use([{"T001": "done", "T003": "done"}, {}, {}])
    assert cli.main(["run-all"]) == 1
    assert calls[1:] == [["T002"]]
    assert "T002: todo" in capsys.readouterr().out
