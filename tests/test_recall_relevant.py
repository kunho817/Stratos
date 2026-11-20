"""Tests for task recall_relevant (P14, 2026-11-21, the M6 A/B): the coder's pack began with EVERY general lesson tagged
"code" - the same ~1.5k characters for every task (checked on T155, T195, T204) - so memory said nothing about the
task at hand. Replaying 10 tasks Tiel had failed: 2/10 without memory, 3/10 with it.

recall.ALWAYS_N = 5. recall.pack with always_tags: when more than ALWAYS_N guide chunks share a tag with always_tags,
only ALWAYS_N of them go into the "GENERAL LESSONS" section: those ranked first by memsearch.search(store, query,
embedder, cmap, k=<the number of guide chunks>, kinds={"guide"}) among the tagged ones, then (when the search finds
fewer) the other tagged ones in store order; they are listed in that order. With ALWAYS_N or fewer tagged chunks,
all of them in store order and no search for "guide" (as before)."""
import pytest

from stratos import memsearch, memstore, recall


@pytest.fixture
def store(tmp_path):
    s = memstore.Store(tmp_path / "memory.db")
    for i in range(1, 8):
        s.upsert({"id": f"guide:{i}", "kind": "guide", "source": "LESSONS.md", "title": "code, x",
                  "text": f"[code, x] lesson {i}"})
    s.upsert({"id": "guide:9", "kind": "guide", "source": "LESSONS.md", "title": "plan", "text": "[plan] other"})
    yield s
    s.close()


def test_only_the_most_relevant(store, monkeypatch):
    calls = []

    def search(store_, query, embedder=None, cmap=None, k=10, kinds=None):
        calls.append((query, k, kinds))
        order = ["guide:9", "guide:6", "guide:2", "guide:7"]
        return [{"id": i, "title": "", "score": 1.0, "why": "keyword"} for i in order][:k]
    monkeypatch.setattr(memsearch, "search", search)
    text = recall.pack(store, "parse the dates", always_tags={"code"}, sections=[])
    assert text == ("GENERAL LESSONS (from earlier projects):\n- [code, x] lesson 6\n- [code, x] lesson 2\n"
                    "- [code, x] lesson 7\n- [code, x] lesson 1\n- [code, x] lesson 3")
    assert calls == [("parse the dates", 8, {"guide"})]


def test_few_lessons_need_no_search(store, monkeypatch):
    calls = []
    monkeypatch.setattr(memsearch, "search", lambda *a, **k: calls.append(1) or [])
    monkeypatch.setattr(recall, "ALWAYS_N", 10)
    text = recall.pack(store, "q", always_tags={"code"}, sections=[])
    assert text.count("- [code, x]") == 7 and calls == []
