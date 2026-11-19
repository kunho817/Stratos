"""Tests for task recall: a context pack from memory for one role's prompt (memory M5).

recall.SECTIONS = [("guide", "GENERAL LESSONS (from earlier projects)", 4), ("lesson", "LESSONS FROM PEOPLE'S
CORRECTIONS", 5), ("episode", "PAST TASKS", 3), ("doc", "PROJECT CONVENTIONS", 3), ("code", "RELEVANT CODE", 6),
("test", "RELEVANT TESTS", 4)] (kind, heading, how many). (Memory A/B 2, 2026-11-19: code entries filled the budget
first and only 2 general lessons fit, so the short, general sections come first, task recall_order.)

recall.pack(store, query, embedder=None, cmap=None, budget=12000, sections=None) -> str. sections None ->
recall.SECTIONS. For each (kind, heading, n) in order: hits = memsearch.search(store, query, embedder, cmap, k=n,
kinds={kind}) (called through the memsearch module); no hits -> the section is left out. A section is
f"{heading}:\n" + "\n\n".join(one entry per hit), an entry being f"--- {title} ({why})\n{text}" with text the
chunk's text (store.get) cut to recall.CUT.get(kind, 1500) characters (+ "\n..." when cut), with recall.CUT =
{"code": 1000, "test": 800}. Sections are joined with "\n\n". The pack
never grows past budget characters: entries are added in order while the whole text stays within budget; an entry
that does not fit is skipped (later, smaller ones may still fit); a section none of whose entries fit is left out.
No sections -> ""."""
import pytest

from stratos import memsearch, memstore, recall


@pytest.fixture
def store(tmp_path):
    s = memstore.Store(tmp_path / "memory.db")
    for cid, kind, title, text in [
        ("code:a.js:f", "code", "a.js:f", "function f() {}"),
        ("code:b.js:g", "code", "b.js:g", "x" * 2000),
        ("test:t.js:test: f", "test", "t.js:test: f", "test f"),
        ("lesson:reset:T1:1", "lesson", "T1: a", "T1 a: the old test pinned wave 5"),
    ]:
        s.upsert({"id": cid, "kind": kind, "source": "s", "title": title, "text": text})
    yield s
    s.close()


def fake_search(results):
    calls = []

    def search(store, query, embedder=None, cmap=None, k=10, kinds=None):
        calls.append((query, k, kinds))
        (kind,) = kinds
        return [{"id": i, "title": store.get(i)["title"], "score": 0.1, "why": "keyword"}
                for i in results.get(kind, [])]
    return search, calls


def test_sections(store, monkeypatch):
    search, calls = fake_search({"code": ["code:a.js:f", "code:b.js:g"], "test": ["test:t.js:test: f"],
                                 "lesson": ["lesson:reset:T1:1"]})
    monkeypatch.setattr(memsearch, "search", search)
    text = recall.pack(store, "make f faster")
    # (task recall_order: the short, general sections come first; code entries are cut at 1000)
    assert [c[1:] for c in calls] == [(4, {"guide"}), (5, {"lesson"}), (3, {"episode"}), (3, {"doc"}), (6, {"code"}),
                                      (4, {"test"})]
    assert text == "\n\n".join([
        "LESSONS FROM PEOPLE'S CORRECTIONS:\n--- T1: a (keyword)\nT1 a: the old test pinned wave 5",
        "RELEVANT CODE:\n--- a.js:f (keyword)\nfunction f() {}\n\n--- b.js:g (keyword)\n" + "x" * 1000 + "\n...",
        "RELEVANT TESTS:\n--- t.js:test: f (keyword)\ntest f",
    ])


def test_budget(store, monkeypatch):
    search, _ = fake_search({"code": ["code:b.js:g", "code:a.js:f"], "lesson": ["lesson:reset:T1:1"]})
    monkeypatch.setattr(memsearch, "search", search)
    text = recall.pack(store, "q", budget=200)
    # the long entry does not fit; the short code entry and the lesson do
    assert text == ("LESSONS FROM PEOPLE'S CORRECTIONS:\n--- T1: a (keyword)\nT1 a: the old test pinned wave 5\n\n"
                    "RELEVANT CODE:\n--- a.js:f (keyword)\nfunction f() {}")
    assert len(text) <= 200
    assert recall.pack(store, "q", budget=10) == ""


def test_custom_sections_and_nothing_found(store, monkeypatch):
    search, calls = fake_search({})
    monkeypatch.setattr(memsearch, "search", search)
    assert recall.pack(store, "q", sections=[("code", "CODE", 2)]) == ""
    assert calls == [("q", 2, {"code"})]
