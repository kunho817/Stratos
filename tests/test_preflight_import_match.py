"""Tests for task t19_import_match: in stratos/preflight.py, missing_imports counts a
"No module named '<name>'" match only when the line it is on, after stripping leading
whitespace, an optional "E" followed by whitespace, and leading whitespace, starts with
"ModuleNotFoundError:" or "ImportError:". Lines inside assertion messages, printed test
output, or docstrings are ignored.

In missing_imports(output, wt, tests):
- A line like "ModuleNotFoundError: No module named 'x'" → counted (path resolved).
- A line like "E   ModuleNotFoundError: No module named 'x'" → counted.
- A line like "E\tImportError: No module named 'x'" → counted.
- A line inside an assertion message containing "No module named 'x'" → NOT counted.
- A print() output line containing "No module named 'x'" → NOT counted.
- A docstring line containing "No module named 'x'" → NOT counted.
- A bare "No module named 'x'" without the ModuleNotFoundError/ImportError prefix → NOT counted.
- Node.js "Cannot find module" patterns are unaffected.
check() uses missing_imports in step 4; a test printing a fake
"No module named 'x'" in its assertion does not trigger a refusal.
"""

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


# ---------------------------------------------------------------------------
# 1. A real ModuleNotFoundError line is counted.
# ---------------------------------------------------------------------------

def test_real_module_not_found_is_counted(tmp_path):
    wt = make(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": ""})
    out = "ModuleNotFoundError: No module named 'pkg.new'\nFAILED tests/test_a.py"
    result = preflight.missing_imports(out, wt, ["tests/test_a.py"])
    # Line: "ModuleNotFoundError: No module named 'pkg.new'"
    # lstrip → "ModuleNotFoundError: No module named 'pkg.new'"
    # starts with "ModuleNotFoundError:" → valid.
    # Module "pkg.new": first part "pkg" is a dir under wt → path "pkg/new.py".
    # pkg/new.py does not exist under wt → added.
    # Expected: ["pkg/new.py"]
    assert result == ["pkg/new.py"]


# ---------------------------------------------------------------------------
# 2. A real ImportError line is counted.
# ---------------------------------------------------------------------------

def test_real_import_error_is_counted(tmp_path):
    wt = make(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": ""})
    out = "ImportError: No module named 'yaml'\nFAILED tests/test_a.py"
    result = preflight.missing_imports(out, wt, ["tests/test_a.py"])
    # Line starts with "ImportError:" → valid.
    # Module "yaml": first part "yaml" is not a dir, not a .py file under wt
    # → "module:yaml".
    # Expected: ["module:yaml"]
    assert result == ["module:yaml"]


# ---------------------------------------------------------------------------
# 3. Pytest "E" prefix + ModuleNotFoundError is counted.
# ---------------------------------------------------------------------------

def test_pytest_E_prefix_counted(tmp_path):
    wt = make(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": ""})
    out = "E   ModuleNotFoundError: No module named 'pkg.new'\nFAILED tests/test_a.py"
    result = preflight.missing_imports(out, wt, ["tests/test_a.py"])
    # lstrip → "E   ModuleNotFoundError: No module named 'pkg.new'"
    # starts with "E" + space → strip "E" + whitespace → lstrip
    # → "ModuleNotFoundError: No module named 'pkg.new'" → valid.
    # Expected: ["pkg/new.py"]
    assert result == ["pkg/new.py"]


# ---------------------------------------------------------------------------
# 4. Text inside an assertion message is not counted.
# ---------------------------------------------------------------------------

def test_assertion_message_not_counted(tmp_path):
    wt = make(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": ""})
    out = 'assert "No module named \'transit.parse\'" in output\nFAILED tests/test_a.py'
    result = preflight.missing_imports(out, wt, ["tests/test_a.py"])
    # Line: 'assert "No module named \'transit.parse\'" in output'
    # lstrip → 'assert "No module...' → starts with "assert"
    # not "ModuleNotFoundError:" or "ImportError:" → skipped.
    # Expected: []
    assert result == []


# ---------------------------------------------------------------------------
# 5. Text inside print() output is not counted.
# ---------------------------------------------------------------------------

def test_print_output_not_counted(tmp_path):
    wt = make(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": ""})
    out = 'print("No module named \'transit.parse\'")\nFAILED tests/test_a.py'
    result = preflight.missing_imports(out, wt, ["tests/test_a.py"])
    # Line starts with "print(" → not valid.
    # Expected: []
    assert result == []


# ---------------------------------------------------------------------------
# 6. Text inside a docstring is not counted.
# ---------------------------------------------------------------------------

def test_docstring_not_counted(tmp_path):
    wt = make(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": ""})
    out = '  """No module named \'pkg.new\' is expected here"""\nFAILED tests/test_a.py'
    result = preflight.missing_imports(out, wt, ["tests/test_a.py"])
    # lstrip → '"""No module named...' → starts with '"""'
    # not "ModuleNotFoundError:" or "ImportError:" → skipped.
    # Expected: []
    assert result == []


# ---------------------------------------------------------------------------
# 7. Bare "No module named 'x'" without the prefix is not counted.
# ---------------------------------------------------------------------------

def test_bare_no_module_not_counted(tmp_path):
    wt = make(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": ""})
    out = "No module named 'pkg.new'\nFAILED tests/test_a.py"
    result = preflight.missing_imports(out, wt, ["tests/test_a.py"])
    # lstrip → "No module named 'pkg.new'"
    # not "ModuleNotFoundError:" or "ImportError:" → skipped.
    # Expected: []
    assert result == []


# ---------------------------------------------------------------------------
# 8. Leading whitespace + E prefix is counted.
# ---------------------------------------------------------------------------

def test_leading_ws_E_prefix_counted(tmp_path):
    wt = make(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": ""})
    out = "  E  ModuleNotFoundError: No module named 'pkg.new'\nFAILED tests/test_a.py"
    result = preflight.missing_imports(out, wt, ["tests/test_a.py"])
    # lstrip → "E  ModuleNotFoundError: No module named 'pkg.new'"
    # starts with "E" + space → strip "E" + ws → lstrip
    # → "ModuleNotFoundError: No module named 'pkg.new'" → valid.
    # Expected: ["pkg/new.py"]
    assert result == ["pkg/new.py"]


# ---------------------------------------------------------------------------
# 9. check(): assertion with fake text → no refusal.
# ---------------------------------------------------------------------------

def test_check_assertion_fake_not_refused(tmp_path):
    wt = make(tmp_path, {
        "tests/test_a.py": 'def test_a():\n    out = "No module named \'transit.parse\'"\n    assert "No module named \'transit.parse\'" in out\n',
        "transit/parse.py": "def f(): pass\n",
    })
    out = 'assert "No module named \'transit.parse\'" in out\nFAILED tests/test_a.py'
    r = preflight.check(task(["transit/parse.py"], ["tests/test_a.py"]), wt,
                        run=lambda w, t: (False, out))
    # missing_imports: "No module named 'transit.parse'" is on the assert line
    # → line lstrip starts with "assert" → not valid → skipped → [].
    # No entries → step 5: verdict "run", reason "tests fail before the change".
    # Expected: verdict "run"
    assert r["verdict"] == "run"
    # Expected: reason is "tests fail before the change"
    assert r["reason"] == "tests fail before the change"


# ---------------------------------------------------------------------------
# 10. check(): real ModuleNotFoundError → refusal.
# ---------------------------------------------------------------------------

def test_check_real_import_error_refused(tmp_path):
    wt = make(tmp_path, {"tests/test_a.py": "import numpy\n"})
    out = "ModuleNotFoundError: No module named 'numpy'\nFAILED tests/test_a.py"
    r = preflight.check(task(["pkg/a.py"], ["tests/test_a.py"]), wt,
                        run=lambda w, t: (False, out))
    # Line is valid → "module:numpy" → not explained by ["pkg/a.py"] → refuse.
    # Expected: verdict "refuse"
    assert r["verdict"] == "refuse"
    # Expected: reason mentions "numpy"
    assert "numpy" in r["reason"]
    # Expected: output is the run output
    assert r["output"] == out


# ---------------------------------------------------------------------------
# 11. Tab after E is counted.
# ---------------------------------------------------------------------------

def test_tab_after_E_counted(tmp_path):
    wt = make(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": ""})
    out = "E\tModuleNotFoundError: No module named 'pkg.new'\nFAILED tests/test_a.py"
    result = preflight.missing_imports(out, wt, ["tests/test_a.py"])
    # lstrip → "E\tModuleNotFoundError..."
    # E + tab (whitespace) → strip → "ModuleNotFoundError..." → valid.
    # Expected: ["pkg/new.py"]
    assert result == ["pkg/new.py"]


# ---------------------------------------------------------------------------
# 12. Line starting directly with ModuleNotFoundError (no E, no ws) is counted.
# ---------------------------------------------------------------------------

def test_no_E_prefix_direct_counted(tmp_path):
    wt = make(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": ""})
    out = "ModuleNotFoundError: No module named 'pkg.new'\nFAILED tests/test_a.py"
    result = preflight.missing_imports(out, wt, ["tests/test_a.py"])
    # lstrip → "ModuleNotFoundError: No module named 'pkg.new'"
    # starts with "ModuleNotFoundError:" → valid.
    # Expected: ["pkg/new.py"]
    assert result == ["pkg/new.py"]


# ---------------------------------------------------------------------------
# 13. Multiple lines: only valid ones counted.
# ---------------------------------------------------------------------------

def test_multiple_lines_only_valid_counted(tmp_path):
    wt = make(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": ""})
    out = ("ModuleNotFoundError: No module named 'pkg.new'\n"
           'assert "No module named \'pkg.new\'" in x\n'
           "E   ImportError: No module named 'yaml'\n"
           "FAILED tests/test_a.py")
    result = preflight.missing_imports(out, wt, ["tests/test_a.py"])
    # Line 1: valid → pkg/new.py.
    # Line 2: starts with "assert" → skipped.
    # Line 3: valid (E + ws prefix) → module:yaml.
    # Expected: ["pkg/new.py", "module:yaml"]
    assert result == ["pkg/new.py", "module:yaml"]


# ---------------------------------------------------------------------------
# 14. "E" followed by non-whitespace (e.g. "EX") is not counted.
# ---------------------------------------------------------------------------

def test_E_followed_by_nonwhitespace_not_counted(tmp_path):
    wt = make(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": ""})
    out = "EXModuleNotFoundError: No module named 'pkg.new'\nFAILED tests/test_a.py"
    result = preflight.missing_imports(out, wt, ["tests/test_a.py"])
    # lstrip → "EXModuleNotFoundError..."
    # starts with "E" but next char "X" is not whitespace → no strip.
    # "EX..." is not "ModuleNotFoundError:" → skipped.
    # Expected: []
    assert result == []


# ---------------------------------------------------------------------------
# 15. Node.js "Cannot find module" patterns are unaffected.
# ---------------------------------------------------------------------------

def test_node_patterns_unaffected(tmp_path):
    wt = make(tmp_path, {"src/vec.js": "", "tests/levels.test.js": ""})
    abs_path = (wt / "src" / "physics.js").as_posix()
    out = f"Error [ERR_MODULE_NOT_FOUND]: Cannot find module '{abs_path}' imported from {wt / 'tests' / 'x.js'}\nFAILED"
    result = preflight.missing_imports(out, wt, ["tests/levels.test.js"])
    # Node pattern: "Cannot find module '<abs>'" → resolved to src/physics.js.
    # Expected: ["src/physics.js"]
    assert result == ["src/physics.js"]
