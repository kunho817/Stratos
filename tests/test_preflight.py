"""Tests for task preflight (P1, 2026-11-20): stratos/preflight.py checks a task's tests on its base before any model
call, so a task that no coder can pass is handed to a person at once instead of after several attempts and model
switches. Evidence: of 85 first-try failures in 4 projects, 36 tasks were later reset by a person; causes seen: a
test that imports a module another task writes (Orbit T003, a missing After), test files with syntax errors.

preflight.check(task, wt, run=None) -> {"verdict": "run" | "refuse", "reason": str, "output": str}
(run defaults to verify.run_tests; it is called as run(wt, task["tests"]) and returns (passed, output)).
Test paths are task["tests"] with any "::..." suffix cut off. In order:
1. a test path that does not exist under wt -> refuse, reason f"test file missing: {path}" (the first one);
2. verify.syntax_errors(wt, paths) not empty -> refuse, reason "test file has a syntax error: " + the first error;
3. run(wt, task["tests"]); passed -> verdict "run", reason "tests already pass on the base", output "";
4. missing_imports(output, wt, task["tests"]) -> paths the tests import that do not exist or lack a name; the first
   one not in task["files"] -> refuse, reason f"the tests import {path}, which this task does not write: add the
   task that writes it to After, or the file to Files";
   a missing module that is not part of the project -> refuse, reason f"the tests need module {name}, which is not
   installed";
5. otherwise verdict "run", reason "tests fail before the change", output = the run's output.
"output" is "" for every refusal except step 4's (it holds the run's output there).

preflight.missing_imports(output, wt, tests) -> list of repo-relative POSIX paths, in output order, no repeats:
- Python r"cannot import name '(\w+)' from '([\w.]+)' \(([^)]+)\)": group 3 is a file path; inside wt -> relative;
- Python r"No module named '([\w.]+)'": the module's path as a file m.replace(".", "/") + ".py" when its first part
  is a folder or a .py file under wt; otherwise the special entry "module:" + name (not installed);
- node r"Cannot find module '([^']+)'": an absolute path (or file:/// URL) inside wt -> relative;
- node r"The requested module '([^']+)' does not provide an export named": a relative spec, resolved against the
  folder of the first JS test path (suffix .js/.mjs/.cjs) in tests -> relative to wt.
Paths outside wt are left out."""
from pathlib import Path

from stratos import preflight


def make(tmp_path, files):
    for path, text in files.items():
        p = tmp_path / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


def task(files, tests):
    return {"id": "T001", "files": files, "tests": tests, "protected": tests}


def never(wt, tests):
    raise AssertionError("the tests must not run")


def test_missing_test_file(tmp_path):
    wt = make(tmp_path, {"tests/test_a.py": "def test_a():\n    pass\n"})
    r = preflight.check(task(["pkg/a.py"], ["tests/test_a.py::test_a", "tests/test_b.py"]), wt, run=never)
    assert r == {"verdict": "refuse", "reason": "test file missing: tests/test_b.py", "output": ""}


def test_broken_test_file(tmp_path):
    wt = make(tmp_path, {"tests/test_a.py": "def test_a(:\n    pass\n"})
    r = preflight.check(task(["pkg/a.py"], ["tests/test_a.py"]), wt, run=never)
    assert r["verdict"] == "refuse" and r["output"] == ""
    assert r["reason"].startswith("test file has a syntax error: tests/test_a.py: line 1: ")


def test_already_passing(tmp_path):
    wt = make(tmp_path, {"tests/test_a.py": "def test_a():\n    pass\n"})
    seen = []
    r = preflight.check(task(["pkg/a.py"], ["tests/test_a.py"]), wt,
                        run=lambda w, tests: seen.append((w, tests)) or (True, "1 passed"))
    assert r == {"verdict": "run", "reason": "tests already pass on the base", "output": ""}
    assert seen == [(wt, ["tests/test_a.py"])]


def test_fails_for_the_right_reason(tmp_path):
    wt = make(tmp_path, {"tests/test_a.py": "from pkg.a import f\n", "pkg/__init__.py": "", "pkg/a.py": "X = 1\n"})
    out = (f"E   ImportError: cannot import name 'f' from 'pkg.a' ({wt / 'pkg' / 'a.py'})\n"
           "FAILED tests/test_a.py")
    r = preflight.check(task(["pkg/a.py"], ["tests/test_a.py"]), wt, run=lambda w, t: (False, out))
    assert r == {"verdict": "run", "reason": "tests fail before the change", "output": out}


def test_import_of_another_tasks_file(tmp_path):
    wt = make(tmp_path, {"tests/test_a.py": "from pkg.vec import length\n", "pkg/__init__.py": "",
                         "pkg/vec.py": "X = 1\n"})
    out = f"ImportError: cannot import name 'length' from 'pkg.vec' ({wt / 'pkg' / 'vec.py'})"
    r = preflight.check(task(["pkg/a.py"], ["tests/test_a.py"]), wt, run=lambda w, t: (False, out))
    assert r["verdict"] == "refuse" and r["output"] == out
    assert r["reason"] == ("the tests import pkg/vec.py, which this task does not write: add the task that writes it "
                           "to After, or the file to Files")


def test_module_not_installed(tmp_path):
    wt = make(tmp_path, {"tests/test_a.py": "import numpy\n"})
    out = "ModuleNotFoundError: No module named 'numpy'"
    r = preflight.check(task(["pkg/a.py"], ["tests/test_a.py"]), wt, run=lambda w, t: (False, out))
    assert r["verdict"] == "refuse"
    assert r["reason"] == "the tests need module numpy, which is not installed"


def test_missing_imports_python(tmp_path):
    wt = make(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": ""})
    out = "\n".join([
        f"ImportError: cannot import name 'f' from 'pkg.a' ({wt / 'pkg' / 'a.py'})",
        "ModuleNotFoundError: No module named 'pkg.new'",
        f"ImportError: cannot import name 'g' from 'pkg.a' ({wt / 'pkg' / 'a.py'})",
        "ModuleNotFoundError: No module named 'yaml'",
        "ImportError: cannot import name 'h' from 'other' (C:\\elsewhere\\other.py)",
    ])
    assert preflight.missing_imports(out, wt, ["tests/test_a.py"]) == ["pkg/a.py", "pkg/new.py", "module:yaml"]


def test_missing_imports_node(tmp_path):
    wt = make(tmp_path, {"src/vec.js": "", "tests/levels.test.js": ""})
    absolute = (wt / "src" / "physics.js").as_posix()
    out = "\n".join([
        f"Error [ERR_MODULE_NOT_FOUND]: Cannot find module '{Path(absolute)}' imported from {wt / 'tests' / 'x.js'}",
        "SyntaxError: The requested module '../src/vec.js' does not provide an export named 'length'",
        f"Error: Cannot find module 'file:///{absolute}'",
    ])
    assert preflight.missing_imports(out, wt, ["tests/levels.test.js"]) == ["src/physics.js", "src/vec.js"]


def test_node_import_of_another_tasks_file(tmp_path):
    wt = make(tmp_path, {"src/vec.js": "export const add = 1;\n", "tests/levels.test.js": "import { length } from '../src/vec.js';\n"})
    out = "SyntaxError: The requested module '../src/vec.js' does not provide an export named 'length'"
    r = preflight.check(task(["src/levels.js"], ["tests/levels.test.js"]), wt, run=lambda w, t: (False, out))
    assert r["verdict"] == "refuse" and "src/vec.js" in r["reason"]
