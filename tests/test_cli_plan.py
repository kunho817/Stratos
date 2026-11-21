"""Tests for task T062: `stratos plan --goal-file F [--tries N]` and `stratos plan-add <plan id>` (stratos/plan.py, T061).

plan: reads the goal file, gw = Gateway(Telemetry(config.STATE_DIR / "telemetry.jsonl")), gw.ensure_model(planner
    model), messages = plan.build_messages(goal, plan.repo_summary(config.REPO)), then up to --tries (default 2)
    calls gw.chat(messages, task="plan", role="planner", attempt=n, model=..., effort=..., max_tokens=...) with the
    settings of config.PLANNER, plus reasoning_budget=config.PLANNER["reasoning_budget"] when that is present and not
    None. The answer goes through plan.parse_plan. A PlanError adds the answer as {"role": "assistant", ...} and
    {"role": "user", "content": f"Your plan was invalid: {e}. Answer with the corrected JSON plan only."} to the
    messages and tries again. On success: pid = plan.save_plan(config.STATE_DIR, goal, tasks); prints
    f"plan {pid}: {len(tasks)} tasks", then per task f"  {key}. {title}" and a line with its files and tests; returns 0.
    When every try is invalid: prints "plan invalid: <reason>" on stderr, saves nothing, returns 1.
plan-add: loads the plan (unknown id: "no such plan: <id>" on stderr, return 1; status not "draft": "plan <id> was
    already added" on stderr, return 1). Adds each task in order exactly as `stratos add` does (role None -> the rules'
    role decision with its telemetry and Jev shadow, like add without --role), with "after" keys turned into the task
    ids just added. Then plan.mark_added(config.STATE_DIR, pid, {key: task id}), a telemetry event
    record("plan", plan=pid, tasks=<count>, edited=plan.edited(<the plan as loaded>)), prints "added <id>: <title>"
    per task (like add), returns 0. The add command's body is shared with plan-add, so add behaves as before."""
import json

import pytest

from stratos import __main__ as cli
from stratos import config, plan
from stratos.state import Store
from stratos.telemetry import Telemetry

GOOD = {"tasks": [
    {"key": "a", "title": "Add f", "goal": "Add f to x.", "files": ["stratos/x.py"], "tests": ["tests/test_x.py"]},
    {"key": "b", "title": "Use f", "goal": "Call f in y.", "files": ["stratos/y.py", "stratos/z.py"],
     "tests": ["tests/test_y.py"], "protected": ["stratos/x.py"], "after": ["a"], "role": "coder"},
]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(plan, "repo_summary", lambda root: "SUMMARY")
    made = []

    class FakeGateway:
        answers = []

        def __init__(self, telemetry):
            self.telemetry = telemetry
            self.models, self.calls = [], []
            made.append(self)

        def ensure_model(self, model):
            self.models.append(model)
            return 0.0

        def chat(self, messages, **kw):
            self.calls.append((list(messages), kw))
            return f"c{len(self.calls)}", FakeGateway.answers.pop(0)
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    goal = tmp_path / "goal.txt"
    goal.write_text("Make it fly.", encoding="utf-8")
    return FakeGateway, made, goal, tmp_path


def test_plan_saves_a_valid_plan(env, capsys):
    gw_cls, made, goal, tmp = env
    gw_cls.answers = ["```json\n" + json.dumps(GOOD) + "\n```"]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    gw = made[0]
    assert gw.models == [config.PLANNER["model"]]
    messages, kw = gw.calls[0]
    assert messages == plan.build_messages("Make it fly.", "SUMMARY")
    want = {"task": "plan", "role": "planner", "attempt": 1, "model": config.PLANNER["model"],
            "effort": config.PLANNER["effort"], "max_tokens": config.PLANNER["max_tokens"]}
    if config.PLANNER.get("reasoning_budget") is not None:
        want["reasoning_budget"] = config.PLANNER["reasoning_budget"]
    assert kw == want
    assert str(gw.telemetry.path).endswith("telemetry.jsonl")
    p = plan.load_plan(config.STATE_DIR, "P001")
    assert p["status"] == "draft" and p["goal"] == "Make it fly." and [t["key"] for t in p["tasks"]] == ["a", "b"]
    out = capsys.readouterr().out
    assert "plan P001: 2 tasks" in out and "  a. Add f" in out and "  b. Use f" in out
    assert "stratos/z.py" in out and "tests/test_y.py" in out


def test_plan_retries_with_the_reason(env, capsys):
    gw_cls, made, goal, tmp = env
    bad = json.dumps({"tasks": [{"title": "x", "goal": "g", "files": [], "tests": ["tests/t.py"]}]})
    gw_cls.answers = [bad, json.dumps(GOOD)]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    first, _ = made[0].calls[0]
    second, kw = made[0].calls[1]
    assert kw["attempt"] == 2
    assert second[:2] == first and second[2] == {"role": "assistant", "content": bad}
    assert second[3]["role"] == "user" and second[3]["content"].startswith("Your plan was invalid: ")
    assert second[3]["content"].endswith(". Answer with the corrected JSON plan only.")
    assert plan.load_plan(config.STATE_DIR, "P001")["tasks"][0]["key"] == "a"


def test_plan_gives_up(env, capsys):
    gw_cls, made, goal, tmp = env
    gw_cls.answers = ["no plan", "still no plan", "never"]
    assert cli.main(["plan", "--goal-file", str(goal), "--tries", "3"]) == 1
    assert len(made[0].calls) == 3
    assert "plan invalid: " in capsys.readouterr().err
    assert not (config.STATE_DIR / "plans").exists() or not list((config.STATE_DIR / "plans").glob("*.json"))


def test_plan_add(env, capsys):
    tasks = plan.parse_plan(json.dumps(GOOD))
    tasks[0]["role"] = None
    pid = plan.save_plan(config.STATE_DIR, "Make it fly.", tasks)
    assert cli.main(["plan-add", pid]) == 0
    store = Store(config.STATE_DIR)
    t1, t2 = store.get("T001"), store.get("T002")
    assert (t1["title"], t1["goal"], t1["files"], t1["tests"], t1["protected"], t1["after"]) == \
        ("Add f", "Add f to x.", ["stratos/x.py"], ["tests/test_x.py"], ["tests/test_x.py"], [])  # P010: tests protected
    assert t1["role"] == "coder"                      # the rules' choice for a one-file task without flow words
    assert t1.get("role_decision", {}).get("choice") == "coder"
    assert (t2["role"], t2["after"], t2["protected"], t2["files"]) == \
        ("coder", ["T001"], ["stratos/x.py", "tests/test_y.py"], ["stratos/y.py", "stratos/z.py"])
    p = plan.load_plan(config.STATE_DIR, pid)
    assert p["status"] == "added" and p["task_ids"] == {"a": "T001", "b": "T002"}
    events = Telemetry(config.STATE_DIR / "telemetry.jsonl").load()
    assert [e["task"] for e in events if e["kind"] == "decision" and e.get("decision") == "role"] == ["T001"]
    (pe,) = [e for e in events if e["kind"] == "plan"]
    assert (pe["plan"], pe["tasks"], pe["edited"]) == (pid, 2, False)
    out = capsys.readouterr().out
    assert "added T001: Add f" in out and "added T002: Use f" in out


def test_plan_add_records_an_edited_plan(env):
    pid = plan.save_plan(config.STATE_DIR, "Make it fly.", plan.parse_plan(json.dumps(GOOD)))
    path = config.STATE_DIR / "plans" / f"{pid}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tasks"][1]["goal"] = "Call f in y, and log it."
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert cli.main(["plan-add", pid]) == 0
    assert Store(config.STATE_DIR).get("T002")["goal"] == "Call f in y, and log it."
    (pe,) = [e for e in Telemetry(config.STATE_DIR / "telemetry.jsonl").load() if e["kind"] == "plan"]
    assert pe["edited"] is True


def test_plan_add_refuses_unknown_and_added_plans(env, capsys):
    assert cli.main(["plan-add", "P404"]) == 1
    assert "no such plan: P404" in capsys.readouterr().err
    pid = plan.save_plan(config.STATE_DIR, "g", plan.parse_plan(json.dumps(GOOD)))
    assert cli.main(["plan-add", pid]) == 0
    capsys.readouterr()
    assert cli.main(["plan-add", pid]) == 1
    assert f"plan {pid} was already added" in capsys.readouterr().err
    assert len(Store(config.STATE_DIR).tasks()) == 2


def test_plan_add_keeps_a_search_output(env, capsys):
    """(Claude, 2026-11-21, Lantern) a plan task's "output" (a search task, P16) reaches the stored task."""
    tasks = plan.parse_plan(json.dumps(GOOD))
    tasks[0]["output"] = "data/levels.json"
    pid = plan.save_plan(config.STATE_DIR, "Make it fly.", tasks)
    assert cli.main(["plan-add", pid]) == 0
    store = Store(config.STATE_DIR)
    assert store.get("T001")["output"] == "data/levels.json" and "output" not in store.get("T002")
