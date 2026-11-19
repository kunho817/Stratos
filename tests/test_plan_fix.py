"""Tests for task plan_fix: the plan's mechanical rules are fixed by code instead of sent back (Ledger round 2).

Swift planned Ledger round 2 three times and every time gave tasks an existing test file first (it extends modules,
so it extends their test files), and once wrote "After: T004", a past task's id it saw in the memory pack.

plan.fix_new_tests(tasks, root, settings=None) -> list of messages; it changes tasks in place. settings None ->
config.PROJECT. For each task in order, first = task["tests"][0]: when Path(root, first) exists or an earlier task
already starts with the same file, a new file name is put in front of task["tests"]: slug = the task key lowercased
with every run of characters other than a-z and 0-9 replaced by "_" and "_" stripped at both ends; suffix =
settings["test_suffixes"][0]; the name is f"{test_dir}/test_{slug}.py" when suffix is ".py", else
f"{test_dir}/{slug}{suffix}"; when that name exists or is already some task's test file, "_2", "_3", ... is added
to the slug until it is free. The message is f"Task {key}: added the new test file {name} ({first} already
existed)" or f"Task {key}: added the new test file {name} ({first} is task {other}'s first test file)".

plan.parse_text_plan: an After item that is not a key of an earlier task but matches ^T\\d+$ (a past task's id) is
dropped instead of refused.

`stratos plan`: after a plan is read, it calls fix_new_tests(tasks, config.REPO) instead of check_new_tests and
prints each message; the plan is saved with the fixed test lists."""
from stratos import config, plan

PY = {"test_dir": "tests", "test_suffixes": [".py"]}
JS = {"test_dir": "tests", "test_suffixes": [".test.js"]}


def task(key, tests):
    return {"key": key, "title": "t", "goal": "g", "files": ["src/a.py"], "tests": list(tests)}


def test_an_existing_first_file_gets_a_new_one(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_cli.py").write_text("", encoding="utf-8")
    tasks = [task("CLI new-commands", ["tests/test_cli.py"]), task("b", ["tests/test_b.py"])]
    msgs = plan.fix_new_tests(tasks, tmp_path, PY)
    assert tasks[0]["tests"] == ["tests/test_cli_new_commands.py", "tests/test_cli.py"]
    assert tasks[1]["tests"] == ["tests/test_b.py"]
    assert msgs == ["Task CLI new-commands: added the new test file tests/test_cli_new_commands.py "
                    "(tests/test_cli.py already existed)"]


def test_a_shared_first_file_and_a_taken_name(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("", encoding="utf-8")
    tasks = [task("a", ["tests/test_y.py"]), task("x", ["tests/test_y.py"])]
    msgs = plan.fix_new_tests(tasks, tmp_path, PY)
    assert tasks[1]["tests"] == ["tests/test_x_2.py", "tests/test_y.py"]
    assert msgs == ["Task x: added the new test file tests/test_x_2.py (tests/test_y.py is task a's first test file)"]


def test_js_names(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "towers.test.js").write_text("", encoding="utf-8")
    tasks = [task("tower_levels", ["tests/towers.test.js"])]
    plan.fix_new_tests(tasks, tmp_path, JS)
    assert tasks[0]["tests"] == ["tests/tower_levels.test.js", "tests/towers.test.js"]


def test_nothing_to_fix(tmp_path):
    tasks = [task("a", ["tests/test_a.py"])]
    assert plan.fix_new_tests(tasks, tmp_path, PY) == [] and tasks[0]["tests"] == ["tests/test_a.py"]


def test_settings_default_to_the_project(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests", "test_suffixes": [".test.js"]})
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "a.test.js").write_text("", encoding="utf-8")
    tasks = [task("k", ["tests/a.test.js"])]
    plan.fix_new_tests(tasks, tmp_path)
    assert tasks[0]["tests"][0] == "tests/k.test.js"


def test_past_task_ids_in_after_are_dropped():
    text = ("Key: a\nTitle: A\nGoal: g\nFiles: stratos/a.py\nTests: tests/test_a.py\nAfter: T004\n\n"
            "Key: b\nTitle: B\nGoal: g\nFiles: stratos/b.py\nTests: tests/test_b.py\nAfter: a, T012\n")
    tasks = plan.parse_text_plan(text)
    assert [t["after"] for t in tasks] == [[], ["a"]]
