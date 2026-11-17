"""Tests for task T013: `add --goal-file PATH` reads the goal from a UTF-8 file (PowerShell mangles double quotes in
long --goal arguments). Exactly one of --goal and --goal-file is required; a missing file is an argparse error."""
import pytest

from stratos import __main__ as cli
from stratos import config
from stratos.state import Store


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    return Store(tmp_path / "state")


def add(*args):
    return cli.main(["add", "--title", "t", "--tests", "tests/x.py", *args])


def test_goal_from_a_file(state, tmp_path):
    f = tmp_path / "goal.txt"
    f.write_text('Use "double quotes", {braces} and 한글\nline two\n', encoding="utf-8")
    assert add("--goal-file", str(f)) == 0
    assert state.get("T001")["goal"] == 'Use "double quotes", {braces} and 한글\nline two\n'


def test_goal_text_still_works(state):
    assert add("--goal", "g") == 0
    assert state.get("T001")["goal"] == "g"


def test_goal_and_goal_file_together_are_refused(state, tmp_path):
    f = tmp_path / "goal.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        add("--goal", "g", "--goal-file", str(f))


def test_a_goal_is_required(state):
    with pytest.raises(SystemExit):
        add()


# T028: without --role, add asks decide.choose_role({'files': ..., 'goal': ...}), stores the choice as the task's role
# and the whole decision as task['role_decision'], records a telemetry event kind "decision" with decision="role",
# task, choice, confidence and reason in config.STATE_DIR / 'telemetry.jsonl', and prints 'role: <choice> (<reason>)'.
# With --role given, that role is used as it is and no decision is made (no role_decision key, no event).

def events(state):
    import json
    p = state.dir / "telemetry.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def test_role_is_decided_when_not_given(state, capsys):
    add("--goal", "Add a helper that counts things.", "--files", "stratos/a.py")
    t = state.get("T001")
    assert t["role"] == "coder" and t["role_decision"]["choice"] == "coder"
    ev = [e for e in events(state) if e["kind"] == "decision"]
    assert ev and ev[0]["decision"] == "role" and ev[0]["task"] == "T001" and ev[0]["choice"] == "coder"
    assert "role: coder (" in capsys.readouterr().out


def test_two_files_get_the_hard_coder(state):
    add("--goal", "Add a helper.", "--files", "stratos/a.py,stratos/b.py")
    assert state.get("T001")["role"] == "coder_hard"


def test_a_given_role_is_kept_without_a_decision(state):
    add("--goal", "Add a helper.", "--files", "stratos/a.py,stratos/b.py", "--role", "coder")
    t = state.get("T001")
    assert t["role"] == "coder" and "role_decision" not in t
    assert [e for e in events(state) if e["kind"] == "decision"] == []


def test_a_missing_goal_file_is_an_error(state, tmp_path):
    with pytest.raises(SystemExit):
        add("--goal-file", str(tmp_path / "nope.txt"))
    assert state.tasks() == []
