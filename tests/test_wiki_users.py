"""Tests for task wiki_users: the search expansion and the wiki ask for users of a name where it is defined
(task codemap_imports), and wiki pages are rewritten when the users change, not only the source.

memsearch.search: the expansion calls codemap.users(cmap, name, path) with the path from the hit's id
(f"{kind}:{path}:{name}").
wiki.used_by(cmap, path) calls codemap.users(cmap, name, path).
wiki.build: index[path]["source"] is now the sha1 hex of the user message wiki.messages(path, source, used)[1]["content"]
(so a page is rewritten when its file or its users change); everything else as before.
wiki.SYSTEM also says, for Traps, to name only problems that a line of the code shows, and to write "- none found"
rather than guess."""
import hashlib
import json

from stratos import codemap, memsearch, memstore, wiki

PAGE = "## Purpose\nLoads.\n\n## Data shapes\n-\n\n## Used by\n-\n\n## Invariants\n-\n\n## Traps\n- none found"


def test_expansion_asks_by_definition(tmp_path, monkeypatch):
    s = memstore.Store(tmp_path / "memory.db")
    s.upsert({"id": "code:src/towers.js:towerStats", "kind": "code", "source": "src/towers.js",
              "title": "src/towers.js:towerStats", "text": "towerStats damage"})
    s.upsert({"id": "code:src/step.js:step", "kind": "code", "source": "src/step.js", "title": "src/step.js:step",
              "text": "move"})
    calls = []
    monkeypatch.setattr(codemap, "users", lambda cmap, name, path=None: calls.append((name, path)) or
                        (["src/step.js:step"] if name == "towerStats" else []))
    hits = memsearch.search(s, "towerStats damage", cmap={"test_dir": "tests", "files": {}}, k=1)
    s.close()
    assert [h["id"] for h in hits] == ["code:src/towers.js:towerStats", "code:src/step.js:step"]
    assert calls[0] == ("towerStats", "src/towers.js")


def test_used_by_asks_by_definition(monkeypatch):
    cmap = {"test_dir": "tests", "files": {"src/a.py": [{"name": "load", "kind": "function", "uses": []}]}}
    calls = []
    monkeypatch.setattr(codemap, "users", lambda cmap, name, path=None: calls.append((name, path)) or ["src/b.py:x"])
    assert wiki.used_by(cmap, "src/a.py") == "- load: src/b.py:x"
    assert calls == [("load", "src/a.py")]


def test_system_traps():
    assert "none found" in wiki.SYSTEM


class FakeGateway:
    def __init__(self):
        self.calls = 0

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        self.calls += 1
        return "c", PAGE


def test_a_page_follows_its_users(tmp_path):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("def load():\n    pass\n", encoding="utf-8")
    (root / "src" / "b.py").write_text("from src import a\n\ndef run():\n    a.load()\n", encoding="utf-8")
    settings = {"source_dirs": ["src"], "test_dir": "tests"}
    state = tmp_path / "state"
    gw = FakeGateway()
    cmap = codemap.build(root, settings)
    wiki.build(gw, root, state, cmap, only=["src/a.py"], log=lambda s: None)
    index = json.loads((state / "wiki" / "index.json").read_text(encoding="utf-8"))
    content = wiki.messages("src/a.py", "def load():\n    pass\n", "- load: src/b.py:run")[1]["content"]
    assert index["src/a.py"]["source"] == hashlib.sha1(content.encode("utf-8")).hexdigest()
    assert wiki.build(gw, root, state, cmap, only=["src/a.py"], log=lambda s: None)["unchanged"] == 1
    (root / "src" / "c.py").write_text("from src import a\n\ndef go():\n    a.load()\n", encoding="utf-8")
    counts = wiki.build(gw, root, state, codemap.build(root, settings), only=["src/a.py"], log=lambda s: None)
    assert counts["written"] == 1 and gw.calls == 2
