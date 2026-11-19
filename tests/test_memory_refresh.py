"""Tests for task memory_refresh: the memory is brought up to date before planning, drafting and running (M5).

memindex.refresh(repo, state_dir, embedder) -> the index_project counts: opens memstore.Store(state_dir /
"memory.db"), runs index_history(store, stratos.state.Store(state_dir).tasks(), Telemetry(state_dir /
"telemetry.jsonl").load()) and then index_project(repo, store, embedder) (through the memindex module's own names),
and closes the store.

`stratos plan`, `stratos plan-tests` and `stratos run-all`: when config.MEMORY is on, first
memindex.refresh(config.REPO, config.STATE_DIR, embed.Embedder()) and print
f"memory: {changed} changed, {embedded} embedded"; an exception is printed to stderr as f"memory: {e}" and the
command goes on. Off: no refresh."""
import pytest

from stratos import __main__ as cli
from stratos import config, embed, memindex, memstore
from stratos.state import Store


def test_refresh(tmp_path, monkeypatch):
    state = tmp_path / "state"
    Store(state).add_task("t", "g", [], [], ["tests/x.py"])
    Store(state).update("T001", status="done")
    order = []
    monkeypatch.setattr(memindex, "index_history", lambda store, tasks, events: order.append(
        ("history", type(store).__name__, [t["id"] for t in tasks], events)) or {})
    monkeypatch.setattr(memindex, "index_project", lambda repo, store, embedder, state_dir=None: order.append(
        ("project", repo, embedder)) or {"chunks": 1, "changed": 1, "removed": 0, "embedded": 1})
    assert memindex.refresh(tmp_path / "repo", state, "EMB") == {"chunks": 1, "changed": 1, "removed": 0, "embedded": 1}
    assert order == [("history", "Store", ["T001"], []), ("project", tmp_path / "repo", "EMB")]
    assert (state / "memory.db").exists()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(embed, "Embedder", lambda: "EMB")
    seen = []
    monkeypatch.setattr(memindex, "refresh", lambda repo, state_dir, embedder: seen.append((repo, state_dir, embedder))
                        or {"chunks": 9, "changed": 2, "removed": 0, "embedded": 2})

    class FakeGateway:
        def __init__(self, telemetry):
            self.telemetry = telemetry

        def health(self):
            return {"model": None}
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    return seen


def test_run_all_refreshes(env, monkeypatch, capsys):
    monkeypatch.setattr(config, "MEMORY", True)
    assert cli.main(["run-all"]) == 0                           # nothing to run, but the memory is refreshed
    assert env == [(config.REPO, config.STATE_DIR, "EMB")]
    assert "memory: 2 changed, 2 embedded" in capsys.readouterr().out


def test_plan_tests_refreshes(env, monkeypatch, capsys):
    from stratos import plantests
    monkeypatch.setattr(config, "MEMORY", True)
    monkeypatch.setattr(plantests, "draft_tests", lambda gw, pid, root, state: [])
    assert cli.main(["plan-tests", "P001"]) == 0
    assert len(env) == 1


def test_off(env, monkeypatch):
    monkeypatch.setattr(config, "MEMORY", False)
    assert cli.main(["run-all"]) == 0
    assert env == []


def test_a_failing_refresh(env, monkeypatch, capsys):
    monkeypatch.setattr(config, "MEMORY", True)

    def boom(*a):
        raise RuntimeError("disk full")
    monkeypatch.setattr(memindex, "refresh", boom)
    assert cli.main(["run-all"]) == 0
    assert "memory: disk full" in capsys.readouterr().err
