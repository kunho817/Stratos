"""Tests for task check_flat (P9, 2026-11-20): loop.check_answer had grown to 9 levels of nested if/else (deepest line
indented 56 spaces); T196 and T198 failed 7 times on its indentation (syntax errors, SEARCH blocks of 60 lines) and
the reviewer misread its branches. Same behaviour, flat code:

loop._judge(task, wt, text, finish) does the steps of check_answer in the same order and returns (result, detail) as
soon as one step decides (early returns, no result/detail flags); loop.check_answer(task, wt, text, finish=None)
calls it and only adds the cut-off note for finish == "length" and a result other than "passed". No line of either
function is indented more than 20 spaces. All the old check_answer tests keep passing."""
import inspect

from stratos import loop


def deepest(fn):
    return max(len(line) - len(line.lstrip(" ")) for line in inspect.getsource(fn).splitlines() if line.strip())


def test_flat():
    assert deepest(loop._judge) <= 20
    assert deepest(loop.check_answer) <= 20


def test_check_answer_wraps_judge(monkeypatch):
    monkeypatch.setattr(loop, "_judge", lambda task, wt, text, finish: ("failed", "boom"))
    assert loop.check_answer({}, ".", "x") == ("failed", "boom")
    assert loop.check_answer({}, ".", "x", finish="length")[1].startswith(
        "Your answer was cut off: it reached the length limit.")
    monkeypatch.setattr(loop, "_judge", lambda task, wt, text, finish: ("passed", "ok"))
    assert loop.check_answer({}, ".", "x", finish="length") == ("passed", "ok")
