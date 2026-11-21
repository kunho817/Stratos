"""Tests for patch."""
import pytest

from stratos import patch


ANSWER = """Here you go.
FILE: stratos/a.py
```python
X = 1
```
FILE: `docs/b.md`
```
hello
```
"""


def test_parse_files_reads_every_block():
    assert patch.parse_files(ANSWER) == [("stratos/a.py", "X = 1\n"), ("docs/b.md", "hello\n")]


def test_parse_files_without_blocks():
    assert patch.parse_files("no files here") == []


@pytest.mark.parametrize("path", ["../x.py", "C:/x.py", "/etc/x.py", "a/../../x.py", "stratos/x.exe"])
def test_bad_paths_are_refused(path):
    with pytest.raises(patch.PatchRefused):
        patch.check_path(path, [])


def test_protected_file_is_refused(tmp_path):
    with pytest.raises(patch.PatchRefused):
        patch.apply_files(tmp_path, [("tests/test_x.py", "x")], ["tests/test_x.py"])
    assert not (tmp_path / "tests").exists()


def test_nothing_written_when_one_path_is_bad(tmp_path):
    with pytest.raises(patch.PatchRefused):
        patch.apply_files(tmp_path, [("ok.py", "x"), ("../bad.py", "y")], [])
    assert not (tmp_path / "ok.py").exists()


NESTED = '''FILE: stratos/review.py
```python
PROMPT = """Answer inside a json block:
```json
{"verdict": "approve"}
```
"""
X = 1
```
'''


def test_content_may_hold_fences():
    assert patch.parse_files(NESTED) == [("stratos/review.py",
                                          'PROMPT = """Answer inside a json block:\n```json\n{"verdict": "approve"}\n```\n"""\nX = 1\n')]


SELF = '''FILE: stratos/context.py
```python
SYSTEM = """Answer like this:

FILE: relative/path.py
```python
<code>
```
"""
```
'''


def test_only_the_tasks_files_count_as_headers():
    files = patch.parse_files(SELF, allowed=["stratos/context.py"])
    assert [p for p, _ in files] == ["stratos/context.py"]
    assert "FILE: relative/path.py" in files[0][1] and files[0][1].rstrip().endswith('"""')


def test_header_on_the_first_line_inside_the_fence():
    text = "Here:\n```python\nFILE: stratos/a.py\nX = 1\n```\n```python\nFILE: stratos/b.py\nY = 2\n```\n"
    assert patch.parse_files(text, allowed=["stratos/a.py", "stratos/b.py"]) == [("stratos/a.py", "X = 1\n"),
                                                                                  ("stratos/b.py", "Y = 2\n")]


# T022: a missing header is forgiven only when nothing else is possible: no header anywhere, exactly one allowed
# file, exactly one code block (exactly two fence lines). Tiel answered T009 and T019 that way.

def test_a_lone_block_belongs_to_the_only_file():
    text = "Here is the updated module:\n```python\nX = 1\n\ndef f():\n    return X\n```\nDone."
    assert patch.parse_files(text, allowed=["stratos/a.py"]) == [("stratos/a.py", "X = 1\n\ndef f():\n    return X\n")]


def test_no_guess_with_two_blocks():
    text = "```python\nX = 1\n```\nUsage:\n```python\nprint(X)\n```\n"
    assert patch.parse_files(text, allowed=["stratos/a.py"]) == []


def test_no_guess_with_two_allowed_files():
    assert patch.parse_files("```python\nX = 1\n```\n", allowed=["stratos/a.py", "stratos/b.py"]) == []


def test_no_guess_without_an_allowed_list():
    assert patch.parse_files("```python\nX = 1\n```\n") == []


def test_a_header_still_wins():
    text = "FILE: stratos/a.py\n```python\nX = 2\n```\n"
    assert patch.parse_files(text, allowed=["stratos/a.py"]) == [("stratos/a.py", "X = 2\n")]


def test_unclosed_block_is_ignored():
    assert patch.parse_files("FILE: a.py\n```python\nx = 1\n") == []


def test_file_outside_the_task_is_refused(tmp_path):
    with pytest.raises(patch.PatchRefused):
        patch.apply_files(tmp_path, [("stratos/other.py", "x")], [], allowed=["stratos/mine.py"])


def test_an_empty_file_is_refused_and_nothing_is_written(tmp_path):
    with pytest.raises(patch.PatchRefused):
        patch.apply_files(tmp_path, [("ok.py", "X = 1\n"), ("stratos/loop.py", "\n  \n")], [])
    assert not (tmp_path / "ok.py").exists()


def test_apply_writes_files(tmp_path):
    assert patch.apply_files(tmp_path, [("pkg/m.py", "Y = 2\n")], []) == ["pkg/m.py"]
    assert (tmp_path / "pkg" / "m.py").read_text(encoding="utf-8") == "Y = 2\n"


# T025: the only allowed file is a Python file whose content holds ``` fences or "FILE:" lines (patch.py's own
# docstring does), and the answer has no header naming that file. Tiel answered T022's attempt 3 that way and the
# whole answer was lost. Then the block runs from the first fence line to the LAST bare ``` line, and counts only
# when the allowed file ends in .py and that content parses as Python (ast.parse). The T022 rule (exactly one code
# block, no header anywhere) still applies to every file type. A header naming the allowed file still wins.

MODULE_WITH_FENCES = '''"""Docs.

    FILE: stratos/report.py
    ```python
    ...
    ```
"""
X = 1
'''


def test_a_python_file_holding_fences_is_saved():
    text = "Here is the module:\n```python\n" + MODULE_WITH_FENCES + "```\n"
    assert patch.parse_files(text, allowed=["stratos/patch.py"]) == [("stratos/patch.py", MODULE_WITH_FENCES)]


def test_the_answer_may_end_right_after_the_closing_fence():
    text = "```python\n" + MODULE_WITH_FENCES + "```"
    assert patch.parse_files(text, allowed=["stratos/patch.py"]) == [("stratos/patch.py", MODULE_WITH_FENCES)]


def test_no_guess_when_the_joined_content_is_not_python():
    text = "```python\nX = 1\n```\nThen call it:\n```python\nprint(X)\n```\n"
    assert patch.parse_files(text, allowed=["stratos/a.py"]) == []


def test_no_guess_for_a_file_that_is_not_python():
    text = "```markdown\n# Title\n\n```\ncode\n```\n\nend\n```\n"
    assert patch.parse_files(text, allowed=["docs/a.md"]) == []


def test_no_guess_with_two_allowed_files_even_if_it_parses():
    text = "```python\n" + MODULE_WITH_FENCES + "```\n"
    assert patch.parse_files(text, allowed=["stratos/a.py", "stratos/b.py"]) == []


def test_a_header_naming_the_file_still_wins_over_the_fallback():
    text = "FILE: stratos/patch.py\n```python\n" + MODULE_WITH_FENCES + "```\n"
    assert patch.parse_files(text, allowed=["stratos/patch.py"]) == [("stratos/patch.py", MODULE_WITH_FENCES)]


# ---- was test_patch_answer_files.py ----
# Tests for task answer_files (P10, 2026-11-20): triage saw a failed answer's code through patch.parse_files only,
# so an answer made of edit blocks (most answers since P8) reached triage as "Code files: (none)".
#
# patch.answer_files(root, text, allowed=None) -> [(path, new_text)]: the files an answer would write - its edit
# blocks rendered against the files under root (patch.render_edits), then its whole-file blocks for paths that have
# no edit blocks; when the edits do not apply (EditMismatch), only the whole-file blocks. Nothing is written.
# loop.run_task gives triage patch.answer_files(wt, <the last failed answer>, task["files"] or None) as code_files.


OLD = "def f():\n    return 1\n"


EDIT = "FILE: pkg/a.py\n<<<<<<< SEARCH\n    return 1\n=======\n    return 2\n>>>>>>> REPLACE\n"


NEW = "FILE: pkg/b.py\n```python\nX = 1\n```\n"


def setup(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text(OLD, encoding="utf-8")
    return tmp_path


def test_edits_rendered_then_whole_files(tmp_path):
    root = setup(tmp_path)
    assert patch.answer_files(root, EDIT + NEW) == [("pkg/a.py", "def f():\n    return 2\n"), ("pkg/b.py", "X = 1\n")]
    assert (root / "pkg" / "a.py").read_text(encoding="utf-8") == OLD


def test_a_mismatch_keeps_the_whole_files(tmp_path):
    root = setup(tmp_path)
    bad = EDIT.replace("    return 1\n=", "    return 9\n=")
    assert patch.answer_files(root, bad + NEW) == [("pkg/b.py", "X = 1\n")]


def test_loop_gives_triage_the_rendered_files():
    import inspect

    from stratos import loop
    src = inspect.getsource(loop)
    assert "code_files = patch.answer_files(wt, last_failed_text, task[\"files\"] or None)" in src
    assert "code_files = patch.parse_files(last_failed_text" not in src


def test_allowed(tmp_path):
    root = setup(tmp_path)
    assert patch.answer_files(root, EDIT + NEW, ["pkg/b.py"]) == [("pkg/b.py", "X = 1\n")]


# ---- was test_patch_edits.py ----
# Tests for task patch_edits (P8, 2026-11-20): SEARCH/REPLACE edit blocks for existing files.
# Experiment (scratchpad edit_eval.py, 10 past tasks on 580-680 line files, one run each): whole files passed 7/10
# (Tiel 0/3 - two cut off at its 6000-token limit), edit blocks 8/10 with 0 SEARCH mismatches, about 6.6 times fewer
# tokens (97k -> 14.7k) and 3.3 times faster (1180 s -> 356 s).
#
# A block, inside a FILE section (also when the section wraps it in a ``` fence):
#     <<<<<<< SEARCH
#     <lines copied from the current file>
#     =======
#     <replacement lines>
#     >>>>>>> REPLACE
# patch.parse_edits(text, allowed=None) -> [(path, [(search, replace), ...])] in answer order, one entry per FILE
# section that holds at least one block; search and replace are the text between the markers without the newline
# before "=======" / ">>>>>>> REPLACE" (an empty REPLACE deletes the lines). allowed works as in parse_files. A path met
# twice gets its blocks appended to its first entry.
#
# patch.EditMismatch(Exception) with attributes path, search, found (how many times SEARCH occurs), closest (the
# 1-based line number and text of the file line most similar to SEARCH's first non-empty line, as "line N: <text>", or
# "" when the file does not exist) and a str() of f"{path}: the SEARCH text was found {found} times (it must be found
# exactly once){'; the closest line is ' + closest if closest else ''}".
#
# patch.render_edits(root, edits) -> [(path, new_text)]: applies each file's blocks in order to the file's current text
# (each block to the result of the ones before); a file that does not exist -> EditMismatch with found 0 and
# closest ""; a SEARCH found 0 or 2+ times -> EditMismatch. Nothing is written.


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


# ---- was test_patch_edits_order.py ----
# Tests for task edits_order (P9, 2026-11-20, found by Claude reading T197): _read_blocks kept looking for a divider
# after it had met the end line, so a block without a divider swallowed the next block and gave a wrong edit. Also
# (found in T198): marker text inside a code line must not split a block - only whole lines are markers.
#
# patch.parse_edits: a block ends at its first end line; when no divider came before it, the block is not used and the
# reading goes on after that end line.


def test_a_block_without_divider_does_not_swallow_the_next():
    text = ("FILE: pkg/a.py\n<<<<<<< SEARCH\na = 1\n>>>>>>> REPLACE\n"
            "<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE\n")
    assert patch.parse_edits(text) == [("pkg/a.py", [("x = 1", "x = 2")])]


def test_markers_inside_a_code_line_are_text():
    line = '    msg = "FILE: <path>\\n<<<<<<< SEARCH\\n<old>\\n=======\\n<new>\\n>>>>>>> REPLACE"'
    text = f"FILE: pkg/a.py\n<<<<<<< SEARCH\n    msg = ''\n=======\n{line}\n>>>>>>> REPLACE\n"
    assert patch.parse_edits(text) == [("pkg/a.py", [("    msg = ''", line)])]


# ---- was test_patch_edits_tolerant.py ----
# Tests for task edits_tolerant (P9, 2026-11-20, found in T196): Tiel ended a block with "======= REPLACE" instead of
# ">>>>>>> REPLACE"; the block was not read, the answer counted as "no_files" twice, and the next model got no help.
# The markers are read mechanically and leniently, line by line.
#
# patch.parse_edits reads each FILE section line by line:
# - a block starts at a line that is, after strip(), 5 to 9 "<" then optional spaces then "SEARCH";
# - the divider is a line that is, after strip(), 5 to 9 "=";
# - the block ends at a line that is, after strip(), 5 to 9 of one of ">", "=", "<" then optional spaces then "REPLACE";
# - search = the lines between start and divider, replace = the lines between divider and end, each joined without
#   its last newline (as the old regex gave);
# - a block with a second divider line before its end, or with no divider or no end, is not used (it is malformed);
# - fence lines (```) outside blocks are ignored, as before. Answers the old regex read give the same result.


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
