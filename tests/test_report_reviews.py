"""Tests for task report_reviews (P17 c, 2026-11-21): the reviewer is Tiel since P16 - it reviews its own code - so the
report counts how often a review blocked a task that a person then accepted (a false block, as in T198, T201, T216,
Lantern T007).

report.review_quality(events) -> {model: {"reviews": n, "blocks": b, "overruled": o}}: every "outcome" with result
"review_approve" or "review_changes" is a review by the model of its call (the "call" event with the same call_id;
"?" when none); a "review_changes" is a block; a block is overruled when, later in the events, its task gets a
"verdict" with result "done_by_human" and no "review_approve" outcome for that task comes between the block and that
verdict (each verdict overrules every such block before it). Models are keys in first-seen order.
report.format_reviews(q) -> lines f"{model}: {reviews} reviews, {blocks} blocks, {overruled} overruled by a person".
`stratos report --reviews` prints them (one per line) and returns 0."""
from stratos import report


def ev(kind, **f):
    return {"kind": kind, **f}


EVENTS = [
    ev("call", call_id="r1", model="tiel"), ev("outcome", call_id="r1", task="T1", result="review_changes"),
    ev("call", call_id="r2", model="tiel"), ev("outcome", call_id="r2", task="T1", result="review_changes"),
    ev("verdict", task="T1", result="done_by_human"),
    ev("call", call_id="r3", model="tiel"), ev("outcome", call_id="r3", task="T2", result="review_changes"),
    ev("call", call_id="r4", model="tiel"), ev("outcome", call_id="r4", task="T2", result="review_approve"),
    ev("verdict", task="T2", result="done_by_human"),
    ev("call", call_id="r5", model="qwen"), ev("outcome", call_id="r5", task="T3", result="review_approve"),
    ev("outcome", call_id="zz", task="T4", result="review_changes"),
    ev("outcome", call_id="r1", task="T1", result="passed"),
]


def test_review_quality():
    assert report.review_quality(EVENTS) == {
        "tiel": {"reviews": 4, "blocks": 3, "overruled": 2},
        "qwen": {"reviews": 1, "blocks": 0, "overruled": 0},
        "?": {"reviews": 1, "blocks": 1, "overruled": 0},
    }
    assert report.format_reviews(report.review_quality(EVENTS))[0] == "tiel: 4 reviews, 3 blocks, 2 overruled by a person"


def test_cli(tmp_path, monkeypatch, capsys):
    from stratos import __main__ as cli
    from stratos import config
    from stratos.telemetry import Telemetry
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    tel = Telemetry(tmp_path / "telemetry.jsonl")
    for e in EVENTS[:5]:
        tel.record(e["kind"], **{k: v for k, v in e.items() if k != "kind"})
    assert cli.main(["report", "--reviews"]) == 0
    assert "tiel: 2 reviews, 2 blocks, 2 overruled by a person" in capsys.readouterr().out
