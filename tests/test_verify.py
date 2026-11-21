"""Tests for verify."""
import os
import subprocess
import sys

from stratos import config, plantests, verify
from stratos.verify import summarize_output


def write(tmp_path, body):
    (tmp_path / "test_x.py").write_text(body, encoding="utf-8")


def test_passes_when_every_run_passes(tmp_path):
    write(tmp_path, "def test_ok():\n    assert 1 + 1 == 2\n")
    ok, out = verify.run_tests(tmp_path, ["test_x.py"])
    assert ok and "passed" in out


def test_fails_when_a_later_run_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VERIFY_RUNS", 3)
    write(tmp_path, "import os\n\ndef test_seed():\n    assert os.environ['PYTHONHASHSEED'] != '2'\n")
    ok, out = verify.run_tests(tmp_path, ["test_x.py"])
    assert not ok
    assert "run 2 of 3" in out and "nondeterminism" in out


def test_non_ascii_test_output_is_read(tmp_path):
    write(tmp_path, "def test_korean():\n    assert '한글 출력' == '다른 글자'\n")
    ok, out = verify.run_tests(tmp_path, ["test_x.py"])
    assert not ok and "한글" in out


def test_fails_on_the_first_run(tmp_path):
    write(tmp_path, "def test_bad():\n    assert False\n")
    ok, out = verify.run_tests(tmp_path, ["test_x.py"])
    assert not ok and "run 1 of" in out


# ---- was test_verify_dotnet.py ----
# Tests for task verify_dotnet (P19, 2026-11-21, C#): `dotnet test` runs a solution, not a file, so a task's test
# files become a filter; its CLI prints in the Windows language (Korean here) unless told otherwise.
#
# verify.run_tests: when config.PROJECT["test_runner"] == "dotnet", the command is test_command + ["--filter",
# "|".join(f"FullyQualifiedName~{name}" for each test)] where name is the file stem of the test path ("::" part cut;
# "tests/Game.Tests/BoardTests.cs" -> "BoardTests"), no paths appended; and the environment of every run also has
# DOTNET_CLI_UI_LANGUAGE=en. Other runners as before.
# plantests.check_draft: when the runner is "dotnet", the draft check command (draft_check_command, e.g. dotnet build)
# runs without the draft path appended; its exit code decides "collected" as before.


class Done:
    returncode = 0
    stdout = "Passed!  - Failed: 0, Passed: 1, Skipped: 0, Total: 1"
    stderr = ""


def test_run_tests_filters_by_class(monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.append((cmd, kw["env"])) or Done())
    monkeypatch.setattr(config, "VERIFY_RUNS", 1)
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_runner": "dotnet",
                                            "test_command": ["dotnet", "test", "--nologo"]})
    assert verify.run_tests(".", ["tests/Game.Tests/BoardTests.cs", "tests/Game.Tests/LevelTests.cs::X"])[0]
    cmd, env = seen[0]
    assert cmd == ["dotnet", "test", "--nologo", "--filter", "FullyQualifiedName~BoardTests|FullyQualifiedName~LevelTests"]
    assert env["DOTNET_CLI_UI_LANGUAGE"] == "en"


def test_other_runners_unchanged(monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.append(cmd) or Done())
    monkeypatch.setattr(config, "VERIFY_RUNS", 1)
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_runner": "pytest", "test_command": ["pytest", "-q"]})
    verify.run_tests(".", ["tests/test_a.py"])
    assert seen[0] == ["pytest", "-q", "tests/test_a.py"]


def test_check_draft_runs_the_build_without_a_path(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.append(cmd) or Done())
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_runner": "dotnet",
                                            "draft_check_command": ["dotnet", "build", "--nologo"]})
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "BoardTests.cs").write_text("class BoardTests {}", encoding="utf-8")
    assert plantests.check_draft(tmp_path, "tests/BoardTests.cs")[0] == "collected"
    assert seen == [["dotnet", "build", "--nologo"]]


def test_a_draft_naming_missing_types_is_an_import_error(tmp_path, monkeypatch):
    """(Claude, 2026-11-21, Settle) a C# draft does not build before its types exist - like Python's ImportError."""
    class Fail:
        returncode = 1
        stdout = "T.cs(3,9): error CS0103: The name 'Split' does not exist in the current context [x.csproj]"
        stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: Fail())
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_runner": "dotnet",
                                            "draft_check_command": ["dotnet", "build"]})
    (tmp_path / "SplitTests.cs").write_text("x", encoding="utf-8")
    assert plantests.check_draft(tmp_path, "SplitTests.cs")[0] == "import_error"


def test_refcheck_with_no_test_run_is_an_error(tmp_path, monkeypatch):
    """(Claude, 2026-11-21, Settle) refcheck gave "agree" for 0 of 0 tests when the command could not run any test."""
    from stratos import refcheck

    class GW:
        def ensure_model(self, model):
            return 0.0

        def chat(self, messages, **kw):
            return "c", "FILE: pkg/a.py\n```python\nX = 1\n```\n"
    root = tmp_path / "r"
    (root / "pkg").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "tests" / "test_none.py").write_text("X = 1\n", encoding="utf-8")
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "source_dirs": ["pkg"], "test_runner": "pytest",
                                            "test_command": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]})
    monkeypatch.setattr(config, "REF_WRITER", {"model": "m", "effort": "low", "max_tokens": 9})
    r = refcheck.check(GW(), "P1", {"key": "a", "goal": "g", "files": ["pkg/a.py"], "tests": []}, root,
                       ["tests/test_none.py"])
    assert r["status"] == "error" and r["first_error"].startswith("no test ran")


def test_refcheck_skips_build_output(tmp_path, monkeypatch):
    """(Claude, 2026-11-21, Settle) refcheck read src/**/bin/*.dll as text and failed on the bytes."""
    from stratos import refcheck
    (tmp_path / "src" / "A" / "bin").mkdir(parents=True)
    (tmp_path / "src" / "A" / "bin" / "A.dll").write_bytes(b"MZ\x90\x00\xff")
    (tmp_path / "src" / "A" / "Money.cs").write_text("class Money {}", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "source_dirs": ["src"], "writable_suffixes": [".cs"]})
    user = refcheck.build_messages({"key": "k", "goal": "g", "files": ["src/A/Split.cs"], "tests": []}, tmp_path)[1]["content"]
    assert "EXISTING FILE src/A/Money.cs" in user and "A.dll" not in user


# ---- was test_verify_project.py ----
# Tests for stratos/verify.py: run_tests uses config.PROJECT["test_command"] as the base command
# and appends the task's tests. The command runs config.VERIFY_RUNS times with PYTHONHASHSEED 1, 2, 3.
# PYTHONIOENCODING="utf-8" and PYTHONUTF8="1" are always set; every other env variable is kept from os.environ.
# Tests pass only if every run passes; a failing run reports which seed failed and notes if earlier runs passed.
# A timeout returns (False, ...) mentioning the timeout. Output is truncated to 4000 chars.


# --- helpers ---------------------------------------------------------------

class FakeRun:
    """Records every subprocess.run call so we can inspect cmd, cwd, env."""
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.calls = []
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def run(self, cmd, **kw):
        self.calls.append((cmd, kw))
        # If we want to simulate a failure on a specific seed, use .fail_on_seed
        seed = kw.get("env", {}).get("PYTHONHASHSEED", "1")
        rc = self.returncode
        out, err = self.stdout, self.stderr
        if hasattr(self, "fail_on_seed") and str(seed) == str(self.fail_on_seed):
            rc = 1
            err = "FAILED\n"
        return subprocess.CompletedProcess(args=cmd, returncode=rc, stdout=out, stderr=err)


def _setup(monkeypatch, test_command, verify_runs=3, timeout=300):
    monkeypatch.setattr(config, "PROJECT", {"test_command": test_command})
    monkeypatch.setattr(config, "VERIFY_RUNS", verify_runs)
    monkeypatch.setattr(config, "TEST_TIMEOUT_S", timeout)


# --- tests ----------------------------------------------------------------

def test_run_tests_uses_project_test_command(monkeypatch):
    """The base command is config.PROJECT["test_command"], not a hard-coded pytest string."""
    project_cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=short"]
    _setup(monkeypatch, project_cmd)
    fake = FakeRun(returncode=0, stdout="all pass")
    monkeypatch.setattr(subprocess, "run", fake.run)

    ok, out = verify.run_tests("/tmp/wt", ["tests/test_foo.py", "tests/test_bar.py"])
    assert ok is True
    assert len(fake.calls) == config.VERIFY_RUNS
    # Each call must use the project command + the task's tests
    for cmd, kw in fake.calls:
        assert cmd == project_cmd + ["tests/test_foo.py", "tests/test_bar.py"]
        assert kw["cwd"] == "/tmp/wt"
        assert kw["capture_output"] is True
        assert kw["text"] is True


def test_run_tests_appends_task_tests(monkeypatch):
    """A single test file is appended to the project command."""
    project_cmd = [sys.executable, "-m", "pytest", "-q"]
    _setup(monkeypatch, project_cmd)
    fake = FakeRun(returncode=0, stdout="ok")
    monkeypatch.setattr(subprocess, "run", fake.run)

    ok, out = verify.run_tests("/tmp/wt", ["tests/test_one.py"])
    assert ok is True
    cmd = fake.calls[0][0]
    assert cmd == [sys.executable, "-m", "pytest", "-q", "tests/test_one.py"]


def test_run_tests_multiple_runs_with_hashseed(monkeypatch):
    """VERIFY_RUNS=3 → seeds 1,2,3."""
    project_cmd = [sys.executable, "-m", "pytest", "-q"]
    _setup(monkeypatch, project_cmd, verify_runs=3)
    fake = FakeRun(returncode=0, stdout="ok")
    monkeypatch.setattr(subprocess, "run", fake.run)

    ok, out = verify.run_tests("/tmp/wt", ["tests/a.py"])
    assert ok is True
    assert len(fake.calls) == 3
    seeds = [kw["env"]["PYTHONHASHSEED"] for _, kw in fake.calls]
    assert seeds == ["1", "2", "3"]


def test_run_tests_verify_runs_from_config(monkeypatch):
    """VERIFY_RUNS=2 → seeds 1,2."""
    project_cmd = [sys.executable, "-m", "pytest", "-q"]
    _setup(monkeypatch, project_cmd, verify_runs=2)
    fake = FakeRun(returncode=0, stdout="ok")
    monkeypatch.setattr(subprocess, "run", fake.run)

    ok, out = verify.run_tests("/tmp/wt", ["tests/a.py"])
    assert ok is True
    assert len(fake.calls) == 2
    seeds = [kw["env"]["PYTHONHASHSEED"] for _, kw in fake.calls]
    assert seeds == ["1", "2"]


def test_run_tests_env_has_pythonioencoding_and_utf8(monkeypatch):
    """PYTHONIOENCODING=utf-8 and PYTHONUTF8=1 are set on every run."""
    project_cmd = [sys.executable, "-m", "pytest", "-q"]
    _setup(monkeypatch, project_cmd)
    fake = FakeRun(returncode=0, stdout="ok")
    monkeypatch.setattr(subprocess, "run", fake.run)

    ok, out = verify.run_tests("/tmp/wt", ["tests/a.py"])
    for _, kw in fake.calls:
        env = kw["env"]
        assert env["PYTHONIOENCODING"] == "utf-8"
        assert env["PYTHONUTF8"] == "1"


def test_run_tests_env_keeps_os_environ(monkeypatch):
    """Variables from os.environ survive; only PYTHONHASHSEED, PYTHONIOENCODING, PYTHONUTF8 are added."""
    monkeypatch.setenv("MY_CUSTOM_VAR", "hello123")
    project_cmd = [sys.executable, "-m", "pytest", "-q"]
    _setup(monkeypatch, project_cmd, verify_runs=1)
    fake = FakeRun(returncode=0, stdout="ok")
    monkeypatch.setattr(subprocess, "run", fake.run)

    ok, out = verify.run_tests("/tmp/wt", ["tests/a.py"])
    env = fake.calls[0][1]["env"]
    assert env["MY_CUSTOM_VAR"] == "hello123"


def test_run_tests_fail_first_run(monkeypatch):
    """If the first run fails, the note says 'failed on run 1 of N' with no 'earlier runs passed'."""
    project_cmd = [sys.executable, "-m", "pytest", "-q"]
    _setup(monkeypatch, project_cmd, verify_runs=3)
    fake = FakeRun(returncode=1, stdout="", stderr="FAILED at seed 1")
    fake.fail_on_seed = 1
    monkeypatch.setattr(subprocess, "run", fake.run)

    ok, out = verify.run_tests("/tmp/wt", ["tests/a.py"])
    assert ok is False
    assert "failed on run 1 of 3" in out
    assert "PYTHONHASHSEED=1" in out
    # seed 1 → no "earlier runs passed" note
    assert "earlier runs passed" not in out


def test_run_tests_fail_later_run_notes_earlier_passes(monkeypatch):
    """If run 2 fails after run 1 passed, the note mentions earlier passes."""
    project_cmd = [sys.executable, "-m", "pytest", "-q"]
    _setup(monkeypatch, project_cmd, verify_runs=3)
    fake = FakeRun(returncode=0, stdout="", stderr="")
    fake.fail_on_seed = 2
    monkeypatch.setattr(subprocess, "run", fake.run)

    ok, out = verify.run_tests("/tmp/wt", ["tests/a.py"])
    assert ok is False
    assert "failed on run 2 of 3" in out
    assert "PYTHONHASHSEED=2" in out
    assert "earlier runs passed" in out
    assert "nondeterminism" in out


def test_run_tests_timeout_returns_failure(monkeypatch):
    """A TimeoutExpired from subprocess.run → (False, msg mentioning timeout)."""
    project_cmd = [sys.executable, "-m", "pytest", "-q"]
    _setup(monkeypatch, project_cmd, verify_runs=3, timeout=60)

    def _timeout_run(cmd, **kw):
        seed = kw.get("env", {}).get("PYTHONHASHSEED", "1")
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kw.get("timeout", 300))

    monkeypatch.setattr(subprocess, "run", _timeout_run)
    ok, out = verify.run_tests("/tmp/wt", ["tests/a.py"])
    assert ok is False
    assert "timed out" in out
    assert "60" in out
    assert "PYTHONHASHSEED=1" in out


def test_run_tests_output_truncated_to_4000(monkeypatch):
    """Returned detail is at most 4000 chars of stdout+stderr."""
    project_cmd = [sys.executable, "-m", "pytest", "-q"]
    _setup(monkeypatch, project_cmd, verify_runs=1)
    long_out = "x" * 6000
    fake = FakeRun(returncode=0, stdout=long_out, stderr="")
    monkeypatch.setattr(subprocess, "run", fake.run)

    ok, out = verify.run_tests("/tmp/wt", ["tests/a.py"])
    assert ok is True
    assert len(out) <= 4000
    # the last 4000 chars of the combined output
    assert out == "x" * 4000


def test_run_tests_no_tests_uses_only_project_command(monkeypatch):
    """Empty tests list → command is just the project command."""
    project_cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    _setup(monkeypatch, project_cmd, verify_runs=1)
    fake = FakeRun(returncode=0, stdout="ok")
    monkeypatch.setattr(subprocess, "run", fake.run)

    ok, out = verify.run_tests("/tmp/wt", [])
    assert ok is True
    assert fake.calls[0][0] == project_cmd


def test_run_tests_project_command_not_hardcoded_pytest(monkeypatch):
    """The command must come from config.PROJECT, not be built inside run_tests."""
    custom_cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--maxfail=1", "--tb=short"]
    _setup(monkeypatch, custom_cmd, verify_runs=1)
    fake = FakeRun(returncode=0, stdout="ok")
    monkeypatch.setattr(subprocess, "run", fake.run)

    ok, out = verify.run_tests("/tmp/wt", ["tests/a.py"])
    cmd = fake.calls[0][0]
    # --maxfail and --tb=short are not in the old hard-coded command
    assert "--maxfail=1" in cmd
    assert "--tb=short" in cmd
    assert cmd == custom_cmd + ["tests/a.py"]


# ---- was test_verify_summary.py ----
# Tests for summarize_output(out) in stratos/verify.py.
#
# summarize_output(out) -> str
#     Parse TAP output. For every "not ok <n> - <name>" line (including indented subtests),
#     include that line plus up to 8 lines from its YAML block that contain
#     "error:", "expected:", "actual:", "location:". Then append the
#     "# tests", "# pass", "# fail" summary lines. Return out unchanged when
#     no "not ok" lines are found.


SIMPLE_FAIL = """\
ok 1 - test_a
not ok 2 - test_b
  ---
  error: assertion failed
  expected: 3
  actual: 2
  location: tests/test_x.py:10
  ---
ok 3 - test_c
# tests 3
# pass 2
# fail 1
"""


def test_simple_not_ok_with_yaml_block():
    out = summarize_output(SIMPLE_FAIL)
    lines = out.splitlines()
    # The "not ok" line must be present
    assert "not ok 2 - test_b" in lines
    # YAML keyword lines must be present
    assert "  error: assertion failed" in out
    assert "  expected: 3" in out
    assert "  actual: 2" in out
    assert "  location: tests/test_x.py:10" in out
    # The ok lines are NOT included
    assert "ok 1 - test_a" not in out
    assert "ok 3 - test_c" not in out
    # Summary lines must be present
    assert "# tests 3" in out
    assert "# pass 2" in out
    assert "# fail 1" in out


def test_no_not_ok_returns_unchanged():
    out = "ok 1 - a\nok 2 - b\n# tests 2\n# pass 2\n# fail 0\n"
    assert summarize_output(out) == out


def test_indented_subtests():
    tap = """\
not ok 1 - outer
  not ok 2 - inner
    ---
    error: boom
    expected: 5
    actual: 4
    location: x.py:1
    ---
  ok 3 - sub_ok
ok 4 - top_ok
# tests 4
# pass 2
# fail 2
"""
    out = summarize_output(tap)
    assert "not ok 1 - outer" in out
    assert "not ok 2 - inner" in out
    # indented YAML lines preserved
    assert "    error: boom" in out
    assert "    expected: 5" in out
    assert "    actual: 4" in out
    assert "    location: x.py:1" in out
    # ok lines excluded
    assert "ok 3 - sub_ok" not in out
    assert "ok 4 - top_ok" not in out
    # summary appended
    assert "# fail 2" in out


def test_yaml_block_truncates_to_8_matching_lines():
    # A YAML block with more than 8 lines containing keywords
    yaml_block = "\n".join(
        f"  key{i}: val{i}" for i in range(12)
    )
    # Add lines that match keywords
    matching = "\n".join(
        f"  {kw} val" for kw in ["error", "expected", "actual", "location"]
    )
    tap = f"not ok 1 - x\n  ---\n{matching}\n{yaml_block}\n  ---\nok 2 - y\n# tests 2\n# pass 1\n# fail 1\n"
    out = summarize_output(tap)
    # Count lines in the YAML section that contain the keywords
    yaml_lines = [l for l in out.splitlines() if
                  any(k in l for k in ("error:", "expected:", "actual:", "location:"))]
    # At most 8 matching keyword lines per YAML block
    assert len(yaml_lines) <= 8


def test_yaml_lines_without_keywords_are_skipped():
    tap = """\
not ok 1 - a
  ---
  type: assertion
  file: x.py
  line: 10
  error: boom
  ---
# tests 1
# pass 0
# fail 1
"""
    out = summarize_output(tap)
    assert "error: boom" in out
    # lines without the four keywords are not included
    assert "type: assertion" not in out
    assert "file: x.py" not in out
    assert "line: 10" not in out


def test_multiple_not_ok_lines():
    tap = """\
not ok 1 - a
  ---
  error: e1
  expected: x
  ---
not ok 2 - b
  ---
  actual: y
  location: z.py:3
  ---
ok 3 - c
# tests 3
# pass 1
# fail 2
"""
    out = summarize_output(tap)
    assert "not ok 1 - a" in out
    assert "not ok 2 - b" in out
    assert "error: e1" in out
    assert "expected: x" in out
    assert "actual: y" in out
    assert "location: z.py:3" in out
    assert "# fail 2" in out


def test_not_ok_without_yaml_block():
    # "not ok" line with no YAML block follows
    tap = "not ok 1 - a\nok 2 - b\n# tests 2\n# pass 1\n# fail 1\n"
    out = summarize_output(tap)
    assert "not ok 1 - a" in out
    # summary lines still appended
    assert "# tests 2" in out
    assert "# pass 1" in out
    assert "# fail 1" in out


def test_empty_output():
    assert summarize_output("") == ""


def test_only_summary_lines_no_not_ok():
    out = "# tests 5\n# pass 5\n# fail 0\n"
    assert summarize_output(out) == out


def test_not_ok_line_with_leading_spaces_pattern():
    # Indented "not ok" (subtest)
    tap = """\
ok 1 - top
  not ok 2 - sub
    ---
    error: deep
    expected: 1
    actual: 2
    location: a/b.py:99
    ---
ok 3 - top2
# tests 3
# pass 2
# fail 1
"""
    out = summarize_output(tap)
    assert "not ok 2 - sub" in out
    assert "    error: deep" in out
    assert "    location: a/b.py:99" in out
    assert "# fail 1" in out


def test_summary_lines_present_at_end():
    tap = """\
not ok 1 - a
  ---
  error: x
  ---
# tests 4
# pass 3
# fail 1
"""
    out = summarize_output(tap)
    lines = out.strip().splitlines()
    # The last three lines should be the summary
    assert lines[-3] == "# tests 4"
    assert lines[-2] == "# pass 3"
    assert lines[-1] == "# fail 1"


def test_yaml_block_delimiters_not_in_output():
    tap = """\
not ok 1 - a
  ---
  error: e
  ---
# tests 1
# pass 0
# fail 1
"""
    out = summarize_output(tap)
    # The --- delimiters should not appear
    assert "  ---" not in out
    assert "---" not in out


def test_out_with_trailing_newlines():
    tap = "not ok 1 - a\n  ---\n  error: z\n  ---\n# tests 1\n# pass 0\n# fail 1\n\n"
    out = summarize_output(tap)
    assert "not ok 1 - a" in out
    assert "error: z" in out
    assert "# fail 1" in out


# ---- was test_verify_tap_values.py ----
# Tests for task tap_values (P2, 2026-11-20, BACKLOG item 13): summarize_output keeps the multi-line values of
# "error:", "expected:" and "actual:" in a TAP YAML block. Before, only the key lines were kept, so a failing
# deepStrictEqual showed "expected:" and "actual:" with nothing after them (Lumen T001: the coder could not see
# what was expected and failed twice).
#
# Rules, on top of the old ones (tests/test_verify_summary.py):
# - a YAML block starts at the line "---" after a "not ok" line and ends at a line whose stripped text is "---" or
#   "..." (node's own TAP ends blocks with "...");
# - a kept key line (one of error:, expected:, actual:, location:) whose value after the colon is empty or one of
#   "|", "|-", ">", ">-" is followed by its value lines: the next lines indented more than the key line (blank lines
#   inside count as part of it), at most 20 per key;
# - lines of other keys (stack: |- and its lines, code:, name:, operator:, duration_ms:) are still left out.


NODE_TAP = """TAP version 13
# Subtest: arr
not ok 1 - arr
  ---
  duration_ms: 1.8693
  type: 'test'
  location: 'C:\\\\x\\\\t.test.mjs:3:1'
  failureType: 'testCodeFailure'
  error: |-
    Expected values to be strictly deep-equal:
    + actual - expected

      [
        {
    +     x: 3,
    -     x: 9,
          y: 4
        }
      ]

  code: 'ERR_ASSERTION'
  name: 'AssertionError'
  expected:
    0:
      x: 9
      y: 4
  actual:
    0:
      x: 3
      y: 4
  operator: 'deepStrictEqual'
  stack: |-
    TestContext.<anonymous> (file:///C:/x/t.test.mjs:3:28)
    Test.runInAsyncScope (node:async_hooks:214:14)
  ...
# Subtest: num
not ok 2 - num
  ---
  duration_ms: 0.276
  error: |-
    Expected values to be strictly equal:

    2 !== 3

  expected: 3
  actual: 2
  stack: |-
    TestContext.<anonymous> (file:///C:/x/t.test.mjs:4:28)
  ...
1..2
# tests 2
# pass 0
# fail 2
"""


def test_multi_line_values_are_kept():
    out = summarize_output(NODE_TAP)
    lines = out.splitlines()
    i = lines.index("  expected:")
    assert lines[i + 1:i + 4] == ["    0:", "      x: 9", "      y: 4"]
    j = lines.index("  actual:")
    assert lines[j + 1:j + 4] == ["    0:", "      x: 3", "      y: 4"]
    assert "    +     x: 3," in lines and "    -     x: 9," in lines
    assert "    2 !== 3" in lines


def test_other_keys_and_the_stack_are_left_out():
    out = summarize_output(NODE_TAP)
    assert "TestContext" not in out and "runInAsyncScope" not in out
    assert "operator:" not in out and "duration_ms" not in out and "ERR_ASSERTION" not in out


def test_blocks_end_at_dots_and_single_line_values_stay_single():
    out = summarize_output(NODE_TAP)
    lines = out.splitlines()
    assert "not ok 2 - num" in lines
    k = lines.index("not ok 2 - num")
    after = lines[k + 1:]
    assert "  expected: 3" in after and "  actual: 2" in after
    assert out.rstrip().endswith("# fail 2")


def test_at_most_20_value_lines_per_key():
    value = "\n".join(f"    line {n}" for n in range(30))
    tap = f"not ok 1 - big\n  ---\n  actual: |-\n{value}\n  expected: 1\n  ...\n# tests 1\n# pass 0\n# fail 1\n"
    out = summarize_output(tap)
    assert "    line 19" in out and "    line 20" not in out
    assert "  expected: 1" in out
