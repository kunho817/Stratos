"""Harness fix (Claude, 2026-11-21, Sieve P002 test drafts): an answer wrapped each FILE header in its own fence
(```, FILE: x, ```, content, ```, then ``` / FILE: y / ``` for the next file). parse_files took the content up to
the LAST bare fence before the next header - the wrapper of that header - so the first file kept its own closing
fence as its last line (a syntax error; the Claude Code hook caught it).

When a later FILE header follows and the segment ends with two bare ``` lines separated only by blank lines, the
first of them closes the file and the second belongs to the next header."""
from stratos import patch

ANSWER = ("```\nFILE: tests/test_a.py\n```\ndef test_a():\n    assert 1\n```\n\n```\nFILE: tests/test_b.py\n```\n"
          "def test_b():\n    assert 2\n```\n")


def test_wrapped_headers():
    assert patch.parse_files(ANSWER) == [("tests/test_a.py", "def test_a():\n    assert 1\n"),
                                         ("tests/test_b.py", "def test_b():\n    assert 2\n")]


def test_header_as_the_first_line_of_the_fence():
    """(Claude, 2026-11-21, Lantern solver drafts) ``` / FILE: x / content / ``` - the header is the fence's first line
    and the content follows it with no fence of its own; the whole draft was dropped as "missing"."""
    text = "```\nFILE: tests/solver.test.js\nimport x from 'y';\ntest('a', () => {});\n```\n"
    assert patch.parse_files(text, ["tests/solver.test.js"]) == [
        ("tests/solver.test.js", "import x from 'y';\ntest('a', () => {});\n")]
    two = text + "```js\nFILE: tests/b.test.js\nconst b = 1;\n```\n"
    assert [p for p, _ in patch.parse_files(two)] == ["tests/solver.test.js", "tests/b.test.js"]
    assert patch.parse_files(two)[0][1] == "import x from 'y';\ntest('a', () => {});\n"


def test_a_fence_inside_the_content_still_counts():
    text = ("FILE: tests/test_a.py\n```python\nDOC = '''\n```\n'''\n```\nFILE: tests/test_b.py\n```python\nX = 1\n```\n")
    assert patch.parse_files(text)[0] == ("tests/test_a.py", "DOC = '''\n```\n'''\n")
