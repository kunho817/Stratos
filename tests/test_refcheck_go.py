"""Tests for task t3: Go test counts in refcheck.

stratos/refcheck.py count_tests(output) is extended: after the existing TAP check,
when any line starts exactly with "--- PASS: " or "--- FAIL: " (no leading
whitespace), total equals the count of such lines and failing is the list of
names (the word after the prefix up to the first space) from the "--- FAIL: "
lines. The TAP, dotnet, and pytest branches keep working unchanged.
"""

from stratos import refcheck

# Go test output constants
GO_ONE_PASS = "--- PASS: TestFoo (0.01s)\n"
GO_ONE_FAIL = "--- FAIL: TestFoo (0.01s)\n"
GO_TWO_PASS = "--- PASS: TestFoo (0.01s)\n--- PASS: TestBar (0.02s)\n"
GO_TWO_FAIL = "--- FAIL: TestFoo (0.01s)\n--- FAIL: TestBar (0.02s)\n"
GO_MIXED = "--- PASS: TestFoo (0.01s)\n--- FAIL: TestBar (0.02s)\n--- PASS: TestBaz (0.03s)\n"
GO_INDENTED = "    --- FAIL: SubTest (0.01s)\n--- FAIL: TestFoo (0.01s)\n"
GO_ALL_SUB = "    --- FAIL: SubTest (0.01s)\n"
GO_NO_TIME = "--- FAIL: TestFoo\n"
GO_EMPTY = "--- FAIL: \n"
GO_DUP = "--- FAIL: TestFoo (0.01s)\n--- FAIL: TestFoo (0.02s)\n--- FAIL: TestBar (0.01s)\n"
GO_SUB_TOP = "--- FAIL: TestFoo (0.01s)\n    --- FAIL: Sub (0.01s)\n--- PASS: TestBar (0.02s)\n"
PYTEST = "FAILED tests/x.py::test_b - assert 1 == 2\n1 failed, 2 passed in 0.1s\n"
TAP = "ok 1 - a\nnot ok 2 - b\nok 3 - c\n# tests 3\n"
GO_WITH_SUMMARY = "--- PASS: TestFoo (0.01s)\nPASS\n"


def test_count_go_single_pass():
    """One '--- PASS: ' line yields total=1, no failures."""
    # "--- PASS: TestFoo (0.01s)" → 1 Go line, no FAIL
    # Expected: total=1, failing=[]
    assert refcheck.count_tests(GO_ONE_PASS) == (1, [])


def test_count_go_single_fail():
    """One '--- FAIL: ' line yields total=1, failing=['TestFoo']."""
    # "--- FAIL: TestFoo (0.01s)" → 1 Go line, 1 FAIL
    # Name: "TestFoo" (word after "--- FAIL: " up to first space)
    # Expected: total=1, failing=["TestFoo"]
    assert refcheck.count_tests(GO_ONE_FAIL) == (1, ["TestFoo"])


def test_count_go_two_pass():
    """Two '--- PASS: ' lines yield total=2, no failures."""
    # Two PASS lines → total=2, no FAIL lines
    # Expected: total=2, failing=[]
    assert refcheck.count_tests(GO_TWO_PASS) == (2, [])


def test_count_go_two_fail():
    """Two '--- FAIL: ' lines yield total=2, failing in order of appearance."""
    # "--- FAIL: TestFoo (0.01s)" → name "TestFoo"
    # "--- FAIL: TestBar (0.02s)" → name "TestBar"
    # total = 2, failing = ["TestFoo", "TestBar"] (order of appearance)
    # Expected: total=2, failing=["TestFoo", "TestBar"]
    assert refcheck.count_tests(GO_TWO_FAIL) == (2, ["TestFoo", "TestBar"])


def test_count_go_mixed_pass_fail():
    """PASS and FAIL lines: total counts all, failing lists only FAIL names."""
    # "--- PASS: TestFoo" → counts
    # "--- FAIL: TestBar" → counts, name "TestBar"
    # "--- PASS: TestBaz" → counts
    # total = 3, failing = ["TestBar"]
    # Expected: total=3, failing=["TestBar"]
    assert refcheck.count_tests(GO_MIXED) == (3, ["TestBar"])


def test_count_go_indented_not_matched():
    """An indented '--- FAIL: ' line (subtest) has leading whitespace, not matched."""
    # "    --- FAIL: SubTest (0.01s)" → leading spaces → not matched
    # "--- FAIL: TestFoo (0.01s)" → no leading whitespace → matched
    # total = 1, failing = ["TestFoo"]
    # Expected: total=1, failing=["TestFoo"]
    assert refcheck.count_tests(GO_INDENTED) == (1, ["TestFoo"])


def test_count_go_all_subtests():
    """Only indented subtest lines → no top-level Go lines, total=0."""
    # "    --- FAIL: SubTest (0.01s)" → leading whitespace → not matched
    # Expected: total=0, failing=[]
    assert refcheck.count_tests(GO_ALL_SUB) == (0, [])


def test_count_go_no_timing():
    """A FAIL line without parenthetical timing: name is the whole remaining word."""
    # "--- FAIL: TestFoo" → after prefix: "TestFoo" → first word "TestFoo"
    # Expected: total=1, failing=["TestFoo"]
    assert refcheck.count_tests(GO_NO_TIME) == (1, ["TestFoo"])


def test_count_go_empty_name():
    """'--- FAIL: ' with nothing after: line counts toward total, no name in failing."""
    # "--- FAIL: " → after prefix: "" → no word → no name
    # total = 1 (it is a Go FAIL line), failing = []
    # Expected: total=1, failing=[]
    assert refcheck.count_tests(GO_EMPTY) == (1, [])


def test_count_go_dup_names():
    """Duplicate names appear in failing in order of appearance (no dedup)."""
    # "--- FAIL: TestFoo (0.01s)" → "TestFoo"
    # "--- FAIL: TestFoo (0.02s)" → "TestFoo"
    # "--- FAIL: TestBar (0.01s)" → "TestBar"
    # total = 3, failing = ["TestFoo", "TestFoo", "TestBar"]
    # Expected: total=3, failing=["TestFoo", "TestFoo", "TestBar"]
    assert refcheck.count_tests(GO_DUP) == (3, ["TestFoo", "TestFoo", "TestBar"])


def test_count_go_subtest_with_top_level():
    """Top-level PASS/FAIL lines count; indented subtests do not."""
    # "--- FAIL: TestFoo (0.01s)" → matched
    # "    --- FAIL: Sub (0.01s)" → indented, NOT matched
    # "--- PASS: TestBar (0.02s)" → matched
    # total = 2, failing = ["TestFoo"]
    # Expected: total=2, failing=["TestFoo"]
    assert refcheck.count_tests(GO_SUB_TOP) == (2, ["TestFoo"])


def test_count_go_pytest_mixed():
    """Go lines fire the Go branch; pytest summary lines are ignored."""
    # GO_ONE_FAIL + PYTEST: Go branch fires first (Go lines found)
    # Only "--- FAIL: TestFoo (0.01s)" counts → total=1, failing=["TestFoo"]
    # The pytest "1 failed, 2 passed" line is NOT used
    # Expected: total=1, failing=["TestFoo"]
    detail = GO_ONE_FAIL + PYTEST
    assert refcheck.count_tests(detail) == (1, ["TestFoo"])


def test_count_go_tap_wins():
    """TAP output fires first; Go lines are ignored when TAP is present."""
    # TAP "ok 1 - a\nnot ok 2 - b\nok 3 - c\n# tests 3" + Go FAIL
    # TAP branch fires: total=3, failing=["b"]
    # Expected: total=3, failing=["b"]
    detail = TAP + GO_ONE_FAIL
    assert refcheck.count_tests(detail) == (3, ["b"])


def test_count_go_empty_output():
    """Empty output: no Go lines, no TAP, no dotnet, no pytest → (0, [])."""
    # Expected: total=0, failing=[]
    assert refcheck.count_tests("") == (0, [])


def test_count_go_pass_summary_line_ignored():
    """Go's trailing 'PASS' line is not a Go result line; only PASS/FAIL prefixed lines count."""
    # "--- PASS: TestFoo (0.01s)" → matched
    # "PASS" → not a Go result line
    # total = 1, failing = []
    # Expected: total=1, failing=[]
    assert refcheck.count_tests(GO_WITH_SUMMARY) == (1, [])
