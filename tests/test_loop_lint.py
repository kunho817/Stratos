"""Tests for task loop_lint (P6, 2026-11-20, after lint): check_answer uses the lint step.

config.LINT (True by default; tests/conftest.py turns it off). When on, in loop.check_answer:
1. after the syntax check passes and before the tests: errors = lint.check(wt, written); when not empty, the result is
   "lint_error" with detail "Your files use names that are not defined:\n" + the lines joined by "\n" +
   "\nDefine or import every name you use." and the tests are not run (a failed attempt like syntax_error);
2. after the tests pass: fixed = lint.fix(wt, written); when not empty, the tests run once more (verify.run_tests);
   passing again keeps the result "passed" and appends "\n(lint removed unused imports in: " + ", ".join(fixed) +
   ")" to the detail; failing gives result "failed" with that run's output.
Off: neither lint function is called."""
import pytest

from stratos import config, lint, loop, verify

TASK = {"id": "T001", "title": "t", "goal": "g", "files": ["pkg/a.py"], "protected": [], "tests": ["tests/x.py"]}
ANSWER = "FILE: pkg/a.py\n```python\nimport os\nX = 1\n```\n"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LINT", True)
    rec = {"check": [], "fix": [], "runs": [], "outs": [], "errors": [], "fixed": []}
    monkeypatch.setattr(lint, "check", lambda root, paths: rec["check"].append(list(paths)) or list(rec["errors"]))
    monkeypatch.setattr(lint, "fix", lambda root, paths: rec["fix"].append(list(paths)) or list(rec["fixed"]))

    def run(w, tests):
        rec["runs"].append(tests)
        return rec["outs"].pop(0)
    monkeypatch.setattr(verify, "run_tests", run)
    return tmp_path, rec


def test_undefined_names_stop_before_the_tests(env):
    wt, rec = env
    rec["errors"] = ["pkg/a.py:2:5: F821 Undefined name `json`"]
    result, detail = loop.check_answer(TASK, wt, ANSWER)
    assert result == "lint_error"
    assert detail == ("Your files use names that are not defined:\npkg/a.py:2:5: F821 Undefined name `json`\n"
                      "Define or import every name you use.")
    assert rec["runs"] == [] and rec["check"] == [["pkg/a.py"]]


def test_unused_imports_are_fixed_and_the_tests_run_again(env):
    wt, rec = env
    rec["fixed"] = ["pkg/a.py"]
    rec["outs"] = [(True, "1 passed"), (True, "1 passed again")]
    result, detail = loop.check_answer(TASK, wt, ANSWER)
    assert result == "passed"
    assert detail.endswith("\n(lint removed unused imports in: pkg/a.py)")
    assert len(rec["runs"]) == 2 and rec["fix"] == [["pkg/a.py"]]


def test_a_fix_that_breaks_the_tests_fails(env):
    wt, rec = env
    rec["fixed"] = ["pkg/a.py"]
    rec["outs"] = [(True, "1 passed"), (False, "FAILED tests/x.py::t - boom")]
    assert loop.check_answer(TASK, wt, ANSWER) == ("failed", "FAILED tests/x.py::t - boom")


def test_nothing_to_fix_runs_the_tests_once(env):
    wt, rec = env
    rec["outs"] = [(True, "1 passed")]
    assert loop.check_answer(TASK, wt, ANSWER) == ("passed", "1 passed")
    assert len(rec["runs"]) == 1


def test_off(env, monkeypatch):
    wt, rec = env
    monkeypatch.setattr(config, "LINT", False)
    rec["outs"] = [(True, "ok")]
    assert loop.check_answer(TASK, wt, ANSWER)[0] == "passed"
    assert rec["check"] == [] and rec["fix"] == []
