"""Tests for task plantests-js-unbound: js_unbound_calls strips comments, string literals and template
literals before scanning, and recognises method shorthand declarations (name(params) { inside an object
literal or class body) as declaring the name and its parameters.

Behaviour after the change:
  - text is cleaned: remove /* ... */ (non-greedy, multi-line), then // to end-of-line, then
    '...', "..." and `...` string literals (honouring backslash escapes);
  - method shorthand: a regex (\\w+)\\s*\\(([^)]*)\\)\\s*\\{ at an object/class-member position
    (preceded by {, comma, newline, start-of-object – NOT preceded by the word function)
    adds the name and every parameter name to the declared set;
  - the remaining code is scanned for identifier-call patterns;
  - names in declared / imported / keyword / global sets are skipped;
  - sorted unique names are returned.

Examples that must give []:
  - "// flow(grid) wets the spring"
  - test("click(state) after the win", () => {})
  - const ctx = { arc(x, y) { calls.push("arc"); }, fill() {} }  (arc, fill called as ctx.arc(1,2))
A call openings("corner", 1) in real code (never imported, never declared) still gives ["openings"].
"""

from stratos.plantests import js_unbound_calls


# ---- comment stripping ----

def test_comment_line_stripped():
    # Input: "// flow(grid) wets the spring"
    # After stripping // comment: empty string
    # No calls remain.
    # Expected: []
    assert js_unbound_calls("// flow(grid) wets the spring") == []


def test_block_comment_stripped():
    # Input: "/* flow(grid) */"
    # After stripping /* ... */: empty string
    # Expected: []
    assert js_unbound_calls("/* flow(grid) */") == []


def test_block_comment_multiline_stripped():
    # Input: "/* first\nflow(grid)\nlast */\n"
    # Non-greedy /* ... */ spanning lines removes the whole block
    # Remaining: "\n" → no calls
    # Expected: []
    text = "/* first\nflow(grid)\nlast */\n"
    assert js_unbound_calls(text) == []


# ---- string literal stripping ----

def test_single_quote_string_stripped():
    # Input: "test('foo(bar)', () => {})"
    # Strip single-quote string 'foo(bar)' → "test(, () => {})"
    # test is a global; no unbound calls
    # Expected: []
    text = "test('foo(bar)', () => {})"
    assert js_unbound_calls(text) == []


def test_double_quote_string_stripped():
    # Input: 'test("click(state) after the win", () => {})'
    # Strip double-quote string "click(state) after the win" → 'test(, () => {})'
    # test is a global
    # Expected: []
    text = 'test("click(state) after the win", () => {})'
    assert js_unbound_calls(text) == []


def test_template_literal_strips_inner_calls():
    # Input: 'const x = `hello ${openings(y)} world`;'
    # Strip the whole template literal (including ${...} parts) → 'const x = ;'
    # No calls remain (a missed call inside the template is accepted)
    # Expected: []
    text = 'const x = `hello ${openings(y)} world`;'
    assert js_unbound_calls(text) == []


def test_string_containing_call_pattern_stripped():
    # Input: 'foo("bar(baz)", x)'
    # Strip "bar(baz)" → 'foo(, x)'
    # foo( matches: foo is unbound; x is not followed by (
    # Expected: ["foo"]
    text = 'foo("bar(baz)", x)'
    assert js_unbound_calls(text) == ["foo"]


# ---- method shorthand ----

def test_method_shorthand_object_member():
    # Input: 'const ctx = { arc(x, y) { calls.push("arc"); }, fill() {} }'
    # Strip strings: "arc" removed
    # Method shorthand regex finds:
    #   arc after { → declares arc, x, y
    #   fill after , → declares fill
    # calls.push( → .push is a property call, excluded
    # No unbound calls
    # Expected: []
    text = 'const ctx = { arc(x, y) { calls.push("arc"); }, fill() {} }'
    assert js_unbound_calls(text) == []


def test_method_shorthand_params_declared():
    # Input: 'const o = { fn(a) { a(); } }'
    # Strip strings: none
    # fn after { → method shorthand, declares fn and a
    # a( matches: a is in declared → skip
    # Expected: []
    text = 'const o = { fn(a) { a(); } }'
    assert js_unbound_calls(text) == []


def test_method_shorthand_after_comma():
    # Input: '{ a() {}, b() {} }'
    # a after { → method shorthand, declares a
    # b after , → method shorthand, declares b
    # No unbound calls
    # Expected: []
    text = '{ a() {}, b() {} }'
    assert js_unbound_calls(text) == []


def test_method_shorthand_class_member():
    # Input: 'class C { m(x) { return x; } }'
    # m after { → method shorthand, declares m, x
    # x not followed by (
    # Expected: []
    text = 'class C { m(x) { return x; } }'
    assert js_unbound_calls(text) == []


def test_method_shorthand_not_after_function_keyword():
    # Input: 'const obj = { fn() {} }; function helper() {}'
    # fn after { → method shorthand, declares fn
    # helper preceded by function → NOT method shorthand;
    #   helper declared by existing function-regex (function helper)
    # No unbound calls
    # Expected: []
    text = 'const obj = { fn() {} }; function helper() {}'
    assert js_unbound_calls(text) == []


# ---- real unbound call ----

def test_real_call_with_string_arg_still_unbound():
    # Input: 'openings("corner", 1)'
    # Strip "corner" → 'openings(, 1)'
    # openings( matches: not imported, not declared, not keyword, not global
    # Expected: ["openings"]
    text = 'openings("corner", 1)'
    assert js_unbound_calls(text) == ["openings"]


# ---- call inside method shorthand body ----

def test_call_inside_method_shorthand_body():
    # Input: 'const o = { go() { unbound(); } }'
    # Strip strings: none
    # go after { → method shorthand, declares go
    # unbound( in the body: not declared, not imported, not keyword, not global
    # Expected: ["unbound"]
    text = 'const o = { go() { unbound(); } }'
    assert js_unbound_calls(text) == ["unbound"]


# ---- combined strips ----

def test_combined_strips():
    # Input:
    #   // unbound(a)\n
    #   /* foo(b) */\n
    #   const obj = { bar() {} };\n
    #   "baz(qux)"\n
    #   `quux(c)`\n
    #   openings(1);
    # After removing // comment: line 1 gone
    # After removing /* */: line 2 gone
    # After removing "baz(qux)": line 4 becomes empty
    # After removing `quux(c)`: line 5 becomes empty
    # Remaining code: 'const obj = { bar() {} };\n\n\nopenings(1);'
    # Method shorthand: bar after { → declares bar
    # openings( matches: unbound
    # bar is declared → skip
    # Expected: ["openings"]
    text = '// unbound(a)\n/* foo(b) */\nconst obj = { bar() {} };\n"baz(qux)"\n`quux(c)`\nopenings(1);'
    assert js_unbound_calls(text) == ["openings"]
