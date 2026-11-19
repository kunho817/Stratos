"""Tests for task memstore: stratos/memstore.py, the memory's SQLite store and keyword search (memory M2).

tokenize(text) -> list of tokens: for every word matching [A-Za-z0-9_$]+ in order, its lowercase form, followed by
its parts when it has more than one: split at "_" and "$" and at camelCase / digit boundaries (lowercased, empty
parts dropped). "towerStats" -> "towerstats", "tower", "stats"; "TOWER_TYPES" -> "tower_types", "tower", "types";
"HTTPServer2" -> "httpserver2", "http", "server", "2".

bm25(query_tokens, docs_tokens, k1=1.5, b=0.75) -> one float per doc, the Okapi BM25 score with
idf = ln(1 + (N - n + 0.5) / (n + 0.5)) (N docs, n docs holding the term), term frequency f in the doc, doc length
|d| and average length avgdl: sum over the distinct query terms of idf * f * (k1 + 1) / (f + k1 * (1 - b + b * |d| /
avgdl)). No docs -> []. A doc with no query term scores 0.0.

Store(path): a SQLite file (folders made), two tables:
  chunks(id TEXT PRIMARY KEY, kind TEXT, source TEXT, title TEXT, text TEXT, hash TEXT)
  vectors(id TEXT PRIMARY KEY, model TEXT, hash TEXT, vec BLOB)
- upsert(chunk) with chunk = {"id", "kind", "source", "title", "text"}: hash = sha256 of text (hex). Returns True when
  the chunk is new or its hash changed, else False (nothing written).
- get(id) -> the chunk dict with its "hash", or None. all(kind=None) -> every chunk (of that kind), sorted by id.
- remove_except(kind, keep_ids) -> removes the chunks of that kind whose id is not in keep_ids, and their vectors;
  returns how many were removed.
- set_vector(id, model, hash, vec): vec a list of floats, stored as float32 bytes (array("f")).
- vectors(model) -> {id: list of floats} for the vectors of that model whose hash equals their chunk's hash.
- stale(model) -> sorted ids of chunks that have no vector of that model or whose vector's hash differs.
- close()."""
import math

import pytest

from stratos import memstore


def test_tokenize():
    assert memstore.tokenize("towerStats TOWER_TYPES sell-refund") == [
        "towerstats", "tower", "stats", "tower_types", "tower", "types", "sell", "refund"]
    assert memstore.tokenize("HTTPServer2 x") == ["httpserver2", "http", "server", "2", "x"]
    assert memstore.tokenize("") == []


def test_bm25_values():
    docs = [["a", "b"], ["a"], ["c", "c", "c"]]
    scores = memstore.bm25(["a"], docs)
    # N = 3, n = 2: idf = ln(1 + 1.5 / 2.5) = ln(1.6); avgdl = 2
    idf = math.log(1.6)
    want0 = idf * 1 * 2.5 / (1 + 1.5 * (0.25 + 0.75 * 2 / 2))
    want1 = idf * 1 * 2.5 / (1 + 1.5 * (0.25 + 0.75 * 1 / 2))
    assert scores[0] == pytest.approx(want0) and scores[1] == pytest.approx(want1) and scores[2] == 0.0
    assert scores[1] > scores[0]            # the shorter doc wins
    assert memstore.bm25(["a"], []) == []


def test_bm25_counts_a_query_term_once():
    docs = [["a"], ["b"]]
    assert memstore.bm25(["a", "a"], docs) == memstore.bm25(["a"], docs)


def chunk(i, kind="code", text=None):
    return {"id": i, "kind": kind, "source": "src/x.js", "title": i.upper(), "text": text or f"text of {i}"}


def test_store(tmp_path):
    s = memstore.Store(tmp_path / "m" / "memory.db")
    assert s.upsert(chunk("b")) is True
    assert s.upsert(chunk("a")) is True
    assert s.upsert(chunk("a")) is False
    assert s.upsert(chunk("a", text="new")) is True
    s.upsert(chunk("d", kind="doc"))
    a = s.get("a")
    assert a["text"] == "new" and a["title"] == "A" and len(a["hash"]) == 64
    assert s.get("zz") is None
    assert [c["id"] for c in s.all()] == ["a", "b", "d"]
    assert [c["id"] for c in s.all("code")] == ["a", "b"]
    s.close()
    again = memstore.Store(tmp_path / "m" / "memory.db")
    assert again.get("b")["text"] == "text of b"
    again.close()


def test_vectors(tmp_path):
    s = memstore.Store(tmp_path / "memory.db")
    for i in ("a", "b", "c"):
        s.upsert(chunk(i))
    assert s.stale("m1") == ["a", "b", "c"]
    s.set_vector("a", "m1", s.get("a")["hash"], [0.5, 0.25])
    s.set_vector("b", "m1", "old-hash", [1.0, 0.0])
    s.set_vector("c", "m2", s.get("c")["hash"], [1.0])
    assert s.vectors("m1") == {"a": [0.5, 0.25]}
    assert s.stale("m1") == ["b", "c"]
    s.upsert(chunk("a", text="changed"))
    assert s.stale("m1") == ["a", "b", "c"]
    s.close()


def test_remove_except(tmp_path):
    s = memstore.Store(tmp_path / "memory.db")
    for i in ("a", "b", "c"):
        s.upsert(chunk(i))
    s.upsert(chunk("d", kind="doc"))
    s.set_vector("b", "m1", s.get("b")["hash"], [1.0])
    assert s.remove_except("code", {"a"}) == 2
    assert [c["id"] for c in s.all()] == ["a", "d"]
    assert s.vectors("m1") == {}
    s.close()
