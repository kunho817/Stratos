"""Tests for the TRIAGE settings in stratos/config.py and the new stratos/triage.py module.

config.TRIAGE: True when STRATOS_TRIAGE env var is not "0", False when it is "0".
config.TRIAGER: {"model": "swift-1.5-iq2_xs", "effort": "low", "max_tokens": 8000, "reasoning_budget": 3000}.

triage.SYSTEM
    A str; it asks whether the failing assertion contradicts the task's goal, answer JSON only.
triage.build_messages(task, root, code_files, test_output) -> [{"role": "system", ...}, {"role": "user", ...}]
    The user content includes the goal, the text of each of the task's test files (read from root),
    each (path, content) of code_files, and test_output.
triage.parse(text) -> {"verdict", "test", "reason"} from the last JSON object in text.
    verdict one of test_wrong / code_wrong / unclear. Anything else, or no JSON,
    gives {"verdict": "unclear", "test": "", "reason": ""}.
triage.triage(gw, task, root, code_files, test_output)
    gw.ensure_model(TRIAGER["model"]), then gw.chat(build_messages(...), task=task["id"],
    role="triage", attempt=1, model, effort, max_tokens, reasoning_budget); returns parse(answer).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from stratos import config, triage


# ---------- config settings ----------

def test_triager_dict():
    assert config.TRIAGER == {"model": "swift-1.5-iq2_xs", "effort": "low",
                              "max_tokens": 8000, "reasoning_budget": 3000}


def triage_flag(value):
    """config.TRIAGE is read at import, so it is checked in a fresh process (reloading config in this one would
    change it for every later test)."""
    env = {k: v for k, v in os.environ.items() if k != "STRATOS_TRIAGE"}
    if value is not None:
        env["STRATOS_TRIAGE"] = value
    r = subprocess.run([sys.executable, "-c", "from stratos import config; print(config.TRIAGE)"],
                       cwd=Path(__file__).resolve().parent.parent, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_triage_flag_from_the_environment():
    assert triage_flag(None) == "True"
    assert triage_flag("1") == "True"
    assert triage_flag("0") == "False"


# ---------- SYSTEM prompt ----------

def test_system_mentions_json_and_goal():
    assert isinstance(triage.SYSTEM, str)
    assert "JSON" in triage.SYSTEM
    assert "goal" in triage.SYSTEM.lower()
    assert "assert" in triage.SYSTEM.lower()


# ---------- build_messages ----------

def test_build_messages_structure(tmp_path):
    task = {"id": "T001", "goal": "Make X = 2", "tests": ["tests/test_x.py"]}
    # write the test file into root
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    assert x == 2\n")
    code_files = [("src/a.py", "x = 1")]
    msgs = triage.build_messages(task, tmp_path, code_files, "FAILED test_x")
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[0]["content"] == triage.SYSTEM
    user = msgs[1]["content"]
    assert "Make X = 2" in user
    assert "def test_x()" in user
    assert "src/a.py" in user and "x = 1" in user
    assert "FAILED test_x" in user


def test_build_messages_multiple_tests_and_files(tmp_path):
    task = {"id": "T002", "goal": "goal text", "tests": ["tests/a.py", "tests/b.py"]}
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "a.py").write_text("content_a")
    (tmp_path / "tests" / "b.py").write_text("content_b")
    code_files = [("src/x.py", "hello"), ("src/y.py", "world")]
    msgs = triage.build_messages(task, tmp_path, code_files, "out")
    user = msgs[1]["content"]
    assert "content_a" in user
    assert "content_b" in user
    assert "hello" in user
    assert "world" in user


def test_build_messages_no_code_files(tmp_path):
    task = {"id": "T003", "goal": "g", "tests": []}
    msgs = triage.build_messages(task, tmp_path, [], "out")
    assert msgs[0]["content"] == triage.SYSTEM
    assert "g" in msgs[1]["content"]


# ---------- parse ----------

def test_parse_single_json():
    text = '{"verdict": "test_wrong", "test": "tests/a.py", "reason": "bad assertion"}'
    result = triage.parse(text)
    assert result == {"verdict": "test_wrong", "test": "tests/a.py", "reason": "bad assertion"}


def test_parse_last_json_in_multi_json_text():
    text = '{"verdict": "code_wrong", "test": "", "reason": "r1"}\nnoise\n{"verdict": "unclear", "test": "T", "reason": "r2"}'
    result = triage.parse(text)
    assert result == {"verdict": "unclear", "test": "T", "reason": "r2"}


def test_parse_code_wrong():
    result = triage.parse('{"verdict": "code_wrong", "test": "x", "reason": "y"}')
    assert result["verdict"] == "code_wrong"


def test_parse_test_wrong():
    result = triage.parse('{"verdict": "test_wrong", "test": "x", "reason": "y"}')
    assert result["verdict"] == "test_wrong"


def test_parse_unclear():
    result = triage.parse('{"verdict": "unclear", "test": "x", "reason": "y"}')
    assert result["verdict"] == "unclear"


def test_parse_invalid_verdict_gives_unclear():
    result = triage.parse('{"verdict": "banana", "test": "x", "reason": "y"}')
    assert result == {"verdict": "unclear", "test": "", "reason": ""}


def test_parse_no_json():
    result = triage.parse("The code is wrong, the test says 2.")
    assert result == {"verdict": "unclear", "test": "", "reason": ""}


def test_parse_empty_text():
    result = triage.parse("")
    assert result == {"verdict": "unclear", "test": "", "reason": ""}


def test_parse_extra_text_around_json():
    text = "thinking...\n{\"verdict\": \"code_wrong\", \"test\": \"t.py\", \"reason\": \"r\"}\ndone"
    result = triage.parse(text)
    assert result["verdict"] == "code_wrong"
    assert result["test"] == "t.py"


def test_parse_missing_keys_defaults():
    result = triage.parse('{"verdict": "code_wrong"}')
    assert result == {"verdict": "code_wrong", "test": "", "reason": ""}


# ---------- triage ----------

class FakeGateway:
    def __init__(self, answer=""):
        self.models = []
        self.calls = []
        self._answer = answer

    def ensure_model(self, model):
        self.models.append(model)
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        return "c1", self._answer


def test_triage_calls_model_and_parses(tmp_path):
    task = {"id": "T050", "goal": "X = 2", "tests": ["tests/x.py"]}
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "x.py").write_text("assert x == 2")
    code_files = [("src/x.py", "x = 1")]
    answer = '{"verdict": "code_wrong", "test": "tests/x.py", "reason": "x is 1"}'
    gw = FakeGateway(answer)
    result = triage.triage(gw, task, tmp_path, code_files, "FAILED")
    assert gw.models == [config.TRIAGER["model"]]
    messages, kw = gw.calls[0]
    assert kw["task"] == "T050"
    assert kw["role"] == "triage"
    assert kw["attempt"] == 1
    assert kw["model"] == config.TRIAGER["model"]
    assert kw["effort"] == config.TRIAGER["effort"]
    assert kw["max_tokens"] == config.TRIAGER["max_tokens"]
    assert kw["reasoning_budget"] == config.TRIAGER["reasoning_budget"]
    assert messages == triage.build_messages(task, tmp_path, code_files, "FAILED")
    assert result == {"verdict": "code_wrong", "test": "tests/x.py", "reason": "x is 1"}


def test_triage_returns_unclear_on_garbage(tmp_path):
    task = {"id": "T051", "goal": "g", "tests": []}
    gw = FakeGateway("I think the test is wrong.")
    result = triage.triage(gw, task, tmp_path, [], "out")
    assert result == {"verdict": "unclear", "test": "", "reason": ""}
