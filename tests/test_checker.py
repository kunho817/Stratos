"""Tests for task checker (P18, 2026-11-21): one static-check step for every language, using the engines language
servers use, run as command-line tools (an LSP conversation was tried and is not worth it for one-shot checks).
pyright on Stratos: 17 errors in 42 files, 3.7 s; of 440 failed attempts so far ~80 were errors a static check can
see (types, attributes, imports, names) - and for C# or Go "does it build" is the main failure.

checker.parse(output, root, paths) -> sorted unique lines f"{path}:{line}: {message}" for the errors in `paths`:
an output line is an error when it matches either
  colon form: r"^\\s*(?P<file>.+?):(?P<line>\\d+)(?::\\d+)?\\s*-?\\s*error\\s*:?\\s*(?P<msg>.+)$" (pyright, gcc style), or
  paren form: r"^\\s*(?P<file>.+?)\\((?P<line>\\d+),\\d+\\)\\s*:\\s*error\\s+(?P<msg>.+)$" (tsc, dotnet, msbuild);
the file is resolved against root and turned into a path relative to root with "/"; errors in other files are
dropped; the message is stripped, and a trailing " [<something>]" (msbuild's project) is cut.
checker.check(root, paths) -> [] when config.PROJECT.get("check_command") is empty or paths is empty; otherwise it
runs the command with every "{files}" item replaced by the paths (or the paths appended when no item is "{files}"),
cwd=root, timeout 120 s (a timeout gives []), and returns parse(stdout + stderr, root, paths)."""
from stratos import checker, config

PYRIGHT = """No configuration file found.
  C:\\w\\pkg\\user.py
  C:\\w\\pkg\\user.py:1:23 - error: "subtract" is unknown import symbol (reportAttributeAccessIssue)
  C:\\w\\pkg\\user.py:6:16 - error: Argument of type "Literal['2']" cannot be assigned (reportArgumentType)
  C:\\w\\pkg\\other.py:2:1 - error: elsewhere
  C:\\w\\pkg\\user.py:9:1 - warning: unused thing
3 errors, 1 warning, 0 informations
"""
DOTNET = r"""C:\w\src\Game.cs(12,5): error CS0103: The name 'scor' does not exist in the current context [C:\w\src\Game.csproj]
C:\w\src\Game.cs(14,9): warning CS0168: The variable 'e' is declared but never used [C:\w\src\Game.csproj]
src/lib.js(3,7): error TS2339: Property 'lenght' does not exist on type 'string'.
"""


def test_parse_colon_form(tmp_path):
    root = "C:\\w"
    got = checker.parse(PYRIGHT, root, ["pkg/user.py"])
    assert got == ['pkg/user.py:1: "subtract" is unknown import symbol (reportAttributeAccessIssue)',
                   "pkg/user.py:6: Argument of type \"Literal['2']\" cannot be assigned (reportArgumentType)"]


def test_parse_paren_form():
    got = checker.parse(DOTNET, "C:\\w", ["src/Game.cs", "src/lib.js"])
    assert got == ["src/Game.cs:12: CS0103: The name 'scor' does not exist in the current context",
                   "src/lib.js:3: TS2339: Property 'lenght' does not exist on type 'string'."]


def test_check_runs_the_command(tmp_path, monkeypatch):
    import sys
    script = tmp_path / "fake_checker.py"
    script.write_text("import sys\nfor f in sys.argv[1:]:\n    print(f'{f}:3:1 - error: bad thing in {f}')\n",
                      encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "check_command": [sys.executable, str(script), "{files}"]})
    assert checker.check(tmp_path, ["a.py", "b.py"]) == ["a.py:3: bad thing in a.py", "b.py:3: bad thing in b.py"]
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "check_command": [sys.executable, str(script)]})
    assert checker.check(tmp_path, ["c.py"]) == ["c.py:3: bad thing in c.py"]
    assert checker.check(tmp_path, []) == []
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "check_command": None})
    assert checker.check(tmp_path, ["a.py"]) == []


def test_dotnet_builds_without_file_paths(tmp_path, monkeypatch):
    """(Claude, 2026-11-21, Settle) `dotnet build <file>.cs` reads the .cs as a project (MSB4025) - every C# attempt
    failed on it; for dotnet the command runs as given, and in English."""
    import subprocess
    seen = []

    class Done:
        returncode = 1
        stdout = "C:\\w\\src\\A.cs(3,1): error CS1002: ; expected [C:\\w\\src\\A.csproj]"
        stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.append((cmd, kw["env"].get("DOTNET_CLI_UI_LANGUAGE")))
                        or Done())
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_runner": "dotnet",
                                            "check_command": ["dotnet", "build", "-v", "q"]})
    assert checker.check("C:\\w", ["src/A.cs"]) == ["src/A.cs:3: CS1002: ; expected"]
    assert seen == [(["dotnet", "build", "-v", "q"], "en")]
