"""Tests for task replay_memory (P14, M6 A/B, 2026-11-20): does memory help the coder? A fair replay may not show what
was learned FROM the replayed task, nor code or wiki notes written after it (they hold the answer), so the replay
pack holds lessons only.

replay.lesson_pack(store, task, embedder=None) -> str or None: recall.pack(store, task["title"] + "\\n" +
task["goal"], embedder, None, budget=6000, sections=[("lesson", "LESSONS FROM PEOPLE'S CORRECTIONS", 3)],
always_tags={"code"}), then every line that names the task's id as a whole word (re \\b<id>\\b) is dropped; None
when nothing is left but headings, or when the pack is empty.
replay.replay(..., memory=False): with memory=True and STATE_DIR/memory.db present, each attempt's messages are
context.build_messages(task, path, failure, memory=<the lesson pack>); without, as before.
`stratos replay --memory ...` passes memory=True."""
from stratos import replay


class Store:
    pass


def test_lesson_pack_drops_lines_about_the_task(monkeypatch):
    from stratos import recall
    text = ("GENERAL LESSONS (from earlier projects):\n- Compare floats with a tolerance. (td: reset:T003:1)\n"
            "- Name the old tests a change breaks. (stratos: reset:T012:1)\n\n"
            "LESSONS FROM PEOPLE'S CORRECTIONS:\n- T012 was reset: the test pinned old output")
    seen = {}

    def fake_pack(store, query, embedder=None, cmap=None, budget=12000, sections=None, always_tags=None):
        seen.update(query=query, sections=sections, always_tags=always_tags, budget=budget, cmap=cmap)
        return text
    monkeypatch.setattr(recall, "pack", fake_pack)
    got = replay.lesson_pack(Store(), {"id": "T012", "title": "t", "goal": "g"})
    assert "T012" not in got and "Compare floats with a tolerance." in got
    assert seen["sections"] == [("lesson", "LESSONS FROM PEOPLE'S CORRECTIONS", 3)]
    assert seen["always_tags"] == {"code"} and seen["budget"] == 6000 and seen["cmap"] is None
    assert seen["query"] == "t\ng"
    monkeypatch.setattr(recall, "pack", lambda *a, **k: "LESSONS FROM PEOPLE'S CORRECTIONS:\n- T012 only")
    assert replay.lesson_pack(Store(), {"id": "T012", "title": "t", "goal": "g"}) is None
    monkeypatch.setattr(recall, "pack", lambda *a, **k: "")
    assert replay.lesson_pack(Store(), {"id": "T012", "title": "t", "goal": "g"}) is None


def test_cli_flag():
    import inspect

    from stratos import __main__ as cli
    src = inspect.getsource(cli._main)
    assert '"--memory"' in src and "memory=args.memory" in src
    assert "memory=False" in str(inspect.signature(replay.replay))
