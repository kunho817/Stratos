"""Tests for task t19_check_ignore: checker.check() drops lines whose message ends with
(<rule>) for a rule in config.CHECK_IGNORE_RULES. parse() is NOT changed.

config.CHECK_IGNORE_RULES = ("reportArgumentType", "reportGeneralTypeIssues",
"reportIndexIssue", "reportOptionalSubscript", "reportOptionalMemberAccess",
"reportOptionalIterable").

In stratos/checker.py, check(root, paths) calls parse() as before, then drops every
returned line whose message (the part after "path:line: ") ends with "(<rule>)" where
rule is in config.CHECK_IGNORE_RULES. A line ending in a rule NOT in the tuple
(reportAttributeAccessIssue, reportUnknownVariableType, reportMissingImports, etc.)
is kept. A rule name in the middle of the message is kept.
parse() itself is unchanged: a line ending in an ignored rule passes through parse().
check() returns [] when check_command is empty or paths is empty, unchanged.
"""

import subprocess

from stratos import checker, config

IGNORE = ("reportArgumentType", "reportGeneralTypeIssues", "reportIndexIssue",
          "reportOptionalSubscript", "reportOptionalMemberAccess",
          "reportOptionalIterable")


def _run_check(output, root, paths, monkeypatch):
    """Fake subprocess.run to return output; set check_command; return check()."""
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT,
                                            "check_command": ["pyright", "{files}"]})

    class R:
        stdout = output
        stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: R())
    return checker.check(root, paths)


# ---------------------------------------------------------------------------
# 1. config.CHECK_IGNORE_RULES is the exact tuple of six rule names.
# ---------------------------------------------------------------------------

def test_check_ignore_rules_constant():
    """config.CHECK_IGNORE_RULES must be the tuple of six pyright rule names."""
    # expected: the tuple in exact order
    assert config.CHECK_IGNORE_RULES == IGNORE
    # expected: len == 6
    assert len(config.CHECK_IGNORE_RULES) == 6


# ---------------------------------------------------------------------------
# 2. check() drops a line ending in (reportArgumentType).
# ---------------------------------------------------------------------------

def test_drop_report_argument_type(tmp_path, monkeypatch):
    """pyright reports Argument-of-type as reportArgumentType; check() drops it."""
    out = 'pkg/a.py:6:16 - error: Argument of type X cannot be assigned (reportArgumentType)\n'
    result = _run_check(out, tmp_path, ["pkg/a.py"], monkeypatch)
    # parse produces: "pkg/a.py:6: Argument of type X cannot be assigned (reportArgumentType)"
    # message = 'Argument of type X cannot be assigned (reportArgumentType)'
    # ends with "(reportArgumentType)" → in CHECK_IGNORE_RULES → dropped
    # expected: []
    assert result == []


# ---------------------------------------------------------------------------
# 3. check() drops a line ending in (reportGeneralTypeIssues).
# ---------------------------------------------------------------------------

def test_drop_report_general_type_issues(tmp_path, monkeypatch):
    """pyright reports undefined names as reportGeneralTypeIssues; check() drops it."""
    out = 'pkg/a.py:3:1 - error: "x" is not defined (reportGeneralTypeIssues)\n'
    result = _run_check(out, tmp_path, ["pkg/a.py"], monkeypatch)
    # parse produces: 'pkg/a.py:3: "x" is not defined (reportGeneralTypeIssues)'
    # message ends with "(reportGeneralTypeIssues)" → dropped
    # expected: []
    assert result == []


# ---------------------------------------------------------------------------
# 4. check() drops a line ending in (reportIndexIssue).
# ---------------------------------------------------------------------------

def test_drop_report_index_issue(tmp_path, monkeypatch):
    """pyright reports out-of-range index as reportIndexIssue; check() drops it."""
    out = 'pkg/a.py:5:2 - error: Index is not in range (reportIndexIssue)\n'
    result = _run_check(out, tmp_path, ["pkg/a.py"], monkeypatch)
    # parse produces: "pkg/a.py:5: Index is not in range (reportIndexIssue)"
    # message ends with "(reportIndexIssue)" → dropped
    # expected: []
    assert result == []


# ---------------------------------------------------------------------------
# 5. check() drops a line ending in (reportOptionalSubscript).
# ---------------------------------------------------------------------------

def test_drop_report_optional_subscript(tmp_path, monkeypatch):
    """pyright reports optional subscript as reportOptionalSubscript; check() drops it."""
    out = 'pkg/a.py:4:10 - error: Object is possibly unbound (reportOptionalSubscript)\n'
    result = _run_check(out, tmp_path, ["pkg/a.py"], monkeypatch)
    # parse produces: "pkg/a.py:4: Object is possibly unbound (reportOptionalSubscript)"
    # message ends with "(reportOptionalSubscript)" → dropped
    # expected: []
    assert result == []


# ---------------------------------------------------------------------------
# 6. check() drops a line ending in (reportOptionalMemberAccess).
# ---------------------------------------------------------------------------

def test_drop_report_optional_member_access(tmp_path, monkeypatch):
    """pyright reports optional member access as reportOptionalMemberAccess; check() drops it."""
    out = 'pkg/a.py:7:2 - error: x is possibly None (reportOptionalMemberAccess)\n'
    result = _run_check(out, tmp_path, ["pkg/a.py"], monkeypatch)
    # parse produces: "pkg/a.py:7: x is possibly None (reportOptionalMemberAccess)"
    # message ends with "(reportOptionalMemberAccess)" → dropped
    # expected: []
    assert result == []


# ---------------------------------------------------------------------------
# 7. check() drops a line ending in (reportOptionalIterable).
# ---------------------------------------------------------------------------

def test_drop_report_optional_iterable(tmp_path, monkeypatch):
    """pyright reports optional iterable as reportOptionalIterable; check() drops it."""
    out = 'pkg/a.py:8:5 - error: x is possibly None (reportOptionalIterable)\n'
    result = _run_check(out, tmp_path, ["pkg/a.py"], monkeypatch)
    # parse produces: "pkg/a.py:8: x is possibly None (reportOptionalIterable)"
    # message ends with "(reportOptionalIterable)" → dropped
    # expected: []
    assert result == []


# ---------------------------------------------------------------------------
# 8. check() keeps a line ending in reportAttributeAccessIssue.
# ---------------------------------------------------------------------------

def test_keep_report_attribute_access_issue(tmp_path, monkeypatch):
    """reportAttributeAccessIssue is NOT in CHECK_IGNORE_RULES; the line is kept."""
    out = 'pkg/a.py:1:23 - error: "subtract" is unknown import symbol (reportAttributeAccessIssue)\n'
    result = _run_check(out, tmp_path, ["pkg/a.py"], monkeypatch)
    # parse produces: 'pkg/a.py:1: "subtract" is unknown import symbol (reportAttributeAccessIssue)'
    # message ends with "(reportAttributeAccessIssue)"
    # "reportAttributeAccessIssue" is NOT in CHECK_IGNORE_RULES → kept
    # expected: the line is present
    expected = 'pkg/a.py:1: "subtract" is unknown import symbol (reportAttributeAccessIssue)'
    assert result == [expected]


# ---------------------------------------------------------------------------
# 9. check() keeps a line ending in reportUnknownVariableType.
# ---------------------------------------------------------------------------

def test_keep_report_unknown_variable_type(tmp_path, monkeypatch):
    """reportUnknownVariableType is NOT in CHECK_IGNORE_RULES; the line is kept."""
    out = 'pkg/a.py:2:5 - error: x is unknown type (reportUnknownVariableType)\n'
    result = _run_check(out, tmp_path, ["pkg/a.py"], monkeypatch)
    # parse produces: "pkg/a.py:2: x is unknown type (reportUnknownVariableType)"
    # "reportUnknownVariableType" not in CHECK_IGNORE_RULES → kept
    # expected: the line
    assert result == ["pkg/a.py:2: x is unknown type (reportUnknownVariableType)"]


# ---------------------------------------------------------------------------
# 10. check() keeps a line with no trailing parenthesized rule.
# ---------------------------------------------------------------------------

def test_keep_no_trailing_rule(tmp_path, monkeypatch):
    """A message with no trailing (rule) is kept by check()."""
    out = 'pkg/a.py:3:1 - error: x is not defined\n'
    result = _run_check(out, tmp_path, ["pkg/a.py"], monkeypatch)
    # parse produces: "pkg/a.py:3: x is not defined"
    # message has no "(...)" suffix → kept
    # expected: the line
    assert result == ["pkg/a.py:3: x is not defined"]


# ---------------------------------------------------------------------------
# 11. check() keeps a parenthesized text not in CHECK_IGNORE_RULES.
# ---------------------------------------------------------------------------

def test_keep_unknown_rule_in_parens(tmp_path, monkeypatch):
    """reportMissingImports is NOT in CHECK_IGNORE_RULES; the line is kept."""
    out = 'pkg/a.py:4:2 - error: thing (reportMissingImports)\n'
    result = _run_check(out, tmp_path, ["pkg/a.py"], monkeypatch)
    # parse produces: "pkg/a.py:4: thing (reportMissingImports)"
    # "reportMissingImports" not in CHECK_IGNORE_RULES → kept
    # expected: the line
    assert result == ["pkg/a.py:4: thing (reportMissingImports)"]


# ---------------------------------------------------------------------------
# 12. parse() is unchanged: a line ending in reportArgumentType passes through.
# ---------------------------------------------------------------------------

def test_parse_is_not_filtered(tmp_path):
    """parse() returns lines ending in (reportArgumentType); the filter is in check(),
    not in parse()."""
    out = 'pkg/a.py:6:16 - error: Argument of type X cannot be assigned (reportArgumentType)\n'
    # parse() does NOT filter ignored rules
    # parse produces: "pkg/a.py:6: Argument of type X cannot be assigned (reportArgumentType)"
    # expected: the line is in parse's output
    result = checker.parse(out, tmp_path, ["pkg/a.py"])
    # expected: one line, the full parse output
    expected = 'pkg/a.py:6: Argument of type X cannot be assigned (reportArgumentType)'
    assert result == [expected]
    # expected: the line IS in parse() result (not dropped by parse)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# 13. check() drops some lines and keeps others in mixed output.
# ---------------------------------------------------------------------------

def test_mixed_drop_and_keep(tmp_path, monkeypatch):
    """Three pyright lines: two with ignored rules (dropped), one with a kept rule."""
    out = (
        'pkg/a.py:6:16 - error: Argument X (reportArgumentType)\n'
        'pkg/a.py:1:23 - error: "subtract" unknown (reportAttributeAccessIssue)\n'
        'pkg/a.py:10:1 - error: undefined x (reportGeneralTypeIssues)\n'
    )
    result = _run_check(out, tmp_path, ["pkg/a.py"], monkeypatch)
    # parse produces three lines sorted by path, line:
    #   "pkg/a.py:1: \"subtract\" unknown (reportAttributeAccessIssue)"
    #   "pkg/a.py:6: Argument X (reportArgumentType)"
    #   "pkg/a.py:10: undefined x (reportGeneralTypeIssues)"
    # check drops line at 6 (reportArgumentType) and line at 10 (reportGeneralTypeIssues)
    # check keeps line at 1 (reportAttributeAccessIssue, not in tuple)
    # expected: only the reportAttributeAccessIssue line
    expected = 'pkg/a.py:1: "subtract" unknown (reportAttributeAccessIssue)'
    assert result == [expected]
    # expected: len == 1
    assert len(result) == 1


# ---------------------------------------------------------------------------
# 14. A rule name in the middle of the message (not at the end) is kept.
# ---------------------------------------------------------------------------

def test_keep_rule_in_middle_of_message(tmp_path, monkeypatch):
    """(reportArgumentType) appears in the middle of the message, not at the
    end, so the line is not dropped."""
    out = 'pkg/a.py:3:1 - error: Argument (reportArgumentType) is bad\n'
    result = _run_check(out, tmp_path, ["pkg/a.py"], monkeypatch)
    # parse produces: "pkg/a.py:3: Argument (reportArgumentType) is bad"
    # message = "Argument (reportArgumentType) is bad"
    # ends with "is bad", NOT "(reportArgumentType)" → kept
    # expected: the line
    assert result == ["pkg/a.py:3: Argument (reportArgumentType) is bad"]


# ---------------------------------------------------------------------------
# 15. check() returns [] when check_command is empty (unchanged behaviour).
# ---------------------------------------------------------------------------

def test_check_returns_empty_when_no_command(tmp_path, monkeypatch):
    """An empty check_command gives [] regardless of the filter."""
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT,
                                            "check_command": []})
    # expected: [] because check_command is empty
    assert checker.check(tmp_path, ["pkg/a.py"]) == []
    # expected: [] also for empty paths
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT,
                                            "check_command": ["pyright", "{files}"]})
    assert checker.check(tmp_path, []) == []
