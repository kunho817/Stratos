"""Tests for task drop (P1, 2026-11-20, BACKLOG item 11): `python -m stratos drop <task id> --reason R` gives a task
up for good (T142's work went into T143, but T142 stayed needs_human forever).

Like `reset`, it removes the task's worktree and branch (gitops.remove_worktree) and refuses, changing nothing and
returning 1 with a message on stderr, when there is no such task or when the task's commit is already in HEAD
(the message contains "merged"). Then it sets status "dropped", worktree None, dropped_reason R; records a decision
(task, result "dropped_by_human", reason R) and a telemetry "verdict" event with the same task, result and reason;
prints f"dropped {id}" and returns 0. --reason is required. run-all never runs a dropped task (the scheduler only
runs "todo" tasks) and `status` lists it as "dropped"."""
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


def lines(path):
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_drop_a_stuck_task(proj, capsys):
    repo, root, store, state = proj
    t = store.add_task("t", "g", [], [], ["x"])
    wt = gitops.ensure_worktree(repo, root, t["id"])
    store.update(t["id"], status="needs_human", worktree=str(wt))
    assert cli.main(["drop", t["id"], "--reason", "done by T143"]) == 0
    assert f"dropped {t['id']}" in capsys.readouterr().out
    assert not wt.exists()
    assert gitops.git(repo, "branch", "--list", f"stratos/{t['id']}") == ""
    task = store.get(t["id"])
    assert task["status"] == "dropped" and task["worktree"] is None and task["dropped_reason"] == "done by T143"
    d = lines(state / "decisions.jsonl")[-1]
    assert (d["task"], d["result"], d["reason"]) == (t["id"], "dropped_by_human", "done by T143")
    (v,) = [e for e in lines(state / "telemetry.jsonl") if e["kind"] == "verdict"]
    assert (v["task"], v["result"], v["reason"]) == (t["id"], "dropped_by_human", "done by T143")
    cli.main(["status"])
    assert "dropped" in capsys.readouterr().out


def test_drop_a_todo_task_without_worktree(proj, capsys):
    repo, root, store, state = proj
    t = store.add_task("t", "g", [], [], ["x"])
    assert cli.main(["drop", t["id"], "--reason", "not needed"]) == 0
    assert store.get(t["id"])["status"] == "dropped"


def test_drop_refuses_a_merged_task(proj, capsys):
    repo, root, store, state = proj
    t = store.add_task("t", "g", [], [], ["x"])
    wt = gitops.ensure_worktree(repo, root, t["id"])
    (wt / "b.py").write_text("B = 1\n", encoding="utf-8")
    sha = gitops.commit_all(wt, "work")
    store.update(t["id"], status="done", worktree=str(wt), commit=sha)
    gitops.git(repo, *gitops.BOT, "merge", "--no-edit", "-q", f"stratos/{t['id']}")
    assert cli.main(["drop", t["id"], "--reason", "x"]) == 1
    assert "merged" in capsys.readouterr().err
    assert wt.exists() and store.get(t["id"])["status"] == "done"
    assert lines(state / "decisions.jsonl") == []


def test_drop_refuses_an_unknown_task(proj, capsys):
    assert cli.main(["drop", "T999", "--reason", "x"]) == 1
    assert "T999" in capsys.readouterr().err


def test_reason_is_required(proj):
    repo, root, store, state = proj
    t = store.add_task("t", "g", [], [], ["x"])
    with pytest.raises(SystemExit):
        cli.main(["drop", t["id"]])
