"""Tests for task replace: Store.add_task gets replace=() keyword; add_one passes it to add_task; cmd_add gets
--replace (comma-separated, validated against --files); cmd_plan_add passes plan task's get("replace") to add_one.

Store.add_task(..., replace=()):
  - empty replace () → no "replace" key in the stored task dict
  - non-empty replace → task["replace"] is a list of the paths

add_one(store, ..., replace=()):
  - passes replace to store.add_task as the replace= keyword

cmd_add --replace PATHS (comma-separated, like --files):
  - every --replace path must appear in --files; missing paths → stderr "--replace paths must be in --files: <paths>",
    return 2
  - all paths in files → task stored with "replace", return 0
  - empty --replace → no "replace" key, no validation

cmd_plan_add:
  - plan task that has "replace" → stored task has "replace"
  - plan task without "replace" → stored task has no "replace" key
"""
import json

import pytest

from stratos import __main__ as cli
from stratos import config, codemap
from stratos.plan import save_plan
from stratos.state import Store


def _setup(tmp_path, monkeypatch):
    state = tmp_path / "state"
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", repo)
    monkeypatch.setattr(config, "JEV_SHADOW", False)
    monkeypatch.setattr(codemap, "build", lambda root: {"test_dir": "tests", "files": {}, "imports": {}})
    return state


# --- Store.add_task replace keyword ---

def test_empty_replace_adds_no_key(tmp_path):
    """Store.add_task(..., replace=()) → no 'replace' key in the stored task."""
    s = Store(tmp_path)
    t = s.add_task("t", "g", ["a.py"], [], ["tests/t.py"], replace=())
    # Step: replace=() is empty, so no key is stored
    assert "replace" not in t
    # Step: existing keys are unchanged
    assert t["id"] == "T001" and t["title"] == "t" and t["files"] == ["a.py"]
    # Step: round-trip: reading back from disk also has no replace key
    assert "replace" not in Store(tmp_path).get("T001")


def test_non_empty_replace_stored_as_list(tmp_path):
    """Store.add_task(..., replace=("a.py","b.py")) → task["replace"] == ["a.py","b.py"]."""
    s = Store(tmp_path)
    t = s.add_task("t", "g", ["a.py", "b.py"], [], ["tests/t.py"], replace=("a.py", "b.py"))
    # Step: replace is non-empty → stored as list
    assert t["replace"] == ["a.py", "b.py"]
    # Step: round-trip
    assert Store(tmp_path).get("T001")["replace"] == ["a.py", "b.py"]


def test_existing_task_keeps_its_keys(tmp_path):
    """A task added without replace=() has exactly the old keys; adding a second task with replace
    does not affect the first."""
    s = Store(tmp_path)
    t1 = s.add_task("first", "g1", ["x.py"], [], ["tests/1.py"])
    t2 = s.add_task("second", "g2", ["y.py"], [], ["tests/2.py"], replace=("y.py",))
    # Step: t1 has no replace key
    assert "replace" not in t1
    # Step: t2 has replace
    assert t2["replace"] == ["y.py"]
    # Step: round-trip
    r1 = Store(tmp_path).get("T001")
    r2 = Store(tmp_path).get("T002")
    assert "replace" not in r1
    assert r2["replace"] == ["y.py"]


# --- add_one passes replace to add_task ---

def test_add_one_passes_replace_to_add_task(tmp_path, monkeypatch):
    """add_one(..., replace=("a.py",)) calls store.add_task with replace=("a.py",)."""
    state = _setup(tmp_path, monkeypatch)
    calls = []
    store = Store(state)
    orig = store.add_task

    def spy(*a, **kw):
        calls.append((a, kw))
        return orig(*a, **kw)

    monkeypatch.setattr(store, "add_task", spy)
    cli.add_one(store, "t", "g", ["a.py", "b.py"], [], ["tests/t.py"], "coder", (), replace=("a.py",))
    # Step: add_task was called with replace=("a.py",)
    assert calls[0][1]["replace"] == ("a.py",)
    # Step: the stored task has replace
    t = store.get("T001")
    assert t["replace"] == ["a.py"]


def test_add_one_empty_replace(tmp_path, monkeypatch):
    """add_one(..., replace=()) passes () → add_task stores no replace key."""
    state = _setup(tmp_path, monkeypatch)
    store = Store(state)
    t = cli.add_one(store, "t", "g", ["a.py"], [], ["tests/t.py"], "coder", (), replace=())
    # Step: default replace=() → no key
    assert "replace" not in t


# --- cmd_add --replace validation ---

def test_replace_paths_must_be_in_files(tmp_path, monkeypatch, capsys):
    """--replace d.py,e.py with --files a.py,b.py → d.py and e.py are not in --files → return 2,
    stderr lists them."""
    state = _setup(tmp_path, monkeypatch)
    rc = cli.main(["add", "--title", "t", "--goal", "g",
                   "--files", "a.py,b.py", "--tests", "tests/t.py",
                   "--replace", "d.py,e.py"])
    # Step: d.py and e.py are not in --files
    assert rc == 2
    err = capsys.readouterr().err
    # Step: the message lists the missing paths
    assert "--replace paths must be in --files:" in err
    assert "d.py" in err and "e.py" in err
    # Step: nothing was added
    assert Store(state).tasks() == []


def test_replace_partially_missing(tmp_path, monkeypatch, capsys):
    """--replace a.py,d.py with --files a.py,b.py → only d.py is missing."""
    state = _setup(tmp_path, monkeypatch)
    rc = cli.main(["add", "--title", "t", "--goal", "g",
                   "--files", "a.py,b.py", "--tests", "tests/t.py",
                   "--replace", "a.py,d.py"])
    # Step: d.py is not in files; a.py is
    assert rc == 2
    err = capsys.readouterr().err
    # Step: only d.py is listed
    assert "d.py" in err
    assert "a.py" not in err.split("must be in --files: ")[1]
    assert Store(state).tasks() == []


def test_replace_all_in_files_stores_task(tmp_path, monkeypatch, capsys):
    """--replace a.py,b.py with --files a.py,b.py,c.py → all present → 0, task has replace."""
    state = _setup(tmp_path, monkeypatch)
    rc = cli.main(["add", "--title", "t", "--goal", "g",
                   "--files", "a.py,b.py,c.py", "--tests", "tests/t.py",
                   "--replace", "a.py,b.py"])
    # Step: a.py and b.py are in --files
    assert rc == 0
    t = Store(state).get("T001")
    # Step: replace stored as list
    assert t["replace"] == ["a.py", "b.py"]


def test_empty_replace_adds_no_key(tmp_path, monkeypatch, capsys):
    """--replace "" (empty) → no validation, no replace key, task added."""
    state = _setup(tmp_path, monkeypatch)
    rc = cli.main(["add", "--title", "t", "--goal", "g",
                   "--files", "a.py", "--tests", "tests/t.py",
                   "--replace", ""])
    # Step: empty split → [] → no validation
    assert rc == 0
    t = Store(state).get("T001")
    # Step: no replace key
    assert "replace" not in t


def test_replace_without_files(tmp_path, monkeypatch, capsys):
    """--replace a.py with --files "" (empty) → a.py is not in files → 2."""
    state = _setup(tmp_path, monkeypatch)
    rc = cli.main(["add", "--title", "t", "--goal", "g",
                   "--files", "", "--tests", "tests/t.py",
                   "--replace", "a.py"])
    # Step: files is empty; a.py not found
    assert rc == 2
    assert "--replace paths must be in --files: a.py" in capsys.readouterr().err


# --- cmd_plan_add passes replace ---

def test_plan_add_stores_replace(tmp_path, monkeypatch):
    """A plan task with "replace": ["a.py"] → the stored task has replace=["a.py"]."""
    state = _setup(tmp_path, monkeypatch)
    task = {"key": "a", "title": "A", "goal": "g", "files": ["a.py", "b.py"],
            "tests": ["tests/a.py"], "protected": [], "after": [], "role": "coder",
            "replace": ["a.py"]}
    pid = save_plan(state, "FEATURE", [task])
    assert cli.main(["plan-add", pid]) == 0
    t = Store(state).get("T001")
    # Step: plan task has replace → stored task has replace
    assert t["replace"] == ["a.py"]


def test_plan_add_no_replace_key(tmp_path, monkeypatch):
    """A plan task without "replace" → stored task has no "replace" key."""
    state = _setup(tmp_path, monkeypatch)
    task = {"key": "a", "title": "A", "goal": "g", "files": ["a.py"],
            "tests": ["tests/a.py"], "protected": [], "after": [], "role": "coder"}
    pid = save_plan(state, "FEATURE", [task])
    assert cli.main(["plan-add", pid]) == 0
    t = Store(state).get("T001")
    # Step: plan task has no "replace" key
    assert "replace" not in task
    # Step: stored task has no replace key
    assert "replace" not in t


def test_plan_add_preserves_other_fields_with_replace(tmp_path, monkeypatch):
    """A plan task with replace keeps files, tests, protected, after as before."""
    state = _setup(tmp_path, monkeypatch)
    t1 = {"key": "a", "title": "A", "goal": "g", "files": ["a.py", "b.py"],
          "tests": ["tests/a.py"], "protected": [], "after": [], "role": "coder",
          "replace": ["a.py"]}
    t2 = {"key": "b", "title": "B", "goal": "g2", "files": ["c.py"],
          "tests": ["tests/b.py"], "protected": [], "after": ["a"], "role": "coder"}
    pid = save_plan(state, "FEATURE", [t1, t2])
    assert cli.main(["plan-add", pid]) == 0
    s = Store(state)
    # Step: T001 has replace
    assert s.get("T001")["replace"] == ["a.py"]
    # Step: T002 has no replace
    assert "replace" not in s.get("T002")
    # Step: T002 after = ["T001"]
    assert s.get("T002")["after"] == ["T001"]
    # Step: T001 files preserved
    assert s.get("T001")["files"] == ["a.py", "b.py"]
