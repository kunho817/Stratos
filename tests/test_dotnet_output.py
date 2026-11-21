"""Tests for task dotnet_output (P19, 2026-11-21, C#): `dotnet test --logger "console;verbosity=normal"` (run with
DOTNET_CLI_UI_LANGUAGE=en) prints "  Failed <full test name> [<time>]" for each failing test and a summary
"Failed!  - Failed:     2, Passed:     2, Skipped:     0, Total:     4, Duration: ..." (or "Passed!  - ...").

decide._extract_ids also reads dotnet's lines: a stripped line r"^Failed (\\S.*?) \\[[^\\]]*\\]$" gives the id
(the full test name, with its "(a: 2, ...)" arguments). refcheck.count_tests: when the output has a dotnet summary
(r"Total:\\s*(\\d+)"), total = the last such number and failing = decide._extract_ids(output).
context.coder_system(language): the example path is "relative/path" + the language's extension (".py" python,
".js" javascript, ".cs" csharp, ".go" go, ".rs" rust; ".txt" for others); the fence word stays the language in
lower case."""
from stratos import context, decide, refcheck

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
