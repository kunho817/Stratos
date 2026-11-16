"""Tests for task T015: gitops.remove_worktree(repo, root, task_id, delete_branch=True) removes a task's worktree
(root/<task_id>), prunes git's worktree list and, unless delete_branch is False, deletes the branch stratos/<task_id>.
Removing a task that has no worktree or branch does nothing and raises nothing."""
import subprocess

import pytest

from stratos import gitops


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    (r / "a.py").write_text("A = 1\n", encoding="utf-8")
    gitops.git(r, "add", "-A")
    gitops.git(r, *gitops.BOT, "commit", "-q", "-m", "init")
    return r


def branches(repo):
    return gitops.git(repo, "branch", "--list", "stratos/*")


def test_remove_worktree_and_branch(repo, tmp_path):
    root = tmp_path / "wt"
    wt = gitops.ensure_worktree(repo, root, "T001")
    assert wt.exists() and "stratos/T001" in branches(repo)
    gitops.remove_worktree(repo, root, "T001")
    assert not wt.exists()
    assert "stratos/T001" not in branches(repo)
    assert str(wt).replace("\\", "/") not in gitops.git(repo, "worktree", "list").replace("\\", "/")


def test_keep_the_branch_when_asked(repo, tmp_path):
    root = tmp_path / "wt"
    gitops.ensure_worktree(repo, root, "T001")
    gitops.remove_worktree(repo, root, "T001", delete_branch=False)
    assert not (root / "T001").exists()
    assert "stratos/T001" in branches(repo)


def test_removing_an_unknown_task_does_nothing(repo, tmp_path):
    gitops.remove_worktree(repo, tmp_path / "wt", "T009")
    assert branches(repo) == ""
