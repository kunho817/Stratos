"""Tests for task plan_tolerant: parse_text_plan reads list items with notes, and drops test files from Files.

Wiki A/B (2026-11-19, 5 plans per variant): 3 of 5 plans with module notes failed to parse, all on form, not
content: "Tests: tests/a.test.js (new), tests/towers.test.js (existing, add level checks)" (the comma inside the note
split the item) and the new test file listed in Files as well as in Tests. The notes were useful (they named old
tests to update), so they are kept in the goal.

parse_text_plan, for the list fields (Files, Tests, Protected, After): every parenthesised note "(...)" is taken out
of the value before it is split on commas, together with the space before it. A note that follows an item (the text
before it, back to the previous comma or the start, stripped and without backticks) is recorded as (item, note
stripped), in order (fields in the order they appear in the task); notes that are only "new" or "new file" (any case)
are dropped. When a task has recorded notes and a goal, the goal gets "\n\nNotes from the plan:\n" + lines
f"- {item}: {note}" joined with "\n".
Then every item of "files" that is also in the task's "tests" is dropped from "files" (order kept).
Everything else as before."""
from stratos import plan

TEXT = """Key: stats
Title: Tower stats
Goal: Add towerStats.
Files: stratos/towers.py, tests/test_tower_stats.py
Tests: tests/test_tower_stats.py (new), tests/test_towers.py (existing, add level/totalSpent checks)
Protected: `stratos/grid.py` (read only)
After: none

Key: step
Title: Step uses stats
Goal: Read towerStats in step.
Files: stratos/step.py (New File)
Tests: tests/test_step_levels.py (NEW), tests/test_step.py
After: stats (needs towerStats)
"""


def test_notes_and_test_files():
    tasks = plan.parse_text_plan(TEXT)
    a, b = tasks
    assert a["files"] == ["stratos/towers.py"]
    assert a["tests"] == ["tests/test_tower_stats.py", "tests/test_towers.py"]
    assert a["protected"] == ["stratos/grid.py"]
    assert a["goal"] == ("Add towerStats.\n\nNotes from the plan:\n"
                         "- tests/test_towers.py: existing, add level/totalSpent checks\n- stratos/grid.py: read only")
    assert b["files"] == ["stratos/step.py"]
    assert b["tests"] == ["tests/test_step_levels.py", "tests/test_step.py"]
    assert b["after"] == ["stats"]
    assert b["goal"] == "Read towerStats in step.\n\nNotes from the plan:\n- stats: needs towerStats"


def test_plain_plans_are_unchanged():
    text = "Key: a\nTitle: T\nGoal: G\nFiles: stratos/a.py\nTests: tests/test_a.py\n"
    (t,) = plan.parse_text_plan(text)
    assert t["goal"] == "G" and t["files"] == ["stratos/a.py"] and t["tests"] == ["tests/test_a.py"]
