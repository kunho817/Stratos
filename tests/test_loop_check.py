"""Tests for task T048: loop.check_answer, the judging of one model answer, taken out of write_task so that other
callers (the replay command of T049) judge answers exactly like the task loop.

check_answer(task, wt, text, finish=None) -> (result, detail)
    task: a task dict (files, protected, tests, goal); wt: the folder the files are written to; text: the model's answer;
    finish: the call's finish reason (gw.last_finish), or None.
    - no FILE blocks for the task's files -> "no_files", detail "the answer held no FILE blocks for the task's files";
      when finish is "tool_calls" the detail is instead the message that there are no tools here (it says "no tools").
    - the answer drops existing top-level definitions (patch.dropped_definitions(wt, files, goal)) -> "dropped_defs",
      detail naming each path and its dropped names; nothing is written and no tests run.
    - patch.apply_files raises PatchRefused -> "refused", detail the exception text.
    - otherwise the files are written and verify.run_tests(wt, task["tests"]) decides: "passed" or "failed", detail
      the test output.
    - when finish is "length" and the result is not "passed", the detail starts with the cut-off message (it says
      "cut off") followed by the detail above.
write_task keeps its behaviour and calls check_answer with getattr(gw, "last_finish", None).
"""
from stratos import loop, verify

TASK = {"id": "T900", "files": ["pkg/a.py"], "protected": ["tests/test_a.py"], "tests": ["tests/test_a.py"],
        "goal": "Add Y to pkg/a.py."}
GOOD = "FILE: pkg/a.py\n```python\ndef keep():\n    return 1\n\nY = 2\n```\n"


def setup(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def keep():\n    return 1\n", encoding="utf-8")
    return tmp_path


def test_no_files(tmp_path):
    wt = setup(tmp_path)
    assert loop.check_answer(TASK, wt, "no blocks here") == (
        "no_files", "the answer held no FILE blocks for the task's files")
    result, detail = loop.check_answer(TASK, wt, "no blocks here", finish="tool_calls")
    assert result == "no_files" and "no tools" in detail


def test_dropped_defs_write_nothing(tmp_path, monkeypatch):
    wt = setup(tmp_path)
    ran = []
    monkeypatch.setattr(verify, "run_tests", lambda w, t: ran.append(t) or (True, "ok"))
    result, detail = loop.check_answer(TASK, wt, "FILE: pkg/a.py\n```python\nY = 2\n```\n")
    assert result == "dropped_defs" and "pkg/a.py: keep" in detail
    assert ran == [] and "def keep" in (wt / "pkg" / "a.py").read_text(encoding="utf-8")


def test_refused(tmp_path):
    wt = setup(tmp_path)
    task = dict(TASK, files=[])
    result, detail = loop.check_answer(task, wt, "FILE: tests/test_a.py\n```python\nX = 1\n```\n")
    assert result == "refused" and "tests/test_a.py" in detail


def test_passed_and_failed(tmp_path, monkeypatch):
    wt = setup(tmp_path)
    monkeypatch.setattr(verify, "run_tests", lambda w, t: (t == ["tests/test_a.py"], "1 passed"))
    assert loop.check_answer(TASK, wt, GOOD) == ("passed", "1 passed")
    assert "Y = 2" in (wt / "pkg" / "a.py").read_text(encoding="utf-8")
    monkeypatch.setattr(verify, "run_tests", lambda w, t: (False, "FAILED tests/test_a.py::test_y"))
    assert loop.check_answer(TASK, wt, GOOD) == ("failed", "FAILED tests/test_a.py::test_y")


def test_cut_off_answers(tmp_path, monkeypatch):
    wt = setup(tmp_path)
    monkeypatch.setattr(verify, "run_tests", lambda w, t: (False, "FAILED x"))
    result, detail = loop.check_answer(TASK, wt, GOOD, finish="length")
    assert result == "failed" and "cut off" in detail and detail.endswith("FAILED x")
    monkeypatch.setattr(verify, "run_tests", lambda w, t: (True, "ok"))
    assert loop.check_answer(TASK, wt, GOOD, finish="length") == ("passed", "ok")
