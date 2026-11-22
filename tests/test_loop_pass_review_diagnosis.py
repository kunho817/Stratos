"""Tests for task loop_pass_review_diagnosis: write_task starts failure=None (not the stored review_feedback)
and passes review= and diagnosis= to build_messages on every attempt.

In stratos/loop.py, write_task:
- failure = None at the start (not task.get("review_feedback")).
- review = task["review_feedback"]: passed to build_messages on every attempt of the call when non-empty.
- diagnosis = triage["reason"] when the stored triage is a dict with verdict "code_wrong" and a non-empty reason:
  passed to build_messages on every attempt when non-empty.
- Only pass review= and diagnosis= keywords when they are non-empty; old fakes of build_messages take
  (task, wt, failure) only, so empty ones must not be passed as keywords.
- After a failed attempt failure becomes the test output as before; review and diagnosis are still passed.
"""
import pytest

from stratos import config, context, gitops, loop, verify
from stratos.state import Store
from stratos.telemetry import Telemetry

WRITER = "FILE: pkg/a.py\n```python\nX = 1\n```\n"

REVIEW_TEXT = "Fix: condition is always true"
DIAG_REASON = "the code calls the wrong function"
CODE_WRONG = {"verdict": "code_wrong", "reason": DIAG_REASON}
TEST_WRONG = {"verdict": "test_wrong", "reason": "off by one"}
EMPTY_REASON = {"verdict": "code_wrong", "reason": ""}


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
    monkeypatch.setattr(config, "PREFLIGHT", False)
    monkeypatch.setattr(loop, "task_memory", lambda task: None)
    rec = {"outs": [], "build_calls": []}

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

    def fake_build(task, wt, failure=None, **kw):
        rec["build_calls"].append((failure, kw))
        return [{"role": "user", "content": "fake"}]
    monkeypatch.setattr(context, "build_messages", fake_build)

    store = Store(state)
    store.add_task("t", "make X", ["pkg/a.py"], [], ["tests/x.py"], role="coder")
    return store, Telemetry(state / "telemetry.jsonl"), rec


def run(env, outs):
    store, tel, rec = env
    rec["outs"] = list(outs)
    gw = FakeGateway(tel, [WRITER] * len(outs))
    result = loop.write_task(store, gw, "T001", log=lambda *a: None)
    return result


def test_failure_starts_as_none(env):
    """failure is None at the start, not task.get("review_feedback").
    Task has review_feedback="Fix X", passes on attempt 1.
    build_messages receives failure=None (not "Fix X") and review="Fix X".
    - first build call: failure is None → failure kw is None.
    - review="Fix X" is in the kwargs.
    """
    store, tel, rec = env
    store.update("T001", review_feedback=REVIEW_TEXT)
    result = run(env, [(True, "ok")])
    assert result == "done"
    failure, kw = rec["build_calls"][0]
    # failure is None, NOT the review feedback
    assert failure is None
    # review is passed as a keyword
    assert kw.get("review") == REVIEW_TEXT


def test_review_on_first_attempt(env):
    """When review_feedback is set, the first attempt's build_messages gets review=task["review_feedback"].
    Task has review_feedback, passes on attempt 1.
    - one build call.
    - kw["review"] == the stored review text.
    """
    store, tel, rec = env
    store.update("T001", review_feedback=REVIEW_TEXT)
    run(env, [(True, "ok")])
    failure, kw = rec["build_calls"][0]
    assert kw["review"] == REVIEW_TEXT


def test_review_on_every_attempt(env):
    """review is passed on every attempt, not just the first.
    Task has review_feedback; attempt 1 fails, attempt 2 passes.
    - two build calls.
    - first: failure=None,  review=REVIEW_TEXT.
    - second: failure="FAILED t1", review=REVIEW_TEXT (still present).
    """
    store, tel, rec = env
    store.update("T001", review_feedback=REVIEW_TEXT)
    run(env, [(False, "FAILED t1"), (True, "ok")])
    assert len(rec["build_calls"]) == 2
    f0, kw0 = rec["build_calls"][0]
    f1, kw1 = rec["build_calls"][1]
    assert f0 is None
    assert kw0.get("review") == REVIEW_TEXT
    # second attempt: failure is the test output, review is still passed
    assert f1 == "FAILED t1"
    assert kw1.get("review") == REVIEW_TEXT


def test_no_review_keyword_when_empty(env):
    """When review_feedback is empty (not set), review is not passed as a keyword.
    No review_feedback; passes on attempt 1.
    - one build call; kw does not contain "review".
    """
    store, tel, rec = env
    run(env, [(True, "ok")])
    failure, kw = rec["build_calls"][0]
    # old fakes: only (task, wt, failure) — no review keyword
    assert "review" not in kw


def test_no_review_keyword_when_none(env):
    """review_feedback=None (explicitly set to None) → no review keyword.
    - one build call; "review" absent from kw.
    """
    store, tel, rec = env
    store.update("T001", review_feedback=None)
    run(env, [(True, "ok")])
    failure, kw = rec["build_calls"][0]
    assert "review" not in kw


def test_diagnosis_on_every_attempt(env):
    """When triage is {"verdict": "code_wrong", "reason": DIAG_REASON}, diagnosis is passed on every attempt.
    attempt 1 fails, attempt 2 passes.
    - two build calls.
    - each kw["diagnosis"] == DIAG_REASON.
    """
    store, tel, rec = env
    store.update("T001", triage=CODE_WRONG)
    run(env, [(False, "FAILED t1"), (True, "ok")])
    assert len(rec["build_calls"]) == 2
    for failure, kw in rec["build_calls"]:
        # every attempt gets the diagnosis
        assert kw.get("diagnosis") == DIAG_REASON


def test_no_diagnosis_for_test_wrong(env):
    """triage verdict "test_wrong" → diagnosis is not passed.
    - one build call; "diagnosis" absent from kw.
    """
    store, tel, rec = env
    store.update("T001", triage=TEST_WRONG)
    run(env, [(True, "ok")])
    failure, kw = rec["build_calls"][0]
    assert "diagnosis" not in kw


def test_no_diagnosis_for_empty_reason(env):
    """triage is {"verdict": "code_wrong", "reason": ""} → no diagnosis.
    - one build call; "diagnosis" absent from kw.
    """
    store, tel, rec = env
    store.update("T001", triage=EMPTY_REASON)
    run(env, [(True, "ok")])
    failure, kw = rec["build_calls"][0]
    # reason is empty → falsy → keyword not passed
    assert "diagnosis" not in kw


def test_no_diagnosis_for_non_dict(env):
    """triage is a string (not a dict) → no diagnosis.
    - one build call; "diagnosis" absent from kw.
    """
    store, tel, rec = env
    store.update("T001", triage="not a dict")
    run(env, [(True, "ok")])
    failure, kw = rec["build_calls"][0]
    # not a dict → no diagnosis keyword
    assert "diagnosis" not in kw


def test_no_diagnosis_when_no_triage(env):
    """No triage field set at all (task.get("triage") is None) → no diagnosis keyword.
    - one build call; "diagnosis" absent from kw.
    """
    store, tel, rec = env
    run(env, [(True, "ok")])
    failure, kw = rec["build_calls"][0]
    # no triage stored → diagnosis not passed
    assert "diagnosis" not in kw


def test_review_and_diagnosis_together(env):
    """Both review_feedback and triage code_wrong: every attempt gets review= and diagnosis=.
    attempt 1 fails, attempt 2 passes → 2 build calls.
    - each call has review=REVIEW_TEXT and diagnosis=DIAG_REASON.
    """
    store, tel, rec = env
    store.update("T001", review_feedback=REVIEW_TEXT, triage=CODE_WRONG)
    run(env, [(False, "FAILED t1"), (True, "ok")])
    assert len(rec["build_calls"]) == 2
    for failure, kw in rec["build_calls"]:
        # both keywords present on every attempt
        assert kw["review"] == REVIEW_TEXT
        assert kw["diagnosis"] == DIAG_REASON


def test_no_keywords_when_neither(env):
    """No review_feedback and no triage: build_messages receives neither keyword.
    One build call; kw has neither "review" nor "diagnosis".
    """
    store, tel, rec = env
    run(env, [(True, "ok")])
    failure, kw = rec["build_calls"][0]
    assert "review" not in kw
    assert "diagnosis" not in kw
