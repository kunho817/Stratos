"""Tests for task t19_syntax: check_draft uses verify.syntax_errors for .py files.

In stratos/plantests.py, check_draft(root, path): for a .py path, verify.syntax_errors(root, [path])
replaces the bare ast.parse call. If syntax_errors returns any lines, check_draft returns
("syntax_error", first_line). A file that passes syntax check proceeds to the pytest --collect-only
subprocess as before. Non-.py files skip the syntax check. This catches SyntaxWarnings
(invalid escape sequences such as "\\." in a string) as errors, where the old ast.parse
silently passed them.
"""

import inspect
import subprocess

import pytest

from stratos import config, plantests, steps, verify


# ---------------------------------------------------------------------------
# 1. A SyntaxWarning (invalid escape) is reported as syntax_error.
# ---------------------------------------------------------------------------

def test_syntax_warning_invalid_escape_is_syntax_error(tmp_path, monkeypatch):
    """x = "\\." in a .py file triggers SyntaxWarning; check_draft returns
    ("syntax_error", <first line of verify.syntax_errors>)."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    # file content: x = "\."  (literal backslash-dot inside a string)
    p.write_text('x = "\\."\n', encoding="utf-8")

    def fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()
    monkeypatch.setattr(plantests.subprocess, "run", fake_run)

    # Use the real verify.syntax_errors
    lines = verify.syntax_errors(str(tmp_path), ["tests/test_x.py"])
    # expected: SyntaxWarning caught as error
    # e.lineno = 1, e.msg contains "invalid escape"
    # message = "tests/test_x.py: line 1: invalid escape sequence '\\.'"
    # expected: len(lines) == 1
    assert len(lines) == 1
    # expected: detail starts with "tests/test_x.py: line 1:"
    assert lines[0].startswith("tests/test_x.py: line 1:")
    # expected: message mentions "invalid escape"
    assert "invalid escape" in lines[0]

    result = plantests.check_draft(str(tmp_path), "tests/test_x.py")
    # expected: status is syntax_error
    assert result[0] == "syntax_error"
    # expected: detail is the first line from syntax_errors
    assert result[1] == lines[0]


# ---------------------------------------------------------------------------
# 2. The detail is the first line returned by verify.syntax_errors.
# ---------------------------------------------------------------------------

def test_first_line_returned_when_multiple_syntax_lines(tmp_path, monkeypatch):
    """syntax_errors returns ["a", "b", "c"]; check_draft returns
    ("syntax_error", "a")."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def test_a(): pass\n", encoding="utf-8")

    def fake_syntax(root, paths):
        return ["a", "b", "c"]
    monkeypatch.setattr(plantests.verify, "syntax_errors", fake_syntax)

    result = plantests.check_draft(str(tmp_path), "tests/test_x.py")
    # expected: status syntax_error, detail is the FIRST line "a"
    assert result == ("syntax_error", "a")


# ---------------------------------------------------------------------------
# 3. A valid .py file passes syntax check and proceeds to pytest.
# ---------------------------------------------------------------------------

def test_valid_py_file_proceeds_to_pytest(tmp_path, monkeypatch):
    """syntax_errors returns [] for a valid file; check_draft runs the
    draft_check subprocess and returns ("collected", "")."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def test_a():\n    assert 1 == 1\n", encoding="utf-8")

    monkeypatch.setattr(plantests.verify, "syntax_errors", lambda r, paths: [])

    def fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = "1 test collected\n"
            stderr = ""
        return R()
    monkeypatch.setattr(plantests.subprocess, "run", fake_run)

    result = plantests.check_draft(str(tmp_path), "tests/test_x.py")
    # expected: syntax check passes → pytest returns 0 → ("collected", "")
    assert result == ("collected", "")


# ---------------------------------------------------------------------------
# 4. A non-.py file skips the syntax check.
# ---------------------------------------------------------------------------

def test_non_py_file_skips_syntax_check(tmp_path, monkeypatch):
    """A .js path does not call verify.syntax_errors; it goes straight to
    the subprocess."""
    p = tmp_path / "tests" / "test_x.js"
    p.parent.mkdir()
    p.write_text("test('a', () => {});\n", encoding="utf-8")

    calls = []
    def spy_syntax(root, paths):
        calls.append((root, paths))
        return []
    monkeypatch.setattr(plantests.verify, "syntax_errors", spy_syntax)

    def fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()
    monkeypatch.setattr(plantests.subprocess, "run", fake_run)

    result = plantests.check_draft(str(tmp_path), "tests/test_x.js")
    # expected: syntax_errors NOT called for .js
    assert calls == []
    # expected: proceeds to subprocess → collected
    assert result == ("collected", "")


# ---------------------------------------------------------------------------
# 5. verify.syntax_errors receives root and [path] as its arguments.
# ---------------------------------------------------------------------------

def test_syntax_errors_gets_root_and_path_list(tmp_path, monkeypatch):
    """verify.syntax_errors is called with root (str) and [path]."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def test_a(): pass\n", encoding="utf-8")

    seen = []
    def spy_syntax(root, paths):
        seen.append((root, paths))
        return []
    monkeypatch.setattr(plantests.verify, "syntax_errors", spy_syntax)

    def fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()
    monkeypatch.setattr(plantests.subprocess, "run", fake_run)

    root = str(tmp_path)
    plantests.check_draft(root, "tests/test_x.py")
    # expected: syntax_errors called once with (root, ["tests/test_x.py"])
    assert len(seen) == 1
    # expected: root is the str
    assert seen[0][0] == root
    # expected: paths is a list of one element
    assert seen[0][1] == ["tests/test_x.py"]


# ---------------------------------------------------------------------------
# 6. An empty syntax_errors list proceeds to the subprocess.
# ---------------------------------------------------------------------------

def test_empty_syntax_errors_proceeds_to_pytest(tmp_path, monkeypatch):
    """syntax_errors returns []; the draft check runs as normal."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def test_a(): pass\n", encoding="utf-8")

    monkeypatch.setattr(plantests.verify, "syntax_errors", lambda r, p: [])

    def fake_run(cmd, **kw):
        class R:
            returncode = 1
            stdout = "ModuleNotFoundError: No module named 'x'\n"
            stderr = ""
        return R()
    monkeypatch.setattr(plantests.subprocess, "run", fake_run)
    monkeypatch.setattr(plantests.langs, "runner", lambda *a: type("R", (), {
        "with_paths": lambda self, cmd, paths: cmd,
        "missing_import": lambda self, out: "ModuleNotFoundError" in out,
    })())

    result = plantests.check_draft(str(tmp_path), "tests/test_x.py")
    # expected: syntax check passes, pytest fails with import error
    # expected: status "import_error"
    assert result[0] == "import_error"


# ---------------------------------------------------------------------------
# 7. A real SyntaxError is still caught.
# ---------------------------------------------------------------------------

def test_real_syntax_error_still_caught(tmp_path, monkeypatch):
    """def test_a(:\n is a SyntaxError; verify.syntax_errors catches it
    and check_draft returns ("syntax_error", detail)."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def test_a(:\n", encoding="utf-8")

    result = plantests.check_draft(str(tmp_path), "tests/test_x.py")
    # expected: syntax_errors catches SyntaxError
    # message = "tests/test_x.py: line 1: <msg>"
    # expected: status is syntax_error
    assert result[0] == "syntax_error"
    # expected: detail starts with "tests/test_x.py: line 1:"
    assert result[1].startswith("tests/test_x.py: line 1:")


# ---------------------------------------------------------------------------
# 8. ast.parse is no longer used in check_draft.
# ---------------------------------------------------------------------------

def test_ast_parse_removed_from_check_draft():
    """check_draft must use verify.syntax_errors, not ast.parse."""
    src = inspect.getsource(plantests.check_draft)
    # expected: no "ast.parse" in the source
    assert "ast.parse" not in src
    # expected: "syntax_errors" appears in the source
    assert "syntax_errors" in src


# ---------------------------------------------------------------------------
# 9. The detail string is the syntax_errors line, not str(exception).
# ---------------------------------------------------------------------------

def test_detail_is_syntax_errors_line_not_str_of_exception(tmp_path, monkeypatch):
    """The returned detail is the line from syntax_errors (formatted
    "path: line N: msg"), not str(SyntaxError(...))."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def test_a(): pass\n", encoding="utf-8")

    marker = "tests/test_x.py: line 3: hello"
    monkeypatch.setattr(plantests.verify, "syntax_errors", lambda r, paths: [marker])

    result = plantests.check_draft(str(tmp_path), "tests/test_x.py")
    # expected: detail is exactly the string from syntax_errors
    # expected: not str(SyntaxError(...))
    assert result == ("syntax_error", marker)
    # expected: the format "path: line N: msg" is preserved
    assert "tests/test_x.py: line 3: hello" == result[1]


# ---------------------------------------------------------------------------
# 10. The existing check_draft syntax-error test scenario still passes.
# ---------------------------------------------------------------------------

def test_existing_syntax_scenario(tmp_path):
    """def broken(:\n → ("syntax_error", non-empty detail)."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def broken(:\n", encoding="utf-8")
    result = plantests.check_draft(str(tmp_path), "tests/test_x.py")
    # expected: status syntax_error, detail truthy
    assert result[0] == "syntax_error"
    assert result[1]
    # expected: detail follows syntax_errors format
    # "tests/test_x.py: line 1: ..."
    assert result[1].startswith("tests/test_x.py: line 1:")
