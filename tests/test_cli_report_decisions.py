"""Tests for task T036: `report` ends with the role decisions' accuracy from report.decision_accuracy(events):
a line 'role decisions:' and then, for each decider in sorted order, a line
'  <decider>: <correct>/<judged> right (<decisions> decided; confidence >= 0.3: <confident_correct>/<confident_judged>)'.
With no role decisions in the telemetry the section is left out."""
import json

import pytest

from stratos import __main__ as cli
from stratos import config


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
