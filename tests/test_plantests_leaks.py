"""Tests for task suite_check: plantests.suite_leaks and the "leaks" draft status (plan P010).

A draft can pass its own collection and still break other tests by leaving global state behind (P009's drafts set
config.STATE_DIR for good). suite_leaks(root, path) runs the whole suite with the draft in it and names the tests
outside the draft that fail:
- only for a .py path (pytest); any other path returns [] without running anything;
- runs config.PROJECT["test_command"] + [config.PROJECT["test_dir"]] with cwd=root, capture_output, text,
  encoding="utf-8", errors="replace", timeout=600;
- reads the failing ids from stdout + stderr with decide._extract_ids and returns, sorted, the ids whose file part
  (before "::") is not the draft's path. The draft's own failures are expected: the task is not done yet;
- a timeout returns [].

draft_tests: after the risky check, a .py draft whose status is still "collected" is checked with suite_leaks; when
it returns ids the status becomes "leaks", the log line is f"{path}: leaks into: {', '.join(ids[:5])}" and the
"test_draft" event gets leaks=ids[:10]. A "risky" draft is not run."""
import json
import subprocess
import sys

import pytest

from stratos import config, plantests

COMMAND = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_command": COMMAND, "test_dir": "tests"})
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_b.py").write_text("import os\n\n\ndef test_clean_env():\n    assert 'LEAK_X' not in os.environ\n",
                                     encoding="utf-8")
    return tmp_path


def test_a_leaking_draft(project):
    (project / "tests" / "test_a.py").write_text(
        "import os\n\n\ndef test_x():\n    os.environ['LEAK_X'] = '1'\n    assert False\n", encoding="utf-8")
    assert plantests.suite_leaks(project, "tests/test_a.py") == ["tests/test_b.py::test_clean_env"]


def test_a_failing_draft_that_leaks_nothing(project):
    (project / "tests" / "test_a.py").write_text("def test_x():\n    assert False\n", encoding="utf-8")
    assert plantests.suite_leaks(project, "tests/test_a.py") == []


def test_not_python(project, monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("must not run")
    monkeypatch.setattr(subprocess, "run", boom)
    assert plantests.suite_leaks(project, "tests/a.test.js") == []


def test_the_command_and_a_timeout(project, monkeypatch):
    seen = {}

    def slow(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        raise subprocess.TimeoutExpired(cmd, 600)
    monkeypatch.setattr(subprocess, "run", slow)
    assert plantests.suite_leaks(project, "tests/test_a.py") == []
    assert seen["cmd"] == COMMAND + ["tests"]
    assert str(seen["kw"]["cwd"]) == str(project) and seen["kw"]["timeout"] == 600


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


@pytest.fixture
def env(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    monkeypatch.setattr(plantests, "check_draft", lambda root, path: ("collected", ""))
    calls = []
    leaks = {"ids": []}

    def fake_leaks(root, path, ignore=()):
        calls.append(path)
        return list(leaks["ids"])
    monkeypatch.setattr(plantests, "suite_leaks", fake_leaks)
    root = tmp_path / "repo"
    root.mkdir()
    plans = state / "plans"
    plans.mkdir(parents=True)
    task = {"key": "a", "title": "T", "goal": "G", "files": ["stratos/x.py"], "tests": ["tests/test_x.py"],
            "protected": [], "after": [], "role": None}
    (plans / "P001.json").write_text(json.dumps({"id": "P001", "goal": "G", "tasks": [task], "status": "draft",
                                                 "hash": "h"}), encoding="utf-8")
    return state, root, calls, leaks


CLEAN = "FILE: tests/test_x.py\n```python\ndef test_a():\n    assert True\n```\n"
RISKY = "FILE: tests/test_x.py\n```python\nimport os\n\n\ndef test_a():\n    os.environ['A'] = '1'\n```\n"


def test_a_draft_that_leaks(env):
    state, root, calls, leaks = env
    leaks["ids"] = [f"tests/test_{i:02d}.py::t" for i in range(12)]
    gw = FakeGateway(CLEAN)
    lines = []
    results = plantests.draft_tests(gw, "P001", root, state, log=lines.append)
    assert results[0]["status"] == "leaks" and calls == ["tests/test_x.py"]
    assert "tests/test_x.py: leaks into: " + ", ".join(leaks["ids"][:5]) in lines
    assert gw.telemetry.events[0]["leaks"] == leaks["ids"][:10]


def test_a_draft_that_does_not_leak(env):
    state, root, calls, leaks = env
    gw = FakeGateway(CLEAN)
    assert plantests.draft_tests(gw, "P001", root, state, log=lambda s: None)[0]["status"] == "collected"
    assert calls == ["tests/test_x.py"] and "leaks" not in gw.telemetry.events[0]


def test_a_risky_draft_is_not_run(env):
    state, root, calls, leaks = env
    gw = FakeGateway(RISKY)
    assert plantests.draft_tests(gw, "P001", root, state, log=lambda s: None)[0]["status"] == "risky"
    assert calls == []
