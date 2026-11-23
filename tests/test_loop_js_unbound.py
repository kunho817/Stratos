"""Tests for task loop_js_unbound: _judge checks JS test files for unbound names.

In stratos/loop.py, in _judge, right after the syntax_errors check passes:
for every written path that ends with ".test.js" or ".test.mjs", or ends
with ".js" or ".mjs" and starts with "tests/", read the file text and call
plantests.js_unbound_calls(text). Collect per-file unbound names. If any
file has names, return ("check_error", "These test files call names they
never import or define:\n<path>: <name1>, <name2>\n...\nImport them or
define them; the tests did not run."). If none, continue as today.
A source file (not a test file by that rule) is not checked.
Import plantests inside _judge via "from . import plantests".
"""
import pytest
from pathlib import Path

from stratos import config, loop, patch, plantests, verify

# ---- fixed data ----

TASK_JS = {"id": "T1", "files": ["tests/a.test.js"], "protected": [],
           "tests": ["tests/a.test.js"], "goal": "g"}

TASK_TWO = {"id": "T1", "files": ["tests/a.test.js", "tests/b.test.mjs"],
            "protected": [], "tests": ["tests/a.test.js", "tests/b.test.mjs"],
            "goal": "g"}

TASK_SRC = {"id": "T1", "files": ["pkg/foo.js"], "protected": [],
            "tests": ["tests/a.test.js"], "goal": "g"}

# ---- answers ----

ANSWER_JS_CLEAN = ("FILE: tests/a.test.js\n```javascript\n"
                   "import { x } from 'y';\n"
                   "test('x', () => { x(1); });\n```\n")

ANSWER_JS_UNBOUND = ("FILE: tests/a.test.js\n```javascript\n"
                     "test('x', () => { makeRng(42); });\n```\n")

ANSWER_TWO = ("FILE: tests/a.test.js\n```javascript\n"
              "test('x', () => { makeRng(42); });\n```\n"
              "FILE: tests/b.test.mjs\n```javascript\n"
              "test('y', () => { helper(1); });\n```\n")

ANSWER_SRC_JS = ("FILE: pkg/foo.js\n```javascript\n"
                 "const y = makeRng(42);\n```\n")

ANSWER_TESTS_JS = ("FILE: tests/helper.js\n```javascript\n"
                   "function helper() { makeRng(1); }\n```\n")

ANSWER_PY = ("FILE: pkg/a.py\n```python\nX = 1\n```\n")

ANSWER_SUB = ("FILE: tests/sub/a.test.js\n```javascript\n"
              "test('x', () => { makeRng(42); });\n```\n")


class FakeJs:
    """Fake for plantests.js_unbound_calls: returns results in sequence."""
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, text):
        self.calls.append(text)
        if self.results:
            return self.results.pop(0)
        return []


def _setup(tmp_path, monkeypatch, js_results=None):
    """Set up a worktree. monkeypatch syntax_errors to pass, run_tests to record,
    dropped_definitions to return empty. If js_results is given, FakeJs pops them
    in order. Create tests/ and pkg/ dirs in tmp_path."""
    monkeypatch.setattr(config, "CHECK", False)
    monkeypatch.setattr(config, "LINT", False)
    monkeypatch.setattr(config, "PREFLIGHT", False)
    monkeypatch.setattr(verify, "syntax_errors", lambda root, paths: [])
    runs = []
    monkeypatch.setattr(verify, "run_tests",
                        lambda w, t: runs.append(list(t)) or (True, "1 passed"))
    monkeypatch.setattr(patch, "dropped_definitions",
                        lambda root, files, goal="": {})
    if js_results is not None:
        monkeypatch.setattr(plantests, "js_unbound_calls", FakeJs(js_results))
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pkg").mkdir(parents=True, exist_ok=True)
    return tmp_path, runs


# ---- 1. single .test.js with unbound names → check_error ----

def test_js_test_file_with_unbound(tmp_path, monkeypatch):
    # .test.js → test file; js_unbound_calls returns ["makeRng"]
    # Expected result: "check_error"
    # Expected detail contains: "tests/a.test.js: makeRng"
    wt, runs = _setup(tmp_path, monkeypatch, js_results=[["makeRng"]])
    result, detail = loop.check_answer(TASK_JS, wt, ANSWER_JS_UNBOUND)
    assert result == "check_error"
    # Expected: the path and name appear in the detail
    assert "tests/a.test.js: makeRng" in detail
    # Expected: tests were NOT run
    assert runs == []


# ---- 2. .test.mjs is also checked ----

def test_test_mjs_checked(tmp_path, monkeypatch):
    # .test.mjs → test file; js_unbound_calls returns ["helper"]
    # Expected result: "check_error"
    wt, runs = _setup(tmp_path, monkeypatch, js_results=[["helper"]])
    result, detail = loop.check_answer(TASK_TWO, wt, ANSWER_TWO)
    # Expected: the first file triggers, second not reached (early return)
    assert result == "check_error"
    # Expected: first file names makeRng
    assert "makeRng" in detail


# ---- 3. .js in tests/ dir is a test file ----

def test_js_in_tests_dir_checked(tmp_path, monkeypatch):
    # tests/helper.js: starts with "tests/" and ends with ".js" → test file
    # js_unbound_calls returns ["makeRng"]
    task = {"id": "T1", "files": ["tests/helper.js"], "protected": [],
            "tests": ["tests/helper.js"], "goal": "g"}
    wt, runs = _setup(tmp_path, monkeypatch, js_results=[["makeRng"]])
    result, detail = loop.check_answer(task, wt, ANSWER_TESTS_JS)
    # Expected: check_error because tests/helper.js is a test file
    assert result == "check_error"
    # Expected: the path is in the detail
    assert "tests/helper.js: makeRng" in detail


# ---- 4. .mjs in tests/ dir is a test file ----

def test_mjs_in_tests_dir_checked(tmp_path, monkeypatch):
    # tests/helper.mjs: starts with "tests/" and ends with ".mjs" → test file
    task = {"id": "T1", "files": ["tests/helper.mjs"], "protected": [],
            "tests": ["tests/helper.mjs"], "goal": "g"}
    answer = ("FILE: tests/helper.mjs\n```javascript\n"
              "function helper() { makeRng(1); }\n```\n")
    wt, runs = _setup(tmp_path, monkeypatch, js_results=[["makeRng"]])
    result, detail = loop.check_answer(task, wt, answer)
    # Expected: check_error
    assert result == "check_error"
    assert "tests/helper.mjs: makeRng" in detail


# ---- 5. source .js NOT in tests/ is not checked ----

def test_source_js_not_checked(tmp_path, monkeypatch):
    # pkg/foo.js: ends ".js" but does NOT start with "tests/" → not a test file
    # Expected: js_unbound_calls is NOT called for this file
    wt, runs = _setup(tmp_path, monkeypatch)
    result, detail = loop.check_answer(TASK_SRC, wt, ANSWER_SRC_JS)
    # Expected: no check_error, tests run
    assert result == "passed"
    # Expected: run_tests was called
    assert len(runs) == 1


# ---- 6. src/foo.test.js IS checked (ends .test.js) ----

def test_src_test_js_is_checked(tmp_path, monkeypatch):
    # src/a.test.js: ends with ".test.js" → test file, even outside tests/
    task = {"id": "T1", "files": ["src/a.test.js"], "protected": [],
            "tests": ["src/a.test.js"], "goal": "g"}
    answer = ("FILE: src/a.test.js\n```javascript\n"
              "test('x', () => { makeRng(42); });\n```\n")
    wt, runs = _setup(tmp_path, monkeypatch, js_results=[["makeRng"]])
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    result, detail = loop.check_answer(task, wt, answer)
    # Expected: check_error
    assert result == "check_error"
    # Expected: path in detail
    assert "src/a.test.js: makeRng" in detail


# ---- 7. two test files: one line per file, names joined by ", " ----

def test_two_files_one_line_each(tmp_path, monkeypatch):
    # ANSWER_TWO writes tests/a.test.js and tests/b.test.mjs
    # js_unbound_calls: first call returns ["makeRng"], second returns ["helper", "tool"]
    wt, runs = _setup(tmp_path, monkeypatch,
                     js_results=[["makeRng"], ["helper", "tool"]])
    result, detail = loop.check_answer(TASK_TWO, wt, ANSWER_TWO)
    # Expected: check_error
    assert result == "check_error"
    # Expected: line "tests/a.test.js: makeRng"
    assert "tests/a.test.js: makeRng" in detail
    # Expected: line "tests/b.test.mjs: helper, tool"
    assert "tests/b.test.mjs: helper, tool" in detail
    # Expected: tests not run
    assert runs == []


# ---- 8. no unbound names → continue, tests run ----

def test_no_unbound_names_tests_run(tmp_path, monkeypatch):
    # js_unbound_calls returns [] → not check_error, tests run
    wt, runs = _setup(tmp_path, monkeypatch, js_results=[[]])
    result, detail = loop.check_answer(TASK_JS, wt, ANSWER_JS_CLEAN)
    # Expected: result is "passed"
    assert result == "passed"
    # Expected: run_tests called once
    assert len(runs) == 1
    # Expected: the test list was passed
    assert runs[0] == ["tests/a.test.js"]


# ---- 9. exact detail format ----

def test_exact_detail_format(tmp_path, monkeypatch):
    # detail must be exactly:
    # "These test files call names they never import or define:\n"
    # "tests/a.test.js: makeRng\n"
    # "Import them or define them; the tests did not run."
    wt, runs = _setup(tmp_path, monkeypatch, js_results=[["makeRng"]])
    result, detail = loop.check_answer(TASK_JS, wt, ANSWER_JS_UNBOUND)
    # Expected: starts with the header
    assert detail.startswith(
        "These test files call names they never import or define:\n")
    # Expected: ends with the footer
    assert detail.endswith("\nImport them or define them; the tests did not run.")
    # Expected: the middle line is "tests/a.test.js: makeRng"
    middle = detail.split("\n")[1]
    assert middle == "tests/a.test.js: makeRng"


# ---- 10. Python files are not checked by JS unbound ----

def test_py_files_not_js_checked(tmp_path, monkeypatch):
    # .py file is not a test file by the JS rule
    # Expected: js_unbound_calls is never called
    wt, runs = _setup(tmp_path, monkeypatch)
    task = {"id": "T1", "files": ["pkg/a.py"], "protected": [],
            "tests": ["tests/a.test.js"], "goal": "g"}
    result, detail = loop.check_answer(task, wt, ANSWER_PY)
    # Expected: tests run, result passed
    assert result == "passed"
    assert len(runs) == 1


# ---- 11. syntax errors block before JS check ----

def test_syntax_errors_block_before_js(tmp_path, monkeypatch):
    # syntax_errors returns errors → JS check is never reached
    monkeypatch.setattr(config, "CHECK", False)
    monkeypatch.setattr(config, "LINT", False)
    monkeypatch.setattr(config, "PREFLIGHT", False)
    monkeypatch.setattr(verify, "syntax_errors",
                        lambda root, paths: ["tests/a.test.js: line 1: SyntaxError"])
    monkeypatch.setattr(patch, "dropped_definitions",
                        lambda root, files, goal="": {})
    js_calls = []
    def fake_js(text):
        js_calls.append(text)
        return []
    monkeypatch.setattr(plantests, "js_unbound_calls", fake_js)
    runs = []
    monkeypatch.setattr(verify, "run_tests",
                        lambda w, t: runs.append(1) or (True, "ok"))
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pkg").mkdir(parents=True, exist_ok=True)
    result, detail = loop.check_answer(TASK_JS, tmp_path, ANSWER_JS_UNBOUND)
    # Expected: syntax_error, not check_error
    assert result == "syntax_error"
    # Expected: js_unbound_calls NOT called
    assert js_calls == []
    # Expected: run_tests NOT called
    assert runs == []


# ---- 12. multiple names in one file joined by ", " ----

def test_names_joined_by_comma(tmp_path, monkeypatch):
    # js_unbound_calls returns ["makeRng", "helper"] for one file
    wt, runs = _setup(tmp_path, monkeypatch,
                     js_results=[["makeRng", "helper"]])
    result, detail = loop.check_answer(TASK_JS, wt, ANSWER_JS_UNBOUND)
    # Expected: check_error
    assert result == "check_error"
    # Expected: names joined by ", "
    assert "tests/a.test.js: makeRng, helper" in detail


# ---- 13. tests/sub/a.test.js is checked (starts with tests/) ----

def test_js_in_tests_subdir(tmp_path, monkeypatch):
    # tests/sub/a.test.js: starts with "tests/" and ends with ".test.js"
    task = {"id": "T1", "files": ["tests/sub/a.test.js"], "protected": [],
            "tests": ["tests/sub/a.test.js"], "goal": "g"}
    wt, runs = _setup(tmp_path, monkeypatch, js_results=[["makeRng"]])
    (tmp_path / "tests" / "sub").mkdir(parents=True, exist_ok=True)
    result, detail = loop.check_answer(task, wt, ANSWER_SUB)
    # Expected: check_error
    assert result == "check_error"
    # Expected: path in detail
    assert "tests/sub/a.test.js: makeRng" in detail


# ---- 14. no JS test files in the answer → tests run ----

def test_no_js_test_files_tests_run(tmp_path, monkeypatch):
    # Answer writes only pkg/a.py (no JS test files)
    task = {"id": "T1", "files": ["pkg/a.py"], "protected": [],
            "tests": ["tests/a.test.js"], "goal": "g"}
    wt, runs = _setup(tmp_path, monkeypatch)
    result, detail = loop.check_answer(task, wt, ANSWER_PY)
    # Expected: tests run
    assert result == "passed"
    # Expected: run_tests called once
    assert len(runs) == 1


# ---- 15. multiple test files: order follows written list ----

def test_files_follow_written_order(tmp_path, monkeypatch):
    # Two files: first has unbound, second has unbound
    # js_unbound_calls pops ["foo"] for first, ["bar"] for second
    # Expected: detail lines in order: tests/a.test.js: foo, tests/b.test.mjs: bar
    wt, runs = _setup(tmp_path, monkeypatch,
                     js_results=[["foo"], ["bar"]])
    result, detail = loop.check_answer(TASK_TWO, wt, ANSWER_TWO)
    # Expected: check_error
    assert result == "check_error"
    # Expected: first line is a.test.js
    lines = detail.split("\n")
    # lines[0] is header, lines[1] is first file, lines[2] is second, lines[3] is footer
    assert lines[1] == "tests/a.test.js: foo"
    assert lines[2] == "tests/b.test.mjs: bar"
