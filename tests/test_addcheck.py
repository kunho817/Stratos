"""Tests for task addcheck (P6, 2026-11-20): `stratos add` warns about the slips Claude made again and again when
adding tasks (6 times in two days: T151, T167, T171, T172, Pantry T007, ...): a test list that holds another waiting
task's new test, old tests that use the changed files but are left out of the list (they then pin old behaviour), and
missing or broken test files.

addcheck.check(repo, task, others, cmap) -> list of warning lines, in this order:
1. f"missing test file: {path}" for each test path (any "::..." cut off) that does not exist under repo;
2. f"test file has a syntax error: {error}" for each verify.syntax_errors(repo, <existing test paths>) line;
3. f"{path} is the new test of {other['id']}, which is not done: leave it out of this task's tests" for each test
   path equal to the first test path of another task in others whose status is not "done" or "dropped";
4. f"{path} imports a file this task changes: list it in --tests, and update it now if the goal changes what it
   checks" for each path of plantests.old_tests(cmap, {"files": task["files"], "tests": <test paths>}).
`stratos add` (not plan-add) prints each line as f"  warning: {line}" after "added <id>: <title>" (others = the other
tasks in the store, cmap = codemap.build(config.REPO)); the task is added in any case."""
from stratos import __main__ as cli
from stratos import addcheck, codemap, config
from stratos.state import Store


def write(root, path, text):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_warnings_in_order(tmp_path):
    write(tmp_path, "tests/test_new.py", "def test_a(:\n    pass\n")
    write(tmp_path, "tests/test_other.py", "def test_b():\n    pass\n")
    task = {"files": ["pkg/core.py"], "tests": ["tests/test_new.py::test_a", "tests/test_gone.py",
                                                "tests/test_other.py"]}
    others = [{"id": "T010", "status": "todo", "tests": ["tests/test_other.py"]},
              {"id": "T011", "status": "done", "tests": ["tests/test_new.py"]}]
    cmap = {"test_dir": "tests", "files": {"pkg/core.py": [], "tests/test_old.py": [], "tests/test_new.py": []},
            "imports": {"pkg/core.py": [], "tests/test_old.py": ["core"], "tests/test_new.py": ["core"]}}
    lines = addcheck.check(tmp_path, task, others, cmap)
    assert lines[0] == "missing test file: tests/test_gone.py"
    assert lines[1].startswith("test file has a syntax error: tests/test_new.py: line 1: ")
    assert lines[2] == ("tests/test_other.py is the new test of T010, which is not done: leave it out of this "
                        "task's tests")
    assert lines[3] == ("tests/test_old.py imports a file this task changes: list it in --tests, and update it now "
                        "if the goal changes what it checks")
    assert len(lines) == 4


def test_a_clean_task_gives_no_warnings(tmp_path):
    write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    task = {"files": ["pkg/core.py"], "tests": ["tests/test_new.py"]}
    cmap = {"test_dir": "tests", "files": {}, "imports": {}}
    assert addcheck.check(tmp_path, task, [], cmap) == []


def test_add_prints_the_warnings(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path)
    monkeypatch.setattr(codemap, "build", lambda root: {"test_dir": "tests", "files": {}, "imports": {}})
    store = Store(tmp_path / "state")
    store.add_task("other", "g", ["pkg/b.py"], [], ["tests/test_b.py"])
    assert cli.main(["add", "--title", "t", "--goal", "g", "--files", "pkg/a.py", "--tests",
                     "tests/test_b.py", "--role", "coder"]) == 0
    out = capsys.readouterr().out.splitlines()
    i = next(n for n, line in enumerate(out) if line.startswith("added T002"))
    assert out[i + 1:] == ["  warning: missing test file: tests/test_b.py",
                           "  warning: tests/test_b.py is the new test of T001, which is not done: leave it out of "
                           "this task's tests"]
    assert store.get("T002")["tests"] == ["tests/test_b.py"]
