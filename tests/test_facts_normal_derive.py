"""Tests for stratos/facts.py: derive uses normal() for comparison and disagreement.

Changes to derive:
  Step 3: compare normal(obj_a) == normal(obj_b); on agreement return
    {"facts": normal(obj_a), "reason": "agree"}.
  Step 4: skip a (name, key) pair when normal(va) == normal(vb); lines
    print raw json.dumps(va) and json.dumps(vb).
  keep["a"] and keep["b"] store the raw (unnormalized) objects.

SYSTEM_A and SYSTEM_B each gain one line right after
"- A value that is a set is printed as a sorted list.":
"- When the rules allow several answers for one input, the value lists
   every one of them (for example every rotation that fits), never only the first."

OUTDATED: none — existing tests use simple objects where normal() is the
identity, so all existing tests keep passing.
"""

import json

from stratos import config, facts


class FakeGateway:
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
    code = 'import json\nprint(json.dumps(' + json.dumps(obj) + '))'
    return f"```python\n{code}\n```"


# ---------- 1: agree when normal() equal, objects differ in list order ----------

def test_agree_normal_equal_lists_sorted():
    # A prints {"a":{"x":[["spring",1],["flower",1]]}}
    # B prints {"a":{"x":[["flower",1],["spring",1]]}}
    # The two raw objects differ in list order, so obj_a != obj_b.
    # derive compares normal(obj_a) == normal(obj_b); on agreement it returns
    # {"facts": normal(obj_a), "reason": "agree"}.
    #
    # The expected normalized value is taken from facts.normal() itself, not from
    # a hand calculation: the actual normal() reorders the inner lists too, so the
    # expected facts must equal facts.normal(obj_a) exactly.
    code_a = 'import json\nprint(json.dumps({"a": {"x": [["spring",1],["flower",1]]}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": [["flower",1],["spring",1]]}}))'
    gw = FakeGateway([("c1", f"```python\n{code_a}\n```"),
                      ("c2", f"```python\n{code_b}\n```")])
    result = facts.derive(gw, "rules", log=_log)
    # Expected: reason is "agree" (normal values match)
    assert result["reason"] == "agree"
    # Expected: facts is the normalized version of A's object, computed by normal()
    expected_facts = facts.normal({"a": {"x": [["spring", 1], ["flower", 1]]}})
    assert result["facts"] == expected_facts
    # facts is NOT the raw obj_a (which has spring first)
    assert result["facts"] != {"a": {"x": [["spring", 1], ["flower", 1]]}}


# ---------- 2: agree returns normal(obj_a), not obj_a ----------

def test_agree_facts_is_normal_not_raw():
    # Both print {"a":{"x":[[3],[1],[2]]}}
    # normal(obj_a) = {"a":{"x":[[1],[2],[3]]}}
    #   inner list: all elements are lists → sort by json.dumps
    #   json.dumps([1]) = '[1]', json.dumps([2]) = '[2]', json.dumps([3]) = '[3]'
    #   sorted: [[1],[2],[3]]
    # Expected facts = {"a": {"x": [[1], [2], [3]]}}
    obj = {"a": {"x": [[3], [1], [2]]}}
    code = 'import json\nprint(json.dumps(' + json.dumps(obj) + '))'
    gw = FakeGateway([("c1", f"```python\n{code}\n```"),
                      ("c2", f"```python\n{code}\n```")])
    result = facts.derive(gw, "rules", log=_log)
    # Expected facts = normal(obj_a)
    assert result["reason"] == "agree"
    # Expected: facts = {"a": {"x": [[1], [2], [3]]}}
    assert result["facts"] == {"a": {"x": [[1], [2], [3]]}}
    # facts is NOT the raw obj_a
    assert result["facts"] != {"a": {"x": [[3], [1], [2]]}}


# ---------- 3: agree with simple objects (normal = identity) ----------

def test_agree_simple_objects_facts_is_obj():
    # A prints {"a":{"x":1}}, B prints {"a":{"x":1}}
    # normal({"a":{"x":1}}) = {"a":{"x":1}} (scalars pass through)
    # Expected: facts = {"a": {"x": 1}}, reason = "agree"
    code = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    gw = FakeGateway([("c1", f"```python\n{code}\n```"),
                      ("c2", f"```python\n{code}\n```")])
    result = facts.derive(gw, "rules", log=_log)
    # Expected: facts = {"a": {"x": 1}}
    assert result == {"facts": {"a": {"x": 1}}, "reason": "agree"}


# ---------- 4: disagree skips pair when normal(va) == normal(vb) ----------

def test_disagree_skips_pair_normal_equal():
    # A: {"a": {"x": [["spring",1],["flower",1]], "y": 1}}
    # B: {"a": {"x": [["flower",1],["spring",1]], "y": 2}}
    # normal(obj_a) = {"a":{"x":[["flower",1],["spring",1]],"y":1}}
    # normal(obj_b) = {"a":{"x":[["flower",1],["spring",1]],"y":2}}
    # normal(obj_a) != normal(obj_b) → disagree
    # For key "x": normal(va) == normal(vb) → skip
    # For key "y": normal(1) != normal(2) → list
    # Expected reason line: "a y: 1 vs 2"
    # No line for key "x"
    code_a = 'import json\nprint(json.dumps({"a": {"x": [["spring",1],["flower",1]], "y": 1}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": [["flower",1],["spring",1]], "y": 2}}))'
    gw = FakeGateway([("c1", f"```python\n{code_a}\n```"),
                      ("c2", f"```python\n{code_b}\n```")])
    result = facts.derive(gw, "rules", log=_log)
    assert result["facts"] is None
    assert result["reason"].startswith("disagree: ")
    # Expected: "a y: 1 vs 2" present
    assert "a y: 1 vs 2" in result["reason"]
    # Expected: key "x" NOT listed (normal(va) == normal(vb))
    # json.dumps of the raw values contains "spring"
    assert "spring" not in result["reason"]


# ---------- 5: disagree lines print raw values ----------

def test_disagree_lines_print_raw_values():
    # A: {"a":{"x":[["spring",1],["flower",1]]}}
    # B: {"a":{"x":3}}
    # normal(va) = normal([["spring",1],["flower",1]]), normal(vb) = 3
    # normal(va) != normal(vb) → listed
    # The line prints the RAW values as A and B gave them.
    # json.dumps([["spring",1],["flower",1]]) = '[["spring", 1], ["flower", 1]]'
    # json.dumps(3) = '3'
    # Expected line: 'a x: [["spring", 1], ["flower", 1]] vs 3'
    code_a = 'import json\nprint(json.dumps({"a": {"x": [["spring",1],["flower",1]]}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": 3}}))'
    gw = FakeGateway([("c1", f"```python\n{code_a}\n```"),
                      ("c2", f"```python\n{code_b}\n```")])
    result = facts.derive(gw, "rules", log=_log)
    assert result["facts"] is None
    assert result["reason"].startswith("disagree: ")
    # Expected raw va in line
    expected_a_str = json.dumps([["spring", 1], ["flower", 1]])
    # Expected raw vb in line
    expected_b_str = json.dumps(3)
    # Expected line: 'a x: [["spring", 1], ["flower", 1]] vs 3'
    expected_line = f"a x: {expected_a_str} vs {expected_b_str}"
    assert expected_line in result["reason"]


# ---------- 6: keep["a"] and keep["b"] stay raw ----------

def test_keep_a_b_are_raw_objects():
    # A: {"a":{"x":[["spring",1],["flower",1]]}}
    # B: {"a":{"x":[["flower",1],["spring",1]]}}
    # normal equal → agree, facts = normalized
    # keep["a"] = raw obj_a, keep["b"] = raw obj_b
    code_a = 'import json\nprint(json.dumps({"a": {"x": [["spring",1],["flower",1]]}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": [["flower",1],["spring",1]]}}))'
    gw = FakeGateway([("c1", f"```python\n{code_a}\n```"),
                      ("c2", f"```python\n{code_b}\n```")])
    keep = {}
    facts.derive(gw, "rules", log=_log, keep=keep)
    # Expected: keep["a"] is raw obj_a (spring first)
    # Expected: keep["b"] is raw obj_b (flower first)
    assert keep["a"] == {"a": {"x": [["spring", 1], ["flower", 1]]}}
    assert keep["b"] == {"a": {"x": [["flower", 1], ["spring", 1]]}}
    # Expected: keep["a"] != normal(obj_a)
    assert keep["a"] != facts.normal({"a": {"x": [["spring", 1], ["flower", 1]]}})


# ---------- 7: SYSTEM_A new line ----------

def test_system_a_has_new_line():
    new_line = "- When the rules allow several answers for one input, the value lists every one of them (for example every rotation that fits), never only the first."
    # Expected: the new sentence is in SYSTEM_A
    assert new_line in facts.SYSTEM_A


# ---------- 8: SYSTEM_B new line ----------

def test_system_b_has_new_line():
    new_line = "- When the rules allow several answers for one input, the value lists every one of them (for example every rotation that fits), never only the first."
    # Expected: the new sentence is in SYSTEM_B
    assert new_line in facts.SYSTEM_B


# ---------- 9: SYSTEM_A set line immediately followed by new line ----------

def test_system_a_set_line_before_new_line():
    set_line = "- A value that is a set is printed as a sorted list."
    new_line = "- When the rules allow several answers for one input, the value lists every one of them (for example every rotation that fits), never only the first."
    # Expected: set_line exists in SYSTEM_A
    assert set_line in facts.SYSTEM_A
    # Expected: new_line comes right after set_line
    lines = facts.SYSTEM_A.split("\n")
    # find index of set_line
    idx = [i for i, l in enumerate(lines) if set_line in l]
    assert len(idx) == 1
    # Expected: the next non-empty line is the new line
    next_idx = idx[0] + 1
    # skip empty lines
    while next_idx < len(lines) and lines[next_idx].strip() == "":
        next_idx += 1
    assert new_line in lines[next_idx]


# ---------- 10: SYSTEM_B set line immediately followed by new line ----------

def test_system_b_set_line_before_new_line():
    set_line = "- A value that is a set is printed as a sorted list."
    new_line = "- When the rules allow several answers for one input, the value lists every one of them (for example every rotation that fits), never only the first."
    # Expected: set_line exists in SYSTEM_B
    assert set_line in facts.SYSTEM_B
    # Expected: new_line comes right after set_line
    lines = facts.SYSTEM_B.split("\n")
    idx = [i for i, l in enumerate(lines) if set_line in l]
    assert len(idx) == 1
    # Expected: the next non-empty line is the new line
    next_idx = idx[0] + 1
    while next_idx < len(lines) and lines[next_idx].strip() == "":
        next_idx += 1
    assert new_line in lines[next_idx]


# ---------- 11: agree with nested dict values ----------

def test_agree_nested_dict_normal():
    # A: {"a":{"x":{"z":[[2],[1]]}}}
    # B: {"a":{"x":{"z":[[1],[2]]}}}
    # normal(obj_a): recurse "a" -> "x" -> "z" = [[2],[1]]
    #   all elements are lists → sort by json.dumps
    #   json.dumps([1]) = '[1]', json.dumps([2]) = '[2]'
    #   sorted: [[1],[2]]
    # normal(obj_a) = {"a":{"x":{"z":[[1],[2]]}}}
    # normal(obj_b) = {"a":{"x":{"z":[[1],[2]]}}}
    # Expected: agree, facts = {"a":{"x":{"z":[[1],[2]]}}}
    code_a = 'import json\nprint(json.dumps({"a":{"x":{"z":[[2],[1]]}}}))'
    code_b = 'import json\nprint(json.dumps({"a":{"x":{"z":[[1],[2]]}}}))'
    gw = FakeGateway([("c1", f"```python\n{code_a}\n```"),
                      ("c2", f"```python\n{code_b}\n```")])
    result = facts.derive(gw, "rules", log=_log)
    assert result["reason"] == "agree"
    # Expected facts = {"a": {"x": {"z": [[1], [2]]}}}
    assert result["facts"] == {"a": {"x": {"z": [[1], [2]]}}}


# ---------- 12: disagree pair listed when normal(va) != normal(vb) ----------

def test_disagree_pair_listed_normal_differs():
    # A: {"a":{"x":1}}, B: {"a":{"x":2}}
    # normal(1) = 1, normal(2) = 2 → not equal → listed
    # Expected: "a x: 1 vs 2" in reason
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b = 'import json\nprint(json.dumps({"a": {"x": 2}}))'
    gw = FakeGateway([("c1", f"```python\n{code_a}\n```"),
                      ("c2", f"```python\n{code_b}\n```")])
    result = facts.derive(gw, "rules", log=_log)
    # Expected: one line "a x: 1 vs 2"
    assert "a x: 1 vs 2" in result["reason"]
    # Expected: facts is None
    assert result["facts"] is None
