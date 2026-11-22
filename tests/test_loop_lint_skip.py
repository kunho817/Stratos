"""Tests for task loop_lint_skip: skip lint fix on files with pre-existing unused imports.

In stratos/loop.py, _judge: where base = lint.check(wt, existing_paths) is computed, also compute
base_unused = set of file paths (the part before the first ":" in each line of
lint.check(wt, existing_paths, codes=("F401",))). _lint_fix(wt, written, tests, out, skip=()) gets the
keyword parameter skip and runs lint.fix only on the written paths that are not in skip. The caller
in _judge (called by check_answer) passes skip=base_unused. A file without a pre-existing F401 is
fixed as today; a file that already had an unused import is left untouched by lint.fix.

No existing test becomes outdated: test_loop_lint.py monkeypatches lint.fix to accept all paths and
returns [], so the skip=() default passes all paths; the recorded fix list is identical."""
import pytest
from pathlib import Path

from stratos import config, lint, loop, verify

# pkg/a.py: import os unused → pre-existing F401
FILE_A = "import os\nX = 1\n"
# pkg/b.py: sys is used → no pre-existing F401
FILE_B = "import sys\nprint(sys.argv)\n"
# pkg/e.py: import json unused → pre-existing F401
FILE_E = "import json\nY = 1\n"

TASK_AB = {"id": "T1", "title": "t", "goal": "g",
           "files": ["pkg/a.py", "pkg/b.py"],
           "protected": [], "tests": ["tests/x.py"]}

ANSWER_AB = ("FILE: pkg/a.py\n```python\nimport os\nimport json\nX = 1\nY = 2\n```\n"
             "FILE: pkg/b.py\n```python\nimport sys\nimport json\nprint(sys.argv)\nZ = 3\n```\n")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Worktree with pkg/a.py (has F401) and pkg/b.py (no F401).

    fake_check returns F401 lines for files containing 'import os' with no 'os.' usage.
    fake_fix records the paths it receives and returns [] (no changes).
    fake_run always returns (True, '1 passed')."""
    monkeypatch.setattr(config, "LINT", True)
    monkeypatch.setattr(config, "CHECK", False)
    monkeypatch.setattr(config, "PREFLIGHT", False)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text(FILE_A, encoding="utf-8")
    (tmp_path / "pkg" / "b.py").write_text(FILE_B, encoding="utf-8")
    rec = {"check": [], "fix": [], "outs": [(True, "1 passed"), (True, "1 passed")]}

    def fake_check(root, paths, codes=lint.ERRORS):
        rec["check"].append((list(paths), tuple(codes)))
        if "F401" in codes:
            out = []
            for p in paths:
                fp = Path(root) / p
                if fp.exists():
                    text = fp.read_text(encoding="utf-8")
                    if "import os" in text and "os." not in text:
                        out.append(f"{p}:1:1: F401 `os` imported but unused")
            return out
        return []

    monkeypatch.setattr(lint, "check", fake_check)

    def fake_fix(root, paths):
        rec["fix"].append(list(paths))
        return []

    monkeypatch.setattr(lint, "fix", fake_fix)

    def fake_run(w, tests):
        return rec["outs"].pop(0)

    monkeypatch.setattr(verify, "run_tests", fake_run)
    return tmp_path, rec


def test_file_with_pre_existing_f401_is_skipped(env):
    """pkg/a.py had `import os` unused before the answer → base_unused = {"pkg/a.py"}.
    In _lint_fix, written = ["pkg/a.py", "pkg/b.py"]; filtered = [p for p in written if p not in skip]
    = ["pkg/b.py"]. So lint.fix receives only ["pkg/b.py"], not "pkg/a.py"."""
    wt, rec = env
    result, detail = loop.check_answer(TASK_AB, wt, ANSWER_AB)
    assert result == "passed"
    # base_unused = {"pkg/a.py"}; filtered paths = ["pkg/b.py"]
    assert rec["fix"] == [["pkg/b.py"]]


def test_file_without_pre_existing_f401_is_fixed(env):
    """pkg/b.py has no pre-existing F401 → it is NOT in base_unused → it IS passed to lint.fix."""
    wt, rec = env
    loop.check_answer(TASK_AB, wt, ANSWER_AB)
    # "pkg/b.py" must be in the fix paths
    assert "pkg/b.py" in rec["fix"][0]
    # "pkg/a.py" must NOT be in the fix paths
    assert "pkg/a.py" not in rec["fix"][0]


def test_new_file_is_not_skipped(env):
    """pkg/c.py does not exist before → not in existing_paths → not in base_unused → gets fixed.
    base_unused = {"pkg/a.py"}; written = ["pkg/a.py","pkg/b.py","pkg/c.py"];
    filtered = ["pkg/b.py","pkg/c.py"]."""
    wt, rec = env
    task = dict(TASK_AB, files=["pkg/a.py", "pkg/b.py", "pkg/c.py"])
    answer = ANSWER_AB + "FILE: pkg/c.py\n```python\nimport json\nZ = 3\n```\n"
    loop.check_answer(task, wt, answer)
    assert sorted(rec["fix"][0]) == ["pkg/b.py", "pkg/c.py"]


def test_skip_default_passes_all_paths(env):
    """_lint_fix called with skip=() → all written paths pass through the filter unchanged.
    Create a worktree where NO file has pre-existing F401, so base_unused is empty → skip=().
    Every written path must appear in lint.fix."""
    wt, rec = env
    # rewrite a.py so it has no pre-existing F401 (no "import os" without "os.")
    (wt / "pkg" / "a.py").write_text("import sys\nprint(sys.argv)\nX = 1\n", encoding="utf-8")
    # Now base_unused = set() (no file has import os unused)
    # filtered = ["pkg/a.py", "pkg/b.py"] (all)
    loop.check_answer(TASK_AB, wt, ANSWER_AB)
    # both files passed to fix
    assert sorted(rec["fix"][0]) == ["pkg/a.py", "pkg/b.py"]


def test_f401_check_uses_codes_f401(env):
    """The base_unused computation calls lint.check with codes=("F401",).
    rec["check"] records every call. The base check (default codes) and the F401 check are
    the first two calls. The second entry's codes tuple must equal ("F401",)."""
    wt, rec = env
    loop.check_answer(TASK_AB, wt, ANSWER_AB)
    # rec["check"] entries: [(paths, codes) for base, (paths, codes) for F401, (paths, codes) for post-write]
    codes_list = [codes for _, codes in rec["check"]]
    # The F401 call is at index 1 (after the base call at index 0)
    assert codes_list[1] == ("F401",)


def test_f401_check_uses_same_existing_paths_as_base(env):
    """The lint.check call for base_unused uses the same existing file paths as the base
    lint.check call. rec["check"][0][0] and rec["check"][1][0] must be equal."""
    wt, rec = env
    loop.check_answer(TASK_AB, wt, ANSWER_AB)
    paths_base = rec["check"][0][0]
    paths_f401 = rec["check"][1][0]
    # same paths: the files that exist before writing
    assert paths_base == paths_f401
    assert sorted(paths_base) == ["pkg/a.py", "pkg/b.py"]


def test_base_unused_contains_path_before_colon(env):
    """base_unused is built from the part before the first ":" in each F401 lint line.
    The F401 check for pkg/a.py returns "pkg/a.py:1:1: F401 ...".
    split(":")[0] = "pkg/a.py". base_unused must be {"pkg/a.py"}."""
    wt, rec = env
    # trigger the computation; we check the filtered paths as a proxy
    loop.check_answer(TASK_AB, wt, ANSWER_AB)
    # The fix call received ["pkg/b.py"] → base_unused was {"pkg/a.py"}
    # (if base_unused were not a set of paths, the filter logic would fail)
    assert len(rec["fix"]) == 1
    assert "pkg/a.py" not in rec["fix"][0]


def test_lint_off_no_calls(env, monkeypatch):
    """When config.LINT is False, no lint.check for F401 and no lint.fix are called."""
    wt, rec = env
    monkeypatch.setattr(config, "LINT", False)
    result, detail = loop.check_answer(TASK_AB, wt, ANSWER_AB)
    assert result == "passed"
    # no lint calls at all
    assert rec["check"] == []
    assert rec["fix"] == []


def test_all_files_have_f401_fix_gets_empty(env, monkeypatch):
    """Both pkg/a.py and pkg/e.py have pre-existing F401 → base_unused = {"pkg/a.py", "pkg/e.py"}.
    written = ["pkg/a.py", "pkg/e.py"] → filtered = [] → lint.fix gets an empty list."""
    wt, rec = env
    (wt / "pkg" / "e.py").write_text(FILE_E, encoding="utf-8")
    task = {"id": "T1", "title": "t", "goal": "g",
           "files": ["pkg/a.py", "pkg/e.py"],
           "protected": [], "tests": ["tests/x.py"]}
    answer = ("FILE: pkg/a.py\n```python\nimport os\nX = 1\nY = 2\n```\n"
              "FILE: pkg/e.py\n```python\nimport json\nY = 1\nZ = 3\n```\n")
    loop.check_answer(task, wt, answer)
    # base_unused = {"pkg/a.py", "pkg/e.py"} → filtered = []
    assert rec["fix"] == [[]]


def test_skip_is_a_set_of_strings(env):
    """base_unused must be a set (not a list) of path strings.
    The filter `p not in skip` on a set is O(1); on a list it is O(n).
    We verify by checking that multiple files with F401 are all skipped."""
    wt, rec = env
    # add a second file with pre-existing F401
    (wt / "pkg" / "d.py").write_text("import os\nQ = 1\n", encoding="utf-8")
    task = {"id": "T1", "title": "t", "goal": "g",
           "files": ["pkg/a.py", "pkg/b.py", "pkg/d.py"],
           "protected": [], "tests": ["tests/x.py"]}
    answer = (ANSWER_AB +
              "FILE: pkg/d.py\n```python\nimport os\nQ = 1\nR = 2\n```\n")
    loop.check_answer(task, wt, answer)
    # base_unused = {"pkg/a.py", "pkg/d.py"} (both have import os unused)
    # filtered = ["pkg/b.py"]
    assert rec["fix"] == [["pkg/b.py"]]


def test_existing_f401_not_in_written_paths(env):
    """A file that existed with F401 but is NOT in the answer's written paths:
    it appears in base_unused but has no entry in written, so the filter
    `[p for p in written if p not in skip]` never sees it.
    pkg/a.py has F401; the answer only writes pkg/b.py.
    base_unused = {"pkg/a.py"}; written = ["pkg/b.py"]; filtered = ["pkg/b.py"]."""
    wt, rec = env
    task = {"id": "T1", "title": "t", "goal": "g",
           "files": ["pkg/b.py"],
           "protected": [], "tests": ["tests/x.py"]}
    answer = "FILE: pkg/b.py\n```python\nimport sys\nprint(sys.argv)\nZ = 3\n```\n"
    loop.check_answer(task, wt, answer)
    # base_unused = {"pkg/a.py"} (a.py is an existing file checked for F401)
    # written = ["pkg/b.py"]; filtered = ["pkg/b.py"]
    assert rec["fix"] == [["pkg/b.py"]]


def test_fix_returns_empty_and_skipped(env):
    """When lint.fix is called on the filtered paths and returns [] (no changes),
    the tests run once (no re-run) and the result is "passed" with the original output."""
    wt, rec = env
    result, detail = loop.check_answer(TASK_AB, wt, ANSWER_AB)
    # fake_fix returns [] → _lint_fix returns "passed", out unchanged
    assert result == "passed"
    assert detail == "1 passed"
    # only one test run (no re-run)
    # rec["outs"] had 2 entries; fake_run pops; we used one for the first run,
    # and since fix returns [], no second run
    # the test output consumed: 1
    # remaining outs: 1
    assert len(rec["outs"]) == 1
