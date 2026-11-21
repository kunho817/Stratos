"""Tests for task T018: `python -m stratos clean` removes the worktree and branch of every task whose status is 'done'
and whose branch stratos/<id> is merged into the repository's HEAD (gitops.remove_worktree), and records
cleaned=True and worktree=None on the task. Done tasks whose branch is not merged are kept. It prints
'cleaned <id>' or 'kept <id> (not merged)' per done task that still has a branch, then 'cleaned N task(s)', and
returns 0. A real git repository in a temporary folder stands in for the project."""
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


# ---- was test_cli_clean_locked.py ----
# Harness fix (Claude, 2026-11-21, cleaning the trials): VS Code held some task folders open, Windows refused to delete
# one ("in use by another process"), and `stratos clean` stopped at it with a traceback - the other done tasks stayed.
#
# `stratos clean`: a task whose worktree cannot be removed (OSError or RuntimeError from gitops.remove_worktree) prints
# f"kept {id} (its folder is in use: close it in other programs such as VS Code and run clean again)" and the loop goes
# on; such a task is not counted, its store entry is not changed, and the command still returns 0.


def test_a_locked_folder_does_not_stop_clean(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    store = Store(tmp_path / "state")
    for title in ("a", "b"):
        t = store.add_task(title, "g", ["x.py"], [], ["tests/t.py"])
        store.update(t["id"], status="done", worktree=t["id"])
    ids = [t["id"] for t in store.tasks()]

    def git(repo, *args):
        if args[:2] == ("branch", "--merged") or args[:2] == ("branch", "--list"):
            return "\n".join(f"  stratos/{i}" for i in ids)
        return ""
    monkeypatch.setattr(gitops, "git", git)

    def remove(repo, root, task_id, delete_branch=True):
        if task_id == ids[0]:
            raise PermissionError("[WinError 32] in use")
    monkeypatch.setattr(gitops, "remove_worktree", remove)
    assert cli.main(["clean"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert f"kept {ids[0]} (its folder is in use: close it in other programs such as VS Code and run clean again)" in out
    assert f"cleaned {ids[1]}" in out and out[-1] == "cleaned 1 task(s)"
    assert Store(tmp_path / "state").get(ids[0]).get("worktree") == ids[0]
