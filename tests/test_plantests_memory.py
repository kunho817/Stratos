"""Tests for task drafts_memory: the test writer gets a context pack from memory (memory M5).

plantests.build_messages(task, root, example=None, earlier=(), memory=None): a non-empty memory adds the part
"MEMORY (found for this task in the project's code, tests, past tasks and people's corrections):\n" + memory right
after the PROJECT CONVENTIONS part (or after the PROJECT FILES part when there are no conventions). None or "" ->
exactly as before.

draft_tests: when config.MEMORY is on and state_dir / "memory.db" exists, it opens memstore.Store(that path) once,
makes embed.Embedder() and cmap = codemap.build(root) once, and for each task memory = recall.pack(store,
task["title"] + "\n" + task["goal"], embedder, cmap, budget=8000) (all through their modules); the store is closed
at the end. Any exception while opening or packing is logged as f"memory: {e}" and that task (or all, when opening
failed) gets memory None. Off or no memory.db: no memory."""
import pytest

from stratos import codemap, config, embed, memstore, plan, plantests, recall

TASK = {"key": "a", "title": "Tower levels", "goal": "Add levels.", "files": ["src/towers.py"],
        "tests": ["tests/test_levels.py"], "protected": [], "after": [], "role": None}
HEAD = "MEMORY (found for this task in the project's code, tests, past tasks and people's corrections):\n"


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "repo"
    (r / "src").mkdir(parents=True)
    (r / "tests").mkdir()
    return r


def test_build_messages(root):
    # (compared by position: an empty project summary leaves an extra newline after "PROJECT FILES:")
    content = plantests.build_messages(TASK, root, example="tests/none.py", memory="PACK")[1]["content"]
    assert content.index("PROJECT FILES:") < content.index("\n\n" + HEAD + "PACK\n\n") < content.index("WRITE THESE")
    (root / "CONVENTIONS.md").write_text("Rules.", encoding="utf-8")
    content = plantests.build_messages(TASK, root, example="tests/none.py", memory="PACK")[1]["content"]
    assert "PROJECT CONVENTIONS:\nRules.\n\n" + HEAD + "PACK\n\n" in content
    assert plantests.build_messages(TASK, root, memory="") == plantests.build_messages(TASK, root)


class FakeTelemetry:
    def record(self, kind, **fields):
        pass


class FakeGateway:
    def __init__(self):
        self.telemetry = FakeTelemetry()
        self.messages = []

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        self.messages.append(messages)
        return "c", "```python\nnot closed\n"


@pytest.fixture
def env(root, tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    pid = plan.save_plan(state, "G", [TASK, dict(TASK, key="b", title="Panel", goal="Show levels.",
                                                 tests=["tests/test_panel.py"])])
    monkeypatch.setattr(embed, "Embedder", lambda: "EMB")
    monkeypatch.setattr(codemap, "build", lambda r: {"root": str(r)})
    return state, pid


def test_draft_tests_with_memory(root, env, monkeypatch):
    state, pid = env
    monkeypatch.setattr(config, "MEMORY", True)
    memstore.Store(state / "memory.db").close()
    packs = []

    def pack(store, query, embedder, cmap, budget):
        packs.append((query, embedder, cmap, budget))
        return f"PACK {len(packs)}"
    monkeypatch.setattr(recall, "pack", pack)
    gw = FakeGateway()
    plantests.draft_tests(gw, pid, root, state, log=lambda s: None)
    assert packs == [("Tower levels\nAdd levels.", "EMB", {"root": str(root)}, 8000),
                     ("Panel\nShow levels.", "EMB", {"root": str(root)}, 8000)]
    assert HEAD + "PACK 1" in gw.messages[0][1]["content"] and HEAD + "PACK 2" in gw.messages[1][1]["content"]


def test_off_or_missing(root, env, monkeypatch):
    state, pid = env
    monkeypatch.setattr(recall, "pack", lambda *a, **k: pytest.fail("no memory wanted"))
    monkeypatch.setattr(config, "MEMORY", True)
    plantests.draft_tests(FakeGateway(), pid, root, state, log=lambda s: None)     # no memory.db
    memstore.Store(state / "memory.db").close()
    monkeypatch.setattr(config, "MEMORY", False)
    plantests.draft_tests(FakeGateway(), pid, root, state, log=lambda s: None)


def test_a_failing_pack(root, env, monkeypatch):
    state, pid = env
    monkeypatch.setattr(config, "MEMORY", True)
    memstore.Store(state / "memory.db").close()

    def boom(*a, **k):
        raise RuntimeError("no model")
    monkeypatch.setattr(recall, "pack", boom)
    lines = []
    gw = FakeGateway()
    plantests.draft_tests(gw, pid, root, state, log=lines.append)
    assert "memory: no model" in lines and HEAD not in gw.messages[0][1]["content"]
