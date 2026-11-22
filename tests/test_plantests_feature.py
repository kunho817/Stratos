"""Tests for task plantests-feature: build_messages gains a feature keyword; draft_tests passes the plan goal.

stratos/plantests.py, build_messages(task, root, example=None, earlier=(), memory=None, old=(), feature=None):
  When feature is a non-empty string, the part
  "THE WHOLE FEATURE (this task is one part of it; its exact formats and numbers hold):\n" + feature
  is inserted right after the task's goal part (before PROJECT FILES: and before EARLIER TASKS).
  When feature is None or "", no such part appears.

draft_tests(gw, plan_id, root, state_dir, log=print): passes feature=p["goal"] (the plan's feature goal)
  to build_messages for every task in the plan.
"""
import json

import pytest

from stratos import codemap, config, context, plan, plantests


T1 = {"key": "a", "title": "Add f", "goal": "Add f to x.py.",
      "files": ["pkg/x.py"], "tests": ["tests/test_x.py"],
      "protected": [], "after": [], "role": None}

T2 = {"key": "b", "title": "Use f", "goal": "Call f in y.py.",
      "files": ["pkg/y.py"], "tests": ["tests/test_y.py"],
      "protected": [], "after": ["a"], "role": None}

FEATURE = "Levels must be 1-5; score = sum(level) * 10; grid 10x10."


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "repo"
    (r / "pkg").mkdir(parents=True)
    (r / "tests").mkdir()
    (r / "pkg" / "x.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
    (r / "pkg" / "y.py").write_text("from pkg.x import f\n\ndef g():\n    return f(1)\n", encoding="utf-8")
    return r


def user_of(task, root, **kw):
    """Return the user content of build_messages for task."""
    return plantests.build_messages(task, root, example="tests/none.py", **kw)[1]["content"]


def test_feature_block_inserted_after_goal(root):
    user = user_of(T1, root, feature=FEATURE)
    # The goal part is "Add f to x.py." — the feature block must come right after it.
    feature_part = "THE WHOLE FEATURE (this task is one part of it; its exact formats and numbers hold):\n" + FEATURE
    # Split on double-newline: the goal part is parts[1], the feature part is parts[2].
    parts = user.split("\n\n")
    # parts[0] = "TASK a: Add f", parts[1] = goal
    assert parts[1] == "Add f to x.py."
    assert parts[2] == feature_part
    # The feature part sits before PROJECT FILES:
    assert parts[2] < parts[3]
    assert parts[3].startswith("PROJECT FILES:")
    # Verify the exact string
    expected = ("THE WHOLE FEATURE (this task is one part of it; "
                "its exact formats and numbers hold):\n" + FEATURE)
    assert parts[2] == expected


def test_feature_none_omits_block(root):
    user = user_of(T1, root, feature=None)
    # No feature block: goal is immediately followed by PROJECT FILES:
    parts = user.split("\n\n")
    assert parts[1] == "Add f to x.py."
    assert parts[2].startswith("PROJECT FILES:")
    assert "THE WHOLE FEATURE" not in user


def test_feature_empty_string_omits_block(root):
    user = user_of(T1, root, feature="")
    # Empty string is not a non-empty string, so no feature block.
    assert "THE WHOLE FEATURE" not in user
    parts = user.split("\n\n")
    assert parts[1] == "Add f to x.py."
    assert parts[2].startswith("PROJECT FILES:")


def test_feature_before_earlier_tasks(root):
    # When both feature and earlier are present, the feature block comes right
    # after the goal, before EARLIER TASKS and PROJECT FILES.
    user = user_of(T2, root, feature=FEATURE, earlier=[T1])
    feature_part = ("THE WHOLE FEATURE (this task is one part of it; "
                    "its exact formats and numbers hold):\n" + FEATURE)
    # order: goal -> feature -> EARLIER TASKS header -> ... -> PROJECT FILES
    i_goal = user.index("Call f in y.py.")
    i_feat = user.index("THE WHOLE FEATURE")
    i_earlier = user.index("EARLIER TASKS OF THIS PLAN")
    i_proj = user.index("PROJECT FILES:")
    # Step-by-step: goal at i_goal, feature at i_feat, earlier at i_earlier, project at i_proj
    assert i_goal < i_feat < i_earlier < i_proj


class FakeTelemetry:
    def record(self, kind, **fields):
        pass


class FakeGateway:
    def __init__(self, answer):
        self.telemetry = FakeTelemetry()
        self._answer = answer
        self.calls = []

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        return "c", self._answer


def _run_draft(plan_id, root, state, monkeypatch, feature, tasks, answer):
    """Run draft_tests with a fake gateway and capture build_messages kwargs."""
    pid = plan.save_plan(state, feature, tasks)
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    monkeypatch.setattr(plantests, "check_draft", lambda r, p: ("collected", ""))
    monkeypatch.setattr(plantests, "suite_leaks", lambda r, p, ignore=(): [])
    monkeypatch.setattr(plantests, "draft_problems", lambda r, p: [])
    monkeypatch.setattr(plantests, "risky_patterns", lambda t: [])
    monkeypatch.setattr(codemap, "build", lambda r: {"test_dir": "tests", "files": {}, "imports": {}})

    captured_kwargs = []
    original = plantests.build_messages

    def spy(task, r, **kw):
        captured_kwargs.append(kw)
        return original(task, r, **kw)

    monkeypatch.setattr(plantests, "build_messages", spy)
    gw = FakeGateway(answer)
    plantests.draft_tests(gw, pid, root, state, log=lambda s: None)
    return captured_kwargs


def test_draft_tests_passes_plan_goal(root, tmp_path, monkeypatch):
    """Every build_messages call in draft_tests gets feature = the plan's goal."""
    state = tmp_path / "state"
    answer = "FILE: tests/test_x.py\n```python\ndef test_a():\n    assert True\n```\n"
    captured = _run_draft("P001", root, state, monkeypatch, FEATURE, [T1, T2], answer)
    # Two tasks in the plan -> two build_messages calls, both with feature=FEATURE.
    # Step: len(captured) == 2 (tasks T1, T2 in plan order).
    assert len(captured) == 2
    # Step: captured[0]["feature"] == FEATURE (the plan goal).
    assert captured[0]["feature"] == FEATURE
    # Step: captured[1]["feature"] == FEATURE.
    assert captured[1]["feature"] == FEATURE


def test_draft_tests_single_task_feature(root, tmp_path, monkeypatch):
    """A plan with one task still passes the plan goal as feature."""
    state = tmp_path / "state"
    goal = "Grid is 10x10; levels 1-5."
    answer = "FILE: tests/test_x.py\n```python\ndef test_z():\n    pass\n```\n"
    captured = _run_draft("P002", root, state, monkeypatch, goal, [T1], answer)
    # One task -> one build_messages call.
    # Step: captured[0]["feature"] == goal.
    assert len(captured) == 1
    assert captured[0]["feature"] == goal
