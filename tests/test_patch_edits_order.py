"""Tests for task edits_order (P9, 2026-11-20, found by Claude reading T197): _read_blocks kept looking for a divider
after it had met the end line, so a block without a divider swallowed the next block and gave a wrong edit. Also
(found in T198): marker text inside a code line must not split a block - only whole lines are markers.

patch.parse_edits: a block ends at its first end line; when no divider came before it, the block is not used and the
reading goes on after that end line."""
from stratos import patch


def test_a_block_without_divider_does_not_swallow_the_next():
    text = ("FILE: pkg/a.py\n<<<<<<< SEARCH\na = 1\n>>>>>>> REPLACE\n"
            "<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE\n")
    assert patch.parse_edits(text) == [("pkg/a.py", [("x = 1", "x = 2")])]


def test_markers_inside_a_code_line_are_text():
    line = '    msg = "FILE: <path>\\n<<<<<<< SEARCH\\n<old>\\n=======\\n<new>\\n>>>>>>> REPLACE"'
    text = f"FILE: pkg/a.py\n<<<<<<< SEARCH\n    msg = ''\n=======\n{line}\n>>>>>>> REPLACE\n"
    assert patch.parse_edits(text) == [("pkg/a.py", [("    msg = ''", line)])]
