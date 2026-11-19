"""Tests for task memsearch: stratos/memsearch.py, hybrid search over the memory store (memory M2).

search(store, query, embedder=None, cmap=None, k=10) -> list of {"id", "title", "score", "why"}:
- Keyword list: bm25(tokenize(query), [tokenize(title + " " + text) for each chunk in store.all()]); the chunks
  with a score > 0, best first (ties by id).
- Vector list (only with an embedder): q = embedder.embed_query(query); every vector of store.vectors(embedder.name)
  ranked by cosine similarity to q, best first (ties by id); a zero vector has similarity 0.
- Reciprocal rank fusion: score(id) = sum over the lists it is in of 1 / (60 + rank), rank counted from 1. "why" is
  "keyword", "vector" or "keyword+vector". The k best by score (ties by id) are the hits, best first.
- Expansion (only with a cmap): for each hit in order whose id is f"code:{path}:{name}" or f"test:{path}:{name}",
  every user u in codemap.users(cmap, name) (as "path:symbol") whose chunk f"code:{u}" or f"test:{u}" exists in the
  store and is not already in the result is appended after the hits as {"id", "title", "score": <the hit's score> /
  2, "why": f"uses {name}"}, in that order, each id once.
- An empty store gives []."""
import math

import pytest

from stratos import codemap, memsearch, memstore


class FakeEmbedder:
    name = "fake"

    def __init__(self, query_vec):
        self.query_vec = query_vec

    def embed_query(self, text):
        return self.query_vec


def make_store(tmp_path):
    s = memstore.Store(tmp_path / "memory.db")
    chunks = [
        ("code:src/towers.js:towerStats", "code", "towerStats returns range and damage by level"),
        # (no "towers" here: with stemming it would match "tower")
        ("code:src/step.js:step", "code", "move enemies and let them shoot"),
        ("code:src/waves.js:waveDef", "code", "wave count hp speed gold, boss every fifth wave"),
        ("doc:CONVENTIONS.md:1", "doc", "Tower: type x y cooldownLeft level"),
    ]
    for cid, kind, text in chunks:
        s.upsert({"id": cid, "kind": kind, "source": cid.split(":")[1], "title": cid.split(":", 1)[1], "text": text})
    return s


def test_keyword_only(tmp_path):
    s = make_store(tmp_path)
    hits = memsearch.search(s, "boss wave hp", k=3)
    assert hits[0]["id"] == "code:src/waves.js:waveDef" and hits[0]["why"] == "keyword"
    assert hits[0]["score"] == pytest.approx(1 / 61)
    assert all(h["why"] == "keyword" for h in hits)
    assert hits[0]["title"] == "src/waves.js:waveDef"
    s.close()


def test_fusion(tmp_path):
    s = make_store(tmp_path)
    vecs = {"code:src/towers.js:towerStats": [1.0, 0.0], "code:src/step.js:step": [0.6, 0.8],
            "code:src/waves.js:waveDef": [0.0, 1.0], "doc:CONVENTIONS.md:1": [0.0, 0.0]}
    for cid, v in vecs.items():
        s.set_vector(cid, "fake", s.get(cid)["hash"], v)
    hits = memsearch.search(s, "tower level", embedder=FakeEmbedder([1.0, 0.0]), k=10)
    by = {h["id"]: h for h in hits}
    # keyword: "tower" and "level" are in towerStats (title tokens "towerstats tower stats", text "level") and in the
    # doc ("Tower", "level"); vector ranks: towerStats 1, step 2 (0.6), then waveDef and the doc (0.0) by id
    assert by["code:src/towers.js:towerStats"]["why"] == "keyword+vector"
    assert by["code:src/step.js:step"]["why"] == "vector"
    assert by["code:src/step.js:step"]["score"] == pytest.approx(1 / 62)
    assert hits[0]["id"] == "code:src/towers.js:towerStats"
    assert by["code:src/towers.js:towerStats"]["score"] == pytest.approx(
        1 / 61 + 1 / (60 + 1 + [h["id"] for h in memsearch.search(s, "tower level", k=10)].index(
            "code:src/towers.js:towerStats")))
    s.close()


def test_expansion_through_the_code_map(tmp_path):
    s = make_store(tmp_path)
    cmap = {"test_dir": "tests", "files": {
        "src/towers.js": [{"name": "towerStats", "kind": "function", "uses": []}],
        "src/step.js": [{"name": "step", "kind": "function", "uses": ["towerStats"]}],
        "src/main.js": [{"name": "(top level)", "kind": "script", "uses": ["towerStats"]}],
    }}
    hits = memsearch.search(s, "towerStats damage", cmap=cmap, k=1)
    assert [h["id"] for h in hits] == ["code:src/towers.js:towerStats", "code:src/step.js:step"]
    assert hits[1]["why"] == "uses towerStats" and hits[1]["score"] == pytest.approx(hits[0]["score"] / 2)
    assert hits[1]["title"] == "src/step.js:step"
    s.close()


def test_empty(tmp_path):
    s = memstore.Store(tmp_path / "memory.db")
    assert memsearch.search(s, "anything", embedder=FakeEmbedder([1.0])) == []
    s.close()
