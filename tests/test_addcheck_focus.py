"""Tests for task addcheck_focus (P9, 2026-11-20): the old-test warning of `stratos add` listed ~40 files for a task on
config.py or loop.py (every test imports them), so the one that mattered was lost (T184/T188/T192: an exact-dict test
and two old fakes). Now it names the tests that use what the goal changes.

addcheck.check, warning 4 (the other warnings stay as they are):
- changed = the names of the symbols the code map has for task["files"] (any kind) that the goal
  (task.get("goal", "")) names as a whole word (regex \\b<name>\\b), in code-map order, no repeats;
- when changed is not empty: for each path of plantests.old_tests(...) whose text (read from repo) names one of them
  as a whole word: f"{path} uses {', '.join(<those names, in changed order>)}, which this task changes: list it in
  --tests, and update it now if the goal changes what it checks"; old tests that name none of them give no line;
- when changed is empty: the old line for each old test, as before;
- at most 8 such lines; when there are more, the 8 first and then f"... and {n} more old tests" (n = the rest)."""
from stratos import addcheck

GOAL = "Change REF_WRITER to Swift and make check() refuse a reference that does not compile."


def write(root, path, text):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def cmap_for(tests):
    files = {"pkg/config.py": [{"name": "REF_WRITER", "kind": "constant", "uses": []},
                               {"name": "LINT", "kind": "constant", "uses": []}],
             "pkg/refcheck.py": [{"name": "check", "kind": "function", "uses": []},
                                 {"name": "judge", "kind": "function", "uses": []}]}
    imports = {"pkg/config.py": [], "pkg/refcheck.py": ["config"]}
    for t in tests:
        files[t] = []
        imports[t] = ["config", "refcheck"]
    return {"test_dir": "tests", "files": files, "imports": imports}


def test_only_tests_that_use_the_changed_names(tmp_path):
    write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    write(tmp_path, "tests/test_ref.py", "def test_w():\n    assert config.REF_WRITER['model'] == 'x'\n"
                                          "    refcheck.check(1)\n")
    write(tmp_path, "tests/test_fake.py", "monkeypatch.setattr(refcheck, \"check\", fake)\n")
    write(tmp_path, "tests/test_lint.py", "config.LINT = True\nrefcheck.judge(1, [])\nchecked = 1\n")
    task = {"goal": GOAL, "files": ["pkg/config.py", "pkg/refcheck.py"], "tests": ["tests/test_new.py"]}
    lines = addcheck.check(tmp_path, task, [], cmap_for(["tests/test_new.py", "tests/test_ref.py",
                                                         "tests/test_fake.py", "tests/test_lint.py"]))
    tail = ", which this task changes: list it in --tests, and update it now if the goal changes what it checks"
    assert lines == ["tests/test_fake.py uses check" + tail,
                     "tests/test_ref.py uses REF_WRITER, check" + tail]


def test_no_named_symbol_keeps_the_old_line_and_the_cap(tmp_path):
    write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    olds = [f"tests/test_o{i:02}.py" for i in range(11)]
    for o in olds:
        write(tmp_path, o, "x = 1\n")
    task = {"goal": "tidy the module", "files": ["pkg/config.py"], "tests": ["tests/test_new.py"]}
    lines = addcheck.check(tmp_path, task, [], cmap_for(["tests/test_new.py"] + olds))
    assert len(lines) == 9
    assert lines[0] == ("tests/test_o00.py imports a file this task changes: list it in --tests, and update it now "
                        "if the goal changes what it checks")
    assert lines[7].startswith("tests/test_o07.py imports")
    assert lines[8] == "... and 3 more old tests"
