"""Tests for task facts-shapes: value_shape(v) and fact_shapes(obj) in stratos/facts.py,
the derive user message to B now includes value shapes, and SYSTEM_B gains the value-shape rule line.

value_shape(v) -> str:
  True/False -> "boolean"; int (not bool) -> "integer"; float -> "number"; str -> "string";
  None -> "null"; empty list -> "list"; list with all same shape s -> "list of " + s;
  other list -> "list [" + ", ".join(shape of each element) + "]";
  dict -> "object {" + ", ".join(f"{k}: {shape}" for sorted keys) + "}".

fact_shapes(obj) -> dict: for each fact name, sorted list of distinct value_shape of its values.

derive: B's user message = rules + "\n\nFact names, input keys and value shapes:\n" + blocks,
  each block f"{name}: {json.dumps(sorted(keys))}\n  value shape: {' or '.join(shapes)}",
  blocks joined by "\n". B never sees A's values, only their shapes.

SYSTEM_B gains one line before its last:
  "- Every value must have exactly the value shape given for its fact (for a list, the same order of elements)."

OUTDATED: none - the existing tests in test_facts.py, test_facts_derive_messages.py,
test_facts_full.py, test_facts_disagree.py all remain valid (header text change is additive,
model selection unchanged in this task).
"""

import json

from stratos import config, facts


# ---------- helpers ----------

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


def _code_answer(obj):
    """Build a gateway answer containing a ```python block that prints obj as JSON."""
    code = 'import json\nprint(json.dumps(' + json.dumps(obj) + '))'
    return f"```python\n{code}\n```"


# ---------- value_shape primitives ----------

def test_value_shape_primitives():
    # True -> "boolean"; False -> "boolean"; 5 -> "integer"; 3.14 -> "number";
    # "hello" -> "string"; None -> "null"
    assert facts.value_shape(True) == "boolean"
    assert facts.value_shape(False) == "boolean"
    # 5 is int, not bool -> "integer"
    assert facts.value_shape(5) == "integer"
    # 3.14 is float -> "number"
    assert facts.value_shape(3.14) == "number"
    # "hello" is str -> "string"
    assert facts.value_shape("hello") == "string"
    # None -> "null"
    assert facts.value_shape(None) == "null"


def test_value_shape_bool_is_not_integer():
    # True is int in Python, but must map to "boolean", not "integer".
    # 1 is int, not bool -> "integer".
    assert facts.value_shape(True) == "boolean"
    assert facts.value_shape(1) == "integer"
    # 0 is int, not bool -> "integer"
    assert facts.value_shape(0) == "integer"


# ---------- value_shape empty list ----------

def test_value_shape_empty_list():
    # [] -> "list" (no elements to check, special case)
    assert facts.value_shape([]) == "list"


# ---------- value_shape homogeneous list ----------

def test_value_shape_homogeneous_list():
    # ["e", "n"] -> all "string" -> "list of string"
    assert facts.value_shape(["e", "n"]) == "list of string"
    # [1, 2, 3] -> all "integer" -> "list of integer"
    assert facts.value_shape([1, 2, 3]) == "list of integer"


# ---------- value_shape heterogeneous list ----------

def test_value_shape_heterogeneous_list():
    # ["corner", 0] -> shapes "string", "integer" -> not same ->
    # "list [string, integer]"
    assert facts.value_shape(["corner", 0]) == "list [string, integer]"
    # [1, "a", True] -> shapes "integer", "string", "boolean" ->
    # "list [integer, string, boolean]"
    assert facts.value_shape([1, "a", True]) == "list [integer, string, boolean]"


# ---------- value_shape nested homogeneous list ----------

def test_value_shape_nested_homogeneous_list():
    # [["flower", 1], ["spring", 1]]
    # inner: ["flower", 1] -> shapes string, integer -> "list [string, integer]"
    # inner: ["spring", 1] -> "list [string, integer]"
    # all inner shapes equal -> "list of list [string, integer]"
    assert facts.value_shape([["flower", 1], ["spring", 1]]) == "list of list [string, integer]"


# ---------- value_shape dict ----------

def test_value_shape_dict():
    # {"rot": 1, "kind": "tee"}
    # sorted keys: "kind", "rot"
    # kind -> "tee" -> "string"; rot -> 1 -> "integer"
    # "object {kind: string, rot: integer}"
    assert facts.value_shape({"rot": 1, "kind": "tee"}) == "object {kind: string, rot: integer}"


# ---------- value_shape nested dict in list ----------

def test_value_shape_nested_dict_in_list():
    # [{"a": 1}, {"a": 2}]
    # each dict -> "object {a: integer}"
    # all same shape -> "list of object {a: integer}"
    assert facts.value_shape([{"a": 1}, {"a": 2}]) == "list of object {a: integer}"


# ---------- fact_shapes ----------

def test_fact_shapes_single_fact_duplicates():
    # obj = {"a": {"x": 1, "y": 2}}
    # values: 1 -> "integer", 2 -> "integer"
    # distinct shapes: {"integer"} -> sorted: ["integer"]
    # result: {"a": ["integer"]}
    obj = {"a": {"x": 1, "y": 2}}
    assert facts.fact_shapes(obj) == {"a": ["integer"]}


def test_fact_shapes_multiple_facts():
    # obj = {"a": {"x": 1, "y": "s", "z": 3.14}, "b": {"w": True, "p": "q"}}
    # fact "a": shapes integer, string, number -> sorted distinct: ["integer", "number", "string"]
    # fact "b": shapes boolean, string -> sorted distinct: ["boolean", "string"]
    # result: {"a": ["integer", "number", "string"], "b": ["boolean", "string"]}
    obj = {"a": {"x": 1, "y": "s", "z": 3.14}, "b": {"w": True, "p": "q"}}
    result = facts.fact_shapes(obj)
    assert result["a"] == ["integer", "number", "string"]
    assert result["b"] == ["boolean", "string"]


# ---------- derive B user message with shapes ----------

def test_derive_b_user_message_single_fact_exact_format():
    # A prints {"a": {"x": 1, "y": "s"}}
    # fact_shapes: {"a": ["integer", "string"]}
    # sorted keys for "a": ["x", "y"]
    # json.dumps(["x", "y"]) = '["x", "y"]'
    # shapes joined: "integer or string"
    # block: 'a: ["x", "y"]\n  value shape: integer or string'
    # full user message: RULES + "\n\nFact names, input keys and value shapes:\n" + block
    RULES = "The sum of two numbers is always commutative."
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1, "y": "s"}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": 1, "y": "s"}}))'
    gw = FakeGateway([("c1", f"```python\n{code_a}\n```"),
                      ("c2", f"```python\n{code_b}\n```")])
    facts.derive(gw, RULES, log=_log)
    user_b = gw.calls[1][0][1]["content"]
    # Expected:
    expected_block = 'a: ["x", "y"]\n  value shape: integer or string'
    expected = RULES + "\n\nFact names, input keys and value shapes:\n" + expected_block
    assert user_b == expected


def test_derive_b_user_message_two_facts_exact_format():
    # A prints {"b": {"k": 3.14}, "a": {"p": True}}
    # fact_shapes:
    #   "a": values [True] -> ["boolean"]
    #   "b": values [3.14] -> ["number"]
    # sorted names: "a", "b"
    # block a: 'a: ["p"]\n  value shape: boolean'
    # block b: 'b: ["k"]\n  value shape: number'
    # joined blocks: 'a: ["p"]\n  value shape: boolean\nb: ["k"]\n  value shape: number'
    RULES = "Rules text."
    code_a = 'import json\nprint(json.dumps({"b": {"k": 3.14}, "a": {"p": True}}))'
    code_b = 'import json\nprint(json.dumps({"b": {"k": 3.14}, "a": {"p": True}}))'
    gw = FakeGateway([("c1", f"```python\n{code_a}\n```"),
                      ("c2", f"```python\n{code_b}\n```")])
    facts.derive(gw, RULES, log=_log)
    user_b = gw.calls[1][0][1]["content"]
    block_a = 'a: ["p"]\n  value shape: boolean'
    block_b = 'b: ["k"]\n  value shape: number'
    blocks = block_a + "\n" + block_b
    expected = RULES + "\n\nFact names, input keys and value shapes:\n" + blocks
    assert user_b == expected


def test_derive_b_never_sees_a_values():
    # A prints {"a": {"x": 1, "y": "hello"}}
    # B's message must NOT contain the literal value "hello" (A's value).
    # B sees shapes "integer" and "string", not the values 1 or "hello".
    # The rules text is present, keys "x","y" are present, fact name "a" is present.
    RULES = "Some rules."
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1, "y": "hello"}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": 1, "y": "hello"}}))'
    gw = FakeGateway([("c1", f"```python\n{code_a}\n```"),
                      ("c2", f"```python\n{code_b}\n```")])
    facts.derive(gw, RULES, log=_log)
    user_b = gw.calls[1][0][1]["content"]
    # "hello" is A's value, must NOT appear in B's user message
    assert "hello" not in user_b
    # shapes must appear
    assert "integer" in user_b
    assert "string" in user_b
    # fact name and keys appear
    assert "a" in user_b
    assert "x" in user_b
    assert "y" in user_b


# ---------- SYSTEM_B new line ----------

def test_system_b_has_value_shape_rule_before_last_line():
    new_line = "- Every value must have exactly the value shape given for its fact (for a list, the same order of elements)."
    assert new_line in facts.SYSTEM_B
    # It must NOT be the last line
    lines = facts.SYSTEM_B.split("\n")
    # Last non-empty line is the answer line
    last_line = [l for l in lines if l.strip()][-1]
    assert "The answer is exactly one" in last_line
    # The new rule line must appear before the last line
    new_idx = facts.SYSTEM_B.index(new_line)
    last_idx = facts.SYSTEM_B.index(last_line)
    # step: new_idx < last_idx means the rule comes first
    assert new_idx < last_idx


# ---------- derive B user message header text ----------

def test_derive_b_header_changed_to_include_shapes():
    # The header is now "Fact names, input keys and value shapes:"
    # NOT the old "Fact names and input keys:"
    RULES = "x."
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    gw = FakeGateway([("c1", f"```python\n{code_a}\n```"),
                      ("c2", f"```python\n{code_b}\n```")])
    facts.derive(gw, RULES, log=_log)
    user_b = gw.calls[1][0][1]["content"]
    assert "Fact names, input keys and value shapes:" in user_b
    # Old header must NOT be present
    assert "Fact names and input keys:" not in user_b
