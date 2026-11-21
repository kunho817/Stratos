"""Tests for the modules that use stratos/langs.py (P20, 2026-11-21): verify, checker, plantests and refcheck ask
langs.runner() and langs.child_env() instead of testing config.PROJECT["test_runner"] themselves.

- In stratos/verify.py, checker.py, plantests.py and refcheck.py no code (comments and docstrings aside) names a
  runner: no string literal contains "dotnet" or "DOTNET_CLI_UI_LANGUAGE". (Reading "test_runner" is fine where
  only its text is used: plantests names it in the test writer's prompt. Claude's first test forbade that too.)
- verify.test_cmd(tests) -> langs.runner().test_cmd(tests); verify.dotnet_scope(root, tests) ->
  langs.runner().scope(root, tests) (both names stay: other modules and tests use them).
- verify.run_tests(worktree, tests, parallel) runs langs.runner().test_cmd(tests, parallel=parallel) inside
  langs.runner().scope(worktree, tests), with env langs.child_env(PYTHONHASHSEED=str(seed)) for each seed 1..
  config.VERIFY_RUNS; what it returns is unchanged.
- checker.check builds its command with langs.runner().with_paths(check_command, paths) and runs it with
  env=langs.child_env().
- plantests.check_draft builds its command with langs.runner().with_paths(draft_check_command, [path]) and calls a
  failed check "import_error" exactly when langs.runner().missing_import(output) is true.
- refcheck.check runs its tests with env=langs.child_env()."""
import io
import subprocess
import tokenize
from pathlib import Path

from stratos import checker, config, langs, plantests, verify

ROOT = Path(__file__).resolve().parent.parent


def code_strings(path):
    src = (ROOT / "stratos" / path).read_text(encoding="utf-8")
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    out = []
    for i, t in enumerate(toks):
        if t.type != tokenize.STRING:
            continue
        prev = next((p for p in reversed(toks[:i]) if p.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                                                                       tokenize.DEDENT, tokenize.COMMENT)), None)
        if prev is None or prev.string == ":" and t.string.startswith(('"""', 'r"""')):
            continue   # a docstring
        out.append(t.string)
    return out


def test_no_runner_names_left():
    for name in ("verify.py", "checker.py", "plantests.py", "refcheck.py"):
        strings = code_strings(name)
        assert not [s for s in strings if "dotnet" in s or "DOTNET_CLI_UI_LANGUAGE" in s], name


class Recorder(langs.Runner):
    def __init__(self, project):
        super().__init__(project)
        self.seen = []

    def test_cmd(self, tests, parallel=False):
        self.seen.append(("test_cmd", list(tests), parallel))
        return ["fake-test", *tests]

    def with_paths(self, cmd, paths):
        self.seen.append(("with_paths", list(cmd), list(paths)))
        return ["fake-check", *paths]

    def scope(self, root, tests):
        import contextlib
        seen = self.seen

        @contextlib.contextmanager
        def cm():
            seen.append(("enter", str(root), list(tests)))
            yield
            seen.append(("exit",))
        return cm()

    def missing_import(self, output):
        self.seen.append(("missing_import", output))
        return "NEEDS-A-TYPE" in output


def use(monkeypatch):
    rec = Recorder(config.PROJECT)
    monkeypatch.setattr(langs, "runner", lambda project=None: rec)
    return rec


class Done:
    def __init__(self, code=0, out="1 passed"):
        self.returncode, self.stdout, self.stderr = code, out, ""


def test_verify_wrappers(monkeypatch, tmp_path):
    rec = use(monkeypatch)
    assert verify.test_cmd(["t/a"]) == ["fake-test", "t/a"]
    with verify.dotnet_scope(tmp_path, ["t/a"]):
        pass
    assert rec.seen == [("test_cmd", ["t/a"], False), ("enter", str(tmp_path), ["t/a"]), ("exit",)]


def test_verify_run_tests(monkeypatch, tmp_path):
    rec = use(monkeypatch)
    monkeypatch.setattr(config, "VERIFY_RUNS", 2)
    runs = []

    def fake_run(cmd, **kw):
        runs.append((cmd, kw["env"]["PYTHONHASHSEED"], kw["env"]["DOTNET_CLI_UI_LANGUAGE"], kw["env"]["PYTHONUTF8"]))
        rec.seen.append(("run",))
        return Done()
    monkeypatch.setattr(subprocess, "run", fake_run)
    ok, _ = verify.run_tests(tmp_path, ["t/a"], parallel=True)
    assert ok is True
    assert runs == [(["fake-test", "t/a"], "1", "en", "1"), (["fake-test", "t/a"], "2", "en", "1")]
    assert rec.seen[0] == ("enter", str(tmp_path), ["t/a"]) and rec.seen[-1] == ("exit",)
    assert ("test_cmd", ["t/a"], True) in rec.seen


def test_checker_uses_with_paths(monkeypatch, tmp_path):
    rec = use(monkeypatch)
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "check_command": ["chk"]})
    rec.project = config.PROJECT
    got = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: got.append((cmd, kw["env"]["DOTNET_CLI_UI_LANGUAGE"]))
                        or Done(1, "a.py:3:1 - error: bad"))
    assert checker.check(tmp_path, ["a.py"]) == ["a.py:3: bad"]
    assert got == [(["fake-check", "a.py"], "en")]
    assert rec.seen == [("with_paths", ["chk"], ["a.py"])]


def test_check_draft_uses_the_runner(monkeypatch, tmp_path):
    rec = use(monkeypatch)
    (tmp_path / "t.cs").write_text("x", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "draft_check_command": ["build"]})
    outs = iter([Done(1, "NEEDS-A-TYPE here"), Done(1, "something else broke"), Done(0, "")])
    cmds = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: cmds.append(cmd) or next(outs))
    assert plantests.check_draft(tmp_path, "t.cs")[0] == "import_error"
    assert plantests.check_draft(tmp_path, "t.cs")[0] == "error"
    assert plantests.check_draft(tmp_path, "t.cs") == ("collected", "")
    assert cmds == [["fake-check", "t.cs"]] * 3
    assert ("with_paths", ["build"], ["t.cs"]) in rec.seen
