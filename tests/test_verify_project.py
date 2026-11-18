"""Tests for stratos/verify.py: run_tests uses config.PROJECT["test_command"] as the base command
and appends the task's tests. The command runs config.VERIFY_RUNS times with PYTHONHASHSEED 1, 2, 3.
PYTHONIOENCODING="utf-8" and PYTHONUTF8="1" are always set; every other env variable is kept from os.environ.
Tests pass only if every run passes; a failing run reports which seed failed and notes if earlier runs passed.
A timeout returns (False, ...) mentioning the timeout. Output is truncated to 4000 chars."""
import os
import subprocess
import sys

from stratos import config, verify

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
