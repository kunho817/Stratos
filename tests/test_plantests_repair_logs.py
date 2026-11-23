"""Tests for task plantests_repair_logs: second_opinion logs repair round failures.

In plantests.second_opinion, three early-return paths in the repair round now log one line each:
(1) _ask_test_writer raises:
    "key: repair round: the test writer failed: <error>"
(2) the answer has none of the task's test files:
    "key: repair round: the answer has none of the test files"
(3) a rewritten file fails check_draft (one line per such file):
    "key: repair round: <path> gave <status>; the earlier draft is kept"
Results dict and files stay unchanged in all three paths.
"""

import json
from pathlib import Path

from stratos import codemap, config, plan, plantests, refcheck
from stratos.telemetry import Telemetry

# ---- fixed data ----

TASK = {"key": "a", "title": "T A", "goal": "Goal A.",
        "files": ["pkg/a.py"], "tests": ["tests/test_a.py"],
        "protected": [], "after": [], "role": None}

TASK_TWO = {"key": "a", "title": "T A", "goal": "Goal A.",
            "files": ["pkg/a.py"], "tests": ["tests/test_a.py", "tests/test_b.py"],
            "protected": [], "after": [], "role": None}

DRAFT_CONTENT = "def test_x(): pass\ndef test_y(): pass\ndef test_z(): pass\n"

FIRST_REF = {"status": "flagged", "total": 3, "failing": ["test_x", "test_y"],
             "first_error": "a1==a2", "files": [("pkg/a.py", "a1")],
             "output": "first ref output"}

SECOND_REF = {"status": "flagged", "total": 3, "failing": ["test_y", "test_z"],
              "first_error": "a3==a4", "files": [("pkg/a.py", "a2")],
              "output": "second ref output"}
# suspect = sorted({"test_x","test_y"} & {"test_y","test_z"}) = ["test_y"]

REPAIRED_REF = {"status": "agree", "total": 3, "failing": [], "first_error": "",
                "files": [("pkg/a.py", "a3")], "output": "repaired ref output"}

REPAIR_ANSWER = "FILE: tests/test_a.py\n```python\ndef test_y():\n    assert True\n```\n"

REPAIR_ANSWER_TWO = ('FILE: tests/test_a.py\n```python\n'
                     + 'def test_a():\n    assert True\n'
                     + '```\nFILE: tests/test_b.py\n```python\n'
                     + 'def test_b():\n    assert False\n'
                     + '```\n')

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


def _run(tmp_path, monkeypatch, gw, ref, first, refs, task=TASK,
         paths=None, answers=None, check=None):
    root, state = _setup(tmp_path, monkeypatch)
    if check is not None:
        monkeypatch.setattr(plantests, "check_draft", check)
    monkeypatch.setattr(refcheck, "check", ref.fake)
    if paths is None:
        paths = task["tests"]
    for p in paths:
        (root / p).write_text(DRAFT_CONTENT, encoding="utf-8")
    log = []
    result, extra = plantests.second_opinion(
        gw, "P001", _plan([task]), 0, task, root, paths,
        list(refs), first, {"test_dir": "tests", "files": {}, "imports": {}},
        state / "answers", log.append)
    return result, extra, log, gw, ref, root


# ---- 1. writer raises: log format ----

def test_writer_failure_log_format(tmp_path, monkeypatch):
    # _ask_test_writer raises RuntimeError("model overloaded")
    # Expected log: "a: repair round: the test writer failed: model overloaded"
    def fake_writer(gw, pid, task, messages, model_cfg, answers_dir, root):
        raise RuntimeError("model overloaded")
    monkeypatch.setattr(plantests, "_ask_test_writer", fake_writer)
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [])
    ref = RefRecorder([SECOND_REF])
    _, _, log, _, _, _ = _run(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                              [("pkg/a.py", "a1")])
    # Expected: the log line
    want = "a: repair round: the test writer failed: model overloaded"
    assert want in log


# ---- 2. writer raises: result and extra ----

def test_writer_failure_result(tmp_path, monkeypatch):
    # suspect = sorted({"test_x","test_y"} & {"test_y","test_z"}) = ["test_y"]
    # Expected: result == FIRST_REF, extra == {"suspect": ["test_y"]}
    def fake_writer(gw, pid, task, messages, model_cfg, answers_dir, root):
        raise RuntimeError("boom")
    monkeypatch.setattr(plantests, "_ask_test_writer", fake_writer)
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [])
    ref = RefRecorder([SECOND_REF])
    result, extra, _, _, _, _ = _run(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                                      [("pkg/a.py", "a1")])
    assert result == FIRST_REF
    # suspect = ["test_y"]
    assert extra["suspect"] == ["test_y"]
    # Expected: no "repaired" key
    assert "repaired" not in extra


# ---- 3. writer raises: files unchanged ----

def test_writer_failure_files_unchanged(tmp_path, monkeypatch):
    # _ask_test_writer raises before writing any file
    # Expected: test_a.py on disk == DRAFT_CONTENT
    def fake_writer(gw, pid, task, messages, model_cfg, answers_dir, root):
        raise RuntimeError("boom")
    monkeypatch.setattr(plantests, "_ask_test_writer", fake_writer)
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [])
    ref = RefRecorder([SECOND_REF])
    _, _, _, _, _, root = _run(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                                [("pkg/a.py", "a1")])
    # Expected: original content preserved
    assert (root / "tests" / "test_a.py").read_text(encoding="utf-8") == DRAFT_CONTENT


# ---- 4. writer raises: no gw.chat call ----

def test_writer_failure_no_chat(tmp_path, monkeypatch):
    # _ask_test_writer raises before gw.chat
    # Expected: 0 gw.chat calls
    def fake_writer(gw, pid, task, messages, model_cfg, answers_dir, root):
        raise RuntimeError("boom")
    monkeypatch.setattr(plantests, "_ask_test_writer", fake_writer)
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [])
    ref = RefRecorder([SECOND_REF])
    _, _, _, gw, _, _ = _run(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                              [("pkg/a.py", "a1")])
    # Expected: 0
    assert len(gw.calls) == 0


# ---- 5. writer raises: only one refcheck call ----

def test_writer_failure_one_refcheck(tmp_path, monkeypatch):
    # The second check runs once; repair fails, so no recheck
    # Expected: 1 refcheck call
    def fake_writer(gw, pid, task, messages, model_cfg, answers_dir, root):
        raise RuntimeError("boom")
    monkeypatch.setattr(plantests, "_ask_test_writer", fake_writer)
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [])
    ref = RefRecorder([SECOND_REF])
    _, _, _, _, ref, _ = _run(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                               [("pkg/a.py", "a1")])
    # Expected: 1
    assert len(ref.calls) == 1


# ---- 6. no test files in answer: log format ----

def test_no_files_log_format(tmp_path, monkeypatch):
    # _ask_test_writer returns files not in task["tests"]
    # Expected log: "a: repair round: the answer has none of the test files"
    def fake_writer(gw, pid, task, messages, model_cfg, answers_dir, root):
        return [("other/path.py", "content")]
    monkeypatch.setattr(plantests, "_ask_test_writer", fake_writer)
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [])
    ref = RefRecorder([SECOND_REF])
    _, _, log, _, _, _ = _run(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                              [("pkg/a.py", "a1")])
    # Expected: the log line
    want = "a: repair round: the answer has none of the test files"
    assert want in log


# ---- 7. no test files: result and files ----

def test_no_files_result_and_files(tmp_path, monkeypatch):
    # suspect = ["test_y"]
    # Expected: result == FIRST_REF, extra has suspect, files unchanged
    def fake_writer(gw, pid, task, messages, model_cfg, answers_dir, root):
        return [("other/path.py", "content")]
    monkeypatch.setattr(plantests, "_ask_test_writer", fake_writer)
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [])
    ref = RefRecorder([SECOND_REF])
    result, extra, _, _, _, root = _run(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                                         [("pkg/a.py", "a1")])
    # Expected: result is first
    assert result == FIRST_REF
    # Expected: suspect = ["test_y"]
    assert extra["suspect"] == ["test_y"]
    # Expected: no repaired key
    assert "repaired" not in extra
    # Expected: files unchanged
    assert (root / "tests" / "test_a.py").read_text(encoding="utf-8") == DRAFT_CONTENT


# ---- 8. no test files: one chat call ----

def test_no_files_one_chat(tmp_path, monkeypatch):
    # _ask_test_writer calls gw.chat once, returns non-matching files
    # Expected: 1 gw.chat call
    def fake_writer(gw, pid, task, messages, model_cfg, answers_dir, root):
        # simulate the chat call inside
        call_id, answer = gw.chat(messages, task="x", role="test_writer",
                                  attempt=1, model="m", effort="low", max_tokens=100)
        return [("other/path.py", "content")]
    monkeypatch.setattr(plantests, "_ask_test_writer", fake_writer)
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [""])
    ref = RefRecorder([SECOND_REF])
    _, _, _, gw, _, _ = _run(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                              [("pkg/a.py", "a1")])
    # Expected: 1
    assert len(gw.calls) == 1


# ---- 9. check_draft fails: log format ----

def test_check_failure_log_format(tmp_path, monkeypatch):
    # Repair writes test_a.py; check_draft returns ("syntax_error", "bad")
    # Expected log: "a: repair round: tests/test_a.py gave syntax_error; the earlier draft is kept"
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [REPAIR_ANSWER])
    ref = RefRecorder([SECOND_REF])
    _, _, log, _, _, _ = _run(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                              [("pkg/a.py", "a1")],
                              check=lambda r, p: ("syntax_error", "bad"))
    # Expected: the log line with path, status
    want = "a: repair round: tests/test_a.py gave syntax_error; the earlier draft is kept"
    assert want in log


# ---- 10. check_draft fails: file restored ----

def test_check_failure_restored(tmp_path, monkeypatch):
    # Repair writes new content; check_draft fails; file restored to saved (DRAFT_CONTENT)
    # Expected: test_a.py == DRAFT_CONTENT
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [REPAIR_ANSWER])
    ref = RefRecorder([SECOND_REF])
    _, _, _, _, _, root = _run(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                                [("pkg/a.py", "a1")],
                                check=lambda r, p: ("syntax_error", "bad"))
    # Expected: original content restored
    assert (root / "tests" / "test_a.py").read_text(encoding="utf-8") == DRAFT_CONTENT


# ---- 11. check_draft fails for two files: two log lines ----

def test_check_failure_two_files(tmp_path, monkeypatch):
    # TASK_TWO has test_a.py and test_b.py; both fail check_draft
    # Expected: two log lines, one per path
    # Expected: log has:
    #   "a: repair round: tests/test_a.py gave import_error; the earlier draft is kept"
    #   "a: repair round: tests/test_b.py gave import_error; the earlier draft is kept"
    def fake_check(r, p):
        return ("import_error", "no module")
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [REPAIR_ANSWER_TWO])
    ref = RefRecorder([SECOND_REF])
    _, _, log, _, _, root = _run(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                                  [("pkg/a.py", "a1")], task=TASK_TWO,
                                  paths=["tests/test_a.py", "tests/test_b.py"],
                                  check=fake_check)
    # Expected: two log lines
    want_a = "a: repair round: tests/test_a.py gave import_error; the earlier draft is kept"
    want_b = "a: repair round: tests/test_b.py gave import_error; the earlier draft is kept"
    assert want_a in log
    # Expected: one per file
    assert want_b in log
    # Expected: both files restored to DRAFT_CONTENT
    assert (root / "tests" / "test_a.py").read_text(encoding="utf-8") == DRAFT_CONTENT
    assert (root / "tests" / "test_b.py").read_text(encoding="utf-8") == DRAFT_CONTENT


# ---- 12. check_draft fails: one chat call, one refcheck ----

def test_check_failure_one_chat_one_refcheck(tmp_path, monkeypatch):
    # Repair writes one file, check_draft fails, return before recheck
    # Expected: 1 gw.chat call, 1 refcheck call
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [REPAIR_ANSWER])
    ref = RefRecorder([SECOND_REF])
    _, _, _, gw, ref, _ = _run(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                                [("pkg/a.py", "a1")],
                                check=lambda r, p: ("syntax_error", "bad"))
    # Expected: 1 chat
    assert len(gw.calls) == 1
    # Expected: 1 refcheck (the second check; no recheck)
    assert len(ref.calls) == 1


# ---- 13. check_draft fails: result is first, no repaired key ----

def test_check_failure_result(tmp_path, monkeypatch):
    # suspect = ["test_y"]
    # Expected: result == FIRST_REF, extra == {"suspect": ["test_y"]}, no "repaired"
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [REPAIR_ANSWER])
    ref = RefRecorder([SECOND_REF])
    result, extra, _, _, _, _ = _run(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                                      [("pkg/a.py", "a1")],
                                      check=lambda r, p: ("syntax_error", "bad"))
    # Expected: result is the first reference
    assert result == FIRST_REF
    # Expected: suspect = ["test_y"]
    assert extra["suspect"] == ["test_y"]
    # Expected: no repaired key
    assert "repaired" not in extra


# ---- 14. writer raises: error text appears in log ----

def test_writer_failure_specific_error_text(tmp_path, monkeypatch):
    # The exception's str() must appear in the log line
    # Expected: "connection reset" is in the log line
    def fake_writer(gw, pid, task, messages, model_cfg, answers_dir, root):
        raise ConnectionError("connection reset")
    monkeypatch.setattr(plantests, "_ask_test_writer", fake_writer)
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [])
    ref = RefRecorder([SECOND_REF])
    _, _, log, _, _, _ = _run(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                              [("pkg/a.py", "a1")])
    # Expected: the error text is in the log
    assert any("connection reset" in line for line in log)


# ---- 15. check_draft status string in log ----

def test_check_failure_status_in_log(tmp_path, monkeypatch):
    # check_draft returns ("import_error", "no module"); the status is in the log
    # Expected: "import_error" appears in the log line
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [REPAIR_ANSWER])
    ref = RefRecorder([SECOND_REF])
    _, _, log, _, _, _ = _run(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                              [("pkg/a.py", "a1")],
                              check=lambda r, p: ("import_error", "x"))
    # Expected: status "import_error" is in the log line
    assert any("import_error" in line for line in log)
    # Expected: "the earlier draft is kept" is in the log line
    assert any("the earlier draft is kept" in line for line in log)
