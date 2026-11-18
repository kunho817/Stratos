"""Tests for task plantests_project_settings: stratos/plantests.py reads config.PROJECT for
example_test, draft_check_command, language, and test_runner. For Stratos's defaults the
prompt still says pytest, but the values come from config.PROJECT, not hard-coded strings.

plantests.system_prompt(language, test_runner) builds the test writer's system prompt;
TEST_SYSTEM = system_prompt(config.PROJECT["language"], config.PROJECT["test_runner"])."""

import subprocess
import sys
from pathlib import Path

from stratos import config, plantests


def test_config_project_has_required_keys():
    """config.PROJECT must define language, test_runner, example_test, draft_check_command."""
    for key in ("language", "test_runner", "example_test", "draft_check_command"):
        assert key in config.PROJECT, f"config.PROJECT missing key {key}"


def test_stratos_defaults_in_project_config():
    """For Stratos, config.PROJECT names Python and pytest, and points at the existing example."""
    assert config.PROJECT["test_runner"] == "pytest"
    assert config.PROJECT["language"] == "python"
    assert config.PROJECT["example_test"] == "tests/test_diagnose.py"
    assert isinstance(config.PROJECT["draft_check_command"], list)
    assert "--collect-only" in config.PROJECT["draft_check_command"]


def test_test_system_names_language_and_runner():
    """TEST_SYSTEM must include config.PROJECT['language'] and config.PROJECT['test_runner']."""
    assert config.PROJECT["language"].lower() in plantests.TEST_SYSTEM.lower()
    assert config.PROJECT["test_runner"] in plantests.TEST_SYSTEM


def test_test_system_says_pytest_for_stratos_defaults():
    """With Stratos defaults, TEST_SYSTEM mentions pytest."""
    assert "pytest" in plantests.TEST_SYSTEM


def test_test_system_for_non_python_project():
    """For a Rust project the prompt names Rust and cargo test, not pytest."""
    text = plantests.system_prompt("Rust", "cargo test")
    assert "Rust" in text and "cargo test" in text and "pytest" not in text
    assert plantests.TEST_SYSTEM == plantests.system_prompt(config.PROJECT["language"], config.PROJECT["test_runner"])
