"""Tests for task loop_no_change: in write_task, after tests pass, check gitops.diff(wt) before the commit.
If the diff is empty (the tests already passed on the base, no files changed), skip the commit: set the store task's
"note" field to "no change: the tests already passed", record the outcome result as "no_change", record the decision
result as "no_change", and return "done" — even when config.REVIEW is on (the review step is skipped).
When the diff is non-empty, the normal commit/review flow continues unchanged.
Fakes stand in for the gateway, git and the test runner; no GPU, repository, or network is needed."""

import json

import pytest

from stratos import config, gitops, loop, verify
from stratos.state import Store
from stratos.telemetry import Telemetry

WRITER = "FILE: pkg/a.py\n```python\nX = 1\n```\n"
APPROVE = '```json\n{"verdict": "approve", "issues": []}\n```'
REVIEWER_MODEL = "reviewer-model"


class FakeGateway:
    def __init__(self, telemetry, script):
        self.telemetry = telemetry
        self.script = {role: list(answers) for role, answers in script.items()}
        self.loaded = None
        self.switches = []
        self.calls = []

    def ensure_model(self, model):
        if model == self.loaded:
            return 0.0
        self.loaded = model
        self.switches.append(model)
        return 1.0

    def chat(self, messages, *, task, role, attempt, model, effort, max_tokens, reasoning_budget=None):
        self.calls.append({"role": role, "model": model, "attempt": attempt, "task": task, "messages": messages})
        cid = f"c{len(self.calls)}"
        self.telemetry.record("call", call_id=cid, task=task, role=role, attempt=attempt, model=model)
        return cid, self.script[role].pop(0)


@pytest.fixture
def env(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REVIEW", True)
    monkeypatch.setattr(config, "REVIEW_ROUNDS", 3)
    monkeypatch.setattr(config, "ROLES", {**config.ROLES, "reviewer": {**config.ROLES["reviewer"], "model": REVIEWER_MODEL}})

    rec = {"commits": [], "diff_out": "", "outs": [], "tests_ok": True}

    def worktree(repo, root, tid, bases=None):
        p = tmp_path / "wt" / tid
        p.mkdir(parents=True, exist_ok=True)
        return p

    monkeypatch.setattr(gitops, "ensure_worktree", worktree)
    monkeypatch.setattr(gitops, "dependency_bases", lambda repo, ids: [])

    def fake_diff(w):
        return rec["diff_out"]

    monkeypatch.setattr(gitops, "diff", fake_diff)
    monkeypatch.setattr(gitops, "commit_diff", lambda w: "diff --git a/pkg/a.py b/pkg/a.py\n+X = 1\n")

    def commit(w, message):
        rec["commits"].append(message)
        return f"sha{len(rec['commits'])}"

    monkeypatch.setattr(gitops, "commit_all", commit)
    monkeypatch.setattr(gitops, "discard_changes", lambda w: None)
    monkeypatch.setattr(gitops, "undo_last_commit", lambda w: None)
    monkeypatch.setattr(gitops, "finalize_commit_message", lambda w, text: rec["commits"].append("finalized:" + text))

    def run_tests(w, tests):
        out = rec["outs"].pop(0) if rec["outs"] else ("1 passed" if rec["tests_ok"] else "boom")
        return rec["tests_ok"], out

    monkeypatch.setattr(verify, "run_tests", run_tests)

    store = Store(state)
    store.add_task("t", "make X", ["pkg/a.py"], [], ["tests/x.py"])
    tel = Telemetry(state / "telemetry.jsonl")
    return store, tel, rec, state


def gateway(env, script):
    return FakeGateway(env[1], script)


def outcomes(env):
    return [e for e in env[1].load() if e["kind"] == "outcome"]


def decisions(env):
    return [e for e in env[1].load() if e["kind"] == "decision"]


def quiet(*a):
    pass


# ---- diff empty: the no-change path ----

def test_no_change_returns_done(env):
    """Tests pass, diff is empty → write_task returns "done" (not "candidate")."""
    store, _, rec, _ = env
    rec["diff_out"] = ""
    gw = gateway(env, {"coder": [WRITER]})
    result = loop.write_task(store, gw, "T001", log=quiet)
    # diff empty → skip commit, return done
    assert result == "done"


def test_no_change_sets_note(env):
    """Store task's "note" field is "no change: the tests already passed"."""
    store, _, rec, _ = env
    rec["diff_out"] = ""
    gw = gateway(env, {"coder": [WRITER]})
    loop.write_task(store, gw, "T001", log=quiet)
    t = store.get("T001")
    # Expected note string from the goal: "no change: the tests already passed"
    assert t["note"] == "no change: the tests already passed"


def test_no_change_outcome_recorded(env):
    """Telemetry outcome for the passing attempt has result "no_change"."""
    store, _, rec, _ = env
    rec["diff_out"] = ""
    gw = gateway(env, {"coder": [WRITER]})
    loop.write_task(store, gw, "T001", log=quiet)
    outs = outcomes(env)
    # The attempt's outcome is "no_change", not "passed"
    results = [o["result"] for o in outs]
    assert "no_change" in results
    # There should be exactly one "no_change" outcome
    assert results.count("no_change") == 1


def test_no_change_decision_recorded(env):
    """Store decision for the attempt has result "no_change"."""
    store, _, rec, _ = env
    rec["diff_out"] = ""
    gw = gateway(env, {"coder": [WRITER]})
    loop.write_task(store, gw, "T001", log=quiet)
    # decisions.jsonl entries
    lines = (env[3] / "decisions.jsonl").read_text(encoding="utf-8").strip().split("\n")
    recs = [json.loads(line) for line in lines]
    results = [r["result"] for r in recs]
    # The attempt decision is "no_change"
    assert "no_change" in results


def test_no_change_skips_commit(env):
    """No commit is made when the diff is empty."""
    store, _, rec, _ = env
    rec["diff_out"] = ""
    gw = gateway(env, {"coder": [WRITER]})
    loop.write_task(store, gw, "T001", log=quiet)
    # commit_all was never called
    assert rec["commits"] == []


def test_no_change_no_commit_field(env):
    """The store task has no "commit" field when the diff is empty."""
    store, _, rec, _ = env
    rec["diff_out"] = ""
    gw = gateway(env, {"coder": [WRITER]})
    loop.write_task(store, gw, "T001", log=quiet)
    t = store.get("T001")
    # No commit field was set
    assert "commit" not in t


def test_no_change_skips_review_when_review_is_on(env):
    """Even with config.REVIEW=True, an empty diff returns "done" (not "candidate") and no reviewer is called."""
    store, _, rec, _ = env
    rec["diff_out"] = ""
    # REVIEW is True in the fixture
    gw = gateway(env, {"coder": [WRITER], "reviewer": [APPROVE]})
    result = loop.write_task(store, gw, "T001", log=quiet)
    # Should be "done", not "candidate"
    assert result == "done"
    # No reviewer call was made
    roles = [c["role"] for c in gw.calls]
    # Expected: only ["coder"], no "reviewer"
    assert roles == ["coder"]


def test_no_change_with_review_off(env):
    """With REVIEW=False and empty diff, returns "done" and no commit."""
    store, _, rec, _ = env
    rec["diff_out"] = ""
    # Monkeypatch REVIEW off
    # Expected result: "done"
    assert loop.write_task(store, gateway(env, {"coder": [WRITER]}), "T001", log=quiet) == "done"
    assert rec["commits"] == []


def test_no_change_log_line(env):
    """The log mentions "no change" when the diff is empty."""
    store, _, rec, _ = env
    rec["diff_out"] = ""
    lines = []
    gw = gateway(env, {"coder": [WRITER]})
    loop.write_task(store, gw, "T001", log=lines.append)
    # Expected: a log line containing "no change"
    assert any("no change" in line for line in lines)


# ---- diff non-empty: normal behaviour is unchanged ----

def test_non_empty_diff_commits_normally_with_review_off(env, monkeypatch):
    """Non-empty diff + REVIEW off → commit made, returns "done", status "done"."""
    store, _, rec, _ = env
    monkeypatch.setattr(config, "REVIEW", False)
    rec["diff_out"] = "diff --git a/pkg/a.py b/pkg/a.py\n+X = 1\n"
    gw = gateway(env, {"coder": [WRITER]})
    result = loop.write_task(store, gw, "T001", log=quiet)
    # Expected: "done" with a commit
    assert result == "done"
    # One commit was made
    assert len(rec["commits"]) == 1
    t = store.get("T001")
    assert t["status"] == "done"
    assert t["commit"] == "sha1"


def test_non_empty_diff_makes_candidate_with_review_on(env):
    """Non-empty diff + REVIEW on → candidate commit, returns "candidate"."""
    store, _, rec, _ = env
    rec["diff_out"] = "diff --git a/pkg/a.py b/pkg/a.py\n+X = 1\n"
    gw = gateway(env, {"coder": [WRITER], "reviewer": [APPROVE]})
    result = loop.write_task(store, gw, "T001", log=quiet)
    # Expected: "candidate"
    assert result == "candidate"
    # One commit was made (the candidate)
    assert len(rec["commits"]) == 1
    t = store.get("T001")
    assert t["status"] == "awaiting_review"
