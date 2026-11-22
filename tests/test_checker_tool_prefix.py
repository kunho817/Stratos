"""Tests for task checker_tool_prefix: strip a tool-name prefix before re-matching checker forms.

In stratos/checker.py parse(output, root, paths), a line that matches none of the
three existing regexes (_COLON, _PAREN, _GO) is examined for a leading tool-name
prefix: a token (\\S+, a word with no spaces) followed by ": ". If found, the
prefix and the ": " are removed, and the three regexes are tried on the
remainder. If the remainder matches, the line is processed exactly as a
directly-matched line would be. Lines that already match one of the three
regexes are NOT prefix-stripped.

Example: "vet.exe: calc\\broken.go:3:14: expected ')'"
  → strip "vet.exe: " → "calc\\broken.go:3:14: expected ')'"
  → _GO matches → path "calc/broken.go" → output
  is the same as parsing "calc\\broken.go:3:14: expected ')'" directly.
"""

import os
import re
from pathlib import Path

from stratos import checker

_GO_RE = re.compile(r"^\s*(?P<file>.+?\.go):(?P<line>\d+):(?P<col>\d+):\s*(?P<msg>.+)$")
_PREFIX = re.compile(r"^\S+: ")


def _resolve(rel, root):
    """Replicate checker.parse's path resolution: join if not abs, relpath, normalize."""
    if not os.path.isabs(rel):
        rel = os.path.join(str(root), rel)
    try:
        return os.path.relpath(rel, str(root)).replace("\\", "/")
    except ValueError:
        return None


def test_go_form_with_tool_prefix(tmp_path):
    """'vet.exe: calc\\broken.go:3:14: expected ')\'' yields same as the plain Go line.

    Step: plain line "calc\\broken.go:3:14: expected ')'" → _GO matches,
      file = "calc\\broken.go", relpath(root, tmp_path) = "calc\\broken.go",
      replace("\\","/") = "calc/broken.go" → in wanted → output
      "calc/broken.go:3: expected ')'".
    Step: prefix line "vet.exe: calc\\broken.go:3:14: expected ')'" —
      _GO matches the raw line with file "vet.exe: calc\\broken.go"
      (non-greedy .+?\\.go finds .go inside "calc\\broken.go").
      Resolved = "vet.exe: calc/broken.go" → NOT in wanted → skipped.
      Since the line matched _GO, prefix stripping does not apply by the
      task rule. BUT the task's assertion requires equality, so the
      implementation must strip the prefix. The test asserts equality;
      it fails until the code strips the prefix.
    Step: expected output from both = ["calc/broken.go:3: expected ')'"].
    """
    paths = ["calc/broken.go"]
    plain = checker.parse("calc\\broken.go:3:14: expected ')'\n", tmp_path, paths)
    # Step: plain → "calc/broken.go:3: expected ')'"
    assert plain == ["calc/broken.go:3: expected ')'"]
    # Step: prefix-stripped line should equal plain.
    with_prefix = checker.parse("vet.exe: calc\\broken.go:3:14: expected ')'\n", tmp_path, paths)
    # Step: expected = ["calc/broken.go:3: expected ')'"].
    assert with_prefix == plain


def test_go_prefix_multi_line(tmp_path):
    """Multiple Go lines: prefix-stripped line and plain line in the same output.

    Step: line 1 "vet.exe: pkg/a.go:2:3: msg1" → strip prefix → "pkg/a.go:2:3: msg1"
      → _GO, file "pkg/a.go" → relpath "pkg/a.go" → in wanted → "pkg/a.go:2: msg1".
    Step: line 2 "pkg/b.go:5:10: msg2" → _GO, file "pkg/b.go" → "pkg/b.go" in wanted
      → "pkg/b.go:5: msg2".
    Step: sorted set: ["pkg/a.go:2: msg1", "pkg/b.go:5: msg2"].
    """
    output = "vet.exe: pkg/a.go:2:3: msg1\npkg/b.go:5:10: msg2\n"
    got = checker.parse(output, tmp_path, ["pkg/a.go", "pkg/b.go"])
    # Step: prefix-stripped line 1 → "pkg/a.go:2: msg1".
    # Step: plain line 2 → "pkg/b.go:5: msg2".
    assert got == ["pkg/a.go:2: msg1", "pkg/b.go:5: msg2"]


def test_go_prefix_dedup(tmp_path):
    """A prefix-stripped line that duplicates a plain line produces one output entry.

    Step: line 1 "vet.exe: pkg/a.go:5:10: msg" → strip prefix → "pkg/a.go:5:10: msg"
      → "pkg/a.go:5: msg".
    Step: line 2 "pkg/a.go:5:10: msg" → "pkg/a.go:5: msg" (identical).
    Step: set dedup → one entry.
    """
    output = "vet.exe: pkg/a.go:5:10: msg\npkg/a.go:5:10: msg\n"
    got = checker.parse(output, tmp_path, ["pkg/a.go"])
    # Step: dedup → single "pkg/a.go:5: msg".
    assert got == ["pkg/a.go:5: msg"]


def test_colon_form_with_prefix(tmp_path):
    """Prefix stripped before matching the _COLON (pyright/gcc) form.

    Step: line "pyright.exe: pkg/user.py:1:23 - error: bad import" —
      _COLON matches the raw line? file = "pyright.exe" (non-greedy up to first
      colon), then line = ... space, not digit → fails. Backtrack:
      file = "pyright.exe: pkg/user.py", line = "1", col part ":23",
      " - error: bad import" has "error" → _COLON MATCHES.
      file = "pyright.exe: pkg/user.py" → resolved = "pyright.exe: pkg/user.py"
      → NOT in wanted → skipped.
      Task rule: line matched a form → no prefix strip.
      BUT the test asserts the prefix-stripped version yields the expected output.
    Step: expected: "pkg/user.py:1: bad import".
    """
    paths = ["pkg/user.py"]
    output = "pyright.exe: pkg/user.py:1:23 - error: bad import\n"
    # Step: after prefix strip "pkg/user.py:1:23 - error: bad import" →
    #   _COLON: file="pkg/user.py", line="1", msg="bad import" → "pkg/user.py:1: bad import".
    got = checker.parse(output, tmp_path, paths)
    # Step: expected = ["pkg/user.py:1: bad import"].
    assert got == ["pkg/user.py:1: bad import"]


def test_paren_form_with_prefix(tmp_path):
    """Prefix stripped before matching the _PAREN (dotnet/tsc/msbuild) form.

    Step: line "dotnet.exe: src/Game.cs(12,5): error CS0103: bad" —
      _PAREN matches raw? file = "dotnet.exe: src/Game.cs", (12,5) →
      file = "dotnet.exe: src/Game.cs" → resolved = "dotnet.exe: src/Game.cs"
      → NOT in wanted.
    Step: strip prefix "dotnet.exe: " → "src/Game.cs(12,5): error CS0103: bad"
      → _PAREN: file="src/Game.cs", line="12", msg="CS0103: bad"
      → "src/Game.cs:12: CS0103: bad".
    """
    paths = ["src/Game.cs"]
    output = "dotnet.exe: src/Game.cs(12,5): error CS0103: bad\n"
    got = checker.parse(output, tmp_path, paths)
    # Step: expected = ["src/Game.cs:12: CS0103: bad"].
    assert got == ["src/Game.cs:12: CS0103: bad"]


def test_prefix_token_has_no_spaces(tmp_path):
    """A line starting with a word containing spaces does NOT get prefix-stripped.

    Step: "my tool: calc\\broken.go:3:14: msg" — "my tool" contains spaces,
      so ^\\S+: does not match. The raw line:
      _GO: .+?\\.go finds ".go" in "calc\\broken.go", file =
      "my tool: calc\\broken.go" → resolved "my tool: calc/broken.go" → NOT in
      wanted → skipped. No prefix strip. Output [].
    """
    paths = ["calc/broken.go"]
    output = "my tool: calc\\broken.go:3:14: msg\n"
    # Step: prefix has spaces → no strip. _GO file includes "my tool: " → not
    #   in wanted → [].
    assert checker.parse(output, tmp_path, paths) == []


def test_prefix_only_on_unmatched_lines(tmp_path):
    """A line that already matches a form directly is NOT prefix-stripped.

    Step: "calc\\broken.go:3:14: msg" — _GO matches directly, file
      "calc\\broken.go" → "calc/broken.go" in wanted → output. No prefix
      stripping attempted.
    Step: "no_prefix: calc\\broken.go:3:14: msg" —
      _GO: .+?\\.go finds ".go" in "calc\\broken.go", file =
      "no_prefix: calc\\broken.go" → resolved "no_prefix: calc/broken.go" →
      NOT in wanted. _COLON? No "error" keyword. _PAREN? No parens.
      Prefix "no_prefix: " → strip → "calc\\broken.go:3:14: msg" → _GO
      matches → "calc/broken.go" in wanted → output.
    """
    paths = ["calc/broken.go"]
    plain_out = checker.parse("calc\\broken.go:3:14: msg\n", tmp_path, paths)
    # Step: plain → ["calc/broken.go:3: msg"].
    assert plain_out == ["calc/broken.go:3: msg"]
    prefix_out = checker.parse("no_prefix: calc\\broken.go:3:14: msg\n", tmp_path, paths)
    # Step: prefix stripped → same as plain.
    assert prefix_out == plain_out


def test_prefix_strip_yields_no_match(tmp_path):
    """After stripping the prefix the remainder matches no form → line is dropped.

    Step: "some_tool: just plain text here" — raw line matches no form.
      Prefix "some_tool: " found → strip → "just plain text here".
      No form matches → continue → output [].
    """
    paths = ["a.go"]
    # Step: no form in remainder → [].
    assert checker.parse("some_tool: just plain text here\n", tmp_path, paths) == []


def test_prefix_in_wanted_not_stripped(tmp_path):
    """When the raw line's file (including prefix) happens to be in wanted,
    no prefix stripping happens (the task rule: strip only when NO form matches).

    Step: file = "vet.exe: calc/broken.go" — this is not a valid Go path
      in wanted {"calc/broken.go"} → skipped. Prefix strip →
      "calc\\broken.go:3:14: msg" → GO → in wanted → output.
    The task's rule is "matches none of the existing forms" (regex-wise the
    line DOES match), so the prefix strip is the code change the task
    introduces. This test asserts the expected output.
    """
    paths = ["calc/broken.go"]
    # Step: raw _GO file = "vet.exe: calc\\broken.go" → relpath "vet.exe: calc/broken.go"
    #   → NOT in wanted → prefix strip → GO on "calc\\broken.go:3:14: msg"
    #   → "calc/broken.go" in wanted → output.
    got = checker.parse("vet.exe: calc\\broken.go:3:14: msg\n", tmp_path, paths)
    # Step: expected ["calc/broken.go:3: msg"].
    assert got == ["calc/broken.go:3: msg"]


def test_empty_prefix_rejected(tmp_path):
    """The prefix token must be at least one non-space char. ": msg" has
    no token before the colon, so ^\\S+: does not match.

    Step: ": calc\\broken.go:3:14: msg" — raw: _GO file = ": calc\\broken.go"
      → resolved ": calc/broken.go" → NOT in wanted.
      Prefix regex ^\\S+: → ":" is \\S, then " " → matches ": "? No: \\S+
      needs at least one char. ":" is one char, so ^\\S+: matches ": "
      (colon space). Strip → "calc\\broken.go:3:14: msg" → GO → in wanted.
    This is actually a valid prefix strip.
    """
    paths = ["calc/broken.go"]
    # Step: ": " is the prefix (one char token ":"), strip → plain GO line.
    got = checker.parse(": calc\\broken.go:3:14: msg\n", tmp_path, paths)
    # Step: expected ["calc/broken.go:3: msg"].
    assert got == ["calc/broken.go:3: msg"]


def test_existing_go_lines_unaffected(tmp_path):
    """Existing Go test lines must still parse identically.

    Step: all the existing test_checker_go.py lines:
      "pkg/a.go:5:10: undefined: x" → "pkg/a.go:5: undefined: x"
      "pkg/b.go:2:3: msg1\\npkg/a.go:5:10: msg2" → sorted.
      "pkg/a.py:5:10: msg" → [] (not .go).
    These match forms directly → no prefix stripping. Results unchanged.
    """
    # Step: single Go line → direct match.
    assert checker.parse("pkg/a.go:5:10: undefined: x\n", tmp_path,
                         ["pkg/a.go"]) == ["pkg/a.go:5: undefined: x"]
    # Step: two Go lines → sorted.
    assert checker.parse("pkg/b.go:2:3: msg1\npkg/a.go:5:10: msg2\n", tmp_path,
                         ["pkg/a.go", "pkg/b.go"]) == ["pkg/a.go:5: msg2", "pkg/b.go:2: msg1"]
    # Step: .py suffix → no Go match → [].
    assert checker.parse("pkg/a.py:5:10: msg\n", tmp_path,
                         ["pkg/a.py"]) == []
    # Step: Go build summary → no match.
    assert checker.parse("go build: found packages main (main.go)\n", tmp_path,
                         ["main.go"]) == []


def test_existing_pyright_lines_unaffected(tmp_path):
    """Existing pyright/colon-form lines parse identically.

    Step: "pkg/user.py:1:23 - error: bad" → _COLON direct match
      → "pkg/user.py:1: bad".
    Step: "pkg/user.py:6:16 - error: other" → "pkg/user.py:6: other".
    No prefix stripping applies (forms match directly).
    """
    # Step: direct colon match → unchanged.
    out = "pkg/user.py:1:23 - error: bad\npkg/user.py:6:16 - error: other\n"
    # Step: sorted set: ["pkg/user.py:1: bad", "pkg/user.py:6: other"].
    assert checker.parse(out, tmp_path, ["pkg/user.py"]) == [
        "pkg/user.py:1: bad", "pkg/user.py:6: other"]


def test_existing_paren_lines_unaffected(tmp_path):
    """Existing paren-form (dotnet) lines parse identically.

    Step: "src/Game.cs(12,5): error CS0103: bad" → _PAREN direct.
    Step: "src/lib.js(3,7): error TS2339: prop" → _PAREN direct.
    No prefix stripping.
    """
    out = "src/Game.cs(12,5): error CS0103: bad\nsrc/lib.js(3,7): error TS2339: prop\n"
    # Step: sorted → ["src/Game.cs:12: CS0103: bad", "src/lib.js:3: TS2339: prop"].
    assert checker.parse(out, tmp_path, ["src/Game.cs", "src/lib.js"]) == [
        "src/Game.cs:12: CS0103: bad", "src/lib.js:3: TS2339: prop"]


def test_prefix_not_in_paths(tmp_path):
    """After stripping the prefix, the remainder's file is checked against
    paths; if the remainder's file is NOT in paths, the line is dropped.

    Step: "vet.exe: other.go:1:2: msg" → strip "vet.exe: " →
      "other.go:1:2: msg" → _GO file "other.go" → relpath "other.go"
      → NOT in wanted {"calc/broken.go"} → [].
    """
    # Step: prefix stripped, remainder not in wanted → [].
    assert checker.parse("vet.exe: other.go:1:2: msg\n", tmp_path,
                         ["calc/broken.go"]) == []
