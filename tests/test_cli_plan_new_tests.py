"""Tests for task cli_new_tests: `stratos plan` checks for new test files, `plan-add` protects the tests (plan P010).

plan: after a plan is read (by text, converter or JSON), plan.fix_new_tests(tasks, config.REPO) puts a new first
test file in front where needed and its messages are printed (task plan_fix; before, check_new_tests sent the plan
back, and Swift did not fix it in three tries on Ledger round 2).

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


def test_an_existing_first_test_file_is_fixed_by_code(env, capsys):
    # (task plan_fix, Ledger round 2: Swift kept the existing file first in every retry, so code fixes it now)
    gw_cls, made, goal = env
    gw_cls.answers = [OLD]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    (e1,) = parses()
    assert (e1["via"], e1["ok"]) == ("text", True) and len(made[0].messages) == 1
    assert "Task a: added the new test file tests/test_a.py (tests/test_old.py already existed)" in capsys.readouterr().out
    p = plan.load_plan(config.STATE_DIR, "P001")
    assert p["tasks"][0]["tests"] == ["tests/test_a.py", "tests/test_old.py"]


def test_a_plan_with_a_new_first_file_is_kept(env):
    gw_cls, made, goal = env
    gw_cls.answers = [NEW]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    assert plan.load_plan(config.STATE_DIR, "P001")["tasks"][0]["tests"] == ["tests/test_new.py", "tests/test_old.py"]


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
