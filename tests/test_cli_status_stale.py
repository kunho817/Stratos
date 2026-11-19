"""Tests for task status_stale (P1, 2026-11-20, BACKLOG item 12): `status` warns when a test file a waiting task
lists was changed on main after the task was added (T151: Claude's lists named tests that another task of the same
batch changed; the task failed for that, not for its code).

gitops.changed_since(repo, paths, since) -> the paths (in the given order; "::..." suffixes cut off, repeats once)
whose last commit in repo (`git log -1 --format=%ct -- <path>`) is later than `since` (a time.time() float);
paths with no commit are left out.
`status`: after the line of each task whose status is "todo" or "needs_human", one line per such path:
f"  warning: {path} changed after {id} was added" (since = the task's "created"; a task without "created" is not
checked). Other tasks get no warnings."""
import os
import subprocess
import time

import pytest

from stratos import __main__ as cli
from stratos import config, gitops
from stratos.state import Store


def commit(repo, path, text, when):
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text, encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_DATE": f"{int(when)} +0000", "GIT_COMMITTER_DATE": f"{int(when)} +0000"}
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", *gitops.BOT, "commit", "-q", "-m", f"change {path}"], cwd=repo, check=True, env=env)


@pytest.fixture
def proj(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    now = time.time()
    commit(repo, "tests/test_old.py", "A = 1\n", now - 1000)
    commit(repo, "tests/test_new.py", "B = 1\n", now - 1000)
    commit(repo, "tests/test_new.py", "B = 2\n", now - 100)
    monkeypatch.setattr(config, "REPO", repo)
    monkeypatch.setattr(config, "WORKTREES", tmp_path / "wt")
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    return repo, Store(tmp_path / "state"), now


def test_changed_since(proj):
    repo, store, now = proj
    paths = ["tests/test_new.py::test_b", "tests/test_old.py", "tests/test_new.py", "tests/none.py"]
    assert gitops.changed_since(repo, paths, now - 500) == ["tests/test_new.py"]
    assert gitops.changed_since(repo, paths, now - 2000) == ["tests/test_new.py", "tests/test_old.py"]
    assert gitops.changed_since(repo, paths, now) == []


def test_status_warns_for_waiting_tasks(proj, capsys):
    repo, store, now = proj
    tests = ["tests/test_old.py", "tests/test_new.py::test_b"]
    for status in ("todo", "needs_human", "done"):
        t = store.add_task(status, "g", [], [], tests)
        store.update(t["id"], status=status, created=now - 500)
    fresh = store.add_task("fresh", "g", [], [], tests)
    store.update(fresh["id"], created=now)
    old = store.add_task("legacy", "g", [], [], tests)
    tasks = store.tasks()
    del tasks[-1]["created"]
    store._save(tasks)
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out.splitlines()
    warnings = [line for line in out if "warning" in line]
    assert warnings == ["  warning: tests/test_new.py changed after T001 was added",
                        "  warning: tests/test_new.py changed after T002 was added"]
    assert out.index(warnings[0]) == out.index(next(line for line in out if line.startswith("T001"))) + 1
