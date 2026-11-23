"""Tests for task preflight_self: preflight.check skips a "module:<name>" refusal reason
when the module is explained by the task's own files.

Rule in stratos/preflight.py check(): a "module:<name>" entry from missing_imports is
not a reason to refuse when <name> (dots read as "/") equals the path of one of the
task's files without its ".py" suffix, OR when <name> (dots as slashes) is a folder
that holds one of the task's files. Such entries are skipped. A module no task file
explains (numpy, requests) is refused as usual.

(a) transit.parse skipped: task writes transit/parse.py
(b) transit skipped: task writes transit/parse.py, folder prefix matches
(c) numpy refused: no task file explains it
(d) other refused: folder "other" exists in wt with files, but no task file is in it
"""
from pathlib import Path

from stratos import preflight


def make(tmp_path, files):
    for path, text in files.items():
        p = tmp_path / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


def task(files, tests):
    return {"id": "T001", "files": files, "tests": tests, "protected": tests}


# (a) transit.parse skipped because transit/parse.py is in task["files"]
def test_module_explained_by_task_file_skipped(tmp_path):
    # Task writes transit/parse.py; test imports transit.parse.
    # No "transit" folder exists in wt (git drops empty dirs), so
    # missing_imports returns "module:transit.parse".
    # Rule: "transit.parse" → dots as slashes = "transit/parse".
    # Task file "transit/parse.py" stripped of ".py" = "transit/parse" → match → skip.
    wt = make(tmp_path, {"tests/test_transit.py": "from transit.parse import f\n"})
    out = "ModuleNotFoundError: No module named 'transit.parse'\nFAILED tests/test_transit.py"
    r = preflight.check(task(["transit/parse.py"], ["tests/test_transit.py"]), wt,
                        run=lambda w, t: (False, out))
    # Expected: verdict "run" (module explained by task's own file, skip refusal)
    assert r["verdict"] == "run"
    # Expected: reason is "tests fail before the change" (not "module ... not installed")
    assert r["reason"] == "tests fail before the change"
    # Expected: output is the run's output
    assert r["output"] == out


# (b) transit skipped because transit/ is a folder holding task file transit/parse.py
def test_module_explained_by_task_folder_skipped(tmp_path):
    # Task writes transit/parse.py; test imports transit (the package).
    # No "transit" folder in wt → missing_imports returns "module:transit".
    # Rule: "transit" → dots as slashes = "transit".
    # Task file "transit/parse.py" starts with "transit/" → folder prefix → skip.
    wt = make(tmp_path, {"tests/test_transit.py": "import transit\n"})
    out = "ModuleNotFoundError: No module named 'transit'\nFAILED tests/test_transit.py"
    r = preflight.check(task(["transit/parse.py"], ["tests/test_transit.py"]), wt,
                        run=lambda w, t: (False, out))
    # Expected: verdict "run" (transit/ folder prefix explains the task's file)
    assert r["verdict"] == "run"
    # Expected: reason is "tests fail before the change"
    assert r["reason"] == "tests fail before the change"


# (c) numpy refused as usual
def test_module_not_explained_by_task_files_refused(tmp_path):
    # Task writes pkg/a.py; test imports numpy. No task file explains numpy.
    # Rule: "numpy" → "numpy", task file "pkg/a.py" → "pkg/a" ≠ "numpy",
    # "numpy/" not a prefix of "pkg/a.py" → not skipped → refuse.
    wt = make(tmp_path, {"tests/test_a.py": "import numpy\n"})
    out = "ModuleNotFoundError: No module named 'numpy'\nFAILED tests/test_a.py"
    r = preflight.check(task(["pkg/a.py"], ["tests/test_a.py"]), wt,
                        run=lambda w, t: (False, out))
    # Expected: verdict "refuse" (numpy not explained by any task file)
    assert r["verdict"] == "refuse"
    # Expected: reason contains "numpy"
    assert "numpy" in r["reason"]
    # Expected: output is the run's output
    assert r["output"] == out


# (d) module name matching only a folder that is NOT a task file folder is refused
def test_module_matching_non_task_folder_refused(tmp_path):
    # wt has folder "other" containing other/helper.py; task writes only pkg/a.py.
    # "other" is a folder in wt (missing_imports resolves "No module named 'other'"
    # to path "other.py" via _module_path), but no task file is in "other/".
    # entry "other.py" is not "module:...", so the path-based check applies:
    # "other.py" not in task["files"] = ["pkg/a.py"] → refuse.
    wt = make(tmp_path, {"tests/test_a.py": "import other\n",
                         "other/helper.py": "X = 1\n"})
    out = "ModuleNotFoundError: No module named 'other'\nFAILED tests/test_a.py"
    r = preflight.check(task(["pkg/a.py"], ["tests/test_a.py"]), wt,
                        run=lambda w, t: (False, out))
    # Expected: verdict "refuse" ("other" is a project folder, not a task file folder)
    assert r["verdict"] == "refuse"
    # Expected: reason mentions the resolved path "other.py"
    assert "other.py" in r["reason"]
    # Expected: output is the run's output
    assert r["output"] == out
