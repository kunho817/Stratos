"""Tests for task plantests_cases_http: HTTPError guard in the CASES branch of draft_tests.

In stratos/plantests.py, draft_tests's CASES branch (a task whose "cases" list has
non-plain lines, so the test writer model is asked) wraps _ask_test_writer in
try/except urllib.error.HTTPError exactly as the non-CASES branch does.
On HTTPError:
  - for each path in task["tests"] append
    {"key", "file", "status": "call_error",
     "detail": str(e.read().decode("utf-8", errors="replace"))[:500]}
  - skip writing any files for that task
  - skip the reference check for that task
  - continue the loop to the next task
A task without "cases", or whose cases are all plain (no model call), is unaffected.
"""

import io
import json
import urllib.error
from pathlib import Path

import pytest

from stratos import codemap, config, plantests, plan
from stratos.telemetry import Telemetry


def _http_error(body: bytes):
    fp = io.BytesIO(body)
    return urllib.error.HTTPError("http://127.0.0.1", 500, "err", {}, fp)


# TASK_CASES has "cases" with one plain line and one "other" line
# (the "other" line makes cases.parse return parsed["other"] non-empty,
# so the model is asked in the CASES branch).
TASK_CASES = {
    "key": "a",
    "title": "T A",
    "goal": "Goal A.",
    "files": ["pkg/a.py"],
    "tests": ["tests/test_a.py", "tests/test_a2.py"],
    "protected": [],
    "after": [],
    "role": None,
    "cases": ["pkg.a.f(1) == 2", "f reads the file it is given"],
}

TASK_B = {
    "key": "b",
    "title": "T B",
    "goal": "Goal B.",
    "files": ["pkg/b.py"],
    "tests": ["tests/test_b.py"],
    "protected": [],
    "after": [],
    "role": None,
}

ANSWER_B = "FILE: tests/test_b.py\n```python\ndef test_b(): pass\n```\n"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """config paths, stubs for check_draft/suite_leaks/draft_problems, fake codemap/refcheck."""
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
    from stratos import refcheck
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
    """bytes → raise HTTPError with that body; str → ("c<n>", text).
    Calls are consumed in order."""

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


# 1. CASES task gets call_error for every test file
def test_cases_call_error_for_all_test_files(env):
    # TASK_CASES has 2 test files. Its cases branch asks the model → HTTPError.
    # TASK_B (no cases) succeeds.
    # Expected: 2 call_error (a) + 1 collected (b) = 3.
    gw, pid, results, ref = _run(env, [TASK_CASES, TASK_B],
                                  [b"body", ANSWER_B])
    a_entries = [r for r in results if r["key"] == "a"]
    # expected: 2 entries
    assert len(a_entries) == 2
    for e in a_entries:
        # expected status
        assert e["status"] == "call_error"
    b_entries = [r for r in results if r["key"] == "b"]
    # expected: task b collected
    assert len(b_entries) == 1
    assert b_entries[0]["status"] == "collected"
    # expected: 3 total
    assert len(results) == 3


# 2. detail is decoded body
def test_cases_call_error_detail_is_decoded_body(env):
    body = b"Error: not found"
    # decoded: "Error: not found"
    # 16 chars ≤ 500 → no truncation
    # expected: detail == "Error: not found"
    gw, pid, results, ref = _run(env, [TASK_CASES], [body])
    assert results[0]["detail"] == "Error: not found"
    # expected len: 16
    assert len(results[0]["detail"]) == 16


# 3. detail truncated to 500
def test_cases_detail_truncated_to_500(env):
    body = b"x" * 600
    # decoded 600 chars; [:500] → 500
    # expected: len == 500, all "x"
    gw, pid, results, ref = _run(env, [TASK_CASES], [body])
    assert len(results[0]["detail"]) == 500
    assert results[0]["detail"] == "x" * 500


# 4. body exactly 500: not truncated
def test_cases_body_exactly_500_not_truncated(env):
    body = b"x" * 500
    # decoded 500; [:500] keeps all
    # expected: len == 500
    gw, pid, results, ref = _run(env, [TASK_CASES], [body])
    assert len(results[0]["detail"]) == 500


# 5. body under 500: no truncation
def test_cases_body_under_500_not_truncated(env):
    body = b"short"
    # decoded "short", 5 chars
    # expected: detail == "short"
    gw, pid, results, ref = _run(env, [TASK_CASES], [body])
    assert results[0]["detail"] == "short"
    # expected len: 5
    assert len(results[0]["detail"]) == 5


# 6. no files written for the CASES-failed task
def test_cases_no_files_written_for_failed_task(env):
    # TASK_CASES raises HTTPError → test_a.py, test_a2.py must NOT appear.
    # TASK_B succeeds → test_b.py IS written.
    # expected: test_a.py absent, test_a2.py absent, test_b.py present
    gw, pid, results, ref = _run(env, [TASK_CASES, TASK_B],
                                  [b"err", ANSWER_B])
    root = env[0]
    assert not (root / "tests" / "test_a.py").exists()
    assert not (root / "tests" / "test_a2.py").exists()
    # expected: task b's file exists
    assert (root / "tests" / "test_b.py").exists()


# 7. refcheck skipped for the CASES-failed task
def test_cases_refcheck_skipped_for_failed_task(env):
    root, state, ref_calls = env
    # TASK_CASES: no files written → task_written["a"] empty → refcheck skipped
    # TASK_B: files written → refcheck runs
    # expected: ref_calls == ["b"]
    gw, pid, results, ref = _run(env, [TASK_CASES, TASK_B],
                                  [b"err", ANSWER_B])
    # expected: only task b
    assert ref_calls == ["b"]


# 8. loop continues: next task runs after CASES failure
def test_cases_next_task_continues_after_http_error(env):
    # TASK_CASES fails; TASK_B must still get its collected result.
    # expected: results has task b with status "collected"
    gw, pid, results, ref = _run(env, [TASK_CASES, TASK_B],
                                  [b"err", ANSWER_B])
    # expected: task b collected
    assert any(r["key"] == "b" and r["status"] == "collected" for r in results)
    # expected: task b file written
    assert (env[0] / "tests" / "test_b.py").exists()


# 9. successful tasks have no call_error
def test_cases_no_call_error_for_successful_task(env):
    # TASK_B alone (no cases), chat succeeds.
    # expected: 1 result, "collected", no call_error
    gw, pid, results, ref = _run(env, [TASK_B], [ANSWER_B])
    # expected: 1 result
    assert len(results) == 1
    assert results[0]["status"] == "collected"
    # expected: no call_error
    for r in results:
        assert r["status"] != "call_error"


# 10. call_error entries carry key, file, status, detail
def test_cases_call_error_entries_have_all_fields(env):
    body = b"body text here"
    # TASK_CASES has 2 test files → 2 entries
    # expected: len == 2
    gw, pid, results, ref = _run(env, [TASK_CASES], [body])
    assert len(results) == 2
    for r in results:
        # expected: key is "a"
        assert r["key"] == "a"
        # expected: file is one of the two test paths
        assert r["file"] in ("tests/test_a.py", "tests/test_a2.py")
        # expected: status
        assert r["status"] == "call_error"
        # expected: detail
        assert r["detail"] == "body text here"


# 11. no test_draft telemetry for the CASES-failed task
def test_cases_no_test_draft_telemetry_for_call_error(env):
    # The inner write/check loop is skipped, so no test_draft events for "a".
    # expected: 0 test_draft events
    gw, pid, results, ref = _run(env, [TASK_CASES], [b"err"])
    events = [e for e in gw.telemetry.load() if e["kind"] == "test_draft"]
    # expected: zero
    assert len(events) == 0


# 12. plain cases (all-plain) bypass the model → HTTPError irrelevant
def test_cases_all_plain_no_model_call(env):
    # A task whose cases are all plain → cases.parse gives parsed["other"] empty
    # → no model call, so no HTTPError.
    plain = {
        "key": "p", "title": "T P", "goal": "Goal P.",
        "files": ["pkg/p.py"],
        "tests": ["tests/test_p.py"],
        "protected": [], "after": [], "role": None,
        "cases": ["pkg.p.f(1) == 2"],
    }
    # TASK_B succeeds with ANSWER_B.
    # No HTTPError needed.
    gw, pid, results, ref = _run(env, [plain, TASK_B], [ANSWER_B, ANSWER_B])
    # expected: task p status is "collected" (written from cases, no model)
    p_entries = [r for r in results if r["key"] == "p"]
    assert len(p_entries) == 1
    # expected: not call_error
    assert p_entries[0]["status"] == "collected"
    # expected: the file was written
    assert (env[0] / "tests" / "test_p.py").exists()


# 13. CASES HTTPError does not affect the answer file directory
def test_cases_no_answer_file_written_for_failed(env):
    # _ask_test_writer writes the answer file inside, so HTTPError before
    # gw.chat means no answer file for key "a".
    # TASK_B writes its answer file.
    # expected: answers dir has P001-b-tests.md, no P001-a-tests.md
    gw, pid, results, ref = _run(env, [TASK_CASES, TASK_B],
                                  [b"err", ANSWER_B])
    state = env[1]
    answers = state / "answers"
    # expected: b answer exists
    assert (answers / f"{pid}-b-tests.md").exists()
    # expected: a answer does not
    assert not (answers / f"{pid}-a-tests.md").exists()


# 14. CASES HTTPError: entries have exactly the right status, no extra keys
def test_cases_call_error_no_extraneous_keys(env):
    # expected keys: key, file, status, detail (no refcheck, no lint, no outdated)
    gw, pid, results, ref = _run(env, [TASK_CASES], [b"err"])
    for r in results:
        # expected: exactly 4 keys
        assert set(r.keys()) == {"key", "file", "status", "detail"}
        # expected: status
        assert r["status"] == "call_error"


# 15. CASES HTTPError in a three-task plan: middle fails, last succeeds
def test_cases_middle_fails_last_succeeds(env):
    TASK_C = {
        "key": "c", "title": "T C", "goal": "Goal C.",
        "files": ["pkg/c.py"], "tests": ["tests/test_c.py"],
        "protected": [], "after": [], "role": None,
    }
    # responses: TASK_CASES → HTTPError, TASK_B → HTTPError, TASK_C → answer
    # expected: a=2 call_error, b=1 call_error, c=1 collected = 4
    gw, pid, results, ref = _run(env, [TASK_CASES, TASK_B, TASK_C],
                                  [b"err", b"err", ANSWER_B])
    # expected: 4 results
    assert len(results) == 4
    # expected: c collected
    c_entries = [r for r in results if r["key"] == "c"]
    assert len(c_entries) == 1
    assert c_entries[0]["status"] == "collected"
    # expected: no call_error for c
    assert c_entries[0]["status"] != "call_error"
    # expected: c's file written
    assert (env[0] / "tests" / "test_c.py").exists()
