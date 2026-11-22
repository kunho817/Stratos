"""Tests for task t4: gofmt syntax check for .go files in verify.syntax_errors(root, paths).

stratos/verify.py syntax_errors is extended: a ".go" file is checked via subprocess
["gofmt", "-l", "-e", path] with cwd=root. Each output line matching
"<file>:<line>:<col>: <message>" becomes "<path>: line <line>: <message>" where
path is the relative path as given in `paths`. If shutil.which("gofmt") returns
None, .go files are skipped. Existing .py/.js/.mjs/.cjs behaviour is unchanged.
"""

import shutil
import subprocess

from stratos import verify


def write(root, path, text):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class Result:
    def __init__(self, code, out="", err=""):
        self.returncode = code
        self.stdout = out
        self.stderr = err


def make_run(calls, code, out="", err=""):
    """Fake subprocess.run: records (cmd, cwd) in `calls`, returns a fixed Result."""

    def run(cmd, **kw):
        calls.append((cmd, kw.get("cwd")))
        return Result(code, out, err)

    return run


GO_ERROR_ONE = "pkg/bad.go:2:1: expected 'package', found 'var'\n"
GO_ERROR_TWO = "pkg/bad.go:3:1: expected ')'\npkg/bad.go:5:2: syntax error\n"
GO_ERROR_NESTED = "pkg/sub/bad.go:4:3: expected '}'\n"
GO_ERROR_HIGH = "pkg/a.go:100:1: expected ';'\n"
GO_STDERR = "pkg/bad.go:7:5: unexpected token\n"


def test_go_valid_file_gofmt_is_called(tmp_path, monkeypatch):
    """Valid .go file: gofmt is invoked with cwd=root; exit 0, no syntax errors."""
    write(tmp_path, "pkg/good.go", "package main\n\nfunc main() {}\n")
    calls = []
    monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/gofmt")
    monkeypatch.setattr(subprocess, "run", make_run(calls, 0, "", ""))
    errors = verify.syntax_errors(tmp_path, ["pkg/good.go"])
    # gofmt exit 0, empty stdout+stderr → no colon-triplet lines
    # Expected: []
    assert errors == []
    # gofmt invoked: ["gofmt", "-l", "-e", "pkg/good.go"], cwd=tmp_path
    # Expected: calls == [(["gofmt", "-l", "-e", "pkg/good.go"], tmp_path)]
    assert calls == [(["gofmt", "-l", "-e", "pkg/good.go"], tmp_path)]


def test_go_one_gofmt_error(tmp_path, monkeypatch):
    """One gofmt error line → "<path>: line <line>: <message>"."""
    write(tmp_path, "pkg/bad.go", "package main\nvar x = 3\n")
    calls = []
    monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/gofmt")
    monkeypatch.setattr(subprocess, "run", make_run(calls, 1, "", GO_ERROR_ONE))
    errors = verify.syntax_errors(tmp_path, ["pkg/bad.go"])
    # stderr: "pkg/bad.go:2:1: expected 'package', found 'var'"
    # regex: file="pkg/bad.go", line="2", col="1", msg="expected 'package', found 'var'"
    # message: "pkg/bad.go: line 2: expected 'package', found 'var'"
    # Expected: ["pkg/bad.go: line 2: expected 'package', found 'var'"]
    assert errors == ["pkg/bad.go: line 2: expected 'package', found 'var'"]
    # Expected: one gofmt call
    assert len(calls) == 1


def test_go_multiple_gofmt_errors(tmp_path, monkeypatch):
    """Two gofmt error lines → two messages, in order of appearance."""
    write(tmp_path, "pkg/bad.go", "package main\nfunc f() {\n  x\n}\n")
    calls = []
    monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/gofmt")
    monkeypatch.setattr(subprocess, "run", make_run(calls, 1, "", GO_ERROR_TWO))
    errors = verify.syntax_errors(tmp_path, ["pkg/bad.go"])
    # line 1: "pkg/bad.go:3:1: expected ')'"
    #   → "pkg/bad.go: line 3: expected ')'"
    # line 2: "pkg/bad.go:5:2: syntax error"
    #   → "pkg/bad.go: line 5: syntax error"
    # Expected: ["pkg/bad.go: line 3: expected ')'",
    #           "pkg/bad.go: line 5: syntax error"]
    assert errors == ["pkg/bad.go: line 3: expected ')'",
                      "pkg/bad.go: line 5: syntax error"]


def test_gofmt_missing_skips_go_files(tmp_path, monkeypatch):
    """shutil.which('gofmt') → None → .go files are skipped; no subprocess call."""
    write(tmp_path, "pkg/bad.go", "var x = 3\n")
    calls = []
    monkeypatch.setattr(shutil, "which", lambda x: None)
    monkeypatch.setattr(subprocess, "run", make_run(calls, 1, "", GO_ERROR_ONE))
    errors = verify.syntax_errors(tmp_path, ["pkg/bad.go"])
    # which returns None → gofmt not installed → .go skipped
    # Expected: []
    assert errors == []
    # Expected: calls == [] (no subprocess call)
    assert calls == []


def test_go_nested_path(tmp_path, monkeypatch):
    """The path in the message is the relative path as given in `paths`."""
    write(tmp_path, "pkg/sub/bad.go", "package main\nvar x = 3\nfunc f() {}\n")
    calls = []
    monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/gofmt")
    monkeypatch.setattr(subprocess, "run", make_run(calls, 1, "", GO_ERROR_NESTED))
    errors = verify.syntax_errors(tmp_path, ["pkg/sub/bad.go"])
    # Output: "pkg/sub/bad.go:4:3: expected '}'"
    #   → "pkg/sub/bad.go: line 4: expected '}'"
    # Expected: ["pkg/sub/bad.go: line 4: expected '}'"]
    assert errors == ["pkg/sub/bad.go: line 4: expected '}'"]
    # gofmt cmd uses the relative path
    # Expected: calls[0][0] == ["gofmt", "-l", "-e", "pkg/sub/bad.go"]
    assert calls[0][0] == ["gofmt", "-l", "-e", "pkg/sub/bad.go"]


def test_go_and_py_mixed(tmp_path, monkeypatch):
    """.go with a gofmt error alongside a valid .py: only the gofmt message."""
    write(tmp_path, "pkg/a.go", "var x = 3\n")
    write(tmp_path, "pkg/b.py", "def f():\n    return 1\n")
    calls = []
    monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/gofmt")
    monkeypatch.setattr(subprocess, "run", make_run(calls, 1, "", GO_ERROR_ONE))
    errors = verify.syntax_errors(tmp_path, ["pkg/a.go", "pkg/b.py"])
    # .go: gofmt exit 1 → "pkg/a.go: line 2: expected 'package', found 'var'"
    # .py: compile("def f():\n    return 1\n", "pkg/b.py", "exec") → OK
    # Expected: 1 message
    assert len(errors) == 1
    # Expected: errors[0] == "pkg/a.go: line 2: expected 'package', found 'var'"
    assert errors[0] == "pkg/a.go: line 2: expected 'package', found 'var'"


def test_gofmt_error_in_stderr(tmp_path, monkeypatch):
    """gofmt writes syntax errors to stderr; stdout+stderr are scanned."""
    write(tmp_path, "pkg/bad.go", "package main\nvar x = 3\n")
    calls = []
    monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/gofmt")
    # exit 1, stdout empty, stderr has the error
    monkeypatch.setattr(subprocess, "run", make_run(calls, 1, "", GO_STDERR))
    errors = verify.syntax_errors(tmp_path, ["pkg/bad.go"])
    # stderr: "pkg/bad.go:7:5: unexpected token"
    #   → "pkg/bad.go: line 7: unexpected token"
    # Expected: ["pkg/bad.go: line 7: unexpected token"]
    assert errors == ["pkg/bad.go: line 7: unexpected token"]


def test_gofmt_exit_zero_no_matching_lines(tmp_path, monkeypatch):
    """gofmt exit 0 with -l listing: no colon-triplet lines → no messages."""
    write(tmp_path, "pkg/good.go", "package main\n\nfunc main() {}\n")
    calls = []
    monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/gofmt")
    # exit 0; stdout "pkg/good.go\n" (the -l listing)
    monkeypatch.setattr(subprocess, "run", make_run(calls, 0, "pkg/good.go\n", ""))
    errors = verify.syntax_errors(tmp_path, ["pkg/good.go"])
    # "pkg/good.go" does not match "file:line:col: msg"
    # Expected: []
    assert errors == []


def test_non_go_files_not_checked(tmp_path, monkeypatch):
    """.txt file does not trigger a gofmt call."""
    write(tmp_path, "notes.txt", "var x = 3\n")
    calls = []
    monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/gofmt")
    monkeypatch.setattr(subprocess, "run", make_run(calls, 1, "", GO_ERROR_ONE))
    errors = verify.syntax_errors(tmp_path, ["notes.txt"])
    # .txt → "any other suffix is not checked"
    # Expected: []
    assert errors == []
    # Expected: calls == [] (no gofmt call)
    assert calls == []


def test_go_multiline_high_line_number(tmp_path, monkeypatch):
    """Multi-digit line number (100) is extracted correctly."""
    write(tmp_path, "pkg/a.go", "package main\n\nfunc f() {\n  x\n}\n")
    calls = []
    monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/gofmt")
    monkeypatch.setattr(subprocess, "run", make_run(calls, 1, "", GO_ERROR_HIGH))
    errors = verify.syntax_errors(tmp_path, ["pkg/a.go"])
    # Output: "pkg/a.go:100:1: expected ';'"
    #   file="pkg/a.go", line="100", col="1", msg="expected ';'"
    #   → "pkg/a.go: line 100: expected ';'"
    # Expected: ["pkg/a.go: line 100: expected ';'"]
    assert errors == ["pkg/a.go: line 100: expected ';'"]
