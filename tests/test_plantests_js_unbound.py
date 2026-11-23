"""Tests for task plantests_js_unbound: js_unbound_calls(text) and check_draft "unbound" status.

js_unbound_calls(text) -> sorted list of names called as name( in text that are NOT:
  imported (import {a, b as c}, import d from, import * as e),
  declared (function f, const/let/var g, class h, function/arrow parameters),
  a property call (.name( ),
  a JS keyword (if, for, while, switch, catch, function, return, typeof, new, super, await),
  a common global (test, it, describe, before, after, beforeEach, afterEach, assert, expect,
    require, console, Math, JSON, Object, Array, Number, String, Boolean, Symbol, Set, Map,
    Promise, Error, TypeError, RangeError, Date, RegExp, parseInt, parseFloat, isNaN,
    structuredClone, setTimeout, clearTimeout, queueMicrotask, fetch).

check_draft(root, path): for a .js or .mjs file, if js_unbound_calls is non-empty,
  status "unbound" with line "uses names it never imports or defines: <names>".
"""

import subprocess

from stratos import config, langs, plantests, steps
from stratos.plantests import check_draft, js_unbound_calls


# ---------- js_unbound_calls ----------

def test_js_unbound_basic_call():
    # text "foo()" → foo is called, not imported/declared/keyword/global
    # Expected: ["foo"]
    assert js_unbound_calls("foo()") == ["foo"]


def test_js_unbound_import_named_excluded():
    # "import {foo, bar} from 'x';\nfoo(); bar();"
    # foo, bar are imported → no unbound
    # Expected: []
    text = "import {foo, bar} from 'x';\nfoo(); bar();\n"
    assert js_unbound_calls(text) == []


def test_js_unbound_import_as_excluded():
    # "import {b as c} from 'x';\nc();"
    # c is the imported name (the alias) → not unbound
    # Expected: []
    text = "import {b as c} from 'x';\nc();\n"
    assert js_unbound_calls(text) == []


def test_js_unbound_import_default_star_excluded():
    # "import d from 'x';\nimport * as e from 'y';\nd(); e();"
    # d (default) and e (namespace) are imported
    # Expected: []
    text = "import d from 'x';\nimport * as e from 'y';\nd(); e();\n"
    assert js_unbound_calls(text) == []


def test_js_unbound_function_declared_excluded():
    # "function f() { f(); }"
    # f is declared by `function f`, so f() is not unbound
    # Expected: []
    text = "function f() { f(); }\n"
    assert js_unbound_calls(text) == []


def test_js_unbound_const_let_var_declared_excluded():
    # "const g = () => { g(); }\nlet h = 1; h();\nvar k = 2; k();"
    # g (const), h (let), k (var) are declared
    # Expected: []
    text = "const g = () => { g(); }\nlet h = 1; h();\nvar k = 2; k();\n"
    assert js_unbound_calls(text) == []


def test_js_unbound_class_declared_excluded():
    # "class H {}\nnew H();"
    # H is declared as class; new is a keyword
    # Expected: []
    text = "class H {}\nnew H();\n"
    assert js_unbound_calls(text) == []


def test_js_unbound_property_call_excluded():
    # "obj.foo(); arr.push(x);"
    # .foo( and .push( are property calls, excluded
    # Expected: []
    text = "obj.foo(); arr.push(x);\n"
    assert js_unbound_calls(text) == []


def test_js_unbound_keywords_excluded():
    # "if (x) { } for (let i=0; i<3; i++) { } while (y) { }"
    # if, for, while are keywords → excluded
    # Expected: []
    text = "if (x) { } for (let i = 0; i < 3; i++) { } while (y) { }\n"
    assert js_unbound_calls(text) == []


def test_js_unbound_globals_excluded():
    # "test(() => {}); console.log(x); Math.max(1,2);"
    # test is a global, console is a global, .log/.max are property calls
    # Expected: []
    text = "test(() => {}); console.log(x); Math.max(1, 2);\n"
    assert js_unbound_calls(text) == []


def test_js_unbound_arrow_params_excluded():
    # "const f = (a, b) => { a(); b(); }"
    # f is const, a and b are arrow parameters
    # Expected: []
    text = "const f = (a, b) => { a(); b(); }\n"
    assert js_unbound_calls(text) == []


def test_js_unbound_sorted_output():
    # "zz(); aa();"
    # zz, aa are both unbound; sorted → ["aa", "zz"]
    text = "zz(); aa();\n"
    # Expected: ["aa", "zz"]
    assert js_unbound_calls(text) == ["aa", "zz"]


# ---------- check_draft unbound for .js and .mjs ----------

def _mock_draft_check(monkeypatch, root, path):
    """Set up stubs so check_draft's subprocess run succeeds and langs is neutralised."""
    # Mock subprocess.run to return success
    monkeypatch.setattr(
        "stratos.plantests.subprocess.run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
    )
    # Mock langs.runner and child_env so check_draft does not need the real runner
    class _Runner:
        def with_paths(self, cmd, paths):
            return cmd + list(paths)
        def missing_import(self, output):
            return False
    monkeypatch.setattr(langs, "runner", lambda project=None: _Runner())
    monkeypatch.setattr(langs, "child_env", lambda **kw: {})
    monkeypatch.setattr(
        config, "PROJECT",
        {**config.PROJECT, "draft_check_command": ["node", "--check"]},
    )
    # steps.timed needs a no-op context manager
    import contextlib
    monkeypatch.setattr(steps, "timed", lambda name: contextlib.contextmanager(lambda: (yield))())


def test_check_draft_js_unbound(tmp_path, monkeypatch):
    # File tests/test_x.js contains "foo(); bar();"
    # subprocess returns 0 → normal check passes
    # js_unbound_calls("foo(); bar();") → ["bar", "foo"] (sorted)
    # Expected: status "unbound", detail "uses names it never imports or defines: bar, foo"
    p = tmp_path / "tests" / "test_x.js"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("foo(); bar();\n", encoding="utf-8")
    _mock_draft_check(monkeypatch, tmp_path, "tests/test_x.js")
    status, detail = check_draft(str(tmp_path), "tests/test_x.js")
    # Expected: unbound
    assert status == "unbound"
    # names sorted: bar < foo
    assert detail == "uses names it never imports or defines: bar, foo"


def test_check_draft_mjs_unbound(tmp_path, monkeypatch):
    # Same as above but .mjs
    # File tests/test_y.mjs contains "alpha(); beta();"
    # js_unbound_calls → ["alpha", "beta"] (sorted)
    p = tmp_path / "tests" / "test_y.mjs"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("alpha(); beta();\n", encoding="utf-8")
    _mock_draft_check(monkeypatch, tmp_path, "tests/test_y.mjs")
    status, detail = check_draft(str(tmp_path), "tests/test_y.mjs")
    # Expected: unbound with sorted names alpha, beta
    assert status == "unbound"
    assert detail == "uses names it never imports or defines: alpha, beta"


def test_check_draft_py_no_unbound(tmp_path, monkeypatch):
    # File tests/test_x.py is NOT .js/.mjs, so unbound check does not apply
    # Mock subprocess.run to return success → "collected"
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("def test_a():\n    pass\n", encoding="utf-8")
    _mock_draft_check(monkeypatch, tmp_path, "tests/test_x.py")
    status, detail = check_draft(str(tmp_path), "tests/test_x.py")
    # Expected: collected, not unbound
    assert status == "collected"
