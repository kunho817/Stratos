"""Tests for task T034: `add` asks Jev in shadow mode. When config.JEV_SHADOW is true, after the task is stored
(whether its role was decided by the rules or given with --role), add calls
jev.choose_role({'files': ..., 'goal': ...}) and records a telemetry event kind "decision" with decision="role",
decider="jev", task, choice, confidence, reason and input_tokens (choice None, confidence None and reason
"jev unavailable" when choose_role returns None), then prints 'jev: <choice> <confidence> (shadow)' or
'jev: unavailable'. The task's role never changes because of Jev. The rules' own decision event now also carries
decider="rules". When config.JEV_SHADOW is false, Jev is not called at all."""
import json

import pytest

from stratos import __main__ as cli
from stratos import config, jev
from stratos.state import Store

JEV_SAYS_HARD = {"choice": "coder_hard", "confidence": 0.8, "reason": "jev: coder 0.1, coder_hard 0.9",
                 "input_tokens": 300}


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    return Store(tmp_path / "state")


@pytest.fixture
def jev_calls(monkeypatch):
    calls = []

    def fake(task, **kwargs):
        calls.append(task)
        return fake.answer
    fake.answer = JEV_SAYS_HARD
    monkeypatch.setattr(jev, "choose_role", fake)
    monkeypatch.setattr(config, "JEV_SHADOW", True)
    return calls, fake


def add(*args):
    return cli.main(["add", "--title", "t", "--tests", "tests/x.py", "--goal", "Add a helper.",
                     "--files", "stratos/a.py", *args])


def decisions(state):
    p = state.dir / "telemetry.jsonl"
    return [e for e in map(json.loads, p.read_text(encoding="utf-8").splitlines()) if e["kind"] == "decision"]


def test_jev_is_asked_and_recorded_but_not_followed(state, jev_calls, capsys):
    calls, _ = jev_calls
    assert add() == 0
    assert calls == [{"files": ["stratos/a.py"], "goal": "Add a helper."}]
    assert state.get("T001")["role"] == "coder"
    rules, shadow = decisions(state)
    assert rules["decider"] == "rules" and rules["choice"] == "coder"
    assert shadow["decider"] == "jev" and shadow["decision"] == "role" and shadow["task"] == "T001"
    assert shadow["choice"] == "coder_hard" and shadow["confidence"] == 0.8 and shadow["input_tokens"] == 300
    assert shadow["reason"] == JEV_SAYS_HARD["reason"]
    assert "jev: coder_hard 0.8 (shadow)" in capsys.readouterr().out


def test_jev_is_asked_when_the_role_is_given(state, jev_calls):
    calls, _ = jev_calls
    add("--role", "coder")
    assert len(calls) == 1 and state.get("T001")["role"] == "coder"
    [shadow] = decisions(state)
    assert shadow["decider"] == "jev"


def test_jev_unavailable(state, jev_calls, capsys):
    _, fake = jev_calls
    fake.answer = None
    assert add() == 0
    shadow = decisions(state)[-1]
    assert shadow["decider"] == "jev" and shadow["choice"] is None and shadow["confidence"] is None
    assert shadow["reason"] == "jev unavailable"
    assert "jev: unavailable" in capsys.readouterr().out


def test_shadow_off_means_no_call(state, jev_calls):
    calls, _ = jev_calls
    config.JEV_SHADOW = False
    add()
    assert calls == [] and [e["decider"] for e in decisions(state)] == ["rules"]
