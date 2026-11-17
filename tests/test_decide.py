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


# T031: a flow word counts only as a whole word (T029's goal "Remove duplicates" matched 'move ' and a one-file task
# went to the slow coder). Latin words match between word boundaries, case-insensitive; Korean words match anywhere.

def test_flow_words_match_whole_words_only():
    def role(goal):
        return decide.choose_role({"files": ["stratos/a.py"], "goal": goal})["choice"]
    assert role("Remove duplicates and return the list.") == "coder"
    assert role("Keep the workflow the same.") == "coder"
    assert role("A splitter helper.") == "coder"
    assert role("Split the loop in two.") == "coder_hard"
    assert role("Move the check to the end.") == "coder_hard"
    assert role("Do it in rounds.") == "coder_hard"
    assert role("작업 흐름을 바꾼다.") == "coder_hard"


def test_flow_words_have_no_padding():
    assert all(w == w.strip() for w in decide.FLOW_WORDS)
    assert "move" in decide.FLOW_WORDS


def test_flow_words_exist_and_are_lower_case():
    assert decide.FLOW_WORDS and all(w == w.lower() for w in decide.FLOW_WORDS)
    assert "split" in decide.FLOW_WORDS and "restructure" in decide.FLOW_WORDS


# T047: flow words count only in the goal's headline. Goals start with one paragraph that says what to do, then give
# details; detail words ("split goal into sentences", re.split, a quoted description such as "control flow") sent
# one-file tasks T032 and T046 to the slow coder. decide.headline(goal) is the text before the first blank line (a
# line holding only spaces or tabs), with these removed: spans in backticks, in double quotes, in single quotes (a
# quote that does not follow a letter or digit, up to a quote that is not followed by one; so "writer's" is not a
# quote), and dotted names such as re.split or a.b.c. choose_role looks for FLOW_WORDS in decide.headline(goal) only.

def test_headline_is_the_first_paragraph():
    assert decide.headline("Split the loop.\n\nThen move x.") .strip() == "Split the loop."
    assert "move" not in decide.headline("Add a helper.\n  \nMove the check.")
    assert decide.headline("One line only.") == "One line only."


def test_headline_drops_quotes_and_dotted_names():
    h = decide.headline('Use re.split and a.b.c here; "control flow" and `split` and \'phase\' go.')
    assert "split" not in h and "control flow" not in h and "phase" not in h and "a.b.c" not in h
    assert "Use" in h and "here" in h
    assert "writer's outcome" in decide.headline("Move the writer's outcome to the end, it's late.")


def test_flow_words_only_in_the_headline():
    def role(goal):
        return decide.choose_role({"files": ["stratos/a.py"], "goal": goal})["choice"]
    assert role("In stratos/patch.py, add _excused.\n\n- split goal into sentences with re.split.") == "coder"
    assert role('Create stratos/jev.py. Criteria: "for changes to existing control flow".') == "coder"
    assert role("Add a helper that uses re.split.") == "coder"
    assert role("Split the task loop into a write phase and a review phase.\n\nDetails.") == "coder_hard"
    assert role("Two fixes. Move the writer's outcome to after the review.") == "coder_hard"
