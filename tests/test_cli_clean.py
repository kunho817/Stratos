"""Tests for task T018: `python -m stratos clean` removes the worktree and branch of every task whose status is 'done'
and whose branch stratos/<id> is merged into the repository's HEAD (gitops.remove_worktree), and records
cleaned=True and worktree=None on the task. Done tasks whose branch is not merged are kept. It prints
'cleaned <id>' or 'kept <id> (not merged)' per done task that still has a branch, then 'cleaned N task(s)', and
returns 0. A real git repository in a temporary folder stands in for the project."""
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
    return repo, tmp_path / "wt", Store(tmp_path / "state")


def finished_task(repo, root, store, name, merge):
    t = store.add_task(name, "g", [], [], ["x"])
    wt = gitops.ensure_worktree(repo, root, t["id"])
    (wt / f"{name}.py").write_text("X = 1\n", encoding="utf-8")
    gitops.commit_all(wt, f"{t['id']} work")
    store.update(t["id"], status="done", worktree=str(wt))
    if merge:
        gitops.git(repo, *gitops.BOT, "merge", "--no-edit", "-q", f"stratos/{t['id']}")
    return t["id"], wt


def branches(repo):
    return gitops.git(repo, "branch", "--list", "stratos/*")


def test_clean_removes_merged_done_tasks_only(proj, capsys):
    repo, root, store = proj
    merged, merged_wt = finished_task(repo, root, store, "m", merge=True)
    unmerged, unmerged_wt = finished_task(repo, root, store, "u", merge=False)
    assert cli.main(["clean"]) == 0
    out = capsys.readouterr().out
    assert f"cleaned {merged}" in out and f"kept {unmerged} (not merged)" in out and "cleaned 1 task(s)" in out
    assert not merged_wt.exists() and unmerged_wt.exists()
    assert f"stratos/{merged}" not in branches(repo) and f"stratos/{unmerged}" in branches(repo)
    t = store.get(merged)
    assert t["cleaned"] is True and t["worktree"] is None


def test_clean_ignores_tasks_that_are_not_done(proj, capsys):
    repo, root, store = proj
    t = store.add_task("w", "g", [], [], ["x"])
    wt = gitops.ensure_worktree(repo, root, t["id"])
    store.update(t["id"], status="needs_human", worktree=str(wt))
    assert cli.main(["clean"]) == 0
    assert wt.exists()
    assert "cleaned 0 task(s)" in capsys.readouterr().out


def test_clean_twice_is_harmless(proj, capsys):
    repo, root, store = proj
    finished_task(repo, root, store, "m", merge=True)
    cli.main(["clean"])
    assert cli.main(["clean"]) == 0
    assert "cleaned 0 task(s)" in capsys.readouterr().out.splitlines()[-1]
