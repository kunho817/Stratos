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


def test_merged_dependencies_are_not_bases(repo, tmp_path):
    """Harness fix (2026-11-18): T076 ran after T075, but T075 was already merged into main, and T076's copy still
    started from stratos/T075 - without the test fixes made on main since. A dependency whose branch is already in
    HEAD is left out, so a task whose dependencies are all merged starts from HEAD."""
    root = tmp_path / "wt"
    task_branch(repo, root, "T001", {"b.py": "B = 1\n"})
    task_branch(repo, root, "T003", {"c.py": "C = 1\n"})
    gitops.git(repo, *gitops.BOT, "merge", "--no-edit", "stratos/T001")
    assert gitops.dependency_bases(repo, ["T001", "T003"]) == ["stratos/T003"]
    assert gitops.dependency_bases(repo, ["T001"]) == []


def test_a_new_copy_also_gets_what_main_got_since(repo, tmp_path):
    """Harness fix (2026-11-19): T083 ran after T080 (not merged yet), and a test fix committed on main after T080's
    branch was made never reached T083's copy. A copy made from dependency branches now also merges HEAD."""
    root = tmp_path / "wt"
    task_branch(repo, root, "T001", {"b.py": "B = 1\n"})
    (repo / "tests_fix.py").write_text("FIXED = True\n", encoding="utf-8")
    gitops.git(repo, "add", "-A")
    gitops.git(repo, *gitops.BOT, "commit", "-q", "-m", "fix a test on main")
    wt = gitops.ensure_worktree(repo, root, "T002", bases=["stratos/T001"])
    assert (wt / "b.py").exists() and (wt / "tests_fix.py").exists()


def test_main_conflicting_with_a_base_is_a_base_conflict(repo, tmp_path):
    root = tmp_path / "wt"
    task_branch(repo, root, "T001", {"a.py": "A = 2\n"})
    (repo / "a.py").write_text("A = 3\n", encoding="utf-8")
    gitops.git(repo, "add", "-A")
    gitops.git(repo, *gitops.BOT, "commit", "-q", "-m", "main changes a.py too")
    with pytest.raises(gitops.BaseConflict):
        gitops.ensure_worktree(repo, root, "T002", bases=["stratos/T001"])
    assert not (root / "T002").exists()
