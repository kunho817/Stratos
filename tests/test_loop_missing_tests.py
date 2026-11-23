"""Tests for task loop_missing_tests: missing_test_files check in write_task.

loop.missing_test_files(task, wt) -> sorted list of task's "files" that lie under
config.PROJECT["test_dir"] and do not exist in folder wt; return [] when not every
file in task["files"] lies under test_dir.

write_task: right after the worktree copy, call missing_test_files; if non-empty:
  store.update(task_id, status="needs_human", missing=<list>);
  store.decide(task=task_id, result="missing_test_file", missing=<list>);
  log "  task <id>: the test file(s) it should fix are not in its copy: <files>
    - commit them, or chain the task after the task that adds them";
  skip the model call (no chat, no write). The check goes before the preflight.

A file lies under the test folder when it starts with
config.PROJECT["test_dir"].rstrip("/") + "/".
"""

import json

import pytest

from stratos import config, gitops, loop, preflight, verify
from stratos.state import Store
from stratos.telemetry import Telemetry

ANSWER = "FILE: pkg/a.py\n```python\nX = 1\n```\n"

TEST_FILES = ["tests/test_a.py", "tests/test_b.py"]
MIXED_FILES = ["pkg/a.py", "tests/test_a.py"]


# ---------- missing_test_files unit tests ----------

def test_not_all_under_test_dir(tmp_path, monkeypatch):
    # files = ["pkg/a.py", "tests/test_a.py"]: "pkg/a.py" does not start with "tests/"
    # Expected: [] (not every file lies under test_dir)
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests"})
    task = {"files": ["pkg/a.py", "tests/test_a.py"]}
    wt = tmp_path / "wt"
    wt.mkdir()
    assert loop.missing_test_files(task, wt) == []


def test_all_under_test_dir_all_missing(tmp_path, monkeypatch):
    # files = ["tests/test_a.py", "tests/test_b.py"], wt is empty
    # Expected: ["tests/test_a.py", "tests/test_b.py"]
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests"})
    task = {"files": ["tests/test_a.py", "tests/test_b.py"]}
    wt = tmp_path / "wt"
    wt.mkdir()
    # Expected: both files missing
    result = loop.missing_test_files(task, wt)
    assert result == ["tests/test_a.py", "tests/test_b.py"]


def test_all_under_test_dir_some_missing(tmp_path, monkeypatch):
    # files = ["tests/test_a.py", "tests/test_b.py"], wt has test_a.py only
    # Expected: ["tests/test_b.py"]
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests"})
    task = {"files": ["tests/test_a.py", "tests/test_b.py"]}
    wt = tmp_path / "wt"
    p = wt / "tests" / "test_a.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    # Expected: only test_b.py is missing
    result = loop.missing_test_files(task, wt)
    assert result == ["tests/test_b.py"]


def test_all_under_test_dir_all_exist(tmp_path, monkeypatch):
    # files = ["tests/test_a.py"], wt has test_a.py
    # Expected: []
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests"})
    task = {"files": ["tests/test_a.py"]}
    wt = tmp_path / "wt"
    p = wt / "tests" / "test_a.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    # Expected: []
    assert loop.missing_test_files(task, wt) == []


def test_empty_files_list(tmp_path, monkeypatch):
    # files = []: vacuously "every file lies under test_dir", no files to check
    # Expected: []
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests"})
    task = {"files": []}
    wt = tmp_path / "wt"
    wt.mkdir()
    # Expected: []
    assert loop.missing_test_files(task, wt) == []


def test_single_file_missing(tmp_path, monkeypatch):
    # files = ["tests/x.py"], wt empty
    # Expected: ["tests/x.py"]
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests"})
    task = {"files": ["tests/x.py"]}
    wt = tmp_path / "wt"
    wt.mkdir()
    # Expected: one missing file
    assert loop.missing_test_files(task, wt) == ["tests/x.py"]


def test_single_file_exists(tmp_path, monkeypatch):
    # files = ["tests/x.py"], wt has it
    # Expected: []
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests"})
    task = {"files": ["tests/x.py"]}
    wt = tmp_path / "wt"
    p = wt / "tests" / "x.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    # Expected: []
    assert loop.missing_test_files(task, wt) == []


# ---------- write_task integration tests ----------

class FakeGateway:
    def __init__(self, telemetry, answers):
        self.telemetry = telemetry
        self.answers = list(answers)
        self.calls = []
        self.models = []

    def ensure_model(self, model):
        self.models.append(model)
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        if self.answers:
            return f"c{len(self.calls)}", self.answers.pop(0)
        return f"c{len(self.calls)}", ""


def _setup(tmp_path, monkeypatch, store, wt_files):
    """Point config at tmp_path, create the worktree with given files.
    wt_files: list of relative paths to create inside the worktree."""
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(config, "REVIEW", False)
    monkeypatch.setattr(config, "PREFLIGHT", True)
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests"})
    monkeypatch.setattr(loop, "task_memory", lambda task: None)

    wt_dir = tmp_path / "wt"

    def worktree(repo, root, tid, bases=None):
        p = wt_dir / tid
        p.mkdir(parents=True, exist_ok=True)
        for f in wt_files:
            fp = p / f
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text("x\n", encoding="utf-8")
        return p
    monkeypatch.setattr(gitops, "ensure_worktree", worktree)
    monkeypatch.setattr(gitops, "dependency_bases", lambda repo, ids: [])
    monkeypatch.setattr(gitops, "diff", lambda w: "")
    monkeypatch.setattr(gitops, "discard_changes", lambda w: None)
    monkeypatch.setattr(gitops, "commit_all", lambda w, message: "sha1")
    monkeypatch.setattr(verify, "run_tests", lambda w, tests: (True, "1 passed"))

    # preflight refuses so no model is reached in the "exists" scenario
    def fake_preflight(task, wt, run=None):
        return {"verdict": "refuse", "reason": "preflight stub", "output": ""}
    monkeypatch.setattr(preflight, "check", fake_preflight)

    return state


def test_write_task_stops_when_missing(tmp_path, monkeypatch):
    # task files = ["tests/test_a.py"], worktree is empty → missing
    # Expected: write_task returns "needs_human"
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(config, "REVIEW", False)
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests"})
    monkeypatch.setattr(loop, "task_memory", lambda task: None)

    wt_dir = tmp_path / "wt"

    def worktree(repo, root, tid, bases=None):
        p = wt_dir / tid
        p.mkdir(parents=True, exist_ok=True)
        return p
    monkeypatch.setattr(gitops, "ensure_worktree", worktree)
    monkeypatch.setattr(gitops, "dependency_bases", lambda repo, ids: [])

    store = Store(state)
    store.add_task("fix test", "Fix the test", ["tests/test_a.py"],
                   ["tests/test_a.py"], ["tests/test_a.py"], role="coder")
    tel = Telemetry(state / "telemetry.jsonl")
    gw = FakeGateway(tel, [ANSWER])
    lines = []
    result = loop.write_task(store, gw, "T001", log=lines.append)
    # Expected: needs_human
    assert result == "needs_human"
    # Expected: task status is needs_human
    assert store.get("T001")["status"] == "needs_human"


def test_write_task_missing_field(tmp_path, monkeypatch):
    # task files = ["tests/test_a.py", "tests/test_b.py"], worktree empty
    # Expected: store task has "missing": ["tests/test_a.py", "tests/test_b.py"]
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(config, "REVIEW", False)
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests"})
    monkeypatch.setattr(loop, "task_memory", lambda task: None)

    wt_dir = tmp_path / "wt"

    def worktree(repo, root, tid, bases=None):
        p = wt_dir / tid
        p.mkdir(parents=True, exist_ok=True)
        return p
    monkeypatch.setattr(gitops, "ensure_worktree", worktree)
    monkeypatch.setattr(gitops, "dependency_bases", lambda repo, ids: [])

    store = Store(state)
    store.add_task("fix test", "Fix", ["tests/test_a.py", "tests/test_b.py"],
                   ["tests/test_a.py", "tests/test_b.py"],
                   ["tests/test_a.py", "tests/test_b.py"], role="coder")
    tel = Telemetry(state / "telemetry.jsonl")
    gw = FakeGateway(tel, [ANSWER])
    loop.write_task(store, gw, "T001", log=lambda *a: None)
    # Expected: missing = ["tests/test_a.py", "tests/test_b.py"]
    t = store.get("T001")
    assert t["missing"] == ["tests/test_a.py", "tests/test_b.py"]


def test_write_task_decision_recorded(tmp_path, monkeypatch):
    # Expected: store.decide records result "missing_test_file" with the missing list
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(config, "REVIEW", False)
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests"})
    monkeypatch.setattr(loop, "task_memory", lambda task: None)

    wt_dir = tmp_path / "wt"

    def worktree(repo, root, tid, bases=None):
        p = wt_dir / tid
        p.mkdir(parents=True, exist_ok=True)
        return p
    monkeypatch.setattr(gitops, "ensure_worktree", worktree)
    monkeypatch.setattr(gitops, "dependency_bases", lambda repo, ids: [])

    store = Store(state)
    store.add_task("fix", "g", ["tests/test_a.py"],
                   ["tests/test_a.py"], ["tests/test_a.py"], role="coder")
    tel = Telemetry(state / "telemetry.jsonl")
    gw = FakeGateway(tel, [ANSWER])
    loop.write_task(store, gw, "T001", log=lambda *a: None)
    # Expected: decisions.jsonl has result "missing_test_file"
    lines = (state / "decisions.jsonl").read_text(encoding="utf-8").strip().split("\n")
    recs = [json.loads(l) for l in lines]
    results = [r["result"] for r in recs]
    assert "missing_test_file" in results
    # Expected: the decision carries the missing list
    decision = [r for r in recs if r["result"] == "missing_test_file"][0]
    assert decision["missing"] == ["tests/test_a.py"]


def test_write_task_log_message(tmp_path, monkeypatch):
    # Expected: log "  task T001: the test file(s) it should fix are not in its copy:
    #   tests/test_a.py, tests/test_b.py - commit them, or chain the task after the task that adds them"
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(config, "REVIEW", False)
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests"})
    monkeypatch.setattr(loop, "task_memory", lambda task: None)

    wt_dir = tmp_path / "wt"

    def worktree(repo, root, tid, bases=None):
        p = wt_dir / tid
        p.mkdir(parents=True, exist_ok=True)
        return p
    monkeypatch.setattr(gitops, "ensure_worktree", worktree)
    monkeypatch.setattr(gitops, "dependency_bases", lambda repo, ids: [])

    store = Store(state)
    store.add_task("fix", "g", ["tests/test_a.py", "tests/test_b.py"],
                   ["tests/test_a.py", "tests/test_b.py"],
                   ["tests/test_a.py", "tests/test_b.py"], role="coder")
    tel = Telemetry(state / "telemetry.jsonl")
    gw = FakeGateway(tel, [ANSWER])
    lines = []
    loop.write_task(store, gw, "T001", log=lines.append)
    # Expected: joined missing files in the log
    # ", ".join(["tests/test_a.py", "tests/test_b.py"]) = "tests/test_a.py, tests/test_b.py"
    want = ("  task T001: the test file(s) it should fix are not in its copy: "
            "tests/test_a.py, tests/test_b.py - commit them, "
            "or chain the task after the task that adds them")
    # Expected: the full log message is present
    assert want in lines


def test_write_task_no_model_call(tmp_path, monkeypatch):
    # Expected: gw.chat never called, gw.ensure_model never called
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(config, "REVIEW", False)
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests"})
    monkeypatch.setattr(loop, "task_memory", lambda task: None)

    wt_dir = tmp_path / "wt"

    def worktree(repo, root, tid, bases=None):
        p = wt_dir / tid
        p.mkdir(parents=True, exist_ok=True)
        return p
    monkeypatch.setattr(gitops, "ensure_worktree", worktree)
    monkeypatch.setattr(gitops, "dependency_bases", lambda repo, ids: [])

    store = Store(state)
    store.add_task("fix", "g", ["tests/test_a.py"],
                   ["tests/test_a.py"], ["tests/test_a.py"], role="coder")
    tel = Telemetry(state / "telemetry.jsonl")
    gw = FakeGateway(tel, [ANSWER])
    loop.write_task(store, gw, "T001", log=lambda *a: None)
    # Expected: no chat calls, no model loads
    assert gw.calls == []
    assert gw.models == []


def test_write_task_continues_when_files_exist(tmp_path, monkeypatch):
    # Worktree HAS the test file; preflight refuses → task is stopped by preflight,
    # NOT by missing_test_file.
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(config, "REVIEW", False)
    monkeypatch.setattr(config, "PREFLIGHT", True)
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests"})
    monkeypatch.setattr(loop, "task_memory", lambda task: None)

    wt_dir = tmp_path / "wt"

    def worktree(repo, root, tid, bases=None):
        p = wt_dir / tid
        p.mkdir(parents=True, exist_ok=True)
        fp = p / "tests" / "test_a.py"
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text("x\n", encoding="utf-8")
        return p
    monkeypatch.setattr(gitops, "ensure_worktree", worktree)
    monkeypatch.setattr(gitops, "dependency_bases", lambda repo, ids: [])
    monkeypatch.setattr(gitops, "diff", lambda w: "")
    monkeypatch.setattr(gitops, "discard_changes", lambda w: None)

    def fake_preflight(task, wt, run=None):
        return {"verdict": "refuse", "reason": "stub preflight", "output": ""}
    monkeypatch.setattr(preflight, "check", fake_preflight)

    store = Store(state)
    store.add_task("fix", "g", ["tests/test_a.py"],
                   ["tests/test_a.py"], ["tests/test_a.py"], role="coder")
    tel = Telemetry(state / "telemetry.jsonl")
    gw = FakeGateway(tel, [ANSWER])
    result = loop.write_task(store, gw, "T001", log=lambda *a: None)
    # Expected: task is stopped by preflight (needs_human), NOT by missing_test_file
    # The decisions.jsonl should NOT contain "missing_test_file"
    lines = (state / "decisions.jsonl").read_text(encoding="utf-8").strip().split("\n")
    recs = [json.loads(l) for l in lines]
    results = [r["result"] for r in recs]
    # Expected: "missing_test_file" is NOT in the decisions
    assert "missing_test_file" not in results
    # Expected: preflight_refused IS in the decisions
    assert "preflight_refused" in results


def test_write_task_mixed_files_continues(tmp_path, monkeypatch):
    # task files = ["pkg/a.py", "tests/test_a.py"]: not all under test_dir → []
    # preflight refuses → task is not stopped by missing_test_file
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(config, "REVIEW", False)
    monkeypatch.setattr(config, "PREFLIGHT", True)
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests"})
    monkeypatch.setattr(loop, "task_memory", lambda task: None)

    wt_dir = tmp_path / "wt"

    def worktree(repo, root, tid, bases=None):
        p = wt_dir / tid
        p.mkdir(parents=True, exist_ok=True)
        return p
    monkeypatch.setattr(gitops, "ensure_worktree", worktree)
    monkeypatch.setattr(gitops, "dependency_bases", lambda repo, ids: [])
    monkeypatch.setattr(gitops, "diff", lambda w: "")
    monkeypatch.setattr(gitops, "discard_changes", lambda w: None)

    def fake_preflight(task, wt, run=None):
        return {"verdict": "refuse", "reason": "stub", "output": ""}
    monkeypatch.setattr(preflight, "check", fake_preflight)

    store = Store(state)
    store.add_task("fix", "g", ["pkg/a.py", "tests/test_a.py"],
                   ["tests/test_a.py"], ["tests/test_a.py"], role="coder")
    tel = Telemetry(state / "telemetry.jsonl")
    gw = FakeGateway(tel, [ANSWER])
    result = loop.write_task(store, gw, "T001", log=lambda *a: None)
    # Expected: not all files under test_dir → missing_test_files returns []
    # The task is NOT stopped with missing_test_file
    lines = (state / "decisions.jsonl").read_text(encoding="utf-8").strip().split("\n")
    recs = [json.loads(l) for l in lines]
    results = [r["result"] for r in recs]
    # Expected: no missing_test_file decision
    assert "missing_test_file" not in results
    # Expected: preflight_refused is present
    assert "preflight_refused" in results
