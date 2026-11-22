"""Tests for task context_review_diagnosis (rules 1+2, trials 17-18): build_messages gets review and diagnosis
keyword parameters so a review's findings and a diagnosis of earlier attempts reach the coder on every attempt.

context.build_messages(task, root, failure=None, memory=None, before=None, review=None, diagnosis=None):
- review non-empty: insert the part
  "THE TESTS PASSED, BUT A CODE REVIEW FOUND THESE PROBLEMS - fix every one and keep the tests passing:\n" + review
- diagnosis non-empty: insert the part
  "A DIAGNOSIS OF THE EARLIER ATTEMPTS (another model read their code and the failing tests):\n" + diagnosis
- These parts come right before the failure part (after the memory part), review first then diagnosis.
- review and diagnosis empty (None or ""): the prompt is unchanged.
- When failure is None, they come before the before part (the last part).
"""
from stratos import context

REVIEW_HEAD = "THE TESTS PASSED, BUT A CODE REVIEW FOUND THESE PROBLEMS - fix every one and keep the tests passing:\n"
DIAG_HEAD = "A DIAGNOSIS OF THE EARLIER ATTEMPTS (another model read their code and the failing tests):\n"
MEM_HEAD = "MEMORY (found for this task: lessons and related code):\n"
FAIL_START = "YOUR PREVIOUS ATTEMPT FAILED"
BEFORE_START = "BEFORE YOUR CHANGE THE TESTS FAIL LIKE THIS (make them pass)"

TASK = {"id": "T1", "title": "t", "goal": "g", "files": [], "protected": []}


def _user(task, root, **kw):
    return context.build_messages(task, root, **kw)[-1]["content"]


def _parts(content):
    return content.split("\n\n")


def _find(parts, prefix):
    """Index of the first part that starts with `prefix`."""
    for i, p in enumerate(parts):
        if p.startswith(prefix):
            return i
    raise ValueError(f"no part starting with {prefix!r}")


def test_review_part_exact_text():
    # Only TASK T1: t, g, then review. No failure, no memory.
    # parts: ["TASK T1: t", "g", REVIEW_HEAD + "R"]
    # content ends with "\n\n" + REVIEW_HEAD + "R"
    user = _user(TASK, ".", review="R")
    assert user.endswith("\n\n" + REVIEW_HEAD + "R")


def test_diagnosis_part_exact_text():
    # parts: ["TASK T1: t", "g", DIAG_HEAD + "D"]
    # content ends with "\n\n" + DIAG_HEAD + "D"
    user = _user(TASK, ".", diagnosis="D")
    assert user.endswith("\n\n" + DIAG_HEAD + "D")


def test_review_before_failure():
    # parts: ["TASK T1: t", "g", REVIEW_HEAD + "R", FAILURE]
    # review is immediately before failure
    user = _user(TASK, ".", failure="F", review="R")
    p = _parts(user)
    r = _find(p, REVIEW_HEAD)
    f = _find(p, FAIL_START)
    assert r == f - 1


def test_diagnosis_before_failure():
    # parts: ["TASK T1: t", "g", DIAG_HEAD + "D", FAILURE]
    user = _user(TASK, ".", failure="F", diagnosis="D")
    p = _parts(user)
    d = _find(p, DIAG_HEAD)
    f = _find(p, FAIL_START)
    assert d == f - 1


def test_review_before_diagnosis():
    # Both present with failure: review, then diagnosis, then failure.
    # parts: ["TASK T1: t", "g", REVIEW_HEAD + "R", DIAG_HEAD + "D", FAILURE]
    # r=2, d=3, f=4 → r < d < f
    user = _user(TASK, ".", failure="F", review="R", diagnosis="D")
    p = _parts(user)
    r = _find(p, REVIEW_HEAD)
    d = _find(p, DIAG_HEAD)
    f = _find(p, FAIL_START)
    # review=2, diagnosis=3, failure=4
    assert r < d < f


def test_after_memory_before_failure():
    # Memory, then review, then diagnosis, then failure.
    # parts: ["TASK T1: t", "g", MEM_HEAD + "M", REVIEW_HEAD + "R", DIAG_HEAD + "D", FAILURE]
    # m=2, r=3, d=4, f=5 → m < r < d < f
    user = _user(TASK, ".", failure="F", memory="M", review="R", diagnosis="D")
    p = _parts(user)
    m = _find(p, MEM_HEAD)
    r = _find(p, REVIEW_HEAD)
    d = _find(p, DIAG_HEAD)
    f = _find(p, FAIL_START)
    assert m < r < d < f


def test_empty_review_no_change():
    # review="" is falsy → same prompt as without review.
    base = _user(TASK, ".", failure="F")
    got = _user(TASK, ".", failure="F", review="")
    # parts identical, so content identical
    assert base == got


def test_none_review_no_change():
    base = _user(TASK, ".", failure="F")
    got = _user(TASK, ".", failure="F", review=None)
    assert base == got


def test_empty_diagnosis_no_change():
    base = _user(TASK, ".", failure="F")
    got = _user(TASK, ".", failure="F", diagnosis="")
    assert base == got


def test_no_failure_no_memory_review_and_diag_appended():
    # No failure, no memory: review and diagnosis are the last parts, review first.
    # parts: ["TASK T1: t", "g", REVIEW_HEAD + "R", DIAG_HEAD + "D"]
    # content ends with "\n\n" + REVIEW_HEAD + "R" + "\n\n" + DIAG_HEAD + "D"
    user = _user(TASK, ".", review="R", diagnosis="D")
    assert user.endswith("\n\n" + REVIEW_HEAD + "R\n\n" + DIAG_HEAD + "D")


def test_review_before_before_when_no_failure():
    # failure=None, before="B": before is the last part.
    # parts: ["TASK T1: t", "g", REVIEW_HEAD + "R", BEFORE_PART]
    # r=2, b=3 → r < b
    user = _user(TASK, ".", before="B", review="R")
    p = _parts(user)
    r = _find(p, REVIEW_HEAD)
    b = _find(p, BEFORE_START)
    assert r < b


def test_old_signature_unchanged():
    # Calling build_messages(task, root, failure, memory, before) without review/diagnosis
    # must give the same content as passing them as None.
    user1 = _user(TASK, ".", failure="F", memory="M", before="B")
    user2 = _user(TASK, ".", failure="F", memory="M", before="B", review=None, diagnosis=None)
    # failure takes priority over before, so "F" is in user1, "B" is not;
    # parts are identical
    assert user1 == user2
