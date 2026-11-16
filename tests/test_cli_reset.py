"""Tests for task T024: `python -m stratos reset <task id> --reason R` throws away a task's result so it runs again.

It removes the task's worktree and its branch stratos/<id> (gitops.remove_worktree), sets the task's status to
'todo' and its worktree and commit to None, records a decision (Store.decide) with task=<id>,
result='reset_by_human' and reason=R, and records a telemetry event of kind 'verdict' with the same task, result and
reason in config.STATE_DIR / 'telemetry.jsonl'. It prints 'reset <id>' and returns 0.

It refuses, changing nothing, and returns 1 with a message on stderr:
  - when there is no such task;
  - when the task has a commit (its 'commit' field) and that commit is already in the repository's HEAD
    (`git merge-base --is-ancestor <commit> HEAD`): the work is merged, and resetting would not take it back out of
    the main branch. A task without a commit (a worktree but nothing committed) is never refused for this.
--reason is required. A real git repository in a temporary folder stands in for the project."""
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


def finished_task(repo, root, store, merge=False):
    t = store.add_task("t", "g", [], [], ["x"])
    wt = gitops.ensure_worktree(repo, root, t["id"])
    (wt / "b.py").write_text("B = 1\n", encoding="utf-8")
    sha = gitops.commit_all(wt, f"{t['id']} work")
    store.update(t["id"], status="done", worktree=str(wt), commit=sha)
    if merge:
        gitops.git(repo, *gitops.BOT, "merge", "--no-edit", "-q", f"stratos/{t['id']}")
    return t["id"], wt


def lines(path):
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_reset_throws_the_result_away(proj, capsys):
    repo, root, store, state = proj
    tid, wt = finished_task(repo, root, store)
    assert cli.main(["reset", tid, "--reason", "harness bug"]) == 0
    assert f"reset {tid}" in capsys.readouterr().out
    assert not wt.exists()
    assert gitops.git(repo, "branch", "--list", f"stratos/{tid}") == ""
    t = store.get(tid)
    assert t["status"] == "todo" and t["worktree"] is None and t["commit"] is None
    d = lines(state / "decisions.jsonl")[-1]
    assert d["task"] == tid and d["result"] == "reset_by_human" and d["reason"] == "harness bug"
    v = [e for e in lines(state / "telemetry.jsonl") if e["kind"] == "verdict"]
    assert len(v) == 1
    assert v[0]["task"] == tid and v[0]["result"] == "reset_by_human" and v[0]["reason"] == "harness bug"


def test_reset_a_task_without_worktree(proj, capsys):
    repo, root, store, state = proj
    t = store.add_task("t", "g", [], [], ["x"])
    store.update(t["id"], status="needs_human")
    assert cli.main(["reset", t["id"], "--reason", "try again"]) == 0
    assert store.get(t["id"])["status"] == "todo"


def test_reset_a_task_with_an_empty_worktree(proj, capsys):
    repo, root, store, state = proj
    t = store.add_task("t", "g", [], [], ["x"])
    wt = gitops.ensure_worktree(repo, root, t["id"])
    store.update(t["id"], status="needs_human", worktree=str(wt))
    assert cli.main(["reset", t["id"], "--reason", "try again"]) == 0
    assert not wt.exists()
    assert store.get(t["id"])["status"] == "todo"


def test_reset_refuses_a_merged_task(proj, capsys):
    repo, root, store, state = proj
    tid, wt = finished_task(repo, root, store, merge=True)
    assert cli.main(["reset", tid, "--reason", "x"]) == 1
    assert "merged" in capsys.readouterr().err
    assert wt.exists()
    assert store.get(tid)["status"] == "done"
    assert lines(state / "decisions.jsonl") == []
    assert lines(state / "telemetry.jsonl") == []


def test_reset_refuses_an_unknown_task(proj, capsys):
    assert cli.main(["reset", "T999", "--reason", "x"]) == 1
    assert "T999" in capsys.readouterr().err


def test_reason_is_required(proj):
    repo, root, store, state = proj
    tid, _ = finished_task(repo, root, store)
    with pytest.raises(SystemExit):
        cli.main(["reset", tid])
