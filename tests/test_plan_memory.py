"""Tests for task plan_memory: the planner gets a context pack from memory (memory M5).

config.MEMORY = True by default (tests turn it off in conftest unless they turn it on).

plan.build_messages(goal, summary, conventions=None, system=None, uses=None, memory=None): a non-empty memory adds
the part "\n\nMEMORY (found for this goal in the project's code, tests, past tasks and people's corrections):\n" +
memory right after the WHO USES WHAT part (or after PROJECT FILES when there is none), before the conventions.

`stratos plan`: cmap = codemap.build(config.REPO) once (uses = codemap.uses_summary(cmap) as before). When
config.MEMORY is on and config.STATE_DIR / "memory.db" exists: store = memstore.Store(that path), memory =
recall.pack(store, goal, embed.Embedder(), cmap), store closed (all through the modules). Any exception there is
printed to stderr as f"memory: {e}" and the plan goes on with memory None. Off, or no memory.db: memory None."""
import pytest

from stratos import __main__ as cli
from stratos import codemap, config, embed, memstore, plan, recall

HEAD = "MEMORY (found for this goal in the project's code, tests, past tasks and people's corrections):\n"
ANSWER = '{"tasks": [{"key": "a", "title": "T", "goal": "G", "files": ["stratos/x.py"], "tests": ["tests/test_n.py"]}]}'


def test_build_messages_with_memory():
    user = plan.build_messages("G", "S", conventions="C", uses="U", memory="M")[1]["content"]
    assert user == ("PROJECT FILES:\nS\n\nWHO USES WHAT (when a task changes a name, every user listed here must be "
                    "changed or checked too):\nU\n\n" + HEAD + "M\n\nPROJECT CONVENTIONS:\nC\n\nFEATURE GOAL:\nG")
    assert plan.build_messages("G", "S", memory="M")[1]["content"] == "PROJECT FILES:\nS\n\n" + HEAD + "M\n\nFEATURE GOAL:\nG"
    assert plan.build_messages("G", "S", memory="") == plan.build_messages("G", "S")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    (tmp_path / "repo").mkdir()
    (tmp_path / "state").mkdir()
    monkeypatch.setattr(plan, "repo_summary", lambda root: "SUMMARY")
    builds = []
    monkeypatch.setattr(codemap, "build", lambda root: builds.append(root) or {"test_dir": "tests", "files": {}})
    monkeypatch.setattr(codemap, "uses_summary", lambda cmap: "")
    seen = []

    class FakeGateway:
        def __init__(self, telemetry):
            self.telemetry = telemetry

        def ensure_model(self, model):
            return 0.0

        def chat(self, messages, **kw):
            seen.append(messages)
            return "c1", ANSWER
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    monkeypatch.setattr(embed, "Embedder", lambda: "EMB")
    # (task memory_refresh: `plan` refreshes the memory first; these tests are about the pack, so no refresh)
    from stratos import memindex
    monkeypatch.setattr(memindex, "refresh", lambda *a: {"chunks": 0, "changed": 0, "removed": 0, "embedded": 0},
                        raising=False)
    goal = tmp_path / "goal.txt"
    goal.write_text("Make it fly.", encoding="utf-8")
    return seen, builds, goal


def test_the_plan_gets_the_pack(env, monkeypatch):
    seen, builds, goal = env
    monkeypatch.setattr(config, "MEMORY", True)
    memstore.Store(config.STATE_DIR / "memory.db").close()
    packs = []
    monkeypatch.setattr(recall, "pack", lambda store, query, embedder, cmap: packs.append((query, embedder, cmap))
                        or "PACK")
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    assert packs == [("Make it fly.", "EMB", {"test_dir": "tests", "files": {}})]
    assert len(builds) == 1
    assert seen[0] == plan.build_messages("Make it fly.", "SUMMARY", memory="PACK")


def test_no_memory_db(env, monkeypatch):
    seen, builds, goal = env
    monkeypatch.setattr(config, "MEMORY", True)
    monkeypatch.setattr(recall, "pack", lambda *a: pytest.fail("no memory.db, no recall"))
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    assert seen[0] == plan.build_messages("Make it fly.", "SUMMARY")


def test_memory_off(env, monkeypatch):
    seen, builds, goal = env
    monkeypatch.setattr(config, "MEMORY", False)
    memstore.Store(config.STATE_DIR / "memory.db").close()
    monkeypatch.setattr(recall, "pack", lambda *a: pytest.fail("memory is off"))
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0


def test_a_failing_recall_is_reported(env, monkeypatch, capsys):
    seen, builds, goal = env
    monkeypatch.setattr(config, "MEMORY", True)
    memstore.Store(config.STATE_DIR / "memory.db").close()

    def boom(*a):
        raise RuntimeError("no model")
    monkeypatch.setattr(recall, "pack", boom)
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    assert "memory: no model" in capsys.readouterr().err
    assert seen[0] == plan.build_messages("Make it fly.", "SUMMARY")
