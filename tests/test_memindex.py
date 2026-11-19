"""Tests for task memindex: stratos/memindex.py puts a project into the memory store (memory M2).

index_project(root, store, embedder=None, settings=None) -> {"chunks", "changed", "removed", "embedded"}:
- cmap = codemap.build(root, settings) (settings None -> config.PROJECT). For every file and every symbol in it, one
  chunk: kind "test" when the path is under cmap["test_dir"] + "/", else "code"; id f"{kind}:{path}:{name}";
  source = path; title = f"{path}:{name}"; text = f"{path}\n{signature}\n" + codemap.symbol_text(<file text>, sym).
- root / "CONVENTIONS.md", when it exists, is cut into sections at lines starting with "## ": the text before the
  first such line is section 0 (left out when blank), each heading line starts a new section. Section n: kind "doc",
  id f"doc:CONVENTIONS.md:{n}", source "CONVENTIONS.md", title = its heading without the "## " (section 0:
  "CONVENTIONS.md"), text = the section's lines (heading included) joined with "\n" and stripped.
- Every chunk is store.upsert-ed ("changed" counts the True answers, "chunks" all of them); then for each of the
  kinds "code", "test" and "doc", store.remove_except(kind, <ids of that kind made now>) ("removed" = the sum).
- With an embedder: ids = store.stale(embedder.name); their texts are embedded with embedder.embed in batches of 32
  (in id order) and each vector is saved with store.set_vector(id, embedder.name, <chunk hash>, vec); "embedded" =
  len(ids). Without one, "embedded" is 0."""
from stratos import memindex, memstore

SETTINGS = {"source_dirs": ["src"], "test_dir": "tests"}


class FakeEmbedder:
    name = "fake"

    def __init__(self):
        self.batches = []

    def embed(self, texts):
        self.batches.append(list(texts))
        return [[float(len(t)), 1.0] for t in texts]


def project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "a.py").write_text("def f(x):\n    return x\n\n\ndef g():\n    return f(1)\n", encoding="utf-8")
    (tmp_path / "tests" / "test_a.py").write_text("def test_f():\n    assert f(1) == 1\n", encoding="utf-8")
    (tmp_path / "CONVENTIONS.md").write_text("# Conventions\n\nIntro.\n\n## Data\n- Cell {x, y}\n\n## Tests\nnode\n",
                                             encoding="utf-8")
    return tmp_path


def test_index(tmp_path):
    root = project(tmp_path)
    store = memstore.Store(tmp_path / "memory.db")
    emb = FakeEmbedder()
    counts = memindex.index_project(root, store, emb, SETTINGS)
    assert counts == {"chunks": 6, "changed": 6, "removed": 0, "embedded": 6}
    assert [c["id"] for c in store.all()] == [
        "code:src/a.py:f", "code:src/a.py:g", "doc:CONVENTIONS.md:0", "doc:CONVENTIONS.md:1", "doc:CONVENTIONS.md:2",
        "test:tests/test_a.py:test_f"]
    f = store.get("code:src/a.py:f")
    assert (f["kind"], f["source"], f["title"]) == ("code", "src/a.py", "src/a.py:f")
    assert f["text"] == "src/a.py\ndef f(x)\ndef f(x):\n    return x"
    d0, d1 = store.get("doc:CONVENTIONS.md:0"), store.get("doc:CONVENTIONS.md:1")
    assert (d0["title"], d0["text"]) == ("CONVENTIONS.md", "# Conventions\n\nIntro.")
    assert (d1["title"], d1["text"]) == ("Data", "## Data\n- Cell {x, y}")
    assert store.get("test:tests/test_a.py:test_f")["kind"] == "test"
    assert emb.batches == [[store.get(i)["text"] for i in sorted(c["id"] for c in store.all())]]
    assert set(store.vectors("fake")) == {c["id"] for c in store.all()}
    store.close()


def test_index_again_only_changes(tmp_path):
    root = project(tmp_path)
    store = memstore.Store(tmp_path / "memory.db")
    memindex.index_project(root, store, FakeEmbedder(), SETTINGS)
    (root / "src" / "a.py").write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
    emb = FakeEmbedder()
    counts = memindex.index_project(root, store, emb, SETTINGS)
    assert counts == {"chunks": 5, "changed": 1, "removed": 1, "embedded": 1}
    assert store.get("code:src/a.py:g") is None
    assert emb.batches == [[store.get("code:src/a.py:f")["text"]]]
    store.close()


def test_batches_of_32(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "many.py").write_text("".join(f"def f{i}():\n    return {i}\n\n" for i in range(40)),
                                              encoding="utf-8")
    store = memstore.Store(tmp_path / "memory.db")
    emb = FakeEmbedder()
    assert memindex.index_project(tmp_path, store, emb, SETTINGS)["embedded"] == 40
    assert [len(b) for b in emb.batches] == [32, 8]
    store.close()


def test_without_an_embedder(tmp_path):
    store = memstore.Store(tmp_path / "memory.db")
    counts = memindex.index_project(project(tmp_path), store, None, SETTINGS)
    assert counts["embedded"] == 0 and counts["chunks"] == 6
    store.close()
