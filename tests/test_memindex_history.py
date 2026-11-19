"""Tests for task memindex_history: past tasks go into the memory store (memory M3a).

memindex.index_history(store, tasks, events) -> {"chunks", "changed", "removed"}: chunks =
episodes.history_chunks(tasks, events); each is store.upsert-ed ("changed" counts True); then
store.remove_except("episode", <episode ids made now>) + store.remove_except("lesson", <lesson ids made now>) is
"removed". It embeds nothing: `stratos memory index` runs it before index_project, whose embedding step then embeds
every stale chunk, these included."""
from stratos import memindex, memstore

T1 = {"id": "T001", "title": "a", "goal": "g", "files": [], "status": "done", "role": "coder"}
T2 = {"id": "T002", "title": "b", "goal": "g", "files": [], "status": "done", "role": "coder"}
EV = [{"kind": "verdict", "task": "T001", "result": "reset_by_human", "reason": "wrong test"}]


def test_index_history(tmp_path):
    s = memstore.Store(tmp_path / "memory.db")
    s.upsert({"id": "code:a.py:f", "kind": "code", "source": "a.py", "title": "a.py:f", "text": "x"})
    assert memindex.index_history(s, [T1, T2], EV) == {"chunks": 3, "changed": 3, "removed": 0}
    assert [c["id"] for c in s.all()] == ["code:a.py:f", "episode:T001", "episode:T002", "lesson:reset:T001:1"]
    # T001 lost its reset event, so its episode text changed
    assert memindex.index_history(s, [T1], []) == {"chunks": 1, "changed": 1, "removed": 2}
    assert [c["id"] for c in s.all()] == ["code:a.py:f", "episode:T001"]
    s.close()
