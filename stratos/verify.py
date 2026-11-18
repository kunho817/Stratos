"""Run a task's tests in its work tree. The model's word is never the evidence; the tests are.

The tests run config.VERIFY_RUNS times, each with a different PYTHONHASHSEED, and pass only if every run passes:
code that depends on set or dict order can pass once by luck (T003's first answer did, 2026-11-16)."""
import os
import re
import subprocess
import sys

from . import config


def summarize_output(out):
    """Summarize TAP output: keep not-ok lines + their YAML keyword lines + summary."""
    lines = out.splitlines()

    not_ok_pattern = re.compile(r'^\s*not ok \d+ - .+')
    keywords = ("error:", "expected:", "actual:", "location:")

    not_ok_indices = []
    for i, line in enumerate(lines):
        if not_ok_pattern.match(line):
            not_ok_indices.append(i)

    if not not_ok_indices:
        return out

    result = []

    for idx in not_ok_indices:
        result.append(lines[idx])
        i = idx + 1
        # Look for a YAML block starting with a line whose stripped form is '---'
        if i < len(lines) and lines[i].strip() == '---':
            i += 1
            count = 0
            while i < len(lines):
                s = lines[i].strip()
                if s == '---':
                    i += 1
                    break
                if any(kw in lines[i] for kw in keywords):
                    if count < 8:
                        result.append(lines[i])
                        count += 1
                i += 1

    # Append summary lines (# tests, # pass, # fail)
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('# tests') or stripped.startswith('# pass') or stripped.startswith('# fail'):
            result.append(line)

    result_str = '\n'.join(result)
    if out.endswith('\n'):
        result_str += '\n'
    return result_str


def run_tests(worktree, tests):
    cmd = [*config.PROJECT["test_command"], *tests]
    out = ""
    for seed in range(1, config.VERIFY_RUNS + 1):
        # UTF-8 both ways: with the Windows default (cp949 here) a test's Korean text crashed the run (T019, 2026-11-17)
        env = {**os.environ, "PYTHONHASHSEED": str(seed), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        try:
            r = subprocess.run(cmd, cwd=worktree, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=config.TEST_TIMEOUT_S, env=env)
        except subprocess.TimeoutExpired:
            return False, f"tests timed out after {config.TEST_TIMEOUT_S} s (PYTHONHASHSEED={seed})"
        out = (r.stdout + r.stderr).strip()
        if r.returncode != 0:
            summarized = summarize_output(out)
            note = f"\n(failed on run {seed} of {config.VERIFY_RUNS}, PYTHONHASHSEED={seed}"
            note += "; earlier runs passed, so the result depends on set/dict order or other nondeterminism)" if seed > 1 else ")"
            return False, summarized[-4000:] + note
    return True, out[-4000:]
