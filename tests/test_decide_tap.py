"""Tests for TAP "not ok" line extraction in stratos/decide.py's _extract_ids.

The TAP format used by node's test runner produces lines like:
    not ok 1 - test_name
    not ok 2 - sub_name
with indentation for subtests:
        not ok 3 - nested_name
_only "not ok" lines are extracted; "ok" lines are ignored. The id is the name
after " - " (the part after the test number). Existing FAILED/ERROR handling
is unchanged. ids remain sorted and de-duplicated so that should_escalate
works identically for node's TAP output as for pytest output.
"""

from stratos.decide import _extract_ids, failure_signature, should_escalate


def test_extract_tap_not_ok_lines():
    detail = "not ok 1 - test_alpha\nnot ok 2 - test_beta\n"
    assert _extract_ids(detail) == ["test_alpha", "test_beta"]


def test_extract_tap_ok_lines_are_ignored():
    detail = "ok 1 - passing\nnot ok 2 - failing\nok 3 - also_passing\n"
    assert _extract_ids(detail) == ["failing"]


def test_extract_tap_indented_subtests():
    detail = "not ok 1 - parent\n    not ok 2 - child_one\n    not ok 3 - child_two\n"
    assert _extract_ids(detail) == ["child_one", "child_two", "parent"]


def test_extract_tap_deeply_indented():
    detail = "not ok 1 - outer\n        not ok 2 - deep_sub\n"
    assert _extract_ids(detail) == ["deep_sub", "outer"]


def test_extract_tap_with_extra_detail_after_name():
    detail = "not ok 1 - test_one - some extra annotation\nnot ok 2 - test_two\n"
    assert _extract_ids(detail) == ["test_one", "test_two"]


def test_extract_tap_de_duplicate():
    detail = "not ok 1 - test_alpha\nnot ok 2 - test_alpha\nnot ok 3 - test_beta\n"
    assert _extract_ids(detail) == ["test_alpha", "test_beta"]


def test_extract_tap_mixed_with_pytest():
    detail = (
        "FAILED tests/test_a.py::test_one - AssertionError\n"
        "not ok 2 - test_two\n"
        "not ok 1 - test_alpha\n"
        "ok 3 - passing\n"
        "ERROR tests/test_b.py - SyntaxError\n"
    )
    # pytest ids stay full node ids; sorted as strings ("test_" sorts before "tests")
    assert _extract_ids(detail) == [
        "test_alpha",
        "test_two",
        "tests/test_a.py::test_one",
        "tests/test_b.py",
    ]


def test_extract_tap_only_no_pytest():
    detail = "not ok 1 - node_test_a\nnot ok 2 - node_test_b\n"
    assert _extract_ids(detail) == ["node_test_a", "node_test_b"]


def test_extract_tap_number_not_in_id():
    detail = "not ok 42 - my_test_name\n"
    assert _extract_ids(detail) == ["my_test_name"]


def test_extract_tap_no_dash_no_name():
    # "not ok 5" without " - name" → no id extracted
    detail = "not ok 5\nnot ok 6 - has_name\n"
    assert _extract_ids(detail) == ["has_name"]


def test_failure_signature_tap():
    detail = "not ok 1 - test_a\nnot ok 2 - test_b\n"
    assert failure_signature("failed", detail) == "test_a,test_b"


def test_failure_signature_tap_single():
    detail = "not ok 1 - only_test\n"
    assert failure_signature("failed", detail) == "only_test"


def test_failure_signature_tap_indent():
    detail = "not ok 1 - parent\n    not ok 2 - child\n"
    assert failure_signature("failed", detail) == "child,parent"


def test_should_escalate_tap_repeated():
    tap = "not ok 1 - test_x\nnot ok 2 - test_y\n"
    history = [("failed", tap), ("failed", tap)]
    result = should_escalate(history)
    assert result["choice"] is True
    assert "test_x,test_y" in result["reason"]


def test_should_escalate_tap_different():
    tap1 = "not ok 1 - test_x\n"
    tap2 = "not ok 1 - test_y\n"
    history = [("failed", tap1), ("failed", tap2)]
    result = should_escalate(history)
    assert result["choice"] is False


def test_should_escalate_tap_subtests_repeated():
    tap = "not ok 1 - parent\n    not ok 2 - child\n"
    history = [("failed", tap), ("failed", tap)]
    result = should_escalate(history)
    assert result["choice"] is True


def test_should_escalate_pytest_and_tap_same_ids():
    # same logical test names extracted from both formats → escalate
    pytest_detail = "FAILED tests/test_x.py::test_alpha\n"
    tap_detail = "not ok 1 - test_alpha\n"
    # These produce different ids (pytest includes path), so they should NOT match
    history = [("failed", pytest_detail), ("failed", tap_detail)]
    result = should_escalate(history)
    # pytest id is "tests/test_x.py::test_alpha", TAP id is "test_alpha" → no match
    assert result["choice"] is False


def test_should_escalate_pytest_and_tap_not_matching():
    # Ensure TAP-only history escalates
    tap = "not ok 1 - alpha\nnot ok 2 - beta\n"
    history = [("failed", tap), ("failed", tap)]
    assert should_escalate(history)["choice"] is True


def test_extract_tap_ok_with_indented_ok():
    detail = "not ok 1 - parent\n    ok 2 - child_passing\n"
    assert _extract_ids(detail) == ["parent"]


def test_extract_tap_lines_at_start_of_detail():
    detail = "not ok 1 - first\nok 2 - second\nnot ok 3 - third\n"
    assert _extract_ids(detail) == ["first", "third"]
