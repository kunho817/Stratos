"""Tests for task T041: how often each decider (the rules, Jev) was right about switching to the other model.

escalation_accuracy(events, threshold=0.7) -> {decider: stats}
    Over "decision" events with decision == "escalate" (decider "rules" when the field is missing). Every such event
    counts on its own (there is one per failed attempt). Its truth comes from the events AFTER it in the list: find the
    first "outcome" with result "passed" whose call (matched by call_id to a "call" event) is for the same task and has
    role "coder" or "coder_hard". If that call's role is the decision's role, switching was not needed (truth False);
    if it is the other role, switching was needed (truth True); if there is none, the decision is not judged.
    (When a task did switch early we cannot know whether one more try of the same model would have passed; this rule
    counts the switch as right.)
    stats has the same five keys as decision_accuracy: decisions, judged, correct, confident_judged (judged with
    confidence >= threshold), confident_correct. A choice of None is counted in decisions only.
"""
from stratos.report import escalation_accuracy


def call(cid, task, role):
    return {"kind": "call", "call_id": cid, "task": task, "role": role}


def outcome(cid, task, result):
    return {"kind": "outcome", "call_id": cid, "task": task, "result": result}


def esc(task, role, choice, confidence, decider=None):
    e = {"kind": "decision", "decision": "escalate", "task": task, "role": role, "attempt": 1,
         "choice": choice, "confidence": confidence, "reason": "r"}
    if decider:
        e["decider"] = decider
    return e


def test_same_model_passes_next_so_staying_was_right():
    events = [call("a1", "T1", "coder"), outcome("a1", "T1", "failed"),
              esc("T1", "coder", False, 0.6), esc("T1", "coder", True, 0.8, "jev"),
              call("a2", "T1", "coder"), outcome("a2", "T1", "passed")]
    acc = escalation_accuracy(events)
    assert acc["rules"] == {"decisions": 1, "judged": 1, "correct": 1, "confident_judged": 0, "confident_correct": 0}
    assert acc["jev"] == {"decisions": 1, "judged": 1, "correct": 0, "confident_judged": 1, "confident_correct": 0}


def test_other_model_passes_so_switching_was_right():
    events = [call("a1", "T1", "coder"), outcome("a1", "T1", "failed"),
              esc("T1", "coder", False, 0.6, "rules"), esc("T1", "coder", True, 0.71, "jev"),
              call("a2", "T1", "coder"), outcome("a2", "T1", "failed"),
              esc("T1", "coder", True, 0.7, "rules"),
              call("r", "T1", "reviewer"), outcome("r", "T1", "passed"),      # reviewer calls do not count
              call("b1", "T1", "coder_hard"), outcome("b1", "T1", "passed")]
    acc = escalation_accuracy(events)
    assert acc["rules"] == {"decisions": 2, "judged": 2, "correct": 1, "confident_judged": 1, "confident_correct": 1}
    assert acc["jev"]["correct"] == 1 and acc["jev"]["confident_correct"] == 1


def test_only_later_events_and_the_same_task_count():
    events = [call("x", "T1", "coder"), outcome("x", "T1", "passed"),         # before the decision: ignored
              call("a1", "T1", "coder"), outcome("a1", "T1", "failed"),
              esc("T1", "coder", False, 0.6),
              call("o", "T2", "coder"), outcome("o", "T2", "passed"),         # another task: ignored
              esc("T1", "coder", None, None, "jev")]
    acc = escalation_accuracy(events)
    assert acc["rules"]["judged"] == 0 and acc["rules"]["decisions"] == 1
    assert acc["jev"] == {"decisions": 1, "judged": 0, "correct": 0, "confident_judged": 0, "confident_correct": 0}


def test_role_decisions_are_not_mixed_in():
    events = [{"kind": "decision", "decision": "role", "task": "T1", "choice": "coder", "confidence": 0.7}]
    assert escalation_accuracy(events) == {}
