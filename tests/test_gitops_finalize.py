"""Tests for task T020: gitops.finalize_commit_message(worktree, text) amends the last commit when its review approves
it: the title loses its ' (candidate, awaiting review)' ending (a title without it stays as it is), the body stays,
and text is appended after a blank line. The commit is amended as the Stratos bot; no new commit is added."""
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


def commit(repo, message):
    (repo / "a.py").write_text(f"# {message}\n", encoding="utf-8")
    gitops.commit_all(repo, message)


def message(repo):
    return gitops.git(repo, "log", "-1", "--format=%B").splitlines()


def test_candidate_title_is_cleaned_and_review_appended(repo):
    commit(repo, "T001: thing (candidate, awaiting review)\n\nWritten by tiel (attempt 1); tests: tests")
    gitops.finalize_commit_message(repo, "Review: approve")
    assert message(repo) == ["T001: thing", "", "Written by tiel (attempt 1); tests: tests", "", "Review: approve"]
    assert gitops.git(repo, "rev-list", "--count", "HEAD") == "2"
    assert gitops.git(repo, "log", "-1", "--format=%an") == "Stratos"


def test_other_titles_are_kept(repo):
    commit(repo, "T002: plain title\n\nbody")
    gitops.finalize_commit_message(repo, "Review: changes\n- [low] long line")
    assert message(repo) == ["T002: plain title", "", "body", "", "Review: changes", "- [low] long line"]


def test_title_only_commit(repo):
    commit(repo, "T003: short (candidate, awaiting review)")
    gitops.finalize_commit_message(repo, "Review: approve")
    assert message(repo) == ["T003: short", "", "Review: approve"]
