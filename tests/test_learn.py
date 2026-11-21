"""Tests for task learn: a local model turns people's corrections into general lessons in LESSONS.md (memory M3b).

config.LEARNER = {"model": "qwen3.6-35b-a3b-ud-q3_k_m", "effort": "none", "max_tokens": 600} (the reviewer's model,
usually loaded at the end of a run).

learn.corrections(tasks, events) -> for each task (in order), for each of its "verdict" events with result
"reset_by_human" (n = 1, 2, ...): {"id": f"reset:{task id}:{n}", "text": f"Task {id}: {title}\nGoal: {goal cut to
800 characters}\nA person reset this task and said: {reason}"}.

learn.SYSTEM: the system prompt; it asks for ONE general lesson for future tasks in other projects, written as a single
line "- [tag, tag] lesson", or the word NONE when the correction teaches nothing general.
learn.messages(correction, existing) -> [{"role": "system", "content": SYSTEM}, {"role": "user", "content":
"CORRECTION:\n" + correction["text"] + "\n\nLESSONS WE ALREADY HAVE (do not repeat them):\n" + "\n".join(existing)}]
with existing = lesson lines as written in LESSONS.md.

learn.ask(gw, correction, existing) -> (tags, text) or None: gw.ensure_model(LEARNER model), then gw.chat(messages,
task="learn", role="learner", attempt=1, model, effort, max_tokens); the first line of the answer that, stripped,
starts with "- [" is parsed with lessons.parse; no such line (or NONE) -> None.

learn.is_duplicate(text, existing_texts, threshold=0.6) -> True when the Jaccard overlap of the token sets
(set(memstore.tokenize(...))) of text and any existing text is >= threshold.

learn.learn(gw, tasks, events, lessons_path, state_dir, project) -> {"corrections", "added", "duplicates", "skipped"}:
learned = the id list in state_dir / "learned.json" ([] when missing). For each correction whose id is not in learned
("corrections" counts these): result = ask(gw, c, <the lesson lines of lessons_path now>); None -> "skipped";
is_duplicate(text, <the lesson texts now>) -> "duplicates"; else the line f"- [{', '.join(tags)}] {text} ({project}:
{c['id']})" is appended to lessons_path (on its own line) and "added". Every handled id is added to learned, and
learned.json is written (UTF-8 JSON list) at the end. lessons_path is made when missing."""
import json

import pytest

from stratos import config, learn


T1 = {"id": "T012", "title": "Boss waves", "goal": "G" * 900, "status": "done"}


T2 = {"id": "T013", "title": "Panel", "goal": "g", "status": "done"}


EVENTS = [
    {"kind": "verdict", "task": "T012", "result": "reset_by_human", "reason": "old waves.test.js pinned wave 5"},
    {"kind": "verdict", "task": "T013", "result": "reset_by_human", "reason": "my test regex lost a backslash"},
    {"kind": "verdict", "task": "T012", "result": "other", "reason": "x"},
    {"kind": "verdict", "task": "T012", "result": "reset_by_human", "reason": "second"},
]


def test_config():
    assert config.LEARNER["model"] == "qwen3.6-35b-a3b-ud-q3_k_m" and config.LEARNER["effort"] == "none"


def test_corrections():
    cs = learn.corrections([T1, T2], EVENTS)
    assert [c["id"] for c in cs] == ["reset:T012:1", "reset:T012:2", "reset:T013:1"]
    assert cs[0]["text"] == ("Task T012: Boss waves\nGoal: " + "G" * 800 +
                             "\nA person reset this task and said: old waves.test.js pinned wave 5")


def test_messages():
    m = learn.messages({"id": "x", "text": "TEXT"}, ["- [a] one", "- [b] two"])
    assert m[0] == {"role": "system", "content": learn.SYSTEM}
    assert m[1]["content"] == "CORRECTION:\nTEXT\n\nLESSONS WE ALREADY HAVE (do not repeat them):\n- [a] one\n- [b] two"
    for word in ("ONE", "general", "- [", "NONE"):
        assert word in learn.SYSTEM


class FakeGateway:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []
        self.models = []

    def ensure_model(self, model):
        self.models.append(model)
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        return "c", self.answers.pop(0)


def test_ask(monkeypatch):
    monkeypatch.setattr(config, "LEARNER", {"model": "m", "effort": "none", "max_tokens": 50})
    gw = FakeGateway(["Thinking...\n  - [tests, old-tests] Change the tests that pin old behaviour.\nmore", "NONE"])
    c = {"id": "reset:T1:1", "text": "T"}
    assert learn.ask(gw, c, []) == (["tests", "old-tests"], "Change the tests that pin old behaviour.")
    assert gw.models == ["m"]
    assert gw.calls[0][1] == {"task": "learn", "role": "learner", "attempt": 1, "model": "m", "effort": "none",
                              "max_tokens": 50}
    assert gw.calls[0][0] == learn.messages(c, [])
    assert learn.ask(gw, c, []) is None


def test_is_duplicate():
    existing = ["Compare floats with a tolerance, never ==="]
    assert learn.is_duplicate("compare floats with a tolerance", existing)
    assert not learn.is_duplicate("Recompute the path when a tower is sold", existing)
    assert not learn.is_duplicate("anything", [])


def test_learn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LEARNER", {"model": "m", "effort": "none", "max_tokens": 50})
    lessons_path = tmp_path / "LESSONS.md"
    lessons_path.write_text("# Lessons\n\n- [tests, floats] Compare floats with a tolerance. (td)", encoding="utf-8")
    state = tmp_path / "state"
    state.mkdir()
    (state / "learned.json").write_text(json.dumps(["reset:T012:2"]), encoding="utf-8")
    gw = FakeGateway(["- [plan, old-tests] Name the old tests a change breaks.",
                      "- [tests] compare floats with a tolerance"])
    out = learn.learn(gw, [T1, T2], EVENTS, lessons_path, state, "towerdefense")
    assert out == {"corrections": 2, "added": 1, "duplicates": 1, "skipped": 0}
    lines = lessons_path.read_text(encoding="utf-8").splitlines()
    assert lines[-1] == "- [plan, old-tests] Name the old tests a change breaks. (towerdefense: reset:T012:1)"
    assert lines[-2] == "- [tests, floats] Compare floats with a tolerance. (td)"
    assert json.loads((state / "learned.json").read_text(encoding="utf-8")) == [
        "reset:T012:2", "reset:T012:1", "reset:T013:1"]
    # the second answer saw the first lesson already in the file
    assert "Name the old tests a change breaks." in gw.calls[1][0][1]["content"]
    assert learn.learn(FakeGateway([]), [T1, T2], EVENTS, lessons_path, state, "towerdefense") == {
        "corrections": 0, "added": 0, "duplicates": 0, "skipped": 0}


def test_learn_without_files(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LEARNER", {"model": "m", "effort": "none", "max_tokens": 50})
    gw = FakeGateway(["NONE"])
    out = learn.learn(gw, [T2], EVENTS, tmp_path / "new" / "LESSONS.md", tmp_path / "state", "p")
    assert out == {"corrections": 1, "added": 0, "duplicates": 0, "skipped": 1}
    assert json.loads((tmp_path / "state" / "learned.json").read_text(encoding="utf-8")) == ["reset:T013:1"]


# ---- was test_learn_drafts.py ----
# Tests for task learn_drafts (P11, 2026-11-20, user: Claude's fixes to drafted tests never became lessons - the
# "2 oz spice" unit trap was drafted wrong three times in one project). Every fix Claude makes to a drafted test
# carries a note "(Claude: <why>)" in the test file (a comment or a docstring); those notes are corrections.
#
# learn.draft_corrections(repo, test_dir="tests") -> list of {"id", "text"}, for every .py file under repo/test_dir
# (sorted paths) and every "(Claude:" in it, in order: the note is the text from "(Claude:" up to its matching ")"
# (parentheses inside count), over as many lines as it takes; on the lines after the first, a leading "#" and the
# spaces around it are dropped, and the lines are joined with one space. The note text is what follows "(Claude:",
# stripped. The test is the top-level function or class (codemap.scan_python) whose lines hold the "(Claude:",
# else "(module)". id = f"draft:{path}:{test}:{n}" (n counts the notes of that test from 1; path relative with "/");
# text = f"A person fixed a drafted test {path}::{test}: {note}".
# learn.learn(..., repo=None): when repo is given, draft_corrections(repo) are added to the corrections it learns
# from (after the others).


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


def test_quoted_markers_are_examples(tmp_path):
    """(Claude, 2026-11-21) A docstring that explains the format quotes it - '"(Claude: why)"' - and three junk lessons
    came from such a docstring; a marker right after a quote or a backtick is not a note."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_d.py").write_text(
        'def test_y():\n    """Notes look like "(Claude: why)" or `(Claude: why)`.\n    (Claude: a real one)"""\n',
        encoding="utf-8")
    assert [c["text"] for c in learn.draft_corrections(tmp_path)] == [
        "A person fixed a drafted test tests/test_d.py::test_y: a real one"]


def test_no_tests_folder(tmp_path):
    assert learn.draft_corrections(tmp_path) == []
