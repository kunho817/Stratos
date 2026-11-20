"""Tests for task cutoff_everywhere (P9, 2026-11-20, nit from P8): an answer cut off at the length limit gets the note
"Your answer was cut off: ..." before its detail - but an edit_mismatch (a cut-off answer often ends inside a SEARCH
block) returned early and skipped it.

loop.check_answer(task, wt, text, finish="length"): every result other than "passed" - edit_mismatch included - has a
detail that starts with "Your answer was cut off: it reached the length limit." Without finish="length" the
edit_mismatch detail is as before.
Also: stratos/refcheck.py imports from stratos in one line (T194 left two)."""
from pathlib import Path

from stratos import loop

TASK = {"id": "T1", "title": "t", "goal": "g", "files": ["pkg/a.py"], "protected": [], "tests": ["tests/x.py"]}
BAD = "FILE: pkg/a.py\n<<<<<<< SEARCH\nnot in the file\n=======\nX = 2\n>>>>>>> REPLACE\n"


def setup(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("X = 1\n", encoding="utf-8")
    return tmp_path


def test_a_cut_off_mismatch_gets_the_note(tmp_path):
    result, detail = loop.check_answer(TASK, setup(tmp_path), BAD, finish="length")
    assert result == "edit_mismatch"
    assert detail.startswith("Your answer was cut off: it reached the length limit.")
    assert "the SEARCH text was found 0 times" in detail


def test_without_cut_off_no_note(tmp_path):
    result, detail = loop.check_answer(TASK, setup(tmp_path), BAD)
    assert result == "edit_mismatch" and detail.startswith("pkg/a.py: the SEARCH text was found 0 times")


def test_refcheck_has_one_stratos_import_line():
    src = (Path(__file__).parent.parent / "stratos" / "refcheck.py").read_text(encoding="utf-8")
    assert sum(1 for line in src.splitlines() if line.startswith("from stratos import")) == 1
