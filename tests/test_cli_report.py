"""Tests for task T002: `python -m stratos report` prints the telemetry summary (stratos.report.summarize)."""
import json

import pytest

from stratos import __main__ as cli, config
from stratos.telemetry import Telemetry


EVENTS = [
    {"kind": "switch", "model": "tiel", "from_model": "gemma", "seconds": 8.0},
    {"kind": "call", "call_id": "a", "task": "T001", "model": "tiel", "prompt_tokens": 1000, "completion_tokens": 200,
     "seconds": 4.0},
    {"kind": "outcome", "call_id": "a", "task": "T001", "result": "failed"},
    {"kind": "call", "call_id": "b", "task": "T001", "model": "tiel", "prompt_tokens": 1200, "completion_tokens": 300,
     "seconds": 5.0},
    {"kind": "outcome", "call_id": "b", "task": "T001", "result": "passed"},
    {"kind": "switch", "model": "flint", "from_model": "tiel", "seconds": 30.5},
    {"kind": "call", "call_id": "c", "task": "T002", "model": "flint", "prompt_tokens": 800, "completion_tokens": None,
     "seconds": 20.0},
    {"kind": "outcome", "call_id": "c", "task": "T002", "result": "no_files"},
]


def run_report(tmp_path, monkeypatch, capsys, events):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    if events is not None:
        (tmp_path / "telemetry.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    code = cli.main(["report"])
    return code, [line.strip() for line in capsys.readouterr().out.splitlines()]


def test_report_lines(tmp_path, monkeypatch, capsys):
    code, lines = run_report(tmp_path, monkeypatch, capsys, EVENTS)
    assert code == 0
    for expected in [
        "calls: 3  prompt tokens: 3000  completion tokens: 500",
        "switches: 2  switch time: 38.5 s",
        "outcomes: failed=1 no_files=1 passed=1",
        "wasted tokens: 2000",
        "by model:",
        "flint: calls=1 prompt=800 completion=0 time=20.0 s",
        "tiel: calls=2 prompt=2200 completion=500 time=9.0 s",
    ]:
        assert expected in lines, f"missing line: {expected!r}\ngot: {lines}"


def test_models_are_listed_alphabetically(tmp_path, monkeypatch, capsys):
    _, lines = run_report(tmp_path, monkeypatch, capsys, EVENTS)
    assert lines.index("flint: calls=1 prompt=800 completion=0 time=20.0 s") < \
        lines.index("tiel: calls=2 prompt=2200 completion=500 time=9.0 s")


def test_no_telemetry_yet(tmp_path, monkeypatch, capsys):
    code, lines = run_report(tmp_path, monkeypatch, capsys, None)
    assert code == 0
    assert lines == ["no telemetry yet"]


# ---- was test_cli_report_decisions.py ----
# Tests for task T036: `report` ends with the role decisions' accuracy from report.decision_accuracy(events):
# a line 'role decisions:' and then, for each decider in sorted order, a line
# '  <decider>: <correct>/<judged> right (<decisions> decided; confidence >= 0.3: <confident_correct>/<confident_judged>)'.
# With no role decisions in the telemetry the section is left out.


@pytest.fixture
def telemetry(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)

    def write(events):
        (tmp_path / "telemetry.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return write


BASE = [{"kind": "call", "call_id": "a", "task": "T1", "role": "coder", "model": "m", "prompt_tokens": 1,
         "completion_tokens": 1, "seconds": 1.0},
        {"kind": "outcome", "call_id": "a", "task": "T1", "result": "passed"}]


def test_report_shows_decision_accuracy(telemetry, capsys):
    telemetry(BASE + [
        {"kind": "decision", "decision": "role", "decider": "rules", "task": "T1", "choice": "coder_hard",
         "confidence": 0.55, "reason": "r"},
        {"kind": "decision", "decision": "role", "decider": "jev", "task": "T1", "choice": "coder",
         "confidence": 0.9, "reason": "r"}])
    assert cli.main(["report"]) == 0
    out = capsys.readouterr().out.splitlines()
    i = out.index("role decisions:")
    assert out[i + 1] == "  jev: 1/1 right (1 decided; confidence >= 0.3: 1/1)"
    assert out[i + 2] == "  rules: 0/1 right (1 decided; confidence >= 0.3: 0/1)"
    assert "calls: 1" in out[0]


def test_no_section_without_decisions(telemetry, capsys):
    telemetry(BASE)
    cli.main(["report"])
    assert "role decisions:" not in capsys.readouterr().out


# ---- was test_cli_report_escalation.py ----
# Tests for task T042: `report` prints the escalation decisions' accuracy after the role decisions: a line
# 'escalation decisions:' and, for each decider in sorted order,
# '  <decider>: <correct>/<judged> right (<decisions> decided; confidence >= 0.7: <confident_correct>/<confident_judged>)'
# from report.escalation_accuracy(events). Left out when there are no escalation decisions.


def ev_call(cid, role):
    return {"kind": "call", "call_id": cid, "task": "T1", "role": role, "model": "m", "prompt_tokens": 1,
            "completion_tokens": 1, "seconds": 1.0}


def ev_esc(decider, choice, confidence):
    return {"kind": "decision", "decision": "escalate", "decider": decider, "task": "T1", "role": "coder",
            "attempt": 1, "choice": choice, "confidence": confidence, "reason": "r"}


def test_report_shows_escalation_accuracy(telemetry, capsys):
    telemetry([ev_call("a", "coder"), {"kind": "outcome", "call_id": "a", "task": "T1", "result": "failed"},
               ev_esc("rules", False, 0.6), ev_esc("jev", True, 0.81),
               ev_call("b", "coder_hard"), {"kind": "outcome", "call_id": "b", "task": "T1", "result": "passed"}])
    assert cli.main(["report"]) == 0
    out = capsys.readouterr().out.splitlines()
    i = out.index("escalation decisions:")
    assert out[i + 1] == "  jev: 1/1 right (1 decided; confidence >= 0.7: 1/1)"
    assert out[i + 2] == "  rules: 0/1 right (1 decided; confidence >= 0.7: 0/0)"


def test_no_section_without_escalation_decisions(telemetry, capsys):
    telemetry([ev_call("a", "coder"), {"kind": "outcome", "call_id": "a", "task": "T1", "result": "passed"}])
    cli.main(["report"])
    assert "escalation decisions:" not in capsys.readouterr().out


# ---- was test_cli_report_replay.py ----
# Tests for task T052: `python -m stratos report --replay` prints report.replay_summary (T051) of
# config.STATE_DIR / "replay.jsonl" instead of the usual report.
#
# With no replay runs it prints "no replay runs yet". Otherwise, for each model key in sorted order:
# "<key>: <passed>/<runs> passed, <attempts> attempts, <seconds rounded> s", then for each task in sorted order
# "  <task>: <passed>/<runs> passed, <attempts / runs, one decimal> attempts and <seconds / runs rounded> s per run".
# It returns 0. Without --replay, report is unchanged.


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
