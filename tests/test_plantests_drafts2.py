"""Tests for stratos/plantests.py draft_tests: single-file handling.

When a task has exactly ONE test file and the model answer contains no
"FILE:" marker, draft_tests keeps the answer as-is:
  - a lone fenced code block (``` ... ```) → the inner text (fences and
    language tag stripped) is the file body;
  - plain text that does NOT start with a fence → the whole answer is
    the file body.
When the answer DOES have a FILE marker, normal parse_files applies.
When the task has TWO OR MORE test files, normal parsing always applies.
A file that already exists is never overwritten ("exists").
"""

import json
from pathlib import Path

from stratos import config, plantests, plan, patch


class FakeGateway:
    def __init__(self):
        self.calls = []
        self.models = []
        self.telemetry = FakeTelemetry()

    def ensure_model(self, model):
        self.models.append(model)

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        return f"call-{len(self.calls)}", self._answer

    def set_answer(self, text):
        self._answer = text


class FakeTelemetry:
    def __init__(self):
        self.events = []

    def record(self, kind, **fields):
        self.events.append({"kind": kind, **fields})


def _write_plan(state_dir, plan_id, tasks):
    p = {"id": plan_id, "goal": "G", "tasks": tasks,
         "status": "draft", "hash": "abc"}
    plans_dir = Path(state_dir) / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    Path(plans_dir, f"{plan_id}.json").write_text(json.dumps(p), encoding="utf-8")
    return p


def _setup(tmp_path, monkeypatch):
    state_dir = tmp_path / ".stratos"
    monkeypatch.setattr(config, "STATE_DIR", state_dir)
    monkeypatch.setattr(config, "PROJECT", {
        **config.PROJECT,
        "language": "Python",
        "test_runner": "pytest",
        "example_test": "tests/example.py",
        "draft_check_command": ["python", "-m", "pytest", "--collect-only", "-q", "-x"],
    })
    monkeypatch.setattr(config, "PLANNER", {
        "model": "local-model", "effort": "medium", "max_tokens": 4096,
    })
    monkeypatch.setattr(plantests, "TEST_SYSTEM",
                        plantests.system_prompt("Python", "pytest"))
    return state_dir


def test_single_file_lone_fence_block(tmp_path, monkeypatch):
    state_dir = _setup(tmp_path, monkeypatch)
    root = str(tmp_path)
    task = {"key": "T001", "title": "X", "goal": "G",
            "files": ["src/x.py"], "tests": ["tests/test_x.py"],
            "protected": []}
    _write_plan(state_dir, "P001", [task])

    gw = FakeGateway()
    answer = "```python\ndef test_a():\n    assert 1 == 1\n```\n"
    gw.set_answer(answer)

    results = plantests.draft_tests(gw, "P001", root, str(state_dir),
                                     log=lambda *a: None)
    assert len(results) == 1
    assert results[0]["key"] == "T001"
    assert results[0]["file"] == "tests/test_x.py"
    body = Path(root, "tests", "test_x.py").read_text(encoding="utf-8")
    assert "def test_a():" in body
    assert "```" not in body


def test_single_file_plain_text_no_fence(tmp_path, monkeypatch):
    state_dir = _setup(tmp_path, monkeypatch)
    root = str(tmp_path)
    task = {"key": "T001", "title": "X", "goal": "G",
            "files": ["src/x.py"], "tests": ["tests/test_x.py"],
            "protected": []}
    _write_plan(state_dir, "P001", [task])

    gw = FakeGateway()
    answer = "def test_a():\n    assert 1 == 1\n"
    gw.set_answer(answer)

    results = plantests.draft_tests(gw, "P001", root, str(state_dir),
                                     log=lambda *a: None)
    assert len(results) == 1
    body = Path(root, "tests", "test_x.py").read_text(encoding="utf-8")
    assert "def test_a():" in body


def test_single_file_with_file_marker(tmp_path, monkeypatch):
    state_dir = _setup(tmp_path, monkeypatch)
    root = str(tmp_path)
    task = {"key": "T001", "title": "X", "goal": "G",
            "files": ["src/x.py"], "tests": ["tests/test_x.py"],
            "protected": []}
    _write_plan(state_dir, "P001", [task])

    gw = FakeGateway()
    answer = "FILE: tests/test_x.py\n```python\ndef test_a():\n    assert 1 == 1\n```\n"
    gw.set_answer(answer)

    results = plantests.draft_tests(gw, "P001", root, str(state_dir),
                                     log=lambda *a: None)
    assert len(results) == 1
    assert results[0]["file"] == "tests/test_x.py"
    body = Path(root, "tests", "test_x.py").read_text(encoding="utf-8")
    assert "def test_a():" in body


def test_multi_file_always_uses_parse_files(tmp_path, monkeypatch):
    state_dir = _setup(tmp_path, monkeypatch)
    root = str(tmp_path)
    task = {"key": "T001", "title": "X", "goal": "G",
            "files": ["src/x.py"],
            "tests": ["tests/test_x.py", "tests/test_y.py"],
            "protected": []}
    _write_plan(state_dir, "P001", [task])

    gw = FakeGateway()
    answer = "def test_a():\n    assert True\n"
    gw.set_answer(answer)

    results = plantests.draft_tests(gw, "P001", root, str(state_dir),
                                     log=lambda *a: None)
    assert len(results) == 2
    statuses = {r["status"] for r in results}
    assert "missing" in statuses


def test_single_file_existing_not_overwritten(tmp_path, monkeypatch):
    state_dir = _setup(tmp_path, monkeypatch)
    root = str(tmp_path)
    task = {"key": "T001", "title": "X", "goal": "G",
            "files": ["src/x.py"], "tests": ["tests/test_x.py"],
            "protected": []}
    _write_plan(state_dir, "P001", [task])

    existing = Path(root, "tests", "test_x.py")
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("old content", encoding="utf-8")

    gw = FakeGateway()
    answer = "```python\ndef test_a():\n    assert True\n```\n"
    gw.set_answer(answer)

    results = plantests.draft_tests(gw, "P001", root, str(state_dir),
                                     log=lambda *a: None)
    assert results[0]["status"] == "exists"
    assert existing.read_text(encoding="utf-8") == "old content"


def test_single_file_answer_with_extra_prose(tmp_path, monkeypatch):
    """The whole plain-text answer (prose + code, no fence, no FILE marker)
    is kept as-is for the single-file task."""
    state_dir = _setup(tmp_path, monkeypatch)
    root = str(tmp_path)
    task = {"key": "T001", "title": "X", "goal": "G",
            "files": ["src/x.py"], "tests": ["tests/test_x.py"],
            "protected": []}
    _write_plan(state_dir, "P001", [task])

    gw = FakeGateway()
    answer = "I want to test X.  def test_a():\n    assert 1 == 1\n"
    gw.set_answer(answer)

    results = plantests.draft_tests(gw, "P001", root, str(state_dir),
                                     log=lambda *a: None)
    assert len(results) == 1
    body = Path(root, "tests", "test_x.py").read_text(encoding="utf-8")
    assert "I want to test X." in body
    assert "def test_a():" in body


def test_single_file_answer_no_fence_has_answer_body(tmp_path, monkeypatch):
    """When the answer does NOT start with a fence, the whole answer text
    (including leading prose) is written verbatim, NOT stripped."""
    state_dir = _setup(tmp_path, monkeypatch)
    root = str(tmp_path)
    task = {"key": "T001", "title": "X", "goal": "G",
            "files": ["src/x.py"], "tests": ["tests/test_x.py"],
            "protected": []}
    _write_plan(state_dir, "P001", [task])

    gw = FakeGateway()
    answer = "  hello world  "
    gw.set_answer(answer)

    results = plantests.draft_tests(gw, "P001", root, str(state_dir),
                                     log=lambda *a: None)
    body = Path(root, "tests", "test_x.py").read_text(encoding="utf-8")
    assert body == "  hello world  "


def test_system_prompt_top_comment_and_worked_values():
    """The prompt asks for a top comment in the language's style (a docstring only for Python) and for every expected
    value to be worked out step by step in a comment above its assertion (trial 1: 8 wrong expectations)."""
    py = plantests.system_prompt("python", "pytest")
    js = plantests.system_prompt("javascript", "node --test")
    assert "docstring" in py
    assert "docstring" not in js and "//" in js
    for text in (py, js):
        assert "step by step" in text


def test_uses_patch_header_regex():
    """Review: plantests reuses patch.HEADER_RE instead of its own copy."""
    import inspect
    src = inspect.getsource(plantests)
    assert "_HEADER_RE = re.compile" not in src


def test_one_new_file_among_existing_ones_takes_a_lone_block(tmp_path, monkeypatch):
    """Harness fix (2026-11-19, tower defense P002): a task listed its new test file and two existing ones; the
    answer was one fenced block without a FILE header and was dropped ("missing"). The header-less fallback now
    counts only the test files that do not exist yet."""
    state_dir = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(plantests, "check_draft", lambda root, path: ("collected", ""))
    monkeypatch.setattr(plantests, "suite_leaks", lambda root, path, ignore=(): [])
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_old.py").write_text("OLD\n", encoding="utf-8")
    _write_plan(state_dir, "P001", [{"key": "a", "title": "T", "goal": "G", "files": ["stratos/x.py"],
                                     "tests": ["tests/test_new.py", "tests/test_old.py"], "protected": [],
                                     "after": [], "role": None}])
    gw = FakeGateway()
    gw.set_answer("```python\ndef test_a():\n    assert True\n```\n")
    results = plantests.draft_tests(gw, "P001", root, state_dir, log=lambda s: None)
    # an existing file not in the answer ("old" since task drafts_lint; Claude updated this test)
    assert [r["status"] for r in results] == ["collected", "old"]
    assert (root / "tests" / "test_new.py").read_text(encoding="utf-8") == "def test_a():\n    assert True\n"
    assert (root / "tests" / "test_old.py").read_text(encoding="utf-8") == "OLD\n"
