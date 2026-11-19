"""Tests for task new_tests: plan.check_new_tests (plan P010).

The planner twice gave a task only existing test files although CONVENTIONS.md asks for a new one; then
`plan-tests` has nothing to write ("exists") and the task has no test of its own. check_new_tests(tasks, root)
checks the parsed tasks (dicts with "key" and "tests") against the project at root and raises plan.PlanError:
- f"Task {key}: its first test file '{first}' already exists. Give every task a new test file first; existing
  test files may follow it." when Path(root, first) exists;
- f"Task {key}: its first test file '{first}' is also the first test file of task {other}." when an earlier task
  starts with the same file.
The first problem found (in task order) is raised. Otherwise it returns None. Test files after the first one may
exist."""
import pytest

from stratos import plan


def task(key, tests):
    return {"key": key, "title": "t", "goal": "g", "files": ["src/a.py"], "tests": tests}


def test_new_first_files(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_old.py").write_text("", encoding="utf-8")
    tasks = [task("a", ["tests/test_new_a.py", "tests/test_old.py"]), task("b", ["tests/test_new_b.py"])]
    assert plan.check_new_tests(tasks, tmp_path) is None


def test_an_existing_first_file(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_old.py").write_text("", encoding="utf-8")
    tasks = [task("a", ["tests/test_new.py"]), task("b", ["tests/test_old.py", "tests/test_b.py"])]
    with pytest.raises(plan.PlanError) as e:
        plan.check_new_tests(tasks, tmp_path)
    assert str(e.value) == ("Task b: its first test file 'tests/test_old.py' already exists. Give every task a new "
                            "test file first; existing test files may follow it.")


def test_two_tasks_with_the_same_first_file(tmp_path):
    tasks = [task("a", ["tests/test_x.py"]), task("b", ["tests/test_y.py"]), task("c", ["tests/test_x.py"])]
    with pytest.raises(plan.PlanError) as e:
        plan.check_new_tests(tasks, tmp_path)
    assert str(e.value) == "Task c: its first test file 'tests/test_x.py' is also the first test file of task a."


def test_the_first_problem_in_task_order(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_old.py").write_text("", encoding="utf-8")
    tasks = [task("a", ["tests/test_x.py"]), task("b", ["tests/test_x.py"]), task("c", ["tests/test_old.py"])]
    with pytest.raises(plan.PlanError) as e:
        plan.check_new_tests(tasks, tmp_path)
    assert str(e.value).startswith("Task b: ")
