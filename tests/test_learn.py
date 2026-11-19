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
