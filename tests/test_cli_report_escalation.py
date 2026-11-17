"""Tests for task T042: `report` prints the escalation decisions' accuracy after the role decisions: a line
'escalation decisions:' and, for each decider in sorted order,
'  <decider>: <correct>/<judged> right (<decisions> decided; confidence >= 0.7: <confident_correct>/<confident_judged>)'
from report.escalation_accuracy(events). Left out when there are no escalation decisions."""
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
