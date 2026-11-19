"""Tests for task plantests_draftcheck (P2, 2026-11-20, after draftcheck): plan-tests runs the draft checker on every
draft it writes, and the test writer is told not to invent the data of another task.

1. config.DRAFT_CHECK (True by default; tests/conftest.py turns it off). When on, draft_tests calls
   draftcheck.check(gw, plan_id, plan, task, root, path) for each test file it has just written (status not
   "missing" or "exists"), right after that file's own checks. Then:
   - each flag is logged as f'{path}: checker flags "{test}": {reason}';
   - gw.telemetry.record("draft_check", plan=plan_id, key=key, file=path, flags=[the flagged test names]);
   - that file's results entry gets "flags": the list of flag dicts (also when it is empty).
   An exception from the check is logged as f"{path}: draft check failed: {error}" and the entry gets "flags": [];
   no draft_check event then. With DRAFT_CHECK off nothing of this happens (no "flags" key, no event).
2. `stratos plan-tests` prints f"{key} {file}: {status}" as before, plus f", {n} flagged" when the entry has n > 0
   flags, and then one line per flag: f'  - "{test}": {reason}'.
3. plantests.TEST_SYSTEM (system_prompt) also says: when the code under test reads data that another task writes
   (levels, settings, tables), do not assume its contents: build your own small inputs or take cases from the data at
   run time. It contains the words "do not assume its contents". (Lumen and Orbit: the drafts invented level data and
   other drafts depended on it.)"""
import json
from pathlib import Path

import pytest

from stratos import __main__ as cli
from stratos import config, draftcheck, plantests


class FakeTelemetry:
    def __init__(self):
        self.events = []

    def record(self, kind, **fields):
        self.events.append({"kind": kind, **fields})


class FakeGateway:
    def __init__(self, answer):
        self.answer = answer
        self.telemetry = FakeTelemetry()

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        return "c1", self.answer


DRAFT = "FILE: tests/test_x.py\n```python\ndef test_a():\n    assert 1 + 1 == 3\n```\n"


@pytest.fixture
def env(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    monkeypatch.setattr(config, "DRAFT_CHECK", True)
    monkeypatch.setattr(plantests, "check_draft", lambda root, path: ("collected", ""))
    monkeypatch.setattr(plantests, "suite_leaks", lambda root, path, ignore=(): [])
    root = tmp_path / "repo"
    root.mkdir()
    plans = state / "plans"
    plans.mkdir(parents=True)
    task = {"key": "a", "title": "T", "goal": "G", "files": ["stratos/x.py"], "tests": ["tests/test_x.py"],
            "protected": [], "after": [], "role": None}
    (plans / "P001.json").write_text(json.dumps({"id": "P001", "goal": "G", "tasks": [task], "status": "draft",
                                                 "hash": "h"}), encoding="utf-8")
    calls = []

    def fake_check(gw, plan_id, plan, task, root, path):
        calls.append((plan_id, plan["id"], task["key"], path, Path(root, path).exists()))
        return [{"test": "test_a", "reason": "1 + 1 is 2"}]
    monkeypatch.setattr(draftcheck, "check", fake_check)
    return state, root, calls


def test_flags_are_logged_recorded_and_returned(env):
    state, root, calls = env
    gw = FakeGateway(DRAFT)
    lines = []
    results = plantests.draft_tests(gw, "P001", root, state, log=lines.append)
    assert calls == [("P001", "P001", "a", "tests/test_x.py", True)]
    assert results == [{"key": "a", "file": "tests/test_x.py", "status": "collected",
                        "flags": [{"test": "test_a", "reason": "1 + 1 is 2"}]}]
    assert 'tests/test_x.py: checker flags "test_a": 1 + 1 is 2' in lines
    checks = [e for e in gw.telemetry.events if e["kind"] == "draft_check"]
    assert checks == [{"kind": "draft_check", "plan": "P001", "key": "a", "file": "tests/test_x.py",
                       "flags": ["test_a"]}]


def test_a_failing_check_is_logged(env, monkeypatch):
    state, root, calls = env

    def boom(*args):
        raise RuntimeError("model down")
    monkeypatch.setattr(draftcheck, "check", boom)
    gw = FakeGateway(DRAFT)
    lines = []
    results = plantests.draft_tests(gw, "P001", root, state, log=lines.append)
    assert results[0]["flags"] == []
    assert "tests/test_x.py: draft check failed: model down" in lines
    assert not [e for e in gw.telemetry.events if e["kind"] == "draft_check"]


def test_off(env, monkeypatch):
    state, root, calls = env
    monkeypatch.setattr(config, "DRAFT_CHECK", False)
    results = plantests.draft_tests(FakeGateway(DRAFT), "P001", root, state, log=lambda s: None)
    assert calls == [] and "flags" not in results[0]


def test_no_check_for_a_missing_draft(env):
    state, root, calls = env
    # an unclosed fence is the one answer the header-less fallbacks do not turn into a file (a plain text answer
    # becomes the draft itself; Claude's first version of this test used one and was wrong)
    results = plantests.draft_tests(FakeGateway("```python\nunclosed"), "P001", root, state, log=lambda s: None)
    assert results[0]["status"] == "missing" and calls == [] and "flags" not in results[0]


def test_cli_prints_flags(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(cli, "refresh_memory", lambda: None, raising=False)
    monkeypatch.setattr(plantests, "draft_tests", lambda gw, pid, root, state: [
        {"key": "a", "file": "tests/a.test.js", "status": "collected",
         "flags": [{"test": "adds", "reason": "2 + 2 is 4"}]},
        {"key": "b", "file": "tests/b.test.js", "status": "collected", "flags": []},
        {"key": "c", "file": "tests/c.test.js", "status": "missing"}])
    assert cli.main(["plan-tests", "P001"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "a tests/a.test.js: collected, 1 flagged" in out
    assert '  - "adds": 2 + 2 is 4' in out
    assert "b tests/b.test.js: collected" in out
    assert "c tests/c.test.js: missing" in out


def test_system_prompt_says_not_to_invent_data():
    assert "do not assume its contents" in plantests.system_prompt("JavaScript", "node --test")
    assert "do not assume its contents" in plantests.system_prompt("Python", "pytest")
