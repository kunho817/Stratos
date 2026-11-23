"""Tests for task refcheck_writer: check gets writer=None keyword and every result carries "output".

check(gw, plan_id, task, root, tests, extra=None, writer=None):
  writer is a model-settings dict; config.REF_WRITER is the default when writer is None.
  writer's model, effort, max_tokens, reasoning_budget go to gw.chat.
  Every result dict that ran the tests carries "output": last 4000 chars of stdout+stderr combined.
  Results that did NOT run tests carry "output": "".

OUTDATED: tests/test_refcheck.py::test_check_error_without_a_file - expected dict must include "output": ""
"""

import subprocess
from contextlib import nullcontext

from stratos import config, refcheck

TASK = {"key": "add", "goal": "Write pkg/calc.py.",
        "files": ["pkg/calc.py"], "tests": ["tests/test_calc.py"]}
GOOD = "FILE: pkg/calc.py\n```python\ndef add(a, b):\n    return a + b\n```\n"
PASS_OUT = "2 passed in 0.1s"
FAIL_OUT = "FAILED tests/test_calc.py::test_w - assert 1 == 2\n1 failed, 2 passed in 0.1s"
CUSTOM = {"model": "custom", "effort": "high", "max_tokens": 500, "reasoning_budget": 1000}
NO_BUDGET = {"model": "nb", "effort": "none", "max_tokens": 100}


class FakeGW:
    def __init__(self, answer):
        self.answer = answer
        self.models = []
        self.chat_kw = []

    def ensure_model(self, model):
        self.models.append(model)

    def chat(self, messages, **kw):
        self.chat_kw.append(kw)
        return "c1", self.answer


def _env(tmp_path, monkeypatch, stdout="", stderr="", code=0):
    """Set up a minimal repo, stub config, mock subprocess.run."""
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_calc.py").write_text("x=1\n", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT", {
        **config.PROJECT,
        "source_dirs": ["pkg"],
        "test_command": ["pytest"],
        "writable_suffixes": [".py"],
    })
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "TEST_TIMEOUT_S", 30)
    monkeypatch.setattr(config, "MUTATION", False)
    monkeypatch.setattr(
        config, "REF_WRITER",
        {"model": "defmodel", "effort": "defeff", "max_tokens": 10, "reasoning_budget": 100},
    )
    monkeypatch.setattr(refcheck.verify, "syntax_errors", lambda root, paths: [])
    monkeypatch.setattr(refcheck.verify, "test_cmd", lambda tests: ["pytest"] + list(tests))
    monkeypatch.setattr(refcheck.verify, "dotnet_scope", lambda root, tests: nullcontext())
    monkeypatch.setattr(refcheck.langs, "child_env", lambda **kw: {})
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, code, stdout=stdout, stderr=stderr),
    )
    return root


# ---------- writer keyword ----------

def test_default_writer(tmp_path, monkeypatch):
    # writer=None → config.REF_WRITER used
    root = _env(tmp_path, monkeypatch, stdout=PASS_OUT, code=0)
    gw = FakeGW(GOOD)
    refcheck.check(gw, "P1", TASK, root, ["tests/test_calc.py"])
    # ensure_model called with config.REF_WRITER["model"] == "defmodel"
    assert gw.models == ["defmodel"]
    # Expected: chat kwargs match config.REF_WRITER
    kw = gw.chat_kw[0]
    assert kw["model"] == config.REF_WRITER["model"]
    assert kw["effort"] == config.REF_WRITER["effort"]
    assert kw["max_tokens"] == config.REF_WRITER["max_tokens"]
    # config.REF_WRITER has reasoning_budget → chat gets it
    assert kw["reasoning_budget"] == config.REF_WRITER["reasoning_budget"]


def test_custom_writer(tmp_path, monkeypatch):
    # writer=CUSTOM → model/effort/max_tokens/reasoning_budget from CUSTOM
    root = _env(tmp_path, monkeypatch, stdout=PASS_OUT, code=0)
    gw = FakeGW(GOOD)
    refcheck.check(gw, "P1", TASK, root, ["tests/test_calc.py"], writer=CUSTOM)
    # ensure_model called with CUSTOM["model"]
    assert gw.models == ["custom"]
    # Expected: chat kwargs from CUSTOM
    kw = gw.chat_kw[0]
    assert kw["model"] == "custom"
    assert kw["effort"] == "high"
    assert kw["max_tokens"] == 500
    # CUSTOM["reasoning_budget"] == 1000
    assert kw["reasoning_budget"] == 1000


def test_writer_without_reasoning_budget(tmp_path, monkeypatch):
    # writer dict lacks reasoning_budget → chat must not receive it
    root = _env(tmp_path, monkeypatch, stdout=PASS_OUT, code=0)
    gw = FakeGW(GOOD)
    refcheck.check(gw, "P1", TASK, root, ["tests/test_calc.py"], writer=NO_BUDGET)
    kw = gw.chat_kw[0]
    # Expected: model from NO_BUDGET
    assert kw["model"] == "nb"
    # Expected: no reasoning_budget key
    assert "reasoning_budget" not in kw


def test_ensure_model_uses_writer_model(tmp_path, monkeypatch):
    # ensure_model receives writer["model"], not config.REF_WRITER["model"]
    root = _env(tmp_path, monkeypatch, stdout=PASS_OUT, code=0)
    gw = FakeGW(GOOD)
    refcheck.check(gw, "P1", TASK, root, ["tests/test_calc.py"], writer=CUSTOM)
    # Expected: "custom", not "defmodel"
    assert gw.models == ["custom"]


# ---------- output in results that ran tests ----------

def test_output_in_passing_result(tmp_path, monkeypatch):
    # All tests pass (agree): result has "output" = last 4000 of stdout+stderr
    root = _env(tmp_path, monkeypatch, stdout=PASS_OUT, stderr="", code=0)
    gw = FakeGW(GOOD)
    r = refcheck.check(gw, "P1", TASK, root, ["tests/test_calc.py"])
    # Expected: r["output"] == PASS_OUT (20 chars, shorter than 4000, no truncation)
    assert r["output"] == PASS_OUT
    assert r["status"] == "agree"


def test_output_in_flagged_result(tmp_path, monkeypatch):
    # 1 of 3 tests fails → flagged; output present
    root = _env(tmp_path, monkeypatch, stdout=FAIL_OUT, stderr="", code=0)
    gw = FakeGW(GOOD)
    r = refcheck.check(gw, "P1", TASK, root, ["tests/test_calc.py"])
    # Expected: r["output"] == FAIL_OUT
    assert r["output"] == FAIL_OUT
    assert r["status"] == "flagged"


def test_output_last_4000_chars(tmp_path, monkeypatch):
    # stdout+stderr = 5000 chars; output is last 4000
    long_out = "x" * 5000
    root = _env(tmp_path, monkeypatch, stdout=long_out, stderr="", code=0)
    gw = FakeGW(GOOD)
    r = refcheck.check(gw, "P1", TASK, root, ["tests/test_calc.py"])
    # Expected: output == long_out[-4000:]
    assert r["output"] == long_out[-4000:]
    # Expected: len(output) == 4000
    assert len(r["output"]) == 4000


def test_output_is_stdout_plus_stderr(tmp_path, monkeypatch):
    # stdout = "s"*3000, stderr = "e"*2000 → combined "s"*3000+"e"*2000 (5000 chars)
    # last 4000 = "s"*2000 + "e"*2000
    root = _env(tmp_path, monkeypatch, stdout="s" * 3000, stderr="e" * 2000, code=0)
    gw = FakeGW(GOOD)
    r = refcheck.check(gw, "P1", TASK, root, ["tests/test_calc.py"])
    # Expected: "s"*2000 + "e"*2000
    assert r["output"] == "s" * 2000 + "e" * 2000
    assert len(r["output"]) == 4000


def test_output_in_agree_result(tmp_path, monkeypatch):
    # All pass, judge = agree; output present
    root = _env(tmp_path, monkeypatch, stdout="3 passed in 0.1s", code=0)
    gw = FakeGW(GOOD)
    r = refcheck.check(gw, "P1", TASK, root, ["tests/test_calc.py"])
    # Expected: status "agree"
    assert r["status"] == "agree"
    # Expected: output field present and non-empty
    assert r["output"] == "3 passed in 0.1s"


# ---------- output = "" for results that did not run tests ----------

def test_output_empty_no_file_in_answer(tmp_path, monkeypatch):
    # Model answer has no FILE blocks → early return, tests never ran
    root = _env(tmp_path, monkeypatch)
    monkeypatch.setattr(refcheck.patch, "read_answer",
        lambda root, text, allowed: {"edits": [], "whole": [], "files": [], "error": None})
    gw = FakeGW(GOOD)
    r = refcheck.check(gw, "P1", TASK, root, ["tests/test_calc.py"])
    # Expected: r == {"status":"error","total":0,"failing":[],"first_error":"no file in the answer","files":[],"output":""}
    assert r["output"] == ""
    assert r["status"] == "error"
    assert r["first_error"] == "no file in the answer"


def test_output_empty_parse_error(tmp_path, monkeypatch):
    # patch.read_answer returns an error → early return, tests never ran
    root = _env(tmp_path, monkeypatch)
    monkeypatch.setattr(refcheck.patch, "read_answer",
        lambda root, text, allowed: {
            "edits": [("pkg/calc.py", [("x", "y")])],
            "whole": [],
            "files": None,
            "error": Exception("no match"),
        })
    gw = FakeGW(GOOD)
    r = refcheck.check(gw, "P1", TASK, root, ["tests/test_calc.py"])
    # Expected: output == ""
    assert r["output"] == ""
    # Expected: status "error"
    assert r["status"] == "error"


def test_output_empty_syntax_error(tmp_path, monkeypatch):
    # Reference file has syntax errors → early return, tests never ran
    root = _env(tmp_path, monkeypatch)
    monkeypatch.setattr(refcheck.verify, "syntax_errors",
        lambda root, paths: ["pkg/calc.py: line 1: SyntaxError"])
    gw = FakeGW(GOOD)
    r = refcheck.check(gw, "P1", TASK, root, ["tests/test_calc.py"])
    # Expected: output == ""
    assert r["output"] == ""
    # Expected: status "error"
    assert r["status"] == "error"
    # Expected: first_error mentions syntax
    assert "syntax" in r["first_error"].lower()


# ---------- "no test ran" path: tests ran (subprocess completed) ----------

def test_output_in_no_test_ran(tmp_path, monkeypatch):
    # subprocess completes, no test ran: tests ran → output present
    out = "no tests ran"
    root = _env(tmp_path, monkeypatch, stdout=out, code=0)
    monkeypatch.setattr(refcheck, "count_tests", lambda o: (0, []))
    # force judge not reached
    gw = FakeGW(GOOD)
    r = refcheck.check(gw, "P1", TASK, root, ["tests/test_calc.py"])
    # Expected: status "error"
    assert r["status"] == "error"
    # Expected: output == out (tests ran, output present)
    assert r["output"] == out
    # Expected: first_error starts with "no test ran: "
    assert r["first_error"].startswith("no test ran: ")
