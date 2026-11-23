"""Tests for task P025_js_getter_setter: js_unbound_calls recognizes get/set property
declarations. Inside an object literal or class body, "get name() {" and "set name(v) {"
declare name and treat v as a parameter. The words get and set are recognized as this form
only when preceded by {, a comma, a newline, or whitespace at the start of a member line.
A bare identifier (not preceded by get/set in that position) is still an unbound call.
"get fillStyle(" without the closing paren is NOT recognized as the getter form
(the getter pattern requires get + name + empty parens + { ).
"""

from stratos.plantests import js_unbound_calls


def test_getter_inside_object_yields_empty():
    # Input: const canvas = { get fillStyle() { return "#fff"; } };
    # Strip double-quote string "#fff" → const canvas = { get fillStyle() { return  } };
    # const → declares canvas
    # Getter pattern: { (prefix) + get + space + fillStyle + empty parens + { → declares fillStyle
    # return is a keyword
    # No identifier matches call pattern as unbound
    # Expected: []
    text = 'const canvas = { get fillStyle() { return "#fff"; } };'
    assert js_unbound_calls(text) == []


def test_setter_declares_name_and_param():
    # Input: const c = { set fillStyle(v) { this.color = v; } };
    # No strings/comments to strip
    # const → declares c
    # Setter pattern: { (prefix) + set + space + fillStyle + (v) + { → declares fillStyle, v as param
    # this, color not followed by (
    # Expected: []
    text = 'const c = { set fillStyle(v) { this.color = v; } };'
    assert js_unbound_calls(text) == []


def test_getter_without_closing_paren_not_recognized():
    # Input: { get fillStyle( { } }
    # Getter pattern requires get + name + ( + ) + {  (empty parens).
    #   Here: get fillStyle( — no closing ) → getter NOT matched
    # Method shorthand: fillStyle( — prefix before fillStyle is space after "get",
    #   not { , comma, newline → NOT matched
    # Call pattern: fillStyle( matches → fillStyle is unbound
    # Expected: ["fillStyle"]
    text = '{ get fillStyle( { } }'
    assert js_unbound_calls(text) == ["fillStyle"]


def test_getter_after_comma():
    # Input: { a() {}, get fillStyle() {} }
    # Method shorthand: a after { → declares a
    # Getter pattern: get after , (prefix ", ") → declares fillStyle
    # No unbound calls
    # Expected: []
    text = '{ a() {}, get fillStyle() {} }'
    assert js_unbound_calls(text) == []


def test_getter_after_newline():
    # Input: const o = {\n  get fillStyle() {}\n}
    # const → declares o
    # Getter pattern: get after \n  (prefix \n\s*) → declares fillStyle
    # Expected: []
    text = 'const o = {\n  get fillStyle() {}\n}'
    assert js_unbound_calls(text) == []


def test_getter_in_class_body():
    # Input: class Canvas { get fillStyle() {} }
    # class → declares Canvas
    # Getter pattern: get after { → declares fillStyle
    # Expected: []
    text = 'class Canvas { get fillStyle() {} }'
    assert js_unbound_calls(text) == []


def test_setter_after_comma():
    # Input: { get x() {}, set y(v) {} }
    # Getter: get after { → declares x
    # Setter: set after , → declares y, declares v as param
    # Expected: []
    text = '{ get x() {}, set y(v) {} }'
    assert js_unbound_calls(text) == []


def test_get_not_at_member_position():
    # Input: const obj = get; get fillStyle() {}
    # const → declares obj
    # First "get": bare identifier, not followed by ( → no call
    # Second "get fillStyle() {}": prefix before get is "; " (semicolon+space),
    #   NOT { , comma, newline → getter NOT matched
    #   fillStyle( matches call pattern → unbound
    # Expected: ["fillStyle"]
    text = 'const obj = get; get fillStyle() {}'
    assert js_unbound_calls(text) == ["fillStyle"]


def test_setter_empty_parens_not_recognized():
    # Input: { set fillStyle() {} }
    # Setter pattern requires set + name + (param) + {  — params must be non-empty
    #   Empty parens () → NOT matched as setter
    #   Getter pattern: only "get" keyword → NOT matched
    #   Method shorthand: prefix before fillStyle is space after "set",
    #   not { , comma, newline → NOT matched
    #   fillStyle( matches call pattern → unbound
    # Expected: ["fillStyle"]
    text = '{ set fillStyle() {} }'
    assert js_unbound_calls(text) == ["fillStyle"]


def test_getter_declares_name_for_calls_outside():
    # Input: const c = { get fillStyle() {} }; fillStyle();
    # const → declares c
    # Getter: get fillStyle() { → declares fillStyle
    # fillStyle() outside → fillStyle is in declared set → skip
    # Expected: []
    text = 'const c = { get fillStyle() {} }; fillStyle();'
    assert js_unbound_calls(text) == []


def test_getter_and_setter_together():
    # Input: const o = { get x() {}, set y(v) {} }; x(); y(); v();
    # const → declares o
    # get x() {} → declares x
    # set y(v) {} → declares y, declares v
    # x(), y(), v() → all declared → skip
    # Expected: []
    text = 'const o = { get x() {}, set y(v) {} }; x(); y(); v();'
    assert js_unbound_calls(text) == []


def test_getter_spaces_in_empty_parens():
    # Input: const o = { get fillStyle( ) {} };
    # Getter: get + space + fillStyle + ( + space + ) + space + { → matches (empty parens
    #   allow internal whitespace) → declares fillStyle
    # Expected: []
    text = 'const o = { get fillStyle( ) {} };'
    assert js_unbound_calls(text) == []


def test_setter_param_used_as_call():
    # Input: const o = { set fillStyle(v) { v(); } };
    # Setter: set fillStyle(v) { → declares fillStyle, declares v
    # v() in body → v is declared → skip
    # Expected: []
    text = 'const o = { set fillStyle(v) { v(); } };'
    assert js_unbound_calls(text) == []


def test_bare_fillStyle_without_get_set_is_unbound():
    # Input: fillStyle();
    # fillStyle( matches call pattern
    # Not declared, not imported, not keyword, not global
    # Expected: ["fillStyle"]
    text = 'fillStyle();'
    assert js_unbound_calls(text) == ["fillStyle"]


def test_get_as_method_shorthand_not_confused_with_getter():
    # Input: const o = { get(x) {} };
    # Getter pattern requires get + space + name + empty parens:
    #   "get(x)" has no space between get and ( → getter NOT matched
    # Method shorthand: prefix { matches → "get(x) {" → declares get, declares x
    # No unbound calls
    # Expected: []
    text = 'const o = { get(x) {} };'
    assert js_unbound_calls(text) == []
