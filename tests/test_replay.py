"""Tests for task T049: stratos/replay.py, which replays past tasks with a chosen model on a copy of the repository
as it was before the task, and judges each answer exactly like the task loop (loop.check_answer). It is for trying a
model (for example a new one) on tasks with a known outcome; nothing is committed or merged.

base_commit(repo, task_id) -> str | None
    The commit a task started from: among the commits on main (git log main, oldest first) find the first whose subject
    starts with f"{task_id}:" and return the full sha of its first parent. None when there is no such commit.

replay(tasks, gw, *, model, effort, max_tokens, tries, repo, root, log=print) -> list of dicts
    For each task dict, in order:
    - base = base_commit(repo, task["id"]); None -> {"task": id, "result": "no_base", "attempts": 0, "seconds": 0.0}
      and no model call.
    - otherwise a detached worktree root/f"replay-{id}" at base (git worktree add --detach; an old folder of that name
      is removed first), then up to `tries` attempts: gw.ensure_model(model);
      gw.chat(context.build_messages(task, wt, failure), task=id, role="replay", attempt=n, model=model, effort=effort,
      max_tokens=max_tokens); result, detail = loop.check_answer(task, wt, text, getattr(gw, "last_finish", None));
      gw.telemetry.record("outcome", call_id=..., task=id, result=result, detail=detail[-500:]); one log line per
      attempt. The first attempt has failure None, a later one the previous detail[-3000:]. "passed" stops; any other
      result discards the attempt's changes (gitops.discard_changes) before the next one.
    - the dict {"task": id, "result": "passed" or the last result, "attempts": attempts made, "seconds": the summed
      time of the chat calls}; the worktree is removed afterwards (also when an exception is raised).
"""
import subprocess

import pytest

from stratos import context, gitops, loop, replay
from stratos.telemetry import Telemetry


def commit(repo, msg):
    gitops.git(repo, "add", "-A")
    gitops.git(repo, *gitops.BOT, "commit", "-q", "-m", msg)
    return gitops.git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    (r / "a.py").write_text("A = 1\n", encoding="utf-8")
    commit(r, "init")
    (r / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")
    base = commit(r, "Add tests for T901: a")
    (r / "a.py").write_text("A = 2\n", encoding="utf-8")
    commit(r, "T901: change a")
    (r / "a.py").write_text("A = 3\n", encoding="utf-8")
    commit(r, "T901: change a again")
    return r, base


class FakeGateway:
    def __init__(self, telemetry, answers):
        self.telemetry = telemetry
        self.answers = list(answers)
        self.models, self.calls = [], []
        self.last_finish = "stop"

    def ensure_model(self, model):
        self.models.append(model)
        return 0.0

    def chat(self, messages, *, task, role, attempt, model, effort, max_tokens, reasoning_budget=None):
        self.calls.append({"task": task, "role": role, "attempt": attempt, "model": model, "effort": effort,
                           "max_tokens": max_tokens, "messages": messages})
        return f"c{len(self.calls)}", self.answers.pop(0)


TASK = {"id": "T901", "title": "a", "files": ["a.py"], "protected": [], "tests": ["test_a.py"], "goal": "Change A."}


def test_base_commit(repo):
    r, base = repo
    assert replay.base_commit(r, "T901") == base
    assert replay.base_commit(r, "T999") is None
    assert replay.base_commit(r, "T90") is None


def test_replay_passes_on_a_later_try(repo, tmp_path, monkeypatch):
    r, base = repo
    seen = []

    def build(task, wt, failure=None):
        seen.append(failure)
        return [{"role": "user", "content": "x"}]

    def check(task, wt, text, finish=None):
        seen.append((wt.name, (wt / "a.py").read_text(encoding="utf-8"), (wt / "junk.py").exists(), finish))
        (wt / "junk.py").write_text("x", encoding="utf-8")
        return ("failed", "FAILED test_a.py::test_a") if text == "first" else ("passed", "ok")
    monkeypatch.setattr(context, "build_messages", build)
    monkeypatch.setattr(loop, "check_answer", check)
    gw = FakeGateway(Telemetry(tmp_path / "t.jsonl"), ["first", "second"])
    lines = []
    out = replay.replay([TASK], gw, model="m1", effort="low", max_tokens=99, tries=3, repo=r, root=tmp_path / "wt",
                        log=lines.append)
    assert len(out) == 1 and out[0]["task"] == "T901" and out[0]["result"] == "passed" and out[0]["attempts"] == 2
    assert isinstance(out[0]["seconds"], float)
    assert seen == [None, ("replay-T901", "A = 1\n", False, "stop"),
                    "FAILED test_a.py::test_a", ("replay-T901", "A = 1\n", False, "stop")]
    assert [c["attempt"] for c in gw.calls] == [1, 2] and gw.models == ["m1", "m1"]
    c = gw.calls[0]
    assert (c["task"], c["role"], c["model"], c["effort"], c["max_tokens"]) == ("T901", "replay", "m1", "low", 99)
    outcomes = [e for e in gw.telemetry.load() if e["kind"] == "outcome"]
    assert [(e["call_id"], e["task"], e["result"]) for e in outcomes] == [("c1", "T901", "failed"), ("c2", "T901", "passed")]
    assert len(lines) >= 2
    assert not (tmp_path / "wt" / "replay-T901").exists()
    assert len(gitops.git(r, "worktree", "list").splitlines()) == 1


def test_replay_fails_after_the_tries_and_skips_unknown(repo, tmp_path, monkeypatch):
    r, base = repo
    monkeypatch.setattr(context, "build_messages", lambda task, wt, failure=None: [])
    monkeypatch.setattr(loop, "check_answer", lambda task, wt, text, finish=None: ("no_files", "none"))
    gw = FakeGateway(Telemetry(tmp_path / "t.jsonl"), ["a", "b"])
    other = dict(TASK, id="T999")
    out = replay.replay([other, TASK], gw, model="m", effort="none", max_tokens=1, tries=2, repo=r,
                        root=tmp_path / "wt", log=lambda s: None)
    assert out[0] == {"task": "T999", "result": "no_base", "attempts": 0, "seconds": 0.0}
    assert out[1]["result"] == "no_files" and out[1]["attempts"] == 2
    assert [c["task"] for c in gw.calls] == ["T901", "T901"]


def test_worktree_removed_on_error(repo, tmp_path, monkeypatch):
    r, base = repo
    monkeypatch.setattr(context, "build_messages", lambda task, wt, failure=None: [])

    def boom(task, wt, text, finish=None):
        raise RuntimeError("boom")
    monkeypatch.setattr(loop, "check_answer", boom)
    gw = FakeGateway(Telemetry(tmp_path / "t.jsonl"), ["a"])
    with pytest.raises(RuntimeError):
        replay.replay([TASK], gw, model="m", effort="none", max_tokens=1, tries=1, repo=r, root=tmp_path / "wt",
                      log=lambda s: None)
    assert not (tmp_path / "wt" / "replay-T901").exists()
