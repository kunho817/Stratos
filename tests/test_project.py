"""Tests for stratos/project.py: load_settings(repo) reads repo/"stratos.toml" (if it exists) and fills
every missing key with a Stratos-default: language "python", source_dirs ["stratos"], test_dir "tests",
writable_suffixes [".py", ".md", ".toml", ".txt", ".json", ".html"] (.html since P12: the dashboard page), test_command ["python","-m","pytest","-q","-p",
"no:cacheprovider"], test_runner "pytest", test_suffixes [".py"], draft_check_command ["python","-m","pytest",
"--collect-only","-q"], example_test "tests/test_diagnose.py". In test_command and draft_check_command the first
element "python" is replaced by sys.executable. Each call returns a fresh dict; the default lists are never shared
between calls."""

import sys
import tomllib
from pathlib import Path

from stratos.project import load_settings

DEFAULTS = {
    "language": "python",
    "source_dirs": ["stratos"],
    "test_dir": "tests",
    "writable_suffixes": [".py", ".md", ".toml", ".txt", ".json", ".html"],
    "test_command": [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
    "test_runner": "pytest",
    "test_suffixes": [".py"],
    "draft_check_command": [sys.executable, "-m", "pytest", "--collect-only", "-q"],
    "example_test": "tests/test_diagnose.py",
}


def test_all_defaults_when_no_toml(tmp_path):
    repo = tmp_path
    settings = load_settings(repo)
    for key, value in DEFAULTS.items():
        assert settings[key] == value, f"key {key!r}"


def test_no_toml_file_path_used(tmp_path):
    """When stratos.toml does not exist, load_settings must not raise."""
    repo = tmp_path
    assert not (repo / "stratos.toml").exists()
    settings = load_settings(repo)
    assert isinstance(settings, dict)


def test_partial_toml_fills_missing_keys(tmp_path):
    toml_path = tmp_path / "stratos.toml"
    toml_path.write_text('language = "rust"\nsource_dirs = ["src"]\n')
    settings = load_settings(tmp_path)
    assert settings["language"] == "rust"
    assert settings["source_dirs"] == ["src"]
    # all other keys get defaults
    for key, value in DEFAULTS.items():
        if key in ("language", "source_dirs"):
            continue
        assert settings[key] == value, f"key {key!r}"


def test_python_replaced_by_sys_executable_in_commands(tmp_path):
    toml_path = tmp_path / "stratos.toml"
    toml_path.write_text(
        'test_command = ["python", "-m", "pytest", "-q"]\n'
        'draft_check_command = ["python", "-m", "pytest", "--collect-only", "-q"]\n'
    )
    settings = load_settings(tmp_path)
    assert settings["test_command"][0] == sys.executable
    assert settings["test_command"][0] != "python"
    assert settings["test_command"][1:] == ["-m", "pytest", "-q"]
    assert settings["draft_check_command"][0] == sys.executable
    assert settings["draft_check_command"][0] != "python"
    assert settings["draft_check_command"][1:] == ["-m", "pytest", "--collect-only", "-q"]


def test_non_python_first_element_not_replaced(tmp_path):
    toml_path = tmp_path / "stratos.toml"
    toml_path.write_text('test_command = ["python3", "-m", "pytest", "-q"]\n')
    settings = load_settings(tmp_path)
    assert settings["test_command"][0] == "python3"


def test_lists_not_shared_between_calls(tmp_path):
    """Each call must return fresh list objects; mutating one must not affect another."""
    repo = tmp_path
    s1 = load_settings(repo)
    s2 = load_settings(repo)
    # lists are distinct objects
    for key in ("source_dirs", "writable_suffixes", "test_command",
                "test_suffixes", "draft_check_command"):
        assert s1[key] is not s2[key], f"{key} list is shared between calls"
        assert s1[key] == s2[key]

    # mutating one does not affect the other
    s1["source_dirs"].append("extra")
    assert "extra" not in s2["source_dirs"]
    s1["test_command"].append("X")
    assert "X" not in s2["test_command"]


def test_returns_new_dict_each_time(tmp_path):
    s1 = load_settings(tmp_path)
    s2 = load_settings(tmp_path)
    assert s1 is not s2
    # mutating the returned dict does not affect a later call
    s1["language"] = "mutated"
    s3 = load_settings(tmp_path)
    assert s3["language"] == "python"


def test_full_toml_overrides_everything(tmp_path):
    toml_path = tmp_path / "stratos.toml"
    toml_path.write_text(
        'language = "go"\n'
        'source_dirs = ["cmd", "pkg"]\n'
        'test_dir = "test"\n'
        'writable_suffixes = [".go", ".mod"]\n'
        'test_command = ["go", "test", "./..."]\n'
        'test_runner = "go"\n'
        'test_suffixes = ["_test.go"]\n'
        'draft_check_command = ["go", "vet", "./..."]\n'
        'example_test = "cmd/main_test.go"\n'
    )
    settings = load_settings(tmp_path)
    assert settings["language"] == "go"
    assert settings["source_dirs"] == ["cmd", "pkg"]
    assert settings["test_dir"] == "test"
    assert settings["writable_suffixes"] == [".go", ".mod"]
    assert settings["test_command"] == ["go", "test", "./..."]
    assert settings["test_runner"] == "go"
    assert settings["test_suffixes"] == ["_test.go"]
    assert settings["draft_check_command"] == ["go", "vet", "./..."]
    assert settings["example_test"] == "cmd/main_test.go"


def test_toml_path_is_repo_slash_stratos_toml(tmp_path, monkeypatch):
    """load_settings must look at repo / "stratos.toml", not a subdirectory."""
    repo = tmp_path
    toml_path = repo / "stratos.toml"
    toml_path.write_text('language = "c"\n')
    settings = load_settings(repo)
    assert settings["language"] == "c"
    # a nested stratos.toml must NOT be picked up
    nested = repo / "sub"
    nested.mkdir()
    (nested / "stratos.toml").write_text('language = "d"\n')
    settings2 = load_settings(repo)
    assert settings2["language"] == "c"


def test_sys_executable_replacement_applies_to_defaults(tmp_path):
    """The default test_command and draft_check_command start with "python";
    the returned values must start with sys.executable, not the literal "python"."""
    settings = load_settings(tmp_path)
    assert settings["test_command"][0] == sys.executable
    assert settings["draft_check_command"][0] == sys.executable


def test_sys_executable_replacement_with_monkeypatch(tmp_path, monkeypatch):
    fake_exe = "/opt/stratos/bin/python3.12"
    monkeypatch.setattr(sys, "executable", fake_exe)
    settings = load_settings(tmp_path)
    assert settings["test_command"][0] == fake_exe
    assert settings["draft_check_command"][0] == fake_exe
