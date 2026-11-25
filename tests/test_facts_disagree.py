"""Tests for task facts-disagree: derive's disagree reason format and the keep/a/b fields.

derive(gw, rules, log=print, keep=None) -> {"facts": ..., "reason": ...}

Disagree format (new):
  - Keys present in both objects with equal values are NEVER listed.
  - Key in only one object → null on the missing side.
  - Fact name in only one object → "<name>: only in A" or "<name>: only in B".
  - At most 5 lines, sorted by name and key.

keep dict (new):
  - keep["a"] = obj_a printed by A (None if A failed or did not run).
  - keep["b"] = obj_b printed by B (None if B failed or did not run).

Result dict stays exactly {"facts": ..., "reason": ...} (old tests compare ==).
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
    """Build a gateway answer containing a ```python block that prints obj as JSON."""
    # json.dumps(obj) gives the JSON literal embedded in the code
    code = 'import json\nprint(json.dumps(' + json.dumps(obj) + '))'
    return f"```python\n{code}\n```"


# 1 – key present in both with equal values is never listed
def test_equal_key_values_never_listed():
    # A = {"a": {"x": 1, "y": 2}}, B = {"a": {"x": 1, "y": 3}}
    # json.dumps(1) = "1", json.dumps(2) = "2", json.dumps(3) = "3"
    # key x: A=1 B=1 → equal → skip
    # key y: A=2 B=3 → differ → line "a y: 2 vs 3"
    # Lines: ["a y: 2 vs 3"]
    # reason = "disagree: a y: 2 vs 3"
    gw = FakeGateway([("c1", _code_answer({"a": {"x": 1, "y": 2}})),
                      ("c2", _code_answer({"a": {"x": 1, "y": 3}}))])
    result = facts.derive(gw, "rules", log=_log)
    assert result["facts"] is None
    # expected: 1 line, no "a x" anywhere
    lines = result["reason"].replace("disagree: ", "").split("\n")
    assert len(lines) == 1
    # json.dumps(2) = "2", json.dumps(3) = "3" → "a y: 2 vs 3"
    assert lines[0] == "a y: 2 vs 3"
    # "a x" must not appear (equal values are never listed)
    assert "a x" not in result["reason"]


# 2 – key in A only → null on B side
def test_key_only_in_a_null_on_b_side():
    # A = {"a": {"x": 1, "y": 2}}, B = {"a": {"x": 1}}
    # x: 1 vs 1 → skip
    # y: A=2, B=None → key in A only → line "a y: 2 vs null"
    # json.dumps(2) = "2", json.dumps(None) = "null"
    # Lines: ["a y: 2 vs null"]
    gw = FakeGateway([("c1", _code_answer({"a": {"x": 1, "y": 2}})),
                      ("c2", _code_answer({"a": {"x": 1}}))])
    result = facts.derive(gw, "rules", log=_log)
    lines = result["reason"].replace("disagree: ", "").split("\n")
    assert len(lines) == 1
    # expected: "a y: 2 vs null"
    assert lines[0] == "a y: 2 vs null"


# 3 – key in B only → null on A side
def test_key_only_in_b_null_on_a_side():
    # A = {"a": {"x": 1}}, B = {"a": {"x": 1, "y": 2}}
    # x: 1 vs 1 → skip
    # y: A=None, B=2 → line "a y: null vs 2"
    # json.dumps(None) = "null", json.dumps(2) = "2"
    # Lines: ["a y: null vs 2"]
    gw = FakeGateway([("c1", _code_answer({"a": {"x": 1}})),
                      ("c2", _code_answer({"a": {"x": 1, "y": 2}}))])
    result = facts.derive(gw, "rules", log=_log)
    lines = result["reason"].replace("disagree: ", "").split("\n")
    assert len(lines) == 1
    # expected: "a y: null vs 2"
    assert lines[0] == "a y: null vs 2"


# 4 – fact name present in A only → "only in A"
def test_fact_name_only_in_a():
    # A = {"a": {"x": 1}, "b": {"z": 3}}, B = {"a": {"x": 1}}
    # sorted names: ["a", "b"]
    # a: keys ["x"], 1 vs 1 → skip
    # b: only in A → line "b: only in A" (one line, not per-key)
    # Lines: ["b: only in A"]
    gw = FakeGateway([("c1", _code_answer({"a": {"x": 1}, "b": {"z": 3}})),
                      ("c2", _code_answer({"a": {"x": 1}}))])
    result = facts.derive(gw, "rules", log=_log)
    lines = result["reason"].replace("disagree: ", "").split("\n")
    assert len(lines) == 1
    # expected: "b: only in A"
    assert lines[0] == "b: only in A"
    # no key-level line for b
    assert "b z" not in result["reason"]


# 5 – fact name present in B only → "only in B"
def test_fact_name_only_in_b():
    # A = {"a": {"x": 1}}, B = {"a": {"x": 1}, "b": {"z": 3}}
    # sorted names: ["a", "b"]
    # a: x: 1 vs 1 → skip
    # b: only in B → "b: only in B"
    # Lines: ["b: only in B"]
    gw = FakeGateway([("c1", _code_answer({"a": {"x": 1}})),
                      ("c2", _code_answer({"a": {"x": 1}, "b": {"z": 3}}))])
    result = facts.derive(gw, "rules", log=_log)
    lines = result["reason"].replace("disagree: ", "").split("\n")
    assert len(lines) == 1
    # expected: "b: only in B"
    assert lines[0] == "b: only in B"


# 6 – at most 5 lines
def test_at_most_5_lines():
    # 6 facts f0..f5, each key "k": 1 vs 9
    # sorted: f0,f1,f2,f3,f4,f5 → 6 disagreements
    # only first 5 lines kept: f0,f1,f2,f3,f4
    # json.dumps(1) = "1", json.dumps(9) = "9"
    # Lines: "f0 k: 1 vs 9", "f1 k: 1 vs 9", ..., "f4 k: 1 vs 9"
    obj_a = {f"f{i}": {"k": 1} for i in range(6)}
    obj_b = {f"f{i}": {"k": 9} for i in range(6)}
    gw = FakeGateway([("c1", _code_answer(obj_a)),
                      ("c2", _code_answer(obj_b))])
    result = facts.derive(gw, "rules", log=_log)
    lines = result["reason"].replace("disagree: ", "").split("\n")
    # expected: len == 5 (6 disagreements exist, 5 lines kept)
    assert len(lines) == 5
    # first line: "f0 k: 1 vs 9"
    assert lines[0] == "f0 k: 1 vs 9"
    # last line: "f4 k: 1 vs 9"
    assert lines[4] == "f4 k: 1 vs 9"
    # f5 must not appear
    assert "f5" not in result["reason"]


# 7 – sorted by name and key
def test_sorted_by_name_and_key():
    # A = {"b": {"x": 1, "a": 2}, "a": {"z": 3, "y": 4}}
    # B = {"b": {"x": 2, "a": 2}, "a": {"z": 3, "y": 5}}
    # sorted names: ["a", "b"]
    # a: keys sorted ["y", "z"]: y 4 vs 5 → line; z 3 vs 3 → skip
    # b: keys sorted ["a", "x"]: a 2 vs 2 → skip; x 1 vs 2 → line
    # Lines: "a y: 4 vs 5", "b x: 1 vs 2"
    # reason = "disagree: a y: 4 vs 5\nb x: 1 vs 2"
    obj_a = {"b": {"x": 1, "a": 2}, "a": {"z": 3, "y": 4}}
    obj_b = {"b": {"x": 2, "a": 2}, "a": {"z": 3, "y": 5}}
    gw = FakeGateway([("c1", _code_answer(obj_a)),
                      ("c2", _code_answer(obj_b))])
    result = facts.derive(gw, "rules", log=_log)
    # json.dumps(4) = "4", json.dumps(5) = "5", json.dumps(1) = "1", json.dumps(2) = "2"
    # expected reason:
    expected_reason = "disagree: a y: 4 vs 5\nb x: 1 vs 2"
    # step: name "a" < "b" (sorted); key "y" < "z" within a; "a" < "x" within b
    assert result["reason"] == expected_reason


# 8 – keep on agree
def test_keep_on_agree():
    # A = {"a": {"x": 1}}, B = {"a": {"x": 1}} → agree
    # keep["a"] = {"a": {"x": 1}}, keep["b"] = {"a": {"x": 1}}
    obj = {"a": {"x": 1}}
    gw = FakeGateway([("c1", _code_answer(obj)),
                      ("c2", _code_answer(obj))])
    keep = {}
    result = facts.derive(gw, "rules", log=_log, keep=keep)
    assert result["reason"] == "agree"
    # expected: keep["a"] == obj, keep["b"] == obj
    assert keep["a"] == {"a": {"x": 1}}
    assert keep["b"] == {"a": {"x": 1}}


# 9 – keep on disagree
def test_keep_on_disagree():
    # A = {"a": {"x": 1}}, B = {"a": {"x": 2}} → disagree
    # keep["a"] = {"a": {"x": 1}}, keep["b"] = {"a": {"x": 2}}
    gw = FakeGateway([("c1", _code_answer({"a": {"x": 1}})),
                      ("c2", _code_answer({"a": {"x": 2}}))])
    keep = {}
    result = facts.derive(gw, "rules", log=_log, keep=keep)
    # expected: keep["a"] == {"a": {"x": 1}}
    assert keep["a"] == {"a": {"x": 1}}
    # expected: keep["b"] == {"a": {"x": 2}}
    assert keep["b"] == {"a": {"x": 2}}


# 10 – keep["a"] None when program A crashes
def test_keep_a_none_when_a_crashes():
    # A code: raise Exception → run_program → None → repair asks once more, crashes again → "program A failed"
    # B is never run → keep["b"] = None
    code_a = 'raise Exception("boom")'
    answer_a = f"```python\n{code_a}\n```"
    gw = FakeGateway([("c1", answer_a), ("c2", answer_a)])
    keep = {}
    result = facts.derive(gw, "rules", log=_log, keep=keep)
    # expected: result == {"facts": None, "reason": "program A failed"}
    assert result == {"facts": None, "reason": "program A failed"}
    # expected: keep["a"] is None (A failed)
    assert keep["a"] is None
    # expected: keep["b"] is None (B never ran)
    assert keep["b"] is None


# 11 – keep["b"] None when program B crashes
def test_keep_b_none_when_b_crashes():
    # A prints {"a": {"x": 1}} (success), B crashes → repair asks once more, crashes again
    # keep["a"] = {"a": {"x": 1}}, keep["b"] = None
    code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    code_b = 'raise Exception("boom")'
    gw = FakeGateway([("c1", f"```python\n{code_a}\n```"),
                      ("c2", f"```python\n{code_b}\n```"),
                      ("c3", f"```python\n{code_b}\n```")])
    keep = {}
    result = facts.derive(gw, "rules", log=_log, keep=keep)
    # expected: result == {"facts": None, "reason": "program B failed"}
    assert result == {"facts": None, "reason": "program B failed"}
    # expected: keep["a"] == {"a": {"x": 1}} (A ran successfully)
    assert keep["a"] == {"a": {"x": 1}}
    # expected: keep["b"] is None (B crashed)
    assert keep["b"] is None


# 12 – keep["a"] None when A prints NONE
def test_keep_a_none_when_a_returns_none():
    # Model A answers the single word "NONE" → reason "none"
    # keep["a"] = None (no program ran), keep["b"] = None (B never ran)
    gw = FakeGateway([("c1", "NONE")])
    keep = {}
    result = facts.derive(gw, "rules", log=_log, keep=keep)
    # expected: result == {"facts": None, "reason": "none"}
    assert result == {"facts": None, "reason": "none"}
    # expected: keep["a"] is None
    assert keep["a"] is None
    # expected: keep["b"] is None
    assert keep["b"] is None


# 13 – result dict has exactly "facts" and "reason" keys
def test_result_dict_keys_only_facts_and_reason():
    # Agree case with keep dict provided; result must have no extra keys
    obj = {"a": {"x": 1}}
    gw = FakeGateway([("c1", _code_answer(obj)),
                      ("c2", _code_answer(obj))])
    keep = {}
    result = facts.derive(gw, "rules", log=_log, keep=keep)
    # expected: keys == {"facts", "reason"}
    assert set(result.keys()) == {"facts", "reason"}


# 14 – multiple facts "only in A" as single lines per fact name
def test_multiple_facts_only_in_a_lines():
    # A = {"x": {"k": 1}, "y": {"k": 2}, "z": {"k": 3}}
    # B = {"x": {"k": 1}}
    # sorted names: ["x", "y", "z"]
    # x: k: 1 vs 1 → skip
    # y: only in A → "y: only in A"
    # z: only in A → "z: only in A"
    # Lines: ["y: only in A", "z: only in A"] (sorted y < z)
    obj_a = {"x": {"k": 1}, "y": {"k": 2}, "z": {"k": 3}}
    obj_b = {"x": {"k": 1}}
    gw = FakeGateway([("c1", _code_answer(obj_a)),
                      ("c2", _code_answer(obj_b))])
    result = facts.derive(gw, "rules", log=_log)
    lines = result["reason"].replace("disagree: ", "").split("\n")
    # expected: 2 lines
    assert len(lines) == 2
    # expected: "y: only in A" then "z: only in A"
    assert lines[0] == "y: only in A"
    assert lines[1] == "z: only in A"
