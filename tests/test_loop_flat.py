"""Tests for task check_flat (P9, 2026-11-20): loop.check_answer had grown to 9 levels of nested if/else (deepest line
indented 56 spaces); T196 and T198 failed 7 times on its indentation (syntax errors, SEARCH blocks of 60 lines) and
the reviewer misread its branches. Same behaviour, flat code:

loop._judge(task, wt, text, finish) does the steps of check_answer in the same order and returns (result, detail) as
soon as one step decides (early returns, no result/detail flags); loop.check_answer(task, wt, text, finish=None)
calls it and only adds the cut-off note for finish == "length" and a result other than "passed". No line of either
function nests more than 3 if/for/while/try/with blocks. All the old check_answer tests keep passing."""
import ast
import inspect
import textwrap

from stratos import loop


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
