"""Tests for task plan_critique_cli (P3, 2026-11-20, after plancritic): `stratos plan` asks the plan critic about the
plan it saved, and `stratos plan-critique <plan id>` asks again (after a person edited the plan).

config.PLAN_CRITIQUE (True by default; tests/conftest.py turns it off).
plan.save_critique(state_dir, plan_id, problems): sets the plan file's "critique" field to the list and saves it
(nothing else changes; load_plan of an unknown id raises KeyError as before).

`stratos plan`: after printing the saved plan, when config.PLAN_CRITIQUE: problems = plancritic.critique(gw, goal,
config.REPO, tasks) with the same gateway; plan.save_critique(config.STATE_DIR, pid, problems);
gw.telemetry.record("plan_critique", plan=pid, problems=len(problems)); prints
f"critique ({config.PLAN_CRITIC['model']}, advisory): {len(problems)} problems" and one line per problem
f"  - {task}: {problem}". An exception from the critic prints f"critique failed: {e}"; the plan is kept and plan
still returns 0.
`stratos plan-critique <plan id>`: unknown id -> "no such plan: <id>" on stderr, return 1; otherwise the same steps
on the plan's current tasks and goal (a new Gateway on config.STATE_DIR / "telemetry.jsonl"), return 0."""
import json

import pytest

from stratos import __main__ as cli
from stratos import config, plan, plancritic

GOOD = {"tasks": [
    {"key": "a", "title": "Add f", "goal": "Add f to x.", "files": ["stratos/x.py"], "tests": ["tests/test_x.py"]},
]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(config, "PLAN_CRITIQUE", True)
    monkeypatch.setattr(config, "PLAN_AS_TEXT", False)
    monkeypatch.setattr(plan, "repo_summary", lambda root: "SUMMARY")
    made = []

    class FakeGateway:
        answers = []

        def __init__(self, telemetry):
            self.telemetry = telemetry
            made.append(self)

        def ensure_model(self, model):
            return 0.0

        def chat(self, messages, **kw):
            return "c1", FakeGateway.answers.pop(0)
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    calls = []

    def fake_critique(gw, goal, root, tasks):
        calls.append((gw, goal, root, [t["key"] for t in tasks]))
        if fake_critique.boom:
            raise RuntimeError("critic down")
        return [{"task": "a", "problem": "x.py is never imported"}]
    fake_critique.boom = False
    monkeypatch.setattr(plancritic, "critique", fake_critique)
    goal = tmp_path / "goal.txt"
    goal.write_text("Make it fly.", encoding="utf-8")
    return FakeGateway, made, goal, calls, fake_critique


def events(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_plan_runs_the_critic(env, capsys):
    gw_cls, made, goal, calls, fake = env
    gw_cls.answers = [json.dumps(GOOD)]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    assert calls == [(made[0], "Make it fly.", config.REPO, ["a"])]
    assert plan.load_plan(config.STATE_DIR, "P001")["critique"] == [{"task": "a", "problem": "x.py is never imported"}]
    out = capsys.readouterr().out
    assert f"critique ({config.PLAN_CRITIC['model']}, advisory): 1 problems" in out
    assert "  - a: x.py is never imported" in out
    (e,) = [e for e in events(config.STATE_DIR / "telemetry.jsonl") if e["kind"] == "plan_critique"]
    assert e["plan"] == "P001" and e["problems"] == 1


def test_a_failing_critic_keeps_the_plan(env, capsys):
    gw_cls, made, goal, calls, fake = env
    fake.boom = True
    gw_cls.answers = [json.dumps(GOOD)]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    assert "critique failed: critic down" in capsys.readouterr().out
    assert "critique" not in plan.load_plan(config.STATE_DIR, "P001")


def test_off(env, monkeypatch):
    gw_cls, made, goal, calls, fake = env
    monkeypatch.setattr(config, "PLAN_CRITIQUE", False)
    gw_cls.answers = [json.dumps(GOOD)]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    assert calls == []


def test_plan_critique_command(env, capsys):
    gw_cls, made, goal, calls, fake = env
    pid = plan.save_plan(config.STATE_DIR, "Make it fly.", GOOD["tasks"])
    assert cli.main(["plan-critique", pid]) == 0
    assert calls[0][1:] == ("Make it fly.", config.REPO, ["a"])
    assert plan.load_plan(config.STATE_DIR, pid)["critique"][0]["task"] == "a"
    assert "  - a: x.py is never imported" in capsys.readouterr().out
    assert cli.main(["plan-critique", "P999"]) == 1
    assert "no such plan: P999" in capsys.readouterr().err


def test_save_critique(tmp_path):
    pid = plan.save_plan(tmp_path, "G", GOOD["tasks"])
    plan.save_critique(tmp_path, pid, [{"task": "a", "problem": "p"}])
    p = plan.load_plan(tmp_path, pid)
    assert p["critique"] == [{"task": "a", "problem": "p"}] and p["status"] == "draft"
    with pytest.raises(KeyError):
        plan.save_critique(tmp_path, "P999", [])
