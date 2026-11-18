"""Tests for --goal-file read error handling in the plan subcommand.

When --goal-file points to a file that cannot be read (missing, permission
error, is a directory), the plan command must print
'cannot read goal file <F>: <error>' on stderr and exit with code 2,
matching the add command's pattern (parser.error).
When the file is readable, the plan command proceeds as before.
"""

import json
import pytest

from stratos.__main__ import main
from stratos import config


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class FakeGateway:
    """Avoid the network / GPU entirely."""

    def __init__(self, tel):
        self.telemetry = tel

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        plan = [
            {"key": "T1", "title": "Do X", "goal": "x",
             "files": ["a.py"], "tests": ["tests/test_a.py"],
             "role": "coder", "after": []},
        ]
        return "c1", json.dumps({"tasks": plan})


def _fake_plan_mod(monkeypatch, tmp_path):
    """Monkeypatch plan_mod so the happy path doesn't touch disk / model."""
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr("stratos.__main__.Gateway", FakeGateway)
    monkeypatch.setattr("stratos.__main__.plan_mod.repo_summary", lambda root: "summary")
    monkeypatch.setattr("stratos.__main__.plan_mod.save_plan",
                        lambda state_dir, goal, tasks: "P99")


# ---------------------------------------------------------------------------
# error-handling tests (fail until the task is done)
# ---------------------------------------------------------------------------

def test_plan_goal_file_missing_exits_2(tmp_path):
    """A missing --goal-file must trigger SystemExit(2), not an uncaught OSError."""
    missing = str(tmp_path / "no_such_goal.txt")
    with pytest.raises(SystemExit) as exc_info:
        main(["plan", "--goal-file", missing])
    assert exc_info.value.code == 2


def test_plan_goal_file_error_message_on_stderr(tmp_path, capsys):
    """The stderr line must read 'cannot read goal file <F>: <error>'."""
    missing = str(tmp_path / "no_such_goal.txt")
    with pytest.raises(SystemExit) as exc_info:
        main(["plan", "--goal-file", missing])
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "cannot read goal file" in err
    assert missing in err
    # the OS error text is included
    assert "No such file" in err


def test_plan_goal_file_is_directory(tmp_path, capsys):
    """Passing a directory as --goal-file also triggers the error path."""
    d = str(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        main(["plan", "--goal-file", d])
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "cannot read goal file" in err
    assert d in err


def test_plan_goal_file_permission_error(tmp_path, capsys, monkeypatch):
    """Simulate a permission error via monkeypatched open."""
    goal = str(tmp_path / "secret.txt")
    import builtins
    real_open = builtins.open

    def deny_open(path, *a, **kw):
        if str(path) == goal:
            raise PermissionError(13, "Permission denied", str(path))
        return real_open(path, *a, **kw)

    monkeypatch.setattr(builtins, "open", deny_open)
    with pytest.raises(SystemExit) as exc_info:
        main(["plan", "--goal-file", goal])
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "cannot read goal file" in err
    assert goal in err
    assert "Permission denied" in err


# ---------------------------------------------------------------------------
# happy path – the plan command runs when the file IS readable
# ---------------------------------------------------------------------------

def test_plan_goal_file_readable_proceeds(tmp_path, monkeypatch, capsys):
    goal_file = tmp_path / "goal.txt"
    goal_file.write_text("Build the widget")
    _fake_plan_mod(monkeypatch, tmp_path)

    ret = main(["plan", "--goal-file", str(goal_file)])
    assert ret == 0
    out = capsys.readouterr().out
    assert "plan" in out
    assert "Do X" in out
