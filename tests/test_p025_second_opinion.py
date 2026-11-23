"""Tests for task P025: second_opinion restores each file individually from disk.

Before writing a new file, second_opinion reads each path's disk content into a dict
{path: text}. When a rewritten file fails check_draft, that file is restored to its own
saved text from the dict — not the joined text of every path. A task with two test
files gets each file back as it was: if the first passes check_draft and the second
fails, the first keeps its rewrite and the second is restored to its own original
content on disk.
"""

import json
from pathlib import Path

from stratos import codemap, config, plan, plantests, refcheck
from stratos.telemetry import Telemetry

# ---- fixed data ----

TASK_TWO = {"key": "a", "title": "T A", "goal": "Goal A.",
            "files": ["pkg/a.py"],
            "tests": ["tests/test_a.py", "tests/test_b.py"],
            "protected": [], "after": [], "role": None}

# Original disk content of each file (the "before" state)
ORIGINAL_A = "def test_a(): pass\n"
ORIGINAL_B = "def test_b(): pass\n"

# New content produced by the repair model
NEW_A = "def test_a():\n    assert True\n"
NEW_B = "def test_b():\n    assert False\n"

REPAIR_ANSWER_TWO = ('FILE: tests/test_a.py\n```python\n' + NEW_A
                     + '```\nFILE: tests/test_b.py\n```python\n' + NEW_B + '```\n')

FIRST_REF = {"status": "flagged", "total": 3, "failing": ["test_x", "test_y"],
             "first_error": "a1==a2", "files": [("pkg/a.py", "a1")],
             "output": "first ref output"}
SECOND_REF = {"status": "flagged", "total": 3, "failing": ["test_y", "test_z"],
              "first_error": "a3==a4", "files": [("pkg/a.py", "a2")],
              "output": "second ref output"}
# suspect = sorted(set(["test_x","test_y"]) & set(["test_y","test_z"])) = ["test_y"]

REPAIRED_REF = {"status": "agree", "total": 3, "failing": [], "first_error": "",
                "files": [("pkg/a.py", "a3")], "output": "repaired ref output"}

# Single-file task (for the "joined-text" regression test)
TASK_ONE = {"key": "a", "title": "T A", "goal": "Goal A.",
            "files": ["pkg/a.py"],
            "tests": ["tests/test_a.py"],
            "protected": [], "after": [], "role": None}

DRAFT_ONE = "def test_x(): pass\ndef test_y(): pass\n"
REPAIR_ONE = "def test_y():\n    assert True\n"
REPAIR_ANSWER_ONE = 'FILE: tests/test_a.py\n```python\n' + REPAIR_ONE + '```\n'

# ---- helpers ----

class FakeGW:
    def __init__(self, telemetry, answers):
        self.telemetry = telemetry
        self._answers = list(answers)
        self.models, self.calls = [], []

    def ensure_model(self, model):
        self.models.append(model)
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append((list(messages), kw))
        if self._answers:
            return f"c{len(self.calls)}", self._answers.pop(0)
        return f"c{len(self.calls)}", ""


class RefRecorder:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def fake(self, gw, pid, task, root, tests, extra=None, writer=None):
        self.calls.append({"writer": writer, "extra": list(extra) if extra else [],
                           "tests": list(tests)})
        return self.results.pop(0)


def _setup(tmp_path, monkeypatch):
    state = tmp_path / "state"
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", root)
    monkeypatch.setattr(config, "PLANNER",
                        {"model": "planner-m", "effort": "low", "max_tokens": 200})
    monkeypatch.setattr(config, "MEMORY", False)
    monkeypatch.setattr(config, "REF_CHECK", True, raising=False)
    monkeypatch.setattr(config, "REF_SECOND", True, raising=False)
    monkeypatch.setattr(plantests, "check_draft", lambda r, p: ("collected", ""))
    monkeypatch.setattr(plantests, "suite_leaks", lambda r, p, ignore=(): [])
    monkeypatch.setattr(plantests, "draft_problems", lambda r, p: [])
    monkeypatch.setattr(plantests, "risky_patterns", lambda t: [])
    monkeypatch.setattr(plantests, "old_tests", lambda cmap, task: [])
    monkeypatch.setattr(codemap, "build",
                        lambda r: {"test_dir": "tests", "files": {}, "imports": {}})
    monkeypatch.setattr(plan, "repo_summary", lambda r: "SUMMARY")
    return root, state


def _plan(tasks, pid="P001"):
    return {"id": pid, "goal": "the goal", "tasks": tasks, "status": "draft", "hash": "h"}


def _write_plan(state, tasks, pid="P001"):
    (state / "plans").mkdir(parents=True, exist_ok=True)
    (state / "plans" / f"{pid}.json").write_text(
        json.dumps({"id": pid, "goal": "the goal", "tasks": tasks,
                    "status": "draft", "hash": "h"}), encoding="utf-8")


# ---- tests ----

def test_two_files_first_passes_second_fails_restored(tmp_path, monkeypatch):
    """Task has two test files. Repair writes both.
    check_draft passes for test_a.py, fails for test_b.py.
    Second restored to its own disk content; first keeps its rewrite."""
    root, state = _setup(tmp_path, monkeypatch)

    # check_draft: collected for test_a.py, syntax_error for test_b.py
    def fake_check(r, p):
        if p == "tests/test_a.py":
            return ("collected", "")
        return ("syntax_error", "bad")
    monkeypatch.setattr(plantests, "check_draft", fake_check)

    # Put the original content on disk for both files
    (root / "tests" / "test_a.py").write_text(ORIGINAL_A, encoding="utf-8")
    (root / "tests" / "test_b.py").write_text(ORIGINAL_B, encoding="utf-8")

    gw = FakeGW(Telemetry(state / "t.jsonl"), [REPAIR_ANSWER_TWO])
    ref = RefRecorder([SECOND_REF])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    log = []

    result, extra = plantests.second_opinion(
        gw, "P001", _plan([TASK_TWO]), 0, TASK_TWO, root,
        ["tests/test_a.py", "tests/test_b.py"],
        [("pkg/a.py", "a1")], FIRST_REF,
        {"test_dir": "tests", "files": {}, "imports": {}},
        state / "answers", log.append)

    # First file keeps its rewrite
    # Expected: test_a.py on disk == NEW_A (the repair content, not ORIGINAL_A)
    assert (root / "tests" / "test_a.py").read_text(encoding="utf-8") == NEW_A

    # Second file restored to its own original disk content
    # Expected: test_b.py on disk == ORIGINAL_B (not NEW_B, not the joined text)
    assert (root / "tests" / "test_b.py").read_text(encoding="utf-8") == ORIGINAL_B

    # Repair did not succeed → result is the first reference
    # Expected: result == FIRST_REF
    assert result == FIRST_REF

    # extra has suspect, no repaired flag
    # suspect = sorted({"test_x","test_y"} & {"test_y","test_z"}) = ["test_y"]
    assert extra["suspect"] == ["test_y"]
    assert "repaired" not in extra


def test_single_file_restored_to_own_content(tmp_path, monkeypatch):
    """A task with one test file; repair writes it; check_draft fails.
    The file is restored to its own disk text, not the joined text of all paths."""
    root, state = _setup(tmp_path, monkeypatch)
    # check_draft always fails
    monkeypatch.setattr(plantests, "check_draft", lambda r, p: ("syntax_error", "bad"))

    # Single file has its original content on disk
    (root / "tests" / "test_a.py").write_text(DRAFT_ONE, encoding="utf-8")

    gw = FakeGW(Telemetry(state / "t.jsonl"), [REPAIR_ANSWER_ONE])
    ref = RefRecorder([SECOND_REF])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    log = []

    result, extra = plantests.second_opinion(
        gw, "P001", _plan([TASK_ONE]), 0, TASK_ONE, root,
        ["tests/test_a.py"],
        [("pkg/a.py", "a1")], FIRST_REF,
        {"test_dir": "tests", "files": {}, "imports": {}},
        state / "answers", log.append)

    # The file must be restored to its own original content, not the joined text
    # Expected: disk == DRAFT_ONE (the original single file text)
    assert (root / "tests" / "test_a.py").read_text(encoding="utf-8") == DRAFT_ONE

    # Expected: result == FIRST_REF, extra has suspect, no repaired
    assert result == FIRST_REF
    # suspect = sorted({"test_x","test_y"} & {"test_y","test_z"}) = ["test_y"]
    assert extra["suspect"] == ["test_y"]
    assert "repaired" not in extra


def test_two_files_both_pass_repair_succeeds(tmp_path, monkeypatch):
    """Task has two test files. Repair writes both.
    check_draft passes for both. Repair succeeds, re-check runs."""
    root, state = _setup(tmp_path, monkeypatch)
    # check_draft always passes
    monkeypatch.setattr(plantests, "check_draft", lambda r, p: ("collected", ""))

    # Put original content on disk
    (root / "tests" / "test_a.py").write_text(ORIGINAL_A, encoding="utf-8")
    (root / "tests" / "test_b.py").write_text(ORIGINAL_B, encoding="utf-8")

    gw = FakeGW(Telemetry(state / "t.jsonl"), [REPAIR_ANSWER_TWO])
    ref = RefRecorder([SECOND_REF, REPAIRED_REF])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    log = []

    result, extra = plantests.second_opinion(
        gw, "P001", _plan([TASK_TWO]), 0, TASK_TWO, root,
        ["tests/test_a.py", "tests/test_b.py"],
        [("pkg/a.py", "a1")], FIRST_REF,
        {"test_dir": "tests", "files": {}, "imports": {}},
        state / "answers", log.append)

    # Both files keep their repair content
    # Expected: test_a.py == NEW_A, test_b.py == NEW_B
    assert (root / "tests" / "test_a.py").read_text(encoding="utf-8") == NEW_A
    assert (root / "tests" / "test_b.py").read_text(encoding="utf-8") == NEW_B

    # Expected: result == REPAIRED_REF, extra = {"suspect": ["test_y"], "repaired": True}
    assert result == REPAIRED_REF
    assert extra["suspect"] == ["test_y"]
    assert extra.get("repaired") is True
