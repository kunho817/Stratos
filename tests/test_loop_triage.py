"""Tests for the triage step in write_task (stratos/loop.py), plan P009 task loop_triage.

Right before write_task sets a task to needs_human: when config.TRIAGE is on and the last attempt's result was
"failed", it calls triage.triage(gw, task, wt, code_files, detail) with code_files = patch.parse_files(<last answer
text>, task["files"]) and detail = the last attempt's test output. Then store.update(task_id, triage=result),
gw.telemetry.record("triage", task=task_id, verdict=..., test=..., reason=...) and a log line
"  triage: <verdict> - <reason>". An exception from triage.triage is logged and ignored: the task still becomes
needs_human. Nothing happens when TRIAGE is off or when the last result was not "failed" (e.g. "no_files").
(The planner model's draft replaced stratos.triage in sys.modules and built its own MonkeyPatch; rewritten.)"""
import pytest

from stratos import config, gitops, loop, triage, verify
from stratos.state import Store
from stratos.telemetry import Telemetry

WRITER = "FILE: pkg/a.py\n```python\nX = 1\n```\n"
RESULT = {"verdict": "test_wrong", "test": "tests/x.py::t", "reason": "the expected value is off by one"}


class FakeGateway:
    def __init__(self, telemetry, answers):
        self.telemetry = telemetry
        self.answers = list(answers)
        self.calls = []

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append(kw)
        return f"c{len(self.calls)}", self.answers.pop(0)


@pytest.fixture
def env(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REVIEW", False)
    monkeypatch.setattr(config, "TRIAGE", True)
    rec = {"outs": [], "calls": [], "raise": False}

    def worktree(repo, root, tid, bases=None):
        p = tmp_path / "wt" / tid
        p.mkdir(parents=True, exist_ok=True)
        return p
    monkeypatch.setattr(gitops, "ensure_worktree", worktree)
    monkeypatch.setattr(gitops, "dependency_bases", lambda repo, ids: [])
    monkeypatch.setattr(gitops, "diff", lambda w: "")
    monkeypatch.setattr(gitops, "discard_changes", lambda w: None)
    monkeypatch.setattr(gitops, "commit_all", lambda w, message: "sha1")
    monkeypatch.setattr(verify, "run_tests", lambda w, tests: rec["outs"].pop(0))

    def fake_triage(gw, task, wt, code_files, detail):
        rec["calls"].append((task["id"], wt.name, code_files, detail))
        if rec["raise"]:
            raise RuntimeError("triage model down")
        return dict(RESULT)
    monkeypatch.setattr(triage, "triage", fake_triage)
    store = Store(state)
    store.add_task("t", "make X", ["pkg/a.py"], [], ["tests/x.py"], role="coder")
    return store, Telemetry(state / "telemetry.jsonl"), rec


def run(env, answers, outs):
    store, tel, rec = env
    rec["outs"] = list(outs)
    gw = FakeGateway(tel, answers)
    lines = []
    result = loop.write_task(store, gw, "T001", log=lines.append)
    return result, lines


def failures(n):
    return [(False, f"FAILED tests/x.py::t{i}") for i in range(1, n + 1)]


def test_triage_before_a_person(env):
    store, tel, rec = env
    result, lines = run(env, [WRITER] * 4, failures(4))
    assert result == "needs_human"
    assert rec["calls"] == [("T001", "T001", [("pkg/a.py", "X = 1\n")], "FAILED tests/x.py::t4")]
    task = store.get("T001")
    assert task["status"] == "needs_human" and task["triage"] == RESULT
    (e,) = [e for e in tel.load() if e["kind"] == "triage"]
    assert (e["task"], e["verdict"], e["test"], e["reason"]) == ("T001", "test_wrong", "tests/x.py::t", RESULT["reason"])
    assert "  triage: test_wrong - the expected value is off by one" in lines


def test_a_failing_triage_is_ignored(env):
    store, tel, rec = env
    rec["raise"] = True
    result, lines = run(env, [WRITER] * 4, failures(4))
    assert result == "needs_human" and store.get("T001")["status"] == "needs_human"
    assert "triage" not in store.get("T001")
    assert not [e for e in tel.load() if e["kind"] == "triage"]
    assert any("triage" in line and "triage model down" in line for line in lines)


def test_no_triage_when_off(env, monkeypatch):
    store, tel, rec = env
    monkeypatch.setattr(config, "TRIAGE", False)
    assert run(env, [WRITER] * 4, failures(4))[0] == "needs_human"
    assert rec["calls"] == []


def test_no_triage_when_the_last_result_was_not_failed(env):
    store, tel, rec = env
    answers = [WRITER, WRITER, WRITER, "no files here"]
    assert run(env, answers, failures(3))[0] == "needs_human"
    assert rec["calls"] == []


def test_no_triage_when_the_task_passes(env):
    store, tel, rec = env
    assert run(env, [WRITER, WRITER], [(False, "FAILED tests/x.py::t1"), (True, "1 passed")])[0] == "done"
    assert rec["calls"] == []
