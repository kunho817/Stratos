"""Tests for task recall_tags: every general lesson for a role is in its pack, chosen by tag, not by search.

Ledger round 2 (2026-11-19): the goal spoke of lists, rules and thousands separators, so the search did not bring
the "[plan, cli, errors]" lesson and nobody planned bad-input handling again. The lessons are few and short, so a
role gets all of its own.

recall.pack(store, query, embedder=None, cmap=None, budget=12000, sections=None, always_tags=None): with a set
always_tags, the pack starts with the section "GENERAL LESSONS (from earlier projects):\n" + "\n".join(f"- {text}"
for every "guide" chunk of store.all("guide") whose tags (its title split on ", ") share a tag with always_tags), and
the ("guide", ...) entry of the sections is skipped (no search for guides). The budget counts these lines too: a line
that does not fit is left out. No matching guide -> no such section. always_tags None -> as before.

Callers: `stratos plan` passes always_tags={"plan"}, plantests.draft_tests always_tags={"tests"}, loop.task_memory
always_tags={"code"}."""
import pytest

from stratos import memsearch, memstore, recall


@pytest.fixture
def store(tmp_path):
    s = memstore.Store(tmp_path / "memory.db")
    for cid, title, text in [("guide:1", "plan, cli, errors", "[plan, cli, errors] Plan bad input."),
                             ("guide:2", "tests, floats", "[tests, floats] Use a tolerance."),
                             ("guide:3", "plan, data-flow", "[plan, data-flow] Follow the readers.")]:
        s.upsert({"id": cid, "kind": "guide", "source": "LESSONS.md", "title": title, "text": text})
    s.upsert({"id": "code:a.py:f", "kind": "code", "source": "a.py", "title": "a.py:f", "text": "def f(): pass"})
    yield s
    s.close()


def fake_search(calls):
    def search(store, query, embedder=None, cmap=None, k=10, kinds=None):
        calls.append(kinds)
        return [{"id": c["id"], "title": c["title"], "score": 0.1, "why": "keyword"}
                for c in store.all() if c["kind"] in kinds][:k]
    return search


def test_all_lessons_of_the_role(store, monkeypatch):
    calls = []
    monkeypatch.setattr(memsearch, "search", fake_search(calls))
    text = recall.pack(store, "list rules", always_tags={"plan"},
                       sections=[("guide", "GENERAL LESSONS (from earlier projects)", 4), ("code", "CODE", 2)])
    assert text == ("GENERAL LESSONS (from earlier projects):\n- [plan, cli, errors] Plan bad input.\n"
                    "- [plan, data-flow] Follow the readers.\n\nCODE:\n--- a.py:f (keyword)\ndef f(): pass")
    assert calls == [{"code"}]


def test_budget_and_no_match(store, monkeypatch):
    monkeypatch.setattr(memsearch, "search", fake_search([]))
    head = "GENERAL LESSONS (from earlier projects):\n- [plan, cli, errors] Plan bad input."
    assert recall.pack(store, "q", always_tags={"plan"}, sections=[], budget=len(head) + 5) == head
    assert recall.pack(store, "q", always_tags={"wiki"}, sections=[]) == ""


def test_without_tags_as_before(store, monkeypatch):
    calls = []
    monkeypatch.setattr(memsearch, "search", fake_search(calls))
    recall.pack(store, "q", sections=[("guide", "G", 1)])
    assert calls == [{"guide"}]
