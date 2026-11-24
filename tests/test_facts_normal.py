"""Tests for stratos/facts.py: normal(v) normalization function.

normal(v) returns a new value without changing the input:
- dict -> dict with same keys, normal() applied to each value
- list -> normal() applied to each element; then if list has >=1 element
  AND every element is a list or dict, sort elements by
  json.dumps(element, sort_keys=True); otherwise keep order
- scalar (int, str, float, bool, None) -> returned as-is

Examples:
  normal([["spring",1],["flower",1]]) == [["flower",1],["spring",1]]
  normal(["n","e"]) == ["n","e"]
  normal([{"r":2},{"r":1}]) == [{"r":1},{"r":2}]
  normal({"x":[[2],[1]]}) == {"x":[[1],[2]]}
  normal([]) == []
  normal(["a",[1]]) == ["a",[1]]

OUTDATED: tests/test_facts.py::test_derive_agree_checks_gateway_calls -
  derive now compares normal(obj_a) == normal(obj_b) instead of obj_a == obj_b;
  tests that assert obj_a == obj_b for agreement must use normal().
OUTDATED: tests/test_facts.py::test_derive_disagree -
  disagree now uses normal() for equality checks; a pair whose normal() values
  are equal is never listed.
"""

import json

from stratos import facts


# ---------- 1: scalar passthrough ----------

def test_normal_scalar_int():
    # normal(42) returns 42
    assert facts.normal(42) == 42


def test_normal_scalar_string():
    # normal("hello") returns "hello"
    assert facts.normal("hello") == "hello"


def test_normal_scalar_float():
    # normal(3.14) returns 3.14
    assert facts.normal(3.14) == 3.14


def test_normal_scalar_none():
    # normal(None) returns None
    assert facts.normal(None) is None


def test_normal_scalar_bool():
    # normal(True) returns True, normal(False) returns False
    assert facts.normal(True) is True
    assert facts.normal(False) is False


# ---------- 2: empty list ----------

def test_normal_empty_list():
    # normal([]) == []
    assert facts.normal([]) == []


# ---------- 3: list of scalars keeps order ----------

def test_normal_list_of_strings():
    # ["n","e"] - every element is a string (scalar), so keep order
    # Expected: ["n","e"]
    assert facts.normal(["n", "e"]) == ["n", "e"]


def test_normal_list_of_numbers():
    # [5, 1, 3] - every element is a number (scalar), so keep order
    # Expected: [5, 1, 3]
    assert facts.normal([5, 1, 3]) == [5, 1, 3]


# ---------- 4: list of all lists -> sorted ----------

def test_normal_list_of_lists_sorted():
    # [["spring",1],["flower",1]] - every element is a list, so sort
    # json.dumps(["flower",1], sort_keys=True) == '["flower", 1]'
    # json.dumps(["spring",1], sort_keys=True) == '["spring", 1]'
    # '["flower", 1]' < '["spring", 1]' so sorted order is flower, spring
    # Expected: [["flower", 1], ["spring", 1]]
    result = facts.normal([["spring", 1], ["flower", 1]])
    assert result == [["flower", 1], ["spring", 1]]


def test_normal_list_of_lists_single():
    # [[2]] - one element, it is a list, so sorted trivially
    # Expected: [[2]]
    assert facts.normal([[2]]) == [[2]]


def test_normal_list_of_lists_reverse_sort():
    # [[3], [1], [2]] - all elements are lists, sort by json.dumps
    # json.dumps([1]) = '[1]', json.dumps([2]) = '[2]', json.dumps([3]) = '[3]'
    # sorted: [1], [2], [3]
    # Expected: [[1], [2], [3]]
    assert facts.normal([[3], [1], [2]]) == [[1], [2], [3]]


# ---------- 5: list of all dicts -> sorted ----------

def test_normal_list_of_dicts_sorted():
    # [{"r":2},{"r":1}] - every element is a dict, so sort
    # json.dumps({"r":1}, sort_keys=True) == '{"r": 1}'
    # json.dumps({"r":2}, sort_keys=True) == '{"r": 2}'
    # '{"r": 1}' < '{"r": 2}' so sorted order is r:1, r:2
    # Expected: [{"r":1}, {"r":2}]
    assert facts.normal([{"r": 2}, {"r": 1}]) == [{"r": 1}, {"r": 2}]


# ---------- 6: mixed list (scalar + list) keeps order ----------

def test_normal_mixed_list_keeps_order():
    # ["a",[1]] - "a" is a string (not list/dict), [1] is a list
    # not every element is list-or-dict, so keep order
    # Expected: ["a", [1]]
    assert facts.normal(["a", [1]]) == ["a", [1]]


def test_normal_mixed_list_number_and_dict():
    # [1, {"x": 2}] - 1 is scalar, {"x":2} is dict
    # not every element is list-or-dict, so keep order
    # Expected: [1, {"x": 2}]
    assert facts.normal([1, {"x": 2}]) == [1, {"x": 2}]


# ---------- 7: dict recursion ----------

def test_normal_dict_with_list_value():
    # {"x": [[2],[1]]} - recurse into "x", which is [[2],[1]]
    # [[2],[1]]: every element is a list -> sort
    # json.dumps([1]) = '[1]', json.dumps([2]) = '[2]'
    # sorted: [[1],[2]]
    # Expected: {"x": [[1], [2]]}
    assert facts.normal({"x": [[2], [1]]}) == {"x": [[1], [2]]}


def test_normal_dict_with_scalar_values():
    # {"a": 1, "b": "hello"} - scalars returned as-is
    # Expected: {"a": 1, "b": "hello"}
    assert facts.normal({"a": 1, "b": "hello"}) == {"a": 1, "b": "hello"}


def test_normal_dict_with_dict_value():
    # {"x": {"z": 2, "y": 1}} - recurse into inner dict
    # inner dict: values are scalars, keys stay same
    # Expected: {"x": {"z": 2, "y": 1}}
    result = facts.normal({"x": {"z": 2, "y": 1}})
    # dict keys are preserved, values normalized (scalars stay)
    assert result == {"x": {"z": 2, "y": 1}}


# ---------- 8: input immutability ----------

def test_normal_does_not_mutate_input():
    # original list must not change after calling normal
    original = [["spring", 1], ["flower", 1]]
    original_copy = [["spring", 1], ["flower", 1]]
    facts.normal(original)
    # Expected: original unchanged
    assert original == original_copy


def test_normal_does_not_mutate_dict():
    # original dict must not change
    original = {"x": [[2], [1]]}
    original_copy = {"x": [[2], [1]]}
    facts.normal(original)
    # Expected: original unchanged
    assert original == original_copy


# ---------- 9: new objects at every level ----------

def test_normal_returns_new_list():
    # result is not the same object as input
    v = [1, 2, 3]
    r = facts.normal(v)
    # Expected: r is v (equal) but not the same object
    assert r == v
    assert r is not v


def test_normal_returns_new_dict():
    # result is not the same object as input
    v = {"a": 1}
    r = facts.normal(v)
    # Expected: r == v but not the same object
    assert r == v
    assert r is not v


def test_normal_nested_returns_new_inner_objects():
    # nested list elements must be new objects too
    v = [[1], [2]]
    r = facts.normal(v)
    # Expected: inner lists are new objects
    assert r[0] is not v[0]
    assert r[1] is not v[1]
    # Expected: r == [[1], [2]]
    assert r == [[1], [2]]


# ---------- 10: deeply nested ----------

def test_normal_deeply_nested():
    # {"x": [{"r": 2}, {"r": 1}]}
    # recurse into "x": [{"r":2},{"r":1}] -> all dicts -> sort
    # json.dumps({"r":1}, sort_keys=True) = '{"r": 1}'
    # json.dumps({"r":2}, sort_keys=True) = '{"r": 2}'
    # sorted: [{"r":1}, {"r":2}]
    # Expected: {"x": [{"r":1}, {"r":2}]}
    assert facts.normal({"x": [{"r": 2}, {"r": 1}]}) == {"x": [{"r": 1}, {"r": 2}]}


def test_normal_list_of_dicts_with_list_values():
    # [{"b":[2]},{"a":[1]}] - every element is a dict, so sort
    # After recursing: [{"b":[2]},{"a":[1]}] (inner lists: single element, sorted trivially)
    # json.dumps({"a":[1]}, sort_keys=True) = '{"a": [1]}'
    # json.dumps({"b":[2]}, sort_keys=True) = '{"b": [2]}'
    # '{"a": [1]}' < '{"b": [2]}'
    # Expected: [{"a":[1]}, {"b":[2]}]
    result = facts.normal([{"b": [2]}, {"a": [1]}])
    assert result == [{"a": [1]}, {"b": [2]}]


# ---------- 11: list with all dicts (dicts of dicts) ----------

def test_normal_list_of_nested_dicts():
    # [{"b":{"z":1}},{"a":{"z":2}}]
    # every element is dict -> sort
    # recurse each: inner dicts have scalar values, no sorting
    # json.dumps({"a":{"z":2}}, sort_keys=True) = '{"a": {"z": 2}}'
    # json.dumps({"b":{"z":1}}, sort_keys=True) = '{"b": {"z": 1}}'
    # '{"a": {"z": 2}}' < '{"b": {"z": 1}}'
    # Expected: [{"a":{"z":2}}, {"b":{"z":1}}]
    result = facts.normal([{"b": {"z": 1}}, {"a": {"z": 2}}])
    assert result == [{"a": {"z": 2}}, {"b": {"z": 1}}]


# ---------- 12: list of booleans (scalars, keep order) ----------

def test_normal_list_of_booleans():
    # [True, False, True] - all scalars, keep order
    # Expected: [True, False, True]
    assert facts.normal([True, False, True]) == [True, False, True]
