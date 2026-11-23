"""Tests for task plantests_second_error: second_opinion keeps first result on second error.

In plantests.second_opinion, right after the ref_check telemetry record of the second check,
when r2["status"] == "error":
  log f"{key}: second reference check gave error ({r2.get('first_error', '')}); keeping the first result"
  return (first, {})
No other code in second_opinion changes. When the status is not "error", existing behaviour
continues (suspect, repair, recheck).
"""

import json
from pathlib import Path

from stratos import codemap, config, plan, plantests, refcheck
from stratos.telemetry import Telemetry

# ---- fixed data ----

TASK = {"key": "a", "title": "T A", "goal": "Goal A.",
        "files": ["pkg/a.py"], "tests": ["tests/test_a.py"],
        "protected": [], "after": [], "role": None}

DRAFT_CONTENT = "def test_x(): pass\ndef test_y(): pass\ndef test_z(): pass\n"
REPAIRED_CONTENT = "def test_y():\n    # from facts\n    assert True\n"
REPAIRED_ANSWER = "FILE: tests/test_a.py\n```python\n" + REPAIRED_CONTENT + "```\n"

FIRST_REF = {"status": "flagged", "total": 3, "failing": ["test_x", "test_y"],
             "first_error": "a1==a2", "files": [("pkg/a.py", "a1")],
             "output": "first ref output"}

# second check returns status "error" with a first_error string
SECOND_ERROR_REF = {"status": "error", "total": 0, "failing": [],
                    "first_error": "no file in the answer", "files": [], "output": ""}

# second check returns status "error" with first_error = ""
SECOND_ERROR_EMPTY = {"status": "error", "total": 0, "failing": [],
                      "first_error": "", "files": [], "output": ""}

# second check returns status "error" with no first_error key at all
SECOND_ERROR_NO_KEY = {"status": "error", "total": 0, "failing": [],
                       "files": [], "output": ""}

SECOND_REF = {"status": "flagged", "total": 3, "failing": ["test_y", "test_z"],
              "first_error": "a3==a4", "files": [("pkg/a.py", "a2")],
              "output": "second ref output"}

REPAIRED_REF = {"status": "agree", "total": 3, "failing": [], "first_error": "",
                "files": [("pkg/a.py", "a3")], "output": "repaired ref output"}

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


def _plan(pid="P001"):
    return {"id": pid, "goal": "the goal", "tasks": [TASK], "status": "draft", "hash": "h"}


def _call(tmp_path, monkeypatch, gw, ref, first, refs):
    root, state = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(refcheck, "check", ref.fake)
    (root / "tests" / "test_a.py").write_text(DRAFT_CONTENT, encoding="utf-8")
    log = []
    result, extra = plantests.second_opinion(
        gw, "P001", _plan(), 0, TASK, root, ["tests/test_a.py"],
        list(refs), first, {"test_dir": "tests", "files": {}, "imports": {}},
        state / "answers", log.append)
    return result, extra, log, gw, ref


def _write_plan(state, tasks, pid="P001"):
    (state / "plans").mkdir(parents=True, exist_ok=True)
    (state / "plans" / f"{pid}.json").write_text(
        json.dumps({"id": pid, "goal": "the goal", "tasks": tasks,
                    "status": "draft", "hash": "h"}), encoding="utf-8")


# ---- tests ----

def test_error_returns_first_and_empty(tmp_path, monkeypatch):
    # SECOND_ERROR_REF status="error" → second_opinion returns (first, {})
    # Expected: result == FIRST_REF
    # Expected: extra == {}
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [])
    ref = RefRecorder([SECOND_ERROR_REF])
    result, extra, _, _, _ = _call(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                                   [("pkg/a.py", "a1")])
    assert result == FIRST_REF
    assert extra == {}


def test_error_log_format(tmp_path, monkeypatch):
    # key="a", r2["first_error"]="no file in the answer"
    # Expected log line:
    #   "a: second reference check gave error (no file in the answer); keeping the first result"
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [])
    ref = RefRecorder([SECOND_ERROR_REF])
    _, _, log, _, _ = _call(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                            [("pkg/a.py", "a1")])
    want = "a: second reference check gave error (no file in the answer); keeping the first result"
    assert want in log


def test_error_empty_first_error(tmp_path, monkeypatch):
    # SECOND_ERROR_EMPTY first_error="" → r2.get("first_error","") = ""
    # Expected log: "a: second reference check gave error (); keeping the first result"
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [])
    ref = RefRecorder([SECOND_ERROR_EMPTY])
    _, _, log, _, _ = _call(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                            [("pkg/a.py", "a1")])
    want = "a: second reference check gave error (); keeping the first result"
    assert want in log


def test_error_missing_first_error_key(tmp_path, monkeypatch):
    # SECOND_ERROR_NO_KEY has no "first_error" key
    # r2.get("first_error", "") → ""
    # Expected log: "a: second reference check gave error (); keeping the first result"
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [])
    ref = RefRecorder([SECOND_ERROR_NO_KEY])
    _, _, log, _, _ = _call(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                            [("pkg/a.py", "a1")])
    want = "a: second reference check gave error (); keeping the first result"
    assert want in log


def test_error_no_repair_no_chat(tmp_path, monkeypatch):
    # status "error" → return early; no repair round, no gw.chat
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [REPAIRED_ANSWER])
    ref = RefRecorder([SECOND_ERROR_REF])
    _, _, _, gw, ref = _call(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                              [("pkg/a.py", "a1")])
    # Expected: 1 refcheck call (the second check), 0 gw.chat calls
    assert len(ref.calls) == 1
    assert len(gw.calls) == 0


def test_error_no_suspect_computation(tmp_path, monkeypatch):
    # status "error" → return before suspect intersection
    # Expected: 0 ref_suspect telemetry events
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [])
    ref = RefRecorder([SECOND_ERROR_REF])
    _, _, _, gw, _ = _call(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                           [("pkg/a.py", "a1")])
    events = [e for e in gw.telemetry.load() if e["kind"] == "ref_suspect"]
    # Expected: 0
    assert len(events) == 0


def test_error_telemetry_recorded(tmp_path, monkeypatch):
    # The ref_check telemetry IS recorded before the error check
    # Expected: 1 ref_check event with plan="P001", key="a", status="error"
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [])
    ref = RefRecorder([SECOND_ERROR_REF])
    _, _, _, gw, _ = _call(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                           [("pkg/a.py", "a1")])
    events = [e for e in gw.telemetry.load() if e["kind"] == "ref_check"]
    # Expected: 1
    assert len(events) == 1
    assert events[0]["plan"] == "P001"
    assert events[0]["key"] == "a"
    # Expected: status = "error"
    assert events[0]["status"] == "error"


def test_non_error_continues_suspect(tmp_path, monkeypatch):
    # SECOND_REF status="flagged" fails ["test_y","test_z"]
    # FIRST_REF fails ["test_x","test_y"]
    # intersection = {"test_y"}, sorted = ["test_y"]
    # Expected: 2 refcheck calls (second + recheck), 1 gw.chat (repair)
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [REPAIRED_ANSWER])
    ref = RefRecorder([SECOND_REF, REPAIRED_REF])
    result, extra, _, gw, ref = _call(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                                       [("pkg/a.py", "a1")])
    # Expected: 2 refcheck calls
    assert len(ref.calls) == 2
    # Expected: 1 gw.chat call
    assert len(gw.calls) == 1
    # Expected: extra["suspect"] == ["test_y"]
    assert extra["suspect"] == ["test_y"]


def test_non_error_no_suspect_returns_second(tmp_path, monkeypatch):
    # first fails ["test_x"], second fails ["test_y"] → empty intersection
    # status not "error", so existing path: return (r2, {})
    first2 = {"status": "flagged", "total": 3, "failing": ["test_x"],
              "first_error": "a1", "files": [("pkg/a.py", "a1")], "output": "out"}
    second2 = {"status": "flagged", "total": 3, "failing": ["test_y"],
               "first_error": "a2", "files": [("pkg/a.py", "a2")], "output": "out2"}
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [])
    ref = RefRecorder([second2])
    result, extra, _, gw, ref = _call(tmp_path, monkeypatch, gw, ref, first2,
                                       [("pkg/a.py", "a1")])
    # Expected: result = second2, extra = {}
    assert result == second2
    assert extra == {}
    # Expected: no ref_suspect telemetry
    events = [e for e in gw.telemetry.load() if e["kind"] == "ref_suspect"]
    # Expected: 0
    assert len(events) == 0


def test_error_returns_first_not_second(tmp_path, monkeypatch):
    # The return is (first, {}), not (r2, {})
    # Verify result is FIRST_REF (flagged), not SECOND_ERROR_REF
    gw = FakeGW(Telemetry(tmp_path / "state" / "t.jsonl"), [])
    ref = RefRecorder([SECOND_ERROR_REF])
    result, extra, _, _, _ = _call(tmp_path, monkeypatch, gw, ref, FIRST_REF,
                                    [("pkg/a.py", "a1")])
    # Expected: result == FIRST_REF
    assert result == FIRST_REF
    # Expected: extra == {}
    assert extra == {}
    # Expected: result["status"] == "flagged", NOT "error"
    assert result["status"] == "flagged"


def test_draft_tests_second_error(tmp_path, monkeypatch):
    # draft_tests: first refcheck is flagged, REF_SECOND on → second_opinion called.
    # Second check returns error → second_opinion returns (first, {}).
    # Expected: entry["refcheck"] == FIRST_REF (flagged), no suspect key.
    root, state = _setup(tmp_path, monkeypatch)
    _write_plan(state, [TASK], "P001")
    gw = FakeGW(Telemetry(state / "t.jsonl"),
                ["FILE: tests/test_a.py\n```python\n" + DRAFT_CONTENT + "```\n"])
    ref = RefRecorder([FIRST_REF, SECOND_ERROR_REF])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    results = plantests.draft_tests(gw, "P001", root, state, log=lambda x: None)
    entry = [r for r in results if r["key"] == "a"][0]
    # Expected: refcheck is FIRST_REF (the flagged result), not the error
    assert entry["refcheck"] == FIRST_REF
    # Expected: no suspect key
    assert "suspect" not in entry
    # Expected: no repaired key
    assert "repaired" not in entry
