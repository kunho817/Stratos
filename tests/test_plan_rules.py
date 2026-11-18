"""Tests for task T063: plan.SYSTEM teaches the planner Stratos's own task rules.

The first real plan (P001, 2026-11-18) broke them: five tasks wrote the same new file with no "after" between them
(their branches would conflict), one-line helpers were whole tasks, one task's only file was a test file, and a
function that calls the model did not take the gateway. SYSTEM now holds these sentences, word for word:"""
from stratos import plan

RULES = [
    "Tasks that write the same file must be chained: each one lists the previous one in \"after\".",
    "The tests of a task are written before the task runs, so never make a task whose files are only test files.",
    "Keep related small functions of one module in one task; a task should be worth a model call and a review.",
    "A function that calls a model takes the gateway as a parameter (gw), so tests can pass a fake.",
    "Prefer 2 to 6 tasks for a feature.",
]


def test_rules_are_in_the_system_prompt():
    for rule in RULES:
        assert rule in plan.SYSTEM


def test_the_format_is_still_described():
    for word in ("JSON", "title", "goal", "files", "tests", "after", "protected", "role", "tests/"):
        assert word in plan.SYSTEM
