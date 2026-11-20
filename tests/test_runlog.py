"""Tests for task runlog (P12, 2026-11-20, user: "show the terminal log" on the dashboard): the long commands copy what
they print into .stratos/run.log, which the dashboard shows.

stratos/runlog.py: tee(path, argv) is a context manager: it appends a header line
f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} stratos {' '.join(argv)}\\n" to path (folders made), and while it is
open every write to sys.stdout and sys.stderr also goes to path (UTF-8, flushed at once); on exit the streams are
put back. LOGGED = {"run", "run-all", "plan", "plan-tests", "plan-add", "plan-critique", "review", "memory",
"push"}: __main__.main wraps those commands in runlog.tee(config.STATE_DIR / "run.log", argv); other commands
(status, report, dashboard, ...) are not logged. The file is cut to its last 2000 lines when it grows past 4000
(checked when tee opens)."""
import sys

from stratos import __main__ as cli
from stratos import config, runlog


def test_tee_copies_stdout_and_stderr(tmp_path, capsys):
    log = tmp_path / "s" / "run.log"
    with runlog.tee(log, ["run-all"]):
        print("plan: T1")
        print("oops", file=sys.stderr)
    print("after")
    text = log.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0].startswith("=== ") and lines[0].endswith(" stratos run-all")
    assert lines[1:] == ["plan: T1", "oops"]
    out = capsys.readouterr()
    assert "plan: T1" in out.out and "after" in out.out and "oops" in out.err


def test_long_log_is_cut(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("".join(f"line {i}\n" for i in range(4100)), encoding="utf-8")
    with runlog.tee(log, ["run"]):
        pass
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2001 and lines[0] == "line 2100" and lines[-1].startswith("=== ")


def test_main_logs_only_long_commands(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "MEMORY", False)
    from stratos import gateway

    def down(self):
        raise OSError("no server")
    monkeypatch.setattr(gateway.Gateway, "health", down)
    assert cli.main(["run-all"]) == 0
    assert cli.main(["status"]) == 0
    text = (tmp_path / "state" / "run.log").read_text(encoding="utf-8")
    assert "stratos run-all" in text and "nothing to run" in text
    assert "stratos status" not in text
    assert runlog.LOGGED >= {"run", "run-all", "plan", "plan-tests", "plan-add"}
