"""Tests for T243 (P22, 2026-11-21): a review issue blocks only with evidence; an unparsed review is asked again.

Why: in T240 the reviewer (Tiel) rejected 6 answers that passed the tests; 5 of its claims were false (" < " found
inside " <= ", digits in "a1.b2"). And T239's last review could not be read, which counted as an approval.

review.REVIEW_SYSTEM asks for a "quote" in every issue: the exact changed line the issue is about, copied from the
diff (the word "quote" and the sentence "An issue whose quote is not a line of the diff or of the whole changed
files does not count." are in it).
review.parse keeps it: each issue gets "quote" (a str; "" when missing or not a string).
review.grounded(issue, diff, whole="") -> True when the quote, with a leading "+" or "-" removed and every run of
  whitespace made one space (also at the ends: stripped), is at least 3 characters long and is found in the
  diff's code lines (header lines - starting with "diff ", "+++", "---" or "@@" - are left out; each other line
  loses its first character when it is "+", "-" or " ") or in `whole`, all joined with spaces and
  whitespace-collapsed the same way.
review.is_blocking(review, diff=None, whole="") -> diff None: as before (any high or medium issue). Otherwise
  only a high or medium issue that is grounded(issue, diff, whole) blocks.
review.format_issues(review, diff=None, whole="") -> as before; when diff is given, the line of a high or medium
  issue that is not grounded ends with " (not counted: its quote is not in the diff)".
loop.review_tasks:
  - blocks with review.is_blocking(rv, diff=diff_text, whole=whole or ""), and writes the feedback and the commit
    message with review.format_issues(rv, diff=diff_text, whole=whole or "");
  - when the first answer parses as "unparsed", it asks the reviewer once more with the same messages plus
    {"role": "assistant", "content": <the first answer>} and {"role": "user", "content": REVIEW_AGAIN} where
    review.REVIEW_AGAIN = "Your answer was not the JSON object asked for. Answer again with only that JSON object."
    (same role, model, effort, max_tokens; attempt as before) and uses that answer (saved as f"{attempt}-review2");
  - when it is still unparsed: the task is done, store field review = "unparsed", and the commit message is
    "Review: unparsed (not reviewed - check by hand)".
stratos status prints " [unreviewed]" after a done task whose review is "unparsed"."""
import pytest
from test_loop_review import WRITER, FakeGateway, env, quiet  # noqa: F401  (env is a fixture)

from stratos import __main__ as cli, loop, review

DIFF = ("diff --git a/pkg/a.py b/pkg/a.py\n--- a/pkg/a.py\n+++ b/pkg/a.py\n@@ -1,2 +1,2 @@\n"
        " def f(a, b):\n-    return a < b\n+    return a <= b\n")


def issue(sev, quote, problem="p"):
    return {"severity": sev, "file": "pkg/a.py", "problem": problem, "quote": quote}


def test_the_prompt_asks_for_a_quote():
    assert '"quote"' in review.REVIEW_SYSTEM
    assert ("An issue whose quote is not a line of the diff or of the whole changed files does not count."
            in review.REVIEW_SYSTEM)


def test_parse_keeps_the_quote():
    r = review.parse('{"verdict": "changes", "issues": [{"severity": "high", "file": "a", "problem": "x", '
                     '"quote": "return a <= b"}, {"severity": "low", "problem": "y", "quote": 3}]}')
    assert [i["quote"] for i in r["issues"]] == ["return a <= b", ""]


@pytest.mark.parametrize("quote, ok", [
    ("return a <= b", True),
    ("+    return a <= b", True),
    ("-    return a < b", True),
    ("return   a <=   b  ", True),
    ("def f(a, b):", True),
    ("return a < b and c", False),
    ("a1.b2", False),
    ("", False),
    ("b", False),
    ("+++ b/pkg/a.py", False),
])
def test_grounded(quote, ok):
    assert review.grounded(issue("high", quote), DIFF) is ok


def test_grounded_in_the_whole_files():
    assert review.grounded(issue("high", "x = compute(1)"), DIFF, whole="FILE pkg/a.py\nx = compute(1)\n")


def test_is_blocking_needs_evidence():
    assert review.is_blocking({"issues": [issue("medium", "nope")]})                      # no diff: as before
    assert not review.is_blocking({"issues": [issue("medium", "nope")]}, diff=DIFF)
    assert not review.is_blocking({"issues": [issue("high", "")]}, diff=DIFF)
    assert review.is_blocking({"issues": [issue("high", "return a <= b")]}, diff=DIFF)
    assert not review.is_blocking({"issues": [issue("low", "return a <= b")]}, diff=DIFF)


def test_format_marks_issues_without_evidence():
    r = {"issues": [issue("high", "return a <= b", "off by one"), issue("medium", "zzz", "made up"),
                    issue("low", "zzz", "style")]}
    assert review.format_issues(r, diff=DIFF) == (
        "- [high] pkg/a.py: off by one\n"
        "- [medium] pkg/a.py: made up (not counted: its quote is not in the diff)\n"
        "- [low] pkg/a.py: style")
    assert review.format_issues(r) == "- [high] pkg/a.py: off by one\n- [medium] pkg/a.py: made up\n- [low] pkg/a.py: style"


UNGROUNDED = ('```json\n{"verdict": "changes", "issues": [{"severity": "high", "file": "pkg/a.py", '
              '"problem": "a < found inside <=", "quote": "x < y"}]}\n```')
APPROVE = '{"verdict": "approve", "issues": []}'


def test_an_issue_without_evidence_does_not_block(env):  # noqa: F811
    store, tel, rec, _ = env
    gw = FakeGateway(tel, {"coder": [WRITER], "reviewer": [UNGROUNDED]})
    assert loop.run_task(store, gw, "T001", log=quiet) == "done"
    assert rec["undos"] == 0
    assert any("not counted: its quote is not in the diff" in m for m in rec["finalized"])


def test_an_unparsed_review_is_asked_again(env):  # noqa: F811
    store, tel, rec, _ = env
    gw = FakeGateway(tel, {"coder": [WRITER], "reviewer": ["no json here", APPROVE]})
    assert loop.run_task(store, gw, "T001", log=quiet) == "done"
    calls = [c for c in gw.calls if c["role"] == "reviewer"]
    assert len(calls) == 2
    again = calls[1]["messages"]
    assert again[:-2] == calls[0]["messages"]
    assert again[-2] == {"role": "assistant", "content": "no json here"}
    assert again[-1] == {"role": "user", "content": review.REVIEW_AGAIN}
    assert store.get("T001")["review"] == "approve"


def test_twice_unparsed_is_done_but_marked(env, capsys):  # noqa: F811
    store, tel, rec, _ = env
    gw = FakeGateway(tel, {"coder": [WRITER], "reviewer": ["no json", "still none"]})
    assert loop.run_task(store, gw, "T001", log=quiet) == "done"
    assert store.get("T001")["review"] == "unparsed"
    assert "Review: unparsed (not reviewed - check by hand)" in rec["finalized"]
    capsys.readouterr()
    cli.main(["status"])
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if ln.startswith("T001"))
    assert line.endswith(" [unreviewed]")
