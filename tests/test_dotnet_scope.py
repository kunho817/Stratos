"""Harness fix (Claude, 2026-11-21, Settle, C#): a .NET test project builds as one unit, so the drafted tests of later
tasks (types not written yet) broke the build for the first task - no test could run, in task runs and in refcheck.

verify.dotnet_scope(root, tests) is a context manager: when config.PROJECT["test_runner"] == "dotnet" it writes
root/<test_dir>/Directory.Build.targets (MSBuild imports it into every project below) with
  <Compile Remove="$(MSBuildProjectDirectory)/**/*Tests.cs" /> and one
  <Compile Include="$(MSBuildThisFileDirectory)<the test path relative to test_dir>" /> per test file of `tests`
  ("::" parts cut, "/" separators), and deletes the file on exit (also after an error); for other runners it does
nothing. verify.run_tests and refcheck.check run the dotnet tests inside it."""
import subprocess

from stratos import config, verify


def test_scope_writes_and_removes_the_targets(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_runner": "dotnet", "test_dir": "tests"})
    (tmp_path / "tests").mkdir()
    target = tmp_path / "tests" / "Directory.Build.targets"
    with verify.dotnet_scope(tmp_path, ["tests/Settle.Tests/SplitTests.cs", "tests/Settle.Tests/ExampleTests.cs::X"]):
        text = target.read_text(encoding="utf-8")
    assert '<Compile Remove="$(MSBuildProjectDirectory)/**/*Tests.cs" />' in text
    assert '<Compile Include="$(MSBuildThisFileDirectory)Settle.Tests/SplitTests.cs" />' in text
    assert '<Compile Include="$(MSBuildThisFileDirectory)Settle.Tests/ExampleTests.cs" />' in text
    assert not target.exists()


def test_other_runners_write_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_runner": "pytest", "test_dir": "tests"})
    (tmp_path / "tests").mkdir()
    with verify.dotnet_scope(tmp_path, ["tests/test_a.py"]):
        assert not (tmp_path / "tests" / "Directory.Build.targets").exists()


def test_run_tests_runs_inside_the_scope(tmp_path, monkeypatch):
    seen = []

    class Done:
        returncode = 0
        stdout = "Total tests: 1"
        stderr = ""

    def run(cmd, **kw):
        seen.append((tmp_path / "tests" / "Directory.Build.targets").exists())
        return Done()
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(config, "VERIFY_RUNS", 1)
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_runner": "dotnet", "test_dir": "tests",
                                            "test_command": ["dotnet", "test"]})
    (tmp_path / "tests").mkdir()
    assert verify.run_tests(tmp_path, ["tests/Settle.Tests/SplitTests.cs"])[0]
    assert seen == [True] and not (tmp_path / "tests" / "Directory.Build.targets").exists()
