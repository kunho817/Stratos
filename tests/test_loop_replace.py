"""Tests for task loop_replace: skip the partial-file check for paths in task["replace"].

In stratos/loop.py, _judge: the partial-file check (a whole-file block for a file that exists, has >= 20
lines, and the new content has fewer than half) skips every path present in task.get("replace", []).
A path in the replace list may be sent as a whole file shorter than half the existing file without
being refused as partial_file. A path NOT in replace keeps the partial-file refusal. Everything else
in _judge stays the same.

task["replace"] is a list of file-path strings, stored by Store.add_task(..., replace=()) when
non-empty (earlier task); _judge reads task.get("replace", []).
"""
from pathlib import Path

import pytest

from stratos import loop, patch, verify

# 40 lines of simple variable assignments (no top-level def/class, so dropped_definitions stays empty)
LONG = "\n".join(f"X{i} = {i}" for i in range(40)) + "\n"   # 40 lines
# 2 lines, no trailing newline: _answer wraps the body as ```python\n{body}\n``` so the parser keeps the
# content exactly as body (a trailing \n would add a blank line -> 3 lines, not 2). 2*2 = 4 < 40 -> partial.
SHORT = "X0 = 99\nY = 2"   # 2 lines; 2*2 = 4 < 40 -> partial without replace

TASK = {"id": "T1", "title": "t", "goal": "g", "files": ["pkg/a.py", "pkg/b.py", "pkg/c.py"],
        "protected": [], "tests": ["tests/x.py"]}


def _setup(tmp_path, monkeypatch):
    """Worktree with pkg/a.py and pkg/b.py at 40 lines; tests pass, no lint/check."""
    (tmp_path / "pkg").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pkg" / "a.py").write_text(LONG, encoding="utf-8")
    (tmp_path / "pkg" / "b.py").write_text(LONG, encoding="utf-8")
    monkeypatch.setattr(verify, "run_tests", lambda w, t: (True, "1 passed"))
    return tmp_path


def _answer(path, body):
    return f"FILE: {path}\n```python\n{body}\n```\n"


def test_replace_path_is_not_partial(tmp_path, monkeypatch):
    """pkg/a.py is in replace, 40 lines, answer sends 2 lines -> partial-file check skipped -> passed."""
    wt = _setup(tmp_path, monkeypatch)
    task = dict(TASK, replace=["pkg/a.py"])
    answer = _answer("pkg/a.py", SHORT)
    result, detail = loop.check_answer(task, wt, answer)
    # Step: pkg/a.py is in replace -> the partial-file check is skipped
    # Step: LONG has no top-level defs -> dropped_definitions is empty
    # Step: syntax ok, tests pass -> result is "passed"
    assert result == "passed"
    # Step: the short content was written to the file
    assert (wt / "pkg" / "a.py").read_text(encoding="utf-8") == SHORT + "\n"


def test_no_replace_key_still_partial(tmp_path, monkeypatch):
    """A task without "replace" -> task.get("replace", []) = [] -> partial-file fires as before."""
    wt = _setup(tmp_path, monkeypatch)
    # TASK has no "replace" key
    answer = _answer("pkg/a.py", SHORT)
    result, detail = loop.check_answer(TASK, wt, answer)
    # Step: 40 lines existing, 2 sent, 2*2 = 4 < 40 -> partial
    assert result == "partial_file"
    # Step: detail names the path
    assert "pkg/a.py" in detail
    # Step: nothing written
    assert (wt / "pkg" / "a.py").read_text(encoding="utf-8") == LONG


def test_empty_replace_list_is_the_same_as_no_key(tmp_path, monkeypatch):
    """replace=[] -> task.get("replace", []) = [] -> no paths skipped -> partial_file fires."""
    wt = _setup(tmp_path, monkeypatch)
    task = dict(TASK, replace=[])
    answer = _answer("pkg/a.py", SHORT)
    result, detail = loop.check_answer(task, wt, answer)
    # Step: empty list -> nothing to skip -> partial_file fires
    assert result == "partial_file"
    assert "pkg/a.py" in detail


def test_all_paths_in_replace_are_skipped(tmp_path, monkeypatch):
    """replace=["pkg/a.py","pkg/b.py"]: both files 40 lines, both sent as 2 lines -> both skipped -> passed."""
    wt = _setup(tmp_path, monkeypatch)
    task = dict(TASK, replace=["pkg/a.py", "pkg/b.py"])
    answer = _answer("pkg/a.py", SHORT) + _answer("pkg/b.py", SHORT)
    result, detail = loop.check_answer(task, wt, answer)
    # Step: both paths in replace -> partial-file check skipped for each
    # Step: 2*2 = 4 < 40 for each, but both are in replace
    assert result == "passed"
    # Step: both files were written
    assert (wt / "pkg" / "a.py").read_text(encoding="utf-8") == SHORT + "\n"
    assert (wt / "pkg" / "b.py").read_text(encoding="utf-8") == SHORT + "\n"


def test_one_in_replace_one_not(tmp_path, monkeypatch):
    """replace=["pkg/a.py"]: pkg/a.py skipped, pkg/b.py (not in replace) triggers partial_file."""
    wt = _setup(tmp_path, monkeypatch)
    task = dict(TASK, replace=["pkg/a.py"])
    answer = _answer("pkg/a.py", SHORT) + _answer("pkg/b.py", SHORT)
    result, detail = loop.check_answer(task, wt, answer)
    # Step: pkg/a.py is in replace -> skipped; pkg/b.py is not -> partial_file fires
    assert result == "partial_file"
    # Step: detail names only pkg/b.py
    assert "pkg/b.py" in detail
    # Step: pkg/a.py is NOT in the detail (its partial-file line was skipped)
    assert "pkg/a.py" not in detail
    # Step: partial_file returns before apply_files, so nothing is written
    assert (wt / "pkg" / "a.py").read_text(encoding="utf-8") == LONG
    assert (wt / "pkg" / "b.py").read_text(encoding="utf-8") == LONG


def test_replace_path_not_in_answer(tmp_path, monkeypatch):
    """replace=["pkg/c.py"] but the answer writes only pkg/a.py -> pkg/a.py is not in replace -> partial_file."""
    wt = _setup(tmp_path, monkeypatch)
    task = dict(TASK, replace=["pkg/c.py"])
    answer = _answer("pkg/a.py", SHORT)
    result, detail = loop.check_answer(task, wt, answer)
    # Step: pkg/a.py is not in replace -> partial-file fires
    assert result == "partial_file"
    assert "pkg/a.py" in detail


def test_replace_path_that_does_not_exist(tmp_path, monkeypatch):
    """replace=["pkg/c.py"], pkg/c.py does not exist in wt -> new files are never partial."""
    wt = _setup(tmp_path, monkeypatch)
    task = dict(TASK, replace=["pkg/c.py"])
    # pkg/c.py is absent from wt, so fp.is_file() is False -> the partial-file check never sees it
    answer = _answer("pkg/c.py", "NEW = 1\n")
    result, detail = loop.check_answer(task, wt, answer)
    # Step: fp.is_file() is False -> the file is not checked for partial
    assert result == "passed"


def test_replace_path_content_not_short(tmp_path, monkeypatch):
    """replace=["pkg/a.py"], new content has 20 lines (20*2 = 40 >= 40) -> not partial even without replace."""
    wt = _setup(tmp_path, monkeypatch)
    task = dict(TASK, replace=["pkg/a.py"])
    content = "\n".join(f"X{i} = {i}" for i in range(20)) + "\n"  # 20 lines
    answer = _answer("pkg/a.py", content)
    result, detail = loop.check_answer(task, wt, answer)
    # Step: 20*2 = 40 >= 40 -> not partial, replace is irrelevant
    assert result == "passed"


def test_replace_stored_as_list_by_store(tmp_path):
    """Store.add_task(..., replace=["pkg/a.py"]) stores task["replace"] = ["pkg/a.py"] (the earlier task)."""
    from stratos.state import Store
    s = Store(tmp_path / "state")
    t = s.add_task("t", "g", ["pkg/a.py"], [], ["tests/x.py"], replace=["pkg/a.py"])
    # Step: replace is stored as a list
    assert t["replace"] == ["pkg/a.py"]
    # Step: round-trip
    r = Store(tmp_path / "state").get(t["id"])
    assert r["replace"] == ["pkg/a.py"]
    # Step: task.get("replace", []) returns the list
    assert r.get("replace", []) == ["pkg/a.py"]


def test_standard_partial_detail_unchanged(tmp_path, monkeypatch):
    """The existing partial-file check (no replace key) keeps its exact detail text."""
    wt = _setup(tmp_path, monkeypatch)
    # TASK has no "replace" key
    answer = _answer("pkg/a.py", SHORT)
    result, detail = loop.check_answer(TASK, wt, answer)
    # Step: partial_file fires with the standard message
    assert result == "partial_file"
    # Step: detail says "you sent 2 lines as the whole file, but the file has 40"
    assert "you sent 2 lines as the whole file, but the file has 40" in detail
    # Step: mentions SEARCH/REPLACE and "the whole file with everything in it"
    assert "SEARCH/REPLACE" in detail
    assert "the whole file with everything in it" in detail
    # Step: nothing was written
    assert (wt / "pkg" / "a.py").read_text(encoding="utf-8") == LONG
