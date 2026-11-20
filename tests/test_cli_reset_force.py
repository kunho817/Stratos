"""Tests for task reset_force (P6, 2026-11-20): `stratos reset` refuses a task whose status is "done" unless
--force is given. Claude reset Drift's T003 right after a run had finished it (the earlier, cancelled command had
gone on further than Claude knew) and threw the finished work away.

Without --force, a done task: a message on stderr containing "is done" and "--force", return 1, nothing changed
(the worktree, the branch, the status and the commit stay; no decision, no telemetry). With --force the reset goes on
as before. Tasks in any other status are reset without --force, as before. The merged-commit refusal still applies
with --force."""
import json
import subprocess

import pytest

from stratos import __main__ as cli
from stratos import config, gitops
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
    return repo, tmp_path / "wt", Store(tmp_path / "state"), tmp_path / "state"


def done_task(repo, root, store):
    t = store.add_task("t", "g", [], [], ["x"])
    wt = gitops.ensure_worktree(repo, root, t["id"])
    (wt / "b.py").write_text("B = 1\n", encoding="utf-8")
    sha = gitops.commit_all(wt, "work")
    store.update(t["id"], status="done", worktree=str(wt), commit=sha)
    return t["id"], wt, sha


def test_a_done_task_needs_force(proj, capsys):
    repo, root, store, state = proj
    tid, wt, sha = done_task(repo, root, store)
    assert cli.main(["reset", tid, "--reason", "oops"]) == 1
    err = capsys.readouterr().err
    assert "is done" in err and "--force" in err
    t = store.get(tid)
    assert (t["status"], t["commit"]) == ("done", sha) and wt.exists()
    assert not (state / "decisions.jsonl").exists() or "reset_by_human" not in (state / "decisions.jsonl").read_text(encoding="utf-8")


def test_force_resets_a_done_task(proj, capsys):
    repo, root, store, state = proj
    tid, wt, sha = done_task(repo, root, store)
    assert cli.main(["reset", tid, "--reason", "really", "--force"]) == 0
    assert store.get(tid)["status"] == "todo" and not wt.exists()


def test_other_statuses_need_no_force(proj):
    repo, root, store, state = proj
    t = store.add_task("t", "g", [], [], ["x"])
    store.update(t["id"], status="needs_human")
    assert cli.main(["reset", t["id"], "--reason", "again"]) == 0
    assert store.get(t["id"])["status"] == "todo"
