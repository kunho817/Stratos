"""Tests for task js_unbound_calls: add "of" and "import" to the keyword/skip set,
and strip JavaScript regular-expression literals before scanning for calls.

Changes to js_unbound_calls(text):
  (a) "of" is added to the keyword/skip set → "for (const x of (list))" is not a call of "of".
  (b) "import" is added to the keyword/skip set → "await import(...)" is not a call of "import".
  (c) Regex literals are stripped before scanning. A "/" starts a regex when the last
      non-whitespace character before it is one of ( , = : [ ! & | ? { } ; , start-of-text,
      or the word "return". The literal ends at the next unescaped "/" not inside a [...]
      character class, then trailing flags (a-z letters) are consumed. The literal (including
      flags) is replaced by a single space.
  After stripping, scan for name( patterns, skipping keywords (now including "of" and "import"),
  globals, imported names, declared names. Return sorted unbound names.

Examples giving []:
  for (const n of (adj.get(node) || [])) {}
  await import("../src/main.js")
  const m = text.match(/Level (\d+) of 50/);
A real call openings("corner", 1) with openings never imported gives ["openings"],
even on a line after a regex.
"""

from stratos.plantests import js_unbound_calls


def test_of_keyword_skipped_in_for_of():
    # Input: "for (const n of (adj.get(node) || [])) {}"
    # Strip comments/strings: none. Strip regexes: no "/" → nothing.
    # Scan calls:
    #   "for(" → "for" is keyword → skip
    #   "of(" → "of" is keyword (new) → skip
    #   ".get(" → property call → skip
    #   "node" not followed by "(", "[]" no calls
    # Expected: []
    text = 'for (const n of (adj.get(node) || [])) {}'
    assert js_unbound_calls(text) == []


def test_import_keyword_skipped_in_dynamic_import():
    # Input: 'await import("../src/main.js")'
    # Strip strings: "../src/main.js" → removed → 'await import()'
    # Scan calls:
    #   "await(" → "await" is keyword → skip
    #   "import(" → "import" is keyword (new) → skip
    # Expected: []
    text = 'await import("../src/main.js")'
    assert js_unbound_calls(text) == []


def test_regex_stripped_after_paren():
    # Input: r"const m = text.match(/Level (\d+) of 50/);"
    # Strip strings: none.
    # Regex scan: first "/" after "(" in "match(" → "(" is in prefix set → regex starts.
    #   Content scan: "Level (\d+) of 50" → next unescaped "/" not inside [...] → closing "/".
    #   No flags. Replace "/Level (\d+) of 50/" with space.
    #   Result: "const m = text.match( );"
    # Scan calls: ".match(" is property call → skip.
    # Expected: []
    text = r'const m = text.match(/Level (\d+) of 50/);'
    assert js_unbound_calls(text) == []


def test_real_call_on_line_after_regex():
    # Input: 'const m = text.match(/Level (\d+) of 50/);\nopenings("corner", 1);'
    # Strip strings: "corner" → removed.
    # Regex: "/" after "(" in "match(" → regex starts.
    #   Content "Level (\d+) of 50", closing "/" → strip → space.
    #   Result: "const m = text.match( );\nopenings(, 1);"
    # Scan: "openings(" → not keyword, not global, not imported, not declared → unbound.
    # Expected: ["openings"]
    text = 'const m = text.match(/Level (\d+) of 50/);\nopenings("corner", 1);'
    assert js_unbound_calls(text) == ["openings"]


def test_regex_after_return_keyword():
    # Input: "return /abc/.test(s);"
    # Last non-whitespace before "/" is "return" → regex starts.
    #   Content "abc", closing "/" → strip "/abc/" → space.
    #   Result: "return .test(s);"
    # ".test(" is property call → skip.
    # Expected: []
    text = 'return /abc/.test(s);'
    assert js_unbound_calls(text) == []


def test_regex_at_start_of_text():
    # Input: "/pattern/.test(x)"
    # "/" at start of text → regex starts.
    #   Content "pattern", closing "/" → strip → " .test(x)"
    # ".test(" is property call → skip.
    # Expected: []
    text = '/pattern/.test(x)'
    assert js_unbound_calls(text) == []


def test_division_not_regex():
    # Input: "x = a / b;"
    # Last non-whitespace before "/" is "a" → not in prefix set → not a regex.
    # No regex stripping. No identifier followed by "(".
    # Expected: []
    text = 'x = a / b;'
    assert js_unbound_calls(text) == []


def test_regex_char_class():
    # Input: r"const re = /[\/]/;"
    # Strip strings: none.
    # Regex: "/" after "=" → prefix set includes "=" → regex starts.
    #   Scan: "[" opens char class; "\/" inside class (escaped); "]" closes class;
    #   "/" after "]" terminates.
    #   Strip "/[\/]/" → "const re = ;"
    # Expected: []
    text = r'const re = /[\/]/;'
    assert js_unbound_calls(text) == []


def test_regex_escaped_slash():
    # Input: r"const re = /a\/b/;"
    # Regex: "/" after "=" → regex starts.
    #   Scan: "a"; "\/" escaped (skip); "b"; "/" not escaped, not in class → terminates.
    #   Strip "/a\/b/" → "const re = ;"
    # Expected: []
    text = r'const re = /a\/b/;'
    assert js_unbound_calls(text) == []


def test_regex_with_flags():
    # Input: "const re = /abc/gi;"
    # Regex: "/" after "=" → regex starts.
    #   Content "abc", closing "/" → strip "/abc/"; then flags "gi" (a-z letters) consumed.
    #   Strip "/abc/gi" → "const re = ;"
    # Expected: []
    text = 'const re = /abc/gi;'
    assert js_unbound_calls(text) == []


def test_of_followed_by_paren():
    # Input: "of(x)"
    # "of(" matches the call pattern, but "of" is now in the keyword set → skip.
    # Expected: []
    text = 'of(x)'
    assert js_unbound_calls(text) == []


def test_import_followed_by_paren():
    # Input: "import(x)"
    # "import(" matches the call pattern, but "import" is now in the keyword set → skip.
    # Expected: []
    text = 'import(x)'
    assert js_unbound_calls(text) == []


def test_regex_and_string_and_call_combined():
    # Input: 'const a = x.match(/a/);\nconst b = y.match(/b/g);\nopenings("x");'
    # Strip strings: "x" → removed.
    # Regexes:
    #   "/a/" after "(" in "match(" → strip.
    #   "/b/g" after "(" → strip, flag "g" consumed.
    #   Result: "const a = x.match( );\nconst b = y.match( );\nopenings();"
    # "openings(" → unbound. ".match(" → property call.
    # Expected: ["openings"]
    text = 'const a = x.match(/a/);\nconst b = y.match(/b/g);\nopenings("x");'
    assert js_unbound_calls(text) == ["openings"]


def test_regex_after_semicolon():
    # Input: "let x = 1; /abc/.test(y);"
    # Last non-whitespace before "/" is ";" → ";" in prefix set → regex starts.
    #   Content "abc", closing "/" → strip → "let x = 1; .test(y);"
    # ".test(" is property call → skip.
    # Expected: []
    text = 'let x = 1; /abc/.test(y);'
    assert js_unbound_calls(text) == []
