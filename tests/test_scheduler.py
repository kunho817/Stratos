"""Tests for task T003: stratos/scheduler.py orders tasks so the model changes as rarely as possible.

plan(tasks, roles, current_model) -> (order, blocked)
  tasks: dicts with id, status, and optionally role (default "coder") and after (ids that must be done first)
  roles: role -> {"model": ...} (like config.ROLES)
  order: ids of the "todo" tasks, in run order
  blocked: ids of "todo" tasks that can never run (sorted)
switches(order, tasks, roles, current_model) -> how many times the model changes along that order
"""
from stratos.scheduler import plan, switches

ROLES = {"coder": {"model": "tiel"}, "coder_hard": {"model": "flint"}}


def t(id, role="coder", after=(), status="todo"):
    return {"id": id, "status": status, "role": role, "after": list(after)}


def test_groups_tasks_by_model_starting_with_the_loaded_one():
    tasks = [t("T1", "coder_hard"), t("T2"), t("T3", "coder_hard"), t("T4")]
    order, blocked = plan(tasks, ROLES, "tiel")
    assert order == ["T2", "T4", "T1", "T3"]
    assert blocked == []
    assert switches(order, tasks, ROLES, "tiel") == 1
    assert switches(["T1", "T2", "T3", "T4"], tasks, ROLES, "tiel") == 4


def test_dependencies_come_first():
    tasks = [t("T1", "coder_hard"), t("T2", after=["T1"]), t("T3")]
    order, _ = plan(tasks, ROLES, "tiel")
    assert order == ["T3", "T1", "T2"]


def test_role_defaults_to_coder_and_after_to_nothing():
    tasks = [{"id": "T1", "status": "todo"}, t("T2", "coder_hard")]
    order, _ = plan(tasks, ROLES, "flint")
    assert order == ["T2", "T1"]


def test_only_todo_tasks_are_planned_and_done_tasks_satisfy_dependencies():
    tasks = [t("T1", status="done"), t("T2", after=["T1"]), t("T3", status="running")]
    order, blocked = plan(tasks, ROLES, "tiel")
    assert order == ["T2"]
    assert blocked == []


def test_impossible_tasks_are_blocked():
    tasks = [t("T1", after=["T9"]),                     # unknown task
             t("T2", after=["T3"]), t("T3", after=["T2"]),  # a cycle
             t("T4", after=["T5"]), t("T5", status="needs_human"),  # waits on a task that failed
             t("T6", after=["T2"]),                     # waits on a blocked task
             t("T7")]
    order, blocked = plan(tasks, ROLES, "tiel")
    assert order == ["T7"]
    assert blocked == ["T1", "T2", "T3", "T4", "T6"]


def test_no_model_loaded_starts_with_the_lowest_id():
    tasks = [t("T2"), t("T1", "coder_hard"), t("T3", "coder_hard")]
    order, _ = plan(tasks, ROLES, None)
    assert order == ["T1", "T3", "T2"]
    assert switches(order, tasks, ROLES, None) == 2   # None -> flint counts as a change


def test_empty():
    assert plan([], ROLES, "tiel") == ([], [])
    assert switches([], [], ROLES, "tiel") == 0
