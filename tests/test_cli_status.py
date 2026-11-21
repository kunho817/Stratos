"""Tests for task T019 (after T018): `python -m stratos status` appends '  [wt]' to the line of every task whose
worktree folder still exists, so leftovers that `clean` could remove are visible. The rest of the line is unchanged.
It uses `clean` from T018, so it only passes on top of T018's work."""
import subprocess

import pytest

from stratos import __main__ as cli, config, gitops
from stratos.state import Store


@pytest.fixture
def proj(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    (repo / "a.py").write_text("A = 1\n", encoding="utf-8")
    gitops.git(repo, "add", "-A")
    gitops.git(repo, *gitops.BOT, "commit", "-q", "-m", "init")
    monkeypatch.setattr(config, "REPO", repo)
    monkeypatch.setattr(config, "WORKTREES", tmp_path / "wt")
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    return repo, tmp_path / "wt", Store(tmp_path / "state")


def status_lines(capsys):
    cli.main(["status"])
    return capsys.readouterr().out.splitlines()


def test_status_marks_tasks_with_a_worktree_until_clean(proj, capsys):
    repo, root, store = proj
    t = store.add_task("thing", "g", [], [], ["x"])
    other = store.add_task("other", "g", [], [], ["x"])
    wt = gitops.ensure_worktree(repo, root, t["id"])
    (wt / "t.py").write_text("X = 1\n", encoding="utf-8")
    gitops.commit_all(wt, "work")
    store.update(t["id"], status="done", worktree=str(wt), commit="abc1234")
    lines = status_lines(capsys)
    assert lines[0].startswith("T001  done") and lines[0].endswith("  [wt]")
    assert "commit abc1234" in lines[0]
    assert not lines[1].endswith("[wt]")
    gitops.git(repo, *gitops.BOT, "merge", "--no-edit", "-q", f"stratos/{t['id']}")
    cli.main(["clean"])
    capsys.readouterr()
    assert not status_lines(capsys)[0].endswith("[wt]")


# ---- was test_cli_status_triage.py ----
# Tests for `stratos status` showing a triage verdict (plan P009, task status_triage).
#
# A needs_human task with a "triage" field ({"verdict", "test", "reason"}) gets " [triage: <verdict>]" at the end of
# its status line. Other tasks, and needs_human tasks without a triage, look as before.
# (The planner model's draft set config.STATE_DIR without monkeypatch, which leaks into every later test; rewritten.)


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
