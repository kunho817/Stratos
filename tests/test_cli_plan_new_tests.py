"""Tests for task cli_new_tests: `stratos plan` checks for new test files, `plan-add` protects the tests (plan P010).

plan: after a plan is read (by text, converter or JSON), plan.check_new_tests(tasks, config.REPO) runs. A PlanError
from it is handled like a parse error: the "plan_parse" event of that try has ok=False and error=str(e) (via stays
what read the plan), nothing is saved, and the next try gets the usual "Your plan was invalid: {e}. ..." turn.

plan-add: each task's protected list is its plan's protected list followed by those of its tests that are not in it
yet, so the coder always sees its tests read-only."""
import pytest

from stratos import __main__ as cli
from stratos import config, plan
from stratos.state import Store
from stratos.telemetry import Telemetry

OLD = 'Key: a\nTitle: Add f\nGoal: Add f.\nFiles: stratos/x.py\nTests: tests/test_old.py\n'
NEW = 'Key: a\nTitle: Add f\nGoal: Add f.\nFiles: stratos/x.py\nTests: tests/test_new.py, tests/test_old.py\n'


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(config, "PLAN_AS_TEXT", True)
    monkeypatch.setattr(config, "PLAN_CONVERTER", None)
    (tmp_path / "repo" / "tests").mkdir(parents=True)
    (tmp_path / "repo" / "tests" / "test_old.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(plan, "repo_summary", lambda root: "SUMMARY")
    made = []

    class FakeGateway:
        answers = []

        def __init__(self, telemetry):
            self.telemetry = telemetry
            self.messages = []
            made.append(self)

        def ensure_model(self, model):
            return 0.0

        def chat(self, messages, **kw):
            self.messages.append(list(messages))
            return f"c{len(self.messages)}", FakeGateway.answers.pop(0)
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    goal = tmp_path / "goal.txt"
    goal.write_text("Make it fly.", encoding="utf-8")
    return FakeGateway, made, goal


def parses():
    return [e for e in Telemetry(config.STATE_DIR / "telemetry.jsonl").load() if e["kind"] == "plan_parse"]


def test_an_existing_first_test_file_is_sent_back(env):
    gw_cls, made, goal = env
    gw_cls.answers = [OLD, NEW]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    err = ("Task a: its first test file 'tests/test_old.py' already exists. Give every task a new test file first; "
           "existing test files may follow it.")
    e1, e2 = parses()
    assert (e1["via"], e1["ok"], e1["error"]) == ("text", False, err)
    assert (e2["via"], e2["ok"]) == ("text", True)
    second = made[0].messages[1]
    assert second[-2] == {"role": "assistant", "content": OLD}
    assert second[-1] == {"role": "user",
                          "content": f"Your plan was invalid: {err}. Answer with the corrected plan text only."}
    p = plan.load_plan(config.STATE_DIR, "P001")
    assert p["tasks"][0]["tests"] == ["tests/test_new.py", "tests/test_old.py"]


def test_it_gives_up_after_the_tries(env, capsys):
    gw_cls, made, goal = env
    gw_cls.answers = [OLD, OLD]
    assert cli.main(["plan", "--goal-file", str(goal), "--tries", "2"]) == 1
    assert "already exists" in capsys.readouterr().err
    assert not list((config.STATE_DIR / "plans").glob("*.json")) if (config.STATE_DIR / "plans").exists() else True


def test_plan_add_protects_the_tests(env):
    tasks = [{"key": "a", "title": "A", "goal": "g", "files": ["stratos/x.py"],
              "tests": ["tests/test_a.py", "tests/test_old.py"], "protected": ["stratos/y.py", "tests/test_old.py"],
              "after": [], "role": "coder"},
             {"key": "b", "title": "B", "goal": "g", "files": ["stratos/y.py"], "tests": ["tests/test_b.py"],
              "protected": [], "after": ["a"], "role": "coder"}]
    pid = plan.save_plan(config.STATE_DIR, "G", tasks)
    assert cli.main(["plan-add", pid]) == 0
    store = Store(config.STATE_DIR)
    assert store.get("T001")["protected"] == ["stratos/y.py", "tests/test_old.py", "tests/test_a.py"]
    assert store.get("T002")["protected"] == ["tests/test_b.py"]
    assert plan.load_plan(config.STATE_DIR, pid)["tasks"][0]["protected"] == ["stratos/y.py", "tests/test_old.py"]
