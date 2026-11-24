"""Tests for stratos/facts.py: SYSTEM_A, SYSTEM_B, run_program, derive, render.

SYSTEM_A: prompt asking a model to turn rules into a Python 3 program that prints ONE JSON
  object {"<fact>": {"<input>": <value>}, ...}, computed by code, sets as sorted lists, at
  most 400 input keys; answer is one ```python block or the word NONE.

SYSTEM_B: prompt asking a model to write the same program for given fact names and input
  keys (gets rules and keys, never values).

run_program(code, timeout=20): runs code via sys.executable "-I" in a new temp folder,
  parses stdout as one JSON object; None on any failure, timeout, non-JSON, multiple objects.

derive(gw, rules, log=print) -> {"facts": dict|None, "reason": str}:
  asks REF_WRITER with SYSTEM_A; NONE -> "none"; run_program fails -> "program A failed";
  asks coder with SYSTEM_B + fact names/keys; run_program fails -> "program B failed";
  equal -> "agree"; not equal -> "disagree: " + up to 5 "<name> <key>: A vs B" lines.

render(facts) -> text: sorted names, each "name:" then "  key -> value_as_json" per key sorted.
"""

import json
from stratos import config, facts


# ---------- SYSTEM_A / SYSTEM_B content ----------

def test_system_a_mentions_required_elements():
    # Must mention: Python 3, JSON object, ```python block, NONE, 400, sorted
    s = facts.SYSTEM_A
    assert "Python 3" in s
    assert "JSON" in s
    assert "```python" in s
    assert "NONE" in s
    assert "400" in s
    assert "sorted" in s


def test_system_b_mentions_required_elements():
    # Must mention: fact names, input keys, rules; must say never values
    s = facts.SYSTEM_B
    assert "fact" in s.lower()
    assert "key" in s.lower()
    assert "rule" in s.lower()
    assert "never" in s.lower()
    assert "value" in s.lower()  # the phrase "never the values"


# ---------- run_program ----------

def test_run_program_valid_json():
    # Code prints one JSON object -> parsed dict
    code = 'import json\nprint(json.dumps({"a": {"x": 1, "y": 2}}))'
    # Expected: {"a": {"x": 1, "y": 2}}
    assert facts.run_program(code) == {"a": {"x": 1, "y": 2}}


def test_run_program_non_json_output():
    # Code prints a plain string, not JSON -> None
    code = 'print("not json")'
    assert facts.run_program(code) is None


def test_run_program_multiple_objects():
    # Code prints two JSON objects -> None
    code = 'import json\nprint(json.dumps({"a": 1}))\nprint(json.dumps({"b": 2}))'
    assert facts.run_program(code) is None


def test_run_program_crash():
    # Code raises an exception -> non-zero exit -> None
    code = 'raise Exception("boom")'
    assert facts.run_program(code) is None


def test_run_program_timeout():
    # Code sleeps 25 s; timeout=1 -> killed -> None
    code = 'import time\nprint("ok")\ntime.sleep(25)'
    assert facts.run_program(code, timeout=1) is None


def test_run_program_empty_output():
    # Empty code produces empty stdout -> not JSON -> None
    code = ''
    assert facts.run_program(code) is None


# ---------- FakeGateway ----------

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


def test_derive_none():
    # Model answers the single word NONE -> reason "none", facts None
    gw = FakeGateway([("c1", "NONE")])
    result = facts.derive(gw, "some rules", log=_log)
    # Expected: {"facts": None, "reason": "none"}
    assert result == {"facts": None, "reason": "none"}
    # Only one model load (REF_WRITER), no second call
    assert len(gw.models) == 1
    assert gw.models[0] == config.REF_WRITER["model"]


def test_derive_program_a_fails():
    # A's code crashes -> run_program returns None -> reason "program A failed"
    code = 'raise Exception("boom")'
    answer = f"```python\n{code}\n```"
    gw = FakeGateway([("c1", answer)])
    result = facts.derive(gw, "rules", log=_log)
    # Expected: {"facts": None, "reason": "program A failed"}
    assert result == {"facts": None, "reason": "program A failed"}


def test_derive_program_b_fails():
    # A prints JSON, B crashes -> reason "program B failed"
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b = 'raise Exception("boom")'
    answer_a = f"```python\n{code_a}\n```"
    answer_b = f"```python\n{code_b}\n```"
    gw = FakeGateway([("c1", answer_a), ("c2", answer_b)])
    result = facts.derive(gw, "rules", log=_log)
    # Expected: {"facts": None, "reason": "program B failed"}
    assert result == {"facts": None, "reason": "program B failed"}
    # Two model loads: REF_WRITER then FACTS_B
    assert gw.models == [config.REF_WRITER["model"], config.FACTS_B["model"]]


def test_derive_agree_checks_gateway_calls():
    # Both programs print the same JSON -> facts = A's facts, reason "agree"
    code = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    answer = f"```python\n{code}\n```"
    gw = FakeGateway([("c1", answer), ("c2", answer)])
    result = facts.derive(gw, "rules", log=_log)
    # Expected facts = {"a": {"x": 1}}, reason "agree"
    assert result == {"facts": {"a": {"x": 1}}, "reason": "agree"}
    # Two model loads in order: REF_WRITER then FACTS_B
    assert gw.models == [config.REF_WRITER["model"], config.FACTS_B["model"]]
    # First chat: task=facts, role=facts, attempt=1, REF_WRITER settings
    kw1 = gw.calls[0][1]
    assert kw1["task"] == "facts"
    assert kw1["role"] == "facts"
    assert kw1["attempt"] == 1
    assert kw1["model"] == config.REF_WRITER["model"]
    assert kw1["max_tokens"] == config.REF_WRITER["max_tokens"]
    # REF_WRITER has reasoning_budget=3000, so chat receives it
    # Expected: reasoning_budget == config.REF_WRITER["reasoning_budget"] == 3000
    assert kw1.get("reasoning_budget") == config.REF_WRITER["reasoning_budget"]
    # Second chat: FACTS_B settings, no reasoning_budget
    kw2 = gw.calls[1][1]
    assert kw2["model"] == config.FACTS_B["model"]
    # coder has no reasoning_budget key -> chat receives None (not set)
    assert kw2.get("reasoning_budget") is None


def test_derive_disagree():
    # A prints {"a":{"x":1}}, B prints {"a":{"x":2}} -> disagree
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": 2}}))'
    answer_a = f"```python\n{code_a}\n```"
    answer_b = f"```python\n{code_b}\n```"
    gw = FakeGateway([("c1", answer_a), ("c2", answer_b)])
    result = facts.derive(gw, "rules", log=_log)
    # facts None, reason starts with "disagree: "
    assert result["facts"] is None
    assert result["reason"].startswith("disagree: ")
    # Expected: one line "a x: 1 vs 2"
    assert "a x: 1 vs 2" in result["reason"]


def test_derive_disagree_capped_at_5_lines():
    # 6 facts each disagreeing -> reason has at most 5 disagreement lines
    n = 6
    obj_a = {f"f{i}": {"k": 1} for i in range(n)}
    obj_b = {f"f{i}": {"k": 9} for i in range(n)}
    code_a = 'import json\nprint(json.dumps(' + json.dumps(obj_a) + '))'
    code_b = 'import json\nprint(json.dumps(' + json.dumps(obj_b) + '))'
    answer_a = f"```python\n{code_a}\n```"
    answer_b = f"```python\n{code_b}\n```"
    gw = FakeGateway([("c1", answer_a), ("c2", answer_b)])
    result = facts.derive(gw, "rules", log=_log)
    # After "disagree: " split by newline: at most 5 lines
    # Expected: len(lines) <= 5, 6 disagreements exist
    lines = result["reason"].replace("disagree: ", "").split("\n")
    assert len(lines) <= 5
    assert len(lines) >= 1


# ---------- render ----------

def test_render_sorted_names_and_keys():
    # Two facts, sorted names: "a" before "b"; keys sorted within each
    facts_dict = {"b": {"x": 1, "y": [2, 3]}, "a": {"z": {"k": 4}}}
    text = facts.render(facts_dict)
    lines = text.split("\n")
    # Expected lines:
    #   "a:"
    #   '  z -> {"k": 4}'
    #   "b:"
    #   "  x -> 1"
    #   "  y -> [2, 3]"
    assert lines[0] == "a:"
    # z -> {"k": 4} : json.dumps({"k":4}) == '{"k": 4}'
    assert lines[1] == '  z -> {"k": 4}'
    assert lines[2] == "b:"
    # x -> 1 : json.dumps(1) == "1"
    assert lines[3] == "  x -> 1"
    # y -> [2, 3] : json.dumps([2,3]) == "[2, 3]"
    assert lines[4] == "  y -> [2, 3]"


def test_render_empty():
    # No facts -> empty text (or only whitespace)
    assert facts.render({}).strip() == ""
