"""Tests for the review in the task loop, split into a write phase and a review phase (task T011).

write_task(store, gw, task_id, log)       attempts until the tests pass, without a review. With config.REVIEW on, the
                                          passing attempt is committed as a candidate (status awaiting_review) and
                                          'candidate' is returned; with it off, the task is done ('done'). When every
                                          attempt fails: 'needs_human'. A task's review_feedback goes into the first
                                          attempt's prompt, and attempt numbers continue from task['attempts'].
review_tasks(store, gw, task_ids, log)    loads the reviewer once and reviews each candidate's last commit
                                          (gitops.commit_diff). Approved: status done, the review appended to the
                                          commit message. High/medium issues: gitops.undo_last_commit, status todo,
                                          review_feedback set. Returns {task_id: 'done' | 'rejected'}.
run_task(store, gw, task_id, log)         write_task then review_tasks, for up to config.REVIEW_ROUNDS rounds.

Fakes stand in for the gateway, git and the test runner; no GPU or repository is needed."""
import pytest

from stratos import config, gitops, loop, verify
from stratos.state import Store
from stratos.telemetry import Telemetry

WRITER = "FILE: pkg/a.py\n```python\nX = 1\n```\n"
APPROVE = '```json\n{"verdict": "approve", "issues": []}\n```'
BLOCK = ('```json\n{"verdict": "changes", "issues": [{"severity": "medium", "file": "pkg/a.py", '
         '"problem": "condition is always true"}]}\n```')
LOW = '```json\n{"verdict": "changes", "issues": [{"severity": "low", "file": "pkg/a.py", "problem": "long line"}]}\n```'
REVIEWER = config.ROLES["reviewer"]["model"]


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

    def chat(self, messages, *, task, role, attempt, model, effort, max_tokens):
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
    rec = {"commits": [], "discards": 0, "undos": 0, "appended": [], "finalized": [], "tests_ok": True, "bases": {}}

    def worktree(repo, root, tid, bases=None):
        rec["bases"][tid] = bases
        p = tmp_path / "wt" / tid
        p.mkdir(parents=True, exist_ok=True)
        return p
    monkeypatch.setattr(gitops, "ensure_worktree", worktree)
    monkeypatch.setattr(gitops, "dependency_bases", lambda repo, ids: [f"stratos/{i}" for i in ids])
    monkeypatch.setattr(gitops, "diff", lambda w: "diff --git a/pkg/a.py b/pkg/a.py\n+X = 1\n")
    monkeypatch.setattr(gitops, "commit_diff", lambda w: "diff --git a/pkg/a.py b/pkg/a.py\n+X = 1\n")

    def discard(w):
        rec["discards"] += 1

    def undo(w):
        rec["undos"] += 1

    def commit(w, message):
        rec["commits"].append(message)
        return f"sha{len(rec['commits'])}"

    def append(w, text):
        rec["appended"].append(text)
    monkeypatch.setattr(gitops, "discard_changes", discard)
    monkeypatch.setattr(gitops, "undo_last_commit", undo)
    monkeypatch.setattr(gitops, "commit_all", commit)
    monkeypatch.setattr(gitops, "append_to_commit_message", append)

    def finalize(w, text):
        rec["finalized"].append(text)
    monkeypatch.setattr(gitops, "finalize_commit_message", finalize)
    monkeypatch.setattr(verify, "run_tests", lambda w, tests: (rec["tests_ok"], "1 passed" if rec["tests_ok"] else "boom"))
    store = Store(state)
    store.add_task("t", "make X", ["pkg/a.py"], [], ["tests/x.py"])
    store.add_task("u", "make X too", ["pkg/a.py"], [], ["tests/x.py"])
    tel = Telemetry(state / "telemetry.jsonl")
    return store, tel, rec, state


def gateway(env, script):
    return FakeGateway(env[1], script)


def outcomes(env):
    return [e for e in env[1].load() if e["kind"] == "outcome"]


def quiet(*a):
    pass


# ---------------------------------------------------------------- run_task: write then review, in rounds

def test_approved_review_finishes_the_task(env):
    store, _, rec, _ = env
    gw = gateway(env, {"coder": [WRITER], "reviewer": [APPROVE]})
    assert loop.run_task(store, gw, "T001", log=quiet) == "done"
    assert store.get("T001")["status"] == "done"
    assert [c["role"] for c in gw.calls] == ["coder", "reviewer"]
    assert gw.calls[1]["model"] == REVIEWER
    assert len(rec["commits"]) == 1 and any("approve" in a.lower() for a in rec["finalized"])
    assert rec["appended"] == []        # T021: approval finalizes the candidate commit (title cleaned, review added)


def test_rejected_candidate_is_undone_and_rewritten_with_the_issues(env):
    store, _, rec, _ = env
    gw = gateway(env, {"coder": [WRITER, WRITER], "reviewer": [BLOCK, APPROVE]})
    assert loop.run_task(store, gw, "T001", log=quiet) == "done"
    assert [c["role"] for c in gw.calls] == ["coder", "reviewer", "coder", "reviewer"]
    assert "condition is always true" in gw.calls[2]["messages"][-1]["content"]
    assert gw.calls[2]["attempt"] == 2                 # attempt numbers continue across rounds
    assert rec["undos"] == 1 and len(rec["commits"]) == 2
    assert store.get("T001")["status"] == "done"


def test_low_issues_do_not_block_and_go_into_the_commit_message(env):
    store, _, rec, _ = env
    gw = gateway(env, {"coder": [WRITER], "reviewer": [LOW]})
    assert loop.run_task(store, gw, "T001", log=quiet) == "done"
    assert any("long line" in a for a in rec["finalized"])


def test_unparsed_review_does_not_block(env):
    gw = gateway(env, {"coder": [WRITER], "reviewer": ["I cannot review this."]})
    assert loop.run_task(env[0], gw, "T001", log=quiet) == "done"


def test_review_can_be_turned_off(env, monkeypatch):
    monkeypatch.setattr(config, "REVIEW", False)
    store, _, rec, _ = env
    gw = gateway(env, {"coder": [WRITER]})
    assert loop.run_task(store, gw, "T001", log=quiet) == "done"
    assert [c["role"] for c in gw.calls] == ["coder"] and rec["appended"] == []
    assert store.get("T001")["status"] == "done"


def test_failed_tests_are_not_reviewed(env):
    env[2]["tests_ok"] = False
    gw = gateway(env, {"coder": [WRITER] * 3, "coder_hard": [WRITER]})
    assert loop.run_task(env[0], gw, "T001", log=quiet) == "needs_human"
    assert "reviewer" not in [c["role"] for c in gw.calls]


def test_a_task_the_reviewer_keeps_rejecting_goes_to_a_person(env, monkeypatch):
    monkeypatch.setattr(config, "REVIEW_ROUNDS", 2)
    store = env[0]
    gw = gateway(env, {"coder": [WRITER, WRITER], "reviewer": [BLOCK, BLOCK]})
    assert loop.run_task(store, gw, "T001", log=quiet) == "needs_human"
    assert [c["role"] for c in gw.calls] == ["coder", "reviewer", "coder", "reviewer"]
    assert store.get("T001")["status"] == "needs_human"


def test_each_call_gets_one_outcome(env):
    gw = gateway(env, {"coder": [WRITER, WRITER], "reviewer": [BLOCK, APPROVE]})
    loop.run_task(env[0], gw, "T001", log=quiet)
    by_call = {}
    for o in outcomes(env):
        by_call.setdefault(o["call_id"], []).append(o["result"])
    assert by_call == {"c1": ["passed"], "c2": ["review_changes"], "c3": ["passed"], "c4": ["review_approve"]}


def test_review_answer_is_saved(env):
    gw = gateway(env, {"coder": [WRITER], "reviewer": [APPROVE]})
    loop.run_task(env[0], gw, "T001", log=quiet)
    assert (env[3] / "answers" / "T001-a1-review.md").read_text(encoding="utf-8") == APPROVE


# ---------------------------------------------------------------- the phases on their own

def test_write_task_leaves_a_candidate(env):
    store, _, rec, _ = env
    gw = gateway(env, {"coder": [WRITER]})
    assert loop.write_task(store, gw, "T001", log=quiet) == "candidate"
    t = store.get("T001")
    assert t["status"] == "awaiting_review" and t["commit"] == "sha1"
    assert [c["role"] for c in gw.calls] == ["coder"]


def test_review_tasks_loads_the_reviewer_once(env):
    store, _, rec, _ = env
    gw = gateway(env, {"coder": [WRITER, WRITER], "reviewer": [APPROVE, BLOCK]})
    loop.write_task(store, gw, "T001", log=quiet)
    loop.write_task(store, gw, "T002", log=quiet)
    assert loop.review_tasks(store, gw, ["T001", "T002"], log=quiet) == {"T001": "done", "T002": "rejected"}
    assert gw.switches.count(REVIEWER) == 1
    assert store.get("T001")["status"] == "done"
    t2 = store.get("T002")
    assert t2["status"] == "todo" and "condition is always true" in t2["review_feedback"]
    assert rec["undos"] == 1


def test_write_task_uses_the_review_feedback(env):
    store = env[0]
    store.update("T001", review_feedback="Fix: condition is always true", attempts=1)
    gw = gateway(env, {"coder": [WRITER]})
    loop.write_task(store, gw, "T001", log=quiet)
    assert "condition is always true" in gw.calls[0]["messages"][-1]["content"]
    assert gw.calls[0]["attempt"] == 2


# ---------------------------------------------------------------- run_all: rounds of (write all, then review all)
# T012. run_all(store, gw, task_ids, log) runs the given tasks (in that order) in rounds, at most
# config.REVIEW_ROUNDS: each round writes every task that is 'todo' and whose 'after' tasks are all 'done', then
# reviews all the new candidates together (review_tasks). A task rejected in the last round goes to a person
# (needs_human). Tasks that never became runnable stay 'todo'. Returns {task_id: final status}.

CODER = config.ROLES["coder"]["model"]


def test_run_all_writes_everything_then_reviews_everything(env):
    store = env[0]
    gw = gateway(env, {"coder": [WRITER, WRITER], "reviewer": [APPROVE, APPROVE]})
    assert loop.run_all(store, gw, ["T001", "T002"], log=quiet) == {"T001": "done", "T002": "done"}
    assert [c["role"] for c in gw.calls] == ["coder", "coder", "reviewer", "reviewer"]
    assert gw.switches == [CODER, REVIEWER]                      # two loads, not four


def test_run_all_rewrites_rejected_tasks_in_the_next_round(env):
    store = env[0]
    gw = gateway(env, {"coder": [WRITER, WRITER, WRITER], "reviewer": [APPROVE, BLOCK, APPROVE]})
    assert loop.run_all(store, gw, ["T001", "T002"], log=quiet) == {"T001": "done", "T002": "done"}
    assert [(c["role"], c["task"]) for c in gw.calls] == [
        ("coder", "T001"), ("coder", "T002"), ("reviewer", "T001"), ("reviewer", "T002"),
        ("coder", "T002"), ("reviewer", "T002")]
    assert gw.switches == [CODER, REVIEWER, CODER, REVIEWER]


def test_run_all_waits_for_dependencies(env):
    store = env[0]
    store.add_task("v", "after T001", ["pkg/a.py"], [], ["tests/x.py"], after=["T001"])
    gw = gateway(env, {"coder": [WRITER] * 3, "reviewer": [APPROVE] * 3})
    assert loop.run_all(store, gw, ["T001", "T002", "T003"], log=quiet) == {"T001": "done", "T002": "done",
                                                                           "T003": "done"}
    assert [(c["role"], c["task"]) for c in gw.calls] == [
        ("coder", "T001"), ("coder", "T002"), ("reviewer", "T001"), ("reviewer", "T002"),
        ("coder", "T003"), ("reviewer", "T003")]


def test_run_all_hands_over_a_task_rejected_every_round(env, monkeypatch):
    monkeypatch.setattr(config, "REVIEW_ROUNDS", 2)
    store = env[0]
    gw = gateway(env, {"coder": [WRITER] * 3, "reviewer": [BLOCK, APPROVE, BLOCK]})
    assert loop.run_all(store, gw, ["T001", "T002"], log=quiet) == {"T001": "needs_human", "T002": "done"}


def test_run_all_leaves_dependents_of_a_failed_task(env):
    store = env[0]
    store.add_task("v", "after T001", ["pkg/a.py"], [], ["tests/x.py"], after=["T001"])
    env[2]["tests_ok"] = False
    gw = gateway(env, {"coder": [WRITER] * 3, "coder_hard": [WRITER]})
    assert loop.run_all(store, gw, ["T001", "T003"], log=quiet) == {"T001": "needs_human", "T003": "todo"}
    assert {c["task"] for c in gw.calls} == {"T001"}


# ---------------------------------------------------------------- T017: worktrees start from dependency branches
# write_task passes bases=gitops.dependency_bases(config.REPO, task['after']) to gitops.ensure_worktree. When that raises
# gitops.BaseConflict, the task goes to a person (status needs_human, a decision with result 'base_conflict') and no
# model is called.

def test_write_task_starts_from_dependency_branches(env):
    store, _, rec, _ = env
    store.add_task("v", "after T001", ["pkg/a.py"], [], ["tests/x.py"], after=["T001"])
    gw = gateway(env, {"coder": [WRITER, WRITER]})
    loop.write_task(store, gw, "T001", log=quiet)
    loop.write_task(store, gw, "T003", log=quiet)
    assert rec["bases"]["T001"] == []
    assert rec["bases"]["T003"] == ["stratos/T001"]


def test_conflicting_dependency_branches_go_to_a_person(env, monkeypatch):
    store, _, _, state = env

    def conflict(repo, root, tid, bases=None):
        raise gitops.BaseConflict("merging stratos/T002 into stratos/T001 conflicted")
    monkeypatch.setattr(gitops, "ensure_worktree", conflict)
    gw = gateway(env, {"coder": [WRITER]})
    assert loop.write_task(store, gw, "T001", log=quiet) == "needs_human"
    assert store.get("T001")["status"] == "needs_human"
    assert gw.calls == []
    decisions = (state / "decisions.jsonl").read_text(encoding="utf-8")
    assert "base_conflict" in decisions


def test_review_tasks_with_review_off_or_no_tasks(env, monkeypatch):
    store = env[0]
    gw = gateway(env, {})
    assert loop.review_tasks(store, gw, [], log=quiet) == {}
    assert gw.switches == []
