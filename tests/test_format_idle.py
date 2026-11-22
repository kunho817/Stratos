"""Tests for task format_idle: format_efficiency shows idle seconds.

When time["idle_seconds"] > 0, the time line inserts ", idle <s> s" (s formatted
with :.0f, i.e. a whole number) right before ", other ...". When idle_seconds
is 0 the time line stays as today (no ", idle"). The idle value is taken from
efficiency's time dict, which is computed from command start/end intervals.

Fakes: plain event dicts, no network, no GPU, no models.
"""
from stratos import report


def cmd(name, phase, ts):
    return {"kind": "command", "name": name, "phase": phase, "ts": ts}


def call(cid, task, role, tokens, secs, ts, finish="stop", model="m"):
    return {"kind": "call", "call_id": cid, "task": task, "role": role, "model": model,
            "completion_tokens": tokens, "prompt_tokens": 999, "seconds": secs,
            "finish": finish, "ts": ts}


# Events producing idle_seconds = 7.0:
#   ts values: 0, 23, 30 → one session [0, 30] = 30.0 active
#   No model calls, no switches, no steps.
#   Command intervals: run start=0, end=23 → [0,23]; run start=30, no end → no interval.
#   Merged coverage = 23.0
#   idle = 30.0 - 23.0 = 7.0
#   other = max(0, 30.0 - 0.0 - 0.0 - 0.0 - 7.0) = 23.0
EVENTS_IDLE7 = [
    cmd("run", "start", 0),
    cmd("run", "end", 23),
    cmd("run", "start", 30),
]

# Events from test_efficiency.py EVENTS (no command events → idle = 0.0).
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


def test_format_shows_idle_7s_before_other():
    """idle_seconds = 7.0 → the time line contains ", idle 7 s" right before ", other"."""
    e = report.efficiency(EVENTS_IDLE7)
    t = e["time"]
    # step 1: ts values [0, 23, 30]; gaps 23-0=23, 30-23=7, both ≤ 600
    #   → one session [0, 30] = 30.0
    # step 2: no model calls → model_seconds = 0.0
    # step 3: no switch events → switch_seconds = 0.0
    # step 4: no step events → step_sum = 0.0
    # step 5: command intervals: run [0, 23] (start 0, end 23);
    #   start 30 has no end → no interval. Merged coverage = 23.0
    # step 6: idle = 30.0 - 23.0 = 7.0
    # step 7: other = max(0, 30.0 - 0.0 - 0.0 - 0.0 - 7.0) = 23.0
    # step 8: format uses :.0f for idle → "idle 7 s"
    assert t["idle_seconds"] == 7.0
    assert t["active_seconds"] == 30.0
    assert t["other_seconds"] == 23.0

    lines = report.format_efficiency(e)
    time_line = next(ln for ln in lines if "time:" in ln)
    # Expected format (no steps, idle > 0):
    #   "  time: model 0 s, switches 0 s, idle 7 s, other 23 s of 30 s active"
    #   model_seconds 0.0 → :.0f → "0"
    #   switch_seconds 0.0 → :.0f → "0"
    #   idle_seconds 7.0 → :.0f → "7"
    #   other_seconds 23.0 → :.0f → "23"
    #   active_seconds 30.0 → :.0f → "30"
    assert "idle 7 s" in time_line
    # Check idle appears before "other" in the line
    idx_idle = time_line.index("idle 7 s")
    idx_other = time_line.index("other")
    assert idx_idle < idx_other
    # Check the exact substring ", idle 7 s, other" (idle right before other)
    assert ", idle 7 s, other" in time_line


def test_format_no_idle_when_zero():
    """idle_seconds == 0 → the time line has no ", idle" (same as today)."""
    e = report.efficiency(EVENTS_NO_CMD)
    t = e["time"]
    # step 1: ts values 1000..1301 (session 1 = 301.0) + 3000..3101 (session 2 = 101.0)
    #   = 402.0 active
    # step 2: model_seconds = 10+20+30+5+40+50+60+7 = 222.0
    # step 3: switch_seconds = 20.0
    # step 4: no step events → step_sum = 0.0
    # step 5: no command events → idle_seconds = 0.0
    # step 6: other = max(0, 402.0 - 222.0 - 20.0 - 0.0 - 0.0) = 160.0
    # step 7: idle = 0 → format line has no ", idle"
    # Expected: "  time: model 222 s, switches 20 s, other 160 s of 402 s active"
    assert t["idle_seconds"] == 0.0
    lines = report.format_efficiency(e)
    time_line = next(ln for ln in lines if "time:" in ln)
    assert ", idle" not in time_line


def test_format_idle_after_steps_before_other():
    """Steps and idle > 0 → order in the time line is steps, idle, other."""
    events = [
        cmd("run", "start", 0),
        {"kind": "step", "name": "tests", "task": "T1", "seconds": 5.0, "ts": 12},
        cmd("run", "end", 23),
        cmd("run", "start", 30),
    ]
    e = report.efficiency(events)
    t = e["time"]
    # step 1: ts values 0, 12, 23, 30; gaps 12, 11, 7 all ≤ 600 → session [0, 30] = 30.0
    # step 2: no model calls → model_seconds = 0.0
    # step 3: no switch events → switch_seconds = 0.0
    # step 4: step events: tests 5.0 → step_sum = 5.0
    # step 5: command intervals: run [0, 23]; start 30 no end → coverage 23.0
    # step 6: idle = 30.0 - 23.0 = 7.0
    # step 7: other = max(0, 30.0 - 0.0 - 0.0 - 5.0 - 7.0) = 18.0
    # step 8: format (with steps, idle > 0):
    #   "  time: model 0 s, switches 0 s, tests 5 s, idle 7 s, other 18 s of 30 s active"
    assert t["idle_seconds"] == 7.0
    assert t["other_seconds"] == 18.0

    lines = report.format_efficiency(e)
    time_line = next(ln for ln in lines if "time:" in ln)
    # Expected format (steps present, idle > 0):
    #   "  time: model 0 s, switches 0 s, tests 5 s, idle 7 s, other 18 s of 30 s active"
    assert "tests 5 s, idle 7 s, other 18 s" in time_line
    # Check ordering: steps → idle → other
    assert time_line.index("tests 5 s") < time_line.index("idle 7 s")
    assert time_line.index("idle 7 s") < time_line.index("other")
