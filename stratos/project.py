"""Project settings loading for Stratos.

load_settings(repo) reads repo/"stratos.toml" when it exists and fills every
missing key with the default that describes Stratos itself. Each call returns a
fresh dict; default lists are never shared between calls.
"""

import sys
import tomllib
from pathlib import Path


def _default_settings():
    """Return a fresh dict of Stratos defaults with per-call list copies."""
    return {
        "language": "python",
        "source_dirs": ["stratos"],
        "test_dir": "tests",
        "writable_suffixes": [".py", ".md", ".toml", ".txt", ".json", ".html"],
        "test_command": [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        "test_runner": "pytest",
        "test_suffixes": [".py"],
        "draft_check_command": [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        "example_test": "tests/test_diagnose.py",
        "check_command": None,
    }


def _replace_python_first_element(command):
    """Replace a leading "python" element with sys.executable, if present."""
    if command and command[0] == "python":
        return [sys.executable] + list(command[1:])
    return list(command)


def load_settings(repo):
    """Load settings for the repository at ``repo``.

    Reads ``repo / "stratos.toml"`` when it exists and merges it over the
    Stratos defaults. Missing keys are filled with defaults. In ``test_command``
    and ``draft_check_command`` a leading "python" is replaced by
    ``sys.executable``. A fresh dict is returned on every call.
    """
    settings = _default_settings()

    toml_path = Path(repo) / "stratos.toml"
    if toml_path.exists():
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)

        for key, value in data.items():
            if key in ("test_command", "draft_check_command"):
                settings[key] = _replace_python_first_element(value)
            else:
                settings[key] = value

    # When check_command is not set (missing in both default and stratos.toml) and the project is Python,
    # use pyright if it sits next to sys.executable.
    if settings.get("check_command") is None and settings.get("language") == "python":
        exe = Path(sys.executable).with_name("pyright.exe" if sys.platform == "win32" else "pyright")
        if exe.exists():
            settings["check_command"] = [str(exe), "{files}"]

    return settings
