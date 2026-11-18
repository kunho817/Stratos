"""Tests for tasks T072/T074/T076: `stratos plan` with the project's conventions and text planning.

Conventions: when config.REPO / "CONVENTIONS.md" exists, its text is passed as build_messages(..., conventions=text);
otherwise conventions=None.

Text planning (config.PLAN_AS_TEXT True): messages = plan.build_messages(goal, summary, conventions=...,
system=plan.TEXT_SYSTEM). Each try: gw.ensure_model(planner model), the planner call (role "planner"), its raw answer
saved as answers/plan-<call_id>.md, then plan.parse_text_plan(text):
- it reads the text: done (telemetry record("plan_parse", attempt=n, via="text", ok=True)).
- PlanFormatError (not the format) and config.PLAN_CONVERTER set: gw.ensure_model(converter model),
  gw.chat(plan.convert_messages(text), task="plan", role="plan_converter", attempt=n, model, effort, max_tokens),
  its raw answer saved too, then plan.parse_plan(converter answer) (record "plan_parse" via="converter").
  PlanFormatError and no converter: handled like any PlanError (via="text", ok=False).
- any PlanError: record "plan_parse" with ok=False and error=str(e); the planner's text becomes the assistant turn
  and the user turn is f"Your plan was invalid: {e}. Answer with the corrected plan text only."; next try.
PLAN_AS_TEXT False: one stage with plan.SYSTEM, plan.parse_plan, record "plan_parse" via="json", and the retry turn
ends ". Answer with the corrected JSON plan only." The converter is never used then."""
import json

import pytest

from stratos import __main__ as cli
from stratos import config, plan
from stratos.telemetry import Telemetry

GOOD = {"tasks": [{"key": "a", "title": "Add f", "goal": "Add f.", "files": ["stratos/x.py"],
                   "tests": ["tests/test_x.py"]}]}
TEXT = 'Key: a\nTitle: Add f\nGoal: Add f, print "done".\nFiles: stratos/x.py\nTests: tests/test_x.py\n'
BAD_TEXT = "Key: a\nTitle: Add f\nGoal: g\nFiles: stratos/x.py\nTests: tests/test_x.py\nAfter: zz\n"
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


def loads(gw):
    return [e[1] for e in gw.events if e[0] == "load"]


def parses():
    return [e for e in Telemetry(config.STATE_DIR / "telemetry.jsonl").load() if e["kind"] == "plan_parse"]


def test_text_plan_read_by_code(env, monkeypatch, capsys):
    gw_cls, made, goal, tmp = env
    monkeypatch.setattr(config, "PLAN_AS_TEXT", True)
    monkeypatch.setattr(config, "PLAN_CONVERTER", CONV)
    (tmp / "repo" / "CONVENTIONS.md").write_text("Use gw.chat.", encoding="utf-8")
    gw_cls.answers = [TEXT]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    gw = made[0]
    assert loads(gw) == [config.PLANNER["model"]]          # the converter is not needed
    (_, m1, kw1), = chats(gw)
    assert m1 == plan.build_messages("Make it fly.", "SUMMARY", conventions="Use gw.chat.", system=plan.TEXT_SYSTEM)
    assert kw1["role"] == "planner" and kw1["attempt"] == 1
    p = plan.load_plan(config.STATE_DIR, "P001")
    assert p["tasks"][0]["goal"] == 'Add f, print "done".'
    assert (config.STATE_DIR / "answers" / "plan-c1.md").read_text(encoding="utf-8") == TEXT
    (e,) = parses()
    assert (e["attempt"], e["via"], e["ok"]) == (1, "text", True)
    assert "plan P001: 1 tasks" in capsys.readouterr().out


def test_text_not_in_the_format_goes_to_the_converter(env, monkeypatch):
    gw_cls, made, goal, tmp = env
    monkeypatch.setattr(config, "PLAN_AS_TEXT", True)
    monkeypatch.setattr(config, "PLAN_CONVERTER", CONV)
    gw_cls.answers = ["1. Add f to stratos/x.py, tested by tests/test_x.py", json.dumps(GOOD)]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    gw = made[0]
    assert loads(gw) == [config.PLANNER["model"], "conv-model"]
    (_, _, kw1), (_, m2, kw2) = chats(gw)
    assert m2 == plan.convert_messages("1. Add f to stratos/x.py, tested by tests/test_x.py")
    assert kw2 == {"task": "plan", "role": "plan_converter", "attempt": 1, "model": "conv-model", "effort": "none",
                   "max_tokens": 100}
    assert (config.STATE_DIR / "answers" / "plan-c2.md").read_text(encoding="utf-8") == json.dumps(GOOD)
    (e,) = parses()
    assert (e["via"], e["ok"]) == ("converter", True)


def test_a_rule_break_goes_back_to_the_planner(env, monkeypatch):
    gw_cls, made, goal, tmp = env
    monkeypatch.setattr(config, "PLAN_AS_TEXT", True)
    monkeypatch.setattr(config, "PLAN_CONVERTER", CONV)
    gw_cls.answers = [BAD_TEXT, TEXT]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    gw = made[0]
    assert loads(gw) == [config.PLANNER["model"], config.PLANNER["model"]]
    (_, m1, _), (_, m2, kw2) = chats(gw)
    assert m2[:2] == m1 and m2[2] == {"role": "assistant", "content": BAD_TEXT}
    assert m2[3]["role"] == "user" and m2[3]["content"].startswith("Your plan was invalid: ")
    assert m2[3]["content"].endswith(". Answer with the corrected plan text only.") and "zz" in m2[3]["content"]
    assert kw2["attempt"] == 2
    e1, e2 = parses()
    assert (e1["via"], e1["ok"]) == ("text", False) and "zz" in e1["error"]
    assert (e2["via"], e2["ok"]) == ("text", True)


def test_no_converter_and_not_the_format(env, monkeypatch, capsys):
    gw_cls, made, goal, tmp = env
    monkeypatch.setattr(config, "PLAN_AS_TEXT", True)
    gw_cls.answers = ["no plan here", "still nothing"]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 1
    assert loads(made[0]) == [config.PLANNER["model"], config.PLANNER["model"]]
    assert [(e["via"], e["ok"]) for e in parses()] == [("text", False), ("text", False)]
    assert "plan invalid: " in capsys.readouterr().err


def test_json_mode(env, monkeypatch):
    gw_cls, made, goal, tmp = env
    monkeypatch.setattr(config, "PLAN_CONVERTER", CONV)            # never used in JSON mode
    (tmp / "repo" / "CONVENTIONS.md").write_text("Use gw.chat.", encoding="utf-8")
    gw_cls.answers = ["not json", json.dumps(GOOD)]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    gw = made[0]
    assert loads(gw) == [config.PLANNER["model"], config.PLANNER["model"]]
    (_, m1, _), (_, m2, _) = chats(gw)
    assert m1 == plan.build_messages("Make it fly.", "SUMMARY", conventions="Use gw.chat.")
    assert m2[3]["content"].endswith(". Answer with the corrected JSON plan only.")
    assert [(e["via"], e["ok"]) for e in parses()] == [("json", False), ("json", True)]
