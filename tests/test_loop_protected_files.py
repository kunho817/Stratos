"""Tests for task loop-protected-files: in stratos/loop.py, every call to patch.apply_files in _judge
replaces the protected list with [p for p in task["protected"] if p not in task["files"]], so a
test-fix task can write its own test file.

In loop._judge the line:
    patch.apply_files(wt, files, task["protected"], allowed)
becomes:
    patch.apply_files(wt, files, [p for p in task["protected"] if p not in task["files"]], allowed)

- A path in both task["files"] and task["protected"]: removed from the filtered protected → allowed.
- A path in task["protected"] NOT in task["files"]: stays in filtered protected → refused.
- Empty task["files"]: filtered = task["protected"] unchanged.
- Empty task["protected"]: filtered = [].

OUTDATED: tests/test_loop_edits.py::test_an_edit_of_a_protected_file_is_refused - the task
dict(TASK, files=["pkg/m.py", "tests/x.py"]) has tests/x.py in both files and protected; after the
fix it is no longer protected, so the answer is "passed" not "refused".
"""
import pytest

from stratos import config, loop, patch, verify

# existing source and test files in the worktree
SRC_A = "def a():\n    return 1\n"
SRC_B = "def b():\n    return 2\n"
TEST_A = "def test_a():\n    assert True\n"
TEST_B = "def test_b():\n    assert True\n"

ANSWER_A = "FILE: pkg/a.py\n```python\nX = 1\n```\n"
ANSWER_TEST_A = "FILE: tests/test_a.py\n```python\nX = 1\n```\n"
ANSWER_B = "FILE: pkg/b.py\n```python\nY = 2\n```\n"


def _setup(tmp_path, monkeypatch):
    """Worktree with pkg/a.py, pkg/b.py, tests/test_a.py, tests/test_b.py.
    Lint, check, preflight off; fake syntax_errors and run_tests."""
    monkeypatch.setattr(config, "LINT", False)
    monkeypatch.setattr(config, "CHECK", False)
    monkeypatch.setattr(config, "PREFLIGHT", False)
    monkeypatch.setattr(verify, "syntax_errors", lambda root, paths: [])
    monkeypatch.setattr(verify, "run_tests", lambda w, tests: (True, "1 passed"))
    wt = tmp_path
    (wt / "pkg").mkdir(exist_ok=True)
    (wt / "tests").mkdir(exist_ok=True)
    (wt / "pkg" / "a.py").write_text(SRC_A, encoding="utf-8")
    (wt / "pkg" / "b.py").write_text(SRC_B, encoding="utf-8")
    (wt / "tests" / "test_a.py").write_text(TEST_A, encoding="utf-8")
    (wt / "tests" / "test_b.py").write_text(TEST_B, encoding="utf-8")
    return wt


def _task(files, protected, tests=None):
    return {"id": "T1", "title": "t", "goal": "g",
            "files": files, "protected": protected,
            "tests": tests or ["tests/test_a.py"]}


# ---- 1: a file in both files and protected is allowed ----

def test_file_in_files_and_protected_is_allowed(tmp_path, monkeypatch):
    # files = ["pkg/a.py", "tests/test_a.py"], protected = ["tests/test_a.py"]
    # filtered = [p for p in ["tests/test_a.py"] if p not in ["pkg/a.py", "tests/test_a.py"]]
    #          = []
    # → tests/test_a.py not in filtered protected → check_path passes → written
    wt = _setup(tmp_path, monkeypatch)
    task = _task(["pkg/a.py", "tests/test_a.py"], ["tests/test_a.py"])
    answer = "FILE: tests/test_a.py\n```python\ndef test_a():\n    assert True\n```\n"
    result, detail = loop.check_answer(task, wt, answer)
    # filtered protected = [] → tests/test_a.py allowed, tests run → passed
    assert result == "passed"
    assert (wt / "tests" / "test_a.py").read_text(encoding="utf-8") == "def test_a():\n    assert True\n"


# ---- 2: a protected file NOT in files is refused ----

def test_protected_not_in_files_is_refused(tmp_path, monkeypatch):
    # files = ["pkg/a.py"], protected = ["tests/test_a.py"]
    # filtered = [p for p in ["tests/test_a.py"] if p not in ["pkg/a.py"]] = ["tests/test_a.py"]
    # → tests/test_a.py stays in protected → check_path raises PatchRefused
    wt = _setup(tmp_path, monkeypatch)
    task = _task(["pkg/a.py"], ["tests/test_a.py"])
    result, detail = loop.check_answer(task, wt, ANSWER_TEST_A)
    assert result == "refused"
    assert "tests/test_a.py" in detail


# ---- 3: multiple protected paths, filter removes only the ones in files ----

def test_multiple_protected_partial_filter(tmp_path, monkeypatch):
    # files = ["pkg/a.py", "tests/test_a.py"], protected = ["tests/test_a.py", "pkg/b.py"]
    # filtered = [p for p in ["tests/test_a.py", "pkg/b.py"]
    #             if p not in ["pkg/a.py", "tests/test_a.py"]]
    #          = ["pkg/b.py"]
    # writing to pkg/b.py: in filtered protected AND not in files → refused
    wt = _setup(tmp_path, monkeypatch)
    task = _task(["pkg/a.py", "tests/test_a.py"], ["tests/test_a.py", "pkg/b.py"])
    result, detail = loop.check_answer(task, wt, ANSWER_B)
    # pkg/b.py in filtered protected, not in files → refused
    assert result == "refused"
    assert "pkg/b.py" in detail


# ---- 4: all protected in files → empty filtered protected ----

def test_all_protected_in_files_empty_filter(tmp_path, monkeypatch):
    # files = ["pkg/a.py", "pkg/b.py"], protected = ["pkg/a.py", "pkg/b.py"]
    # filtered = [p for p in ["pkg/a.py", "pkg/b.py"] if p not in ["pkg/a.py", "pkg/b.py"]] = []
    # writing to pkg/a.py: not in filtered protected, in files → allowed
    wt = _setup(tmp_path, monkeypatch)
    task = _task(["pkg/a.py", "pkg/b.py"], ["pkg/a.py", "pkg/b.py"])
    result, detail = loop.check_answer(task, wt, ANSWER_A)
    # filtered = [] → pkg/a.py not protected → allowed
    assert result == "passed"
    assert (wt / "pkg" / "a.py").read_text(encoding="utf-8") == "X = 1\n"


# ---- 5: empty files → protected list unchanged ----

def test_empty_files_protected_unchanged(tmp_path, monkeypatch):
    # files = [], protected = ["tests/test_a.py"]
    # filtered = [p for p in ["tests/test_a.py"] if p not in []] = ["tests/test_a.py"]
    # writing to tests/test_a.py: in filtered protected, not in files → refused
    wt = _setup(tmp_path, monkeypatch)
    task = _task([], ["tests/test_a.py"])
    result, detail = loop.check_answer(task, wt, ANSWER_TEST_A)
    # files empty → filtered = protected unchanged → refused
    assert result == "refused"


# ---- 6: empty protected → no filtering, no change ----

def test_empty_protected_no_change(tmp_path, monkeypatch):
    # files = ["pkg/a.py"], protected = []
    # filtered = []
    # writing to pkg/a.py: in files, not in filtered protected → allowed
    wt = _setup(tmp_path, monkeypatch)
    task = _task(["pkg/a.py"], [])
    result, detail = loop.check_answer(task, wt, ANSWER_A)
    # filtered = [] → allowed
    assert result == "passed"


# ---- 7: test-fix task writes its own test file ----

def test_test_fix_task_writes_own_test(tmp_path, monkeypatch):
    # files = ["pkg/a.py", "tests/test_a.py"], protected = ["tests/test_a.py"]
    # answer writes to BOTH pkg/a.py and tests/test_a.py
    # filtered = [] → both allowed
    wt = _setup(tmp_path, monkeypatch)
    task = _task(["pkg/a.py", "tests/test_a.py"], ["tests/test_a.py"])
    answer = ("FILE: pkg/a.py\n```python\nX = 1\n```\n"
              "FILE: tests/test_a.py\n```python\ndef test_a():\n    assert True\n```\n")
    result, detail = loop.check_answer(task, wt, answer)
    # filtered = [] → both files allowed
    assert result == "passed"
    assert (wt / "pkg" / "a.py").read_text(encoding="utf-8") == "X = 1\n"
    assert (wt / "tests" / "test_a.py").read_text(encoding="utf-8") == "def test_a():\n    assert True\n"


# ---- 8: one protected in files (allowed), one not (refused) ----

def test_one_protected_in_files_one_not(tmp_path, monkeypatch):
    # files = ["pkg/a.py"], protected = ["pkg/a.py", "tests/test_b.py"]
    # filtered = [p for p in ["pkg/a.py", "tests/test_b.py"]
    #             if p not in ["pkg/a.py"]] = ["tests/test_b.py"]
    # writing to tests/test_b.py: in filtered protected, not in files → refused
    wt = _setup(tmp_path, monkeypatch)
    task = _task(["pkg/a.py"], ["pkg/a.py", "tests/test_b.py"])
    result, detail = loop.check_answer(task, wt,
                                       "FILE: tests/test_b.py\n```python\nY = 1\n```\n")
    # tests/test_b.py in filtered protected, not in files → refused
    assert result == "refused"
    assert "tests/test_b.py" in detail


# ---- 9: apply_files receives the filtered protected list ----

def test_apply_files_receives_filtered_list(tmp_path, monkeypatch):
    # Record what patch.apply_files receives as the protected argument.
    # files = ["pkg/a.py", "tests/test_a.py"], protected = ["tests/test_a.py", "pkg/b.py"]
    # filtered = [p for p in ["tests/test_a.py", "pkg/b.py"]
    #             if p not in ["pkg/a.py", "tests/test_a.py"]]
    #          = ["pkg/b.py"]
    wt = _setup(tmp_path, monkeypatch)
    task = _task(["pkg/a.py", "tests/test_a.py"], ["tests/test_a.py", "pkg/b.py"])
    received = []

    def fake_apply(root, files, protected, allowed=None):
        received.append(list(protected))
        return [path for path, _ in files]

    monkeypatch.setattr(patch, "apply_files", fake_apply)
    monkeypatch.setattr(verify, "run_tests", lambda w, tests: (True, "1 passed"))
    answer = "FILE: pkg/a.py\n```python\nX = 1\n```\n"
    loop.check_answer(task, wt, answer)
    # filtered = ["pkg/b.py"] (tests/test_a.py removed because it is in files)
    assert received == [["pkg/b.py"]]


# ---- 10: protected in files passes the allowed check too ----

def test_protected_in_files_passes_allowed_check(tmp_path, monkeypatch):
    # files = ["tests/test_a.py"], protected = ["tests/test_a.py"]
    # filtered = [] → tests/test_a.py not in protected
    # allowed = ["tests/test_a.py"] → tests/test_a.py in allowed → passes
    wt = _setup(tmp_path, monkeypatch)
    task = _task(["tests/test_a.py"], ["tests/test_a.py"])
    answer = "FILE: tests/test_a.py\n```python\ndef test_a():\n    assert True\n```\n"
    result, detail = loop.check_answer(task, wt, answer)
    # filtered = [] → tests/test_a.py not protected → in allowed → passed
    assert result == "passed"
    assert (wt / "tests" / "test_a.py").read_text(encoding="utf-8") == "def test_a():\n    assert True\n"
