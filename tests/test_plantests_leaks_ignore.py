"""Tests for task leaks_ignore: suite_leaks ignores the other new drafts of the same run (plan P010 cleanup).

draft_tests writes the drafts of every task of a plan one after another, and every draft is meant to fail until
its task is done. When the suite runs for the second draft, the first draft's failures are not leaks.

suite_leaks(root, path, ignore=()) leaves out every id whose file part (before "::") is path or one of ignore.
draft_tests passes ignore = the test files it has written so far in this run (all tasks, in order), not counting
the one being checked."""
import json
import sys

import pytest

from stratos import config, plantests

COMMAND = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]


def test_ignore(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_command": COMMAND, "test_dir": "tests"})
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_x():\n    assert False\n", encoding="utf-8")
    (tmp_path / "tests" / "test_b.py").write_text("def test_y():\n    assert False\n", encoding="utf-8")
    assert plantests.suite_leaks(tmp_path, "tests/test_b.py") == ["tests/test_a.py::test_x"]
    assert plantests.suite_leaks(tmp_path, "tests/test_b.py", ignore=["tests/test_a.py"]) == []


class FakeTelemetry:
    def record(self, kind, **fields):
        pass


class FakeGateway:
    def __init__(self, answers):
        self.answers = list(answers)
        self.telemetry = FakeTelemetry()

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        return "c", self.answers.pop(0)


def test_draft_tests_passes_the_earlier_drafts(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    monkeypatch.setattr(plantests, "check_draft", lambda root, path: ("collected", ""))
    calls = []
    monkeypatch.setattr(plantests, "suite_leaks", lambda root, path, ignore=(): calls.append((path, list(ignore))) or [])
    root = tmp_path / "repo"
    root.mkdir()
    plans = state / "plans"
    plans.mkdir(parents=True)

    def task(key, tests):
        return {"key": key, "title": "T", "goal": "G", "files": ["stratos/x.py"], "tests": tests, "protected": [],
                "after": [], "role": None}
    tasks = [task("a", ["tests/test_a.py", "tests/test_a2.py"]), task("b", ["tests/test_b.py"])]
    (plans / "P001.json").write_text(json.dumps({"id": "P001", "goal": "G", "tasks": tasks, "status": "draft",
                                                 "hash": "h"}), encoding="utf-8")

    def answer(*paths):
        return "".join(f"FILE: {p}\n```python\ndef test_t():\n    assert False\n```\n" for p in paths)
    gw = FakeGateway([answer("tests/test_a.py", "tests/test_a2.py"), answer("tests/test_b.py")])
    plantests.draft_tests(gw, "P001", root, state, log=lambda s: None)
    assert calls == [("tests/test_a.py", []),
                     ("tests/test_a2.py", ["tests/test_a.py"]),
                     ("tests/test_b.py", ["tests/test_a.py", "tests/test_a2.py"])]
