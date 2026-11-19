"""Tests for task tap_values (P2, 2026-11-20, BACKLOG item 13): summarize_output keeps the multi-line values of
"error:", "expected:" and "actual:" in a TAP YAML block. Before, only the key lines were kept, so a failing
deepStrictEqual showed "expected:" and "actual:" with nothing after them (Lumen T001: the coder could not see
what was expected and failed twice).

Rules, on top of the old ones (tests/test_verify_summary.py):
- a YAML block starts at the line "---" after a "not ok" line and ends at a line whose stripped text is "---" or
  "..." (node's own TAP ends blocks with "...");
- a kept key line (one of error:, expected:, actual:, location:) whose value after the colon is empty or one of
  "|", "|-", ">", ">-" is followed by its value lines: the next lines indented more than the key line (blank lines
  inside count as part of it), at most 20 per key;
- lines of other keys (stack: |- and its lines, code:, name:, operator:, duration_ms:) are still left out."""
from stratos.verify import summarize_output

NODE_TAP = """TAP version 13
# Subtest: arr
not ok 1 - arr
  ---
  duration_ms: 1.8693
  type: 'test'
  location: 'C:\\\\x\\\\t.test.mjs:3:1'
  failureType: 'testCodeFailure'
  error: |-
    Expected values to be strictly deep-equal:
    + actual - expected

      [
        {
    +     x: 3,
    -     x: 9,
          y: 4
        }
      ]

  code: 'ERR_ASSERTION'
  name: 'AssertionError'
  expected:
    0:
      x: 9
      y: 4
  actual:
    0:
      x: 3
      y: 4
  operator: 'deepStrictEqual'
  stack: |-
    TestContext.<anonymous> (file:///C:/x/t.test.mjs:3:28)
    Test.runInAsyncScope (node:async_hooks:214:14)
  ...
# Subtest: num
not ok 2 - num
  ---
  duration_ms: 0.276
  error: |-
    Expected values to be strictly equal:

    2 !== 3

  expected: 3
  actual: 2
  stack: |-
    TestContext.<anonymous> (file:///C:/x/t.test.mjs:4:28)
  ...
1..2
# tests 2
# pass 0
# fail 2
"""


def test_multi_line_values_are_kept():
    out = summarize_output(NODE_TAP)
    lines = out.splitlines()
    i = lines.index("  expected:")
    assert lines[i + 1:i + 4] == ["    0:", "      x: 9", "      y: 4"]
    j = lines.index("  actual:")
    assert lines[j + 1:j + 4] == ["    0:", "      x: 3", "      y: 4"]
    assert "    +     x: 3," in lines and "    -     x: 9," in lines
    assert "    2 !== 3" in lines


def test_other_keys_and_the_stack_are_left_out():
    out = summarize_output(NODE_TAP)
    assert "TestContext" not in out and "runInAsyncScope" not in out
    assert "operator:" not in out and "duration_ms" not in out and "ERR_ASSERTION" not in out


def test_blocks_end_at_dots_and_single_line_values_stay_single():
    out = summarize_output(NODE_TAP)
    lines = out.splitlines()
    assert "not ok 2 - num" in lines
    k = lines.index("not ok 2 - num")
    after = lines[k + 1:]
    assert "  expected: 3" in after and "  actual: 2" in after
    assert out.rstrip().endswith("# fail 2")


def test_at_most_20_value_lines_per_key():
    value = "\n".join(f"    line {n}" for n in range(30))
    tap = f"not ok 1 - big\n  ---\n  actual: |-\n{value}\n  expected: 1\n  ...\n# tests 1\n# pass 0\n# fail 1\n"
    out = summarize_output(tap)
    assert "    line 19" in out and "    line 20" not in out
    assert "  expected: 1" in out
