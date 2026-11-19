"""Tests for task review_severity (P2, 2026-11-20, BACKLOG item 14): the reviewer rated "simulate() is called twice"
on Lumen's 40-cell board as medium, which sent a passing T004 back: 4 more attempts and 2 model switches for a nit.
Repeated work blocks only when it grows with the input (Orbit's drawTrail stroked a growing path after every point:
n^2 per frame). REVIEW_SYSTEM keeps everything else (tests/test_review_scope.py) and changes only this:
- the medium list no longer says "needless repeated work"; it says "work that grows with the input inside a loop
  (for example redrawing everything once per item)";
- it adds: "a repeated call that costs a fixed small amount is low unless the goal is about speed"."""
from stratos import review


def test_growing_work_is_medium():
    assert "work that grows with the input inside a loop (for example redrawing everything once per item)" in \
        review.REVIEW_SYSTEM


def test_small_repeated_calls_are_low():
    assert "a repeated call that costs a fixed small amount is low unless the goal is about speed" in \
        review.REVIEW_SYSTEM
    assert "needless repeated work" not in review.REVIEW_SYSTEM
