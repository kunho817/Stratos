"""Tests for task plantests_refcheck (P7, 2026-11-20, after refcheck): plan-tests runs the reference check after all
drafts are written (one switch to the reference model for the whole plan), and the model draft checker is off by
default (on fresh drafts it found almost none of the real problems: trials 6-9).

config.REF_CHECK (True by default; tests/conftest.py turns it off); config.DRAFT_CHECK becomes False by default.
draft_tests: when config.REF_CHECK, after the loop over the tasks, for each task with at least one file it has just
written (status not "missing" or "exists"): r = refcheck.check(gw, plan_id, task, root, <those written test paths>);
an exception is logged as f"{key}: reference check failed: {e}" and skipped. Then:
- log: "flagged" -> f"{key}: reference implementation fails {n} of {total} tests: {', '.join(failing)}";
  "interface" -> f"{key}: reference implementation fails {n} of {total} tests - the goal may leave the interface
  open: {first_error}"; "agree" -> f"{key}: reference implementation passes all {total} tests";
  "error" -> f"{key}: reference check: {first_error}";
- gw.telemetry.record("ref_check", plan=plan_id, key=key, status=..., total=..., failing=...);
- every results entry of that task gets "refcheck": r.
`stratos plan-tests` prints, after a task's result lines, f"  reference: {status}" plus f" ({n} of {total} fail)"
when failing is not empty."""
import json
from pathlib import Path

import pytest

from stratos import __main__ as cli
from stratos import config, plantests, refcheck


class FakeTelemetry:
    def __init__(self):
        self.events = []

    def record(self, kind, **fields):
        self.events.append({"kind": kind, **fields})


class FakeGateway:
    def __init__(self, answers):
        self.answers = list(answers)
        self.telemetry = FakeTelemetry()

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        return "c1", self.answers.pop(0)


def plan(state, tasks):
    (state / "plans").mkdir(parents=True)
    (state / "plans" / "P001.json").write_text(json.dumps({"id": "P001", "goal": "G", "tasks": tasks,
                                                           "status": "draft", "hash": "h"}), encoding="utf-8")


def task(key, test):
    return {"key": key, "title": key, "goal": "G", "files": [f"pkg/{key}.py"], "tests": [test], "protected": [],
            "after": [], "role": None}


@pytest.fixture
def env(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    monkeypatch.setattr(config, "REF_CHECK", True)
    monkeypatch.setattr(plantests, "check_draft", lambda root, path: ("collected", ""))
    monkeypatch.setattr(plantests, "suite_leaks", lambda root, path, ignore=(): [])
    root = tmp_path / "repo"
    root.mkdir()
    calls = []
    results = {"a": {"status": "flagged", "total": 3, "failing": ["tests/test_a.py::test_x"], "first_error": ""},
               "b": {"status": "interface", "total": 4, "failing": ["t1", "t2", "t3"], "first_error": "ImportError: x"}}

    def fake_check(gw, plan_id, t, root, tests, extra=None):  # extra: task refcheck_chain (Claude updated the fake)
        calls.append((t["key"], tests))
        return dict(results[t["key"]])
    monkeypatch.setattr(refcheck, "check", fake_check)
    return state, root, calls


def draft(name):
    return f"FILE: tests/{name}\n```python\ndef test_x():\n    assert True\n```\n"


def test_reference_check_after_all_drafts(env):
    state, root, calls = env
    plan(state, [task("a", "tests/test_a.py"), task("b", "tests/test_b.py")])
    gw = FakeGateway([draft("test_a.py"), draft("test_b.py")])
    lines = []
    results = plantests.draft_tests(gw, "P001", root, state, log=lines.append)
    assert calls == [("a", ["tests/test_a.py"]), ("b", ["tests/test_b.py"])]
    assert results[0]["refcheck"]["status"] == "flagged" and results[1]["refcheck"]["status"] == "interface"
    assert "a: reference implementation fails 1 of 3 tests: tests/test_a.py::test_x" in lines
    assert ("b: reference implementation fails 3 of 4 tests - the goal may leave the interface open: "
            "ImportError: x") in lines
    evs = [e for e in gw.telemetry.events if e["kind"] == "ref_check"]
    assert [(e["key"], e["status"], e["total"]) for e in evs] == [("a", "flagged", 3), ("b", "interface", 4)]


def test_no_reference_check_for_unwritten_drafts(env):
    state, root, calls = env
    plan(state, [task("a", "tests/test_a.py")])
    results = plantests.draft_tests(FakeGateway(["```python\nunclosed"]), "P001", root, state, log=lambda s: None)
    assert calls == [] and "refcheck" not in results[0]


def test_off(env, monkeypatch):
    state, root, calls = env
    monkeypatch.setattr(config, "REF_CHECK", False)
    plan(state, [task("a", "tests/test_a.py")])
    plantests.draft_tests(FakeGateway([draft("test_a.py")]), "P001", root, state, log=lambda s: None)
    assert calls == []


def test_draft_check_is_off_by_default():
    import importlib.util
    text = open(importlib.util.find_spec("stratos.config").origin, encoding="utf-8").read()
    assert "DRAFT_CHECK" not in text   # (task cleanup_dead: the draft checker is gone; Claude updated this test)
    assert 'REF_CHECK = os.environ.get("STRATOS_REF_CHECK", "1") != "0"' in text


def test_cli_prints_the_reference_status(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(cli, "refresh_memory", lambda: None)
    monkeypatch.setattr(plantests, "draft_tests", lambda gw, pid, root, state: [
        {"key": "a", "file": "tests/a.py", "status": "collected",
         "refcheck": {"status": "flagged", "total": 3, "failing": ["x"], "first_error": ""}},
        {"key": "b", "file": "tests/b.py", "status": "collected",
         "refcheck": {"status": "agree", "total": 2, "failing": [], "first_error": ""}}])
    assert cli.main(["plan-tests", "P001"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "  reference: flagged (1 of 3 fail)" in out
    assert "  reference: agree" in out
