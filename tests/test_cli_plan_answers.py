"""Tests for task cli-plan-save-answers: save raw planner answers as plan-<call_id>.md.

In the plan command flow in stratos/__main__.py, after each model call that produces a plan draft,
write the raw answer text to .stratos/answers/plan-<call_id>.md (call_id from the gateway telemetry).
Ensure the answers directory is created if missing. This lets a failed plan be explained later.

Requirements:
  - After gw.chat returns (call_id, text), write text to STATE_DIR / "answers" / f"plan-{call_id}.md".
  - The answers directory must be created if it does not exist.
  - Every attempt (including failed/invalid ones) saves its raw answer.
  - The file content is exactly the raw text returned by gw.chat (no trimming, no formatting).
  - Files are named plan-<call_id>.md using the call_id from the gateway.
"""
import json
import sys
from pathlib import Path

import pytest

from stratos.__main__ import main


# ---------- helpers ----------

class NullTelemetry:
    def record(self, kind, **fields):
        pass


class FakeGateway:
    """Fake gateway that records calls and returns pre-set (call_id, text) tuples."""

    def __init__(self, responses):
        """responses: list of (call_id, text) tuples, consumed in order."""
        self.telemetry = NullTelemetry()   # plan records "plan_parse" events through gw.telemetry (T076)
        self._responses = list(responses)
        self._idx = 0
        self.calls = []  # (messages, kw) tuples

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        call_id, text = self._responses[self._idx]
        self._idx += 1
        self.calls.append((messages, kw))
        return call_id, text


VALID_PLAN_JSON = json.dumps({"tasks": [
    {"key": "1", "title": "First", "goal": "Do A", "files": ["a.py"], "tests": ["tests/test_a.py"]},
    {"key": "2", "title": "Second", "goal": "Do B", "files": ["b.py"], "tests": ["tests/test_b.py"]},
]})

INVALID_PLAN = "This is not a valid JSON plan."


def _setup(tmp_path, monkeypatch):
    """Set up config paths and fake the gateway so main() runs the plan command offline."""
    state_dir = tmp_path / ".stratos"
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr("stratos.config.STATE_DIR", state_dir)
    monkeypatch.setattr("stratos.config.REPO", repo)
    monkeypatch.setattr("stratos.config.WORKTREES", tmp_path / "worktrees")
    # Ensure PLAN prompt parts work without a real repo
    monkeypatch.setattr("stratos.plan.repo_summary", lambda root: "(empty repo)")
    return state_dir


def _goal_file(tmp_path, goal_text):
    p = tmp_path / "goal.md"
    p.write_text(goal_text, encoding="utf-8")
    return str(p)


# ---------- tests ----------

def test_answers_directory_created(tmp_path, monkeypatch):
    """The .stratos/answers/ directory is created (if missing) during the plan flow."""
    state_dir = _setup(tmp_path, monkeypatch)
    answers_dir = state_dir / "answers"
    assert not answers_dir.exists()

    goal = _goal_file(tmp_path, "Build feature X")
    gw = FakeGateway([("abc123def456", VALID_PLAN_JSON)])
    monkeypatch.setattr("stratos.__main__.Gateway", lambda tel: gw)
    monkeypatch.setattr("stratos.__main__.Telemetry", lambda p: None)

    main(["plan", "--goal-file", goal])

    assert answers_dir.is_dir(), "answers directory must be created"


def test_plan_answer_saved_on_success(tmp_path, monkeypatch):
    """After a successful plan call, plan-<call_id>.md contains the raw text."""
    state_dir = _setup(tmp_path, monkeypatch)
    goal = _goal_file(tmp_path, "Build feature X")

    call_id = "a1b2c3d4e5f6"
    raw_text = VALID_PLAN_JSON
    gw = FakeGateway([(call_id, raw_text)])
    monkeypatch.setattr("stratos.__main__.Gateway", lambda tel: gw)
    monkeypatch.setattr("stratos.__main__.Telemetry", lambda p: None)

    main(["plan", "--goal-file", goal])

    saved = state_dir / "answers" / f"plan-{call_id}.md"
    assert saved.exists(), f"expected {saved} to exist"
    assert saved.read_text(encoding="utf-8") == raw_text


def test_plan_answer_saved_on_invalid_plan(tmp_path, monkeypatch):
    """Even when the plan is invalid (parse fails), the raw answer is saved for later explanation."""
    state_dir = _setup(tmp_path, monkeypatch)
    goal = _goal_file(tmp_path, "Build feature X")

    call_id_fail = "deadbeef1111"
    gw = FakeGateway([
        (call_id_fail, INVALID_PLAN),          # attempt 1: invalid
        ("validcall12345", VALID_PLAN_JSON),   # attempt 2: valid
    ])
    monkeypatch.setattr("stratos.__main__.Gateway", lambda tel: gw)
    monkeypatch.setattr("stratos.__main__.Telemetry", lambda p: None)

    main(["plan", "--goal-file", goal, "--tries", "2"])

    saved_fail = state_dir / "answers" / f"plan-{call_id_fail}.md"
    assert saved_fail.exists(), "failed plan raw answer must be saved"
    assert saved_fail.read_text(encoding="utf-8") == INVALID_PLAN

    saved_ok = state_dir / "answers" / "plan-validcall12345.md"
    assert saved_ok.exists()
    assert saved_ok.read_text(encoding="utf-8") == VALID_PLAN_JSON


def test_all_attempts_save_answers(tmp_path, monkeypatch):
    """Every model call in the plan loop saves its raw text, keyed by its call_id."""
    state_dir = _setup(tmp_path, monkeypatch)
    goal = _goal_file(tmp_path, "Build feature Y")

    responses = [
        ("call1111aaaa", "not a plan"),
        ("call2222bbbb", "still not a plan"),
        ("call3333cccc", VALID_PLAN_JSON),
    ]
    gw = FakeGateway(responses)
    monkeypatch.setattr("stratos.__main__.Gateway", lambda tel: gw)
    monkeypatch.setattr("stratos.__main__.Telemetry", lambda p: None)

    main(["plan", "--goal-file", goal, "--tries", "3"])

    answers_dir = state_dir / "answers"
    for cid, txt in responses:
        f = answers_dir / f"plan-{cid}.md"
        assert f.exists(), f"answer for {cid} not saved"
        assert f.read_text(encoding="utf-8") == txt


def test_filename_uses_call_id_from_gateway(tmp_path, monkeypatch):
    """The filename plan-<call_id>.md uses exactly the call_id returned by gw.chat."""
    state_dir = _setup(tmp_path, monkeypatch)
    goal = _goal_file(tmp_path, "Z")

    unique_id = "feedfacecafe"
    gw = FakeGateway([(unique_id, VALID_PLAN_JSON)])
    monkeypatch.setattr("stratos.__main__.Gateway", lambda tel: gw)
    monkeypatch.setattr("stratos.__main__.Telemetry", lambda p: None)

    main(["plan", "--goal-file", goal])

    answers = list((state_dir / "answers").glob("plan-*.md"))
    assert len(answers) == 1
    assert answers[0].name == f"plan-{unique_id}.md"


def test_answer_content_is_raw_no_trim(tmp_path, monkeypatch):
    """The saved file contains the raw text exactly, preserving whitespace."""
    state_dir = _setup(tmp_path, monkeypatch)
    goal = _goal_file(tmp_path, "W")

    raw = "  \n  {\"key\":\"1\",\"title\":\"T\",\"goal\":\"G\",\"files\":[],\"tests\":[]}\n  "
    cid = "1000000000ab"
    gw = FakeGateway([(cid, raw)])
    monkeypatch.setattr("stratos.__main__.Gateway", lambda tel: gw)
    monkeypatch.setattr("stratos.__main__.Telemetry", lambda p: None)
    # parse_plan will succeed on the stripped version
    # (P010: a task always has a test file, as parse_plan requires; check_new_tests reads the first one)
    monkeypatch.setattr("stratos.plan.parse_plan", lambda text: [{"key": "1", "title": "T", "goal": "G",
                                                                   "files": [], "tests": ["tests/test_t.py"]}])

    main(["plan", "--goal-file", goal])

    saved = state_dir / "answers" / f"plan-{cid}.md"
    assert saved.read_text(encoding="utf-8") == raw
