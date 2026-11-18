"""Tests for check_draft in stratos/plantests.py.

check_draft(root, path) runs pytest --collect-only on the given file.
It calls subprocess.run with encoding='utf-8', errors='replace', and timeout=120.
If the subprocess times out, check_draft returns ('error', 'draft check timed out').
Normal pass/fail logic (syntax_error, collected, import_error, error) stays unchanged.
"""

import subprocess
import sys

import pytest

from stratos.plantests import check_draft


def test_check_draft_passes_encoding_errors_timeout(tmp_path, monkeypatch):
    """subprocess.run must be called with encoding='utf-8', errors='replace', timeout=120."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def test_a(): pass\n", encoding="utf-8")

    captured_kwargs = {}

    def fake_run(cmd, **kwargs):
        captured_kwargs.update(kwargs)

        class FakeResult:
            returncode = 0
            stdout = "1 test collected\n"
            stderr = ""

        return FakeResult()

    monkeypatch.setattr("stratos.plantests.subprocess.run", fake_run)
    result = check_draft(str(tmp_path), "tests/test_x.py")

    assert result == ("collected", "")
    assert captured_kwargs["encoding"] == "utf-8"
    assert captured_kwargs["errors"] == "replace"
    assert captured_kwargs["timeout"] == 120
    assert captured_kwargs["cwd"] == str(tmp_path)
    assert captured_kwargs["capture_output"] is True


def test_check_draft_timeout(tmp_path, monkeypatch):
    """When the subprocess times out, check_draft returns ('error', 'draft check timed out')."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def test_a(): pass\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 120)

    monkeypatch.setattr("stratos.plantests.subprocess.run", fake_run)
    result = check_draft(str(tmp_path), "tests/test_x.py")

    assert result == ("error", "draft check timed out")


def test_check_draft_syntax_error(tmp_path):
    """A file that cannot be parsed returns ('syntax_error', msg)."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def broken(:\n", encoding="utf-8")

    result = check_draft(str(tmp_path), "tests/test_x.py")
    assert result[0] == "syntax_error"


def test_check_draft_collects_ok(tmp_path, monkeypatch):
    """A valid test file that collects successfully returns ('collected', '')."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def test_a(): pass\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        class FakeResult:
            returncode = 0
            stdout = "1 test collected\n"
            stderr = ""

        return FakeResult()

    monkeypatch.setattr("stratos.plantests.subprocess.run", fake_run)
    result = check_draft(str(tmp_path), "tests/test_x.py")
    assert result == ("collected", "")


def test_check_draft_import_error(tmp_path, monkeypatch):
    """A file that fails to import returns ('import_error', tail)."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("import nonexistent_mod_xyz\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        class FakeResult:
            returncode = 2
            stdout = "ModuleNotFoundError: No module named 'nonexistent_mod_xyz'\n"
            stderr = ""

        return FakeResult()

    monkeypatch.setattr("stratos.plantests.subprocess.run", fake_run)
    result = check_draft(str(tmp_path), "tests/test_x.py")
    assert result[0] == "import_error"
    assert "nonexistent_mod_xyz" in result[1]


def test_check_draft_pytest_error(tmp_path, monkeypatch):
    """A file that collects with a generic failure returns ('error', tail)."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def test_a(): pass\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        class FakeResult:
            returncode = 1
            stdout = ""
            stderr = "FAILED tests/test_x.py\n"

        return FakeResult()

    monkeypatch.setattr("stratos.plantests.subprocess.run", fake_run)
    result = check_draft(str(tmp_path), "tests/test_x.py")
    assert result[0] == "error"


def test_check_draft_timeout_preserves_cmd(tmp_path, monkeypatch):
    """The timeout result is the same whatever timeout value the error carries."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def test_a(): pass\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))

    monkeypatch.setattr("stratos.plantests.subprocess.run", fake_run)
    result = check_draft(str(tmp_path), "tests/test_x.py")

    assert result == ("error", "draft check timed out")
