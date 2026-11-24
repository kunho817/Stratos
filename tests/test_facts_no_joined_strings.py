"""Tests for task facts-no-joined-strings: SYSTEM_A and SYSTEM_B each gain one line
"- Never join several values into one string (not 'flower:1' or 'e,n'): use a list such as ['flower', 1] instead."
placed immediately after their existing line
"- When the rules allow several answers for one input, the value lists every one of them (for example every rotation that fits), never only the first."
Nothing else changes in stratos/facts.py.

OUTDATED: none – existing tests check other lines and content unaffected by one added line.
"""

from stratos import facts

# The exact new line with single quotes as written in the task spec:
new_line = "- Never join several values into one string (not 'flower:1' or 'e,n'): use a list such as ['flower', 1] instead."

# The anchor line in both prompts that the new line must follow:
anchor = "- When the rules allow several answers for one input, the value lists every one of them (for example every rotation that fits), never only the first."


def test_system_a_has_no_joined_strings_line():
    # Expected: the exact new line appears in SYSTEM_A
    assert new_line in facts.SYSTEM_A


def test_system_b_has_no_joined_strings_line():
    # Expected: the exact new line appears in SYSTEM_B
    assert new_line in facts.SYSTEM_B


def test_system_a_new_line_immediately_after_anchor():
    # In SYSTEM_A the new line must come right after the anchor line.
    # Find anchor position in lines list.
    lines = facts.SYSTEM_A.split("\n")
    idx = [i for i, l in enumerate(lines) if anchor in l]
    # Expected: anchor appears exactly once
    assert len(idx) == 1
    # step: advance to the next non-empty line
    next_idx = idx[0] + 1
    while next_idx < len(lines) and lines[next_idx].strip() == "":
        next_idx += 1
    # Expected: that next non-empty line is the new_line
    assert new_line in lines[next_idx]


def test_system_b_new_line_immediately_after_anchor():
    # In SYSTEM_B the new line must come right after the anchor line.
    lines = facts.SYSTEM_B.split("\n")
    idx = [i for i, l in enumerate(lines) if anchor in l]
    # Expected: anchor appears exactly once
    assert len(idx) == 1
    # step: advance to the next non-empty line
    next_idx = idx[0] + 1
    while next_idx < len(lines) and lines[next_idx].strip() == "":
        next_idx += 1
    # Expected: that next non-empty line is the new_line
    assert new_line in lines[next_idx]


def test_new_line_has_single_quotes_exactly():
    # The line uses single quotes as written: 'flower:1', 'e,n', ['flower', 1].
    # Expected: 'flower:1' (with surrounding single quotes) is in the line
    assert "'flower:1'" in new_line
    # Expected: 'e,n' (with surrounding single quotes) is in the line
    assert "'e,n'" in new_line
    # Expected: ['flower', 1] (with surrounding single quotes on elements) is in the line
    assert "['flower', 1]" in new_line


def test_system_a_line_appears_exactly_once():
    # The new line must appear exactly once in SYSTEM_A.
    # Expected: count == 1
    assert facts.SYSTEM_A.count(new_line) == 1


def test_system_b_line_appears_exactly_once():
    # The new line must appear exactly once in SYSTEM_B.
    # Expected: count == 1
    assert facts.SYSTEM_B.count(new_line) == 1


def test_system_a_anchor_still_present():
    # The anchor line must not be removed from SYSTEM_A.
    # Expected: anchor in SYSTEM_A
    assert anchor in facts.SYSTEM_A


def test_system_b_anchor_still_present():
    # The anchor line must not be removed from SYSTEM_B.
    # Expected: anchor in SYSTEM_B
    assert anchor in facts.SYSTEM_B


def test_system_a_no_extra_changes():
    # After the new line, SYSTEM_A must still have the 400-input-keys line.
    # Expected: the 400 keys line is present
    assert "- At most 400 input keys in all across all facts." in facts.SYSTEM_A


def test_system_b_no_extra_changes():
    # After the new line, SYSTEM_B must still have the value-shape line.
    # Expected: the value-shape line is present
    assert "- Every value must have exactly the value shape given for its fact" in facts.SYSTEM_B


def test_new_line_identical_in_both():
    # The new line extracted from SYSTEM_A must equal the one extracted from SYSTEM_B.
    lines_a = facts.SYSTEM_A.split("\n")
    lines_b = facts.SYSTEM_B.split("\n")
    found_a = [l for l in lines_a if new_line in l]
    found_b = [l for l in lines_b if new_line in l]
    # Expected: exactly one occurrence in each
    assert len(found_a) == 1
    assert len(found_b) == 1
    # Expected: the lines are identical
    assert found_a[0] == found_b[0]


def test_new_line_forbids_joining():
    # The line's purpose: forbid joining values into one string; prescribe a list.
    # Expected: starts with "- Never"
    assert new_line.startswith("- Never")
    # Expected: contains "join"
    assert "join" in new_line
    # Expected: contains "list"
    assert "list" in new_line
    # Expected: contains "instead"
    assert "instead" in new_line
