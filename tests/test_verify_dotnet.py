"""Tests for task verify_dotnet (P19, 2026-11-21, C#): `dotnet test` runs a solution, not a file, so a task's test
files become a filter; its CLI prints in the Windows language (Korean here) unless told otherwise.

verify.run_tests: when config.PROJECT["test_runner"] == "dotnet", the command is test_command + ["--filter",
"|".join(f"FullyQualifiedName~{name}" for each test)] where name is the file stem of the test path ("::" part cut;
"tests/Game.Tests/BoardTests.cs" -> "BoardTests"), no paths appended; and the environment of every run also has
DOTNET_CLI_UI_LANGUAGE=en. Other runners as before.
plantests.check_draft: when the runner is "dotnet", the draft check command (draft_check_command, e.g. dotnet build)
runs without the draft path appended; its exit code decides "collected" as before."""
import subprocess

from stratos import config, plantests, verify


class Done:
    returncode = 0
    stdout = "Passed!  - Failed: 0, Passed: 1, Skipped: 0, Total: 1"
    stderr = ""


def test_run_tests_filters_by_class(monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.append((cmd, kw["env"])) or Done())
    monkeypatch.setattr(config, "VERIFY_RUNS", 1)
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_runner": "dotnet",
                                            "test_command": ["dotnet", "test", "--nologo"]})
    assert verify.run_tests(".", ["tests/Game.Tests/BoardTests.cs", "tests/Game.Tests/LevelTests.cs::X"])[0]
    cmd, env = seen[0]
    assert cmd == ["dotnet", "test", "--nologo", "--filter", "FullyQualifiedName~BoardTests|FullyQualifiedName~LevelTests"]
    assert env["DOTNET_CLI_UI_LANGUAGE"] == "en"


def test_other_runners_unchanged(monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.append(cmd) or Done())
    monkeypatch.setattr(config, "VERIFY_RUNS", 1)
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_runner": "pytest", "test_command": ["pytest", "-q"]})
    verify.run_tests(".", ["tests/test_a.py"])
    assert seen[0] == ["pytest", "-q", "tests/test_a.py"]


def test_check_draft_runs_the_build_without_a_path(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.append(cmd) or Done())
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_runner": "dotnet",
                                            "draft_check_command": ["dotnet", "build", "--nologo"]})
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "BoardTests.cs").write_text("class BoardTests {}", encoding="utf-8")
    assert plantests.check_draft(tmp_path, "tests/BoardTests.cs")[0] == "collected"
    assert seen == [["dotnet", "build", "--nologo"]]
