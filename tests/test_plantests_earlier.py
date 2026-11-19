"""Tests for task drafts_see_earlier: a test draft sees the plan's earlier tasks, and writes only new test files.

Tower defense round 2 (2026-11-19): the panel task's draft invented its own upgrade cost and refund because only its
own goal was shown, and two drafts rewrote existing test files because every listed file was "to write".

plantests.build_messages(task, root, example=None, earlier=()):
- earlier = the tasks that come before this one in the plan (dicts with key, title, goal, tests). When it is not
  empty, right after the task's goal comes one part:
  "EARLIER TASKS OF THIS PLAN (done before this one; use their functions, names and numbers exactly as they say):"
  followed by, for each earlier task, "\n\n" + f"{key}: {title}\n{goal}".
  Then, for each earlier task whose first test file exists under root, a part
  context.show_file(root, that file, "TEST OF AN EARLIER TASK"). These parts come before "PROJECT FILES:".
- The last part names only the task's test files that do not exist yet: "WRITE THESE TEST FILES: " + ", ".join(new).
  When every listed test file exists already, it names them all, as before. Each listed test file that exists is
  shown, right before that last part, as context.show_file(root, path, "EXISTING TEST, DO NOT REWRITE").
- With earlier empty and no existing test files the messages are exactly as before.

draft_tests passes earlier = the plan's tasks before the current one, in plan order."""
import json

import pytest

from stratos import config, context, plan, plantests

T1 = {"key": "towers", "title": "Tower levels", "goal": "upgradeCost(tower) = floor(cost * level / 2).",
      "files": ["src/towers.py"], "tests": ["tests/test_towers_up.py"], "protected": [], "after": [], "role": None}
T2 = {"key": "panel", "title": "Panel", "goal": "Show upgradeCost in the panel.", "files": ["src/render.py"],
      "tests": ["tests/test_panel.py", "tests/test_render.py"], "protected": [], "after": ["towers"], "role": None}


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "repo"
    (r / "src").mkdir(parents=True)
    (r / "tests").mkdir()
    (r / "src" / "render.py").write_text("def draw():\n    pass\n", encoding="utf-8")
    (r / "tests" / "test_render.py").write_text("def test_old():\n    pass\n", encoding="utf-8")
    return r


def user_of(task, root, **kw):
    return plantests.build_messages(task, root, example="tests/none.py", **kw)[1]["content"]


def test_earlier_tasks_are_shown(root):
    (root / "tests" / "test_towers_up.py").write_text("def test_cost():\n    pass\n", encoding="utf-8")
    parts = user_of(T2, root, earlier=[T1]).split("\n\n")
    head = ("EARLIER TASKS OF THIS PLAN (done before this one; use their functions, names and numbers exactly as "
            "they say):")
    i = parts.index(head)
    assert parts[i - 1] == "Show upgradeCost in the panel."
    assert parts[i + 1] == "towers: Tower levels\nupgradeCost(tower) = floor(cost * level / 2)."
    user = user_of(T2, root, earlier=[T1])
    shown = context.show_file(root, "tests/test_towers_up.py", "TEST OF AN EARLIER TASK")
    assert shown in user
    assert user.index(head) < user.index(shown) < user.index("PROJECT FILES:")


def test_an_earlier_task_without_its_test_file(root):
    user = user_of(T2, root, earlier=[T1])
    assert "towers: Tower levels" in user and "TEST OF AN EARLIER TASK" not in user


def test_only_new_test_files_are_to_write(root):
    user = user_of(T2, root)
    assert user.endswith("\n\nWRITE THESE TEST FILES: tests/test_panel.py")
    existing = context.show_file(root, "tests/test_render.py", "EXISTING TEST, DO NOT REWRITE")
    assert user.endswith(existing + "\n\nWRITE THESE TEST FILES: tests/test_panel.py")
    assert "EARLIER TASKS" not in user


def test_all_listed_files_exist(root):
    task = dict(T2, tests=["tests/test_render.py"])
    assert user_of(task, root).endswith("WRITE THESE TEST FILES: tests/test_render.py")


class FakeTelemetry:
    def record(self, kind, **fields):
        pass


class FakeGateway:
    def __init__(self):
        self.telemetry = FakeTelemetry()
        self.messages = []

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        self.messages.append(messages)
        return "c", "```python\nnot closed\n"      # nothing is written, so the project stays as it was


def test_draft_tests_passes_the_earlier_tasks(root, tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    monkeypatch.setattr(plantests, "check_draft", lambda r, p: ("collected", ""))
    monkeypatch.setattr(plantests, "suite_leaks", lambda r, p, ignore=(): [])
    pid = plan.save_plan(state, "G", [T1, T2])
    gw = FakeGateway()
    first = plantests.build_messages(T1, root, earlier=[])      # before the first draft is written
    plantests.draft_tests(gw, pid, root, state, log=lambda s: None)
    assert gw.messages[0] == first
    assert gw.messages[1] == plantests.build_messages(T2, root, earlier=[T1])
