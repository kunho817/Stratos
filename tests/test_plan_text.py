"""Tests for task T075: plan.parse_text_plan(text), reading a plan the planner wrote as text (plan.TEXT_SYSTEM).

AgentWorld, asked to turn such text into JSON, copied goals that hold double quotes without escaping them and broke
the JSON twice (2026-11-18). The format is regular, so code reads it:

- A line "<Field>: <value>" starts a field, for the fields Key, Title, Goal, Files, Tests, Protected, After, Role
  (case as written). The label may be preceded by spaces, "-", "*", "#" or wrapped in "**" (e.g. "**Key:**" or
  "- Key:"). A line that starts no field continues the previous field's value (joined with "\n"); blank lines end
  nothing. Each "Key:" line starts a new task; text before the first "Key:" is ignored.
- Values are stripped. Files, Tests, Protected and After are comma-separated lists; items are stripped, surrounding
  backticks are removed, empty items dropped. Role "coder" or "coder_hard" (backticks removed); anything else
  (empty, "none", "null", "-") is None. Missing fields are left out, so parse_plan's defaults and checks apply.
- The tasks are then checked exactly like a JSON plan: the result is parse_plan(json.dumps({"tasks": [...]})), so its
  PlanError reasons apply (for example an "after" key that is not earlier).
- No "Key:" line at all raises PlanFormatError (a subclass of PlanError): the text is not in the format."""
import pytest

from stratos import plan

TEXT = '''Here is my plan.

Key: summary
Title: plan_summary in report.py
Goal: Add a pure function plan_summary(plans, events). Count "test_draft" events
by their "status" field.
Files: stratos/report.py
Tests: tests/test_report_plans.py
Protected: stratos/plan.py, `stratos/telemetry.py`
After:
Role: coder

- **Key:** cli
- **Title:** stratos report --plans
- **Goal:** Print "no plans yet" when there are none.
- **Files:** `stratos/__main__.py`
- **Tests:** tests/test_cli_report_plans.py
- **Protected:** stratos/report.py
- **After:** summary
- **Role:** `coder_hard`
'''


def test_reads_both_styles():
    tasks = plan.parse_text_plan(TEXT)
    assert tasks == [
        {"key": "summary", "title": "plan_summary in report.py",
         "goal": 'Add a pure function plan_summary(plans, events). Count "test_draft" events\nby their "status" field.',
         "files": ["stratos/report.py"], "tests": ["tests/test_report_plans.py"],
         "protected": ["stratos/plan.py", "stratos/telemetry.py"], "after": [], "role": "coder"},
        {"key": "cli", "title": "stratos report --plans", "goal": 'Print "no plans yet" when there are none.',
         "files": ["stratos/__main__.py"], "tests": ["tests/test_cli_report_plans.py"],
         "protected": ["stratos/report.py"], "after": ["summary"], "role": "coder_hard"},
    ]


@pytest.mark.parametrize("role", ["", "none", "null", "-", "anything"])
def test_other_roles_are_none(role):
    text = f"Key: a\nTitle: t\nGoal: g\nFiles: stratos/a.py\nTests: tests/test_a.py\nRole: {role}\n"
    assert plan.parse_text_plan(text)[0]["role"] is None


def test_missing_optional_fields_use_the_defaults():
    tasks = plan.parse_text_plan("Key: a\nTitle: t\nGoal: g\nFiles: stratos/a.py, , stratos/b.py\nTests: tests/test_a.py")
    assert tasks[0]["files"] == ["stratos/a.py", "stratos/b.py"]
    assert (tasks[0]["protected"], tasks[0]["after"], tasks[0]["role"]) == ([], [], None)


def test_plan_checks_still_apply():
    bad = "Key: a\nTitle: t\nGoal: g\nFiles: stratos/a.py\nTests: tests/test_a.py\nAfter: zz\n"
    with pytest.raises(plan.PlanError) as e:
        plan.parse_text_plan(bad)
    assert not isinstance(e.value, plan.PlanFormatError) and "zz" in str(e.value)
    with pytest.raises(plan.PlanError):
        plan.parse_text_plan("Key: a\nTitle: t\nGoal: g\nFiles: tests/test_a.py\nTests: tests/test_b.py\n")


def test_not_the_format():
    for text in ["", "I could not plan this.", '{"tasks": []}']:
        with pytest.raises(plan.PlanFormatError):
            plan.parse_text_plan(text)
    assert issubclass(plan.PlanFormatError, plan.PlanError)


def test_none_words_in_list_fields_mean_empty():
    """Memory A/B (2026-11-19): 4 of 9 plans failed because Swift wrote "After: none" or "After: (none)". In the list
    fields (Files, Tests, Protected, After) an item that is, case-insensitively, one of none, (none), -, n/a, nothing,
    [] is dropped, so such a field is empty."""
    text = ("Key: a\nTitle: A\nGoal: g\nFiles: stratos/a.py\nTests: tests/test_a.py\nProtected: None\nAfter: none\n\n"
            "Key: b\nTitle: B\nGoal: g\nFiles: stratos/b.py\nTests: tests/test_b.py\nProtected: -\nAfter: (none)\n\n"
            "Key: c\nTitle: C\nGoal: g\nFiles: stratos/c.py\nTests: tests/test_c.py\nProtected: n/a\nAfter: a, b, []\n")
    tasks = plan.parse_text_plan(text)
    assert [(t["key"], t["protected"], t["after"]) for t in tasks] == [("a", [], []), ("b", [], []), ("c", [], ["a", "b"])]
