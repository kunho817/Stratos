"""Tests for task plan_uses: the planner sees "who uses what" from the code map (memory M1).

Tower defense round 2 (2026-11-19): the planner changed tower damage in towers.js without seeing that step.js reads
TOWER_TYPES directly, so upgrades would have done nothing in play.

plan.build_messages(goal, summary, conventions=None, system=None, uses=None): when uses is a non-empty string, the
user content gets, right after "PROJECT FILES:\n{summary}", the part
    "\n\nWHO USES WHAT (when a task changes a name, every user listed here must be changed or checked too):\n" + uses
(before PROJECT CONVENTIONS when there are conventions). uses None or "" -> exactly as before.

`stratos plan`: uses = codemap.uses_summary(codemap.build(config.REPO)) (called through the codemap module, so a
test can replace both), passed as uses=... to plan.build_messages."""

from stratos import __main__ as cli
from stratos import codemap, config, plan

HEAD = "WHO USES WHAT (when a task changes a name, every user listed here must be changed or checked too):\n"


def test_build_messages_with_uses():
    suffix = "TEST FILES: every test file path starts with tests/ and ends with .py."
    user = plan.build_messages("G", "S", uses="TOWER_TYPES (src/towers.js): used by src/step.js:step; tests: none")[1]
    assert user["content"] == ("PROJECT FILES:\nS\n\n" + suffix + "\n\n" + HEAD +
                               "TOWER_TYPES (src/towers.js): used by src/step.js:step; tests: none\n\nFEATURE GOAL:\nG")


def test_build_messages_with_uses_and_conventions():
    suffix = "TEST FILES: every test file path starts with tests/ and ends with .py."
    user = plan.build_messages("G", "S", conventions="C", uses="U")[1]["content"]
    assert user == "PROJECT FILES:\nS\n\n" + suffix + "\n\n" + HEAD + "U\n\nPROJECT CONVENTIONS:\nC\n\nFEATURE GOAL:\nG"


def test_build_messages_without_uses():
    assert plan.build_messages("G", "S", uses="") == plan.build_messages("G", "S")
    assert plan.build_messages("G", "S", conventions="C", uses=None) == plan.build_messages("G", "S", conventions="C")


def test_plan_command_passes_the_uses(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    (tmp_path / "repo").mkdir()
    monkeypatch.setattr(plan, "repo_summary", lambda root: "SUMMARY")
    built = []
    monkeypatch.setattr(codemap, "build", lambda root: built.append(root) or {"test_dir": "tests", "files": {}})
    monkeypatch.setattr(codemap, "uses_summary", lambda cmap: "USES")
    seen = []

    class FakeGateway:
        def __init__(self, telemetry):
            self.telemetry = telemetry

        def ensure_model(self, model):
            return 0.0

        def chat(self, messages, **kw):
            seen.append(messages)
            return "c1", '{"tasks": [{"key": "a", "title": "T", "goal": "G", "files": ["stratos/x.py"], ' \
                         '"tests": ["tests/test_new.py"]}]}'
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    goal = tmp_path / "goal.txt"
    goal.write_text("Make it fly.", encoding="utf-8")
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    assert built == [config.REPO]
    assert seen[0] == plan.build_messages("Make it fly.", "SUMMARY", uses="USES")
