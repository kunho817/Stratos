"""Tests for task addcheck-text-fake: addcheck.check names old tests that pin a changed file's text (rule a)
or fake its functions (rule b).

After all existing warnings, for each old test p (plantests.old_tests(cmap, task), sorted) whose text can be read:
(a) read Python string constants >=30 chars from each changed .py file via ast; if p's text contains any verbatim,
    add "<p> holds text from <file>: a change of that text breaks it - update it now" (one line per kind per test);
    Non-Python changed files skip rule (a).
(b) find setattr(<module>, "<name>") patterns (single or double quotes) in p where <name> is a function/class
    name from the task's changed files that appears as a whole word in the goal; add
    "<p> replaces <name> with a fake: a new parameter or return value breaks it - update it now".
    Each old test gets at most one line of each kind.
"""

from pathlib import Path

from stratos import addcheck, verify


def _write(root, path, text):
    p = Path(root) / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _cmap(changed, tests, syms=None):
    """Build a minimal cmap: changed files have symbols; every test file imports 'core'."""
    files = {p: [] for p in changed + tests}
    imports = {p: [] for p in changed}
    for t in tests:
        imports[t] = ["core"]
    if syms:
        for path, s in syms.items():
            files[path] = s
    return {"test_dir": "tests", "files": files, "imports": imports}


def _run(tmp_path, monkeypatch, task, cmap):
    monkeypatch.setattr(verify, "syntax_errors", lambda root, paths: [])
    return addcheck.check(tmp_path, task, [], cmap)


LONG = "this is a long string of at least thirty"  # 34 chars
LONG_30 = "x" * 30  # 30 chars, exactly at the boundary
SHORT = "short"  # 5 chars


def test_a_string_literal_in_old_test(tmp_path, monkeypatch):
    # pkg/core.py: TEXT = "this is a long string of at least thirty" (34 >= 30)
    # tests/test_old.py imports core and contains LONG verbatim
    # old_tests = ["tests/test_old.py"] (test_new is task's own, excluded)
    # rule (a): LONG found in pkg/core.py via ast → p contains it → one line
    # Expected: 1 rule-a line
    _write(tmp_path, "pkg/core.py", f'TEXT = "{LONG}"\n')
    _write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    _write(tmp_path, "tests/test_old.py",
           f'import core\nassert "{LONG}" in core.TEXT\n')
    task = {"goal": "fix TEXT", "files": ["pkg/core.py"], "tests": ["tests/test_new.py"]}
    cmap = _cmap(["pkg/core.py"], ["tests/test_new.py", "tests/test_old.py"])
    lines = _run(tmp_path, monkeypatch, task, cmap)
    # rule-a line: p = tests/test_old.py, file = pkg/core.py
    expected = "tests/test_old.py holds text from pkg/core.py: a change of that text breaks it - update it now"
    # 1 rule-a line present
    assert expected in lines


def test_a_short_string_not_flagged(tmp_path, monkeypatch):
    # pkg/core.py: TEXT = "short" (5 chars < 30)
    # tests/test_old.py contains "short"
    # ast finds string constants >= 30 chars: none → no rule-a line
    # Expected: 0 rule-a lines
    _write(tmp_path, "pkg/core.py", f'TEXT = "{SHORT}"\n')
    _write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    _write(tmp_path, "tests/test_old.py",
           f'import core\nassert "{SHORT}" in core.TEXT\n')
    task = {"goal": "fix TEXT", "files": ["pkg/core.py"], "tests": ["tests/test_new.py"]}
    cmap = _cmap(["pkg/core.py"], ["tests/test_new.py", "tests/test_old.py"])
    lines = _run(tmp_path, monkeypatch, task, cmap)
    # no string >= 30 chars → no rule-a line
    a_lines = [l for l in lines if "holds text from" in l]
    # 0 rule-a lines
    assert len(a_lines) == 0


def test_a_non_python_file_skipped(tmp_path, monkeypatch):
    # Changed file pkg/data.txt (not .py) → rule (a) skipped
    # tests/test_old.py imports "data" (module_name("pkg/data.txt") = "data")
    # imports["tests/test_old.py"] = ["data"] → in old_tests
    # rule (a): pkg/data.txt is not .py → skip → no rule-a line
    _write(tmp_path, "pkg/data.txt", f'data = "{LONG}"\n')
    _write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    _write(tmp_path, "tests/test_old.py",
           f'import data\nassert "{LONG}" in data\n')
    task = {"goal": "fix data", "files": ["pkg/data.txt"], "tests": ["tests/test_new.py"]}
    files = {"pkg/data.txt": [], "tests/test_new.py": [], "tests/test_old.py": []}
    imports = {"pkg/data.txt": [], "tests/test_new.py": ["data"], "tests/test_old.py": ["data"]}
    cmap = {"test_dir": "tests", "files": files, "imports": imports}
    lines = _run(tmp_path, monkeypatch, task, cmap)
    # non-Python changed file → rule (a) skipped
    a_lines = [l for l in lines if "holds text from" in l]
    # 0 rule-a lines
    assert len(a_lines) == 0


def test_a_exactly_30_chars(tmp_path, monkeypatch):
    # pkg/core.py: TEXT = "x"*30 (exactly 30 chars) → >= 30 → included
    # tests/test_old.py contains LONG_30 verbatim
    # Expected: 1 rule-a line
    _write(tmp_path, "pkg/core.py", f'TEXT = "{LONG_30}"\n')
    _write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    _write(tmp_path, "tests/test_old.py",
           f'import core\nassert "{LONG_30}" in core.TEXT\n')
    task = {"goal": "fix TEXT", "files": ["pkg/core.py"], "tests": ["tests/test_new.py"]}
    cmap = _cmap(["pkg/core.py"], ["tests/test_new.py", "tests/test_old.py"])
    lines = _run(tmp_path, monkeypatch, task, cmap)
    # 30 >= 30 → boundary included
    expected = "tests/test_old.py holds text from pkg/core.py: a change of that text breaks it - update it now"
    # 1 rule-a line
    assert expected in lines


def test_a_one_line_per_kind_per_test(tmp_path, monkeypatch):
    # pkg/core.py has two strings >= 30 chars: LONG and LONG_30
    # tests/test_old.py contains both verbatim
    # rule (a): one line per kind per test → one line total
    _write(tmp_path, "pkg/core.py", f'A = "{LONG}"\nB = "{LONG_30}"\n')
    _write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    _write(tmp_path, "tests/test_old.py",
           f'import core\nassert "{LONG}" in core.A\nassert "{LONG_30}" in core.B\n')
    task = {"goal": "fix text", "files": ["pkg/core.py"], "tests": ["tests/test_new.py"]}
    cmap = _cmap(["pkg/core.py"], ["tests/test_new.py", "tests/test_old.py"])
    lines = _run(tmp_path, monkeypatch, task, cmap)
    # two string constants >= 30, test contains both → one rule-a line
    a_lines = [l for l in lines if "holds text from" in l]
    # 1 rule-a line (one per kind per test)
    assert len(a_lines) == 1


def test_b_double_quotes(tmp_path, monkeypatch):
    # pkg/core.py defines def process(data): pass
    # goal mentions "process" as whole word
    # tests/test_old.py: setattr(core, "process", fake)
    # changed = ["process"] (function name in cmap, in goal)
    # rule (b): setattr pattern found, name in goal → one line
    _write(tmp_path, "pkg/core.py", "def process(data):\n    pass\n")
    _write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    _write(tmp_path, "tests/test_old.py",
           'import core\nsetattr(core, "process", fake)\n')
    task = {"goal": "change process to accept a second argument",
            "files": ["pkg/core.py"], "tests": ["tests/test_new.py"]}
    syms = {"pkg/core.py": [{"name": "process", "kind": "function", "uses": []}]}
    cmap = _cmap(["pkg/core.py"], ["tests/test_new.py", "tests/test_old.py"], syms)
    lines = _run(tmp_path, monkeypatch, task, cmap)
    # rule-b line: p = tests/test_old.py, name = process
    expected = "tests/test_old.py replaces process with a fake: a new parameter or return value breaks it - update it now"
    # 1 rule-b line
    assert expected in lines


def test_b_single_quotes(tmp_path, monkeypatch):
    # Same as double-quotes test, but setattr(core, 'process', fake)
    # Expected: same rule-b line
    _write(tmp_path, "pkg/core.py", "def process(data):\n    pass\n")
    _write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    _write(tmp_path, "tests/test_old.py",
           "import core\nsetattr(core, 'process', fake)\n")
    task = {"goal": "change process to accept a second argument",
            "files": ["pkg/core.py"], "tests": ["tests/test_new.py"]}
    syms = {"pkg/core.py": [{"name": "process", "kind": "function", "uses": []}]}
    cmap = _cmap(["pkg/core.py"], ["tests/test_new.py", "tests/test_old.py"], syms)
    lines = _run(tmp_path, monkeypatch, task, cmap)
    expected = "tests/test_old.py replaces process with a fake: a new parameter or return value breaks it - update it now"
    # 1 rule-b line (single quotes)
    assert expected in lines


def test_b_name_not_in_goal(tmp_path, monkeypatch):
    # pkg/core.py defines def helper(): pass
    # goal: "change process to accept a second argument" → "helper" NOT in goal
    # tests/test_old.py: setattr(core, "helper", fake)
    # changed = [] for helper (not in goal) → no rule-b line
    _write(tmp_path, "pkg/core.py", "def process(data):\n    pass\ndef helper():\n    pass\n")
    _write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    _write(tmp_path, "tests/test_old.py",
           'import core\nsetattr(core, "helper", fake)\n')
    task = {"goal": "change process to accept a second argument",
            "files": ["pkg/core.py"], "tests": ["tests/test_new.py"]}
    syms = {"pkg/core.py": [{"name": "process", "kind": "function", "uses": []},
                             {"name": "helper", "kind": "function", "uses": []}]}
    cmap = _cmap(["pkg/core.py"], ["tests/test_new.py", "tests/test_old.py"], syms)
    lines = _run(tmp_path, monkeypatch, task, cmap)
    b_lines = [l for l in lines if "replaces" in l and "with a fake" in l]
    # "helper" not in goal → 0 rule-b lines
    assert len(b_lines) == 0


def test_b_one_line_per_kind_per_test(tmp_path, monkeypatch):
    # tests/test_old.py has two setattr lines for "process"
    # Expected: one rule-b line
    _write(tmp_path, "pkg/core.py", "def process(data):\n    pass\n")
    _write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    _write(tmp_path, "tests/test_old.py",
           'import core\nsetattr(core, "process", fake1)\nsetattr(core, "process", fake2)\n')
    task = {"goal": "change process signature",
            "files": ["pkg/core.py"], "tests": ["tests/test_new.py"]}
    syms = {"pkg/core.py": [{"name": "process", "kind": "function", "uses": []}]}
    cmap = _cmap(["pkg/core.py"], ["tests/test_new.py", "tests/test_old.py"], syms)
    lines = _run(tmp_path, monkeypatch, task, cmap)
    b_lines = [l for l in lines if "replaces process" in l]
    # two setattr lines → one rule-b line (one per kind per test)
    assert len(b_lines) == 1


def test_b_class_name_in_setattr(tmp_path, monkeypatch):
    # pkg/core.py defines class Engine: pass
    # goal mentions "Engine" as whole word
    # tests/test_old.py: setattr(core, "Engine", fake)
    # changed includes "Engine" (class name, in goal)
    _write(tmp_path, "pkg/core.py", "class Engine:\n    pass\n")
    _write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    _write(tmp_path, "tests/test_old.py",
           'import core\nsetattr(core, "Engine", fake)\n')
    task = {"goal": "add a timeout parameter to Engine",
            "files": ["pkg/core.py"], "tests": ["tests/test_new.py"]}
    syms = {"pkg/core.py": [{"name": "Engine", "kind": "class", "uses": []}]}
    cmap = _cmap(["pkg/core.py"], ["tests/test_new.py", "tests/test_old.py"], syms)
    lines = _run(tmp_path, monkeypatch, task, cmap)
    expected = "tests/test_old.py replaces Engine with a fake: a new parameter or return value breaks it - update it now"
    # 1 rule-b line for class name
    assert expected in lines


def test_task_own_test_excluded(tmp_path, monkeypatch):
    # Task's own test tests/test_new.py contains LONG from pkg/core.py
    # old_tests excludes tests/test_new.py (it's in task["tests"])
    # No old test exists → no rule-a line
    _write(tmp_path, "pkg/core.py", f'TEXT = "{LONG}"\n')
    _write(tmp_path, "tests/test_new.py",
           f'import core\nassert "{LONG}" in core.TEXT\n')
    task = {"goal": "fix TEXT", "files": ["pkg/core.py"], "tests": ["tests/test_new.py"]}
    cmap = _cmap(["pkg/core.py"], ["tests/test_new.py"])
    lines = _run(tmp_path, monkeypatch, task, cmap)
    # task's own test excluded from old_tests → no rule lines
    rule_lines = [l for l in lines if "holds text from" in l or "with a fake" in l]
    # 0 rule lines
    assert len(rule_lines) == 0


def test_unreadable_skipped(tmp_path, monkeypatch):
    # cmap["files"] has "tests/test_old.py" but the file is NOT on disk
    # old_tests returns it; reading its text raises OSError → skipped
    # No rule-a or rule-b line
    files = {"pkg/core.py": [], "tests/test_new.py": [], "tests/test_old.py": []}
    imports = {"pkg/core.py": [], "tests/test_new.py": ["core"], "tests/test_old.py": ["core"]}
    cmap = {"test_dir": "tests", "files": files, "imports": imports}
    _write(tmp_path, "pkg/core.py", f'TEXT = "{LONG}"\n')
    _write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    # tests/test_old.py NOT written
    task = {"goal": "fix TEXT", "files": ["pkg/core.py"], "tests": ["tests/test_new.py"]}
    lines = _run(tmp_path, monkeypatch, task, cmap)
    # file unreadable → no rule lines for it
    rule_lines = [l for l in lines if "holds text from" in l]
    # 0 rule-a lines
    assert len(rule_lines) == 0


def test_not_in_old_tests(tmp_path, monkeypatch):
    # tests/test_plain.py does NOT import "core" → not in old_tests
    # Its text contains LONG from pkg/core.py, but it's not an old test → no rule line
    _write(tmp_path, "pkg/core.py", f'TEXT = "{LONG}"\n')
    _write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    _write(tmp_path, "tests/test_plain.py",
           f'assert "{LONG}" in x\n')
    task = {"goal": "fix TEXT", "files": ["pkg/core.py"], "tests": ["tests/test_new.py"]}
    files = {"pkg/core.py": [], "tests/test_new.py": [], "tests/test_plain.py": []}
    imports = {"pkg/core.py": [], "tests/test_new.py": ["core"], "tests/test_plain.py": []}
    cmap = {"test_dir": "tests", "files": files, "imports": imports}
    lines = _run(tmp_path, monkeypatch, task, cmap)
    # test_plain not in old_tests → no rule-a line
    a_lines = [l for l in lines if "holds text from" in l]
    # 0 rule-a lines
    assert len(a_lines) == 0


def test_rule_lines_after_existing(tmp_path, monkeypatch):
    # tests/test_old.py triggers warning 4 (imports core) AND rule (a) (contains LONG)
    # rule (a) line must come after the warning-4 line
    _write(tmp_path, "pkg/core.py", f'TEXT = "{LONG}"\n')
    _write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    _write(tmp_path, "tests/test_old.py",
           f'import core\nassert "{LONG}" in core.TEXT\n')
    task = {"goal": "fix TEXT", "files": ["pkg/core.py"], "tests": ["tests/test_new.py"]}
    cmap = _cmap(["pkg/core.py"], ["tests/test_new.py", "tests/test_old.py"])
    lines = _run(tmp_path, monkeypatch, task, cmap)
    # warning 4 line
    w4 = [i for i, l in enumerate(lines) if "imports a file this task changes" in l]
    # rule-a line
    ra = [i for i, l in enumerate(lines) if "holds text from" in l]
    # rule-a comes after warning 4
    # 1 warning-4 line at index < 1 rule-a line
    assert len(w4) == 1 and len(ra) == 1
    assert w4[0] < ra[0]


def test_string_from_one_file_only(tmp_path, monkeypatch):
    # pkg/core.py has LONG (34 chars)
    # pkg/util.py has LONG_30 (30 chars)
    # tests/test_old.py contains LONG (from core) but NOT LONG_30
    # rule (a): only core's string matches → one line naming pkg/core.py
    _write(tmp_path, "pkg/core.py", f'TEXT = "{LONG}"\n')
    _write(tmp_path, "pkg/util.py", f'VAL = "{LONG_30}"\n')
    _write(tmp_path, "tests/test_new.py", "def test_a():\n    pass\n")
    _write(tmp_path, "tests/test_old.py",
           f'import core\nassert "{LONG}" in core.TEXT\n')
    task = {"goal": "fix text", "files": ["pkg/core.py", "pkg/util.py"],
            "tests": ["tests/test_new.py"]}
    # imports: test_old imports "core" only → in old_tests
    # module_names: core, util. test_old imports ["core"] → "core" in module_names → in old_tests
    files = {"pkg/core.py": [], "pkg/util.py": [],
             "tests/test_new.py": [], "tests/test_old.py": []}
    imports = {"pkg/core.py": [], "pkg/util.py": [],
               "tests/test_new.py": ["core", "util"], "tests/test_old.py": ["core"]}
    cmap = {"test_dir": "tests", "files": files, "imports": imports}
    lines = _run(tmp_path, monkeypatch, task, cmap)
    # LONG is in pkg/core.py; test_old contains LONG; LONG_30 is in pkg/util.py; test_old does NOT contain LONG_30
    # → one rule-a line naming pkg/core.py
    # Expected: 1 line, mentioning core.py not util.py
    a_lines = [l for l in lines if "holds text from" in l]
    # 1 rule-a line, from pkg/core.py
    assert len(a_lines) == 1
    # the line names pkg/core.py
    assert "pkg/core.py" in a_lines[0]
    # the line does NOT name pkg/util.py
    assert "pkg/util.py" not in a_lines[0]
