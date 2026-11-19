"""Tests for task wiki_memory: the wiki pages go into memory and into the packs (memory M4).

memindex.index_project(root, store, embedder=None, settings=None, lessons_path=None, state_dir=None): state_dir None
-> Path(root) / ".stratos". The chunks of wiki.chunks(state_dir, cmap) (through the wiki module, with the cmap it
built) are added to the other chunks, and store.remove_except("wiki", <their ids>) is counted in "removed" like the
other kinds. memindex.refresh(repo, state_dir, embedder) calls index_project(repo, store, embedder, state_dir=state_dir).

recall.SECTIONS gets ("wiki", "MODULE NOTES (written by a model from the code; check the code)", 3) right after the
"lesson" section; recall.CUT["wiki"] = 2000.
loop.CODER_SECTIONS gets ("wiki", "MODULE NOTES (written by a model from the code; check the code)", 2) right after
the "lesson" section (before "code")."""
from stratos import loop, memindex, memstore, recall, wiki

SETTINGS = {"source_dirs": ["src"], "test_dir": "tests"}
HEADING = "MODULE NOTES (written by a model from the code; check the code)"


def project(tmp_path):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "a.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
    return root


def test_index_project_adds_wiki_pages(tmp_path):
    root = project(tmp_path)
    pages = root / ".stratos" / "wiki"
    pages.mkdir(parents=True)
    (pages / "src__a.py.md").write_text("# src/a.py\n\n## Purpose\nIdentity.\n", encoding="utf-8")
    store = memstore.Store(tmp_path / "memory.db")
    try:
        counts = memindex.index_project(root, store, settings=SETTINGS, lessons_path=tmp_path / "none.md")
        assert counts["chunks"] == 2
        chunk = store.get("wiki:src/a.py")
        assert chunk["kind"] == "wiki" and chunk["title"] == "notes: src/a.py" and "Identity." in chunk["text"]
        (pages / "src__a.py.md").unlink()
        counts = memindex.index_project(root, store, settings=SETTINGS, lessons_path=tmp_path / "none.md")
        assert counts["removed"] == 1 and store.get("wiki:src/a.py") is None
    finally:
        store.close()


def test_index_project_uses_the_state_dir_given(tmp_path, monkeypatch):
    root = project(tmp_path)
    seen = []
    monkeypatch.setattr(wiki, "chunks", lambda state_dir, cmap: seen.append((state_dir, sorted(cmap["files"]))) or [])
    store = memstore.Store(tmp_path / "memory.db")
    try:
        memindex.index_project(root, store, settings=SETTINGS, lessons_path=tmp_path / "none.md")
        memindex.index_project(root, store, settings=SETTINGS, lessons_path=tmp_path / "none.md",
                               state_dir=tmp_path / "elsewhere")
    finally:
        store.close()
    assert seen == [(root / ".stratos", ["src/a.py"]), (tmp_path / "elsewhere", ["src/a.py"])]


def test_refresh_passes_its_state_dir(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(memindex, "index_history", lambda *a: {"chunks": 0, "changed": 0, "removed": 0})
    monkeypatch.setattr(memindex, "index_project", lambda repo, store, embedder, **kw: seen.append(kw) or {})
    memindex.refresh(tmp_path / "repo", tmp_path / "state", None)
    assert seen == [{"state_dir": tmp_path / "state"}]


def test_sections():
    kinds = [s[0] for s in recall.SECTIONS]
    assert kinds.index("wiki") == kinds.index("lesson") + 1
    assert ("wiki", HEADING, 3) in recall.SECTIONS
    assert recall.CUT["wiki"] == 2000
    assert loop.CODER_SECTIONS == [("guide", "GENERAL LESSONS (from earlier projects)", 3),
                                   ("lesson", "LESSONS FROM PEOPLE'S CORRECTIONS", 3), ("wiki", HEADING, 2),
                                   ("code", "RELEVANT CODE", 5)]
