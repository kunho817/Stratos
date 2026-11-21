"""Tests for task dotnet_output (P19, 2026-11-21, C#): `dotnet test --logger "console;verbosity=normal"` (run with
DOTNET_CLI_UI_LANGUAGE=en) prints "  Failed <full test name> [<time>]" for each failing test and a summary
"Failed!  - Failed:     2, Passed:     2, Skipped:     0, Total:     4, Duration: ..." (or "Passed!  - ...").

decide._extract_ids also reads dotnet's lines: a stripped line r"^Failed (\\S.*?) \\[[^\\]]*\\]$" gives the id
(the full test name, with its "(a: 2, ...)" arguments). refcheck.count_tests: when the output has a dotnet summary
(r"Total:\\s*(\\d+)"), total = the last such number and failing = decide._extract_ids(output).
context.coder_system(language): the example path is "relative/path" + the language's extension (".py" python,
".js" javascript, ".cs" csharp, ".go" go, ".rs" rust; ".txt" for others); the fence word stays the language in
lower case."""
import subprocess

from stratos import config, context, decide, refcheck, verify


OUT = """Test run for C:\\w\\tests\\Probe.Tests\\bin\\Debug\\net8.0\\Probe.Tests.dll (.NETCoreApp,Version=v8.0)
[xUnit.net 00:00:00.11]     Probe.Tests.CalcTests.WrongOnPurpose [FAIL]
  Passed Probe.Tests.CalcTests.Pairs(a: 1, b: 1, s: 2) [3 ms]
  Failed Probe.Tests.CalcTests.Pairs(a: 2, b: 2, s: 5) [1 ms]
  Error Message:
   Assert.Equal() Failure: Values differ
  Passed Probe.Tests.CalcTests.AddsTwo [< 1 ms]
  Failed Probe.Tests.CalcTests.WrongOnPurpose [< 1 ms]
Failed!  - Failed:     2, Passed:     2, Skipped:     0, Total:     4, Duration: 9 ms - Probe.Tests.dll (net8.0)
"""


def test_extract_ids_reads_dotnet():
    assert decide._extract_ids(OUT) == ["Probe.Tests.CalcTests.Pairs(a: 2, b: 2, s: 5)",
                                        "Probe.Tests.CalcTests.WrongOnPurpose"]


def test_count_tests_reads_dotnet():
    assert refcheck.count_tests(OUT) == (4, ["Probe.Tests.CalcTests.Pairs(a: 2, b: 2, s: 5)",
                                             "Probe.Tests.CalcTests.WrongOnPurpose"])
    passed = "Passed!  - Failed:     0, Passed:     3, Skipped:     0, Total:     3, Duration: 5 ms - X.dll (net8.0)\n"
    assert refcheck.count_tests(passed) == (3, [])
    # (Claude, Settle) with --logger "console;verbosity=normal" one project prints "Total tests: 1"
    assert refcheck.count_tests("  Passed Settle.Tests.ExampleTests.A [115 ms]\nTotal tests: 1\n     Passed: 1\n") == (1, [])


def test_coder_system_uses_the_language_extension():
    cs = context.coder_system("Csharp")
    assert "FILE: relative/path.cs\n```csharp\n" in cs and "path.py" not in cs
    assert "FILE: relative/path.py\n```python\n" in context.coder_system("Python")
    assert "FILE: relative/path.js\n" in context.coder_system("Javascript")


# ---- was test_dotnet_scope.py ----
# Harness fix (Claude, 2026-11-21, Settle, C#): a .NET test project builds as one unit, so the drafted tests of later
# tasks (types not written yet) broke the build for the first task - no test could run, in task runs and in refcheck.
#
# verify.dotnet_scope(root, tests) is a context manager: when config.PROJECT["test_runner"] == "dotnet" it writes
# root/<test_dir>/Directory.Build.targets (MSBuild imports it into every project below) with
#   <Compile Remove="$(MSBuildProjectDirectory)/**/*Tests.cs" /> and one
#   <Compile Include="$(MSBuildThisFileDirectory)<the test path relative to test_dir>" /> per test file of `tests`
#   ("::" parts cut, "/" separators), and deletes the file on exit (also after an error); for other runners it does
# nothing. verify.run_tests and refcheck.check run the dotnet tests inside it.


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
