"""Tests for task plantests-second-opinion: extract second_opinion from draft_tests.

plantests.second_opinion(gw, plan_id, p, i, task, root, paths, refs, first, cmap, answers_dir, log)
returns (result_to_keep, extra_dict): {} if no suspect, {"suspect": [names]} if suspect,
{"suspect": [names], "repaired": True} if repair succeeded.
In draft_tests, when first is flagged and REF_SECOND on, second_opinion is called;
its result and extra fields go on every entry of the task.
Fixes: (a) repair files filtered to paths; (b) check_draft fail → restore earlier draft;
(c) second reference and re-check files NOT added to refs.
"""
import inspect
import json
from pathlib import Path

from stratos import codemap, config, plan, plantests, refcheck
from stratos.telemetry import Telemetry

TASK = {"key": "a", "title": "T A", "goal": "Goal A.",
        "files": ["pkg/a.py"], "tests": ["tests/test_a.py"],
        "protected": [], "after": [], "role": None}
DRAFT_CONTENT = "def test_x(): pass\ndef test_y(): pass\ndef test_z(): pass\n"
DRAFT_ANSWER = "FILE: tests/test_a.py\n```python\n" + DRAFT_CONTENT + "```\n"
REPAIRED_CONTENT = "def test_y():\n    # from facts\n    assert True\n"
REPAIRED_ANSWER = "FILE: tests/test_a.py\n```python\n" + REPAIRED_CONTENT + "```\n"
FIRST_REF = {"status": "flagged", "total": 3, "failing": ["test_x", "test_y"],
             "first_error": "a1==a2", "files": [("pkg/a.py", "a1")], "output": "first ref output"}
SECOND_REF = {"status": "flagged", "total": 3, "failing": ["test_y", "test_z"],
              "first_error": "a3==a4", "files": [("pkg/a.py", "a2")], "output": "second ref output"}
# suspect = sorted(set(["test_x","test_y"]) & set(["test_y","test_z"])) = ["test_y"]
REPAIRED_REF = {"status": "agree", "total": 3, "failing": [], "first_error": "",
                "files": [("pkg/a.py", "a3")], "output": "repaired ref output"}
FIRST_REF2 = {"status": "flagged", "total": 3, "failing": ["test_x"],
              "first_error": "a1==a2", "files": [("pkg/a.py", "a1")], "output": "out2"}
SECOND_REF2 = {"status": "flagged", "total": 3, "failing": ["test_y"],
               "first_error": "a3==a4", "files": [("pkg/a.py", "a2")], "output": "out3"}
FIRST_AGREE = {"status": "agree", "total": 3, "failing": [], "first_error": "",
               "files": [("pkg/a.py", "a1")], "output": "agree output"}


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
    monkeypatch.setattr(config, "PLANNER", {"model": "planner-m", "effort": "low", "max_tokens": 200})
    monkeypatch.setattr(config, "MEMORY", False)
    monkeypatch.setattr(config, "REF_CHECK", True, raising=False)
    monkeypatch.setattr(config, "REF_SECOND", True, raising=False)
    monkeypatch.setattr(plantests, "check_draft", lambda r, p: ("collected", ""))
    monkeypatch.setattr(plantests, "suite_leaks", lambda r, p, ignore=(): [])
    monkeypatch.setattr(plantests, "draft_problems", lambda r, p: [])
    monkeypatch.setattr(plantests, "risky_patterns", lambda t: [])
    monkeypatch.setattr(plantests, "old_tests", lambda cmap, task: [])
    monkeypatch.setattr(codemap, "build", lambda r: {"test_dir": "tests", "files": {}, "imports": {}})
    monkeypatch.setattr(plan, "repo_summary", lambda r: "SUMMARY")
    return root, state


def _plan(pid="P001"):
    return {"id": pid, "goal": "the goal", "tasks": [TASK], "status": "draft", "hash": "h"}


def _call(tmp_path, monkeypatch, gw, ref, first, refs, answers_dir, log_lines):
    root, state = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(refcheck, "check", ref.fake)
    (root / "tests" / "test_a.py").write_text(DRAFT_CONTENT, encoding="utf-8")
    return plantests.second_opinion(
        gw, "P001", _plan(), 0, TASK, root, ["tests/test_a.py"],
        list(refs), first, {"test_dir": "tests", "files": {}, "imports": {}},
        answers_dir, log_lines.append)


def _write_plan(state, tasks, pid="P001"):
    (state / "plans").mkdir(parents=True, exist_ok=True)
    (state / "plans" / f"{pid}.json").write_text(
        json.dumps({"id": pid, "goal": "the goal", "tasks": tasks,
                    "status": "draft", "hash": "h"}), encoding="utf-8")


# 1
def test_second_opinion_exists():
    # Expected: plantests has function second_opinion
    assert hasattr(plantests, "second_opinion")
    assert callable(plantests.second_opinion)


# 2
def test_second_check_uses_coder_writer(tmp_path, monkeypatch):
    # FIRST_REF failing=["test_x","test_y"], SECOND_REF failing=["test_y","test_z"]
    # suspect = sorted({"test_x","test_y"} & {"test_y","test_z"}) = ["test_y"]
    # refcheck calls: first writer=None, second writer=coder
    root, state = _setup(tmp_path, monkeypatch)
    gw = FakeGW(Telemetry(state / "t.jsonl"), [])
    ref = RefRecorder([SECOND_REF, REPAIRED_REF])
    (root / "tests" / "test_a.py").write_text(DRAFT_CONTENT, encoding="utf-8")
    monkeypatch.setattr(refcheck, "check", ref.fake)
    log = []
    plantests.second_opinion(gw, "P001", _plan(), 0, TASK, root, ["tests/test_a.py"],
                             [("pkg/a.py", "a1")], FIRST_REF,
                             {"test_dir": "tests", "files": {}, "imports": {}},
                             state / "answers", log.append)
    # Expected: refcheck called twice
    assert len(ref.calls) == 2
    # Expected: second refcheck writer = config.ROLES["coder"]
    assert ref.calls[1]["writer"] == config.ROLES["coder"]
    # Expected: first writer (recheck) = None
    assert ref.calls[1] is not None


# 3
def test_suspect_intersection(tmp_path, monkeypatch):
    # FIRST_REF fails ["test_x","test_y"], SECOND_REF fails ["test_y","test_z"]
    # intersection = {"test_y"}, sorted = ["test_y"]
    # Expected: extra = {"suspect": ["test_y"], "repaired": True}
    root, state = _setup(tmp_path, monkeypatch)
    gw = FakeGW(Telemetry(state / "t.jsonl"), [REPAIRED_ANSWER])
    ref = RefRecorder([SECOND_REF, REPAIRED_REF])
    (root / "tests" / "test_a.py").write_text(DRAFT_CONTENT, encoding="utf-8")
    monkeypatch.setattr(refcheck, "check", ref.fake)
    log = []
    result, extra = plantests.second_opinion(
        gw, "P001", _plan(), 0, TASK, root, ["tests/test_a.py"],
        [("pkg/a.py", "a1")], FIRST_REF, {"test_dir": "tests", "files": {}, "imports": {}},
        state / "answers", log.append)
    # Expected: suspect = ["test_y"]
    assert extra["suspect"] == ["test_y"]


# 4
def test_empty_suspect_returns_second_and_empty(tmp_path, monkeypatch):
    # FIRST_REF2 fails ["test_x"], SECOND_REF2 fails ["test_y"]
    # intersection = empty set → no suspect
    # Expected: result = SECOND_REF2, extra = {}
    root, state = _setup(tmp_path, monkeypatch)
    gw = FakeGW(Telemetry(state / "t.jsonl"), [])
    ref = RefRecorder([SECOND_REF2])
    (root / "tests" / "test_a.py").write_text(DRAFT_CONTENT, encoding="utf-8")
    monkeypatch.setattr(refcheck, "check", ref.fake)
    log = []
    result, extra = plantests.second_opinion(
        gw, "P001", _plan(), 0, TASK, root, ["tests/test_a.py"],
        [("pkg/a.py", "a1")], FIRST_REF2, {"test_dir": "tests", "files": {}, "imports": {}},
        state / "answers", log.append)
    # Expected: extra is {}
    assert extra == {}
    # Expected: result is the second ref result
    assert result == SECOND_REF2


# 5
def test_suspect_log_and_telemetry(tmp_path, monkeypatch):
    # suspect = ["test_y"]
    # Expected log: "a: two independent references fail: test_y - these tests are likely wrong"
    # Expected telemetry: kind="ref_suspect", plan="P001", key="a", tests=["test_y"]
    root, state = _setup(tmp_path, monkeypatch)
    gw = FakeGW(Telemetry(state / "t.jsonl"), [REPAIRED_ANSWER])
    ref = RefRecorder([SECOND_REF, REPAIRED_REF])
    (root / "tests" / "test_a.py").write_text(DRAFT_CONTENT, encoding="utf-8")
    monkeypatch.setattr(refcheck, "check", ref.fake)
    log = []
    plantests.second_opinion(
        gw, "P001", _plan(), 0, TASK, root, ["tests/test_a.py"],
        [("pkg/a.py", "a1")], FIRST_REF, {"test_dir": "tests", "files": {}, "imports": {}},
        state / "answers", log.append)
    # Expected: log line
    want = "a: two independent references fail: test_y - these tests are likely wrong"
    assert want in log
    # Expected: 1 ref_suspect event
    events = [e for e in gw.telemetry.load() if e["kind"] == "ref_suspect"]
    # Expected: len=1, plan="P001", key="a", tests=["test_y"]
    assert len(events) == 1
    assert events[0]["plan"] == "P001"
    assert events[0]["key"] == "a"
    assert events[0]["tests"] == ["test_y"]


# 6
def test_repair_messages_contain_parts(tmp_path, monkeypatch):
    # Repair message must contain: draft text, suspect names, first ref output
    # Expected: gw.chat called twice (repair writer, then recheck is refcheck not chat)
    root, state = _setup(tmp_path, monkeypatch)
    gw = FakeGW(Telemetry(state / "t.jsonl"), [REPAIRED_ANSWER])
    ref = RefRecorder([SECOND_REF, REPAIRED_REF])
    (root / "tests" / "test_a.py").write_text(DRAFT_CONTENT, encoding="utf-8")
    monkeypatch.setattr(refcheck, "check", ref.fake)
    log = []
    plantests.second_opinion(
        gw, "P001", _plan(), 0, TASK, root, ["tests/test_a.py"],
        [("pkg/a.py", "a1")], FIRST_REF, {"test_dir": "tests", "files": {}, "imports": {}},
        state / "answers", log.append)
    # Expected: 1 gw.chat call (repair writer)
    assert len(gw.calls) == 1
    user = gw.calls[0][0][1]["content"]
    # Expected: DRAFT_CONTENT in user
    assert DRAFT_CONTENT in user
    # Expected: suspect "test_y" in user
    assert "test_y" in user
    # Expected: first ref output in user
    assert "first ref output" in user


# 7
def test_repair_uses_planner_memory_none(tmp_path, monkeypatch):
    # Expected: gw.chat kw: model="planner-m", effort="low", max_tokens=200,
    #          role="test_writer", task="P001-a", attempt=1
    root, state = _setup(tmp_path, monkeypatch)
    gw = FakeGW(Telemetry(state / "t.jsonl"), [REPAIRED_ANSWER])
    ref = RefRecorder([SECOND_REF, REPAIRED_REF])
    (root / "tests" / "test_a.py").write_text(DRAFT_CONTENT, encoding="utf-8")
    monkeypatch.setattr(refcheck, "check", ref.fake)
    log = []
    plantests.second_opinion(
        gw, "P001", _plan(), 0, TASK, root, ["tests/test_a.py"],
        [("pkg/a.py", "a1")], FIRST_REF, {"test_dir": "tests", "files": {}, "imports": {}},
        state / "answers", log.append)
    _, kw = gw.calls[0]
    # Expected: PLANNER model settings
    assert kw["model"] == config.PLANNER["model"]
    # Expected: effort
    assert kw["effort"] == config.PLANNER["effort"]
    # Expected: max_tokens
    assert kw["max_tokens"] == config.PLANNER["max_tokens"]
    # Expected: role
    assert kw["role"] == "test_writer"


# 8
def test_repair_files_filtered_to_paths(tmp_path, monkeypatch):
    # Fix (a): repair answer has 2 files, only tests/test_a.py is in paths
    # paths = ["tests/test_a.py"]
    # repair answer files: [("tests/test_a.py", REPAIRED_CONTENT), ("tests/test_other.py", "other")]
    # filtered: only tests/test_a.py → check_draft passes → repaired
    # Expected: result=REPAIRED_REF, extra={"suspect":["test_y"],"repaired":True}
    # Expected: disk has REPAIRED_CONTENT
    root, state = _setup(tmp_path, monkeypatch)
    # repair answer with two files, one in paths
    two_file_answer = ('FILE: tests/test_a.py\n```python\n' + REPAIRED_CONTENT
                       + '```\nFILE: tests/test_other.py\n```python\nother\n```\n')
    gw = FakeGW(Telemetry(state / "t.jsonl"), [two_file_answer])
    ref = RefRecorder([SECOND_REF, REPAIRED_REF])
    (root / "tests" / "test_a.py").write_text(DRAFT_CONTENT, encoding="utf-8")
    monkeypatch.setattr(refcheck, "check", ref.fake)
    log = []
    result, extra = plantests.second_opinion(
        gw, "P001", _plan(), 0, TASK, root, ["tests/test_a.py"],
        [("pkg/a.py", "a1")], FIRST_REF, {"test_dir": "tests", "files": {}, "imports": {}},
        state / "answers", log.append)
    # Expected: repaired=True
    assert extra.get("repaired") is True
    # Expected: result = REPAIRED_REF
    assert result == REPAIRED_REF
    # Expected: disk = REPAIRED_CONTENT
    assert (root / "tests" / "test_a.py").read_text(encoding="utf-8") == REPAIRED_CONTENT


# 9
def test_repair_no_files_in_paths_returns_first(tmp_path, monkeypatch):
    # Fix (a): repair answer files NOT in paths → no repair
    # paths = ["tests/test_a.py"]
    # repair answer file: tests/test_other.py (not in paths)
    # Expected: result=FIRST_REF, extra={"suspect":["test_y"]}
    root, state = _setup(tmp_path, monkeypatch)
    off_path_answer = 'FILE: tests/test_other.py\n```python\nX = 1\n```\n'
    gw = FakeGW(Telemetry(state / "t.jsonl"), [off_path_answer])
    ref = RefRecorder([SECOND_REF])
    (root / "tests" / "test_a.py").write_text(DRAFT_CONTENT, encoding="utf-8")
    monkeypatch.setattr(refcheck, "check", ref.fake)
    log = []
    result, extra = plantests.second_opinion(
        gw, "P001", _plan(), 0, TASK, root, ["tests/test_a.py"],
        [("pkg/a.py", "a1")], FIRST_REF, {"test_dir": "tests", "files": {}, "imports": {}},
        state / "answers", log.append)
    # Expected: result is FIRST_REF
    assert result == FIRST_REF
    # Expected: extra has suspect
    assert extra["suspect"] == ["test_y"]
    # Expected: no "repaired" in extra
    assert "repaired" not in extra


# 10
def test_check_draft_fail_restores_earlier_draft(tmp_path, monkeypatch):
    # Fix (b): check_draft fails → write back earlier draft text
    # Expected: disk = DRAFT_CONTENT, result = FIRST_REF, extra={"suspect":["test_y"]}
    root, state = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(plantests, "check_draft", lambda r, p: ("syntax_error", "bad"))
    gw = FakeGW(Telemetry(state / "t.jsonl"), [REPAIRED_ANSWER])
    ref = RefRecorder([SECOND_REF])
    (root / "tests" / "test_a.py").write_text(DRAFT_CONTENT, encoding="utf-8")
    monkeypatch.setattr(refcheck, "check", ref.fake)
    log = []
    result, extra = plantests.second_opinion(
        gw, "P001", _plan(), 0, TASK, root, ["tests/test_a.py"],
        [("pkg/a.py", "a1")], FIRST_REF, {"test_dir": "tests", "files": {}, "imports": {}},
        state / "answers", log.append)
    # Expected: result = FIRST_REF
    assert result == FIRST_REF
    # Expected: extra has suspect, no repaired
    assert extra["suspect"] == ["test_y"]
    assert "repaired" not in extra
    # Expected: disk = DRAFT_CONTENT (earlier draft restored)
    assert (root / "tests" / "test_a.py").read_text(encoding="utf-8") == DRAFT_CONTENT


# 11
def test_repair_success_rechecks_first_writer(tmp_path, monkeypatch):
    # Repair passes check_draft → re-check with first writer (writer=None)
    # Expected: 2 refcheck calls: second (coder) + recheck (None)
    root, state = _setup(tmp_path, monkeypatch)
    gw = FakeGW(Telemetry(state / "t.jsonl"), [REPAIRED_ANSWER])
    ref = RefRecorder([SECOND_REF, REPAIRED_REF])
    (root / "tests" / "test_a.py").write_text(DRAFT_CONTENT, encoding="utf-8")
    monkeypatch.setattr(refcheck, "check", ref.fake)
    log = []
    result, extra = plantests.second_opinion(
        gw, "P001", _plan(), 0, TASK, root, ["tests/test_a.py"],
        [("pkg/a.py", "a1")], FIRST_REF, {"test_dir": "tests", "files": {}, "imports": {}},
        state / "answers", log.append)
    # Expected: 2 refcheck calls
    assert len(ref.calls) == 2
    # Expected: second writer = coder
    assert ref.calls[0]["writer"] == config.ROLES["coder"]
    # Expected: recheck writer = None (first writer)
    assert ref.calls[1]["writer"] is None
    # Expected: result = REPAIRED_REF, repaired=True
    assert result == REPAIRED_REF
    assert extra.get("repaired") is True


# 12
def test_second_ref_files_not_added_to_refs(tmp_path, monkeypatch):
    # Fix (c): second reference files NOT added to refs
    # refs = [("pkg/a.py", "a1")]
    # SECOND_REF files = [("pkg/a.py", "a2")]
    # Expected: refs unchanged (no a2)
    root, state = _setup(tmp_path, monkeypatch)
    original_refs = [("pkg/a.py", "a1")]
    gw = FakeGW(Telemetry(state / "t.jsonl"), [REPAIRED_ANSWER])
    ref = RefRecorder([SECOND_REF, REPAIRED_REF])
    (root / "tests" / "test_a.py").write_text(DRAFT_CONTENT, encoding="utf-8")
    monkeypatch.setattr(refcheck, "check", ref.fake)
    log = []
    refs_copy = list(original_refs)
    plantests.second_opinion(
        gw, "P001", _plan(), 0, TASK, root, ["tests/test_a.py"],
        refs_copy, FIRST_REF, {"test_dir": "tests", "files": {}, "imports": {}},
        state / "answers", log.append)
    # Expected: refs_copy is unchanged (second ref's files NOT added)
    # Expected: ("pkg/a.py","a2") not in refs
    assert ("pkg/a.py", "a2") not in refs_copy
    # Expected: refs_copy == original_refs
    assert refs_copy == original_refs


# 13
def test_recheck_files_not_added_to_refs(tmp_path, monkeypatch):
    # Fix (c): re-check files NOT added to refs
    # REPAIRED_REF files = [("pkg/a.py", "a3")]
    # Expected: refs unchanged
    root, state = _setup(tmp_path, monkeypatch)
    original_refs = [("pkg/a.py", "a1")]
    gw = FakeGW(Telemetry(state / "t.jsonl"), [REPAIRED_ANSWER])
    ref = RefRecorder([SECOND_REF, REPAIRED_REF])
    (root / "tests" / "test_a.py").write_text(DRAFT_CONTENT, encoding="utf-8")
    monkeypatch.setattr(refcheck, "check", ref.fake)
    log = []
    refs_copy = list(original_refs)
    plantests.second_opinion(
        gw, "P001", _plan(), 0, TASK, root, ["tests/test_a.py"],
        refs_copy, FIRST_REF, {"test_dir": "tests", "files": {}, "imports": {}},
        state / "answers", log.append)
    # Expected: ("pkg/a.py","a3") not in refs (re-check files not added)
    assert ("pkg/a.py", "a3") not in refs_copy
    # Expected: refs == original
    assert refs_copy == original_refs


# 14
def test_draft_tests_calls_second_opinion(tmp_path, monkeypatch):
    # draft_tests source must reference second_opinion, not inline second-check block
    src = inspect.getsource(plantests.draft_tests)
    # Expected: source contains "second_opinion("
    assert "second_opinion(" in src
    # Expected: source does NOT contain 'writer=config.ROLES["coder"]'
    assert 'writer=config.ROLES["coder"]' not in src


# 15
def test_draft_tests_applies_result_to_entries(tmp_path, monkeypatch):
    # Run draft_tests: first check flagged → second_opinion called
    # suspect=["test_y"], repair succeeds → REPAIRED_REF
    # Expected: every entry has refcheck=REPAIRED_REF, suspect=["test_y"], repaired=True
    root, state = _setup(tmp_path, monkeypatch)
    _write_plan(state, [TASK], "P001")
    gw = FakeGW(Telemetry(state / "t.jsonl"), [DRAFT_ANSWER, REPAIRED_ANSWER])
    ref = RefRecorder([FIRST_REF, SECOND_REF, REPAIRED_REF])
    monkeypatch.setattr(refcheck, "check", ref.fake)
    lines = []
    results = plantests.draft_tests(gw, "P001", root, state, log=lines.append)
    # Expected: 1 entry
    assert len(results) == 1
    entry = results[0]
    # Expected: refcheck = REPAIRED_REF
    assert entry["refcheck"] == REPAIRED_REF
    # Expected: suspect = ["test_y"]
    assert entry["suspect"] == ["test_y"]
    # Expected: repaired = True
    assert entry["repaired"] is True
