"""Tests for task T052: `python -m stratos report --replay` prints report.replay_summary (T051) of
config.STATE_DIR / "replay.jsonl" instead of the usual report.

With no replay runs it prints "no replay runs yet". Otherwise, for each model key in sorted order:
"<key>: <passed>/<runs> passed, <attempts> attempts, <seconds rounded> s", then for each task in sorted order
"  <task>: <passed>/<runs> passed, <attempts / runs, one decimal> attempts and <seconds / runs rounded> s per run".
It returns 0. Without --replay, report is unchanged."""
from stratos import __main__ as cli
from stratos import config
from stratos.telemetry import Telemetry


def test_no_runs(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    assert cli.main(["report", "--replay"]) == 0
    assert "no replay runs yet" in capsys.readouterr().out


def test_prints_the_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    t = Telemetry(tmp_path / "replay.jsonl")
    for cid, task, attempt, secs, result in [("a", "T2", 1, 30.0, "passed"), ("b", "T1", 1, 10.0, "failed"),
                                             ("c", "T1", 2, 11.0, "passed"), ("d", "T1", 1, 12.0, "failed")]:
        t.record("call", call_id=cid, task=task, attempt=attempt, model="m", effort="low", seconds=secs)
        t.record("outcome", call_id=cid, task=task, result=result)
    Telemetry(tmp_path / "telemetry.jsonl").record("call", call_id="z", task="T9", attempt=1, model="other",
                                                   effort="none", seconds=1.0)
    assert cli.main(["report", "--replay"]) == 0
    out = capsys.readouterr().out
    assert "m effort=low: 2/3 passed, 4 attempts, 63 s" in out
    assert "  T1: 1/2 passed, 1.5 attempts and 16 s per run" in out
    assert "  T2: 1/1 passed, 1.0 attempts and 30 s per run" in out
    assert out.index("  T1:") < out.index("  T2:") and "other" not in out
