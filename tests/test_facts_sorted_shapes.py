"""Tests for task t001: fact_shapes prefixes "sorted " to list-of-string/integer/number shapes
when every value in the group equals sorted(value) and at least one value has 2+ elements.
SYSTEM_B gains one line after the value-shape rule.

fact_shapes(obj) changes:
  - For each fact, compute value_shape for every value, group by shape.
  - For shapes exactly "list of string", "list of integer", "list of number":
    if ALL values in group == sorted(value) AND at least one value has len >= 2:
      rename shape to "sorted " + shape.
  - Otherwise the shape stays unchanged.
  - Result per fact is the sorted list of distinct (possibly renamed) shapes.
  - No other shape string is ever prefixed. value_shape itself does not change.

SYSTEM_B new line (immediately after "- Every value must have exactly the value shape..."):
  "- A value shape that starts with 'sorted' is a list in ascending order: sort it before printing."

OUTDATED: tests/test_facts_shapes.py::test_system_b_has_value_shape_rule_before_last_line -
  that test checks the anchor line is before the last line; the new line is inserted AFTER
  the anchor, so the anchor is no longer the last rule line. The test checks index of anchor
  vs index of last line; the new line sits between them, so anchor index < last line index
  is still true. The test remains valid.
"""

from stratos import facts


# ---------- fact_shapes: sorted list of string ----------

def test_sorted_list_of_string_all_sorted_one_len2():
    # obj = {"a": {"x": ["e", "n"], "y": ["n"]}}
    # x: ["e","n"] -> value_shape = "list of string"; sorted(["e","n"]) = ["e","n"] -> equal
    # y: ["n"] -> value_shape = "list of string"; sorted(["n"]) = ["n"] -> equal
    # All values in the "list of string" group equal sorted(value) -> True
    # At least one has len >= 2: ["e","n"] has len 2 -> True
    # Rename to "sorted list of string"
    # Result: {"a": ["sorted list of string"]}
    obj = {"a": {"x": ["e", "n"], "y": ["n"]}}
    result = facts.fact_shapes(obj)
    assert result == {"a": ["sorted list of string"]}


# ---------- fact_shapes: unsorted list of string ----------

def test_unsorted_list_of_string_stays():
    # obj = {"a": {"x": ["n", "e"], "y": ["e", "n"]}}
    # x: ["n","e"] -> shape "list of string"; sorted = ["e","n"] != ["n","e"] -> not sorted
    # y: ["e","n"] -> shape "list of string"; sorted = ["e","n"] == ["e","n"] -> sorted
    # NOT all values are sorted -> no rename
    # Result: {"a": ["list of string"]}
    obj = {"a": {"x": ["n", "e"], "y": ["e", "n"]}}
    result = facts.fact_shapes(obj)
    assert result == {"a": ["list of string"]}


# ---------- fact_shapes: single element per group (no len >= 2) ----------

def test_single_element_group_no_rename():
    # obj = {"a": {"x": ["n"], "y": []}}
    # x: ["n"] -> shape "list of string"; sorted(["n"]) = ["n"] -> sorted; len 1 < 2
    # y: [] -> shape "list" (empty list special case)
    # Group "list of string": values [["n"]]; all sorted -> True; at least one len>=2 -> False
    # No rename. Group "list": values [[]]; "list" is not one of the three -> no rename.
    # Result: {"a": ["list", "list of string"]}
    obj = {"a": {"x": ["n"], "y": []}}
    result = facts.fact_shapes(obj)
    # "list" < "list of string" alphabetically
    assert result == {"a": ["list", "list of string"]}


# ---------- fact_shapes: sorted list of integer ----------

def test_sorted_list_of_integer():
    # obj = {"a": {"x": [1, 2], "y": "s"}}
    # x: [1,2] -> shape "list of integer"; sorted([1,2]) = [1,2] -> sorted; len 2 >= 2
    # y: "s" -> shape "string"
    # Group "list of integer": all sorted, one len>=2 -> rename to "sorted list of integer"
    # Result: {"a": ["sorted list of integer", "string"]}
    obj = {"a": {"x": [1, 2], "y": "s"}}
    result = facts.fact_shapes(obj)
    # "sorted list of integer" < "string" alphabetically
    assert result == {"a": ["sorted list of integer", "string"]}


# ---------- fact_shapes: sorted list of number ----------

def test_sorted_list_of_number():
    # obj = {"a": {"x": [1.5, 2.0]}}
    # x: [1.5, 2.0] -> shape "list of number"; sorted = [1.5, 2.0] -> sorted; len 2 >= 2
    # Rename to "sorted list of number"
    # Result: {"a": ["sorted list of number"]}
    obj = {"a": {"x": [1.5, 2.0]}}
    result = facts.fact_shapes(obj)
    assert result == {"a": ["sorted list of number"]}


# ---------- fact_shapes: only the three shapes can be sorted ----------

def test_non_list_of_three_stays():
    # obj = {"a": {"x": [["b", 1], ["a", 1]]}}
    # x: [["b",1],["a",1]] -> inner: ["b",1] shapes string,integer -> "list [string, integer]"
    #     both inner have same shape -> "list of list [string, integer]"
    # This is NOT one of the three shapes, so no rename.
    # Result: {"a": ["list of list [string, integer]"]}
    obj = {"a": {"x": [["b", 1], ["a", 1]]}}
    result = facts.fact_shapes(obj)
    assert result == {"a": ["list of list [string, integer]"]}


# ---------- fact_shapes: all values len 1, no rename ----------

def test_all_values_len1_no_rename():
    # obj = {"a": {"x": ["a"], "y": ["b"], "z": ["c"]}}
    # Each value is shape "list of string", sorted, len 1
    # All sorted -> True; at least one len>=2 -> False (all len 1)
    # No rename
    # Result: {"a": ["list of string"]}
    obj = {"a": {"x": ["a"], "y": ["b"], "z": ["c"]}}
    result = facts.fact_shapes(obj)
    assert result == {"a": ["list of string"]}


# ---------- fact_shapes: multiple facts, one sorted one not ----------

def test_multiple_facts_independent():
    # obj = {"a": {"x": ["e", "n"]}, "b": {"k": ["n", "e"]}}
    # Fact "a": x=["e","n"] -> "list of string", sorted=True, len=2 -> rename
    # Fact "b": k=["n","e"] -> "list of string", sorted=False -> no rename
    # Result: {"a": ["sorted list of string"], "b": ["list of string"]}
    obj = {"a": {"x": ["e", "n"]}, "b": {"k": ["n", "e"]}}
    result = facts.fact_shapes(obj)
    assert result["a"] == ["sorted list of string"]
    assert result["b"] == ["list of string"]


# ---------- fact_shapes: group with multiple values all sorted ----------

def test_group_multiple_all_sorted():
    # obj = {"a": {"x": [1, 3], "y": [2, 5, 7], "z": [4]}}
    # x: [1,3] -> "list of integer", sorted=True, len 2
    # y: [2,5,7] -> "list of integer", sorted=True, len 3
    # z: [4] -> "list of integer", sorted=True, len 1
    # All sorted -> True; at least one len>=2 -> True (x has len 2)
    # Rename to "sorted list of integer"
    # Result: {"a": ["sorted list of integer"]}
    obj = {"a": {"x": [1, 3], "y": [2, 5, 7], "z": [4]}}
    result = facts.fact_shapes(obj)
    assert result == {"a": ["sorted list of integer"]}


# ---------- fact_shapes: one sorted one unsorted in same group ----------

def test_group_one_unsorted_blocks_rename():
    # obj = {"a": {"x": [1, 3], "y": [5, 2]}}
    # x: [1,3] -> "list of integer", sorted=True
    # y: [5,2] -> "list of integer", sorted([5,2])=[2,5] != [5,2] -> sorted=False
    # NOT all values sorted -> no rename
    # Result: {"a": ["list of integer"]}
    obj = {"a": {"x": [1, 3], "y": [5, 2]}}
    result = facts.fact_shapes(obj)
    assert result == {"a": ["list of integer"]}


# ---------- value_shape does not change ----------

def test_value_shape_unchanged():
    # value_shape must still return the original shape strings (no "sorted " prefix).
    # ["e", "n"] -> "list of string" (not "sorted list of string")
    assert facts.value_shape(["e", "n"]) == "list of string"
    # [1, 2] -> "list of integer"
    assert facts.value_shape([1, 2]) == "list of integer"
    # [1.5, 2.0] -> "list of number"
    assert facts.value_shape([1.5, 2.0]) == "list of number"
    # [] -> "list"
    assert facts.value_shape([]) == "list"
    # "s" -> "string"
    assert facts.value_shape("s") == "string"


# ---------- SYSTEM_B: new line present ----------

def test_system_b_sorted_line_present():
    # The exact new line must appear in SYSTEM_B:
    new_line = "- A value shape that starts with 'sorted' is a list in ascending order: sort it before printing."
    # Expected: the exact string is in SYSTEM_B
    assert new_line in facts.SYSTEM_B


# ---------- SYSTEM_B: new line immediately after anchor ----------

def test_system_b_sorted_line_after_anchor():
    anchor = "- Every value must have exactly the value shape given for its fact (for a list, the same order of elements)."
    new_line = "- A value shape that starts with 'sorted' is a list in ascending order: sort it before printing."
    lines = facts.SYSTEM_B.split("\n")
    # Expected: anchor appears exactly once
    idx = [i for i, l in enumerate(lines) if anchor in l]
    assert len(idx) == 1
    # step: advance past any empty lines
    next_idx = idx[0] + 1
    while next_idx < len(lines) and lines[next_idx].strip() == "":
        next_idx += 1
    # Expected: the next non-empty line is the new_line
    assert lines[next_idx] == new_line


# ---------- SYSTEM_B: anchor line still present ----------

def test_system_b_anchor_still_present():
    anchor = "- Every value must have exactly the value shape given for its fact (for a list, the same order of elements)."
    # Expected: the anchor line is still in SYSTEM_B
    assert anchor in facts.SYSTEM_B


# ---------- SYSTEM_B: new line uses single quotes exactly ----------

def test_system_b_sorted_line_single_quotes():
    # The line uses single quotes as written: 'sorted'
    new_line = "- A value shape that starts with 'sorted' is a list in ascending order: sort it before printing."
    # Expected: 'sorted' (with surrounding single quotes) is in the line
    assert "'sorted'" in new_line
    # Expected: the line starts with "- A value shape"
    assert new_line.startswith("- A value shape")
