"""Tests for task partial_file (P9, 2026-11-20, found in T195): Tiel sent a piece of addcheck.py (the changed part,
indented) as the whole file; it failed as "syntax_error: line 2: unexpected indent" twice, and the hint did not say
what was wrong. Two cases are now named mechanically in loop.check_answer, before the dropped-definitions check:

1. "partial_file": a whole-file block (not an edit) for a file that exists, has at least 20 lines, and the new text
   has fewer than half its lines -> detail
   f"{path}: you sent {new} lines as the whole file, but the file has {old}. Send only the changes as SEARCH/REPLACE
   edit blocks (each SEARCH copied exactly from the file), or the whole file with everything in it."
   (one line per such file, joined by "\\n"); nothing is written and no test runs. A new file or a short file is
   never partial.
2. "no_files" for an answer that has a line with "SEARCH" or "REPLACE" between marker characters but no usable
   block: the detail is "Your edit blocks could not be read. Each one must be exactly:\\nFILE: <path>\\n<<<<<<< SEARCH\\n
   <lines copied from the file>\\n=======\\n<the new lines>\\n>>>>>>> REPLACE" (the plain "no FILE blocks" detail
   otherwise)."""
from stratos import loop

TASK = {"id": "T1", "title": "t", "goal": "g", "files": ["pkg/a.py", "pkg/new.py"], "protected": [],
        "tests": ["tests/x.py"]}
LONG = "".join(f"def f{i}():\n    return {i}\n\n\n" for i in range(10))  # 40 lines


def setup(tmp_path, text=LONG):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text(text, encoding="utf-8")
    return tmp_path


def test_a_piece_sent_as_the_whole_file(tmp_path):
    wt = setup(tmp_path)
    answer = "FILE: pkg/a.py\n```python\n    return 99\n\n\ndef g():\n    pass\n```\n"
    result, detail = loop.check_answer(TASK, wt, answer)
    assert result == "partial_file"
    assert detail == ("pkg/a.py: you sent 5 lines as the whole file, but the file has 40. Send only the changes as "
                      "SEARCH/REPLACE edit blocks (each SEARCH copied exactly from the file), or the whole file with "
                      "everything in it.")
    assert (wt / "pkg" / "a.py").read_text(encoding="utf-8") == LONG


def test_new_and_short_files_are_not_partial(tmp_path):
    wt = setup(tmp_path, "X = 1\nY = 2\n")
    answer = "FILE: pkg/a.py\n```python\nX = 1\n```\nFILE: pkg/new.py\n```python\nZ = 1\n```\n"
    assert loop.check_answer(TASK, wt, answer)[0] != "partial_file"


def test_unreadable_edit_blocks_get_the_format(tmp_path):
    wt = setup(tmp_path)
    answer = "FILE: pkg/a.py\n<<<<<<< SEARCH\n    return 1\n>>>>>>> REPLACE\n"
    result, detail = loop.check_answer(TASK, wt, answer)
    assert result == "no_files"
    assert detail == ("Your edit blocks could not be read. Each one must be exactly:\nFILE: <path>\n<<<<<<< SEARCH\n"
                      "<lines copied from the file>\n=======\n<the new lines>\n>>>>>>> REPLACE")


def test_plain_no_files_unchanged(tmp_path):
    wt = setup(tmp_path)
    assert loop.check_answer(TASK, wt, "I would change f1.") == (
        "no_files", "the answer held no FILE blocks for the task's files")
