"""Tests for task T038: the reviewer is told that changes the goal did not ask for and code that is never used are
medium issues (they block). Before this, the reviewer saw T029's reworded prompt and T034's renamed variable but rated
them low, and let T035's unused dict pass. Replaying those diffs with this wording (2026-11-17): 6/6 caught, and 0 of
6 runs on clean diffs blocked."""
from stratos import review


def test_every_line_is_checked_against_the_goal():
    assert "Check every changed line against the goal." in review.REVIEW_SYSTEM


def test_unrequested_changes_are_always_medium():
    s = review.REVIEW_SYSTEM
    assert "a change the goal did not ask for" in s
    assert "is ALWAYS medium, even when it looks small or harmless, never low" in s


def test_unused_code_is_medium():
    assert "code that is never used (an unused variable, import or function)" in review.REVIEW_SYSTEM


def test_low_is_style_in_requested_lines():
    assert "low = style only, in lines the goal asked to change." in review.REVIEW_SYSTEM
