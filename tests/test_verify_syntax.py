"""Tests for task syntax_errors (P1, 2026-11-20): verify.syntax_errors(root, paths) -> list of str.

A cheap check that runs before any test: the files a model wrote (or a task's test files) must at least compile.
For each path in `paths`, in order (paths are relative to root, POSIX or not):
- a file that does not exist is skipped;
- ".py": compile(source, path, "exec"); a SyntaxError (or ValueError, e.g. a null byte) gives
  f"{path}: line {lineno}: {msg}" (msg is the exception's msg; for a ValueError lineno is 0 and msg its str);
- ".js", ".mjs", ".cjs": `node --check <path>` with cwd=root (timeout config.TEST_TIMEOUT_S); a non-zero exit gives
  f"{path}: {line}" where line is the first stripped line of stderr that contains "SyntaxError", else the last
  non-empty stripped line of stderr. Trap (node 24, found 2026-11-20): without a package.json "type": "module", a
  ".js" file with import/export and a syntax error passes `node --check` (exit 0). So when a ".js" file passes and
  its source has a line matching r"^\s*(import|export)\b" (re.M), check it again with
  `node --input-type=module --check`, the source on stdin (cwd=root), and report a failure the same way;
- any other suffix is not checked.
The path in the message is written as given."""
import shutil

import pytest

from stratos import verify


def write(root, path, text):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_python_ok_and_broken(tmp_path):
    write(tmp_path, "pkg/good.py", "def f(x):\n    return x + 1\n")
    write(tmp_path, "pkg/bad.py", "def f(x:\n    return x\n")
    errors = verify.syntax_errors(tmp_path, ["pkg/good.py", "pkg/bad.py"])
    assert len(errors) == 1
    assert errors[0].startswith("pkg/bad.py: line 1: ")


def test_missing_and_other_files_are_skipped(tmp_path):
    write(tmp_path, "notes.md", "def (((")
    write(tmp_path, "data.json", "{not json")
    assert verify.syntax_errors(tmp_path, ["nope.py", "notes.md", "data.json"]) == []


def test_order_follows_paths(tmp_path):
    write(tmp_path, "a.py", "x = (\n")
    write(tmp_path, "b.py", "y = ]\n")
    errors = verify.syntax_errors(tmp_path, ["b.py", "a.py"])
    assert [e.split(":")[0] for e in errors] == ["b.py", "a.py"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_javascript(tmp_path):
    write(tmp_path, "src/ok.js", "export function f(x) { return x + 1; }\n")
    write(tmp_path, "src/bad.js", "export function f(x) { return x + ; }\n")
    write(tmp_path, "src/bad.mjs", "const a = {;\n")
    errors = verify.syntax_errors(tmp_path, ["src/ok.js", "src/bad.js", "src/bad.mjs"])
    assert len(errors) == 2
    assert errors[0].startswith("src/bad.js: ") and "SyntaxError" in errors[0]
    assert errors[1].startswith("src/bad.mjs: ") and "SyntaxError" in errors[1]
