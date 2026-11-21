"""Tests for stratos/langs.py (P20, 2026-11-21): one place per test runner for what differs between languages.

Until now `config.PROJECT.get("test_runner") == "dotnet"` branches sat in verify, checker, plantests and refcheck,
and C# brought 7 harness bugs found one run at a time. langs gathers them:

langs.runner(project=None) -> the Runner for project["test_runner"] (project None -> config.PROJECT, read at call
time): "pytest" -> Pytest(), "node --test" -> NodeTest(), "dotnet" -> Dotnet(), anything else (or no key) -> Runner().
Every Runner keeps the project dict it was made from as `.project`.

Runner (the base; paths are appended):
  test_cmd(tests, parallel=False) -> [*project["test_command"], *tests]
  with_paths(cmd, paths) -> a new list: every "{files}" item replaced by the paths in order; with no "{files}" item
    the paths are appended. (For check_command and draft_check_command.)
  scope(root, tests) -> a context manager that does nothing.
  missing_import(output) -> True when the output names a missing module or type: "ModuleNotFoundError" or
    "ImportError" in it, or a C# error r"error CS0(103|246|234)\\b".
Pytest(Runner): test_cmd(tests, parallel=True) -> [*test_command, "-n", "auto", *tests] when the xdist package can be
  imported (importlib.util.find_spec("xdist") is not None); otherwise as the base.
NodeTest(Runner): the base as it is.
Dotnet(Runner):
  test_cmd(tests, parallel=...) -> [*test_command, "--filter", "|".join(f"FullyQualifiedName~{stem}")] where stem is
    Path(t.split("::")[0]).stem for each test, in order (dotnet takes a class filter, not file paths).
  with_paths(cmd, paths) -> list(cmd) unchanged when no item is "{files}" (`dotnet build` takes a project, not .cs
    files: MSB4025); "{files}" items are still replaced as in the base.
  scope(root, tests): while open, <root>/<test_dir>/Directory.Build.targets (test_dir = project.get("test_dir",
    "tests")) compiles only these test files; removed after (also when the block raises). Content, lines joined
    by "\\n" with a final "\\n":
      <Project>
        <ItemGroup>
          <Compile Remove="$(MSBuildProjectDirectory)/**/*Tests.cs" />
          <Compile Include="$(MSBuildThisFileDirectory)<path of the test relative to test_dir, with />" />   (each)
        </ItemGroup>
      </Project>
    (two-space indents as shown; a test path is cut at "::" and "\\" becomes "/").
langs.child_env(**extra) -> a new dict: os.environ plus PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
  DOTNET_CLI_UI_LANGUAGE="en" (dotnet speaks Korean on this machine otherwise), then the extra items (str values)."""
import importlib.util
import os

import pytest

from stratos import config, langs

PY = {"test_runner": "pytest", "test_command": ["py", "-m", "pytest", "-q"], "test_dir": "tests"}
JS = {"test_runner": "node --test", "test_command": ["node", "--test"], "test_dir": "tests"}
CS = {"test_runner": "dotnet", "test_command": ["dotnet", "test", "--nologo"], "test_dir": "tests"}


def test_runner_by_name():
    assert type(langs.runner(PY)) is langs.Pytest
    assert type(langs.runner(JS)) is langs.NodeTest
    assert type(langs.runner(CS)) is langs.Dotnet
    assert type(langs.runner({"test_runner": "cargo", "test_command": ["cargo", "test"]})) is langs.Runner
    assert type(langs.runner({"test_command": ["x"]})) is langs.Runner
    assert langs.runner(CS).project is CS


def test_runner_reads_the_project_at_call_time(monkeypatch):
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, **CS})
    assert type(langs.runner()) is langs.Dotnet
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, **JS})
    assert type(langs.runner()) is langs.NodeTest


def test_test_cmd_appends_paths():
    assert langs.runner(JS).test_cmd(["tests/a.test.js", "tests/b.test.js"]) == [
        "node", "--test", "tests/a.test.js", "tests/b.test.js"]
    assert langs.runner(JS).test_cmd(["tests/a.test.js"], parallel=True) == ["node", "--test", "tests/a.test.js"]
    assert langs.runner(PY).test_cmd(["tests/test_a.py::test_x"]) == ["py", "-m", "pytest", "-q",
                                                                      "tests/test_a.py::test_x"]


def test_pytest_parallel_uses_xdist_when_installed(monkeypatch):
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: object() if name == "xdist" else real(name, *a))
    assert langs.runner(PY).test_cmd(["tests/t.py"], parallel=True) == ["py", "-m", "pytest", "-q", "-n", "auto",
                                                                       "tests/t.py"]
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: None if name == "xdist" else real(name, *a))
    assert langs.runner(PY).test_cmd(["tests/t.py"], parallel=True) == ["py", "-m", "pytest", "-q", "tests/t.py"]


def test_dotnet_test_cmd_is_a_class_filter():
    got = langs.runner(CS).test_cmd(["tests/Settle.Tests/SplitTests.cs", "tests/Settle.Tests/CliTests.cs::X"],
                                    parallel=True)
    assert got == ["dotnet", "test", "--nologo", "--filter",
                   "FullyQualifiedName~SplitTests|FullyQualifiedName~CliTests"]


def test_with_paths():
    base = langs.runner(PY)
    assert base.with_paths(["pyright", "{files}", "--x"], ["a.py", "b.py"]) == ["pyright", "a.py", "b.py", "--x"]
    cmd = ["ruff", "check"]
    assert base.with_paths(cmd, ["a.py"]) == ["ruff", "check", "a.py"]
    assert cmd == ["ruff", "check"]   # a new list
    cs = langs.runner(CS)
    assert cs.with_paths(["dotnet", "build", "-v", "q"], ["src/A.cs"]) == ["dotnet", "build", "-v", "q"]
    assert cs.with_paths(["tool", "{files}"], ["src/A.cs"]) == ["tool", "src/A.cs"]


def test_missing_import():
    r = langs.runner(PY)
    assert r.missing_import("E   ModuleNotFoundError: No module named 'pkg.x'")
    assert r.missing_import("ImportError: cannot import name 'y'")
    assert langs.runner(CS).missing_import("A.cs(3,1): error CS0246: The type or namespace name 'Expense'")
    assert langs.runner(CS).missing_import("error CS0103: The name 'x' does not exist")
    assert not r.missing_import("error CS1002: ; expected")
    assert not r.missing_import("AssertionError: 1 != 2")


def test_scope_does_nothing_for_others(tmp_path):
    with langs.runner(PY).scope(tmp_path, ["tests/test_a.py"]):
        assert list(tmp_path.rglob("*")) == []


def test_dotnet_scope_writes_and_removes_the_targets(tmp_path):
    target = tmp_path / "tests" / "Directory.Build.targets"
    with langs.runner(CS).scope(tmp_path, ["tests/Settle.Tests/SplitTests.cs", "tests\\Settle.Tests\\CliTests.cs::Y"]):
        assert target.read_text(encoding="utf-8") == (
            "<Project>\n"
            "  <ItemGroup>\n"
            '    <Compile Remove="$(MSBuildProjectDirectory)/**/*Tests.cs" />\n'
            '    <Compile Include="$(MSBuildThisFileDirectory)Settle.Tests/SplitTests.cs" />\n'
            '    <Compile Include="$(MSBuildThisFileDirectory)Settle.Tests/CliTests.cs" />\n'
            "  </ItemGroup>\n"
            "</Project>\n")
    assert not target.exists()
    with pytest.raises(RuntimeError):
        with langs.runner({**CS, "test_dir": "t"}).scope(tmp_path, ["t/ATests.cs"]):
            assert (tmp_path / "t" / "Directory.Build.targets").exists()
            raise RuntimeError("boom")
    assert not (tmp_path / "t" / "Directory.Build.targets").exists()


def test_dotnet_scope_tolerates_a_removed_file(tmp_path):
    """(T238) the old verify.dotnet_scope ignored an OSError on removal: a run that deleted the file (git clean, a
    test) must not turn into a crash of the harness."""
    target = tmp_path / "tests" / "Directory.Build.targets"
    with langs.runner(CS).scope(tmp_path, ["tests/ATests.cs"]):
        target.unlink()
    assert not target.exists()


def test_langs_source_is_tidy():
    """(T238) Dotnet.with_paths reuses Runner.with_paths for "{files}" (super()), and every import of langs.py is at
    the top of the module."""
    import ast
    import inspect
    src = inspect.getsource(langs)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            assert node in tree.body, f"import inside a function at line {node.lineno}"
    dotnet_with_paths = inspect.getsource(langs.Dotnet.with_paths)
    assert "super()" in dotnet_with_paths and "for " not in dotnet_with_paths


def test_child_env(monkeypatch):
    monkeypatch.setenv("STRATOS_TEST_MARK", "1")
    env = langs.child_env(PYTHONHASHSEED="3")
    assert env["STRATOS_TEST_MARK"] == "1"
    assert (env["PYTHONIOENCODING"], env["PYTHONUTF8"], env["DOTNET_CLI_UI_LANGUAGE"], env["PYTHONHASHSEED"]) == (
        "utf-8", "1", "en", "3")
    env["X_NEW"] = "y"
    assert "X_NEW" not in os.environ
