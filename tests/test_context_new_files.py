"""Tests for task context_new_files (P11, 2026-11-20, trial Cronix T006): a task that writes a NEW file got no imported
modules in its prompt (related_files follows the imports of the task's files, and a new file has none), so Tiel
answered "the tests import cronix.expr, cronix.schedule ... none of which exist" and rewrote all of them.

context.related_files(root, files, extra=()): as before for the task's files, plus the package modules imported by
the existing Python files in `extra` (the same import rules), plus the module files named in the goal: the
caller passes them in extra too. context.goal_modules(root, goal) -> sorted paths "<pkg>/<mod>.py" that exist under
root for every dotted name "<pkg>.<mod>" or "<pkg>.<mod>.<name>" in the goal (word characters joined by dots).
build_messages calls related_files(root, task["files"], extra=task["protected"] + goal_modules(root, goal)) and
leaves out the task's own files and protected files as before."""
from stratos import context


def make(tmp_path):
    pkg = tmp_path / "cronix"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("FIELDS = ()\n", encoding="utf-8")
    for name in ("expr", "schedule", "describe", "fields"):
        (pkg / f"{name}.py").write_text(f"def {name}_fn():\n    return '{name}'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_cli.py").write_text("from cronix.cli import main\nfrom cronix import expr\n",
                                                    encoding="utf-8")
    return tmp_path


def test_goal_modules(tmp_path):
    root = make(tmp_path)
    goal = "print cronix.describe.describe(cron), then each of cronix.schedule.next_runs(...); cronix.nothing.x"
    assert context.goal_modules(root, goal) == ["cronix/describe.py", "cronix/schedule.py"]


def test_related_files_follow_tests_and_goal(tmp_path):
    root = make(tmp_path)
    got = context.related_files(root, ["cronix/cli.py"], extra=["tests/test_cli.py", "cronix/schedule.py"])
    assert got == ["cronix/expr.py", "cronix/schedule.py"]
    assert context.related_files(root, ["cronix/cli.py"]) == []


def test_a_new_file_sees_the_modules_it_will_use(tmp_path):
    root = make(tmp_path)
    task = {"id": "T6", "title": "cli", "goal": "Use cronix.schedule.next_runs and cronix.describe.describe.",
            "files": ["cronix/cli.py", "cronix/__main__.py"], "protected": ["tests/test_cli.py"]}
    user = context.build_messages(task, root)[-1]["content"]
    for m in ("cronix/schedule.py", "cronix/describe.py", "cronix/expr.py"):
        assert f"READ-ONLY (imported by the files you write): {m}" in user
    assert "cronix/fields.py" not in user
