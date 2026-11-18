"""Tests for task T072: `stratos plan` shows the planner CONVENTIONS.md and plans in two stages when
config.PLAN_CONVERTER is set.

Conventions: when config.REPO / "CONVENTIONS.md" exists, its text is passed as build_messages(..., conventions=text);
otherwise conventions=None.
Two stages (config.PLAN_CONVERTER is a dict {"model", "effort", "max_tokens"}): each try first asks the planner
(config.PLANNER, role "planner") with messages = plan.build_messages(goal, summary, conventions=...,
system=plan.TEXT_SYSTEM) — gw.ensure_model(planner model) before the call — then the converter:
gw.ensure_model(converter model), gw.chat(plan.convert_messages(planner_text), task="plan", role="plan_converter",
attempt=n, model=..., effort=..., max_tokens=...). Both raw answers are saved as answers/plan-<call_id>.md. The
converter's answer goes to plan.parse_plan. A PlanError adds the PLANNER's text as the assistant turn and the usual
"Your plan was invalid: ..." user turn to the planner's messages, and the next try starts with the planner again.
With PLAN_CONVERTER None, plan works in one stage with plan.SYSTEM, as before (plus the conventions)."""
import json

import pytest

from stratos import __main__ as cli
from stratos import config, plan

GOOD = {"tasks": [{"key": "a", "title": "Add f", "goal": "Add f.", "files": ["stratos/x.py"],
                   "tests": ["tests/test_x.py"]}]}
CONV = {"model": "conv-model", "effort": "none", "max_tokens": 100}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    (tmp_path / "repo").mkdir()
    monkeypatch.setattr(plan, "repo_summary", lambda root: "SUMMARY")
    made = []

    class FakeGateway:
        answers = []

        def __init__(self, telemetry):
            self.telemetry = telemetry
            self.events = []
            made.append(self)

        def ensure_model(self, model):
            self.events.append(("load", model))
            return 0.0

        def chat(self, messages, **kw):
            n = sum(1 for e in self.events if e[0] == "chat") + 1
            self.events.append(("chat", list(messages), kw))
            return f"c{n}", FakeGateway.answers.pop(0)
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    goal = tmp_path / "goal.txt"
    goal.write_text("Make it fly.", encoding="utf-8")
    return FakeGateway, made, goal, tmp_path


def chats(gw):
    return [e for e in gw.events if e[0] == "chat"]


def test_two_stages(env, monkeypatch, capsys):
    gw_cls, made, goal, tmp = env
    monkeypatch.setattr(config, "PLAN_CONVERTER", CONV)
    (tmp / "repo" / "CONVENTIONS.md").write_text("Use gw.chat.", encoding="utf-8")
    gw_cls.answers = ["Key: a\nTitle: Add f", json.dumps(GOOD)]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    gw = made[0]
    loads = [e[1] for e in gw.events if e[0] == "load"]
    assert loads == [config.PLANNER["model"], "conv-model"]
    (_, m1, kw1), (_, m2, kw2) = chats(gw)
    assert m1 == plan.build_messages("Make it fly.", "SUMMARY", conventions="Use gw.chat.", system=plan.TEXT_SYSTEM)
    assert kw1["role"] == "planner" and kw1["model"] == config.PLANNER["model"] and kw1["attempt"] == 1
    assert m2 == plan.convert_messages("Key: a\nTitle: Add f")
    assert kw2 == {"task": "plan", "role": "plan_converter", "attempt": 1, "model": "conv-model", "effort": "none",
                   "max_tokens": 100}
    assert plan.load_plan(config.STATE_DIR, "P001")["tasks"][0]["key"] == "a"
    answers = config.STATE_DIR / "answers"
    assert (answers / "plan-c1.md").read_text(encoding="utf-8") == "Key: a\nTitle: Add f"
    assert (answers / "plan-c2.md").read_text(encoding="utf-8") == json.dumps(GOOD)
    assert "plan P001: 1 tasks" in capsys.readouterr().out


def test_invalid_conversion_goes_back_to_the_planner(env, monkeypatch):
    gw_cls, made, goal, tmp = env
    monkeypatch.setattr(config, "PLAN_CONVERTER", CONV)
    gw_cls.answers = ["plan text one", "not json", "plan text two", json.dumps(GOOD)]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    calls = chats(made[0])
    assert [c[2]["role"] for c in calls] == ["planner", "plan_converter", "planner", "plan_converter"]
    first, third = calls[0][1], calls[2][1]
    assert third[:2] == first and third[2] == {"role": "assistant", "content": "plan text one"}
    assert third[3]["role"] == "user" and third[3]["content"].startswith("Your plan was invalid: ")
    assert calls[3][1] == plan.convert_messages("plan text two") and calls[3][2]["attempt"] == 2
    loads = [e[1] for e in made[0].events if e[0] == "load"]
    assert loads == [config.PLANNER["model"], "conv-model", config.PLANNER["model"], "conv-model"]


def test_gives_up_after_the_tries(env, monkeypatch, capsys):
    gw_cls, made, goal, tmp = env
    monkeypatch.setattr(config, "PLAN_CONVERTER", CONV)
    gw_cls.answers = ["t1", "bad", "t2", "bad"]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 1
    assert "plan invalid: " in capsys.readouterr().err


def test_one_stage_sees_the_conventions(env, monkeypatch):
    gw_cls, made, goal, tmp = env
    (tmp / "repo" / "CONVENTIONS.md").write_text("Use gw.chat.", encoding="utf-8")
    gw_cls.answers = [json.dumps(GOOD)]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    (_, m1, kw1), = chats(made[0])
    assert m1 == plan.build_messages("Make it fly.", "SUMMARY", conventions="Use gw.chat.")
    assert kw1["role"] == "planner"


def test_retry_asks_the_text_planner_for_text(env, monkeypatch):
    """T074: in two stages the planner writes text, so the retry asks for the corrected plan text, not JSON."""
    gw_cls, made, goal, tmp = env
    monkeypatch.setattr(config, "PLAN_CONVERTER", CONV)
    gw_cls.answers = ["plan text one", "not json", "plan text two", json.dumps(GOOD)]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    retry = [c for c in chats(made[0])][2][1][3]["content"]
    assert retry.startswith("Your plan was invalid: ") and retry.endswith(". Answer with the corrected plan text only.")


def test_one_stage_retry_still_asks_for_json(env):
    gw_cls, made, goal, tmp = env
    gw_cls.answers = ["not json", json.dumps(GOOD)]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    retry = [c for c in chats(made[0])][1][1][3]["content"]
    assert retry.endswith(". Answer with the corrected JSON plan only.")
