"""Tests for task T073: the test writer also sees the project's conventions.

plantests.build_messages(task, root, ...): when root / "CONVENTIONS.md" exists, a part
"PROJECT CONVENTIONS:\n" + its text comes right after the "PROJECT FILES:" part; without the file nothing changes."""
from stratos import plan, plantests

TASK = {"key": "core", "title": "Add f", "goal": "Add f.", "files": ["stratos/m.py"], "tests": ["tests/test_m.py"],
        "protected": [], "after": [], "role": None}


def test_conventions_follow_the_project_files(tmp_path):
    (tmp_path / "stratos").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "CONVENTIONS.md").write_text("Fake the gateway.", encoding="utf-8")
    user =plantests.build_messages(TASK, tmp_path, example="tests/none.py")[1]["content"]
    assert "PROJECT FILES:\n" + plan.repo_summary(tmp_path) + "\n\nPROJECT CONVENTIONS:\nFake the gateway.\n\n" in user


def test_no_conventions_file(tmp_path):
    (tmp_path / "stratos").mkdir()
    user = plantests.build_messages(TASK, tmp_path, example="tests/none.py")[1]["content"]
    assert "PROJECT CONVENTIONS" not in user
