"""Tests for task t5: Go compile error parsing in checker.parse.

stratos/checker.py parse(output, root, paths) is extended to recognise Go
compile errors of the form "<file>.go:<line>:<col>: <message>" (no word
"error" in the line).  The Go regex fires only when the existing _COLON
(pyright/gcc) and _PAREN (tsc/dotnet/msbuild) patterns do not match.
Output shape is identical to existing parses: sorted, unique strings
f"{path}:{line}: {message}", with path relative to root using "/"
separators, message stripped, trailing " [<something>]" cut.
"""

from stratos import checker

GO_UNDEFINED = "pkg/a.go:5:10: undefined: x\n"
GO_EXPECTED = "pkg/a.go:12:1: expected declaration, found 'var'\n"
GO_MULTI = "pkg/b.go:2:3: msg1\npkg/a.go:5:10: msg2\n"
GO_MULTI_DIGIT = "pkg/a.go:100:123: msg\n"
GO_INDENTED = "  pkg/a.go:5:10: msg\n"
GO_ABS = "/w/pkg/a.go:5:10: msg\n"
GO_DUP = "pkg/a.go:5:10: msg\npkg/a.go:5:10: msg\npkg/a.go:6:1: msg2\n"
GO_PY_SUFFIX = "pkg/a.py:5:10: msg\n"
GO_NO_COL = "pkg/a.go:5: msg\n"
GO_BUILD = "go build: found packages main (main.go)\n"
GO_BRACKET = "pkg/a.go:5:10: msg [project]\n"
GO_BACKSLASH = "pkg\\sub\\a.go:5:10: msg\n"
GO_NO_ERROR = "pkg/a.go:3:4: x = 5\n"
GO_TRAILING = "pkg/a.go:5:10:\n"
PYRIGHT = "pkg/a.py:1:2 - error: bad\n"
PYRIGHT_GO = "pkg/a.py:1:2 - error: bad\npkg/a.go:5:10: msg\n"


def test_parse_go_single(tmp_path):
    """Go error pkg/a.go:5:10: undefined: x → pkg/a.go:5: undefined: x."""
    # file="pkg/a.go", line="5", col="10", msg="undefined: x"
    # relpath(root/pkg/a.go, root) → "pkg/a.go", replace("\\","/") → "pkg/a.go"
    # msg strip: "undefined: x"
    # output: "pkg/a.go:5: undefined: x"
    assert checker.parse(GO_UNDEFINED, tmp_path, ["pkg/a.go"]) == ["pkg/a.go:5: undefined: x"]


def test_parse_go_not_in_paths(tmp_path):
    """Go error in a file not in paths is dropped."""
    # rel="pkg/a.go", wanted={"pkg/b.go"} → not in wanted → skip
    assert checker.parse(GO_UNDEFINED, tmp_path, ["pkg/b.go"]) == []


def test_parse_go_multi_sorted(tmp_path):
    """Two Go errors from two files are sorted by path then line."""
    # "pkg/b.go:2:3: msg1" → "pkg/b.go:2: msg1"
    # "pkg/a.go:5:10: msg2" → "pkg/a.go:5: msg2"
    # sorted set: ["pkg/a.go:5: msg2", "pkg/b.go:2: msg1"]
    assert checker.parse(GO_MULTI, tmp_path, ["pkg/a.go", "pkg/b.go"]) == [
        "pkg/a.go:5: msg2", "pkg/b.go:2: msg1"
    ]


def test_parse_go_multi_digit(tmp_path):
    """Multi-digit line (100) and col (123): only line appears in output."""
    # file="pkg/a.go", line="100", col="123", msg="msg"
    # output: "pkg/a.go:100: msg"
    assert checker.parse(GO_MULTI_DIGIT, tmp_path, ["pkg/a.go"]) == ["pkg/a.go:100: msg"]


def test_parse_go_colon_in_msg(tmp_path):
    """Colon inside the message is preserved after the first colon-space separator."""
    # file="pkg/a.go", line="12", col="1", msg="expected declaration, found 'var'"
    # output: "pkg/a.go:12: expected declaration, found 'var'"
    assert checker.parse(GO_EXPECTED, tmp_path, ["pkg/a.go"]) == [
        "pkg/a.go:12: expected declaration, found 'var'"
    ]


def test_parse_go_indented(tmp_path):
    """Leading whitespace is consumed by ^\\s*; the Go pattern still matches."""
    # "  pkg/a.go:5:10: msg" → ^\s* eats "  "
    # file="pkg/a.go", line="5", col="10", msg="msg"
    # output: "pkg/a.go:5: msg"
    assert checker.parse(GO_INDENTED, tmp_path, ["pkg/a.go"]) == ["pkg/a.go:5: msg"]


def test_parse_go_absolute_path(tmp_path):
    """Absolute path in Go output is resolved to a relative path against root."""
    # file="/w/pkg/a.go" is absolute → not joined
    # relpath("/w/pkg/a.go", tmp_path) → relative
    # On tmp_path="/tmp/...": relpath gives "../w/pkg/a.go"
    # replace("\\","/") → "../w/pkg/a.go"
    # wanted = {"pkg/a.go"}
    # "../w/pkg/a.go" not in wanted → dropped
    # Expected: []
    assert checker.parse(GO_ABS, tmp_path, ["pkg/a.go"]) == []


def test_parse_go_dedup(tmp_path):
    """Duplicate identical Go lines are deduplicated via set; sorted output."""
    # line1: "pkg/a.go:5:10: msg" → "pkg/a.go:5: msg"
    # line2: same → "pkg/a.go:5: msg" (dup, set removes)
    # line3: "pkg/a.go:6:1: msg2" → "pkg/a.go:6: msg2"
    # sorted set: ["pkg/a.go:5: msg", "pkg/a.go:6: msg2"]
    assert checker.parse(GO_DUP, tmp_path, ["pkg/a.go"]) == [
        "pkg/a.go:5: msg", "pkg/a.go:6: msg2"
    ]


def test_parse_go_not_go_suffix(tmp_path):
    """A colon triple with .py suffix: Go regex requires .go, so not matched."""
    # file="pkg/a.py" does NOT end in .go → Go regex fails
    # _COLON requires "error" keyword → fails
    # _PAREN requires paren form → fails
    # Expected: []
    assert checker.parse(GO_PY_SUFFIX, tmp_path, ["pkg/a.py"]) == []


def test_parse_go_no_col(tmp_path):
    """Go error without col number (file:line: msg): Go regex requires col → not matched."""
    # "pkg/a.go:5: msg" → Go regex needs file:line:col: → fails
    # _COLON needs "error" → fails
    # Expected: []
    assert checker.parse(GO_NO_COL, tmp_path, ["pkg/a.go"]) == []


def test_parse_go_build_summary(tmp_path):
    """go build summary line "go build: found packages main (main.go)" → not matched."""
    # Go regex: .+?\.go non-greedy tries shortest; first .go in string is inside
    # "(main.go)" → file captures "go build: found packages main (main.go"
    # next char after .go is ")" not ":" → regex fails
    # _COLON needs "error" → fails
    # Expected: []
    assert checker.parse(GO_BUILD, tmp_path, ["main.go"]) == []


def test_parse_go_bracket_stripped(tmp_path):
    """Trailing " [project]" is stripped by _TRAILING as in existing parses."""
    # file="pkg/a.go", line="5", col="10", msg="msg [project]"
    # _TRAILING.sub("", "msg [project]") → "msg"
    # strip → "msg"
    # output: "pkg/a.go:5: msg"
    assert checker.parse(GO_BRACKET, tmp_path, ["pkg/a.go"]) == ["pkg/a.go:5: msg"]


def test_parse_go_backslash(tmp_path):
    """Windows backslashes in file path are normalized to "/" separators."""
    # file="pkg\sub\a.go" → joined to root, relpath → "pkg\sub\a.go"
    # replace("\\","/") → "pkg/sub/a.go"
    # wanted = {"pkg/sub/a.go"} → match
    # output: "pkg/sub/a.go:5: msg"
    assert checker.parse(GO_BACKSLASH, tmp_path, ["pkg/sub/a.go"]) == [
        "pkg/sub/a.go:5: msg"
    ]


def test_parse_go_no_error_keyword(tmp_path):
    """Go error without the word "error" in the message: Go regex fires."""
    # "pkg/a.go:3:4: x = 5" → no "error" keyword
    # _COLON fails, _PAREN fails, Go regex matches
    # file="pkg/a.go", line="3", col="4", msg="x = 5"
    # output: "pkg/a.go:3: x = 5"
    assert checker.parse(GO_NO_ERROR, tmp_path, ["pkg/a.go"]) == ["pkg/a.go:3: x = 5"]


def test_parse_go_mixed_pyright(tmp_path):
    """Go line coexists with pyright _COLON line; both parsed, sorted together."""
    # PYRIGHT: "pkg/a.py:1:2 - error: bad" → _COLON matches → "pkg/a.py:1: bad"
    # GO: "pkg/a.go:5:10: msg" → Go regex matches → "pkg/a.go:5: msg"
    # sorted set: ["pkg/a.go:5: msg", "pkg/a.py:1: bad"]
    # ("pkg/a.go" < "pkg/a.py" because 'g' < 'p')
    assert checker.parse(PYRIGHT_GO, tmp_path, ["pkg/a.go", "pkg/a.py"]) == [
        "pkg/a.go:5: msg", "pkg/a.py:1: bad"
    ]
