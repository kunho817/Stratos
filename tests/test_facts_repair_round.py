"""Tests for task facts-repair-round: facts._fix_message and one repair round in facts.derive.

_fix_message(user, code, error) -> str:
  When code does not end with "\n", add one.
  Return: user + "\n\nYour program:\n```python\n" + code + "```\nfailed with:\n"
          + error[-2000:] + "\n\nWrite the whole program again with the error fixed, in one ```python block."

derive with one repair round:
  After run_program_full(code_a): if obj_a is None AND code_a is not None ->
    log("facts: program A failed, asking once more"),
    _chat(gw, config.REF_WRITER, SYSTEM_A, _fix_message(rules, code_a, err_a)),
    extract code; if not None -> code_a = new code, run once more.
    Then the existing failure branch runs.
  After run_program_full(code_b): if obj_b is None AND code_b is not None ->
    log("facts: program B failed, asking once more"),
    _chat(gw, config.FACTS_B, SYSTEM_B, _fix_message(user_b, code_b, err_b)),
    extract code; if not None -> code_b = new code, run once more.
    Then the existing failure branch runs.
  Only ONE repair per program. No repair when code is None (NONE / no code).
  No repair for "a fact is not a JSON object" (obj is not None -> condition false).

OUTDATED: tests/test_facts.py::test_derive_program_a_fails - needs 2 gateway answers (A crash, A crash again); the repair round runs once more.
OUTDATED: tests/test_facts.py::test_derive_program_b_fails - needs 3 answers (A ok, B crash, B crash again); gw.models now has 3 entries [REF_WRITER, FACTS_B, FACTS_B].
OUTDATED: tests/test_facts_disagree.py::test_keep_a_none_when_a_crashes - needs 2 answers (A crash, A crash again); the unused B answer is removed.
OUTDATED: tests/test_facts_disagree.py::test_keep_b_none_when_b_crashes - needs 3 answers (A ok, B crash, B crash again).
"""

import json

from stratos import config, facts


class FakeGateway:
    """answers: list of (call_id, text) tuples returned from chat() in order."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.models = []
        self.calls = []

    def ensure_model(self, model):
        self.models.append(model)

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        return self.answers.pop(0)


def _log(*a):
    pass


def _code_answer(code):
    return f"```python\n{code}\n```"


# ---------- _fix_message ----------

def test_fix_message_format():
    # user="rules", code="x=1", error="boom"
    # code does NOT end with \n -> add one: "x=1\n"
    # full result string:
    #   "rules\n\nYour program:\n```python\nx=1\n```\nfailed with:\nboom\n\nWrite the whole program again with the error fixed, in one ```python block."
    result = facts._fix_message("rules", "x=1", "boom")
    expected = "rules\n\nYour program:\n```python\nx=1\n```\nfailed with:\nboom\n\nWrite the whole program again with the error fixed, in one ```python block."
    assert result == expected


def test_fix_message_code_already_ends_with_newline():
    # code="x=1\n" ends with \n -> no extra newline added
    # The code section between fences must be "x=1\n" not "x=1\n\n"
    result = facts._fix_message("rules", "x=1\n", "boom")
    # "x=1\n" + "```" means code + closing fence
    assert "x=1\n```" in result
    # "x=1\n\n" before the closing fence means double newline -> should not appear
    assert "x=1\n\n```" not in result


def test_fix_message_error_last_2000_chars():
    # error = "x" * 3000; error[-2000:] = "x" * 2000
    long_err = "x" * 3000
    result = facts._fix_message("r", "c\n", long_err)
    # last 2000 x's are present
    # Expected: "x" * 2000 in result
    assert "x" * 2000 in result
    # 2001 consecutive x's must not appear (only 2000 kept)
    # Expected: "x" * 2001 not in result
    assert "x" * 2001 not in result


# ---------- Repair round for A ----------

def test_derive_a_repair_crashes_again():
    # A crashes, repair code also crashes -> result stays "program A failed"
    code_crash = 'raise Exception("boom")'
    code_crash2 = 'raise Exception("boom2")'
    gw = FakeGateway([("c1", _code_answer(code_crash)),
                      ("c2", _code_answer(code_crash2))])
    result = facts.derive(gw, "rules", log=_log)
    # Expected: {"facts": None, "reason": "program A failed"}
    assert result == {"facts": None, "reason": "program A failed"}
    # Two chat calls: original + repair
    # Expected: len(gw.calls) == 2
    assert len(gw.calls) == 2
    # Both use REF_WRITER
    # Expected: [REF_WRITER.model, REF_WRITER.model]
    assert gw.models == [config.REF_WRITER["model"], config.REF_WRITER["model"]]


def test_derive_a_repair_succeeds():
    # A crashes, repair succeeds, B succeeds -> agree
    code_crash = 'raise Exception("boom")'
    code_ok = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    answer_a = _code_answer(code_crash)
    answer_repair = _code_answer(code_ok)
    answer_b = _code_answer(code_ok)
    gw = FakeGateway([("c1", answer_a), ("c2", answer_repair), ("c3", answer_b)])
    result = facts.derive(gw, "rules", log=_log)
    # Expected: reason "agree", facts {"a": {"x": 1}}
    assert result["reason"] == "agree"
    assert result["facts"] == {"a": {"x": 1}}
    # 3 chat calls: A original, A repair, B
    # Expected: len(gw.calls) == 3
    assert len(gw.calls) == 3
    # Expected: models [REF_WRITER, REF_WRITER, FACTS_B]
    assert gw.models == [config.REF_WRITER["model"], config.REF_WRITER["model"], config.FACTS_B["model"]]


def test_derive_a_repair_no_code_in_answer():
    # A crashes, repair answer has no code block -> no re-run, failure
    code_crash = 'raise Exception("boom")'
    gw = FakeGateway([("c1", _code_answer(code_crash)),
                      ("c2", "I cannot fix this.")])
    result = facts.derive(gw, "rules", log=_log)
    # Expected: program A failed
    assert result == {"facts": None, "reason": "program A failed"}
    # Expected: 2 chat calls (repair asked, no re-run)
    assert len(gw.calls) == 2


def test_derive_a_no_repair_code_none():
    # A answers NONE -> code_a is None -> no repair
    gw = FakeGateway([("c1", "NONE")])
    result = facts.derive(gw, "rules", log=_log)
    # Expected: reason "none"
    assert result == {"facts": None, "reason": "none"}
    # Expected: only 1 chat call
    assert len(gw.calls) == 1


def test_derive_a_no_repair_no_program():
    # A's answer has no fenced code block -> code_a is None -> no repair
    gw = FakeGateway([("c1", "I have no code")])
    result = facts.derive(gw, "rules", log=_log)
    # Expected: program A failed
    assert result == {"facts": None, "reason": "program A failed"}
    # Expected: only 1 chat call
    assert len(gw.calls) == 1


def test_derive_a_no_repair_non_dict_fact():
    # A runs OK (obj_a not None) but fact value is not a dict -> no repair
    code = 'import json\nprint(json.dumps({"a": 42}))'
    gw = FakeGateway([("c1", _code_answer(code))])
    result = facts.derive(gw, "rules", log=_log)
    # obj_a is not None, so the repair condition obj_a is None is False
    # Expected: program A failed (the "not JSON object" branch, no repair)
    assert result == {"facts": None, "reason": "program A failed"}
    # Expected: only 1 chat call
    assert len(gw.calls) == 1


def test_derive_a_repair_chat_params():
    # Verify the repair call: model=REF_WRITER, system=SYSTEM_A, user starts with rules
    code_crash = 'raise Exception("boom")'
    code_ok = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    rules = "the rules"
    gw = FakeGateway([("c1", _code_answer(code_crash)),
                      ("c2", _code_answer(code_ok)),
                      ("c3", _code_answer(code_ok))])
    facts.derive(gw, rules, log=_log)
    # Second call (the repair)
    msgs2, kw2 = gw.calls[1]
    # Expected: model == REF_WRITER["model"]
    assert kw2["model"] == config.REF_WRITER["model"]
    # Expected: system content == SYSTEM_A
    assert msgs2[0]["role"] == "system"
    # Expected: system content == facts.SYSTEM_A
    assert msgs2[0]["content"] == facts.SYSTEM_A
    # Expected: user content starts with the rules string
    assert msgs2[1]["role"] == "user"
    # Expected: user content starts with "the rules"
    assert msgs2[1]["content"].startswith(rules)
    # Expected: user content contains the crashed code
    assert code_crash in msgs2[1]["content"]
    # Expected: user content contains the fix instruction
    assert "Write the whole program again" in msgs2[1]["content"]
    # Expected: task=facts, role=facts, attempt=1
    assert kw2["task"] == "facts"
    assert kw2["role"] == "facts"
    assert kw2["attempt"] == 1


def test_derive_a_repair_log():
    # log receives "facts: program A failed, asking once more"
    logged = []
    def log(*a):
        logged.append(" ".join(str(x) for x in a))
    code_crash = 'raise Exception("boom")'
    code_ok = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    gw = FakeGateway([("c1", _code_answer(code_crash)),
                      ("c2", _code_answer(code_ok)),
                      ("c3", _code_answer(code_ok))])
    facts.derive(gw, "rules", log=log)
    # Expected: "facts: program A failed, asking once more" is logged
    # log is called with one string arg
    found = any("facts: program A failed, asking once more" in entry for entry in logged)
    assert found


# ---------- Repair round for B ----------

def test_derive_b_repair_crashes_again():
    # A succeeds, B crashes, B repair crashes -> result "program B failed"
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b1 = 'raise Exception("boom")'
    code_b2 = 'raise Exception("boom2")'
    gw = FakeGateway([("c1", _code_answer(code_a)),
                      ("c2", _code_answer(code_b1)),
                      ("c3", _code_answer(code_b2))])
    result = facts.derive(gw, "rules", log=_log)
    # Expected: {"facts": None, "reason": "program B failed"}
    assert result == {"facts": None, "reason": "program B failed"}
    # Expected: 3 chat calls
    assert len(gw.calls) == 3
    # Expected: models [REF_WRITER, FACTS_B, FACTS_B]
    assert gw.models == [config.REF_WRITER["model"], config.FACTS_B["model"], config.FACTS_B["model"]]


def test_derive_b_repair_succeeds():
    # A succeeds, B crashes, B repair succeeds (same as A) -> agree
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b1 = 'raise Exception("boom")'
    code_b_ok = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    gw = FakeGateway([("c1", _code_answer(code_a)),
                      ("c2", _code_answer(code_b1)),
                      ("c3", _code_answer(code_b_ok))])
    result = facts.derive(gw, "rules", log=_log)
    # Expected: agree
    assert result["reason"] == "agree"
    assert result["facts"] == {"a": {"x": 1}}
    # Expected: 3 chat calls
    assert len(gw.calls) == 3


def test_derive_b_repair_chat_params():
    # Verify repair B: model=FACTS_B, system=SYSTEM_B, user starts with user_b
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b1 = 'raise Exception("boom")'
    code_b_ok = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    rules = "the rules"
    gw = FakeGateway([("c1", _code_answer(code_a)),
                      ("c2", _code_answer(code_b1)),
                      ("c3", _code_answer(code_b_ok))])
    facts.derive(gw, rules, log=_log)
    # Original B user message (call index 1)
    user_b_original = gw.calls[1][0][1]["content"]
    # Repair B call (index 2)
    msgs3, kw3 = gw.calls[2]
    # Expected: model == FACTS_B["model"]
    assert kw3["model"] == config.FACTS_B["model"]
    # Expected: system == SYSTEM_B
    assert msgs3[0]["role"] == "system"
    # Expected: system content == facts.SYSTEM_B
    assert msgs3[0]["content"] == facts.SYSTEM_B
    # Expected: user content starts with original user_b
    # The repair user = _fix_message(user_b, code_b, err_b), which begins with user_b
    assert msgs3[1]["content"].startswith(user_b_original)
    # Expected: user content contains the crashed code
    assert code_b1 in msgs3[1]["content"]
    # Expected: task=facts, role=facts, attempt=1
    assert kw3["task"] == "facts"
    assert kw3["role"] == "facts"
    assert kw3["attempt"] == 1


def test_derive_b_repair_log():
    # log receives "facts: program B failed, asking once more"
    logged = []
    def log(*a):
        logged.append(" ".join(str(x) for x in a))
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b1 = 'raise Exception("boom")'
    code_b_ok = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    gw = FakeGateway([("c1", _code_answer(code_a)),
                      ("c2", _code_answer(code_b1)),
                      ("c3", _code_answer(code_b_ok))])
    facts.derive(gw, "rules", log=log)
    # Expected: "facts: program B failed, asking once more"
    found = any("facts: program B failed, asking once more" in entry for entry in logged)
    assert found
