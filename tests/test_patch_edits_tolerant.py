"""Tests for task edits_tolerant (P9, 2026-11-20, found in T196): Tiel ended a block with "======= REPLACE" instead of
">>>>>>> REPLACE"; the block was not read, the answer counted as "no_files" twice, and the next model got no help.
The markers are read mechanically and leniently, line by line.

patch.parse_edits reads each FILE section line by line:
- a block starts at a line that is, after strip(), 5 to 9 "<" then optional spaces then "SEARCH";
- the divider is a line that is, after strip(), 5 to 9 "=";
- the block ends at a line that is, after strip(), 5 to 9 of one of ">", "=", "<" then optional spaces then "REPLACE";
- search = the lines between start and divider, replace = the lines between divider and end, each joined without
  its last newline (as the old regex gave);
- a block with a second divider line before its end, or with no divider or no end, is not used (it is malformed);
- fence lines (```) outside blocks are ignored, as before. Answers the old regex read give the same result."""
from stratos import patch


def test_the_usual_markers_still_work():
    text = "FILE: pkg/a.py\n```\n<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE\n```\n"
    assert patch.parse_edits(text) == [("pkg/a.py", [("x = 1", "x = 2")])]


def test_lenient_end_and_counts():
    text = ("FILE: pkg/a.py\n<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n======= REPLACE\n"
            "<<<<<<<< SEARCH\n  y = 1\n  z = 1\n========\n  y = 2\n>>>>>>>>REPLACE\n")
    assert patch.parse_edits(text) == [("pkg/a.py", [("x = 1", "x = 2"), ("  y = 1\n  z = 1", "  y = 2")])]


def test_indented_markers():
    text = "FILE: pkg/a.py\n  <<<<<<< SEARCH\nx = 1\n  =======\nx = 2\n  >>>>>>> REPLACE\n"
    assert patch.parse_edits(text) == [("pkg/a.py", [("x = 1", "x = 2")])]


def test_malformed_blocks_are_not_used():
    two_dividers = "FILE: pkg/a.py\n<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n=======\nx = 3\n>>>>>>> REPLACE\n"
    assert patch.parse_edits(two_dividers) == []
    no_end = "FILE: pkg/a.py\n<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n"
    assert patch.parse_edits(no_end) == []


def test_empty_replace():
    text = "FILE: pkg/a.py\n<<<<<<< SEARCH\nx = 1\n=======\n>>>>>>> REPLACE\n"
    assert patch.parse_edits(text) == [("pkg/a.py", [("x = 1", "")])]
