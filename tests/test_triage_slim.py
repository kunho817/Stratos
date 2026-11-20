"""Tests for task triage_slim (P10, 2026-11-20): triage prompts reached 34k tokens because every test file of the task
went in whole (a loop.py task lists ~17 old test files). Now triage sees only the failing tests and what they use.

triage.test_parts(root, tests, test_output) -> [(path, text)]:
- failing = decide._extract_ids(test_output); a failing id is "path::name" (a [param] suffix after the name is
  cut) or a bare "path" (the file could not be imported);
- the files shown are the paths of `tests` (any "::..." cut off) that some failing id names, in the order of
  `tests`; when no failing id names any of them, every file of `tests` is shown whole (as before);
- a file named by a bare id is shown whole; otherwise its text is: the lines before its first top-level def or
  class or their decorators (imports, constants), without trailing blank lines, then the source of each
  top-level function or class that is a failing test or that a shown one uses (codemap uses, followed until
  nothing new is added - helpers, fixtures), from its first decorator line to its end, in file order; the parts
  joined by "\\n\\n" (constants are shown once, in the first part);
- a file that cannot be read gives "".
triage.build_messages lists these parts under "Test files (the failing tests and what they use):" instead of
every test file whole."""
from stratos import triage

TEST = '''import pytest

from pkg import f

LIMIT = 3


def helper(x):
    return base() + x


def base():
    return 1


@pytest.fixture
def board():
    return [0] * LIMIT


def test_ok():
    assert f(1) == 1


def test_bad(board):
    assert f(helper(2)) == len(board)


def test_other():
    assert f(0) == 0
'''


def setup(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(TEST, encoding="utf-8")
    (tmp_path / "tests" / "test_b.py").write_text("def test_b():\n    assert 1\n", encoding="utf-8")
    return tmp_path


def test_only_the_failing_test_and_what_it_uses(tmp_path):
    root = setup(tmp_path)
    out = "FAILED tests/test_a.py::test_bad - assert 4 == 3\n1 failed, 3 passed"
    parts = triage.test_parts(root, ["tests/test_a.py", "tests/test_b.py"], out)
    assert [p for p, _ in parts] == ["tests/test_a.py"]
    text = parts[0][1]
    assert text.startswith("import pytest\n\nfrom pkg import f\n\nLIMIT = 3")
    assert "def helper(x):" in text and "def base():" in text and "@pytest.fixture\ndef board():" in text
    assert text.count("LIMIT = 3") == 1
    assert "def test_bad(board):" in text
    assert "test_ok" not in text and "test_other" not in text
    assert text.index("def helper") < text.index("def base") < text.index("def test_bad")


def test_params_and_import_errors(tmp_path):
    root = setup(tmp_path)
    out = "FAILED tests/test_a.py::test_other[1] - x\nERROR tests/test_b.py - ImportError: boom"
    parts = dict(triage.test_parts(root, ["tests/test_a.py", "tests/test_b.py::test_b"], out))
    assert "def test_other():" in parts["tests/test_a.py"] and "test_bad" not in parts["tests/test_a.py"]
    assert parts["tests/test_b.py"] == "def test_b():\n    assert 1\n"


def test_no_ids_shows_every_file_whole(tmp_path):
    root = setup(tmp_path)
    parts = triage.test_parts(root, ["tests/test_a.py", "tests/test_b.py"], "something broke")
    assert parts == [("tests/test_a.py", TEST), ("tests/test_b.py", "def test_b():\n    assert 1\n")]


def test_build_messages_uses_the_parts(tmp_path):
    root = setup(tmp_path)
    task = {"id": "T1", "goal": "g", "tests": ["tests/test_a.py", "tests/test_b.py"]}
    user = triage.build_messages(task, root, [], "FAILED tests/test_a.py::test_bad - x")[1]["content"]
    assert "Test files (the failing tests and what they use):" in user
    assert "def test_bad(board):" in user and "def test_ok" not in user and "test_b.py" not in user
