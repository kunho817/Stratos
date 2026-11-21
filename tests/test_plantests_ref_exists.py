"""Tests for task plantests_ref_exists: in draft_tests, the reference check loop also processes tasks
whose test file already existed on disk (status "exists"), using that path as the test input to
refcheck.check. Processing is in plan order like newly-drafted tasks; refcheck results are recorded
in the results list. Tasks with status "missing" (no file written, none on disk) are still skipped;
"old" tasks (file on disk, not in the answer) are not processed. Uses fakes for the gateway, codemap
builder, check_draft, suite_leaks, and refcheck.check — no network, GPU, or real models."""

import json

import pytest

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


def make_plan(state, tasks):
    (state / "plans").mkdir(parents=True, exist_ok=True)
    (state / "plans" / "P001.json").write_text(
        json.dumps({"id": "P001", "goal": "G", "tasks": tasks, "status": "draft", "hash": "h"}),
        encoding="utf-8")


def task(key, test):
    return {"key": key, "title": key, "goal": "G",
            "files": [f"pkg/{key}.py"], "tests": [test],
            "protected": [], "after": [], "role": None}


def draft(name):
    return f"FILE: tests/{name}\n```python\ndef test_x():\n    assert True\n```\n"


@pytest.fixture
def env(tmp_path, monkeypatch):
    state = tmp_path / "state"
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    monkeypatch.setattr(config, "REF_CHECK", True)
    monkeypatch.setattr(config, "MEMORY", False)
    monkeypatch.setattr(config, "MUTATION", False)
    monkeypatch.setattr(plantests, "check_draft", lambda root, path: ("collected", ""))
    monkeypatch.setattr(plantests, "suite_leaks", lambda root, path, ignore=(): [])
    monkeypatch.setattr(plantests, "draft_problems", lambda root, path: [])
    monkeypatch.setattr(plantests.codemap, "build",
                        lambda r: {"files": {}, "imports": {}, "test_dir": "tests"})
    calls = []

    def fake_check(gw, plan_id, t, root, tests, extra=None):
        calls.append((t["key"], tests, extra))
        return {"status": "agree", "total": 2, "failing": [], "first_error": "",
                "files": [(f"pkg/{t['key']}.py", "X = 1")]}

    monkeypatch.setattr(refcheck, "check", fake_check)
    return state, root, calls


def test_refcheck_called_for_existing_test_file(env):
    """A task whose test file already exists on disk (status "exists") gets refcheck.check
    called with that existing path."""
    state, root, calls = env
    (root / "tests" / "test_a.py").write_text("def test_old():\n    pass\n", encoding="utf-8")
    make_plan(state, [task("a", "tests/test_a.py")])
    gw = FakeGateway([draft("test_a.py")])
    results = plantests.draft_tests(gw, "P001", root, state, log=lambda s: None)
    # Model produced FILE header, file existed on disk → status "exists"
    assert results[0]["status"] == "exists"
    # refcheck.check must be called with the existing path as the test list
    # Expected: one call, key "a", tests ["tests/test_a.py"], extra []
    assert len(calls) == 1
    assert calls[0][0] == "a"
    assert calls[0][1] == ["tests/test_a.py"]
    assert calls[0][2] == []


def test_refcheck_result_in_results_for_exists_task(env):
    """The refcheck result dict is attached to the results entry of the "exists" task."""
    state, root, calls = env
    (root / "tests" / "test_a.py").write_text("def test_old():\n    pass\n", encoding="utf-8")
    make_plan(state, [task("a", "tests/test_a.py")])
    gw = FakeGateway([draft("test_a.py")])
    results = plantests.draft_tests(gw, "P001", root, state, log=lambda s: None)
    assert results[0]["status"] == "exists"
    # refcheck must appear as a key in the results entry
    # Expected: refcheck dict with status "agree", total 2, failing []
    assert "refcheck" in results[0]
    assert results[0]["refcheck"]["status"] == "agree"
    assert results[0]["refcheck"]["total"] == 2
    assert results[0]["refcheck"]["failing"] == []


def test_refcheck_plan_order_with_exists_task(env):
    """In plan order, an "exists" task is processed between newly-drafted tasks.
    Tasks a, b (exists), c — all three get refcheck.check, in order a, b, c."""
    state, root, calls = env
    (root / "tests" / "test_b.py").write_text("def test_old():\n    pass\n", encoding="utf-8")
    tasks = [task("a", "tests/test_a.py"),
             task("b", "tests/test_b.py"),
             task("c", "tests/test_c.py")]
    make_plan(state, tasks)
    gw = FakeGateway([draft("test_a.py"), draft("test_b.py"), draft("test_c.py")])
    results = plantests.draft_tests(gw, "P001", root, state, log=lambda s: None)
    # a: newly written (collected), b: exists, c: newly written (collected)
    assert results[0]["status"] == "collected"
    assert results[1]["status"] == "exists"
    assert results[2]["status"] == "collected"
    # Expected calls in plan order: a, b, c
    assert [c[0] for c in calls] == ["a", "b", "c"]


def test_extra_chain_includes_files_from_exists_task(env):
    """Files returned by refcheck.check for an "exists" task are added to the extra
    list passed to subsequent tasks' refcheck.check."""
    state, root, calls = env
    (root / "tests" / "test_a.py").write_text("def test_old():\n    pass\n", encoding="utf-8")
    make_plan(state, [task("a", "tests/test_a.py"), task("b", "tests/test_b.py")])
    gw = FakeGateway([draft("test_a.py"), draft("test_b.py")])
    results = plantests.draft_tests(gw, "P001", root, state, log=lambda s: None)
    assert len(calls) == 2
    # a (exists) refcheck returns files [(pkg/a.py, X = 1)]
    # Expected: b's extra includes the files from a's refcheck result
    assert len(calls[0][2]) == 0
    assert ("pkg/a.py", "X = 1") in calls[1][2]


def test_log_messages_for_exists_task(env, monkeypatch):
    """The same log lines (flagged, interface, agree) appear for "exists" tasks
    as for newly-drafted tasks."""
    state, root, calls = env
    (root / "tests" / "test_a.py").write_text("def test_old():\n    pass\n", encoding="utf-8")
    make_plan(state, [task("a", "tests/test_a.py")])
    def flagged_check(gw, pid, t, root, tests, extra=None):
        calls.append((t["key"], tests))
        return {"status": "flagged", "total": 3, "failing": ["x", "y"],
                "first_error": "", "files": []}
    monkeypatch.setattr(refcheck, "check", flagged_check)
    lines = []
    gw = FakeGateway([draft("test_a.py")])
    plantests.draft_tests(gw, "P001", root, state, log=lines.append)
    # Expected log line for "flagged":
    # "a: reference implementation fails 2 of 3 tests: x, y"
    assert "a: reference implementation fails 2 of 3 tests: x, y" in lines


def test_telemetry_ref_check_for_exists_task(env):
    """gw.telemetry.record("ref_check", ...) is written for an "exists" task,
    just as it is for newly-drafted tasks."""
    state, root, calls = env
    (root / "tests" / "test_a.py").write_text("def test_old():\n    pass\n", encoding="utf-8")
    make_plan(state, [task("a", "tests/test_a.py")])
    gw = FakeGateway([draft("test_a.py")])
    plantests.draft_tests(gw, "P001", root, state, log=lambda s: None)
    evs = [e for e in gw.telemetry.events if e["kind"] == "ref_check"]
    # Expected: one ref_check event for key "a", status "agree", total 2
    assert len(evs) == 1
    assert evs[0]["key"] == "a"
    assert evs[0]["status"] == "agree"
    assert evs[0]["total"] == 2


def test_old_status_does_not_trigger_refcheck(env):
    """A task whose test file is on disk but NOT in the model's answer gets status
    "old" and is NOT processed by the reference check. Only "exists" is extended."""
    state, root, calls = env
    (root / "tests" / "test_a.py").write_text("def test_old():\n    pass\n", encoding="utf-8")
    make_plan(state, [task("a", "tests/test_a.py")])
    # Model produces an answer that does not write to test_a.py
    # new_tests is empty (file exists), so no header-less fallback fires
    gw = FakeGateway(["just text, no file header"])
    results = plantests.draft_tests(gw, "P001", root, state, log=lambda s: None)
    # Expected: status "old" (on disk, not in answer)
    assert results[0]["status"] == "old"
    # Expected: refcheck.check is NOT called
    assert calls == []
    assert "refcheck" not in results[0]

