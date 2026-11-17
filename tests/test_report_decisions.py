"""Tests for task T035: how often each decider (the rules, Jev, ...) chose the right coder role.

role_truth(events) -> {task: "coder" | "coder_hard"}
    What a task really needed, read from telemetry: "call" events carry call_id, task and role; "outcome" events carry
    call_id and result. A task needed "coder" when any of its calls with role "coder" led to result "passed". It
    needed "coder_hard" when no "coder" call passed, at least one "coder" call led to another result, and a
    "coder_hard" call passed. Any other task (nothing passed, or only coder_hard ran) is left out: we cannot tell.
    Reviewer calls and their outcomes do not count.

decision_accuracy(events, threshold=0.3) -> {decider: stats}
    Over "decision" events with decision == "role". The decider is the event's "decider" field ("rules" when the
    field is missing: older events). For each (task, decider) only the last such event counts. stats is a dict:
      decisions          number of tasks this decider made a role decision for
      judged             of those, the ones whose choice is not None and whose task is in role_truth
      correct            of the judged, the ones whose choice equals the truth
      confident_judged   of the judged, the ones with confidence >= threshold
      confident_correct  of those, the correct ones
"""
from stratos.report import decision_accuracy, role_truth


def call(cid, task, role):
    return {"kind": "call", "call_id": cid, "task": task, "role": role}


def outcome(cid, task, result):
    return {"kind": "outcome", "call_id": cid, "task": task, "result": result}


def decision(task, choice, confidence, decider=None):
    e = {"kind": "decision", "decision": "role", "task": task, "choice": choice, "confidence": confidence,
         "reason": "r"}
    if decider is not None:
        e["decider"] = decider
    return e


EVENTS = [
    # T1: Tiel passes at once -> coder
    call("a", "T1", "coder"), outcome("a", "T1", "passed"),
    call("r", "T1", "reviewer"), outcome("r", "T1", "review_approve"),
    # T2: Tiel fails twice, Flint passes -> coder_hard
    call("b1", "T2", "coder"), outcome("b1", "T2", "failed"),
    call("b2", "T2", "coder"), outcome("b2", "T2", "no_files"),
    call("b3", "T2", "coder_hard"), outcome("b3", "T2", "passed"),
    # T3: only Flint ran -> unknown
    call("c", "T3", "coder_hard"), outcome("c", "T3", "passed"),
    # T4: Tiel fails, then Tiel passes -> coder
    call("d1", "T4", "coder"), outcome("d1", "T4", "failed"),
    call("d2", "T4", "coder"), outcome("d2", "T4", "passed"),
    # T5: nothing passed -> unknown
    call("e", "T5", "coder"), outcome("e", "T5", "failed"),
]


def test_role_truth():
    assert role_truth(EVENTS) == {"T1": "coder", "T2": "coder_hard", "T4": "coder"}


def test_decision_accuracy():
    events = EVENTS + [
        decision("T1", "coder", 0.7),                     # old event without decider -> rules; right
        decision("T2", "coder", 0.7, "rules"),            # wrong
        decision("T3", "coder_hard", 0.55, "rules"),      # not judged (unknown)
        decision("T1", "coder", 0.9, "jev"),              # right, confident
        decision("T2", "coder_hard", 0.1, "jev"),         # right, not confident
        decision("T4", "coder_hard", 0.2, "jev"),         # first word on T4 ...
        decision("T4", "coder", 0.5, "jev"),              # ... the last one counts: right, confident
        decision("T5", None, None, "jev"),                # unavailable: not judged
    ]
    acc = decision_accuracy(events)
    assert acc["rules"] == {"decisions": 3, "judged": 2, "correct": 1, "confident_judged": 2, "confident_correct": 1}
    assert acc["jev"] == {"decisions": 4, "judged": 3, "correct": 3, "confident_judged": 2, "confident_correct": 2}


def test_threshold_and_other_decisions():
    events = EVENTS + [decision("T1", "coder", 0.25, "jev"),
                       {"kind": "decision", "decision": "escalate", "task": "T2", "choice": True,
                        "confidence": 0.7, "reason": "r"}]
    assert decision_accuracy(events, threshold=0.2)["jev"]["confident_judged"] == 1
    assert decision_accuracy(events)["jev"]["confident_judged"] == 0
    assert set(decision_accuracy(events)) == {"jev"}
    assert decision_accuracy([]) == {}
