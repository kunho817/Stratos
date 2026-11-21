"""Tests for task tests_parallel (P13, 2026-11-20): the whole suite takes ~100 s one file after another and `stratos push`
runs it three times (three hash seeds); with pytest-xdist (-n 8) it took 46 s, all 900 passing.

verify.run_tests(worktree, tests, parallel=False): with parallel=True, when config.PROJECT["test_runner"] is
"pytest" and the module xdist can be imported (importlib.util.find_spec("xdist") is not None), the command gets
"-n", "auto" right after the project's test_command (before the test paths); otherwise it is as before.
`stratos push` runs the suite with parallel=True. pyproject.toml lists the tools the suite and harness use in
[project.optional-dependencies] dev = ["pytest", "pytest-xdist", "ruff"]."""
import subprocess
from pathlib import Path

from stratos import config, verify


class Done:
    returncode = 0
    stdout = "1 passed"
    stderr = ""


def run(monkeypatch, parallel, xdist=True, runner="pytest"):
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.append(cmd) or Done())
    monkeypatch.setattr(config, "VERIFY_RUNS", 1)
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_runner": runner,
                                            "test_command": ["python", "-m", "pytest", "-q"]})
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object() if (xdist and name == "xdist") else None)
    assert verify.run_tests(".", ["tests/test_a.py"], parallel=parallel)[0]
    return seen[0]


def test_parallel_adds_n_auto(monkeypatch):
    assert run(monkeypatch, True) == ["python", "-m", "pytest", "-q", "-n", "auto", "tests/test_a.py"]


def test_not_parallel_by_default_or_without_xdist(monkeypatch):
    assert run(monkeypatch, False) == ["python", "-m", "pytest", "-q", "tests/test_a.py"]
    assert run(monkeypatch, True, xdist=False) == ["python", "-m", "pytest", "-q", "tests/test_a.py"]
    assert run(monkeypatch, True, runner="node") == ["python", "-m", "pytest", "-q", "tests/test_a.py"]


def test_push_runs_in_parallel_and_pyproject_lists_dev_tools():
    import inspect

    from stratos import __main__ as cli
    assert "parallel=True" in inspect.getsource(cli)   # the module: T239 moved the commands out of _main
    text = (Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert "[project.optional-dependencies]" in text and '"pytest-xdist"' in text and '"ruff"' in text
