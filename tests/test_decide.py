"""Tests for task T026: stratos/decide.py, the first rules of the decision layer (pure functions, no model).

Every decision is a dict {"choice": ..., "confidence": float between 0 and 1, "reason": str}, so it can be logged and
later compared with what really happened (and with another decider, such as Jev).

failure_signature(result, detail) -> str
    What a failed attempt failed on, comparable between attempts. For result "failed": the ids of the FAILED tests
    (the text after 'FAILED ' up to ' - ' or the end of the line), sorted and joined by ','; if there are none, the
    ERROR lines' ids the same way; if there are none either, the first line starting with 'E ' (stripped). For any
    other result ("no_files", "refused", ...): the result itself. Empty when nothing is found.
should_escalate(history) -> decision
    history: [(result, detail), ...] of the current role's attempts so far, oldest first. choice True when the last
    two attempts failed with the same non-empty signature (the model is repeating itself; Tiel did that 3 times in
    T007, T009 and T022), confidence 0.7; otherwise choice False, confidence 0.6.
choose_role(task) -> decision
    choice "coder_hard" when the task may write two or more files (confidence 0.6, reason mentions the files), or when
    its goal (case-insensitive) contains one of FLOW_WORDS (confidence 0.55, reason names the word); otherwise
    "coder" (confidence 0.7).
"""
from stratos import decide

FAILED_A = "....F\nFAILED tests/test_x.py::test_one - AssertionError: no\n1 failed, 4 passed"
FAILED_A2 = "F....\nFAILED tests/test_x.py::test_one - KeyError: 'c1'\n1 failed, 4 passed"
FAILED_B = "FAILED tests/test_x.py::test_two - assert 1 == 2\nFAILED tests/test_x.py::test_one\n2 failed"
ERRORS = "ERROR tests/test_y.py - SyntaxError: bad\n!!!! Interrupted: 1 error during collection"
E_ONLY = "something\nE   ValueError: too many values\nmore"


def test_signature_of_failed_tests():
    assert decide.failure_signature("failed", FAILED_A) == "tests/test_x.py::test_one"
    assert decide.failure_signature("failed", FAILED_A2) == "tests/test_x.py::test_one"   # same test, other error
    assert decide.failure_signature("failed", FAILED_B) == "tests/test_x.py::test_one,tests/test_x.py::test_two"


def test_signature_falls_back_to_errors_then_e_lines():
    assert decide.failure_signature("failed", ERRORS) == "tests/test_y.py"
    assert decide.failure_signature("failed", E_ONLY) == "E   ValueError: too many values"
    assert decide.failure_signature("failed", "") == ""


def test_signature_of_other_results():
    assert decide.failure_signature("no_files", "the answer held no FILE blocks") == "no_files"
    assert decide.failure_signature("refused", "protected file: tests/x.py") == "refused"


def test_escalate_when_the_same_failure_repeats():
    d = decide.should_escalate([("failed", FAILED_A), ("failed", FAILED_A2)])
    assert d["choice"] is True and d["confidence"] == 0.7 and d["reason"]


def test_no_escalation_after_one_failure_or_different_failures():
    assert decide.should_escalate([("failed", FAILED_A)])["choice"] is False
    assert decide.should_escalate([("failed", FAILED_A), ("failed", FAILED_B)])["choice"] is False
    assert decide.should_escalate([("failed", ""), ("failed", "")])["choice"] is False     # nothing to compare
    assert decide.should_escalate([])["choice"] is False
    assert decide.should_escalate([("failed", FAILED_B)])["confidence"] == 0.6


def test_escalate_on_repeated_no_files():
    assert decide.should_escalate([("failed", FAILED_A), ("no_files", "x"), ("no_files", "y")])["choice"] is True


def test_choose_role():
    one = {"files": ["stratos/a.py"], "goal": "Add a helper that counts things."}
    two = {"files": ["stratos/a.py", "stratos/b.py"], "goal": "Add a helper."}
    flow = {"files": ["stratos/loop.py"], "goal": "Split the loop into a write phase and a review phase."}
    assert decide.choose_role(one) == {"choice": "coder", "confidence": 0.7, "reason": decide.choose_role(one)["reason"]}
    d2 = decide.choose_role(two)
    assert d2["choice"] == "coder_hard" and d2["confidence"] == 0.6 and "2" in d2["reason"]
    d3 = decide.choose_role(flow)
    assert d3["choice"] == "coder_hard" and d3["confidence"] == 0.55 and "split" in d3["reason"].lower()


def test_flow_words_exist_and_are_lower_case():
    assert decide.FLOW_WORDS and all(w == w.lower() for w in decide.FLOW_WORDS)
    assert "split" in decide.FLOW_WORDS and "restructure" in decide.FLOW_WORDS
