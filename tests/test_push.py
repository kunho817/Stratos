r"""Tests for tasks push and push_cli: `stratos push` sends a finished chunk (a "P") to the remote, only when it is
safe (user, 2026-11-19: push once per P).

push.SECRET_PATTERNS: regular expressions for secrets in added lines: r"sk-[A-Za-z0-9_-]{20,}",
r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]".
push.SECRET_FILES: file names that must not be pushed: ".env", "credentials.json", "settings.local.json", "id_rsa",
and any name ending in ".pem" or ".key".

push.secret_hits(diff) -> list of str, in diff order: for a line "+++ b/<path>" whose last path part is a secret file
name: f"file: {path}"; for another line that starts with "+" (not "+++") and matches a pattern:
f"line: {line[1:].strip()[:80]}".

push.all_tests(root, settings) -> sorted POSIX paths (relative to root) of the files under settings["test_dir"]
(recursive) whose name ends with one of settings["test_suffixes"]; for the suffix ".py" the name must also start with
"test_".

push.check(repo, run_tests) -> (ok, messages, info), all git through gitops.git(repo, ...):
- no remote "origin" (git remote get-url origin fails) -> (False, ["no remote 'origin'"], {"skip": True});
- branch = git rev-parse --abbrev-ref HEAD; not "main" or "master" -> message f"on branch {branch}, not main";
- git status --porcelain --untracked-files=no not empty -> "uncommitted changes";
- base = f"origin/{branch}" when git rev-parse --verify --quiet <base> works, else None (nothing pushed yet);
  ahead = git rev-list --count <base>..HEAD (or HEAD when base is None); ahead 0 -> (True, ["nothing to push"],
  info) without running the tests;
- secret_hits of git diff <base>..HEAD (or git show --format= --patch --root on every commit: use
  `git log -p --format= HEAD` when base is None) -> one message f"secret? {hit}" per hit;
- run_tests() -> (passed, output); not passed -> "tests failed".
ok is True when there is no message (other than "nothing to push"). info = {"branch", "ahead", "skip": False}.

push.push(repo, telemetry, run_tests, dry_run=False, log=print) -> exit code:
- skip -> log "push: no remote, skipped", 0;
- not ok -> log each message as f"push: {m}", then "push: refused", 1;
- ahead 0 -> log "push: nothing to push", 0;
- dry_run -> log f"push: would push {ahead} commits to origin/{branch}", 0;
- git push origin <branch>; telemetry.record("push", branch=branch, commits=ahead); log f"push: pushed {ahead}
  commits to origin/{branch}", 0. A failing push -> log f"push: {error}", 1.

`stratos push [--dry-run]`: push.push(config.REPO, Telemetry(config.STATE_DIR / "telemetry.jsonl"),
lambda: verify.run_tests(config.REPO, push.all_tests(config.REPO, config.PROJECT)), dry_run=args.dry_run) and returns
its exit code."""
import subprocess

import pytest

from stratos import __main__ as cli
from stratos import config, push, verify
from stratos.telemetry import Telemetry


def test_secret_hits():
    diff = "\n".join([
        "+++ b/app/.env",
        "+++ b/src/ok.py",
        "+KEY = 'sk-abcdefghijklmnopqrstuvwxyz'",  # pragma: allowlist secret
        "+api_key = \"abcdef1234567890\"",  # pragma: allowlist secret
        "+print('hello')",
        "-token = 'sk-abcdefghijklmnopqrstuvwxyz'",  # pragma: allowlist secret
        "+++ b/certs/server.pem",
        "+-----BEGIN RSA PRIVATE KEY-----",  # pragma: allowlist secret
        "+password = 'short'",
    ])
    assert push.secret_hits(diff) == [
        "file: app/.env",
        "line: KEY = 'sk-abcdefghijklmnopqrstuvwxyz'",  # pragma: allowlist secret
        "line: api_key = \"abcdef1234567890\"",  # pragma: allowlist secret
        "file: certs/server.pem",
        "line: -----BEGIN RSA PRIVATE KEY-----",  # pragma: allowlist secret
    ]
    assert push.secret_hits("+x = 1\n") == []


def test_all_tests(tmp_path):
    (tmp_path / "tests" / "sub").mkdir(parents=True)
    for name in ("test_a.py", "conftest.py", "helper.py", "sub/test_b.py", "x.test.js", "notes.md"):
        (tmp_path / "tests" / name).write_text("", encoding="utf-8")
    assert push.all_tests(tmp_path, {"test_dir": "tests", "test_suffixes": [".py"]}) == [
        "tests/sub/test_b.py", "tests/test_a.py"]
    assert push.all_tests(tmp_path, {"test_dir": "tests", "test_suffixes": [".test.js"]}) == ["tests/x.test.js"]


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repos(tmp_path):
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    work = tmp_path / "work"
    git(tmp_path, "init", "-q", "-b", "main", str(work))
    git(work, "config", "user.email", "t@example.com")
    git(work, "config", "user.name", "T")
    (work / "a.txt").write_text("a\n", encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-qm", "one")
    return origin, work


def passing():
    return True, "ok"


def test_no_remote(repos):
    origin, work = repos
    ok, msgs, info = push.check(work, passing)
    assert (ok, msgs, info["skip"]) == (False, ["no remote 'origin'"], True)
    lines = []
    assert push.push(work, None, passing, log=lines.append) == 0
    assert lines == ["push: no remote, skipped"]


def test_first_push_and_nothing_left(repos, tmp_path):
    origin, work = repos
    git(work, "remote", "add", "origin", str(origin))
    tel = Telemetry(tmp_path / "t.jsonl")
    lines = []
    assert push.push(work, tel, passing, dry_run=True, log=lines.append) == 0
    assert lines == ["push: would push 1 commits to origin/main"]
    assert git(origin, "rev-list", "--all") == ""
    lines.clear()
    assert push.push(work, tel, passing, log=lines.append) == 0
    assert lines == ["push: pushed 1 commits to origin/main"]
    assert git(origin, "rev-parse", "main") == git(work, "rev-parse", "HEAD")
    (event,) = tel.load()
    assert event["kind"] == "push" and event["branch"] == "main" and event["commits"] == 1
    calls = []
    assert push.check(work, lambda: calls.append(1) or (True, ""))[1] == ["nothing to push"] and calls == []


def test_refusals(repos, tmp_path):
    origin, work = repos
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-q", "origin", "main")
    (work / "b.txt").write_text("token = 'abcdefghijklmnop'\n", encoding="utf-8")  # pragma: allowlist secret
    git(work, "add", "-A")
    git(work, "commit", "-qm", "two")
    (work / "a.txt").write_text("changed\n", encoding="utf-8")
    ok, msgs, info = push.check(work, lambda: (False, "1 failed"))
    assert not ok and info == {"branch": "main", "ahead": 1, "skip": False}
    assert msgs == ["uncommitted changes", "secret? line: token = 'abcdefghijklmnop'", "tests failed"]  # pragma: allowlist secret
    lines = []
    assert push.push(work, Telemetry(tmp_path / "t.jsonl"), lambda: (False, ""), log=lines.append) == 1
    assert lines[-1] == "push: refused" and "push: uncommitted changes" in lines
    git(work, "checkout", "-q", "-b", "side")
    assert "on branch side, not main" in push.check(work, passing)[1]


def test_cli(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(push, "all_tests", lambda root, settings: ["tests/test_a.py"])
    monkeypatch.setattr(verify, "run_tests", lambda root, tests: seen.append(("tests", tests)) or (True, ""))

    def fake_push(repo, telemetry, run_tests, dry_run=False, log=print):
        seen.append((repo, type(telemetry).__name__, dry_run, run_tests()))
        return 7
    monkeypatch.setattr(push, "push", fake_push)
    assert cli.main(["push", "--dry-run"]) == 7
    assert seen == [("tests", ["tests/test_a.py"]), (config.REPO, "Telemetry", True, (True, ""))]


def test_allowlisted_lines_are_skipped():
    """(task push_allowlist) An added line that contains "pragma: allowlist secret" is not a hit (the fake keys in
    these tests would otherwise stop every push of Stratos itself)."""
    line = "+KEY = 'sk-abcdefghijklmnopqrstuvwxyz'  # pragma: allowlist secret"
    assert push.secret_hits(line) == []
