import subprocess

import pytest

from stratos import gitops


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / "a.py").write_text("A = 1\n", encoding="utf-8")
    gitops.git(tmp_path, "add", "-A")
    gitops.git(tmp_path, *gitops.BOT, "commit", "-q", "-m", "init")
    return tmp_path


def test_diff_shows_changes_and_new_files(repo):
    (repo / "a.py").write_text("A = 2\n", encoding="utf-8")
    (repo / "b.py").write_text("B = 1\n", encoding="utf-8")
    d = gitops.diff(repo)
    assert "-A = 1" in d and "+A = 2" in d and "+B = 1" in d


def test_discard_undoes_staged_and_new_files(repo):
    (repo / "a.py").write_text("A = 2\n", encoding="utf-8")
    (repo / "b.py").write_text("B = 1\n", encoding="utf-8")
    gitops.diff(repo)                      # stages everything
    gitops.discard_changes(repo)
    assert (repo / "a.py").read_text(encoding="utf-8") == "A = 1\n"
    assert not (repo / "b.py").exists()
    assert gitops.diff(repo) == ""


def test_commit_diff_and_undo_last_commit(repo):
    (repo / "a.py").write_text("A = 5\n", encoding="utf-8")
    (repo / "c.py").write_text("C = 1\n", encoding="utf-8")
    gitops.commit_all(repo, "candidate")
    d = gitops.commit_diff(repo)
    assert "+A = 5" in d and "+C = 1" in d
    gitops.undo_last_commit(repo)
    assert (repo / "a.py").read_text(encoding="utf-8") == "A = 1\n" and not (repo / "c.py").exists()
    assert gitops.git(repo, "log", "-1", "--format=%s") == "init"


def test_commit_all_uses_the_bot_name(repo):
    (repo / "a.py").write_text("A = 3\n", encoding="utf-8")
    gitops.commit_all(repo, "change")
    assert gitops.git(repo, "log", "-1", "--format=%an <%ae>") == "Stratos <stratos@localhost>"


def test_remove_worktree_when_windows_holds_the_emptied_folder(tmp_path, monkeypatch):
    """(Claude, 2026-11-21) `git worktree remove` failed with "Permission denied" three times this session: a shell
    still had its cwd in the folder. git had already emptied it and dropped it from its list, so the empty folder
    left behind counts as removed (the next worktree add takes an empty folder) and reset goes on."""
    calls = []
    folder = tmp_path / "wt" / "T9"
    folder.mkdir(parents=True)
    (folder / "f.txt").write_text("x", encoding="utf-8")

    def fake_git(repo, *args):
        calls.append(args)
        if args[:2] == ("worktree", "remove"):
            (folder / "f.txt").unlink()   # git empties it, then cannot delete the folder itself
            raise RuntimeError("git worktree remove --force ... failed: error: failed to delete: Permission denied")
        return ""
    monkeypatch.setattr(gitops, "git", fake_git)
    gitops.remove_worktree(tmp_path, tmp_path / "wt", "T9")
    assert ("worktree", "prune", "-v") in calls
    folder.mkdir(exist_ok=True)
    (folder / "f.txt").write_text("x", encoding="utf-8")

    def still_full(repo, *args):
        if args[:2] == ("worktree", "remove"):
            raise RuntimeError("failed: Permission denied")
        return ""
    monkeypatch.setattr(gitops, "git", still_full)
    with pytest.raises(RuntimeError):
        gitops.remove_worktree(tmp_path, tmp_path / "wt", "T9")   # files still there: a real failure
