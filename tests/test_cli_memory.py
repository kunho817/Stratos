"""Tests for task cli_memory: `stratos memory index` and `stratos memory search` (memory M2).

Both open memstore.Store(config.STATE_DIR / "memory.db") and close it at the end. The embedder is embed.Embedder()
(called through the embed module so tests can replace it) unless --no-vectors is given, then None.
- `memory index`: first h = memindex.index_history(store, Store(config.STATE_DIR).tasks(),
  Telemetry(config.STATE_DIR / "telemetry.jsonl").load()) and prints
  f"history: {chunks} chunks, {changed} changed, {removed} removed"; then
  counts = memindex.index_project(config.REPO, store, embedder); prints
  f"memory: {chunks} chunks, {changed} changed, {removed} removed, {embedded} embedded"; returns 0.
- `memory search QUERY [-k N] [--no-vectors]` (k defaults to 10): hits = memsearch.search(store, QUERY, embedder,
  codemap.build(config.REPO), k); one line per hit f"{score:.4f}  {title}  ({why})"; "no results" when there are
  none; returns 0."""
import pytest

from stratos import __main__ as cli
from stratos import codemap, config, embed, memindex, memsearch, memstore


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    made = []

    class FakeEmbedder:
        name = "fake"

        def __init__(self):
            made.append(self)
    monkeypatch.setattr(embed, "Embedder", FakeEmbedder)
    return made


def test_index(env, monkeypatch, capsys):
    # (task memindex_history: `memory index` first indexes the task history, then the project)
    seen = []
    order = []
    monkeypatch.setattr(memindex, "index_history", lambda store, tasks, events: order.append(("history", tasks)) or
                        {"chunks": 3, "changed": 1, "removed": 0})

    def index(root, store, embedder):
        order.append(("project", None))
        seen.append((root, type(store).__name__, embedder))
        return {"chunks": 5, "changed": 2, "removed": 1, "embedded": 2}
    monkeypatch.setattr(memindex, "index_project", index)
    assert cli.main(["memory", "index"]) == 0
    assert capsys.readouterr().out.splitlines() == ["history: 3 chunks, 1 changed, 0 removed",
                                                     "memory: 5 chunks, 2 changed, 1 removed, 2 embedded"]
    assert order == [("history", []), ("project", None)]     # an empty state dir has no tasks
    assert seen == [(config.REPO, "Store", env[0])]
    assert (config.STATE_DIR / "memory.db").exists()


def test_index_without_vectors(env, monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(memindex, "index_history", lambda store, tasks, events:
                        {"chunks": 0, "changed": 0, "removed": 0})
    monkeypatch.setattr(memindex, "index_project",
                        lambda root, store, embedder: seen.append(embedder) or
                        {"chunks": 0, "changed": 0, "removed": 0, "embedded": 0})
    assert cli.main(["memory", "index", "--no-vectors"]) == 0
    assert seen == [None] and env == []


def test_search(env, monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(codemap, "build", lambda root: {"test_dir": "tests", "files": {}, "root": str(root)})

    def search(store, query, embedder, cmap, k):
        seen.append((query, embedder, cmap["root"], k))
        return [{"id": "code:a.py:f", "title": "a.py:f", "score": 0.0325, "why": "keyword+vector"},
                {"id": "code:b.py:g", "title": "b.py:g", "score": 0.01, "why": "uses f"}]
    monkeypatch.setattr(memsearch, "search", search)
    assert cli.main(["memory", "search", "tower damage", "-k", "3"]) == 0
    assert capsys.readouterr().out.splitlines() == ["0.0325  a.py:f  (keyword+vector)", "0.0100  b.py:g  (uses f)"]
    assert seen == [("tower damage", env[0], str(config.REPO), 3)]


def test_search_nothing(env, monkeypatch, capsys):
    monkeypatch.setattr(codemap, "build", lambda root: {"test_dir": "tests", "files": {}})
    monkeypatch.setattr(memsearch, "search", lambda store, query, embedder, cmap, k: [])
    assert cli.main(["memory", "search", "x", "--no-vectors"]) == 0
    assert capsys.readouterr().out.strip() == "no results"


# --- task learn: `stratos memory learn` ---
# learn.learn(Gateway(Telemetry(...)), Store(config.STATE_DIR).tasks(), Telemetry(...).load(), config.LESSONS,
# config.STATE_DIR, config.REPO.name) (through the learn module); prints
# f"learn: {corrections} corrections, {added} added, {duplicates} duplicates, {skipped} skipped" and returns 0.
# It does not open the memory store.

def test_learn_command(env, monkeypatch, capsys):
    from stratos import learn
    seen = []

    class FakeGateway:
        def __init__(self, telemetry):
            self.telemetry = telemetry
    monkeypatch.setattr(cli, "Gateway", FakeGateway)

    def fake_learn(gw, tasks, events, lessons_path, state_dir, project, embedder=None):
        seen.append((type(gw).__name__, tasks, events, lessons_path, state_dir, project))
        return {"corrections": 3, "added": 1, "duplicates": 1, "skipped": 1}
    monkeypatch.setattr(learn, "learn", fake_learn)
    assert cli.main(["memory", "learn"]) == 0
    assert capsys.readouterr().out.strip() == "learn: 3 corrections, 1 added, 1 duplicates, 1 skipped"
    assert seen == [("FakeGateway", [], [], config.LESSONS, config.STATE_DIR, "repo")]
