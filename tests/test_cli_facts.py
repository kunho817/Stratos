"""Tests for task facts_cli: cmd_facts and the stratos facts subcommand in stratos/__main__.py.

cmd_facts(args, store, parser):
  loads plan via plan_mod.load_plan(config.STATE_DIR, args.plan_id);
  creates Gateway(Telemetry(config.STATE_DIR / "telemetry.jsonl"));
  calls facts.derive(gw, plan["goal"]).
  On agree: appends "\n\nWORKED FACTS (computed by two independent programs from the rules -
    read facts from here, never work them out in your head):\n" + render(facts) to goal
    of every task that lacks "WORKED FACTS", saves plan back to its JSON file,
    writes rendered text to state_dir/facts/<pid>.txt,
    prints "facts: agree, <n> facts added to <m> tasks", returns 0.
    n = len(result["facts"]) (fact names); m = tasks whose goal was modified.
  On non-agree: prints "facts: " + result["reason"], returns 0, nothing changes.
  Unknown plan: prints "no such plan: <id>" on stderr, returns 1.
Registered as subcommand "facts" with plan_id argument; usage line in docstring.
"""

import json

import pytest

from stratos import __main__ as cli
from stratos import config
from stratos.plan import PlanNotFound
from stratos.telemetry import Telemetry

HEADER = ("\n\nWORKED FACTS (computed by two independent programs from the rules "
          "- read facts from here, never work them out in your head):\n")

FACTS = {"x": {"1": 2, "3": 4}, "y": {"a": [5]}}
RENDERED = "x:\n  1 -> 2\n  3 -> 4\ny:\n  a -> [5]"


class FakeGateway:
    def __init__(self, tel):
        self.telemetry = tel
        self.models = []
        self.calls = []

    def ensure_model(self, model):
        self.models.append(model)

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        return "c1", "ok"


def _plan(pid="P001", goal="the feature goal", tasks=None):
    if tasks is None:
        tasks = [
            {"key": "T1", "title": "task1", "goal": "do the thing",
             "files": ["a.py"], "tests": ["tests/t1.py"],
             "protected": [], "after": [], "role": "coder"},
            {"key": "T2", "title": "task2", "goal": "already has WORKED FACTS here",
             "files": ["b.py"], "tests": ["tests/t2.py"],
             "protected": [], "after": [], "role": "coder"},
        ]
    return {"id": pid, "goal": goal, "tasks": tasks, "status": "draft", "hash": "abc"}


def _setup(tmp_path, monkeypatch, plan):
    """Point config at tmp_path, write plan file, stub gateway + memory refresh."""
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    (tmp_path / "repo").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("stratos.__main__.Gateway", FakeGateway)
    monkeypatch.setattr(cli, "refresh_memory", lambda: None)
    plans_dir = tmp_path / "state" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / f"{plan['id']}.json").write_text(
        json.dumps(plan, indent=1), encoding="utf-8")
    return tmp_path / "state"


# ---------- registration ----------

def test_facts_in_commands_table():
    # COMMANDS must map "facts" to cmd_facts
    assert "facts" in cli.COMMANDS
    # Expected: COMMANDS["facts"].__name__ == "cmd_facts"
    assert cli.COMMANDS["facts"].__name__ == "cmd_facts"


def test_facts_in_usage_text():
    # The module docstring must include a usage line with PLAN_ID
    # Expected: "facts PLAN_ID" appears in the usage text
    doc = cli.__doc__
    assert "facts" in doc
    # Expected: the usage line follows the pattern seen for other commands
    assert "facts PLAN_ID" in doc


def test_facts_subparser_requires_plan_id(tmp_path, monkeypatch, capsys):
    # Expected: missing plan_id → argparse SystemExit
    _setup(tmp_path, monkeypatch, _plan())
    with pytest.raises(SystemExit):
        cli.main(["facts"])


# ---------- dispatch and gateway ----------

def test_facts_dispatches_and_prints(tmp_path, monkeypatch, capsys):
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    # n=2 fact names; m=1 task (T1 lacks WORKED FACTS, T2 has it)
    # Expected: "facts: agree, 2 facts added to 1 tasks"
    monkeypatch.setattr(cli.facts, "derive",
                        lambda gw, goal: {"facts": FACTS, "reason": "agree"})
    monkeypatch.setattr(cli.facts, "render", lambda f: RENDERED)
    rc = cli.main(["facts", "P001"])
    # Expected: rc 0
    assert rc == 0
    # Expected: n = len({"x":..., "y":...}) = 2, m = 1
    assert capsys.readouterr().out.strip() == "facts: agree, 2 facts added to 1 tasks"


def test_derive_gets_gateway_and_goal(tmp_path, monkeypatch, capsys):
    plan = _plan(goal="the feature goal")
    _setup(tmp_path, monkeypatch, plan)
    seen = []

    def fake_derive(gw, goal):
        seen.append((gw, goal))
        return {"facts": FACTS, "reason": "agree"}
    monkeypatch.setattr(cli.facts, "derive", fake_derive)
    monkeypatch.setattr(cli.facts, "render", lambda f: RENDERED)
    cli.main(["facts", "P001"])
    # Expected: derive called once with (gw, "the feature goal")
    assert len(seen) == 1
    gw, goal = seen[0]
    # Expected: goal is plan["goal"]
    assert goal == "the feature goal"
    # Expected: gw is the FakeGateway created by cmd_facts
    assert isinstance(gw, FakeGateway)


def test_gateway_telemetry_path(tmp_path, monkeypatch, capsys):
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    gw_seen = []

    def fake_derive(gw, goal):
        gw_seen.append(gw)
        return {"facts": FACTS, "reason": "agree"}
    monkeypatch.setattr(cli.facts, "derive", fake_derive)
    monkeypatch.setattr(cli.facts, "render", lambda f: RENDERED)
    cli.main(["facts", "P001"])
    gw = gw_seen[0]
    # Expected: Gateway receives Telemetry(STATE_DIR / "telemetry.jsonl")
    # Expected: gw.telemetry is a Telemetry whose path is STATE_DIR / "telemetry.jsonl"
    expected = str(tmp_path / "state" / "telemetry.jsonl")
    assert isinstance(gw.telemetry, Telemetry)
    # Expected: str(gw.telemetry.path) == expected
    assert str(gw.telemetry.path) == expected


# ---------- agree path ----------

def test_agree_appends_facts_to_clean_tasks(tmp_path, monkeypatch, capsys):
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        lambda gw, goal: {"facts": FACTS, "reason": "agree"})
    monkeypatch.setattr(cli.facts, "render", lambda f: RENDERED)
    cli.main(["facts", "P001"])
    # Expected: T1 goal == "do the thing" + HEADER + RENDERED
    p = json.loads((tmp_path / "state" / "plans" / "P001.json").read_text(encoding="utf-8"))
    t1 = p["tasks"][0]
    # Expected: starts with original goal, ends with HEADER + RENDERED
    assert t1["goal"] == "do the thing" + HEADER + RENDERED
    # Expected: T2 goal unchanged (already has WORKED FACTS)
    assert p["tasks"][1]["goal"] == "already has WORKED FACTS here"


def test_agree_preserves_existing_worked_facts(tmp_path, monkeypatch, capsys):
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        lambda gw, goal: {"facts": FACTS, "reason": "agree"})
    monkeypatch.setattr(cli.facts, "render", lambda f: RENDERED)
    cli.main(["facts", "P001"])
    # Expected: T2 goal is byte-for-byte unchanged
    p = json.loads((tmp_path / "state" / "plans" / "P001.json").read_text(encoding="utf-8"))
    # Expected: T2 "goal" == "already has WORKED FACTS here" (no append)
    assert p["tasks"][1]["goal"] == "already has WORKED FACTS here"
    # Expected: the WORKED FACTS text was NOT appended to T2
    assert not p["tasks"][1]["goal"].endswith(HEADER + RENDERED)


def test_agree_plan_saved_back(tmp_path, monkeypatch, capsys):
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        lambda gw, goal: {"facts": FACTS, "reason": "agree"})
    monkeypatch.setattr(cli.facts, "render", lambda f: RENDERED)
    cli.main(["facts", "P001"])
    # Expected: plan JSON file updated (T1 goal has WORKED FACTS)
    p = json.loads((tmp_path / "state" / "plans" / "P001.json").read_text(encoding="utf-8"))
    # Expected: plan id, tasks count preserved
    assert p["id"] == "P001"
    # Expected: 2 tasks in the plan
    assert len(p["tasks"]) == 2
    # Expected: task 1 has WORKED FACTS in its goal
    assert "WORKED FACTS" in p["tasks"][0]["goal"]


def test_agree_facts_file_written(tmp_path, monkeypatch, capsys):
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        lambda gw, goal: {"facts": FACTS, "reason": "agree"})
    monkeypatch.setattr(cli.facts, "render", lambda f: RENDERED)
    cli.main(["facts", "P001"])
    # Expected: state_dir/facts/P001.txt exists and contains the rendered text
    facts_file = tmp_path / "state" / "facts" / "P001.txt"
    # Expected: facts file exists
    assert facts_file.exists()
    # Expected: facts file content == RENDERED
    assert facts_file.read_text(encoding="utf-8") == RENDERED


def test_agree_all_tasks_clean_m_equals_count(tmp_path, monkeypatch, capsys):
    # Both tasks lack WORKED FACTS; n=2, m=2
    # Expected: "facts: agree, 2 facts added to 2 tasks"
    tasks = [
        {"key": "T1", "title": "a", "goal": "one",
         "files": ["a.py"], "tests": ["tests/t1.py"],
         "protected": [], "after": [], "role": "coder"},
        {"key": "T2", "title": "b", "goal": "two",
         "files": ["b.py"], "tests": ["tests/t2.py"],
         "protected": [], "after": [], "role": "coder"},
    ]
    plan = _plan(tasks=tasks)
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        lambda gw, goal: {"facts": FACTS, "reason": "agree"})
    monkeypatch.setattr(cli.facts, "render", lambda f: RENDERED)
    rc = cli.main(["facts", "P001"])
    # Expected: rc 0
    assert rc == 0
    # Expected: both tasks get WORKED FACTS, so m = 2
    # Expected: n = len({"x":..., "y":...}) = 2, m = 2
    out = capsys.readouterr().out.strip()
    assert out == "facts: agree, 2 facts added to 2 tasks"
    # Expected: both task goals contain WORKED FACTS
    p = json.loads((tmp_path / "state" / "plans" / "P001.json").read_text(encoding="utf-8"))
    # Expected: task T1 goal has WORKED FACTS
    assert "WORKED FACTS" in p["tasks"][0]["goal"]
    # Expected: task T2 goal has WORKED FACTS
    assert "WORKED FACTS" in p["tasks"][1]["goal"]


# ---------- non-agree path ----------

def test_non_agree_prints_reason(tmp_path, monkeypatch, capsys):
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    # Expected: "facts: none" (derive returns reason "none")
    monkeypatch.setattr(cli.facts, "derive",
                        lambda gw, goal: {"facts": None, "reason": "none"})
    rc = cli.main(["facts", "P001"])
    # Expected: rc 0
    assert rc == 0
    # Expected: stdout "facts: none"
    assert capsys.readouterr().out.strip() == "facts: none"


def test_non_agree_plan_unchanged(tmp_path, monkeypatch, capsys):
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        lambda gw, goal: {"facts": None, "reason": "program A failed"})
    rc = cli.main(["facts", "P001"])
    # Expected: rc 0, plan file unchanged, no facts file
    # Expected: rc 0
    assert rc == 0
    # Expected: plan file tasks have no WORKED FACTS
    p = json.loads((tmp_path / "state" / "plans" / "P001.json").read_text(encoding="utf-8"))
    # Expected: T1 goal == "do the thing" (no append)
    assert p["tasks"][0]["goal"] == "do the thing"
    # Expected: facts file NOT written
    assert not (tmp_path / "state" / "facts" / "P001.txt").exists()


# ---------- unknown plan ----------

def test_unknown_plan_returns_1(tmp_path, monkeypatch, capsys):
    _setup(tmp_path, monkeypatch, _plan())
    # P999.json does not exist, so load_plan raises PlanNotFound
    rc = cli.main(["facts", "P999"])
    # Expected: rc 1
    assert rc == 1
    # Expected: stderr "no such plan: P999"
    assert "no such plan: P999" in capsys.readouterr().err
