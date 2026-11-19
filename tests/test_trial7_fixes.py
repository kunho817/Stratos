"""Tests for task trial7_fixes (P4, 2026-11-20): two gaps found by trial 7 (Pantry round 2).

1. OUTDATED never fired: the planner listed the old test files (tests/test_shopping.py) as the task's own tests, and
   plantests.build_messages showed them only as "EXISTING TEST, DO NOT REWRITE" without the OUTDATED instruction.
   Now, when any file of task["tests"] already exists under root (or old is not empty), the final "WRITE THESE TEST
   FILES" part carries the OUTDATED sentence ("If the goal makes a test in those existing files wrong, name it at the
   top of your new file in a comment line: OUTDATED: <path>::<test name> - <reason>"). With no existing test file and
   no old tests it is left out, as before.
2. The plan critic reported "the new test file should be tests/test_<module>.py" five times: Stratos's own rule is
   that each task's first test file is a new file. plancritic.SYSTEM also says: "Each task's first test file is a new
   file of its own and later test files are existing ones it must keep passing (a rule of this harness): never
   report test file names or the split of tests into files.\""""
from stratos import plancritic, plantests

OUTDATED = ("If the goal makes a test in those existing files wrong, name it at the top of your new file in a comment "
            "line: OUTDATED: <path>::<test name> - <reason>")


def task(tests):
    return {"key": "count", "title": "Counting", "goal": "Add counts.", "files": ["pantry/shopping.py"],
            "tests": tests, "protected": tests}


def test_outdated_sentence_for_the_tasks_own_existing_test(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_shopping.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    user = plantests.build_messages(task(["tests/test_count.py", "tests/test_shopping.py"]), tmp_path,
                                    example="tests/none.py")[1]["content"]
    assert "EXISTING TEST, DO NOT REWRITE: tests/test_shopping.py" in user
    assert OUTDATED in user
    assert user.rstrip().endswith(OUTDATED)


def test_no_sentence_without_existing_tests(tmp_path):
    user = plantests.build_messages(task(["tests/test_count.py"]), tmp_path, example="tests/none.py")[1]["content"]
    assert "OUTDATED" not in user


def test_critic_knows_the_test_file_rule():
    assert ("Each task's first test file is a new file of its own and later test files are existing ones it must "
            "keep passing (a rule of this harness): never report test file names or the split of tests into files."
            in plancritic.SYSTEM)
    assert "PROBLEM: <task key> | <one sentence>" in plancritic.SYSTEM
