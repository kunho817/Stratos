"""Tests for task lint_new_and_hints (P8, 2026-11-20, found in trial Pantry round 3).

1. Lint only blames what the answer adds. Pantry T015: lint flagged `best_size` in cmd_show, an old line the task did
   not touch; the coder added `best_size = None` to pass, and the reviewer rejected that as out of scope - three times.
   loop.check_answer: before the answer's files are written, base = lint.check(wt, <the paths about to be written that
   exist>); after the syntax check, errors = lint.check(wt, written); an error counts only when its text without the
   "row:col: " part (f"{path}: {code} {message}") is not among the base errors' texts (as many times as it is there).
   No new error -> the tests run as usual.
2. Hints that fit edit blocks. Pantry T016: Tiel answered with half a file twice after the hint "Write each file
   completely". The dropped-definitions detail now ends with "\nKeep everything that is already in the file: change an
   existing file with SEARCH/REPLACE edit blocks, or write the whole file completely." and the syntax-error detail
   with "\nCheck the syntax of every file you write; for an existing file, change only the lines you need with
   SEARCH/REPLACE edit blocks." (tests/test_loop_preflight.py was updated for the second one)."""
import pytest

from stratos import config, lint, loop, verify

OLD = "def show():\n    if x or best_size:\n        return 1\n\n\ndef other():\n    return 2\n"
TASK = {"id": "T015", "title": "t", "goal": "make other return 3", "files": ["pkg/cli.py"], "protected": [],
        "tests": ["tests/x.py"]}


def block(s, r):
    return f"FILE: pkg/cli.py\n<<<<<<< SEARCH\n{s}\n=======\n{r}\n>>>>>>> REPLACE\n"


@pytest.fixture
def env(tmp_path, monkeypatch):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "cli.py").write_text(OLD, encoding="utf-8")
    monkeypatch.setattr(config, "LINT", True)
    monkeypatch.setattr(lint, "fix", lambda root, paths: [])
    runs = []
    monkeypatch.setattr(verify, "run_tests", lambda w, tests: runs.append(1) or (True, "ok"))

    def fake_check(root, paths, codes=None):
        if codes == ("F401",):
            return []
        text = (root / "pkg" / "cli.py").read_text(encoding="utf-8")
        out = []
        for n, line in enumerate(text.splitlines(), 1):
            for name in ("best_size", "json"):
                if name in line and f"{name} =" not in text and f"import {name}" not in text:
                    out.append(f"pkg/cli.py:{n}:5: F821 Undefined name `{name}`")
        return out
    monkeypatch.setattr(lint, "check", fake_check)
    return tmp_path, runs


def test_an_old_error_does_not_block(env):
    wt, runs = env
    result, detail = loop.check_answer(TASK, wt, block("    return 2", "    return 3"))
    assert result == "passed" and runs == [1]


def test_a_new_error_still_blocks(env):
    wt, runs = env
    result, detail = loop.check_answer(TASK, wt, block("    return 2", "    return json.dumps(3)"))
    assert result == "lint_error" and runs == []
    assert "json" in detail and "best_size" not in detail


def test_hint_for_dropped_definitions(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "cli.py").write_text(OLD, encoding="utf-8")
    answer = "FILE: pkg/cli.py\n```python\ndef other():\n    return 3\n```\n"
    result, detail = loop.check_answer(TASK, tmp_path, answer)
    assert result == "dropped_defs"
    assert detail.endswith("\nKeep everything that is already in the file: change an existing file with SEARCH/REPLACE "
                           "edit blocks, or write the whole file completely.")


def test_hint_for_syntax_errors(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "cli.py").write_text(OLD, encoding="utf-8")
    result, detail = loop.check_answer(TASK, tmp_path, block("    return 2", "    return (3"))
    assert result == "syntax_error"
    assert detail.endswith("\nCheck the syntax of every file you write; for an existing file, change only the lines "
                           "you need with SEARCH/REPLACE edit blocks.")
