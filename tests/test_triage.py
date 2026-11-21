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


def test_test_files_are_read_as_utf8(tmp_path):
    """Review (2026-11-19): test files were read with the Windows default encoding (cp949 here)."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_k.py").write_text("# 한글 주석 — em dash\ndef test_k():\n    assert 1\n", encoding="utf-8")
    msgs = triage.build_messages({"id": "T1", "goal": "g", "tests": ["tests/test_k.py"]}, tmp_path, [], "out")
    assert "한글 주석 — em dash" in msgs[1]["content"]


def test_triager_settings_are_read_at_call_time(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TRIAGER", {"model": "other", "effort": "none", "max_tokens": 10})
    gw = FakeGateway('{"verdict": "unclear", "test": "", "reason": ""}')
    triage.triage(gw, {"id": "T1", "goal": "g", "tests": []}, tmp_path, [], "out")
    assert gw.models == ["other"]
    kw = gw.calls[0][1]
    assert (kw["model"], kw["effort"], kw["max_tokens"]) == ("other", "none", 10) and "reasoning_budget" not in kw


# ---- was test_triage_slim.py ----
# Tests for task triage_slim (P10, 2026-11-20): triage prompts reached 34k tokens because every test file of the task
# went in whole (a loop.py task lists ~17 old test files). Now triage sees only the failing tests and what they use.
#
# triage.test_parts(root, tests, test_output) -> [(path, text)]:
# - failing = decide._extract_ids(test_output); a failing id is "path::name" (a [param] suffix after the name is
#   cut) or a bare "path" (the file could not be imported);
# - the files shown are the paths of `tests` (any "::..." cut off) that some failing id names, in the order of
#   `tests`; when no failing id names any of them, every file of `tests` is shown whole (as before);
# - a file named by a bare id is shown whole; otherwise its text is: the lines before its first top-level def or
#   class or their decorators (imports, constants), without trailing blank lines, then the source of each
#   top-level function or class that is a failing test or that a shown one uses (codemap uses, followed until
#   nothing new is added - helpers, fixtures), from its first decorator line to its end, in file order; the parts
#   joined by "\n\n" (constants are shown once, in the first part);
# - a file that cannot be read gives "".
# triage.build_messages lists these parts under "Test files (the failing tests and what they use):" instead of
# every test file whole.


TEST = '''import pytest

from pkg import f

LIMIT = 3


def helper(x):
    return base() + x


def base():
    return 1


@pytest.fixture
def board():
    return [0] * LIMIT


def test_ok():
    assert f(1) == 1


def test_bad(board):
    assert f(helper(2)) == len(board)


def test_other():
    assert f(0) == 0
'''


def setup(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(TEST, encoding="utf-8")
    (tmp_path / "tests" / "test_b.py").write_text("def test_b():\n    assert 1\n", encoding="utf-8")
    return tmp_path


def test_only_the_failing_test_and_what_it_uses(tmp_path):
    root = setup(tmp_path)
    out = "FAILED tests/test_a.py::test_bad - assert 4 == 3\n1 failed, 3 passed"
    parts = triage.test_parts(root, ["tests/test_a.py", "tests/test_b.py"], out)
    assert [p for p, _ in parts] == ["tests/test_a.py"]
    text = parts[0][1]
    assert text.startswith("import pytest\n\nfrom pkg import f\n\nLIMIT = 3")
    assert "def helper(x):" in text and "def base():" in text and "@pytest.fixture\ndef board():" in text
    assert text.count("LIMIT = 3") == 1
    assert "def test_bad(board):" in text
    assert "test_ok" not in text and "test_other" not in text
    assert text.index("def helper") < text.index("def base") < text.index("def test_bad")


def test_params_and_import_errors(tmp_path):
    root = setup(tmp_path)
    out = "FAILED tests/test_a.py::test_other[1] - x\nERROR tests/test_b.py - ImportError: boom"
    parts = dict(triage.test_parts(root, ["tests/test_a.py", "tests/test_b.py::test_b"], out))
    assert "def test_other():" in parts["tests/test_a.py"] and "test_bad" not in parts["tests/test_a.py"]
    assert parts["tests/test_b.py"] == "def test_b():\n    assert 1\n"


def test_no_ids_shows_every_file_whole(tmp_path):
    root = setup(tmp_path)
    parts = triage.test_parts(root, ["tests/test_a.py", "tests/test_b.py"], "something broke")
    assert parts == [("tests/test_a.py", TEST), ("tests/test_b.py", "def test_b():\n    assert 1\n")]


def test_build_messages_uses_the_parts(tmp_path):
    root = setup(tmp_path)
    task = {"id": "T1", "goal": "g", "tests": ["tests/test_a.py", "tests/test_b.py"]}
    user = triage.build_messages(task, root, [], "FAILED tests/test_a.py::test_bad - x")[1]["content"]
    assert "Test files (the failing tests and what they use):" in user
    assert "def test_bad(board):" in user and "def test_ok" not in user and "test_b.py" not in user
