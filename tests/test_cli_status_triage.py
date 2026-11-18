"""Tests for `stratos status` showing a triage verdict (plan P009, task status_triage).

A needs_human task with a "triage" field ({"verdict", "test", "reason"}) gets " [triage: <verdict>]" at the end of
its status line. Other tasks, and needs_human tasks without a triage, look as before.
(The planner model's draft set config.STATE_DIR without monkeypatch, which leaks into every later test; rewritten.)"""
from stratos import __main__ as cli
from stratos import config
from stratos.state import Store


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    store = Store(tmp_path / "state")
    store.add_task("first", "g", ["a.py"], [], ["tests/a.py"])
    store.add_task("second", "g", ["b.py"], [], ["tests/b.py"])
    store.add_task("third", "g", ["c.py"], [], ["tests/c.py"])
    return store


def line_of(out, tid):
    return next(l for l in out.splitlines() if l.startswith(tid))


def test_verdict_after_a_needs_human_task(tmp_path, monkeypatch, capsys):
    store = setup(tmp_path, monkeypatch)
    store.update("T001", status="needs_human", triage={"verdict": "test_wrong", "test": "t", "reason": "r"})
    store.update("T002", status="needs_human")
    store.update("T003", status="done", triage={"verdict": "code_wrong", "test": "t", "reason": "r"})
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert line_of(out, "T001").endswith(" [triage: test_wrong]")
    assert "triage" not in line_of(out, "T002")
    assert "triage" not in line_of(out, "T003")
