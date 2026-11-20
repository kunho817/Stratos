"""Tests for task read_answer (P13, 2026-11-20): loop._judge, refcheck.check and patch.answer_files each read an answer
the same way (parse_edits, parse_files for the paths without edits, render_edits, catch EditMismatch) - three copies.

patch.read_answer(root, text, allowed=None) -> dict with
  "edits": parse_edits(text, allowed), "whole": the whole-file blocks for paths with no edit blocks,
  "files": render_edits(root, edits) + whole, or None when the edits do not apply, and
  "error": the EditMismatch, or None.
patch.answer_files(root, text, allowed) returns read_answer's "files", or only "whole" on an error (as now).
loop._judge and refcheck.check call read_answer and no longer call parse_edits / parse_files / render_edits
themselves. Their results and messages stay exactly as they are."""
import inspect

from stratos import loop, patch, refcheck

EDIT = "FILE: pkg/a.py\n<<<<<<< SEARCH\n    return 1\n=======\n    return 2\n>>>>>>> REPLACE\n"
NEW = "FILE: pkg/b.py\n```python\nX = 1\n```\n"


def setup(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    return tmp_path


def test_read_answer(tmp_path):
    root = setup(tmp_path)
    r = patch.read_answer(root, EDIT + NEW)
    assert r["edits"] == [("pkg/a.py", [("    return 1", "    return 2")])]
    assert r["whole"] == [("pkg/b.py", "X = 1\n")]
    assert r["files"] == [("pkg/a.py", "def f():\n    return 2\n"), ("pkg/b.py", "X = 1\n")] and r["error"] is None
    bad = patch.read_answer(root, EDIT.replace("return 1\n=", "return 9\n=") + NEW)
    assert bad["files"] is None and isinstance(bad["error"], patch.EditMismatch)
    assert bad["whole"] == [("pkg/b.py", "X = 1\n")]


def test_one_reader():
    for fn in (loop._judge, refcheck.check):
        src = inspect.getsource(fn)
        assert "patch.read_answer(" in src
        for old in ("patch.parse_edits(", "patch.parse_files(", "patch.render_edits("):
            assert old not in src, (fn.__name__, old)
    assert "read_answer(" in inspect.getsource(patch.answer_files)
