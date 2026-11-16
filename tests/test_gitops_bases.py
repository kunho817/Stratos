"""Tests for task T016: a task's worktree can start from its dependencies' branches.

ensure_worktree(repo, root, task_id, bases=None)
  bases empty or None: branch stratos/<task_id> from HEAD, as before.
  one base: the new branch starts at that branch's tip.
  several: start at the first, then merge the others into the new worktree (as the Stratos bot). If a merge conflicts,
  abort it, remove the new worktree and branch, and raise gitops.BaseConflict naming the base.
  An existing worktree is returned as it is.
dependency_bases(repo, task_ids) -> ['stratos/<id>', ...] for the ids whose branch exists, in the given order."""
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


def task_branch(repo, root, task_id, files):
    wt = gitops.ensure_worktree(repo, root, task_id)
    for name, body in files.items():
        (wt / name).write_text(body, encoding="utf-8")
    gitops.commit_all(wt, f"{task_id} work")
    return wt


def branch_exists(repo, name):
    return bool(gitops.git(repo, "branch", "--list", name))


def test_no_bases_starts_from_head(repo, tmp_path):
    root = tmp_path / "wt"
    wt = gitops.ensure_worktree(repo, root, "T001", bases=[])
    assert (wt / "a.py").exists()
    assert gitops.git(wt, "rev-parse", "HEAD") == gitops.git(repo, "rev-parse", "HEAD")


def test_one_base(repo, tmp_path):
    root = tmp_path / "wt"
    task_branch(repo, root, "T001", {"b.py": "B = 1\n"})
    wt = gitops.ensure_worktree(repo, root, "T002", bases=["stratos/T001"])
    assert (wt / "b.py").read_text(encoding="utf-8") == "B = 1\n"
    assert gitops.git(wt, "rev-parse", "HEAD") == gitops.git(repo, "rev-parse", "stratos/T001")
    assert branch_exists(repo, "stratos/T002")


def test_several_bases_are_merged(repo, tmp_path):
    root = tmp_path / "wt"
    task_branch(repo, root, "T001", {"b.py": "B = 1\n"})
    task_branch(repo, root, "T003", {"c.py": "C = 1\n"})
    wt = gitops.ensure_worktree(repo, root, "T004", bases=["stratos/T001", "stratos/T003"])
    assert (wt / "b.py").exists() and (wt / "c.py").exists()
    assert gitops.git(wt, "log", "-1", "--format=%an") == "Stratos"


def test_conflicting_bases(repo, tmp_path):
    root = tmp_path / "wt"
    task_branch(repo, root, "T001", {"a.py": "A = 2\n"})
    task_branch(repo, root, "T003", {"a.py": "A = 3\n"})
    with pytest.raises(gitops.BaseConflict) as e:
        gitops.ensure_worktree(repo, root, "T004", bases=["stratos/T001", "stratos/T003"])
    assert "stratos/T003" in str(e.value)
    assert not (root / "T004").exists()
    assert not branch_exists(repo, "stratos/T004")


def test_existing_worktree_is_returned(repo, tmp_path):
    root = tmp_path / "wt"
    first = gitops.ensure_worktree(repo, root, "T001")
    assert gitops.ensure_worktree(repo, root, "T001", bases=["stratos/whatever"]) == first


def test_dependency_bases(repo, tmp_path):
    root = tmp_path / "wt"
    task_branch(repo, root, "T001", {"b.py": "B = 1\n"})
    task_branch(repo, root, "T003", {"c.py": "C = 1\n"})
    assert gitops.dependency_bases(repo, ["T003", "T009", "T001"]) == ["stratos/T003", "stratos/T001"]
    assert gitops.dependency_bases(repo, []) == []
