"""Tests for task t2: Go failing test ids in decide.

stratos/decide.py _extract_ids(detail) is extended to read Go test output:
A line that starts exactly with "--- FAIL: " (no leading whitespace) contributes the test name,
which is the word after "--- FAIL: " up to the first space.
TAP ("not ok") and pytest (FAILED/ERROR) formats keep working unchanged.
ids remain sorted and de-duplicated.
"""

from stratos.decide import _extract_ids, failure_signature, should_escalate


# Go output constants
GO_SINGLE = "--- FAIL: TestFoo (0.01s)\n"
GO_TWO = "--- FAIL: TestFoo (0.01s)\n--- FAIL: TestBar (0.02s)\n"
GO_INDENTED = "    --- FAIL: TestSub (0.01s)\n--- FAIL: TestFoo (0.01s)\n"
GO_ALL_PASS = "--- PASS: TestFoo (0.01s)\n--- PASS: TestBar (0.02s)\n"
GO_NO_TIME = "--- FAIL: TestFoo\n"
GO_EMPTY_NAME = "--- FAIL: \n"
GO_DUP = "--- FAIL: TestFoo (0.01s)\n--- FAIL: TestFoo (0.02s)\n--- FAIL: TestBar (0.01s)\n"
GO_ORDER = "--- FAIL: TestZ (0.01s)\n--- FAIL: TestA (0.01s)\n--- FAIL: TestZ (0.02s)\n"
GO_SUB_ONLY = "    --- FAIL: SubTest (0.01s)\n"
PYTEST = "FAILED tests/test_a.py::test_one - AssertionError\n"
TAP = "not ok 1 - tap_test\n"
GO_MIXED = "--- FAIL: TestFoo (0.01s)\n"


def test_extract_ids_go_single():
    """A Go FAIL line yields the test name up to the first space."""
    # "--- FAIL: TestFoo (0.01s)" → after prefix: "TestFoo (0.01s)" → first word "TestFoo"
    # Expected: ["TestFoo"]
    assert _extract_ids(GO_SINGLE) == ["TestFoo"]


def test_extract_ids_go_two_sorted():
    """Two Go FAIL lines produce sorted ids."""
    # TestFoo, TestBar → dedup → [TestFoo, TestBar] → sorted → ["TestBar", "TestFoo"]
    # Expected: ["TestBar", "TestFoo"]
    assert _extract_ids(GO_TWO) == ["TestBar", "TestFoo"]


def test_extract_ids_go_indented_not_matched():
    """An indented '--- FAIL: ' line (subtest) is NOT extracted (no leading whitespace rule)."""
    # "    --- FAIL: TestSub (0.01s)" has leading spaces → not matched
    # "--- FAIL: TestFoo (0.01s)" has no leading whitespace → matched
    # Expected: ["TestFoo"]
    assert _extract_ids(GO_INDENTED) == ["TestFoo"]


def test_extract_ids_go_only_top_level():
    """Only top-level FAIL lines are captured; indented subtests are ignored."""
    # "    --- FAIL: SubTest (0.01s)" → indented, ignored
    # Expected: []
    assert _extract_ids(GO_SUB_ONLY) == []


def test_extract_ids_go_pass_ignored():
    """Go PASS lines do not contribute ids."""
    # "--- PASS: TestFoo (0.01s)" and "--- PASS: TestBar (0.02s)" → no FAIL
    # Expected: []
    assert _extract_ids(GO_ALL_PASS) == []


def test_extract_ids_go_no_timing():
    """A FAIL line without parenthetical timing gives the name as the whole remaining word."""
    # "--- FAIL: TestFoo" → after prefix: "TestFoo" → first word "TestFoo"
    # Expected: ["TestFoo"]
    assert _extract_ids(GO_NO_TIME) == ["TestFoo"]


def test_extract_ids_go_empty_name():
    """'--- FAIL: ' with nothing after yields no id."""
    # "--- FAIL: " → after prefix: "" → no word
    # Expected: []
    assert _extract_ids(GO_EMPTY_NAME) == []


def test_extract_ids_go_dedup():
    """Duplicate Go test names are de-duplicated, then sorted."""
    # TestFoo, TestFoo, TestBar → dedup [TestFoo, TestBar] → sorted ["TestBar", "TestFoo"]
    # Expected: ["TestBar", "TestFoo"]
    assert _extract_ids(GO_DUP) == ["TestBar", "TestFoo"]


def test_extract_ids_go_order_preserved_in_dedup():
    """First-seen order is kept during dedup, then sorted."""
    # TestZ, TestA, TestZ → dedup [TestZ, TestA] → sorted ["TestA", "TestZ"]
    # Expected: ["TestA", "TestZ"]
    assert _extract_ids(GO_ORDER) == ["TestA", "TestZ"]


def test_extract_ids_go_mixed_pytest():
    """Go and pytest ids coexist; sorted together."""
    # pytest: "tests/test_a.py::test_one"; Go: "TestFoo"
    # Sorted: "TestFoo" < "tests/test_a.py::test_one" because 'T' (84) < 't' (116)
    # Expected: ["TestFoo", "tests/test_a.py::test_one"]
    detail = PYTEST + GO_SINGLE
    assert _extract_ids(detail) == ["TestFoo", "tests/test_a.py::test_one"]


def test_extract_ids_go_mixed_tap():
    """Go and TAP ids coexist; sorted together."""
    # TAP: "tap_test"; Go: "TestFoo"
    # Sorted: "TestFoo" < "tap_test" because 'T' (84) < 't' (116)
    # Expected: ["TestFoo", "tap_test"]
    detail = TAP + GO_SINGLE
    assert _extract_ids(detail) == ["TestFoo", "tap_test"]


def test_failure_signature_go():
    """failure_signature with Go output returns the joined ids."""
    # detail: "--- FAIL: TestFoo (0.01s)\n--- FAIL: TestBar (0.02s)"
    # ids: TestBar, TestFoo (sorted)
    # Expected: "TestBar,TestFoo"
    assert failure_signature("failed", GO_TWO) == "TestBar,TestFoo"


def test_should_escalate_go_repeated():
    """Same Go failure output in two attempts escalates."""
    # First sig: "TestBar,TestFoo" (from GO_TWO)
    # Second sig: "TestBar,TestFoo" (same detail)
    # Same → escalate
    # Expected: choice True
    history = [("failed", GO_TWO), ("failed", GO_TWO)]
    d = should_escalate(history)
    assert d["choice"] is True
    assert d["confidence"] == 0.7


def test_should_escalate_go_different():
    """Different Go test failures do not escalate."""
    # First sig: "TestFoo"
    # Second sig: "TestBar"
    # Different → no escalate
    # Expected: choice False
    d = should_escalate([("failed", GO_SINGLE), ("failed", "--- FAIL: TestBar (0.02s)\n")])
    assert d["choice"] is False
    assert d["confidence"] == 0.6
