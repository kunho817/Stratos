"""Tests for task plantests_http_error: HTTPError ends only that task's draft.

In stratos/plantests.py, draft_tests wraps the test writer model call in
try/except urllib.error.HTTPError.  On exception:
  - for each path in task["tests"] append
    {"key", "file", "status": "call_error",
     "detail": str(e.read().decode())[:500]}
  - skip writing for that task (no test files written to root)
  - skip refcheck for that task
  - continue to the next task
No result entry with "call_error" is written for tasks that succeed."""

import io
import json
import urllib.error
from pathlib import Path

import pytest

from stratos import config, plantests, plan
from stratos.telemetry import Telemetry


def _http_error(body: bytes):
    fp = io.BytesIO(body)
    return urllib.error.HTTPError("http://127.0.0.1", 500, "err", {}, fp)


TASK_A = {"key": "a", "title": "T A", "goal": "Goal A.",
          "files": ["pkg/a.py"], "tests": ["tests/test_a.py", "tests/test_a2.py"],
          "protected": [], "after": [], "role": None}
TASK_B = {"key": "b", "title": "T B", "goal": "Goal B.",
          "files": ["pkg/b.py"], "tests": ["tests/test_b.py"],
          "protected": [], "after": [], "role": None}

ANSWER_B = "FILE: tests/test_b.py\n```python\ndef test_b(): pass\n```\n"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """config paths, stub subprocess calls, fake codemap / refcheck."""
    state = tmp_path / "state"
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", root)
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    monkeypatch.setattr(config, "MEMORY", False)
    monkeypatch.setattr(config, "REF_CHECK", True)
    monkeypatch.setattr(plantests, "check_draft", lambda r, p: ("collected", ""))
    monkeypatch.setattr(plantests, "suite_leaks", lambda r, p, ignore=(): [])
    monkeypatch.setattr(plantests, "draft_problems", lambda r, p: [])
    monkeypatch.setattr(plantests, "old_tests", lambda cmap, task: [])
    from stratos import codemap, refcheck
    monkeypatch.setattr(codemap, "build", lambda r: {"test_dir": "tests",
                                                      "files": {}, "imports": {}})
    monkeypatch.setattr(plan, "repo_summary", lambda root: "SUMMARY")
    ref_calls = []
    def fake_refcheck(gw, pid, task, root, tests, extra=None):
        ref_calls.append(task["key"])
        return {"status": "agree", "total": 1, "failing": [],
                "first_error": "", "files": [],
                "mutation": {"total": 3, "killed": 2, "survivors": []}}
    monkeypatch.setattr(refcheck, "check", fake_refcheck)
    return root, state, ref_calls


class FakeGateway:
    """A bytes response raises HTTPError with that body; a str returns
    ("c<n>", text).  Calls are consumed in order."""

    def __init__(self, telemetry, responses):
        self.telemetry = telemetry
        self._responses = list(responses)
        self._idx = 0
        self.calls = []

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append((list(messages), kw))
        resp = self._responses[self._idx]
        self._idx += 1
        if isinstance(resp, bytes):
            raise _http_error(resp)
        return f"c{self._idx}", resp


def _run(env, tasks, responses):
    root, state, ref = env
    pid = plan.save_plan(state, "goal", tasks)
    gw = FakeGateway(Telemetry(state / "t.jsonl"), responses)
    results = plantests.draft_tests(gw, pid, root, state, log=lambda s: None)
    return gw, pid, results, ref


# ---- 1. call_error entries for every test file of the failed task ----
def test_call_error_for_all_test_files(env):
    # TASK_A has 2 test files, TASK_B has 1.
    # Task A's chat raises HTTPError → 2 call_error entries.
    # Task B's chat succeeds → 1 collected entry.
    # Expected: 2 call_error + 1 collected = 3 total.
    gw, pid, results, ref = _run(env, [TASK_A, TASK_B],
                                 [b"body", ANSWER_B])
    a_entries = [r for r in results if r["key"] == "a"]
    # expected: 2 entries (test_a.py, test_a2.py)
    assert len(a_entries) == 2
    for e in a_entries:
        # expected status
        assert e["status"] == "call_error"
    # expected: task b's single entry is collected, not call_error
    b_entries = [r for r in results if r["key"] == "b"]
    assert len(b_entries) == 1
    assert b_entries[0]["status"] == "collected"
    # expected: 3 total results
    assert len(results) == 3


# ---- 2. detail is str(e.read().decode()) ----
def test_call_error_detail_is_decoded_body(env):
    body = b"Error: not found"
    # decoded: "Error: not found"
    # str(...) is the same string
    # len("Error: not found") = 16, ≤ 500 → no truncation
    # expected detail == "Error: not found"
    gw, pid, results, ref = _run(env, [TASK_A], [body])
    assert results[0]["detail"] == "Error: not found"
    # expected length: 16
    assert len(results[0]["detail"]) == 16


# ---- 3. detail truncated to 500 characters ----
def test_call_error_detail_truncated_to_500(env):
    body = b"x" * 600
    # decoded: 600 x's; [:500] → 500 x's
    # expected len == 500
    gw, pid, results, ref = _run(env, [TASK_A], [body])
    assert len(results[0]["detail"]) == 500
    assert results[0]["detail"] == "x" * 500


# ---- 4. body exactly 500 chars: not truncated ----
def test_body_exactly_500_not_truncated(env):
    body = b"x" * 500
    # decoded 500 chars; [:500] keeps all 500
    # expected len == 500
    gw, pid, results, ref = _run(env, [TASK_A], [body])
    assert len(results[0]["detail"]) == 500
    assert results[0]["detail"] == "x" * 500


# ---- 5. body under 500: no truncation ----
def test_body_under_500_not_truncated(env):
    body = b"short"
    # decoded "short", 5 chars, ≤ 500
    # expected detail == "short"
    gw, pid, results, ref = _run(env, [TASK_A], [body])
    assert results[0]["detail"] == "short"
    # expected len == 5
    assert len(results[0]["detail"]) == 5


# ---- 6. no test files written for the failed task ----
def test_no_files_written_for_failed_task(env):
    # TASK_A chat raises HTTPError → its test files must NOT appear on disk.
    # TASK_B chat succeeds → its test file IS written.
    # expected: test_a.py missing, test_a2.py missing, test_b.py present.
    gw, pid, results, ref = _run(env, [TASK_A, TASK_B],
                                 [b"err", ANSWER_B])
    assert not (env[0] / "tests" / "test_a.py").exists()
    assert not (env[0] / "tests" / "test_a2.py").exists()
    assert (env[0] / "tests" / "test_b.py").exists()


# ---- 7. refcheck is skipped for the failed task ----
def test_refcheck_skipped_for_failed_task(env):
    root, state, ref_calls = env
    # TASK_A: no files written → task_written["a"] is empty → refcheck skipped
    # TASK_B: files written → refcheck runs for "b"
    # expected: ref_calls == ["b"] (only one call, for task b)
    gw, pid, results, ref = _run(env, [TASK_A, TASK_B],
                                 [b"err", ANSWER_B])
    # expected: only task b
    assert ref_calls == ["b"]


# ---- 8. the loop continues: next task runs after the failure ----
def test_next_task_continues_after_http_error(env):
    # TASK_A fails; TASK_B should still get its result.
    # expected: results contains a task-b entry with status "collected".
    gw, pid, results, ref = _run(env, [TASK_A, TASK_B],
                                 [b"err", ANSWER_B])
    assert any(r["key"] == "b" and r["status"] == "collected"
               for r in results)
    # expected: task b's file was written
    assert (env[0] / "tests" / "test_b.py").exists()


# ---- 9. successful tasks have no call_error entries ----
def test_no_call_error_for_successful_task(env):
    # TASK_B alone, chat succeeds.
    # expected: 1 result, status "collected", no "call_error" anywhere.
    gw, pid, results, ref = _run(env, [TASK_B], [ANSWER_B])
    assert len(results) == 1
    assert results[0]["status"] == "collected"
    for r in results:
        assert r["status"] != "call_error"


# ---- 10. call_error entries carry key, file, status, detail ----
def test_call_error_entries_have_all_fields(env):
    body = b"body text here"
    # TASK_A has 2 test files → 2 entries
    # expected: len == 2
    gw, pid, results, ref = _run(env, [TASK_A], [body])
    assert len(results) == 2
    for r in results:
        # expected: all four keys present
        assert r["key"] == "a"
        assert r["file"] in ("tests/test_a.py", "tests/test_a2.py")
        assert r["status"] == "call_error"
        assert r["detail"] == "body text here"


# ---- 11. no test_draft telemetry events for the failed task ----
def test_no_test_draft_telemetry_for_call_error(env):
    # The inner loop (which records test_draft events) is skipped for
    # the failed task, so no test_draft events exist for key "a".
    # expected: 0 test_draft events
    gw, pid, results, ref = _run(env, [TASK_A], [b"err"])
    events = [e for e in gw.telemetry.load() if e["kind"] == "test_draft"]
    # expected: zero test_draft events
    assert len(events) == 0
