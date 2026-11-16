"""Run a task's tests in its work tree. The model's word is never the evidence; the tests are."""
import subprocess
import sys

from . import config


def run_tests(worktree, tests):
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests]
    try:
        r = subprocess.run(cmd, cwd=worktree, capture_output=True, text=True, timeout=config.TEST_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return False, f"tests timed out after {config.TEST_TIMEOUT_S} s"
    out = (r.stdout + r.stderr).strip()
    return r.returncode == 0, out[-4000:]
