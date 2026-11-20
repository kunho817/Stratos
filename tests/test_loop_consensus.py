"""Tests for task consensus (P5, 2026-11-20, BACKLOG item 17): two models that wrote their own code and fail the same
test are evidence against the test. History of 5 projects: of 25 tasks where two models failed a shared test, 15
were later reset by a person as "test wrong" (60%); of 12 where they failed different tests, 3 (25%); 15 of all 20
test-wrong resets had the signal.

loop.write_task: for every attempt whose result is "failed", collect decide._extract_ids(detail) per model (union over
that model's failed attempts). Right before the task goes to a person (after the attempts, before triage), when at
least two models have failed attempts, consensus = the sorted ids that every such model failed. When it is not
empty: store.update(task_id, consensus=consensus); gw.telemetry.record("consensus", task=task_id, tests=consensus,
models=<the sorted model names>); log f"  consensus: {', '.join(models)} all failed {', '.join(consensus)}";
and triage.triage gets consensus=consensus as a keyword (only then: old fakes take no such argument).

triage.build_messages(task, root, code_files, test_output, consensus=None): with consensus, right before the
"Test output:" line, the lines "Independent attempts: different models wrote their own code for this task and all
failed these same tests:" then one "- <id>" line per id and the line "Code from different models that agrees against
a test is a sign the test may be wrong; check those tests first." and an empty line. triage.triage(gw, task, root,
code_files, test_output, consensus=None) passes it on."""
import pytest

from stratos import config, gitops, loop, triage, verify
from stratos.state import Store
from stratos.telemetry import Telemetry

ANSWER = "FILE: pkg/a.py\n```python\nX = 1\n```\n"


class FakeGateway:
    def __init__(self, telemetry, answers):
        self.telemetry = telemetry
        self.answers = list(answers)

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        return "c", self.answers.pop(0)


@pytest.fixture
def env(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REVIEW", False)
    monkeypatch.setattr(config, "TRIAGE", True)
    monkeypatch.setattr(config, "ATTEMPT_PLANS", {"coder": [("coder", 2), ("coder_hard", 2)],
                                                  "coder_hard": [("coder_hard", 2), ("coder", 1)]})
    rec = {"outs": [], "triage": []}

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

    def fake_triage(gw, task, wt, code_files, detail, **kw):
        rec["triage"].append(kw)
        return {"verdict": "test_wrong", "test": "tests/x.py", "reason": "r"}
    monkeypatch.setattr(triage, "triage", fake_triage)
    store = Store(state)
    store.add_task("t", "make X", ["pkg/a.py"], [], ["tests/x.py"], role="coder")
    return store, Telemetry(state / "telemetry.jsonl"), rec


def run(env, outs):
    store, tel, rec = env
    rec["outs"] = list(outs)
    lines = []
    result = loop.write_task(store, FakeGateway(tel, [ANSWER] * len(outs)), "T001", log=lines.append)
    return result, lines


def test_two_models_failing_the_same_test(env):
    store, tel, rec = env
    outs = [(False, "FAILED tests/x.py::test_a - assert 1 == 2\nFAILED tests/x.py::test_b - x"),
            (False, "FAILED tests/x.py::test_a - assert 1 == 2"),
            (False, "FAILED tests/x.py::test_a - assert 3 == 2\nFAILED tests/x.py::test_c - y"),
            (False, "FAILED tests/x.py::test_c - y")]
    result, lines = run(env, outs)
    assert result == "needs_human"
    models = sorted([config.ROLES["coder"]["model"], config.ROLES["coder_hard"]["model"]])
    want = ["tests/x.py::test_a"]
    assert store.get("T001")["consensus"] == want
    (e,) = [e for e in tel.load() if e["kind"] == "consensus"]
    assert e["task"] == "T001" and e["tests"] == want and e["models"] == models
    assert f"  consensus: {', '.join(models)} all failed tests/x.py::test_a" in lines
    assert rec["triage"] == [{"consensus": want}]


def test_no_consensus_without_a_shared_test(env):
    store, tel, rec = env
    outs = [(False, "FAILED tests/x.py::test_a - a"), (False, "FAILED tests/x.py::test_a - a"),
            (False, "FAILED tests/x.py::test_b - b"), (False, "FAILED tests/x.py::test_b - b")]
    run(env, outs)
    assert "consensus" not in store.get("T001")
    assert not [e for e in tel.load() if e["kind"] == "consensus"]
    assert rec["triage"] == [{}]


def test_triage_messages_with_consensus(tmp_path):
    task = {"id": "T1", "goal": "g", "tests": []}
    user = triage.build_messages(task, tmp_path, [], "OUT", consensus=["tests/x.py::test_a", "t2"])[1]["content"]
    block = ("Independent attempts: different models wrote their own code for this task and all failed these same "
             "tests:\n- tests/x.py::test_a\n- t2\nCode from different models that agrees against a test is a sign the "
             "test may be wrong; check those tests first.\n\nTest output:\nOUT")
    assert block in user
    assert "Independent attempts" not in triage.build_messages(task, tmp_path, [], "OUT")[1]["content"]
