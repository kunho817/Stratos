"""Tests for task lint (P6, 2026-11-20): mechanical checks and fixes of the Python files a model wrote, with ruff
(run as `sys.executable -m ruff`, installed in Stratos's own environment, so a project needs nothing).
History: 12 failed attempts were NameErrors, and 5 of 43 review rejections were about unused code.

lint.ERRORS = ("F821", "F822", "F823"): undefined names, the codes that are certain bugs.
lint.FIXES = ("F401",): unused imports, the one fix that cannot change behaviour.

lint.available() -> True when `sys.executable -m ruff --version` exits 0 (checked once and cached).

lint.check(root, paths) -> list of lines f"{path}:{row}:{col}: {code} {message}" for the .py files among paths that
exist under root, with only the ERRORS codes (`ruff check --no-cache --select F821,F822,F823 --output-format json`
with cwd=root; path written relative to root in POSIX form). [] when no .py path, or when ruff is not available.

lint.fix(root, paths) -> the sorted list of paths whose content the FIXES changed (`ruff check --no-cache --fix
--select F401` on those .py files); [] when nothing changed or ruff is not available."""
import pytest

from stratos import lint

pytestmark = pytest.mark.skipif(not lint.available(), reason="ruff is not installed")


def write(root, path, text):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_codes():
    assert lint.ERRORS == ("F821", "F822", "F823")
    assert lint.FIXES == ("F401",)


def test_check_finds_undefined_names_only(tmp_path):
    write(tmp_path, "pkg/a.py", "import os\n\n\ndef f():\n    return json.dumps(1)\n")
    write(tmp_path, "pkg/b.py", "def g():\n    x = 1\n    return 2\n")
    write(tmp_path, "src/c.js", "const x = y;\n")
    out = lint.check(tmp_path, ["pkg/a.py", "pkg/b.py", "src/c.js", "pkg/gone.py"])
    assert len(out) == 1
    assert out[0].startswith("pkg/a.py:5:12: F821 ")
    assert "json" in out[0]
    assert lint.check(tmp_path, ["src/c.js"]) == []


def test_fix_removes_unused_imports_and_reports_the_files(tmp_path):
    write(tmp_path, "pkg/a.py", "import os\nimport sys\n\n\ndef f():\n    return sys.argv\n")
    write(tmp_path, "pkg/b.py", "def g():\n    return 1\n")
    assert lint.fix(tmp_path, ["pkg/b.py", "pkg/a.py"]) == ["pkg/a.py"]
    text = (tmp_path / "pkg" / "a.py").read_text(encoding="utf-8")
    assert "import os" not in text and "import sys" in text
    assert lint.fix(tmp_path, ["pkg/a.py"]) == []


def test_unused_variables_are_left_alone(tmp_path):
    write(tmp_path, "pkg/a.py", "def f():\n    x = compute()\n    return 1\n\n\ndef compute():\n    return 2\n")
    before = (tmp_path / "pkg" / "a.py").read_text(encoding="utf-8")
    assert lint.fix(tmp_path, ["pkg/a.py"]) == []
    assert (tmp_path / "pkg" / "a.py").read_text(encoding="utf-8") == before
