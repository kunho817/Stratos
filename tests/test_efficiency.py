"""Tests for task efficiency: where the tokens and the time go (user, 2026-11-19: bring back the token-waste and time
checks). The old summarize() "wasted tokens" counts every outcome that is not "passed", reviewer approvals included,
and prompt tokens too; report.efficiency() splits it by cause and counts generated (completion) tokens.

report.efficiency(events) -> dict. A call is a "call" event; its outcome is the first "outcome" event with its
call_id. Each call gets one cause:
- outcome "passed" -> "useful", but "discarded" when a later "verdict" event with result "reset_by_human" names its
  task (as summarize does);
- "review_approve" or "review_changes" -> "review";
- "failed" -> "tests_failed"; "no_files" -> "cut_off" when the call's finish is "length", else "no_files";
  "dropped_defs" -> "dropped_defs"; any other outcome -> "other_failure";
- no outcome -> "support" (planner, test writer, triage, diagnosis, learner, wiki ...).
Keys:
- "by_cause": {cause: {"calls", "completion_tokens", "seconds"}} for the causes that occur.
- "waste": {"completion_tokens", "seconds"} summed over WASTE_CAUSES = ("tests_failed", "cut_off", "no_files",
  "dropped_defs", "other_failure", "discarded"), and "share" = waste completion tokens / all completion tokens
  (rounded to 3 decimals; 0.0 when there are none).
- "time": "model_seconds" (all calls), "switch_seconds" ("switch" events), "active_seconds" (events sorted by ts are cut
  into sessions where two neighbours are more than 600 s apart; the sum of last ts - first ts of each session), and
  "other_seconds" = max(0, active - model - switch) (tests, git, the harness). All rounded to 1 decimal.
- "first_try": over the tasks that have an outcome of a call whose role is "coder" or "coder_hard": "tasks" (how
  many), "passed" (how many have "passed" as the outcome of their first such call), "by_role": {role of that first
  call: [passed, tasks]}.
- "attempts": the mean number of coder/coder_hard outcomes of the tasks whose last such outcome is "passed" (rounded to 2;
  0.0 when none).
- "cut_off": {"calls": calls with finish "length", "completion_tokens": theirs}.
- "top_tasks": the 5 tasks with the most completion tokens over all their calls, most first:
  [{"task", "completion_tokens", "seconds", "calls"}] (seconds rounded to 1).
Missing numbers count as 0.

`stratos report --efficiency` prints report.format_efficiency(efficiency(events)) (a list of lines; its first line is
"efficiency:") for the project's telemetry."""
from stratos import __main__ as cli
from stratos import config, report
from stratos.telemetry import Telemetry


def call(cid, task, role, tokens, secs, ts, finish="stop", model="m"):
    return {"kind": "call", "call_id": cid, "task": task, "role": role, "model": model, "completion_tokens": tokens,
            "prompt_tokens": 999, "seconds": secs, "finish": finish, "ts": ts}


def out(cid, task, result, ts):
    return {"kind": "outcome", "call_id": cid, "task": task, "result": result, "ts": ts}


EVENTS = [
    {"kind": "switch", "seconds": 20, "ts": 1000},
    call("a1", "T1", "coder", 100, 10, 1010), out("a1", "T1", "failed", 1011),
    call("a2", "T1", "coder", 200, 20, 1030, finish="length"), out("a2", "T1", "no_files", 1031),
    call("a3", "T1", "coder_hard", 300, 30, 1100), out("a3", "T1", "passed", 1101),
    call("r1", "T1", "reviewer", 50, 5, 1110), out("r1", "T1", "review_approve", 1111),
    call("b1", "T2", "coder_hard", 400, 40, 1200), out("b1", "T2", "passed", 1201),
    {"kind": "verdict", "task": "T2", "result": "reset_by_human", "reason": "x", "ts": 1210},
    call("b2", "T2", "coder", 500, 50, 1300), out("b2", "T2", "dropped_defs", 1301),
    call("p1", None, "planner", 600, 60, 3000),     # a new session (gap > 600 s)
    call("c1", "T3", "coder", 70, 7, 3100), out("c1", "T3", "passed", 3101),
]


def test_by_cause_and_waste():
    e = report.efficiency(EVENTS)
    assert e["by_cause"] == {
        "tests_failed": {"calls": 1, "completion_tokens": 100, "seconds": 10},
        "cut_off": {"calls": 1, "completion_tokens": 200, "seconds": 20},
        "useful": {"calls": 2, "completion_tokens": 370, "seconds": 37},
        "review": {"calls": 1, "completion_tokens": 50, "seconds": 5},
        "discarded": {"calls": 1, "completion_tokens": 400, "seconds": 40},
        "dropped_defs": {"calls": 1, "completion_tokens": 500, "seconds": 50},
        "support": {"calls": 1, "completion_tokens": 600, "seconds": 60},
    }
    # waste = 100 + 200 + 400 + 500 = 1200 of 2220 generated
    assert e["waste"] == {"completion_tokens": 1200, "seconds": 120, "share": round(1200 / 2220, 3)}
    assert e["cut_off"] == {"calls": 1, "completion_tokens": 200}


def test_time():
    t = report.efficiency(EVENTS)["time"]
    # sessions: 1000..1301 (301 s) and 3000..3101 (101 s)
    assert t == {"model_seconds": 222.0, "switch_seconds": 20.0, "active_seconds": 402.0,
                 "idle_seconds": 0.0, "other_seconds": 160.0,
                 "steps": {}}   # T244: no "step" events here (tests/test_steps.py)


def test_first_try_attempts_and_top():
    e = report.efficiency(EVENTS)
    # first coder outcomes: T1 a1 failed (coder), T2 b1 passed (coder_hard), T3 c1 passed (coder)
    assert e["first_try"] == {"tasks": 3, "passed": 2, "by_role": {"coder": [1, 2], "coder_hard": [1, 1]}}
    # tasks that ended with one "passed": T1 (3 coder outcomes), T3 (1); T2 ended with dropped_defs
    assert e["attempts"] == 2.0
    assert e["top_tasks"][0] == {"task": "T2", "completion_tokens": 900, "seconds": 90.0, "calls": 2}
    assert [t["task"] for t in e["top_tasks"]] == ["T2", "T1", None, "T3"]


def test_empty():
    e = report.efficiency([])
    assert e["waste"] == {"completion_tokens": 0, "seconds": 0, "share": 0.0}
    assert e["attempts"] == 0.0 and e["top_tasks"] == [] and e["by_cause"] == {}


def test_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    tel = Telemetry(tmp_path / "telemetry.jsonl")
    for e in EVENTS:
        fields = {k: v for k, v in e.items() if k not in ("kind", "ts")}
        tel.record(e["kind"], **fields)
    assert cli.main(["report", "--efficiency"]) == 0
    printed = capsys.readouterr().out.splitlines()
    assert printed == report.format_efficiency(report.efficiency(tel.load()))
    assert printed[0] == "efficiency:"


def test_a_pass_after_the_reset_is_useful():
    """(task efficiency_discard_order) Only a pass that comes before a person's reset of its task is "discarded"; the
    pass after the reset is the task's real result ("useful")."""
    events = [call("x1", "T9", "coder", 100, 10, 1), out("x1", "T9", "passed", 2),
              {"kind": "verdict", "task": "T9", "result": "reset_by_human", "reason": "r", "ts": 3},
              call("x2", "T9", "coder", 200, 20, 4), out("x2", "T9", "passed", 5)]
    by = report.efficiency(events)["by_cause"]
    assert by["discarded"]["completion_tokens"] == 100 and by["useful"]["completion_tokens"] == 200


def test_idle_seconds_with_command_gaps():
    """Command events with gaps produce idle_seconds > 0."""
    events = [
        {"kind": "command", "name": "run", "phase": "start", "ts": 10},
        {"kind": "command", "name": "run", "phase": "end", "ts": 20},
        {"kind": "command", "name": "run", "phase": "start", "ts": 30},
        {"kind": "command", "name": "run", "phase": "end", "ts": 40},
    ]
    t = report.efficiency(events)["time"]
    # session [10,40] = 30; intervals [10,20] and [30,40] cover 20; idle = 10
    assert t["idle_seconds"] > 0
    assert t["idle_seconds"] == 10.0
