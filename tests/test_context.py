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


# ---- was test_context_project.py ----
# Tests for the project's language in CODER_SYSTEM (plan P008, context_system_language).
#
# context.coder_system(language) returns the coders' system prompt for a project in that language; the language name
# is used as written in the settings (e.g. "Python", "JavaScript") and lower-cased as the code fence's tag.
# context.CODER_SYSTEM = coder_system(<config.PROJECT["language"] with its first letter upper-cased>), and with
# Stratos's default ("python") it is exactly BEFORE below, last line included (tests/test_context_system.py).
# (Updated by Claude for task loop_edits, 2026-11-20: the edit-block format for existing files.)
# (The test runner is named in plantests.TEST_SYSTEM, not here: the coder already sees the tests it must pass.)


BEFORE = """You are the coding model inside Stratos, a harness that edits a Python project.
Answer ONLY with file blocks in one of these two formats, and nothing else.

A new file, or a short one written whole:
FILE: relative/path.py
```python
<the entire file content>
```

A change to a file that already exists:
FILE: relative/path.py
<<<<<<< SEARCH
<lines copied exactly from the file as shown>
=======
<the lines that replace them>
>>>>>>> REPLACE

Rules:
- You have no tools and cannot open files: everything you need is in this message. Answer with the files directly.
- For an existing file use edit blocks: each SEARCH is copied exactly from the file shown (indentation included), is found exactly once, and holds only a few lines around the change; use several blocks for several changes.
- A whole file must be complete, never a fragment.
- Do not change files marked READ-ONLY. Do not add test code, prints or example runs to the files you write.
- Use only the Python standard library unless the task says otherwise.
- Keep the code plain and correct; the task's tests decide whether you succeeded."""


def test_stratos_default_is_unchanged():
    assert context.CODER_SYSTEM == BEFORE
    assert context.coder_system("Python") == BEFORE


def test_another_language():
    s = context.coder_system("JavaScript")
    assert "edits a JavaScript project." in s
    assert "```javascript\n" in s and "```python" not in s
    assert "Use only the JavaScript standard library" in s
    assert "Python" not in s
    assert s.splitlines()[-1] == BEFORE.splitlines()[-1]
    assert s.count("\n") == BEFORE.count("\n")


# ---- was test_context_retry.py ----
# Tests for task retry_not_kept (P8, 2026-11-20, found in T192): with edit blocks, a failed attempt is thrown away and
# the next one starts from the files as they were - but the model thought its edits had stayed and sent only the fix
# (an import), so the tests failed the same way. The retry message says so.
#
# context.build_messages(task, root, failure=...): the failure part is
# "YOUR PREVIOUS ATTEMPT FAILED and was not kept: the files above are as they were before it, so send every change "
# "again. Test output:
# ```
# " + failure + "
# ```
# Fix it."
# (it still starts with "YOUR PREVIOUS ATTEMPT FAILED", which tests/test_loop_memory.py reads).


TASK = {"id": "T1", "title": "t", "goal": "g", "files": [], "protected": []}


def test_retry_message_says_the_attempt_was_not_kept():
    user = context.build_messages(TASK, ".", failure="F boom")[-1]["content"]
    assert user.endswith("YOUR PREVIOUS ATTEMPT FAILED and was not kept: the files above are as they were before it, "
                         "so send every change again. Test output:\n```\nF boom\n```\nFix it.")


# ---- was test_context_system.py ----
# Tests for task T030: the coder system prompt is the fixed start of every coding request (its wording is part of the
# contract, and PolyStrata reuses its cached computation). T029's coder changed its last line unasked; it must read:


LAST_LINE = "- Keep the code plain and correct; the task's tests decide whether you succeeded."


def test_last_line_of_the_system_prompt():
    assert context.CODER_SYSTEM.splitlines()[-1] == LAST_LINE


def test_rules_are_all_there():
    for rule in ("- You have no tools and cannot open files", "- A whole file must be complete, never a fragment.",
                 "- Do not change files marked READ-ONLY.", "- Use only the Python standard library"):
        assert rule in context.CODER_SYSTEM
