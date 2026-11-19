"""Tests for task coder_memory: the coder gets a context pack from memory (memory M5).

context.build_messages(task, root, failure=None, memory=None): a non-empty memory adds the part
"MEMORY (found for this task: lessons and related code):\n" + memory right before the failure part (the last part
when there is no failure). None or "" -> exactly as before.

loop.CODER_SECTIONS = [("guide", "GENERAL LESSONS (from earlier projects)", 3), ("lesson", "LESSONS FROM PEOPLE'S
CORRECTIONS", 3), ("code", "RELEVANT CODE", 5)].
loop.task_memory(task) -> str or None: when config.MEMORY is on and config.STATE_DIR / "memory.db" exists:
recall.pack(store, task["title"] + "\n" + task["goal"], embed.Embedder(), codemap.build(config.REPO), budget=6000,
sections=CODER_SECTIONS) with store = memstore.Store(that path), closed afterwards (all through their modules); an
exception gives None. Otherwise None.
write_task calls task_memory(task) once, before its attempts, and passes memory=<it> to every
context.build_messages call."""
import pytest

from stratos import codemap, config, context, embed, gitops, loop, memstore, recall, verify
from stratos.state import Store
from stratos.telemetry import Telemetry

HEAD = "MEMORY (found for this task: lessons and related code):\n"


def test_build_messages(tmp_path):
    task = {"id": "T001", "title": "t", "goal": "g", "files": [], "protected": []}
    user = context.build_messages(task, tmp_path, memory="PACK")[1]["content"]
    assert user.endswith("\n\n" + HEAD + "PACK")
    user = context.build_messages(task, tmp_path, failure="boom", memory="PACK")[1]["content"]
    assert (HEAD + "PACK\n\nYOUR PREVIOUS ATTEMPT FAILED") in user
    assert context.build_messages(task, tmp_path, memory="") == context.build_messages(task, tmp_path)


def test_task_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(embed, "Embedder", lambda: "EMB")
    monkeypatch.setattr(codemap, "build", lambda r: {"root": str(r)})
    seen = []

    def pack(store, query, embedder, cmap, budget, sections):
        seen.append((type(store).__name__, query, embedder, cmap, budget, sections))
        return "PACK"
    monkeypatch.setattr(recall, "pack", pack)
    task = {"title": "Tower levels", "goal": "Add levels."}
    monkeypatch.setattr(config, "MEMORY", True)
    assert loop.task_memory(task) is None                      # no memory.db yet
    (tmp_path / "state").mkdir()
    memstore.Store(tmp_path / "state" / "memory.db").close()
    assert loop.task_memory(task) == "PACK"
    assert seen == [("Store", "Tower levels\nAdd levels.", "EMB", {"root": str(tmp_path / "repo")}, 6000,
                     loop.CODER_SECTIONS)]
    monkeypatch.setattr(config, "MEMORY", False)
    assert loop.task_memory(task) is None

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(config, "MEMORY", True)
    monkeypatch.setattr(recall, "pack", boom)
    assert loop.task_memory(task) is None


def test_coder_sections():
    assert loop.CODER_SECTIONS == [("guide", "GENERAL LESSONS (from earlier projects)", 3),
                                   ("lesson", "LESSONS FROM PEOPLE'S CORRECTIONS", 3), ("code", "RELEVANT CODE", 5)]


class FakeGateway:
    def __init__(self, telemetry, answers):
        self.telemetry = telemetry
        self.answers = list(answers)
        self.messages = []

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        self.messages.append(messages)
        return f"c{len(self.messages)}", self.answers.pop(0)


def test_write_task_passes_the_pack(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REVIEW", False)

    def worktree(repo, root, tid, bases=None):
        p = tmp_path / "wt" / tid
        p.mkdir(parents=True, exist_ok=True)
        return p
    monkeypatch.setattr(gitops, "ensure_worktree", worktree)
    monkeypatch.setattr(gitops, "dependency_bases", lambda repo, ids: [])
    monkeypatch.setattr(gitops, "diff", lambda w: "")
    monkeypatch.setattr(gitops, "discard_changes", lambda w: None)
    monkeypatch.setattr(gitops, "commit_all", lambda w, message: "sha1")
    outs = [(False, "FAILED tests/x.py::t"), (True, "1 passed")]
    monkeypatch.setattr(verify, "run_tests", lambda w, tests: outs.pop(0))
    calls = []
    monkeypatch.setattr(loop, "task_memory", lambda task: calls.append(task["id"]) or "PACK")
    store = Store(state)
    store.add_task("t", "make X", ["pkg/a.py"], [], ["tests/x.py"], role="coder")
    gw = FakeGateway(Telemetry(state / "telemetry.jsonl"), ["FILE: pkg/a.py\n```python\nX = 1\n```\n"] * 2)
    assert loop.write_task(store, gw, "T001", log=lambda s: None) == "done"
    assert calls == ["T001"]
    assert len(gw.messages) == 2 and all(HEAD + "PACK" in m[1]["content"] for m in gw.messages)
