"""Tests for task plantests_second_ref: second reference check and suspect/repair in draft_tests.

config.REF_SECOND: os.environ.get("STRATOS_REF_SECOND", "1") != "0".
conftest sets config.REF_SECOND False for every test.

In plantests.draft_tests: when the first refcheck is "flagged" and REF_SECOND is on,
refcheck.check is called again with writer=config.ROLES["coder"]. suspect = sorted
list of test names failing in BOTH references. Non-empty suspect: entry gets
"suspect", log + telemetry "ref_suspect", then one repair round via the PLANNER
test writer; if the repaired file passes check_draft it replaces the file on
disk, refcheck runs again (first writer), entry gets "repaired": true and the
new result. Empty suspect: no extra calls. Non-flagged entries unchanged.
REF_SECOND False: no second check.
"""

import json
import os
from pathlib import Path

import pytest

from stratos import codemap, config, plan, plantests, refcheck
from stratos.telemetry import Telemetry

# ---- fixed data ----

TASK = {"key": "a", "title": "T A", "goal": "Goal A.",
        "files": ["pkg/a.py"], "tests": ["tests/test_a.py"],
        "protected": [], "after": [], "role": None}

DRAFT_CONTENT = "def test_x(): pass\ndef test_y(): pass\ndef test_z(): pass\n"
DRAFT_ANSWER = "FILE: tests/test_a.py\n```python\n" + DRAFT_CONTENT + "```\n"

REPAIRED_CONTENT = "def test_y():\n    # from facts\n    assert True\n"
REPAIRED_ANSWER = "FILE: tests/test_a.py\n```python\n" + REPAIRED_CONTENT + "```\n"

# FIRST_REF: failing test_x, test_y; output "first ref output"
FIRST_REF = {"status": "flagged", "total": 3,
             "failing": ["test_x", "test_y"],
             "first_error": "assert 1 == 2",
             "files": [("pkg/a.py", "a1")],
             "output": "first ref output"}

# SECOND_REF: failing test_y, test_z; output "second ref output"
SECOND_REF = {"status": "flagged", "total": 3,
              "failing": ["test_y", "test_z"],
              "first_error": "assert 3 == 4",
              "files": [("pkg/a.py", "a2")],
              "output": "second ref output"}

# suspect = sorted(["test_x","test_y"] ∩ ["test_y","test_z"]) = ["test_y"]

REPAIRED_REF = {"status": "agree", "total": 3, "failing": [],
                "first_error": "",
                "files": [("pkg/a.py", "a3")],
                "output": "repaired ref output"}

# For empty-suspect: FIRST_REF2 fails test_x only, SECOND_REF2 fails test_y only
FIRST_REF2 = {"status": "flagged", "total": 3,
              "failing": ["test_x"],
              "first_error": "assert 1 == 2",
              "files": [("pkg/a.py", "a1")],
              "output": "output2"}

SECOND_REF2 = {"status": "flagged", "total": 3,
               "failing": ["test_y"],
               "first_error": "assert 3 == 4",
               "files": [("pkg/a.py", "a2")],
               "output": "output3"}

# For non-flagged: FIRST_AGREE
FIRST_AGREE = {"status": "agree", "total": 3, "failing": [],
               "first_error": "",
               "files": [("pkg/a.py", "a1")],
               "output": "agree output"}

# For error status
FIRST_ERROR = {"status": "error", "total": 0, "failing": [],
               "first_error": "no file in the answer",
               "files": [],
               "output": ""}


# ---- helpers ----

class FakeGW:
    def __init__(self, telemetry, answers):
        self.telemetry = telemetry
        self._answers = list(answers)
        self.models = []
        self.calls = []

    def ensure_model(self, model):
        self.models.append(model)
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append((list(messages), kw))
        if self._answers:
            return f"c{len(self.calls)}", self._answers.pop(0)
        return f"c{len(self.calls)}", ""


class RefRecorder:
    """Records refcheck.check calls; returns results in order."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def fake(self, gw, pid, task, root, tests, extra=None, writer=None):
        self.calls.append({"key": task["key"], "writer": writer,
                           "extra": list(extra) if extra else [],
                           "tests": list(tests)})
        return self.results.pop(0)


def _setup(tmp_path, monkeypatch):
    """Root, state, plan stubs; stubs for check_draft, suite_leaks, codemap, repo_summary.
    Sets REF_CHECK=True and REF_SECOND=True. Returns root, state."""
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
    monkeypatch.setattr(codemap, "build", lambda r: {"test_dir": "tests", "files": {}, "imports": {}})
    monkeypatch.setattr(plan, "repo_summary", lambda r: "SUMMARY")
    return root, state


def _write_plan(state, tasks, pid="P001"):
    (state / "plans").mkdir(parents=True, exist_ok=True)
    (state / "plans" / f"{pid}.json").write_text(
        json.dumps({"id": pid, "goal": "the goal", "tasks": tasks,
                    "status": "draft", "hash": "h"}), encoding="utf-8")
    return pid


def _run(root, state, pid, gw, ref):
    """Run draft_tests with the given gateway and ref recorder. Returns results, log lines."""
    lines = []
    results = plantests.draft_tests(gw, pid, root, state, log=lines.append)
    return results, lines


# ---- 1. config.REF_SECOND exists ----

def test_ref_second_defined_in_config():
    # Expected: config has attribute REF_SECOND, a bool
    assert hasattr(config, "REF_SECOND")
    assert isinstance(config.REF_SECOND, bool)


# ---- 2. conftest sets REF_SECOND False ----

def test_conftest_sets_ref_second_false():
    # conftest's no_network fixture runs for every test; without monkeypatch,
    # REF_SECOND must be False (the conftest sets it the same way as REF_CHECK)
    # Expected: False
    assert config.REF_SECOND is False


# ---- 3. second check runs when flagged, uses coder writer; suspect = sorted intersection ----

def test_second_check_uses_coder_writer_and_computes_suspect(tmp_path, monkeypatch):
    root, state = _setup(tmp_path, monkeypatch)
    pid = _write_plan(state, [TASK])
    # Only one model call for the initial test writer; refcheck is monkeypatched
    # Expected: gw.chat calls: 1 (initial test writer)
    gw = FakeGW(Telemetry(state / "t.jsonl"), [DRAFT_ANSWER])
    ref = RefRecorder([FIRST_REF, SECOND_REF, REPAIRED_REF])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    results, _ = _run(root, state, pid, gw, ref)
    # Expected: 2 refcheck calls (first + second)
    assert len(ref.calls) == 2
    # Expected: first refcheck has writer=None (default REF_WRITER)
    assert ref.calls[0]["writer"] is None
    # Expected: second refcheck has writer=config.ROLES["coder"]
    assert ref.calls[1]["writer"] is config.ROLES["coder"]
    # Expected: entry has suspect
    entry = [r for r in results if r["key"] == "a"][0]
    # FIRST_REF failing = ["test_x","test_y"], SECOND_REF failing = ["test_y","test_z"]
    # intersection = {"test_y"}, sorted = ["test_y"]
    assert entry["suspect"] == ["test_y"]


# ---- 4. suspect in entry + log message ----

def test_suspect_in_entry_and_log(tmp_path, monkeypatch):
    root, state = _setup(tmp_path, monkeypatch)
    pid = _write_plan(state, [TASK])
    gw = FakeGW(Telemetry(state / "t.jsonl"), [DRAFT_ANSWER])
    ref = RefRecorder([FIRST_REF, SECOND_REF, REPAIRED_REF])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    results, lines = _run(root, state, pid, gw, ref)
    entry = [r for r in results if r["key"] == "a"][0]
    # Expected: suspect key present, value ["test_y"]
    assert entry["suspect"] == ["test_y"]
    # Expected log: "a: two independent references fail: test_y - these tests are likely wrong"
    # names = ", ".join(["test_y"]) = "test_y"
    want = "a: two independent references fail: test_y - these tests are likely wrong"
    assert want in lines


# ---- 5. telemetry ref_suspect recorded ----

def test_suspect_telemetry(tmp_path, monkeypatch):
    root, state = _setup(tmp_path, monkeypatch)
    pid = _write_plan(state, [TASK])
    gw = FakeGW(Telemetry(state / "t.jsonl"), [DRAFT_ANSWER])
    ref = RefRecorder([FIRST_REF, SECOND_REF, REPAIRED_REF])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    _run(root, state, pid, gw, ref)
    events = [e for e in gw.telemetry.load() if e["kind"] == "ref_suspect"]
    # Expected: 1 event
    assert len(events) == 1
    # Expected: plan=P001, key=a, tests=["test_y"]
    assert events[0]["plan"] == pid
    assert events[0]["key"] == "a"
    # Expected: tests = ["test_y"]
    assert events[0]["tests"] == ["test_y"]


# ---- 6. empty suspect: no extra calls ----

def test_empty_suspect_no_extra_calls(tmp_path, monkeypatch):
    root, state = _setup(tmp_path, monkeypatch)
    pid = _write_plan(state, [TASK])
    # FIRST_REF2 fails ["test_x"], SECOND_REF2 fails ["test_y"]: intersection = empty
    # Expected: gw.chat calls: only 1 (initial test writer)
    gw = FakeGW(Telemetry(state / "t.jsonl"), [DRAFT_ANSWER])
    ref = RefRecorder([FIRST_REF2, SECOND_REF2])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    results, lines = _run(root, state, pid, gw, ref)
    # Expected: 2 refcheck calls (first + second, both flagged, intersection empty)
    # Expected: no repair, no gateway call beyond the initial
    # Expected: 1 gateway chat call
    assert len(gw.calls) == 1
    # Expected: 2 refcheck calls
    assert len(ref.calls) == 2
    # Expected: no "suspect" key in the entry
    entry = [r for r in results if r["key"] == "a"][0]
    # Expected: suspect not in entry
    assert "suspect" not in entry
    # Expected: no ref_suspect telemetry
    events = [e for e in gw.telemetry.load() if e["kind"] == "ref_suspect"]
    # Expected: 0
    assert len(events) == 0
    # Expected: no "two independent references fail" log line
    assert not any("two independent references fail" in l for l in lines)


# ---- 7. repair messages contain draft text, suspect names, first ref output, instruction ----

def test_repair_messages_contain_required_parts(tmp_path, monkeypatch):
    root, state = _setup(tmp_path, monkeypatch)
    pid = _write_plan(state, [TASK])
    # 2 gateway calls: initial draft, then repair draft
    gw = FakeGW(Telemetry(state / "t.jsonl"), [DRAFT_ANSWER, REPAIRED_ANSWER])
    ref = RefRecorder([FIRST_REF, SECOND_REF, REPAIRED_REF])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    _run(root, state, pid, gw, ref)
    # gw.calls[0] = initial test writer messages
    # gw.calls[1] = repair test writer messages
    # Expected: 2 chat calls
    assert len(gw.calls) == 2
    repair_user = gw.calls[1][0][1]["content"]
    # Expected: contains the initial draft content
    assert DRAFT_CONTENT in repair_user
    # Expected: contains suspect name
    assert "test_y" in repair_user
    # Expected: contains first ref's output
    # FIRST_REF output = "first ref output"
    assert "first ref output" in repair_user
    # Expected: instruction mentions rewrite, facts/rules, not head math
    # keywords to look for
    lower = repair_user.lower()
    # Expected: "rewrite" (instruction to rewrite suspect tests)
    assert "rewrite" in lower
    # Expected: "facts"
    assert "facts" in lower
    # Expected: "rules"
    assert "rules" in lower
    # Expected: "head" (head math / head calculation)
    assert "head" in lower


# ---- 8. repair uses PLANNER model settings ----

def test_repair_uses_planner_model(tmp_path, monkeypatch):
    root, state = _setup(tmp_path, monkeypatch)
    pid = _write_plan(state, [TASK])
    gw = FakeGW(Telemetry(state / "t.jsonl"), [DRAFT_ANSWER, REPAIRED_ANSWER])
    ref = RefRecorder([FIRST_REF, SECOND_REF, REPAIRED_REF])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    _run(root, state, pid, gw, ref)
    # gw.calls[1] is the repair test writer call
    _, kw = gw.calls[1]
    # Expected: model = PLANNER["model"] = "planner-m"
    assert kw["model"] == config.PLANNER["model"]
    # Expected: effort = PLANNER["effort"] = "low"
    assert kw["effort"] == config.PLANNER["effort"]
    # Expected: max_tokens = PLANNER["max_tokens"] = 200
    assert kw["max_tokens"] == config.PLANNER["max_tokens"]
    # Expected: role = "test_writer"
    assert kw["role"] == "test_writer"
    # Expected: task = "P001-a"
    assert kw["task"] == f"{pid}-a"
    # Expected: attempt = 1
    assert kw["attempt"] == 1


# ---- 9. repair replaces file on disk when check_draft passes ----

def test_repair_replaces_file_on_disk(tmp_path, monkeypatch):
    root, state = _setup(tmp_path, monkeypatch)
    pid = _write_plan(state, [TASK])
    gw = FakeGW(Telemetry(state / "t.jsonl"), [DRAFT_ANSWER, REPAIRED_ANSWER])
    ref = RefRecorder([FIRST_REF, SECOND_REF, REPAIRED_REF])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    _run(root, state, pid, gw, ref)
    # Expected: file on disk = REPAIRED_CONTENT
    disk = (root / "tests" / "test_a.py").read_text(encoding="utf-8")
    # Expected: matches repaired content
    assert disk == REPAIRED_CONTENT


# ---- 10. after repair, first writer refcheck runs again ----

def test_repair_runs_first_writer_refcheck(tmp_path, monkeypatch):
    root, state = _setup(tmp_path, monkeypatch)
    pid = _write_plan(state, [TASK])
    gw = FakeGW(Telemetry(state / "t.jsonl"), [DRAFT_ANSWER, REPAIRED_ANSWER])
    ref = RefRecorder([FIRST_REF, SECOND_REF, REPAIRED_REF])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    _run(root, state, pid, gw, ref)
    # Expected: 3 refcheck calls: first (None), second (coder), third (None for repair)
    # Expected: 3
    assert len(ref.calls) == 3
    # Expected: first writer = None
    assert ref.calls[0]["writer"] is None
    # Expected: second writer = coder
    assert ref.calls[1]["writer"] is config.ROLES["coder"]
    # Expected: third writer = None (first writer again)
    assert ref.calls[2]["writer"] is None


# ---- 11. repaired entry has "repaired": True and the new result ----

def test_repaired_entry_has_repaired_and_new_result(tmp_path, monkeypatch):
    root, state = _setup(tmp_path, monkeypatch)
    pid = _write_plan(state, [TASK])
    gw = FakeGW(Telemetry(state / "t.jsonl"), [DRAFT_ANSWER, REPAIRED_ANSWER])
    ref = RefRecorder([FIRST_REF, SECOND_REF, REPAIRED_REF])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    results, _ = _run(root, state, pid, gw, ref)
    entry = [r for r in results if r["key"] == "a"][0]
    # Expected: "repaired": True
    assert entry.get("repaired") is True
    # Expected: entry["refcheck"] == REPAIRED_REF
    assert entry["refcheck"] == REPAIRED_REF


# ---- 12. non-flagged entries unchanged ----

def test_non_flagged_entries_unchanged(tmp_path, monkeypatch):
    root, state = _setup(tmp_path, monkeypatch)
    pid = _write_plan(state, [TASK])
    # refcheck returns agree, so no second check, no suspect, no repair
    gw = FakeGW(Telemetry(state / "t.jsonl"), [DRAFT_ANSWER])
    ref = RefRecorder([FIRST_AGREE])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    results, lines = _run(root, state, pid, gw, ref)
    # Expected: 1 refcheck call
    assert len(ref.calls) == 1
    entry = [r for r in results if r["key"] == "a"][0]
    # Expected: no "suspect" key
    # Expected: no "repaired" key
    assert "suspect" not in entry
    assert "repaired" not in entry
    # Expected: refcheck is the agree result
    assert entry["refcheck"] == FIRST_AGREE
    # Expected: no ref_suspect telemetry
    events = [e for e in gw.telemetry.load() if e["kind"] == "ref_suspect"]
    # Expected: 0
    assert len(events) == 0


# ---- 13. REF_SECOND False: no second check ----

def test_ref_second_off_no_second_check(tmp_path, monkeypatch):
    root, state = _setup(tmp_path, monkeypatch)
    # Expected: override REF_SECOND to False
    monkeypatch.setattr(config, "REF_SECOND", False)
    pid = _write_plan(state, [TASK])
    # Only the initial test writer gateway call
    gw = FakeGW(Telemetry(state / "t.jsonl"), [DRAFT_ANSWER])
    ref = RefRecorder([FIRST_REF])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    results, _ = _run(root, state, pid, gw, ref)
    # Expected: only 1 refcheck call
    # Expected: 1
    assert len(ref.calls) == 1
    # Expected: no suspect in entry
    entry = [r for r in results if r["key"] == "a"][0]
    # Expected: no suspect
    assert "suspect" not in entry
    # Expected: no repaired
    assert "repaired" not in entry


# ---- 14. first check "agree" → no second check, no suspect ----

def test_first_check_agree_no_second_check(tmp_path, monkeypatch):
    root, state = _setup(tmp_path, monkeypatch)
    pid = _write_plan(state, [TASK])
    gw = FakeGW(Telemetry(state / "t.jsonl"), [DRAFT_ANSWER])
    ref = RefRecorder([FIRST_AGREE])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    results, _ = _run(root, state, pid, gw, ref)
    # Expected: only 1 refcheck call
    # Expected: 1
    assert len(ref.calls) == 1
    entry = [r for r in results if r["key"] == "a"][0]
    # Expected: no suspect key
    assert "suspect" not in entry
    # Expected: no repaired key
    assert "repaired" not in entry
    # Expected: no ref_suspect telemetry
    events = [e for e in gw.telemetry.load() if e["kind"] == "ref_suspect"]
    # Expected: 0
    assert len(events) == 0


# ---- 15. first check "error" → no second check, no suspect ----

def test_first_check_error_no_second_check(tmp_path, monkeypatch):
    root, state = _setup(tmp_path, monkeypatch)
    pid = _write_plan(state, [TASK])
    gw = FakeGW(Telemetry(state / "t.jsonl"), [DRAFT_ANSWER])
    ref = RefRecorder([FIRST_ERROR])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    results, _ = _run(root, state, pid, gw, ref)
    # Expected: only 1 refcheck call
    # Expected: 1
    assert len(ref.calls) == 1
    entry = [r for r in results if r["key"] == "a"][0]
    # Expected: no suspect
    assert "suspect" not in entry
    # Expected: no repaired
    assert "repaired" not in entry
    # Expected: refcheck is the error result
    # Expected: status == "error"
    assert entry["refcheck"]["status"] == "error"
    # Expected: no ref_suspect telemetry
    events = [e for e in gw.telemetry.load() if e["kind"] == "ref_suspect"]
    # Expected: 0
    assert len(events) == 0
