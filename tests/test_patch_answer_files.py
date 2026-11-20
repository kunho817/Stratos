"""Tests for task answer_files (P10, 2026-11-20): triage saw a failed answer's code through patch.parse_files only,
so an answer made of edit blocks (most answers since P8) reached triage as "Code files: (none)".

patch.answer_files(root, text, allowed=None) -> [(path, new_text)]: the files an answer would write - its edit
blocks rendered against the files under root (patch.render_edits), then its whole-file blocks for paths that have
no edit blocks; when the edits do not apply (EditMismatch), only the whole-file blocks. Nothing is written.
loop.run_task gives triage patch.answer_files(wt, <the last failed answer>, task["files"] or None) as code_files."""
from stratos import patch

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
