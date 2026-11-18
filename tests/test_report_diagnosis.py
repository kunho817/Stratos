"""Tests for task T059: report.diagnosis_ab(events) and its line in `python -m stratos report`.

diagnosis_ab(events) -> {"hinted": {"retries": n, "passed": k}, "plain": {"retries": n, "passed": k}}
    For each "diagnosis" event (task, attempt, used; T058), in order: the first later "call" event with the same task
    and attempt is that retry; its "outcome" event (same call_id) decides passed (result "passed") or not. used True
    counts in "hinted", False in "plain". A diagnosis whose call or outcome is missing is not counted. Both keys are
    always present (0/0 when empty).
report: when there is at least one counted retry it prints
    "diagnosis A/B: with diagnosis <k>/<n> retries passed, without <k>/<n>"
    and nothing about it otherwise."""
from stratos import __main__ as cli
from stratos import config, report
from stratos.telemetry import Telemetry


def diag(task, attempt, used):
    return {"kind": "diagnosis", "task": task, "attempt": attempt, "used": used, "chars": 10 if used else 0}


def call(cid, task, attempt):
    return {"kind": "call", "call_id": cid, "task": task, "attempt": attempt, "role": "coder", "model": "tiel"}


def outcome(cid, result):
    return {"kind": "outcome", "call_id": cid, "task": "x", "result": result}


def test_counts_both_halves():
    events = [call("a", "T1", 1), outcome("a", "failed"), diag("T1", 2, True), call("b", "T1", 2), outcome("b", "passed"),
              call("c", "T2", 1), outcome("c", "failed"), diag("T2", 2, False), call("d", "T2", 2), outcome("d", "failed"),
              diag("T2", 3, True), call("e", "T2", 3), outcome("e", "failed"),
              diag("T3", 2, False), call("f", "T3", 2), outcome("f", "passed")]
    assert report.diagnosis_ab(events) == {"hinted": {"retries": 2, "passed": 1}, "plain": {"retries": 2, "passed": 1}}


def test_matches_the_call_after_the_diagnosis():
    events = [call("old", "T1", 2), outcome("old", "passed"),          # an earlier run of the task: not this retry
              diag("T1", 2, True), call("x", "T9", 2), outcome("x", "passed"), call("new", "T1", 2), outcome("new", "failed")]
    assert report.diagnosis_ab(events)["hinted"] == {"retries": 1, "passed": 0}


def test_missing_call_or_outcome_is_skipped():
    events = [diag("T1", 2, True), diag("T2", 2, False), call("b", "T2", 2)]
    empty = {"hinted": {"retries": 0, "passed": 0}, "plain": {"retries": 0, "passed": 0}}
    assert report.diagnosis_ab(events) == empty
    assert report.diagnosis_ab([]) == empty


def record_all(t, events):
    for e in events:
        e = dict(e)
        kind = e.pop("kind")
        t.record(kind, **e)


def test_report_prints_the_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    record_all(Telemetry(tmp_path / "telemetry.jsonl"),
               [diag("T1", 2, True), call("b", "T1", 2), outcome("b", "passed"),
                diag("T2", 2, False), call("d", "T2", 2), outcome("d", "failed")])
    assert cli.main(["report"]) == 0
    assert "diagnosis A/B: with diagnosis 1/1 retries passed, without 0/1" in capsys.readouterr().out


def test_report_is_silent_without_diagnoses(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    t = Telemetry(tmp_path / "telemetry.jsonl")
    t.record("call", call_id="a", task="T1", attempt=1, role="coder", model="tiel", seconds=1.0)
    t.record("outcome", call_id="a", task="T1", result="passed")
    assert cli.main(["report"]) == 0
    assert "diagnosis" not in capsys.readouterr().out
