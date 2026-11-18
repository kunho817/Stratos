"""Tests for task T071: plan.py for two-stage planning and the project's conventions, and a stricter parse_plan.

An offline comparison (2026-11-18, three feature goals) found that plans improve when the planner sees the project's
conventions (CONVENTIONS.md) and writes the plan as text that AgentWorld turns into JSON; and that every variant
still made tasks whose only files are test files, which the prompt rules did not stop.

- parse_plan refuses a task whose files are all under "tests/", and a task whose files include one of its own
  "tests" paths (tests are written before the task runs). The PlanError names the task's key.
- build_messages(goal, summary, conventions=None, system=None): system None means SYSTEM. When conventions is given,
  the user content is f"PROJECT FILES:\n{summary}\n\nPROJECT CONVENTIONS:\n{conventions}\n\nFEATURE GOAL:\n{goal}";
  without it, as before.
- TEXT_SYSTEM: the planner prompt for the text stage. It asks for plain text, no JSON, one block per task with the
  lines "Key:", "Title:", "Goal:", "Files:", "Tests:", "Protected:", "After:" and "Role:", explains them like SYSTEM
  does, and holds the same rule sentences as SYSTEM (every line of SYSTEM from "Tasks that write the same file" on).
- CONVERT_SYSTEM: the converter prompt: turn the plan text into JSON {"tasks": [...]} with the fields key, title,
  goal, files, tests, protected, after, role; copy every goal word for word; answer with JSON only.
- convert_messages(text) -> [{"role": "system", "content": CONVERT_SYSTEM}, {"role": "user", "content": text}]."""
import json

import pytest

from stratos import plan


def one(**task):
    base = {"key": "k", "title": "t", "goal": "g", "files": ["stratos/a.py"], "tests": ["tests/test_a.py"]}
    base.update(task)
    return json.dumps({"tasks": [base]})


def test_a_task_of_only_test_files_is_refused():
    with pytest.raises(plan.PlanError) as e:
        plan.parse_plan(one(key="tests_only", files=["tests/test_a.py", "tests/test_b.py"], tests=["tests/test_c.py"]))
    assert "tests_only" in str(e.value)


def test_a_task_that_writes_its_own_tests_is_refused():
    with pytest.raises(plan.PlanError) as e:
        plan.parse_plan(one(key="mixed", files=["stratos/a.py", "tests/test_a.py"]))
    assert "mixed" in str(e.value) and "tests/test_a.py" in str(e.value)


def test_a_normal_task_still_passes():
    assert plan.parse_plan(one())[0]["files"] == ["stratos/a.py"]


def test_build_messages_with_conventions_and_system():
    msgs = plan.build_messages("Fly.", "stratos/a.py", conventions="Use gw.chat.")
    assert msgs[0] == {"role": "system", "content": plan.SYSTEM}
    assert msgs[1]["content"] == "PROJECT FILES:\nstratos/a.py\n\nPROJECT CONVENTIONS:\nUse gw.chat.\n\nFEATURE GOAL:\nFly."
    assert plan.build_messages("Fly.", "s", system=plan.TEXT_SYSTEM)[0]["content"] == plan.TEXT_SYSTEM
    assert plan.build_messages("Fly.", "s") == plan.build_messages("Fly.", "s", conventions=None, system=None)
    assert plan.build_messages("Fly.", "s")[1]["content"] == "PROJECT FILES:\ns\n\nFEATURE GOAL:\nFly."


def test_text_system():
    t = plan.TEXT_SYSTEM
    assert "plain text" in t and "no JSON" in t
    for field in ("Key:", "Title:", "Goal:", "Files:", "Tests:", "Protected:", "After:", "Role:"):
        assert field in t
    rules = plan.SYSTEM[plan.SYSTEM.index("Tasks that write the same file"):]
    for line in rules.splitlines():
        assert line in t


def test_convert_system_and_messages():
    c = plan.CONVERT_SYSTEM
    assert "JSON" in c and '"tasks"' in c and "word for word" in c
    for field in ("key", "title", "goal", "files", "tests", "protected", "after", "role"):
        assert field in c
    assert plan.convert_messages("Key: a\nTitle: x") == [{"role": "system", "content": c},
                                                         {"role": "user", "content": "Key: a\nTitle: x"}]
