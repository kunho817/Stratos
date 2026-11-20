"""Harness fix (Claude, 2026-11-21, cleaning the trials): VS Code held some task folders open, Windows refused to delete
one ("in use by another process"), and `stratos clean` stopped at it with a traceback - the other done tasks stayed.

`stratos clean`: a task whose worktree cannot be removed (OSError or RuntimeError from gitops.remove_worktree) prints
f"kept {id} (its folder is in use: close it in other programs such as VS Code and run clean again)" and the loop goes
on; such a task is not counted, its store entry is not changed, and the command still returns 0."""
from stratos import __main__ as cli
from stratos import config, gitops
from stratos.state import Store


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
