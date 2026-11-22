"""Tests for task checker_tool_prefix: strip tool-name prefix before re-parsing checker lines.

In stratos/checker.py, parse(output, root, paths): for a line that matches none of the existing
forms (_COLON, _PAREN, _GO), check whether the line starts with a token (word with no spaces)
followed by ": ". If so, strip that prefix and the ": " and run the existing form-matching on
the remainder. The result must be identical to the same line without the prefix.

Key case: "vet.exe: calc\\broken.go:3:14: expected ')'" yields the same result as
"calc\\broken.go:3:14: expected ')'" → "calc/broken.go:3: expected ')'".
"""

from pathlib import Path

from stratos import checker


# ─── the headline test from the task ────────────────────────────────────────────

def test_go_prefix_stripped_yields_same_as_bare():
    """The task's headline: "vet.exe: calc\\broken.go:3:14: expected ')'" == "calc\\broken.go:3:14: expected ')'"."""
    # Step: bare line "calc\\broken.go:3:14: expected ')'" → _GO matches.
    # file="calc\\broken.go", line="3", col="14", msg="expected ')'"
    # resolve against tmp_path → relpath → "calc\\broken.go" → replace backslashes → "calc/broken.go"
    # _TRAILING finds no bracket → msg stays "expected ')'"
    # output: "calc/broken.go:3: expected ')'"
    bare = "calc\\broken.go:3:14: expected ')'\n"
    # Step: prefixed line: starts with "vet.exe" (word, no spaces) + ": "
    # strip prefix → remainder is "calc\\broken.go:3:14: expected ')'" → _GO matches
    # resolve → "calc/broken.go" → msg "expected ')'"
    # output: "calc/broken.go:3: expected ')'"
    prefixed = "vet.exe: calc\\broken.go:3:14: expected ')'\n"
    assert checker.parse(prefixed, tmp_path, ["calc/broken.go"]) == checker.parse(bare, tmp_path, ["calc/broken.go"])


def test_go_prefix_file_not_in_paths(tmp_path):
    """A tool-prefixed Go line whose file is not in paths is dropped."""
    # Step: "vet.exe: pkg/a.go:1:2: undefined" → strip prefix → "pkg/a.go:1:2: undefined"
    # _GO matches → file="pkg/a.go" → relpath → "pkg/a.go"
    # wanted = {"pkg/b.go"} → "pkg/a.go" not in wanted → skip
    # output: []
    assert checker.parse("vet.exe: pkg/a.go:1:2: undefined\n", tmp_path, ["pkg/b.go"]) == []


# ─── tool prefix + _COLON form ──────────────────────────────────────────────────

def test_colon_form_with_tool_prefix(tmp_path):
    """"pyright.exe: pkg/user.py:1:23 - error: bad" → strip prefix → _COLON matches → "pkg/user.py:1: bad"."""
    # Step: line "pyright.exe: pkg/user.py:1:23 - error: bad"
    # _COLON on full line: file=".+?" → tries "pyright" → next char after ":" is "e" not digit → fails
    # _PAREN fails, _GO fails (no .go)
    # Tool prefix: "pyright.exe" (no spaces) + ": " → strip → "pkg/user.py:1:23 - error: bad"
    # _COLON: file="pkg/user.py", line="1", col optional="23", msg="bad"
    # resolve: tmp_path/pkg/user.py → relpath → "pkg/user.py"
    # output: "pkg/user.py:1: bad"
    got = checker.parse("pyright.exe: pkg/user.py:1:23 - error: bad\n", tmp_path, ["pkg/user.py"])
    # Step: expected output is the same as parsing "pkg/user.py:1:23 - error: bad"
    assert got == ["pkg/user.py:1: bad"]


def test_colon_form_without_prefix_unchanged(tmp_path):
    """A bare _COLON line is parsed directly; tool-prefix code does not fire."""
    # Step: "pkg/user.py:1:23 - error: bad" → _COLON matches directly.
    # file="pkg/user.py", line="1", msg="bad"
    # output: "pkg/user.py:1: bad"
    assert checker.parse("pkg/user.py:1:23 - error: bad\n", tmp_path, ["pkg/user.py"]) == ["pkg/user.py:1: bad"]


# ─── tool prefix + _PAREN form ──────────────────────────────────────────────────

def test_paren_form_with_tool_prefix(tmp_path):
    """"msbuild: src/Game.cs(12,5): error CS0103: bad" → strip → _PAREN matches → "src/Game.cs:12: CS0103: bad"."""
    # Step: line "msbuild: src/Game.cs(12,5): error CS0103: bad"
    # _COLON fails (no digit after first colon for "msbuild"), _PAREN fails on full line, _GO fails
    # Tool prefix: "msbuild" + ": " → strip → "src/Game.cs(12,5): error CS0103: bad"
    # _PAREN: file="src/Game.cs", line="12", msg="CS0103: bad"
    # resolve → "src/Game.cs"
    # _TRAILING: no bracket → msg "CS0103: bad"
    # output: "src/Game.cs:12: CS0103: bad"
    got = checker.parse("msbuild: src/Game.cs(12,5): error CS0103: bad\n", tmp_path, ["src/Game.cs"])
    assert got == ["src/Game.cs:12: CS0103: bad"]


# ─── tool prefix: token with dots ────────────────────────────────────────────────

def test_token_with_dots_stripped(tmp_path):
    """"vet.exe" (contains dots, no spaces) is stripped as a tool prefix."""
    # Step: "vet.exe: pkg/a.go:1:2: msg"
    # _COLON fails, _PAREN fails, _GO fails on full line?
    # Check _GO on full line: file=".+?\.go" non-greedy → "vet.exe: pkg/a.go" →
    #   after ".go" need ":" → next char is ":" → line="1", col="2", msg="msg"
    #   file="vet.exe: pkg/a.go" → resolve → relpath → weird → not in wanted
    #   So _GO matches the full line, file="vet.exe: pkg/a.go", relpath fails → skipped
    #   Result: [] — prefix NOT stripped because _GO already matched the full line.
    # Step: The prefix stripping fires only when NONE of _COLON/_PAREN/_GO match.
    # Use a file that _GO can't match on the full line.
    # "vet.exe: pkg/a.py:5:10: msg" → _GO needs .go → fails on full line
    # Tool prefix: "vet.exe" + ": " → strip → "pkg/a.py:5:10: msg"
    # _COLON: file="pkg/a.py", line="5", msg? "10: msg" → needs "error" → fails
    # _GO: needs .go → fails
    # output: []
    # Better test: use .go file where full-line _GO captures the prefix as part of file
    # "tool.exe: pkg/a.go:1:2: msg"
    # _GO on full line: .+?\.go non-greedy: "tool.exe: pkg/a.go" → file="tool.exe: pkg/a.go"
    #   relpath: tmp_path/tool.exe: pkg/a.go → ValueError → skip
    #   So _GO "matches" (the regex fires) but the line is dropped due to ValueError.
    #   Result: [] — NOT stripped because _GO matched.
    # This is fine; the feature says "matches none of the existing forms" fires the prefix check.
    # For the dots-in-token test, use a .py suffix so _GO can't fire on the full line.
    # Step: "vet.exe: pkg/a.py:1:23 - error: bad"
    # Full-line _COLON: "vet.exe" → file="vet" → "exe" not digit → fails. Good.
    # Full-line _PAREN, _GO: fail.
    # Tool prefix: "vet.exe" (no spaces, has dots) + ": " → strip.
    # "pkg/a.py:1:23 - error: bad" → _COLON → "pkg/a.py:1: bad"
    got = checker.parse("vet.exe: pkg/a.py:1:23 - error: bad\n", tmp_path, ["pkg/a.py"])
    # Step: prefix stripped, _COLON matches remainder
    assert got == ["pkg/a.py:1: bad"]


# ─── tool prefix + _GO form (main case with .go) ────────────────────────────────

def test_go_prefix_strip_on_dot_go_file(tmp_path):
    """"vet.exe: calc/broken.go:3:14: expected ')'" → strip → _GO on remainder → "calc/broken.go:3: expected ')'".
    This works because the full-line _GO regex's file capture includes "vet.exe: calc/broken.go"
    which is NOT in wanted, so the line is dropped. The prefix check fires because...
    Actually _GO matches the full line. So prefix stripping does NOT fire.
    Use a case where full-line _GO does NOT match: a .go file where the tool prefix
    causes _GO's file group to capture the prefix too.
    Step: "vet.exe: calc/broken.go:3:14: expected ')'"
    _GO: .+?\.go non-greedy → "vet.exe: calc/broken.go" → file includes prefix
    relpath(tmp_path/"vet.exe: calc/broken.go", tmp_path) → ValueError on colon?
    Actually os.path.relpath("tmp_path/vet.exe: calc/broken.go", tmp_path) → "vet.exe: calc/broken.go"
    → replace("\\","/") → "vet.exe: calc/broken.go" → not in wanted → line dropped
    So result is [] and prefix is NOT stripped.
    The task's headline example uses backslashes: "calc\\broken.go".
    Step: "vet.exe: calc\\broken.go:3:14: expected ')'"
    _GO on full line: .+?\.go non-greedy → "vet.exe: calc\\broken.go"
    resolve: os.path.join(root, "vet.exe: calc\\broken.go")
    relpath → "vet.exe: calc\\broken.go" → replace → "vet.exe: calc/broken.go"
    wanted = {"calc/broken.go"} → not in wanted → drop
    So the full-line _GO match is "successful" (regex fires) but line is dropped.
    Prefix stripping fires only when regex fires and line is dropped? No —
    the spec says "matches NONE of the existing forms". The regex fires, so the
    prefix stripping does NOT fire. This means the headline test as stated
    ("same result") requires the implementation to try prefix stripping when
    the full-line match produces a line that gets dropped (file not in wanted).

    Re-reading the spec: "for a line that matches none of the existing forms".
    If _GO matches the full line (regex fires), prefix stripping does NOT fire.
    So "vet.exe: calc\\broken.go:3:14: expected ')'" → _GO fires on full line
    → file="vet.exe: calc\\broken.go" → not in wanted → dropped → [].
    This does NOT give the same result as the bare line.

    The task says: "a line that matches none of the forms but starts with a word
    without spaces followed by ': '". So the prefix stripping fires when NO form
    matches the full line. For "vet.exe: calc\\broken.go:3:14: expected ')'"
    _GO DOES match the full line (the regex fires), so prefix stripping does NOT fire.

    Therefore the task's headline assertion "same result" requires the implementation
    to also strip the prefix when the full-line match is dropped (file not in wanted).
    OR the implementation tries prefix stripping on lines where the regex fires
    but the result is dropped. Let me assume the task means: the implementation
    strips the prefix and re-tries all three forms, and the existing parse logic
    handles both cases. The headline test is the required behaviour.

    For this test, assert the task's headline directly.
    """
    # Step: prefixed line
    prefixed = "vet.exe: calc\\broken.go:3:14: expected ')'\n"
    # Step: bare line
    bare = "calc\\broken.go:3:14: expected ')'\n"
    # Step: both should produce the same output when calc/broken.go is in paths.
    result_pref = checker.parse(prefixed, tmp_path, ["calc/broken.go"])
    result_bare = checker.parse(bare, tmp_path, ["calc/broken.go"])
    # Step: both yield ["calc/broken.go:3: expected ')'"]
    assert result_pref == result_bare
    # Step: the bare line gives "calc/broken.go:3: expected ')'"
    assert result_bare == ["calc/broken.go:3: expected ')'"]


def test_prefix_line_dropped_file_not_in_paths(tmp_path):
    """When the prefix is stripped and the remainder's file is not in paths, result is []."""
    # Step: "vet.exe: calc\\broken.go:3:14: msg" → strip → "calc\\broken.go:3:14: msg"
    # _GO matches remainder → file "calc\\broken.go" → relpath → "calc/broken.go"
    # wanted = {"other.go"} → not in wanted → drop
    # output: []
    assert checker.parse("vet.exe: calc\\broken.go:3:14: msg\n", tmp_path, ["other.go"]) == []


# ─── tool prefix: colon without space is NOT a tool prefix ──────────────────────

def test_colon_no_space_not_a_prefix(tmp_path):
    """"tool:x" — colon not followed by space → not a tool prefix → line matches no form → []."""
    # Step: "tool:x:1:2: msg"
    # _COLON, _PAREN, _GO all fail on full line.
    # Tool prefix regex ^\S+:\s → "tool:" then ":" not space → no match.
    # Prefix not stripped → line matches no form → []
    # Step: output is []
    assert checker.parse("tool:x:1:2: msg\n", tmp_path, ["x.py"]) == []


def test_colon_then_non_space_not_a_prefix(tmp_path):
    """"tool:a.py:1:23 - error: bad" — colon then non-space → not stripped → []."""
    # Step: "tool:a.py:1:23 - error: bad"
    # _COLON on full line: file=".+?" → "tool" → next ":" then line must be digit
    #   after "tool:" is "a.py:1:23 - error: bad" → "a" not digit → fails
    # Tool prefix: ^\S+:\s → "tool:a.py" — colon not followed by space → no
    # output: []
    assert checker.parse("tool:a.py:1:23 - error: bad\n", tmp_path, ["a.py"]) == []


# ─── tool prefix + trailing bracket ─────────────────────────────────────────────

def test_prefix_and_trailing_bracket(tmp_path):
    """Tool prefix stripped, _COLON matches, trailing "[proj]" cut by _TRAILING."""
    # Step: "msbuild: src/a.py(12,5): error CS0103: bad [src.csproj]"
    # Full-line _PAREN: file=".+?" → "msbuild: src/a.py" (non-greedy)
    #   After first "(12,5)" → msg="error CS0103: bad [src.csproj]"
    #   file="msbuild: src/a.py" → relpath → "msbuild: src/a.py" → not in wanted → drop
    #   _PAREN matched → prefix stripping does NOT fire.
    # Use .cs paren form that _PAREN matches on full line...
    # Better: "tool.exe: src/Game.cs(12,5): error CS0103: bad [src.csproj]"
    # Full-line _PAREN: file=".+?" → "tool.exe: src/Game.cs" → relpath → not in wanted → drop
    # Prefix stripping does NOT fire.
    # Use .py so _PAREN doesn't match the full line file pattern...
    # Actually _PAREN matches any file pattern. The regex fires; the file is dropped.
    # The task says prefix stripping fires when NONE of the forms match.
    # If the regex fires, prefix stripping does NOT fire.
    # For trailing bracket test, use a form where the full-line regex truly fails.
    # "tool.exe: pkg/a.py:1:23 - error: bad [proj]"
    # Full-line _COLON: "tool" then "exe" not digit → fails.
    # _PAREN, _GO fail.
    # Prefix: "tool.exe" + ": " → strip → "pkg/a.py:1:23 - error: bad [proj]"
    # _COLON: file="pkg/a.py", line="1", msg="bad [proj]"
    # _TRAILING.sub("", "bad [proj]") → "bad"
    # output: "pkg/a.py:1: bad"
    got = checker.parse("tool.exe: pkg/a.py:1:23 - error: bad [proj]\n", tmp_path, ["pkg/a.py"])
    assert got == ["pkg/a.py:1: bad"]


# ─── multiple lines: prefix on one, bare on the other ───────────────────────────

def test_mixed_prefix_and_bare_lines(tmp_path):
    """A tool-prefixed line and a bare line in the same output both parse correctly."""
    # Step: line1 "vet.exe: pkg/a.go:2:3: msg1" → strip → "pkg/a.go:2:3: msg1" → _GO
    #   file="pkg/a.go", line="2", msg="msg1" → "pkg/a.go:2: msg1"
    # Step: line2 "pkg/b.go:1:1: msg2" → _GO directly
    #   file="pkg/b.go", line="1", msg="msg2" → "pkg/b.go:1: msg2"
    # sorted set: ["pkg/a.go:2: msg1", "pkg/b.go:1: msg2"]
    #   "pkg/b.go" < "pkg/a.go"? "b" < "a"? No, "a" < "b". So sorted:
    #   ["pkg/a.go:2: msg1", "pkg/b.go:1: msg2"]
    out = "vet.exe: pkg/a.go:2:3: msg1\npkg/b.go:1:1: msg2\n"
    got = checker.parse(out, tmp_path, ["pkg/a.go", "pkg/b.go"])
    # Step: sorted by path; "pkg/a.go" < "pkg/b.go"
    assert got == ["pkg/a.go:2: msg1", "pkg/b.go:1: msg2"]


# ─── dedup: prefixed line and its bare counterpart merge ────────────────────────

def test_dedup_prefix_and_bare(tmp_path):
    """The same error written once with a tool prefix and once bare → one output entry."""
    # Step: "tool.exe: pkg/a.go:1:2: msg" → strip → "pkg/a.go:1:2: msg" → "pkg/a.go:1: msg"
    # Step: "pkg/a.go:1:2: msg" → _GO directly → "pkg/a.go:1: msg"
    # set dedup → one entry
    # sorted: ["pkg/a.go:1: msg"]
    out = "tool.exe: pkg/a.go:1:2: msg\npkg/a.go:1:2: msg\n"
    got = checker.parse(out, tmp_path, ["pkg/a.go"])
    # Step: both produce "pkg/a.go:1: msg" → set has one element
    assert got == ["pkg/a.go:1: msg"]


# ─── prefix: token is the whole line (no remainder after ": ") ──────────────────

def test_prefix_is_whole_line(tmp_path):
    """"tool.exe: " — the line is just the prefix; remainder is empty → no match → []."""
    # Step: line "tool.exe: " (prefix + colon + space, nothing after)
    # Full-line _COLON, _PAREN, _GO: all fail.
    # Tool prefix: "tool.exe" + ": " → strip → ""
    # "" matches no form → skip
    # output: []
    assert checker.parse("tool.exe: \n", tmp_path, ["a.py"]) == []


# ─── prefix on a line that already matches _COLON: prefix NOT stripped ──────────

def test_no_prefix_strip_when_form_already_matches(tmp_path):
    """A line matching _COLON directly is parsed as-is; prefix stripping does NOT fire."""
    # Step: "pkg/a.py:1:23 - error: bad" → _COLON matches → "pkg/a.py:1: bad"
    # Even though the file "pkg/a.py" contains ": " inside it, the line
    # is consumed by _COLON, so prefix stripping is not applied.
    # Step: output
    got = checker.parse("pkg/a.py:1:23 - error: bad\n", tmp_path, ["pkg/a.py"])
    assert got == ["pkg/a.py:1: bad"]


# ─── prefix stripping only applied once (not repeated) ──────────────────────────

def test_single_prefix_strip(tmp_path):
    """Only the first "word: " is stripped; the remainder is re-parsed once."""
    # Step: "a.exe: b.exe: pkg/a.go:1:2: msg"
    # Full line: _GO .+?\.go → file="a.exe: b.exe: pkg/a.go" → relpath → not in wanted → drop
    # Prefix fires? _GO matched the full line (regex fires). So NO.
    # Use .py: "a.exe: b.exe: pkg/a.py:1:23 - error: bad"
    # _COLON on full line: "a" → "exe" not digit → fails. _PAREN, _GO fail.
    # Tool prefix: "a.exe" + ": " → strip → "b.exe: pkg/a.py:1:23 - error: bad"
    # Re-match: _COLON on remainder: "b" → "exe" not digit → fails. _PAREN, _GO fail.
    # Prefix check on remainder: "b.exe" + ": " → strip?
    # The task says "strip that prefix and the ': ' and run the existing
    # form-matching on the remainder" — one strip only, then form-matching.
    # After one strip, we run form-matching. No second prefix check.
    # "b.exe: pkg/a.py:1:23 - error: bad" → _COLON fails → output [].
    # Step:
    # assert checker.parse(...) == []
    out = "a.exe: b.exe: pkg/a.py:1:23 - error: bad\n"
    got = checker.parse(out, tmp_path, ["pkg/a.py"])
    # Step: first prefix stripped, remainder re-parsed; second prefix NOT stripped
    assert got == []
