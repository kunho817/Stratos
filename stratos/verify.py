"""Run a task's tests in its work tree. The model's word is never the evidence; the tests are.

The tests run config.VERIFY_RUNS times, each with a different PYTHONHASHSEED, and pass only if every run passes:
code that depends on set or dict order can pass once by luck (T003's first answer did, 2026-11-16)."""
import os
import subprocess
import sys

from . import config


def run_tests(worktree, tests):
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests]
    out = ""
    for seed in range(1, config.VERIFY_RUNS + 1):
        env = {**os.environ, "PYTHONHASHSEED": str(seed)}
        try:
            r = subprocess.run(cmd, cwd=worktree, capture_output=True, text=True, timeout=config.TEST_TIMEOUT_S, env=env)
        except subprocess.TimeoutExpired:
            return False, f"tests timed out after {config.TEST_TIMEOUT_S} s (PYTHONHASHSEED={seed})"
        out = (r.stdout + r.stderr).strip()
        if r.returncode != 0:
            note = f"\n(failed on run {seed} of {config.VERIFY_RUNS}, PYTHONHASHSEED={seed}"
            note += "; earlier runs passed, so the result depends on set/dict order or other nondeterminism)" if seed > 1 else ")"
            return False, out[-4000:] + note
    return True, out[-4000:]
