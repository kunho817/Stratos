"""Tests for task learn_drafts (P11, 2026-11-20, user: Claude's fixes to drafted tests never became lessons - the
"2 oz spice" unit trap was drafted wrong three times in one project). Every fix Claude makes to a drafted test
carries a note "(Claude: <why>)" in the test file (a comment or a docstring); those notes are corrections.

learn.draft_corrections(repo, test_dir="tests") -> list of {"id", "text"}, for every .py file under repo/test_dir
(sorted paths) and every "(Claude:" in it, in order: the note is the text from "(Claude:" up to its matching ")"
(parentheses inside count), over as many lines as it takes; on the lines after the first, a leading "#" and the
spaces around it are dropped, and the lines are joined with one space. The note text is what follows "(Claude:",
stripped. The test is the top-level function or class (codemap.scan_python) whose lines hold the "(Claude:",
else "(module)". id = f"draft:{path}:{test}:{n}" (n counts the notes of that test from 1; path relative with "/");
text = f"A person fixed a drafted test {path}::{test}: {note}".
learn.learn(..., repo=None): when repo is given, draft_corrections(repo) are added to the corrections it learns
from (after the others)."""
from stratos import learn

TEST = '''def test_slug():
    # (Claude: removing "&" leaves two spaces, so the slug is "a--b",
    # not the draft's "a-b"; see slugify() (the rule))
    assert slug("a & b") == "a--b"


def test_other():
    """(Claude: one paragraph from two lines)"""
    assert 1
'''


def test_draft_corrections(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(TEST, encoding="utf-8")
    (tmp_path / "tests" / "test_b.py").write_text("X = 1  # (Claude: module note)\n", encoding="utf-8")
    got = learn.draft_corrections(tmp_path)
    assert got == [
        {"id": "draft:tests/test_a.py:test_slug:1",
         "text": 'A person fixed a drafted test tests/test_a.py::test_slug: removing "&" leaves two spaces, so the '
                 'slug is "a--b", not the draft\'s "a-b"; see slugify() (the rule)'},
        {"id": "draft:tests/test_a.py:test_other:1",
         "text": "A person fixed a drafted test tests/test_a.py::test_other: one paragraph from two lines"},
        {"id": "draft:tests/test_b.py:(module):1",
         "text": "A person fixed a drafted test tests/test_b.py::(module): module note"},
    ]


def test_learn_reads_the_notes(tmp_path, monkeypatch):
    from stratos import config
    from test_learn import FakeGateway
    monkeypatch.setattr(config, "LEARNER", {"model": "m", "effort": "none", "max_tokens": 50})
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_b.py").write_text("X = 1  # (Claude: an unknown unit is part of the name)\n",
                                              encoding="utf-8")
    state = tmp_path / "state"
    state.mkdir()
    lessons_path = tmp_path / "LESSONS.md"
    gw = FakeGateway(["- [tests, data] Read the data rules before writing expected values."])
    out = learn.learn(gw, [], [], lessons_path, state, "pantry", repo=repo)
    assert out["corrections"] == 1 and out["added"] == 1
    assert "an unknown unit is part of the name" in gw.calls[0][0][1]["content"]
    assert learn.learn(FakeGateway([]), [], [], lessons_path, state, "pantry")["corrections"] == 0


def test_only_comments_and_docstrings_count(tmp_path):
    """(task learn_notes_only, 2026-11-21) The first automatic learn read "(Claude: ...)" inside test DATA (this file's
    TEST string, a fake note in test_upkeep.py) and made 7 junk lessons. A note counts only when it is in a comment
    (tokenize COMMENT) or in a docstring (the first statement string of the module, a function or a class)."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_c.py").write_text(
        'DATA = "X = 1  # (Claude: not a note, a string)"\n\n\n'
        'def test_x():\n    """(Claude: a docstring note)"""\n    text = """(Claude: data again)"""\n'
        '    assert text  # (Claude: a comment note)\n', encoding="utf-8")
    texts = [c["text"] for c in learn.draft_corrections(tmp_path)]
    assert texts == ["A person fixed a drafted test tests/test_c.py::test_x: a docstring note",
                     "A person fixed a drafted test tests/test_c.py::test_x: a comment note"]


def test_no_tests_folder(tmp_path):
    assert learn.draft_corrections(tmp_path) == []
