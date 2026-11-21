"""One place per test runner for what differs between languages.

Gathers the per-language branches that used to sit in verify, checker, plantests and refcheck,
so C# (and the others) bring their bugs to one place.
"""
import contextlib
import importlib.util
import os
import re
from pathlib import Path

from stratos import config


class Runner:
    def __init__(self, project):
        self.project = project

    def test_cmd(self, tests, parallel=False):
        return [*self.project["test_command"], *tests]

    def with_paths(self, cmd, paths):
        out = []
        for item in cmd:
            if item == "{files}":
                out.extend(paths)
            else:
                out.append(item)
        if "{files}" not in cmd:
            out.extend(paths)
        return out

    @contextlib.contextmanager
    def scope(self, root, tests):
        yield

    def missing_import(self, output):
        if "ModuleNotFoundError" in output or "ImportError" in output:
            return True
        return re.search(r"error CS0(103|246|234)\b", output) is not None


class Pytest(Runner):
    def test_cmd(self, tests, parallel=False):
        if parallel and importlib.util.find_spec("xdist") is not None:
            return [*self.project["test_command"], "-n", "auto", *tests]
        return super().test_cmd(tests, parallel)


class NodeTest(Runner):
    pass


class Dotnet(Runner):
    def test_cmd(self, tests, parallel=False):
        filter_ = "|".join(f"FullyQualifiedName~{Path(t.split('::')[0]).stem}" for t in tests)
        return [*self.project["test_command"], "--filter", filter_]

    def with_paths(self, cmd, paths):
        if "{files}" in cmd:
            return super().with_paths(cmd, paths)
        return list(cmd)

    @contextlib.contextmanager
    def scope(self, root, tests):
        test_dir = self.project.get("test_dir", "tests")
        targets = Path(root) / test_dir / "Directory.Build.targets"
        lines = [
            "<Project>",
            "  <ItemGroup>",
            '    <Compile Remove="$(MSBuildProjectDirectory)/**/*Tests.cs" />',
        ]
        for t in tests:
            rel = t.split("::")[0].replace("\\", "/")
            prefix = test_dir + "/"
            if rel.startswith(prefix):
                rel = rel[len(prefix):]
            lines.append(f'    <Compile Include="$(MSBuildThisFileDirectory){rel}" />')
        lines.append("  </ItemGroup>")
        lines.append("</Project>")
        targets.parent.mkdir(parents=True, exist_ok=True)
        targets.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            yield
        finally:
            with contextlib.suppress(OSError):
                targets.unlink(missing_ok=True)


def runner(project=None):
    if project is None:
        project = config.PROJECT
    name = project.get("test_runner")
    if name == "pytest":
        return Pytest(project)
    if name == "node --test":
        return NodeTest(project)
    if name == "dotnet":
        return Dotnet(project)
    return Runner(project)


def child_env(**extra):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["DOTNET_CLI_UI_LANGUAGE"] = "en"
    for k, v in extra.items():
        env[k] = v
    return env
