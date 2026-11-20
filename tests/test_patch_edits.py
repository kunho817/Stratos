"""Tests for task patch_edits (P8, 2026-11-20): SEARCH/REPLACE edit blocks for existing files.
Experiment (scratchpad edit_eval.py, 10 past tasks on 580-680 line files, one run each): whole files passed 7/10
(Tiel 0/3 - two cut off at its 6000-token limit), edit blocks 8/10 with 0 SEARCH mismatches, about 6.6 times fewer
tokens (97k -> 14.7k) and 3.3 times faster (1180 s -> 356 s).

A block, inside a FILE section (also when the section wraps it in a ``` fence):
    <<<<<<< SEARCH
    <lines copied from the current file>
    =======
    <replacement lines>
    >>>>>>> REPLACE
patch.parse_edits(text, allowed=None) -> [(path, [(search, replace), ...])] in answer order, one entry per FILE
section that holds at least one block; search and replace are the text between the markers without the newline
before "=======" / ">>>>>>> REPLACE" (an empty REPLACE deletes the lines). allowed works as in parse_files. A path met
twice gets its blocks appended to its first entry.

patch.EditMismatch(Exception) with attributes path, search, found (how many times SEARCH occurs), closest (the
1-based line number and text of the file line most similar to SEARCH's first non-empty line, as "line N: <text>", or
"" when the file does not exist) and a str() of f"{path}: the SEARCH text was found {found} times (it must be found
exactly once){'; the closest line is ' + closest if closest else ''}".

patch.render_edits(root, edits) -> [(path, new_text)]: applies each file's blocks in order to the file's current text
(each block to the result of the ones before); a file that does not exist -> EditMismatch with found 0 and
closest ""; a SEARCH found 0 or 2+ times -> EditMismatch. Nothing is written."""
import pytest

from stratos import patch

SRC = "def a():\n    return 1\n\n\ndef b():\n    return 2\n\n\ndef c():\n    return 2\n"


def edit(path, *blocks, fence=False):
    body = "".join(f"<<<<<<< SEARCH\n{s}\n=======\n{r}\n>>>>>>> REPLACE\n" for s, r in blocks)
    if fence:
        body = "```python\n" + body + "```\n"
    return f"FILE: {path}\n{body}"


def test_parse_edits():
    text = ("Here are the changes.\n" + edit("pkg/m.py", ("    return 1", "    return 10"))
            + edit("pkg/n.py", ("x = 1", "x = 2"), ("y = 1", ""), fence=True)
            + "FILE: pkg/new.py\n```python\nZ = 3\n```\n"
            + edit("pkg/m.py", ("def b():", "def bb():")))
    assert patch.parse_edits(text) == [
        ("pkg/m.py", [("    return 1", "    return 10"), ("def b():", "def bb():")]),
        ("pkg/n.py", [("x = 1", "x = 2"), ("y = 1", "")]),
    ]
    assert patch.parse_edits(text, allowed=["pkg/n.py"]) == [("pkg/n.py", [("x = 1", "x = 2"), ("y = 1", "")])]
    assert patch.parse_edits("FILE: pkg/new.py\n```python\nZ = 3\n```\n") == []


def test_render_edits_in_order(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text(SRC, encoding="utf-8")
    out = patch.render_edits(tmp_path, [("pkg/m.py", [("def a():\n    return 1", "def a():\n    return 10"),
                                                     ("return 10", "return 11")])])
    assert out == [("pkg/m.py", SRC.replace("return 1\n", "return 11\n", 1))]
    assert (tmp_path / "pkg" / "m.py").read_text(encoding="utf-8") == SRC  # nothing written


def test_mismatch_not_found_gives_the_closest_line(tmp_path):
    (tmp_path / "m.py").write_text(SRC, encoding="utf-8")
    with pytest.raises(patch.EditMismatch) as e:
        patch.render_edits(tmp_path, [("m.py", [("def b(x):\n    return 2", "def b(x):\n    return 3")])])
    err = e.value
    assert (err.path, err.found) == ("m.py", 0)
    assert err.closest == "line 5: def b():"
    assert str(err) == ("m.py: the SEARCH text was found 0 times (it must be found exactly once); the closest line is "
                        "line 5: def b():")


def test_mismatch_found_twice(tmp_path):
    (tmp_path / "m.py").write_text(SRC, encoding="utf-8")
    with pytest.raises(patch.EditMismatch) as e:
        patch.render_edits(tmp_path, [("m.py", [("    return 2", "    return 3")])])
    assert e.value.found == 2


def test_mismatch_for_a_missing_file(tmp_path):
    with pytest.raises(patch.EditMismatch) as e:
        patch.render_edits(tmp_path, [("gone.py", [("a", "b")])])
    assert (e.value.found, e.value.closest) == (0, "")
    assert str(e.value) == "gone.py: the SEARCH text was found 0 times (it must be found exactly once)"
