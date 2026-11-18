"""Tests for summarize_output(out) in stratos/verify.py.

summarize_output(out) -> str
    Parse TAP output. For every "not ok <n> - <name>" line (including indented subtests),
    include that line plus up to 8 lines from its YAML block that contain
    "error:", "expected:", "actual:", "location:". Then append the
    "# tests", "# pass", "# fail" summary lines. Return out unchanged when
    no "not ok" lines are found."""
from stratos.verify import summarize_output


SIMPLE_FAIL = """\
ok 1 - test_a
not ok 2 - test_b
  ---
  error: assertion failed
  expected: 3
  actual: 2
  location: tests/test_x.py:10
  ---
ok 3 - test_c
# tests 3
# pass 2
# fail 1
"""

def test_simple_not_ok_with_yaml_block():
    out = summarize_output(SIMPLE_FAIL)
    lines = out.splitlines()
    # The "not ok" line must be present
    assert "not ok 2 - test_b" in lines
    # YAML keyword lines must be present
    assert "  error: assertion failed" in out
    assert "  expected: 3" in out
    assert "  actual: 2" in out
    assert "  location: tests/test_x.py:10" in out
    # The ok lines are NOT included
    assert "ok 1 - test_a" not in out
    assert "ok 3 - test_c" not in out
    # Summary lines must be present
    assert "# tests 3" in out
    assert "# pass 2" in out
    assert "# fail 1" in out


def test_no_not_ok_returns_unchanged():
    out = "ok 1 - a\nok 2 - b\n# tests 2\n# pass 2\n# fail 0\n"
    assert summarize_output(out) == out


def test_indented_subtests():
    tap = """\
not ok 1 - outer
  not ok 2 - inner
    ---
    error: boom
    expected: 5
    actual: 4
    location: x.py:1
    ---
  ok 3 - sub_ok
ok 4 - top_ok
# tests 4
# pass 2
# fail 2
"""
    out = summarize_output(tap)
    assert "not ok 1 - outer" in out
    assert "not ok 2 - inner" in out
    # indented YAML lines preserved
    assert "    error: boom" in out
    assert "    expected: 5" in out
    assert "    actual: 4" in out
    assert "    location: x.py:1" in out
    # ok lines excluded
    assert "ok 3 - sub_ok" not in out
    assert "ok 4 - top_ok" not in out
    # summary appended
    assert "# fail 2" in out


def test_yaml_block_truncates_to_8_matching_lines():
    # A YAML block with more than 8 lines containing keywords
    yaml_block = "\n".join(
        f"  key{i}: val{i}" for i in range(12)
    )
    # Add lines that match keywords
    matching = "\n".join(
        f"  {kw} val" for kw in ["error", "expected", "actual", "location"]
    )
    tap = f"not ok 1 - x\n  ---\n{matching}\n{yaml_block}\n  ---\nok 2 - y\n# tests 2\n# pass 1\n# fail 1\n"
    out = summarize_output(tap)
    # Count lines in the YAML section that contain the keywords
    yaml_lines = [l for l in out.splitlines() if
                  any(k in l for k in ("error:", "expected:", "actual:", "location:"))]
    # At most 8 matching keyword lines per YAML block
    assert len(yaml_lines) <= 8


def test_yaml_lines_without_keywords_are_skipped():
    tap = """\
not ok 1 - a
  ---
  type: assertion
  file: x.py
  line: 10
  error: boom
  ---
# tests 1
# pass 0
# fail 1
"""
    out = summarize_output(tap)
    assert "error: boom" in out
    # lines without the four keywords are not included
    assert "type: assertion" not in out
    assert "file: x.py" not in out
    assert "line: 10" not in out


def test_multiple_not_ok_lines():
    tap = """\
not ok 1 - a
  ---
  error: e1
  expected: x
  ---
not ok 2 - b
  ---
  actual: y
  location: z.py:3
  ---
ok 3 - c
# tests 3
# pass 1
# fail 2
"""
    out = summarize_output(tap)
    assert "not ok 1 - a" in out
    assert "not ok 2 - b" in out
    assert "error: e1" in out
    assert "expected: x" in out
    assert "actual: y" in out
    assert "location: z.py:3" in out
    assert "# fail 2" in out


def test_not_ok_without_yaml_block():
    # "not ok" line with no YAML block follows
    tap = "not ok 1 - a\nok 2 - b\n# tests 2\n# pass 1\n# fail 1\n"
    out = summarize_output(tap)
    assert "not ok 1 - a" in out
    # summary lines still appended
    assert "# tests 2" in out
    assert "# pass 1" in out
    assert "# fail 1" in out


def test_empty_output():
    assert summarize_output("") == ""


def test_only_summary_lines_no_not_ok():
    out = "# tests 5\n# pass 5\n# fail 0\n"
    assert summarize_output(out) == out


def test_not_ok_line_with_leading_spaces_pattern():
    # Indented "not ok" (subtest)
    tap = """\
ok 1 - top
  not ok 2 - sub
    ---
    error: deep
    expected: 1
    actual: 2
    location: a/b.py:99
    ---
ok 3 - top2
# tests 3
# pass 2
# fail 1
"""
    out = summarize_output(tap)
    assert "not ok 2 - sub" in out
    assert "    error: deep" in out
    assert "    location: a/b.py:99" in out
    assert "# fail 1" in out


def test_summary_lines_present_at_end():
    tap = """\
not ok 1 - a
  ---
  error: x
  ---
# tests 4
# pass 3
# fail 1
"""
    out = summarize_output(tap)
    lines = out.strip().splitlines()
    # The last three lines should be the summary
    assert lines[-3] == "# tests 4"
    assert lines[-2] == "# pass 3"
    assert lines[-1] == "# fail 1"


def test_yaml_block_delimiters_not_in_output():
    tap = """\
not ok 1 - a
  ---
  error: e
  ---
# tests 1
# pass 0
# fail 1
"""
    out = summarize_output(tap)
    # The --- delimiters should not appear
    assert "  ---" not in out
    assert "---" not in out


def test_out_with_trailing_newlines():
    tap = "not ok 1 - a\n  ---\n  error: z\n  ---\n# tests 1\n# pass 0\n# fail 1\n\n"
    out = summarize_output(tap)
    assert "not ok 1 - a" in out
    assert "error: z" in out
    assert "# fail 1" in out
