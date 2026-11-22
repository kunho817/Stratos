"""Tests for task idle_seconds: efficiency adds idle_seconds from command events.

In stratos/report.py efficiency(), scan "command" events to build start..end intervals per command.
Compute idle_seconds as the active session time (same sessions as active_seconds) that lies outside
every interval, rounded to 1 decimal; 0.0 when there are no command events.
Add "idle_seconds" to the time dict. Subtract idle_seconds from other_seconds:
max(0, active - model - switches - steps - idle).
format_efficiency's time line shows ", idle <s> s" right before ", other ..." when idle_seconds > 0;
otherwise the line is as today (no ", idle").

OUTDATED: tests/test_efficiency.py::test_time - the expected time dict must gain
  "idle_seconds": 0.0; its EVENTS have no command events, so idle is 0.0, but the
  dict equality now fails because "idle_seconds" is a new key.
"""
from stratos import report


def call(cid, task, role, tokens, secs, ts, finish="stop", model="m"):
    return {"kind": "call", "call_id": cid, "task": task, "role": role, "model": model,
            "completion_tokens": tokens, "prompt_tokens": 999, "seconds": secs,
            "finish": finish, "ts": ts}


def cmd(name, phase, ts):
    return {"kind": "command", "name": name, "phase": phase, "ts": ts}


# Re-use the EVENTS from test_efficiency.py (no command events).
EVENTS_NO_CMD = [
    {"kind": "switch", "seconds": 20, "ts": 1000},
    call("a1", "T1", "coder", 100, 10, 1010),
    {"kind": "outcome", "call_id": "a1", "task": "T1", "result": "failed", "ts": 1011},
    call("a2", "T1", "coder", 200, 20, 1030, finish="length"),
    {"kind": "outcome", "call_id": "a2", "task": "T1", "result": "no_files", "ts": 1031},
    call("a3", "T1", "coder_hard", 300, 30, 1100),
    {"kind": "outcome", "call_id": "a3", "task": "T1", "result": "passed", "ts": 1101},
    call("r1", "T1", "reviewer", 50, 5, 1110),
    {"kind": "outcome", "call_id": "r1", "task": "T1", "result": "review_approve", "ts": 1111},
    call("b1", "T2", "coder_hard", 400, 40, 1200),
    {"kind": "outcome", "call_id": "b1", "task": "T2", "result": "passed", "ts": 1201},
    {"kind": "verdict", "task": "T2", "result": "reset_by_human", "reason": "x", "ts": 1210},
    call("b2", "T2", "coder", 500, 50, 1300),
    {"kind": "outcome", "call_id": "b2", "task": "T2", "result": "dropped_defs", "ts": 1301},
    call("p1", None, "planner", 600, 60, 3000),
    call("c1", "T3", "coder", 70, 7, 3100),
    {"kind": "outcome", "call_id": "c1", "task": "T3", "result": "passed", "ts": 3101},
]


def test_idle_zero_when_no_command_events():
    """No "command" events → idle_seconds is 0.0."""
    t = report.efficiency(EVENTS_NO_CMD)["time"]
    # active_seconds: sessions 1000..1301 (301 s) + 3000..3101 (101 s) = 402.0
    # model_seconds = 10+20+30+5+40+50+60+7 = 222.0
    # switch_seconds = 20.0
    # steps = {} → step_sum = 0
    # No command events → idle = 0.0
    # other = max(0, 402.0 - 222.0 - 20.0 - 0 - 0) = 160.0
    assert t["idle_seconds"] == 0.0
    assert t["active_seconds"] == 402.0
    assert t["other_seconds"] == 160.0


def test_idle_seconds_with_gaps():
    """One session 10→40; commands cover [10,20] and [30,40]; gap [20,30] is idle."""
    events = [
        cmd("run", "start", 10),
        call("c1", "T1", "coder", 100, 10, 15),
        cmd("run", "end", 20),
        cmd("run", "start", 30),
        cmd("run", "end", 40),
    ]
    t = report.efficiency(events)["time"]
    # ts values: 10, 15, 20, 30, 40 → one session (all gaps ≤ 600): [10, 40] = 30.0
    # model_seconds = 10 (one call); switch_seconds = 0; steps = {}
    # command intervals: run [10,20] and run [30,40] → merged coverage = 10+10 = 20
    # idle = 30 - 20 = 10.0
    # other = max(0, 30 - 10 - 0 - 0 - 10) = 10.0
    assert t["active_seconds"] == 30.0
    assert t["idle_seconds"] == 10.0
    assert t["other_seconds"] == 10.0


def test_idle_overlapping_intervals():
    """Two commands overlap → merged interval covers the whole session; idle = 0."""
    events = [
        cmd("run", "start", 5),
        cmd("plan", "start", 10),
        cmd("run", "end", 15),
        cmd("plan", "end", 20),
    ]
    t = report.efficiency(events)["time"]
    # ts values: 5, 10, 15, 20 → one session [5, 20] = 15.0
    # model_seconds = 0, switch_seconds = 0, steps = {}
    # intervals: run [5,15], plan [10,20] → merged [5,20] = 15
    # idle = 15 - 15 = 0.0
    # other = max(0, 15 - 0 - 0 - 0 - 0) = 15.0
    assert t["idle_seconds"] == 0.0
    assert t["other_seconds"] == 15.0


def test_idle_across_multiple_sessions():
    """Two sessions (gap > 600); commands cover session 1 fully, session 2 partially."""
    events = [
        cmd("run", "start", 10),
        cmd("run", "end", 20),
        cmd("run", "start", 700),
        cmd("run", "end", 710),
        call("c1", "T1", "coder", 50, 5, 720),
    ]
    t = report.efficiency(events)["time"]
    # ts values: 10, 20, 700, 710, 720
    # Gap 20→700 = 680 > 600 → session1 [10,20]=10, session2 [700,720]=20
    # active_seconds = 10 + 20 = 30.0
    # model_seconds = 5; switch_seconds = 0; steps = {}
    # Intervals: [10,20] covers session1 → idle in session1 = 0
    #            [700,710] covers 10 of session2 (20-10=10 idle in session2)
    # total idle = 0 + 10 = 10.0
    # other = max(0, 30 - 5 - 0 - 0 - 10) = 15.0
    assert t["active_seconds"] == 30.0
    assert t["idle_seconds"] == 10.0
    assert t["other_seconds"] == 15.0


def test_idle_all_covered_by_commands():
    """One command covers the entire session → idle = 0."""
    events = [
        cmd("run", "start", 10),
        cmd("run", "end", 40),
    ]
    t = report.efficiency(events)["time"]
    # ts: 10, 40 → session [10,40] = 30.0
    # interval [10,40] = 30 → idle = 0
    assert t["active_seconds"] == 30.0
    assert t["idle_seconds"] == 0.0


def test_other_seconds_includes_idle():
    """other_seconds = max(0, active - model - switch - steps - idle)."""
    events = [
        cmd("run", "start", 10),
        cmd("run", "end", 20),
        cmd("run", "start", 30),
        cmd("run", "end", 40),
    ]
    t = report.efficiency(events)["time"]
    # active = 30.0, model = 0, switch = 0, steps = {} (step_sum=0), idle = 10.0
    # other = max(0, 30 - 0 - 0 - 0 - 10) = 20.0
    assert t["idle_seconds"] == 10.0
    assert t["other_seconds"] == 20.0
    # verify the arithmetic: 30.0 - 0.0 - 0.0 - 0.0 - 10.0 = 20.0
    assert t["other_seconds"] == round(max(0, t["active_seconds"] - t["model_seconds"]
                                         - t["switch_seconds"] - 0.0 - t["idle_seconds"]), 1)


def test_format_shows_idle_when_positive():
    """When idle_seconds > 0 (no steps), the time line has ", idle X s" before ", other"."""
    events = [
        cmd("run", "start", 10),
        call("c1", "T1", "coder", 100, 10, 15),
        cmd("run", "end", 20),
        cmd("run", "start", 30),
        cmd("run", "end", 40),
    ]
    e = report.efficiency(events)
    t = e["time"]
    # model=10, switch=0, active=30, idle=10, other=10
    # active = 30 - 10 = 20 covered; idle = 10; other = 30-10-0-0-10 = 10
    lines = report.format_efficiency(e)
    time_line = next(ln for ln in lines if "time:" in ln)
    # expected: "  time: model 10 s, switches 0 s, idle 10 s, other 10 s of 30 s active"
    expected = (f"  time: model {t['model_seconds']:.0f} s, switches {t['switch_seconds']:.0f} s, "
                f"idle {t['idle_seconds']:.0f} s, other {t['other_seconds']:.0f} s of "
                f"{t['active_seconds']:.0f} s active")
    assert time_line == expected
    assert ", idle 10 s" in time_line
    assert ", idle 10 s, other 10 s" in time_line


def test_format_no_idle_when_zero():
    """When idle_seconds == 0, the time line has no ", idle" (same as before)."""
    e = report.efficiency(EVENTS_NO_CMD)
    t = e["time"]
    # active=402, model=222, switch=20, steps={}, idle=0, other=160
    lines = report.format_efficiency(e)
    time_line = next(ln for ln in lines if "time:" in ln)
    # expected: "  time: model 222 s, switches 20 s, other 160 s of 402 s active"
    expected = (f"  time: model {t['model_seconds']:.0f} s, switches {t['switch_seconds']:.0f} s, "
                f"other {t['other_seconds']:.0f} s of {t['active_seconds']:.0f} s active")
    assert time_line == expected
    assert ", idle" not in time_line


def test_format_idle_with_steps():
    """When steps and idle are both present, format has steps then idle before other."""
    events = [
        cmd("run", "start", 10),
        {"kind": "step", "name": "tests", "task": "T1", "seconds": 5.0, "ts": 12},
        cmd("run", "end", 20),
        cmd("run", "start", 30),
        cmd("run", "end", 40),
    ]
    e = report.efficiency(events)
    t = e["time"]
    # active=30, model=0, switch=0, steps={"tests":5.0}, step_sum=5, idle=10, other=15
    # expected line: "  time: model 0 s, switches 0 s, tests 5 s, idle 10 s, other 15 s of 30 s active"
    lines = report.format_efficiency(e)
    time_line = next(ln for ln in lines if "time:" in ln)
    expected = (f"  time: model {t['model_seconds']:.0f} s, switches {t['switch_seconds']:.0f} s, "
                f"tests 5 s, idle {t['idle_seconds']:.0f} s, other {t['other_seconds']:.0f} s of "
                f"{t['active_seconds']:.0f} s active")
    assert time_line == expected
    # step_sum = 5.0, so other = max(0, 30-0-0-5-10) = 15.0
    assert t["other_seconds"] == 15.0


def test_idle_empty_events():
    """Empty events → idle_seconds = 0.0 and active = 0.0."""
    t = report.efficiency([])["time"]
    assert t["idle_seconds"] == 0.0
    assert t["active_seconds"] == 0.0
    assert t["other_seconds"] == 0.0


def test_idle_command_start_without_end():
    """A command start with no matching end produces no interval → all active is idle."""
    events = [
        cmd("run", "start", 10),
        call("c1", "T1", "coder", 100, 20, 30),
    ]
    t = report.efficiency(events)["time"]
    # ts: 10, 30 → session [10,30] = 20.0
    # model_seconds = 20; switch = 0; steps = {}
    # interval: run start 10, no end → no interval
    # idle = 20 - 0 = 20.0
    # other = max(0, 20 - 20 - 0 - 0 - 20) = 0.0
    assert t["idle_seconds"] == 20.0
    assert t["other_seconds"] == 0.0
