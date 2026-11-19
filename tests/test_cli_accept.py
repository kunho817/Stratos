"""Tests for task accept (P2, 2026-11-20, BACKLOG item 15): `python -m stratos accept <task id> --reason R` marks a
task done with work a person did in its worktree (Lumen T002: Claude designed the levels by search and edited
tasks.json by hand so T003-T005 could run on top).

It refuses, changing nothing, and returns 1 with a message on stderr:
- no such task (the message holds the id);
- the task is already "done" (the message contains "already done");
- the task has no worktree folder (its "worktree" field missing, None or not an existing folder; "no worktree");
- after committing, branch stratos/<id> has no commit that HEAD of config.REPO lacks
  (`git rev-list --count HEAD..stratos/<id>` is 0; "nothing to accept").
Otherwise: uncommitted changes in the worktree are committed first (gitops.commit_all(wt, f"{id}: {title} (by a
person)\n\n{R}")); sha = `git rev-parse --short HEAD` in the worktree; store.update(id, status="done", commit=sha,
model="person", accepted_reason=R); store.decide(task=id, result="done_by_human", reason=R); a telemetry "verdict"
event with task, result "done_by_human" and reason; prints f"accepted {id} (commit {sha})" and returns 0. Tasks
that come after it can then run on its branch like after any done task. --reason is required."""
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


def stuck_task(repo, root, store):
    t = store.add_task("levels", "g", ["b.py"], [], ["x"])
    wt = gitops.ensure_worktree(repo, root, t["id"])
    store.update(t["id"], status="needs_human", worktree=str(wt))
    return t["id"], wt


def test_accept_uncommitted_work(proj, capsys):
    repo, root, store, state = proj
    tid, wt = stuck_task(repo, root, store)
    (wt / "b.py").write_text("B = 2\n", encoding="utf-8")
    assert cli.main(["accept", tid, "--reason", "designed by search"]) == 0
    sha = gitops.git(wt, "rev-parse", "--short", "HEAD").strip()
    assert f"accepted {tid} (commit {sha})" in capsys.readouterr().out
    assert gitops.git(wt, "status", "--porcelain").strip() == ""
    assert "(by a person)" in gitops.git(wt, "log", "-1", "--format=%B")
    t = store.get(tid)
    assert (t["status"], t["commit"], t["model"], t["accepted_reason"]) == ("done", sha, "person", "designed by search")
    d = lines(state / "decisions.jsonl")[-1]
    assert (d["task"], d["result"], d["reason"]) == (tid, "done_by_human", "designed by search")
    (v,) = [e for e in lines(state / "telemetry.jsonl") if e["kind"] == "verdict"]
    assert (v["task"], v["result"], v["reason"]) == (tid, "done_by_human", "designed by search")


def test_accept_work_already_committed(proj, capsys):
    repo, root, store, state = proj
    tid, wt = stuck_task(repo, root, store)
    (wt / "b.py").write_text("B = 2\n", encoding="utf-8")
    gitops.commit_all(wt, "by hand")
    assert cli.main(["accept", tid, "--reason", "r"]) == 0
    assert store.get(tid)["commit"] == gitops.git(wt, "rev-parse", "--short", "HEAD").strip()


def test_nothing_to_accept(proj, capsys):
    repo, root, store, state = proj
    tid, wt = stuck_task(repo, root, store)
    assert cli.main(["accept", tid, "--reason", "r"]) == 1
    assert "nothing to accept" in capsys.readouterr().err
    assert store.get(tid)["status"] == "needs_human"


def test_refusals(proj, capsys):
    repo, root, store, state = proj
    assert cli.main(["accept", "T999", "--reason", "r"]) == 1
    assert "T999" in capsys.readouterr().err
    t = store.add_task("t", "g", [], [], ["x"])
    assert cli.main(["accept", t["id"], "--reason", "r"]) == 1
    assert "no worktree" in capsys.readouterr().err
    store.update(t["id"], status="done")
    assert cli.main(["accept", t["id"], "--reason", "r"]) == 1
    assert "already done" in capsys.readouterr().err
    assert lines(state / "decisions.jsonl") == []


def test_reason_is_required(proj):
    repo, root, store, state = proj
    tid, wt = stuck_task(repo, root, store)
    with pytest.raises(SystemExit):
        cli.main(["accept", tid])
