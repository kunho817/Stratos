"""Tests for task cases (P11, 2026-11-20, user: "you give the test cases and Stratos writes the tests"): plain-call
cases become pytest functions mechanically - no model, the case text goes in as written, so the step itself cannot
get an expected value or an import wrong.

cases.parse(text) -> {"imports": [...], "plain": [...], "other": [...]}: per line, stripped; blank lines and lines
starting with "#" are skipped.
- "IMPORT <import statement>" -> imports (the statement, as written);
- "<call> == <expected>": the line parses (ast, mode "eval") as one comparison with a single "==" whose left side
  is a call of a name or a dotted name -> plain {"kind": "eq", "call": <left source>, "expected": <right source>};
- "<call> raises <Name>" or "<call> raises <Name>: <message>" (split at the last " raises "; the left side parses
  as such a call, <Name> is an identifier) -> plain {"kind": "raises", "call": ..., "error": <Name>,
  "message": <message> or None};
- anything else -> other (the line as written).
For a dotted call "a.b.f(...)" the case also has "module": "a.b" and "name": "f", and its "call" is rewritten to
start at "f(" (the arguments as written); a bare "f(...)" has "module": None, "name": "f".
cases.render(parsed) -> the text of a pytest file: a docstring line, then "import re" and "import pytest" only when
a raises case exists, then the IMPORT statements in order, then "from <module> import <names>" for each module (in
first-use order, names sorted, joined with ", "), then two blank lines before each test function. Functions are
named f"test_{name}_{n}" (n counts per name from 1, in case order) and hold
"    assert <call> == <expected>", or
"    with pytest.raises(<Name>):" / "    with pytest.raises(<Name>, match=re.escape(<repr of message>)):" and
"        <call>". The text ends with one newline."""
import pytest

from stratos import cases

TEXT = """# fields
IMPORT from datetime import datetime
cronix.fields.parse_field("*/20", 0) == frozenset({0, 20, 40})
cronix.fields.parse_field("61", 0) raises ValueError: minute: 61 is out of range 0-59
cronix.fields.parse_field("x", 1) raises ValueError
cronix.schedule.next_runs(cron, datetime(2026, 1, 1), 0) == []
helper(1) == 2

a fixture-backed case that needs setup
cronix.fields.parse_field("1") != {1}
"""


def test_parse():
    p = cases.parse(TEXT)
    assert p["imports"] == ["from datetime import datetime"]
    assert p["other"] == ["a fixture-backed case that needs setup", 'cronix.fields.parse_field("1") != {1}']
    eq, err, bare_err, nxt, helper = p["plain"]
    assert eq == {"kind": "eq", "call": 'parse_field("*/20", 0)', "expected": "frozenset({0, 20, 40})",
                  "module": "cronix.fields", "name": "parse_field"}
    assert err == {"kind": "raises", "call": 'parse_field("61", 0)', "error": "ValueError",
                   "message": "minute: 61 is out of range 0-59", "module": "cronix.fields", "name": "parse_field"}
    assert bare_err["message"] is None and bare_err["error"] == "ValueError"
    assert nxt["module"] == "cronix.schedule" and nxt["call"] == "next_runs(cron, datetime(2026, 1, 1), 0)"
    assert helper == {"kind": "eq", "call": "helper(1)", "expected": "2", "module": None, "name": "helper"}


def test_render():
    text = cases.render(cases.parse(TEXT))
    assert text.endswith("\n") and not text.endswith("\n\n")
    compile(text, "t.py", "exec")
    head = text.split("\n\n\n")[0]
    assert head.splitlines()[1:] == ["import re", "import pytest", "from datetime import datetime",
                                     "from cronix.fields import parse_field",
                                     "from cronix.schedule import next_runs"]
    assert ('def test_parse_field_1():\n    assert parse_field("*/20", 0) == frozenset({0, 20, 40})' in text)
    assert ("def test_parse_field_2():\n    with pytest.raises(ValueError, match=re.escape("
            "'minute: 61 is out of range 0-59')):\n        parse_field(\"61\", 0)") in text
    assert 'def test_parse_field_3():\n    with pytest.raises(ValueError):\n        parse_field("x", 1)' in text
    assert "def test_next_runs_1():" in text and "def test_helper_1():\n    assert helper(1) == 2" in text


def test_render_runs(tmp_path):
    (tmp_path / "m.py").write_text("def f(x):\n    if x < 0:\n        raise ValueError(f'bad {x} (x)')\n"
                                   "    return x * 2\n", encoding="utf-8")
    test = cases.render(cases.parse("m.f(2) == 4\nm.f(-1) raises ValueError: bad -1 (x)\nm.f(3) == 7\n"))
    (tmp_path / "test_m.py").write_text(test, encoding="utf-8")
    import subprocess
    import sys
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_m.py"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 1, r.stdout  # f(3) == 7 is a wrong case on purpose
    assert "1 failed, 2 passed" in r.stdout
