"""Tests for task T006: stratos/review.py, the parts of the review step that need no model.

build_messages(task, diff) -> chat messages asking a reviewer model for a JSON verdict on the diff
parse(text)                -> {"verdict": "approve" | "changes" | "unparsed", "issues": [{severity, file, problem}]}
is_blocking(review)        -> True when any issue is "high" or "medium"
format_issues(review)      -> the issues as lines for the next attempt's prompt
"""
from stratos import review


TASK = {"id": "T009", "title": "add a thing", "goal": "Add the thing to stratos/x.py."}


DIFF = "diff --git a/stratos/x.py b/stratos/x.py\n+def thing():\n+    return 1\n"


def test_build_messages_has_a_fixed_system_prompt_and_the_diff():
    msgs = review.build_messages(TASK, DIFF)
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[0]["content"] == review.REVIEW_SYSTEM            # fixed: the start of the prompt can be cached
    user = msgs[1]["content"]
    assert "T009" in user and "add a thing" in user and "Add the thing to stratos/x.py." in user
    assert DIFF in user
    for word in ("approve", "changes", "high", "medium", "low"):
        assert word in review.REVIEW_SYSTEM


def test_parse_a_json_block():
    text = 'Looks mostly fine.\n```json\n{"verdict": "changes", "issues": [{"severity": "Medium", "file": "stratos/x.py", "problem": "condition is always true"}]}\n```'
    r = review.parse(text)
    assert r["verdict"] == "changes"
    assert r["issues"] == [{"severity": "medium", "file": "stratos/x.py", "problem": "condition is always true"}]


def test_parse_bare_json_and_approve():
    r = review.parse('{"verdict": "APPROVE", "issues": []}')
    assert r == {"verdict": "approve", "issues": []}


def test_parse_bare_json_with_nested_issues():
    text = 'My review: {"verdict": "changes", "issues": [{"severity": "high", "file": "a.py", "problem": "crashes"}]} done.'
    r = review.parse(text)
    assert r["verdict"] == "changes"
    assert r["issues"] == [{"severity": "high", "file": "a.py", "problem": "crashes"}]


def test_system_prompt_shows_valid_json():
    # T009's reviewer copied a single-quoted example and its answer was read as unparsed, so nothing was reviewed
    assert "{'" not in review.REVIEW_SYSTEM and "'verdict'" not in review.REVIEW_SYSTEM
    assert '"verdict"' in review.REVIEW_SYSTEM and '"issues"' in review.REVIEW_SYSTEM


def test_parse_accepts_a_python_style_dict():
    assert review.parse("{'verdict': 'approve', 'issues': []}") == {"verdict": "approve", "issues": []}
    text = "```json\n{'verdict': 'changes', 'issues': [{'severity': 'high', 'file': 'a.py', 'problem': 'crash'}]}\n```"
    assert review.parse(text)["issues"] == [{"severity": "high", "file": "a.py", "problem": "crash"}]


def test_module_imports_are_at_the_top():
    import inspect
    assert "__import__" not in inspect.getsource(review)


def test_parse_normalizes_bad_fields():
    r = review.parse('```json\n{"verdict": "changes", "issues": [{"severity": "critical", "problem": "x"}, "not an issue"]}\n```')
    assert r["issues"] == [{"severity": "medium", "file": "", "problem": "x"}]   # unknown severity -> medium


def test_parse_garbage():
    assert review.parse("I could not review this.") == {"verdict": "unparsed", "issues": []}
    assert review.parse('```json\n{"verdict": "maybe"}\n```') == {"verdict": "unparsed", "issues": []}
    assert review.parse("") == {"verdict": "unparsed", "issues": []}


def test_is_blocking():
    issue = lambda s: {"severity": s, "file": "f.py", "problem": "p"}
    assert review.is_blocking({"verdict": "changes", "issues": [issue("high")]})
    assert review.is_blocking({"verdict": "approve", "issues": [issue("medium")]})   # the issues decide, not the word
    assert not review.is_blocking({"verdict": "changes", "issues": [issue("low")]})
    assert not review.is_blocking({"verdict": "changes", "issues": []})
    assert not review.is_blocking({"verdict": "unparsed", "issues": []})            # a broken review blocks nothing


def test_format_issues():
    r = {"verdict": "changes", "issues": [{"severity": "high", "file": "stratos/x.py", "problem": "returns None"},
                                          {"severity": "low", "file": "", "problem": "long line"}]}
    assert review.format_issues(r) == "- [high] stratos/x.py: returns None\n- [low] long line"
    assert review.format_issues({"verdict": "approve", "issues": []}) == ""


# ---- was test_review_scope.py ----
# Tests for task T038: the reviewer is told that changes the goal did not ask for and code that is never used are
# medium issues (they block). Before this, the reviewer saw T029's reworded prompt and T034's renamed variable but rated
# them low, and let T035's unused dict pass. Replaying those diffs with this wording (2026-11-17): 6/6 caught, and 0 of
# 6 runs on clean diffs blocked.


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


# ---- was test_review_severity.py ----
# Tests for task review_severity (P2, 2026-11-20, BACKLOG item 14): the reviewer rated "simulate() is called twice"
# on Lumen's 40-cell board as medium, which sent a passing T004 back: 4 more attempts and 2 model switches for a nit.
# Repeated work blocks only when it grows with the input (Orbit's drawTrail stroked a growing path after every point:
# n^2 per frame). REVIEW_SYSTEM keeps everything else (tests/test_review_scope.py) and changes only this:
# - the medium list no longer says "needless repeated work"; it says "work that grows with the input inside a loop
#   (for example redrawing everything once per item)";
# - it adds: "a repeated call that costs a fixed small amount is low unless the goal is about speed".


def test_growing_work_is_medium():
    assert "work that grows with the input inside a loop (for example redrawing everything once per item)" in \
        review.REVIEW_SYSTEM


def test_small_repeated_calls_are_low():
    assert "a repeated call that costs a fixed small amount is low unless the goal is about speed" in \
        review.REVIEW_SYSTEM
    assert "needless repeated work" not in review.REVIEW_SYSTEM
