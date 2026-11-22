"""Tests for task dashboard_try_timeout: TRY_TIMEOUT_S is the try runner's time limit.

In stratos/dashboard.py, TRY_TIMEOUT_S = 10 is a module constant used for BOTH the
subprocess.run timeout kwarg AND the "timed out after N s" message in run_try.
When monkeypatched to 60, the subprocess call's timeout kwarg is 60 and the
timeout message reads "timed out after 60 s". The default is 10 (the original literal).

OUTDATED: tests/test_dashboard_try.py::test_server - the existing test_server does not
monkeypatch TRY_TIMEOUT_S; a Python child can start slower than 10 s on a loaded
machine, making the 3 parallel runs flaky. After this task the test_server must
monkeypatch TRY_TIMEOUT_S to 60 (the task description says test_server sets it to 60).

The subprocess module is faked (monkeypatched) so no real child process is spawned.
No network, no GPU, no real models.
"""

import subprocess

import pytest

from stratos import dashboard


CLI_TOML = (
    '[try]\nkind = "cli"\n'
    'command = ["{py}", "-m", "echoer", "{{file}}"]\n'
    'input_name = "in.md"\n'
)


def make_cli_repo(root, name="Echo", toml=None):
    """A minimal cli try repo: stratos.toml + .stratos dirs. No real package needed."""
    repo = root / name
    (repo / ".stratos").mkdir(parents=True)
    (repo / ".stratos" / "tasks.json").write_text("[]", encoding="utf-8")
    (repo / ".stratos" / "telemetry.jsonl").write_text("", encoding="utf-8")
    if toml is None:
        toml = CLI_TOML.format(py="python")
    (repo / "stratos.toml").write_text(toml, encoding="utf-8")
    return repo


def _fake_ok(cmd, **kw):
    """subprocess.run replacement: return a dummy CompletedProcess, record kwargs."""
    _fake_ok.calls.append(kw)
    return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")


def _fake_timeout(cmd, **kw):
    """subprocess.run replacement: raise TimeoutExpired to hit the timeout branch."""
    raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 0))


@pytest.fixture(autouse=True)
def _reset_calls():
    """Clear the recorded calls before each test that uses _fake_ok."""
    _fake_ok.calls = []


# ─── 1. the constant exists with the original value ──────────────────────────────

def test_try_timeout_s_is_10():
    """TRY_TIMEOUT_S is the module constant equal to 10 (the original literal)."""
    # Step: the constant is defined and equals 10.
    assert dashboard.TRY_TIMEOUT_S == 10


# ─── 2. default timeout kwarg is TRY_TIMEOUT_S (10) ─────────────────────────────

def test_default_timeout_kwarg_is_10(tmp_path, monkeypatch):
    """Without monkeypatch, subprocess.run gets timeout=TRY_TIMEOUT_S which is 10."""
    repo = make_cli_repo(tmp_path)
    monkeypatch.setattr(dashboard.subprocess, "run", _fake_ok)
    dashboard.run_try(repo, "x")
    # Step: the captured timeout kwarg == TRY_TIMEOUT_S == 10.
    assert _fake_ok.calls[0]["timeout"] == 10


# ─── 3. monkeypatched timeout kwarg ─────────────────────────────────────────────

def test_monkeypatch_60_subprocess_timeout(tmp_path, monkeypatch):
    """TRY_TIMEOUT_S=60 → subprocess.run receives timeout=60, not 10."""
    repo = make_cli_repo(tmp_path)
    monkeypatch.setattr(dashboard, "TRY_TIMEOUT_S", 60)
    monkeypatch.setattr(dashboard.subprocess, "run", _fake_ok)
    dashboard.run_try(repo, "x")
    # Step: the timeout kwarg is the monkeypatched 60.
    assert _fake_ok.calls[0]["timeout"] == 60
    # Step: it is NOT the old literal 10.
    assert _fake_ok.calls[0]["timeout"] != 10


# ─── 4. timeout message after monkeypatch ───────────────────────────────────────

def test_monkeypatch_60_timeout_message(tmp_path, monkeypatch):
    """TRY_TIMEOUT_S=60 and TimeoutExpired → stderr "timed out after 60 s"."""
    repo = make_cli_repo(tmp_path)
    monkeypatch.setattr(dashboard, "TRY_TIMEOUT_S", 60)
    monkeypatch.setattr(dashboard.subprocess, "run", _fake_timeout)
    result = dashboard.run_try(repo, "x")
    # Step: code is the -1 timeout sentinel.
    assert result["code"] == -1
    # Step: stdout is empty (the child produced nothing before timeout).
    assert result["stdout"] == ""
    # Step: stderr uses the monkeypatched value.
    assert result["stderr"] == "timed out after 60 s"


# ─── 5. default timeout message ─────────────────────────────────────────────────

def test_default_timeout_message_is_10(tmp_path, monkeypatch):
    """Default TRY_TIMEOUT_S=10 → TimeoutExpired → "timed out after 10 s"."""
    repo = make_cli_repo(tmp_path)
    # Step: no monkeypatch on TRY_TIMEOUT_S; it stays 10.
    monkeypatch.setattr(dashboard.subprocess, "run", _fake_timeout)
    result = dashboard.run_try(repo, "x")
    # Step: message contains the default 10.
    assert result["stderr"] == "timed out after 10 s"


# ─── 6. a third value (7) changes both the kwarg and the message ────────────────

def test_monkeypatch_7_changes_both(tmp_path, monkeypatch):
    """TRY_TIMEOUT_S=7 → subprocess timeout kwarg is 7 AND message says 7."""
    repo = make_cli_repo(tmp_path)
    monkeypatch.setattr(dashboard, "TRY_TIMEOUT_S", 7)
    # Step: first run succeeds (normal path), capture the timeout kwarg.
    monkeypatch.setattr(dashboard.subprocess, "run", _fake_ok)
    dashboard.run_try(repo, "x")
    # Step: the timeout kwarg is 7.
    assert _fake_ok.calls[0]["timeout"] == 7
    # Step: second run times out; check the message.
    monkeypatch.setattr(dashboard.subprocess, "run", _fake_timeout)
    result = dashboard.run_try(repo, "x")
    # Step: message uses 7.
    assert result["stderr"] == "timed out after 7 s"


# ─── 7. the message never contains the literal "10" after monkeypatch ───────────

def test_message_excludes_10_after_monkeypatch(tmp_path, monkeypatch):
    """After TRY_TIMEOUT_S=60 the message does NOT say "timed out after 10 s"."""
    repo = make_cli_repo(tmp_path)
    monkeypatch.setattr(dashboard, "TRY_TIMEOUT_S", 60)
    monkeypatch.setattr(dashboard.subprocess, "run", _fake_timeout)
    result = dashboard.run_try(repo, "x")
    # Step: the old literal string is absent.
    assert "timed out after 10 s" not in result["stderr"]
    # Step: the new value 60 is present.
    assert "60" in result["stderr"]


# ─── 8. shell=False is preserved (not part of TRY_TIMEOUT_S, sanity) ─────────────

def test_shell_false_preserved(tmp_path, monkeypatch):
    """run_try passes shell=False to subprocess.run; TRY_TIMEOUT_S change must not alter it."""
    repo = make_cli_repo(tmp_path)
    monkeypatch.setattr(dashboard, "TRY_TIMEOUT_S", 60)
    monkeypatch.setattr(dashboard.subprocess, "run", _fake_ok)
    dashboard.run_try(repo, "x")
    # Step: shell=False is still in the kwargs.
    assert _fake_ok.calls[0]["shell"] is False


# ─── 9. the constant is read at call time, not import time ──────────────────────

def test_constant_read_per_call(tmp_path, monkeypatch):
    """Each run_try call reads the current TRY_TIMEOUT_S (not a baked-in import-time copy)."""
    repo = make_cli_repo(tmp_path)
    # Step: first call with 10.
    monkeypatch.setattr(dashboard.subprocess, "run", _fake_ok)
    dashboard.run_try(repo, "x")
    # Step: first timeout kwarg is 10 (default).
    assert _fake_ok.calls[0]["timeout"] == 10
    # Step: monkeypatch to 60, then call again.
    monkeypatch.setattr(dashboard, "TRY_TIMEOUT_S", 60)
    dashboard.run_try(repo, "x")
    # Step: second timeout kwarg is 60 (read at call time).
    assert _fake_ok.calls[1]["timeout"] == 60


# ─── 10. non-cli project raises ValueError, timeout irrelevant ──────────────────

def test_non_cli_raises_before_timeout(tmp_path, monkeypatch):
    """A static project raises ValueError before subprocess.run, so TRY_TIMEOUT_S is never used."""
    repo = make_cli_repo(tmp_path, name="Static",
                         toml='[try]\nkind = "static"\nindex = "index.html"\n')
    monkeypatch.setattr(dashboard, "TRY_TIMEOUT_S", 60)
    monkeypatch.setattr(dashboard.subprocess, "run", _fake_ok)
    # Step: run_try raises ValueError for a non-cli project.
    with pytest.raises(ValueError, match="not a cli project"):
        dashboard.run_try(repo, "x")
    # Step: subprocess.run was never called, so no timeout kwarg recorded.
    assert len(_fake_ok.calls) == 0
