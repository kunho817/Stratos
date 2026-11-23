"""Tests for task facts-derive-messages: derive sends proper system/user messages and rejects non-dict facts.

After the fix:
- derive sends model A (REF_WRITER) a system message = SYSTEM_A (instructions only, no {rules} placeholder,
  no rules text) and a user message containing the rules.
- derive sends model B (coder) a system message = SYSTEM_B (instructions only, no {rules} or {keys}
  placeholder, no rules text) and a user message containing the rules plus fact names and input keys.
- Neither system message is empty, neither user message is empty.
- When a program's JSON output has a fact whose value is not a dict, that program counts as failed
  (A: "program A failed", B: "program B failed"); it is not included in comparison.

SYSTEM_A keeps words: "Python 3", "JSON", "```python", "NONE", "400", "sorted", "rules", "never".
SYSTEM_B keeps words: "fact", "key", "rule", "never", "value".
Neither SYSTEM_A nor SYSTEM_B contains the literal string "{rules}" or "{keys}".
"""

import json

from stratos import config, facts


class FakeGateway:
    """Fake gateway that records messages and returns pre-set answers."""

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


RULES = "The sum of two numbers is always commutative."

# helper: build matching answers for both A and B printing the same code
def _same_pair(code, fact_output):
    answer = f"```python\nimport json\nprint(json.dumps({fact_output}))\n```"
    return [(answer), (answer)]


# 1
def test_system_a_has_no_rules_placeholder():
    # SYSTEM_A must not contain the literal "{rules}" string
    # Expected: "{rules}" absent from SYSTEM_A
    assert "{rules}" not in facts.SYSTEM_A


# 2
def test_system_b_has_no_rules_or_keys_placeholder():
    # SYSTEM_B must not contain "{rules}" or "{keys}"
    # Expected: neither placeholder in SYSTEM_B
    assert "{rules}" not in facts.SYSTEM_B
    assert "{keys}" not in facts.SYSTEM_B


# 3
def test_derive_system_message_a_is_instructions_only():
    # A's system message is SYSTEM_A (the instructions), not the rules text.
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    answer_a = f"```python\n{code_a}\n```"
    answer_b = f"```python\n{code_b}\n```"
    gw = FakeGateway([("c1", answer_a), ("c2", answer_b)])
    facts.derive(gw, RULES, log=_log)
    # Expected: first call system message content == facts.SYSTEM_A
    sys_a = gw.calls[0][0][0]
    assert sys_a["role"] == "system"
    assert sys_a["content"] == facts.SYSTEM_A
    # Expected: rules text NOT in system message
    assert RULES not in sys_a["content"]


# 4
def test_derive_user_message_a_is_rules():
    # A's user message contains the rules.
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    answer_a = f"```python\n{code_a}\n```"
    answer_b = f"```python\n{code_b}\n```"
    gw = FakeGateway([("c1", answer_a), ("c2", answer_b)])
    facts.derive(gw, RULES, log=_log)
    # Expected: user message for A contains RULES
    user_a = gw.calls[0][0][1]
    assert user_a["role"] == "user"
    assert RULES in user_a["content"]


# 5
def test_derive_system_message_b_is_instructions_only():
    # B's system message is SYSTEM_B (instructions), not the rules text.
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    answer_a = f"```python\n{code_a}\n```"
    answer_b = f"```python\n{code_b}\n```"
    gw = FakeGateway([("c1", answer_a), ("c2", answer_b)])
    facts.derive(gw, RULES, log=_log)
    # Expected: second call system message content == facts.SYSTEM_B
    sys_b = gw.calls[1][0][0]
    assert sys_b["role"] == "system"
    assert sys_b["content"] == facts.SYSTEM_B
    # Expected: rules text NOT in B's system message
    assert RULES not in sys_b["content"]


# 6
def test_derive_user_message_b_has_rules_and_keys():
    # B's user message contains rules AND fact names + input keys.
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1, "y": 2}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": 1, "y": 2}}))'
    answer_a = f"```python\n{code_a}\n```"
    answer_b = f"```python\n{code_b}\n```"
    gw = FakeGateway([("c1", answer_a), ("c2", answer_b)])
    facts.derive(gw, RULES, log=_log)
    # Expected: B's user message has RULES, fact name "a", keys "x" and "y"
    user_b = gw.calls[1][0][1]
    assert user_b["role"] == "user"
    assert RULES in user_b["content"]
    # Expected: fact name "a" present
    assert "a" in user_b["content"]
    # Expected: key "x" present
    assert "x" in user_b["content"]
    # Expected: key "y" present
    assert "y" in user_b["content"]


# 7
def test_derive_system_message_a_not_empty():
    # A's system message must not be empty.
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    answer_a = f"```python\n{code_a}\n```"
    answer_b = f"```python\n{code_b}\n```"
    gw = FakeGateway([("c1", answer_a), ("c2", answer_b)])
    facts.derive(gw, RULES, log=_log)
    # Expected: A's system message is non-empty
    sys_a = gw.calls[0][0][0]
    # Expected: content has at least one non-whitespace character
    assert sys_a["content"].strip() != ""


# 8
def test_derive_system_message_b_not_empty():
    # B's system message must not be empty.
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    answer_a = f"```python\n{code_a}\n```"
    answer_b = f"```python\n{code_b}\n```"
    gw = FakeGateway([("c1", answer_a), ("c2", answer_b)])
    facts.derive(gw, RULES, log=_log)
    # Expected: B's system message is non-empty
    sys_b = gw.calls[1][0][0]
    # Expected: content has at least one non-whitespace character
    assert sys_b["content"].strip() != ""


# 9
def test_derive_user_message_a_not_empty():
    # A's user message must not be empty.
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    answer_a = f"```python\n{code_a}\n```"
    answer_b = f"```python\n{code_b}\n```"
    gw = FakeGateway([("c1", answer_a), ("c2", answer_b)])
    facts.derive(gw, RULES, log=_log)
    # Expected: A's user message is non-empty
    user_a = gw.calls[0][0][1]
    # Expected: content has at least one non-whitespace character
    assert user_a["content"].strip() != ""


# 10
def test_derive_user_message_b_not_empty():
    # B's user message must not be empty.
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    answer_a = f"```python\n{code_a}\n```"
    answer_b = f"```python\n{code_b}\n```"
    gw = FakeGateway([("c1", answer_a), ("c2", answer_b)])
    facts.derive(gw, RULES, log=_log)
    # Expected: B's user message is non-empty
    user_b = gw.calls[1][0][1]
    # Expected: content has at least one non-whitespace character
    assert user_b["content"].strip() != ""


# 11
def test_derive_non_dict_fact_value_a_fails():
    # A outputs {"a": 42} — fact "a" value is 42 (an int), not a dict -> program A failed.
    code_a = 'import json\nprint(json.dumps({"a": 42}))'
    answer_a = f"```python\n{code_a}\n```"
    gw = FakeGateway([("c1", answer_a)])
    result = facts.derive(gw, RULES, log=_log)
    # Expected: {"facts": None, "reason": "program A failed"}
    assert result == {"facts": None, "reason": "program A failed"}
    # Expected: only 1 chat call (no second model invoked)
    assert len(gw.calls) == 1


# 12
def test_derive_non_dict_fact_value_b_fails():
    # A succeeds with {"a": {"x": 1}}, B outputs {"a": "not a dict"} -> fact value is str, not dict -> B failed.
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b = 'import json\nprint(json.dumps({"a": "not a dict"}))'
    answer_a = f"```python\n{code_a}\n```"
    answer_b = f"```python\n{code_b}\n```"
    gw = FakeGateway([("c1", answer_a), ("c2", answer_b)])
    result = facts.derive(gw, RULES, log=_log)
    # Expected: {"facts": None, "reason": "program B failed"}
    assert result == {"facts": None, "reason": "program B failed"}


# 13
def test_derive_non_dict_fact_value_list_a_fails():
    # A outputs {"a": [1, 2, 3]} — fact "a" value is a list, not a dict -> program A failed.
    code_a = 'import json\nprint(json.dumps({"a": [1, 2, 3]}))'
    answer_a = f"```python\n{code_a}\n```"
    gw = FakeGateway([("c1", answer_a)])
    result = facts.derive(gw, RULES, log=_log)
    # Expected: {"facts": None, "reason": "program A failed"}
    assert result == {"facts": None, "reason": "program A failed"}


# 14
def test_derive_system_a_mentions_instructions():
    # SYSTEM_A mentions required elements: Python 3, JSON, ```python, NONE, 400, sorted, rules
    s = facts.SYSTEM_A
    assert "Python 3" in s
    assert "JSON" in s
    assert "```python" in s
    assert "NONE" in s
    assert "400" in s
    assert "sorted" in s
    # Expected: "rules" in SYSTEM_A (instructions reference rules concept)
    assert "rules" in s.lower()


# 15
def test_derive_system_b_mentions_instructions():
    # SYSTEM_B mentions required elements: fact, key, rule, never, value
    s = facts.SYSTEM_B
    assert "fact" in s.lower()
    assert "key" in s.lower()
    assert "rule" in s.lower()
    # Expected: "never" in SYSTEM_B
    assert "never" in s.lower()
    # Expected: "value" in SYSTEM_B
    assert "value" in s.lower()
