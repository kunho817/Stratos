"""Tests for T244 (P22, 2026-11-21): where the "other" time goes.

report --efficiency said "other 34250 s of 92152 s active" (37%) with no breakdown: everything that is neither a model
call nor a model switch - test runs (3 seeds per attempt), static checks, lint, the reference check. Now those steps
are timed.

stratos/steps.py:
  use(telemetry, task=None): later timed steps are recorded to this telemetry with this task; use(None) stops it.
  timed(name): a context manager; on leaving (also by an exception) it records, when a telemetry is in use,
    telemetry.record("step", name=name, task=<the task given to use>, seconds=round(elapsed, 2)) with the elapsed
    time from time.monotonic().
Timed steps: verify.run_tests -> "tests"; checker.check (the command run) -> "check"; lint.check -> "lint";
  refcheck.check (its test run) -> "refcheck"; refcheck.mutation -> "mutation"; plantests.check_draft ->
  "draft_check".
loop.write_task calls steps.use(gw.telemetry, task_id) first; plantests.draft_tests calls
  steps.use(gw.telemetry, plan_id) first.
report.efficiency(events)["time"]["steps"]: {name: seconds summed over the "step" events, rounded to 1 decimal},
  keys sorted; "other_seconds" = max(0, active - model - switch - the sum of the steps), rounded to 1 decimal.
report.format_efficiency (a list of lines) - its time line, when steps is not empty:
  f"  time: model {m:.0f} s, switches {s:.0f} s, " + ", ".join(f"{name} {sec:.0f} s") + f", other {o:.0f} s of
  {a:.0f} s active"; with no steps it is the line it was."""
import inspect

import pytest

from stratos import checker, lint, loop, plantests, refcheck, report, steps, verify


class Tel:
    def __init__(self):
        self.events = []

    def record(self, kind, **fields):
        self.events.append({"kind": kind, **fields})


@pytest.fixture(autouse=True)
def reset_steps():
    yield
    steps.use(None)


def test_timed_records_to_the_telemetry_in_use(monkeypatch):
    clock = iter([10.0, 12.345, 20.0, 21.0])
    monkeypatch.setattr(steps.time, "monotonic", lambda: next(clock))
    tel = Tel()
    steps.use(tel, "T9")
    with steps.timed("tests"):
        pass
    with pytest.raises(ValueError):
        with steps.timed("check"):
            raise ValueError("x")
    assert tel.events == [{"kind": "step", "name": "tests", "task": "T9", "seconds": 2.35},
                          {"kind": "step", "name": "check", "task": "T9", "seconds": 1.0}]


def test_nothing_is_recorded_without_a_telemetry():
    steps.use(None)
    with steps.timed("tests"):
        pass   # no error, nowhere to record


def timed_in(fn, name):
    return f'steps.timed("{name}")' in inspect.getsource(fn)


def test_verify_checker_lint_are_timed():          # part A (with steps.py)
    assert timed_in(verify.run_tests, "tests") and timed_in(checker.check, "check") and timed_in(lint.check, "lint")


def test_refcheck_and_drafts_are_timed():          # part B
    assert timed_in(refcheck.check, "refcheck") and timed_in(refcheck.mutation, "mutation")
    assert timed_in(plantests.check_draft, "draft_check")
    assert "steps.use(gw.telemetry, plan_id)" in inspect.getsource(plantests.draft_tests)


def test_the_loop_names_its_task():                # part C
    assert "steps.use(gw.telemetry, task_id)" in inspect.getsource(loop.write_task)


EVENTS = [
    {"kind": "call", "ts": 1000, "seconds": 100, "completion_tokens": 10, "call_id": "c1", "role": "coder"},
    {"kind": "step", "ts": 1100, "name": "tests", "task": "T1", "seconds": 30.04},
    {"kind": "step", "ts": 1150, "name": "check", "task": "T1", "seconds": 5},
    {"kind": "step", "ts": 1200, "name": "tests", "task": "T1", "seconds": 20},
    {"kind": "outcome", "ts": 1300, "call_id": "c1", "result": "passed"},
]


def test_report_breaks_down_the_other_time():   # part C
    t = report.efficiency(EVENTS)["time"]
    assert t["steps"] == {"check": 5.0, "tests": 50.0}
    assert list(t["steps"]) == ["check", "tests"]
    assert t["active_seconds"] == 300.0
    assert t["other_seconds"] == round(300.0 - t["model_seconds"] - t["switch_seconds"] - 55.04, 1)
    line = next(ln for ln in report.format_efficiency(report.efficiency(EVENTS)) if "time:" in ln)   # a list of lines
    assert line == (f"  time: model {t['model_seconds']:.0f} s, switches {t['switch_seconds']:.0f} s, check 5 s, "
                    f"tests 50 s, other {t['other_seconds']:.0f} s of 300 s active")
