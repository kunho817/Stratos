"""Tests for T242 (P21, 2026-11-21): addcheck warns about old tests that read a changed file's source text.

T239 (one function per command in __main__) failed its first round on three old tests that asserted strings in
inspect.getsource(cli._main): behaviour stayed, the structure moved. addcheck had only said "uses main" among 14
generic lines. A test that reads source text breaks on any restructure, so it gets its own warning.

addcheck.check(repo, task, others, cmap) adds, after the "new test of another task" lines and before the lines
about old tests that use the changed files, one line per test file p (sorted) for which all hold:
  - p is in cmap["files"], under cmap.get("test_dir", "tests") + "/", not in the task's tests, and it exists
    under repo (a missing or unreadable file is skipped);
  - its text reads source: either p is one of plantests.old_tests(cmap, ...) (it imports a changed file) and the
    text contains "getsource(" or ".__file__", or the text contains one of the task's file paths as written
    (e.g. "stratos/config.py").
The line: f"{p} reads the source text of a file this task changes (getsource, __file__ or its path): a new
structure breaks it even when the behaviour stays the same - update it now". These lines are not capped."""
from stratos import addcheck

LINE = (" reads the source text of a file this task changes (getsource, __file__ or its path): a new structure "
        "breaks it even when the behaviour stays the same - update it now")


def write(root, path, text):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def cmap(*tests):
    files = {"pkg/cli.py": [{"name": "main", "kind": "function", "uses": []}]}
    imports = {"pkg/cli.py": []}
    for t, imps in tests:
        files[t] = []
        imports[t] = imps
    return {"test_dir": "tests", "files": files, "imports": imports}


def test_source_readers_are_named(tmp_path):
    write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    write(tmp_path, "tests/test_getsource.py", "import inspect\nsrc = inspect.getsource(cli._main)\n")
    write(tmp_path, "tests/test_file.py", "text = Path(cli.__file__).read_text()\n")
    write(tmp_path, "tests/test_path.py", "text = open('pkg/cli.py').read()\n")
    write(tmp_path, "tests/test_plain.py", "def test_b():\n    assert cli.main([]) == 0\n")
    write(tmp_path, "tests/test_unrelated.py", "import inspect\nsrc = inspect.getsource(other)\n")
    task = {"goal": "restructure main", "files": ["pkg/cli.py"], "tests": ["tests/test_new.py"]}
    c = cmap(("tests/test_new.py", ["cli"]), ("tests/test_getsource.py", ["cli"]), ("tests/test_file.py", ["cli"]),
             ("tests/test_path.py", []), ("tests/test_plain.py", ["cli"]), ("tests/test_unrelated.py", ["other"]))
    lines = addcheck.check(tmp_path, task, [], c)
    readers = [ln for ln in lines if ln.endswith(LINE)]
    assert readers == ["tests/test_file.py" + LINE, "tests/test_getsource.py" + LINE, "tests/test_path.py" + LINE]
    first_reader = lines.index(readers[0])
    uses = [i for i, ln in enumerate(lines) if "which this task changes" in ln]
    assert uses and all(i > first_reader for i in uses)


def test_the_tasks_own_tests_are_not_named(tmp_path):
    write(tmp_path, "tests/test_new.py", "src = inspect.getsource(cli._main)\n")
    task = {"goal": "g", "files": ["pkg/cli.py"], "tests": ["tests/test_new.py"]}
    assert addcheck.check(tmp_path, task, [], cmap(("tests/test_new.py", ["cli"]))) == []
