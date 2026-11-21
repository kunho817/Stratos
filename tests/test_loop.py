"""Tests for task T048: loop.check_answer, the judging of one model answer, taken out of write_task so that other
callers (the replay command of T049) judge answers exactly like the task loop.

check_answer(task, wt, text, finish=None) -> (result, detail)
    task: a task dict (files, protected, tests, goal); wt: the folder the files are written to; text: the model's answer;
    finish: the call's finish reason (gw.last_finish), or None.
    - no FILE blocks for the task's files -> "no_files", detail "the answer held no FILE blocks for the task's files";
      when finish is "tool_calls" the detail is instead the message that there are no tools here (it says "no tools").
    - the answer drops existing top-level definitions (patch.dropped_definitions(wt, files, goal)) -> "dropped_defs",
      detail naming each path and its dropped names; nothing is written and no tests run.
    - patch.apply_files raises PatchRefused -> "refused", detail the exception text.
    - otherwise the files are written and verify.run_tests(wt, task["tests"]) decides: "passed" or "failed", detail
      the test output.
    - when finish is "length" and the result is not "passed", the detail starts with the cut-off message (it says
      "cut off") followed by the detail above.
write_task keeps its behaviour and calls check_answer with getattr(gw, "last_finish", None).
"""
import ast
import inspect
import textwrap

import pytest

from stratos import config, gitops, loop, triage, verify
from stratos.state import Store
from stratos.telemetry import Telemetry


TASK = {"id": "T900", "files": ["pkg/a.py"], "protected": ["tests/test_a.py"], "tests": ["tests/test_a.py"],
        "goal": "Add Y to pkg/a.py."}


GOOD = "FILE: pkg/a.py\n```python\ndef keep():\n    return 1\n\nY = 2\n```\n"


def setup(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def keep():\n    return 1\n", encoding="utf-8")
    return tmp_path


def test_no_files(tmp_path):
    wt = setup(tmp_path)
    assert loop.check_answer(TASK, wt, "no blocks here") == (
        "no_files", "the answer held no FILE blocks for the task's files")
    result, detail = loop.check_answer(TASK, wt, "no blocks here", finish="tool_calls")
    assert result == "no_files" and "no tools" in detail


def test_dropped_defs_write_nothing(tmp_path, monkeypatch):
    wt = setup(tmp_path)
    ran = []
    monkeypatch.setattr(verify, "run_tests", lambda w, t: ran.append(t) or (True, "ok"))
    result, detail = loop.check_answer(TASK, wt, "FILE: pkg/a.py\n```python\nY = 2\n```\n")
    assert result == "dropped_defs" and "pkg/a.py: keep" in detail
    assert ran == [] and "def keep" in (wt / "pkg" / "a.py").read_text(encoding="utf-8")


def test_refused(tmp_path):
    wt = setup(tmp_path)
    task = dict(TASK, files=[])
    result, detail = loop.check_answer(task, wt, "FILE: tests/test_a.py\n```python\nX = 1\n```\n")
    assert result == "refused" and "tests/test_a.py" in detail


def test_passed_and_failed(tmp_path, monkeypatch):
    wt = setup(tmp_path)
    monkeypatch.setattr(verify, "run_tests", lambda w, t: (t == ["tests/test_a.py"], "1 passed"))
    assert loop.check_answer(TASK, wt, GOOD) == ("passed", "1 passed")
    assert "Y = 2" in (wt / "pkg" / "a.py").read_text(encoding="utf-8")
    monkeypatch.setattr(verify, "run_tests", lambda w, t: (False, "FAILED tests/test_a.py::test_y"))
    assert loop.check_answer(TASK, wt, GOOD) == ("failed", "FAILED tests/test_a.py::test_y")


def test_cut_off_answers(tmp_path, monkeypatch):
    wt = setup(tmp_path)
    monkeypatch.setattr(verify, "run_tests", lambda w, t: (False, "FAILED x"))
    result, detail = loop.check_answer(TASK, wt, GOOD, finish="length")
    assert result == "failed" and "cut off" in detail and detail.endswith("FAILED x")
    monkeypatch.setattr(verify, "run_tests", lambda w, t: (True, "ok"))
    assert loop.check_answer(TASK, wt, GOOD, finish="length") == ("passed", "ok")


# ---- was test_loop_consensus.py ----
# Tests for task consensus (P5, 2026-11-20, BACKLOG item 17): two models that wrote their own code and fail the same
# test are evidence against the test. History of 5 projects: of 25 tasks where two models failed a shared test, 15
# were later reset by a person as "test wrong" (60%); of 12 where they failed different tests, 3 (25%); 15 of all 20
# test-wrong resets had the signal.
#
# loop.write_task: for every attempt whose result is "failed", collect decide._extract_ids(detail) per model (union over
# that model's failed attempts). Right before the task goes to a person (after the attempts, before triage), when at
# least two models have failed attempts, consensus = the sorted ids that every such model failed. When it is not
# empty: store.update(task_id, consensus=consensus); gw.telemetry.record("consensus", task=task_id, tests=consensus,
# models=<the sorted model names>); log f"  consensus: {', '.join(models)} all failed {', '.join(consensus)}";
# and triage.triage gets consensus=consensus as a keyword (only then: old fakes take no such argument).
#
# triage.build_messages(task, root, code_files, test_output, consensus=None): with consensus, right before the
# "Test output:" line, the lines "Independent attempts: different models wrote their own code for this task and all
# failed these same tests:" then one "- <id>" line per id and the line "Code from different models that agrees against
# a test is a sign the test may be wrong; check those tests first." and an empty line. triage.triage(gw, task, root,
# code_files, test_output, consensus=None) passes it on.


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


# ---- was test_loop_flat.py ----
# Tests for task check_flat (P9, 2026-11-20): loop.check_answer had grown to 9 levels of nested if/else (deepest line
# indented 56 spaces); T196 and T198 failed 7 times on its indentation (syntax errors, SEARCH blocks of 60 lines) and
# the reviewer misread its branches. Same behaviour, flat code:
#
# loop._judge(task, wt, text, finish) does the steps of check_answer in the same order and returns (result, detail) as
# soon as one step decides (early returns, no result/detail flags); loop.check_answer(task, wt, text, finish=None)
# calls it and only adds the cut-off note for finish == "length" and a result other than "passed". No line of either
# function nests more than 3 if/for/while/try/with blocks. All the old check_answer tests keep passing.


def deepest(fn):
    """How many if/for/while/try/with blocks are nested inside the function at most (continuation lines of a long
    string do not count; Claude's first version counted indentation and failed two models on aligned strings)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    blocks = (ast.If, ast.For, ast.While, ast.Try, ast.With)

    def depth(node, elif_=False):
        inner = []
        for c in ast.iter_child_nodes(node):
            is_elif = isinstance(node, ast.If) and len(node.orelse) == 1 and c is node.orelse[0] \
                and isinstance(c, ast.If)
            inner.append(depth(c, is_elif))
        own = 1 if isinstance(node, blocks) and not elif_ else 0
        return own + max(inner, default=0)
    return depth(tree)


def test_flat():
    assert deepest(loop._judge) <= 3
    assert deepest(loop.check_answer) <= 3


def test_check_answer_wraps_judge(monkeypatch):
    monkeypatch.setattr(loop, "_judge", lambda task, wt, text, finish: ("failed", "boom"))
    assert loop.check_answer({}, ".", "x") == ("failed", "boom")
    assert loop.check_answer({}, ".", "x", finish="length")[1].startswith(
        "Your answer was cut off: it reached the length limit.")
    monkeypatch.setattr(loop, "_judge", lambda task, wt, text, finish: ("passed", "ok"))
    assert loop.check_answer({}, ".", "x", finish="length") == ("passed", "ok")
