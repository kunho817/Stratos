"""Tests for stratos/mutate.py (P21, 2026-11-21): small bugs made by rule, to see whether drafted tests catch them.

Why: refcheck says a draft "agrees" with an independent reference, but not whether the draft would notice a wrong
answer (Lantern's solver tests all passed on a wrong solver). A draft that lets most small bugs through is weak.

mutate.mutants(source, limit=12) -> a list of dicts {"line": n (1-based), "old": the line, "new": the mutated
line, "source": the whole mutated source}. Each mutant changes ONE occurrence on ONE line (the line ending kept).
Mutants of a line are ordered by their position on the line (left to right); at the same position, in the
order of this list of operators:
  " <= " -> " < ", " >= " -> " > ", " < " -> " <= ", " > " -> " >= "   (only with a space on both sides: no ->, <<,
  generics like List<int>, or =>)
  " == " -> " != ", " != " -> " == "
  " + " -> " - ", " - " -> " + "                                       (spaces on both sides again)
  " and " -> " or ", " or " -> " and ", " && " -> " || ", " || " -> " && "
  the words True <-> False and true <-> false                          (whole words)
  an integer literal n -> n + 1 written as a number ("0" -> "1", "41" -> "42"): a run of digits that is not part of
  a name or of a decimal number (no letter, digit, "_" or "." right before or after it)
Places that are never mutated:
  - blank lines and comment lines (after leading spaces they start with "#", "//", "/*" or "*");
  - anything after a "#" or "//" that is outside a string on the line;
  - anything inside a string literal on the line ('...' or "..."; a quote preceded by a backslash does not count);
  - lines inside a Python triple-quoted block, and lines that open or close one (a line with an odd number of
    \"\"\" or ''' toggles the block; a line with an even, nonzero number is a one-line docstring and is skipped).
All mutants are collected in that order (line by line). With more than `limit` of them, `limit` are kept, spread
evenly: the ones at index round(i * (n - 1) / (limit - 1)) for i in range(limit) (limit 1 keeps the first);
limit <= 0 gives []."""
from stratos import mutate


def news(source, limit=50):
    return [m["new"] for m in mutate.mutants(source, limit)]


def test_comparison_and_spacing():
    assert news("if a < b:\n") == ["if a <= b:\n"]
    assert news("if a >= b:\n") == ["if a > b:\n"]
    assert news("x = a<b\ndef f() -> int:\nList<int> y;\nf = x => y\n") == []


def test_one_occurrence_at_a_time_in_order():
    src = "    return a == b and c + 1 > 2\n"
    assert news(src) == [
        "    return a != b and c + 1 > 2\n",
        "    return a == b or c + 1 > 2\n",
        "    return a == b and c - 1 > 2\n",
        "    return a == b and c + 2 > 2\n",
        "    return a == b and c + 1 >= 2\n",
        "    return a == b and c + 1 > 3\n",
    ]


def test_words_and_js_operators():
    assert news("ok = True\n") == ["ok = False\n"]
    assert news("const ok = false || x && y;\n") == [
        "const ok = true || x && y;\n", "const ok = false && x && y;\n", "const ok = false || x || y;\n"]
    assert news("Trueish = untrue\n") == []


def test_integers_only_alone():
    assert news("n = 41\n") == ["n = 42\n"]
    assert news("x2 = 3.5 + y_1\n") == ["x2 = 3.5 - y_1\n"]
    assert news("v = 0\n") == ["v = 1\n"]


def test_strings_and_comments_are_left_alone():
    assert news('msg = "a < b and 1 == 2"\n') == []
    assert news("msg = 'it\\'s 3'  # 4 + 5\n") == []
    assert news("# x = 1 + 2\n    // y < z\n  * 3 == 3\n/* 1 */\n") == []
    assert news("int n = 7; // was 8\n") == ["int n = 8; // was 8\n"]


def test_docstrings_are_left_alone():
    src = 'def f():\n    """One line 1 + 2."""\n    return 1\n\n\ndef g():\n    """\n    a < b\n    """\n    return 0\n'
    got = mutate.mutants(src, 50)
    assert [(m["line"], m["new"]) for m in got] == [(3, "    return 2\n"), (10, "    return 1\n")]
    assert got[0]["old"] == "    return 1\n"
    assert got[0]["source"] == src.replace("    return 1\n", "    return 2\n")


def test_line_endings_kept():
    got = mutate.mutants("a = 1\r\nb = 2", 50)
    assert [m["new"] for m in got] == ["a = 2\r\n", "b = 3"]
    assert got[1]["source"] == "a = 1\r\nb = 3"


def test_limit_spreads_evenly():
    src = "".join(f"v{i} = {i}\n" for i in range(10))   # 10 mutants, one per line
    lines = [m["line"] for m in mutate.mutants(src, 4)]
    assert lines == [1, 4, 7, 10]
    assert [m["line"] for m in mutate.mutants(src, 1)] == [1]
    assert mutate.mutants(src, 0) == []
    assert len(mutate.mutants(src)) == 10
