"""Tests for task T039: ask Jev whether a failing task should go to the other model now (shadow use, like T034).

escalate_request(task, history) -> (state, questions)
    history: [(result, detail), ...] of the current role's attempts, oldest first (as decide.should_escalate gets it).
    Only a summary goes out: state is {"goal": task goal, "files": task files, "attempts": [one dict per attempt:
    {"result": result, "failed_tests": decide.failure_signature(result, detail)}]}, except that a signature
    starting with "E " (an error line, which may quote code or data) is sent as "". No other part of detail is sent.
    One question "switch", type "noul", whose criteria are {"true": ..., "false": ...}.

should_escalate(task, history, **ask_kwargs) -> decision | None
    p = the "switch" answer's "noul" (probability of yes). {"choice": p >= 0.5, "confidence": max(p, 1 - p),
    "reason": text naming Jev and p, "input_tokens"}; None when ask fails or the answer has no number "noul".
"""
import json

from stratos import jev

TASK = {"id": "T900", "files": ["stratos/loop.py"], "goal": "Restructure the loop."}
FAIL_A = "FAILED tests/x.py::test_a - AssertionError: secret value 42\n1 failed"
E_ONLY = "boom\nE   ValueError: password=hunter2\n"


class FakePost:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, url, body, headers, timeout):
        self.calls.append(json.loads(body.decode("utf-8")))
        return self.replies.pop(0)


def answer(p):
    return (200, json.dumps({"model": "jev-1.14.0", "answers": {"switch": {"type": "noul", "noul": p}},
                             "usage": {"input_tokens": 210}}).encode("utf-8"))


def test_escalate_request_sends_a_summary_only():
    state, questions = jev.escalate_request(TASK, [("failed", FAIL_A), ("no_files", "no FILE blocks"),
                                                   ("failed", E_ONLY)])
    assert state == {"goal": TASK["goal"], "files": TASK["files"], "attempts": [
        {"result": "failed", "failed_tests": "tests/x.py::test_a"},
        {"result": "no_files", "failed_tests": "no_files"},
        {"result": "failed", "failed_tests": ""}]}
    text = json.dumps(state)
    assert "secret" not in text and "hunter2" not in text
    q = questions["switch"]
    assert list(questions) == ["switch"] and q["type"] == "noul" and q["instructions"]
    assert set(q["criteria"]) == {"true", "false"}


def test_should_escalate_yes_and_no():
    post = FakePost(answer(0.8))
    d = jev.should_escalate(TASK, [("failed", FAIL_A)], key="k", post=post, sleep=lambda s: None)
    assert d["choice"] is True and d["confidence"] == 0.8 and d["input_tokens"] == 210
    assert "jev" in d["reason"].lower() and "0.8" in d["reason"]
    assert post.calls[0]["questions"]["switch"]["type"] == "noul"
    d = jev.should_escalate(TASK, [("failed", FAIL_A)], key="k", post=FakePost(answer(0.1)), sleep=lambda s: None)
    assert d["choice"] is False and d["confidence"] == 0.9


def test_should_escalate_none_on_failure_or_malformed_answer():
    assert jev.should_escalate(TASK, [], key="k", post=FakePost((401, b"{}")), sleep=lambda s: None) is None
    broken = (200, json.dumps({"answers": {"switch": {"type": "noul"}}}).encode("utf-8"))
    assert jev.should_escalate(TASK, [], key="k", post=FakePost(broken), sleep=lambda s: None) is None
