"""Tests for task loop_checker (P18, 2026-11-21): the static check runs in loop._judge right after the syntax check
passes and before lint and the search generator: base = checker.check(wt, <the paths about to be written that exist>)
before the files are written; after writing, errors = checker.check(wt, written); an error counts only when its text
without the line number (f"{path}: {message}") is not among the base errors' texts (as many times as it is there).
New errors -> "check_error" with detail "The checker found errors in your files:\\n" + the lines joined by "\\n" +
"\\nFix them; the tests did not run." config.CHECK = True (tests/conftest.py turns it off); off -> no checker call.
project defaults: a Python project gets check_command [<pyright next to sys.executable>, "{files}"] when that file
exists (pyright.exe on Windows), else None; stratos.toml may set "check_command" (a list) for any language."""
import sys
from pathlib import Path

import pytest

from stratos import checker, config, loop, project, verify

OLD = "def f():\n    return old_bad\n"
TASK = {"id": "T1", "title": "t", "goal": "g", "files": ["pkg/a.py"], "protected": [], "tests": ["tests/x.py"]}


def edit(s, r):
    return f"FILE: pkg/a.py\n<<<<<<< SEARCH\n{s}\n=======\n{r}\n>>>>>>> REPLACE\n"


@pytest.fixture
def env(tmp_path, monkeypatch):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text(OLD, encoding="utf-8")
    monkeypatch.setattr(config, "CHECK", True)
    runs = []
    monkeypatch.setattr(verify, "run_tests", lambda w, tests: runs.append(1) or (True, "ok"))

    def fake(root, paths):
        text = (Path(root) / "pkg" / "a.py").read_text(encoding="utf-8")
        out = []
        for n, line in enumerate(text.splitlines(), 1):
            for name in ("old_bad", "new_bad"):
                if name in line:
                    out.append(f"pkg/a.py:{n}: \"{name}\" is not defined")
        return out
    monkeypatch.setattr(checker, "check", fake)
    return tmp_path, runs


def test_old_errors_do_not_block(env):
    wt, runs = env
    assert loop.check_answer(TASK, wt, edit("def f():", "def g():\n    return 1\n\n\ndef f():"))[0] == "passed"
    assert runs == [1]


def test_new_errors_block(env):
    wt, runs = env
    result, detail = loop.check_answer(TASK, wt, edit("    return old_bad", "    return old_bad + new_bad"))
    assert result == "check_error" and runs == []
    assert detail == ('The checker found errors in your files:\npkg/a.py:2: "new_bad" is not defined\n'
                      "Fix them; the tests did not run.")


def test_off(env, monkeypatch):
    wt, runs = env
    monkeypatch.setattr(config, "CHECK", False)
    assert loop.check_answer(TASK, wt, edit("    return old_bad", "    return new_bad"))[0] == "passed"


def test_python_default_uses_pyright_when_there(tmp_path, monkeypatch):
    exe = Path(sys.executable).with_name("pyright.exe" if sys.platform == "win32" else "pyright")
    settings = project.load_settings(tmp_path)
    if exe.exists():
        assert settings["check_command"] == [str(exe), "{files}"]
    else:
        assert settings["check_command"] is None
