"""Tests for task T002: `python -m stratos report` prints the telemetry summary (stratos.report.summarize)."""
import json

from stratos import __main__ as cli
from stratos import config

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
