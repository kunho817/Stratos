"""Tests for task T008: the task loop runs a code review after the tests pass.

After an attempt passes its tests (and config.REVIEW is on), the loop asks the reviewer role (config.ROLES['reviewer'])
about gitops.diff(worktree) using stratos.review. A review with a high or medium issue sends the attempt back:
the writer's outcome is 'review_failed', the changes are discarded, and the next attempt gets the issues in its prompt.
The gateway, git and the test runner are fakes here; no GPU or repository is needed."""
import pytest

from stratos import config, gitops, loop, verify
from stratos.state import Store
from stratos.telemetry import Telemetry

WRITER = "FILE: pkg/a.py\n```python\nX = 1\n```\n"
APPROVE = '```json\n{"verdict": "approve", "issues": []}\n```'
BLOCK = ('```json\n{"verdict": "changes", "issues": [{"severity": "medium", "file": "pkg/a.py", '
         '"problem": "condition is always true"}]}\n```')
LOW = '```json\n{"verdict": "changes", "issues": [{"severity": "low", "file": "pkg/a.py", "problem": "long line"}]}\n```'


class FakeGateway:
    def __init__(self, telemetry, script):
        self.telemetry = telemetry
        self.script = {role: list(answers) for role, answers in script.items()}
        self.loaded = None
        self.calls = []

    def ensure_model(self, model):
        if model == self.loaded:
            return 0.0
        self.loaded = model
        return 1.0

    def chat(self, messages, *, task, role, attempt, model, effort, max_tokens):
        self.calls.append({"role": role, "model": model, "attempt": attempt, "messages": messages})
        cid = f"c{len(self.calls)}"
        self.telemetry.record("call", call_id=cid, task=task, role=role, attempt=attempt, model=model)
        return cid, self.script[role].pop(0)


@pytest.fixture
def env(tmp_path, monkeypatch):
    state, wt = tmp_path / "state", tmp_path / "wt"
    wt.mkdir()
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REVIEW", True)
    rec = {"commits": [], "discards": 0, "tests_ok": True}
    monkeypatch.setattr(gitops, "ensure_worktree", lambda repo, root, tid: wt)
    monkeypatch.setattr(gitops, "diff", lambda w: "diff --git a/pkg/a.py b/pkg/a.py\n+X = 1\n")

    def discard(w):
        rec["discards"] += 1
    monkeypatch.setattr(gitops, "discard_changes", discard)

    def commit(w, message):
        rec["commits"].append(message)
        return "abc1234"
    monkeypatch.setattr(gitops, "commit_all", commit)
    monkeypatch.setattr(verify, "run_tests", lambda w, tests: (rec["tests_ok"], "1 passed" if rec["tests_ok"] else "boom"))
    store = Store(state)
    store.add_task("t", "make X", ["pkg/a.py"], [], ["tests/x.py"])
    tel = Telemetry(state / "telemetry.jsonl")
    return store, tel, rec, state


def run(env, script):
    store, tel, rec, state = env
    gw = FakeGateway(tel, script)
    result = loop.run_task(store, gw, "T001", log=lambda *a: None)
    return result, gw


def outcomes(env):
    return [e for e in env[1].load() if e["kind"] == "outcome"]


def test_approved_review_commits(env):
    result, gw = run(env, {"coder": [WRITER], "reviewer": [APPROVE]})
    store, _, rec, _ = env
    assert result == "done" and store.get("T001")["status"] == "done"
    assert [c["role"] for c in gw.calls] == ["coder", "reviewer"]
    assert gw.calls[1]["model"] == config.ROLES["reviewer"]["model"]
    assert len(rec["commits"]) == 1


def test_blocking_review_sends_the_attempt_back(env):
    result, gw = run(env, {"coder": [WRITER, WRITER], "reviewer": [BLOCK, APPROVE]})
    _, _, rec, _ = env
    assert result == "done"
    assert [c["role"] for c in gw.calls] == ["coder", "reviewer", "coder", "reviewer"]
    second_prompt = gw.calls[2]["messages"][-1]["content"]
    assert "condition is always true" in second_prompt
    assert rec["discards"] == 1 and len(rec["commits"]) == 1
    results = [o["result"] for o in outcomes(env)]
    assert "review_failed" in results and results[-1] in ("passed", "review_approve")


def test_low_issues_do_not_block(env):
    result, gw = run(env, {"coder": [WRITER], "reviewer": [LOW]})
    assert result == "done" and [c["role"] for c in gw.calls] == ["coder", "reviewer"]


def test_unparsed_review_does_not_block(env):
    result, gw = run(env, {"coder": [WRITER], "reviewer": ["I cannot review this."]})
    assert result == "done"


def test_review_can_be_turned_off(env, monkeypatch):
    monkeypatch.setattr(config, "REVIEW", False)
    result, gw = run(env, {"coder": [WRITER]})
    assert result == "done" and [c["role"] for c in gw.calls] == ["coder"]


def test_failed_tests_are_not_reviewed(env):
    env[2]["tests_ok"] = False
    result, gw = run(env, {"coder": [WRITER] * 3, "coder_hard": [WRITER]})
    assert result == "needs_human"
    assert "reviewer" not in [c["role"] for c in gw.calls]


def test_review_answer_and_outcome_are_recorded(env):
    run(env, {"coder": [WRITER], "reviewer": [APPROVE]})
    state = env[3]
    assert (state / "answers" / "T001-a1-review.md").read_text(encoding="utf-8") == APPROVE
    review_outcomes = [o for o in outcomes(env) if o["call_id"] == "c2"]
    assert review_outcomes and review_outcomes[0]["result"] == "review_approve"
