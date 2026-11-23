"""Tests for task facts_run_full: facts.run_program_full, derive changes, FACTS_B_ROLE.

run_program_full(code, timeout=20) -> (obj, error):
  obj: dict on success, None on failure.
  error: None on success, otherwise one of:
    "exit code <n>: <last 2000 chars of stderr>"
    "no output"
    "output is not JSON: <first 200 chars of stdout>"
    "output is not a JSON object"
    "timed out after <timeout> s"
  run_program(code, timeout=20) returns run_program_full(code, timeout)[0].

derive uses run_program_full; when keep is a dict, also sets:
  keep["a_program"], keep["b_program"] (code text or None),
  keep["a_error"], keep["b_error"] (run_program_full error,
  "no program in the answer", "a fact is not a JSON object", None).
  Model B uses config.ROLES[config.FACTS_B_ROLE].

config.FACTS_B_ROLE = os.environ.get("STRATOS_FACTS_B", "coder");
  falls back to "coder" if not in config.ROLES.

cmd_facts writes <plan>-a.py / <plan>-b.py for non-None programs,
  <plan>-a-error.txt / <plan>-b-error.txt for non-None errors.

OUTDATED: tests/test_facts_cmd_save.py::test_derive_receives_keep_kwarg -
  the new derive sets more keys in keep (a_program, b_program, a_error, b_error);
  the existing test checks keep starts as {} which is still true.
OUTDATED: tests/test_facts_disagree.py::test_keep_on_agree -
  keep now also carries a_program/b_program/a_error/b_error; the test checks
  keep["a"] and keep["b"] which remain unchanged, so it stays valid.
OUTDATED: tests/test_facts.py::test_derive_agree_checks_gateway_calls -
  model B now uses config.ROLES[config.FACTS_B_ROLE] (default "coder"),
  so the second model name is config.ROLES["coder"]["model"] — the same value
  when FACTS_B_ROLE defaults to "coder". This test stays valid.
OUTDATED: tests/test_facts.py::test_derive_program_b_fails -
  same: FACTS_B_ROLE defaults to "coder" so the model is ROLES["coder"]["model"].
  The test's assertion gw.models == [REF_WRITER["model"], ROLES["coder"]["model"]]
  is unchanged.
OUTDATED: tests/test_cli_facts.py::test_derive_gets_gateway_and_goal -
  derive signature keeps (gw, goal) as positional args; keep= is keyword.
  This test stays valid.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from stratos import config, facts
from stratos import __main__ as cli
from stratos.telemetry import Telemetry


# ---- helpers ----

def _fake_run(returncode, stdout, stderr):
    """Fake subprocess.run returning a CompletedProcess."""
    def run(cmd, **kw):
        return subprocess.CompletedProcess(
            cmd, returncode, stdout.encode(), stderr.encode())
    return run


def _setup_run(monkeypatch, returncode, stdout, stderr):
    """Monkeypatch facts.subprocess.run to return the canned result."""
    monkeypatch.setattr(facts.subprocess, "run",
                        _fake_run(returncode, stdout, stderr))


def _setup_timeout(monkeypatch):
    """Monkeypatch facts.subprocess.run to raise TimeoutExpired."""
    def run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 0))
    monkeypatch.setattr(facts.subprocess, "run", run)


class FakeGateway:
    def __init__(self, answers):
        self.answers = list(answers)
        self.models = []
        self.calls = []

    def ensure_model(self, model):
        self.models.append(model)

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        return self.answers.pop(0)


def _log(*a):
    pass


def _code_answer(code):
    return f"```python\n{code}\n```"


def _plan(pid="P001", goal="the goal", tasks=None):
    if tasks is None:
        tasks = [{"key": "T1", "title": "a", "goal": "g",
                  "files": ["a.py"], "tests": ["tests/t.py"],
                  "protected": [], "after": [], "role": "coder"}]
    return {"id": pid, "goal": goal, "tasks": tasks,
            "status": "draft", "hash": "abc"}


def _setup_cli(tmp_path, monkeypatch, plan):
    """Point config at tmp_path, write plan file, stub gateway."""
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    (tmp_path / "repo").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("stratos.__main__.Gateway",
                        lambda tel: FakeGateway([]))
    monkeypatch.setattr(cli, "refresh_memory", lambda: None)
    plans_dir = tmp_path / "state" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / f"{plan['id']}.json").write_text(
        json.dumps(plan, indent=1), encoding="utf-8")
    return tmp_path / "state"


# ---- 1: run_program_full success ----

def test_run_program_full_success(monkeypatch):
    # Code prints {"a": {"x": 1}} — valid JSON dict.
    # subprocess: returncode=0, stdout='{"a": {"x": 1}}', stderr=''
    # Expected: obj == {"a": {"x": 1}}, error == None
    code = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    _setup_run(monkeypatch, 0, '{"a": {"x": 1}}', '')
    obj, error = facts.run_program_full(code)
    # Expected: obj is the parsed dict
    assert obj == {"a": {"x": 1}}
    # Expected: error is None on success
    assert error is None


# ---- 2: run_program_full exit code ----

def test_run_program_full_exit_code(monkeypatch):
    # Code crashes → returncode=1, stderr='boom'.
    # Last 2000 chars of "boom" = "boom".
    # Expected: obj == None, error == "exit code 1: boom"
    code = 'raise Exception("boom")'
    _setup_run(monkeypatch, 1, '', 'boom')
    obj, error = facts.run_program_full(code)
    # Expected: obj is None
    assert obj is None
    # Expected: "exit code 1: boom"
    assert error == "exit code 1: boom"


# ---- 3: run_program_full no output ----

def test_run_program_full_no_output(monkeypatch):
    # Code prints nothing → returncode=0, stdout=''.
    # Expected: obj == None, error == "no output"
    code = 'pass'
    _setup_run(monkeypatch, 0, '', '')
    obj, error = facts.run_program_full(code)
    # Expected: obj is None
    assert obj is None
    # Expected: "no output"
    assert error == "no output"


# ---- 4: run_program_full non-JSON stdout ----

def test_run_program_full_not_json(monkeypatch):
    # stdout = "not json" → not valid JSON.
    # First 200 chars of "not json" = "not json".
    # Expected: obj == None, error == "output is not JSON: not json"
    code = 'print("not json")'
    _setup_run(monkeypatch, 0, 'not json', '')
    obj, error = facts.run_program_full(code)
    # Expected: obj is None
    assert obj is None
    # Expected: "output is not JSON: not json"
    assert error == "output is not JSON: not json"


# ---- 5: run_program_full JSON not a dict ----

def test_run_program_full_not_json_object(monkeypatch):
    # stdout = "[1, 2]" → valid JSON, but a list, not a dict.
    # Expected: obj == None, error == "output is not a JSON object"
    code = 'import json\nprint(json.dumps([1, 2]))'
    _setup_run(monkeypatch, 0, '[1, 2]', '')
    obj, error = facts.run_program_full(code)
    # Expected: obj is None
    assert obj is None
    # Expected: "output is not a JSON object"
    assert error == "output is not a JSON object"


# ---- 6: run_program_full timeout ----

def test_run_program_full_timeout(monkeypatch):
    # subprocess raises TimeoutExpired; timeout=1.
    # Expected: obj == None, error == "timed out after 1 s"
    code = 'import time; time.sleep(10)'
    _setup_timeout(monkeypatch)
    obj, error = facts.run_program_full(code, timeout=1)
    # Expected: obj is None
    assert obj is None
    # Expected: "timed out after 1 s"
    assert error == "timed out after 1 s"


# ---- 7: run_program delegates to run_program_full ----

def test_run_program_delegates_to_full(monkeypatch):
    # Monkeypatch run_program_full to return ({"x": 1}, "err").
    # run_program must return [0], i.e. just the obj.
    # Expected: facts.run_program("code") == {"x": 1}
    monkeypatch.setattr(facts, "run_program_full",
                        lambda code, timeout=20: ({"x": 1}, "err"))
    # Expected: the obj is returned
    assert facts.run_program("code") == {"x": 1}


# ---- 8: FACTS_B_ROLE default ----

def test_facts_b_role_default(monkeypatch):
    # env "STRATOS_FACTS_B" not set → default "coder".
    # "coder" IS in config.ROLES.
    # Expected: config.FACTS_B_ROLE == "coder"
    monkeypatch.delenv("STRATOS_FACTS_B", raising=False)
    val = os.environ.get("STRATOS_FACTS_B", "coder")
    # Expected: "coder"
    assert val == "coder"
    # Expected: in ROLES
    assert val in config.ROLES
    # Expected: config.FACTS_B_ROLE is the module attribute
    assert config.FACTS_B_ROLE == "coder"


# ---- 9: FACTS_B_ROLE env var set to a valid role ----

def test_facts_b_role_env_var(monkeypatch):
    # env "STRATOS_FACTS_B" = "reviewer", which IS in ROLES.
    # config reads env at import time, so check in a child process.
    # Expected: FACTS_B_ROLE == "reviewer"
    r = subprocess.run(
        [sys.executable, "-c", "from stratos import config; print(config.FACTS_B_ROLE)"],
        capture_output=True, text=True,
        env=dict(os.environ, STRATOS_FACTS_B="reviewer"),
        cwd=str(Path(__file__).resolve().parent.parent))
    # Expected: child prints "reviewer"
    assert r.stdout.strip() == "reviewer"


# ---- 10: FACTS_B_ROLE fallback when not in ROLES ----

def test_facts_b_role_fallback(monkeypatch):
    # env "STRATOS_FACTS_B" = "painter" → not in ROLES → "coder".
    # config reads env at import time, so check in a child process.
    # Expected: FACTS_B_ROLE falls back to "coder"
    r = subprocess.run(
        [sys.executable, "-c", "from stratos import config; print(config.FACTS_B_ROLE)"],
        capture_output=True, text=True,
        env=dict(os.environ, STRATOS_FACTS_B="painter"),
        cwd=str(Path(__file__).resolve().parent.parent))
    # Expected: child prints "coder" (fallback)
    assert r.stdout.strip() == "coder"


# ---- 11: derive keep: a_program, b_program, a_error, b_error on success ----

def test_derive_keep_program_error_success(monkeypatch):
    # A prints {"a": {"x": 1}}, B prints same → agree.
    # code_a = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    # run_program_full → (obj, None) for both.
    # Expected: keep["a_program"] == code_a + "\n", keep["a_error"] == None,
    #   keep["b_program"] == code_b + "\n", keep["b_error"] == None
    code = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    answer = _code_answer(code)
    _setup_run(monkeypatch, 0, '{"a": {"x": 1}}', '')
    gw = FakeGateway([("c1", answer), ("c2", answer)])
    keep = {}
    facts.derive(gw, "rules", log=_log, keep=keep)
    # Expected: a_program is the code text with final newline
    assert keep["a_program"] == code + "\n"
    # Expected: b_program is the code text with final newline
    assert keep["b_program"] == code + "\n"
    # Expected: a_error is None
    assert keep["a_error"] is None
    # Expected: b_error is None
    assert keep["b_error"] is None


# ---- 12: derive missing code block ----

def test_derive_no_program_in_answer(monkeypatch):
    # Model A answers "I have no code" (no fenced block).
    # _extract_code returns None.
    # Expected: keep["a_program"] == None,
    #   keep["a_error"] == "no program in the answer",
    #   keep["b_program"] == None, keep["b_error"] == None
    gw = FakeGateway([("c1", "I have no code")])
    keep = {}
    result = facts.derive(gw, "rules", log=_log, keep=keep)
    # Expected: a_program is None (no code extracted)
    assert keep["a_program"] is None
    # Expected: a_error == "no program in the answer"
    assert keep["a_error"] == "no program in the answer"
    # Expected: b_program is None (B never ran)
    assert keep["b_program"] is None
    # Expected: b_error is None (B never ran)
    assert keep["b_error"] is None
    # Expected: result reason is "program A failed"
    assert result["reason"] == "program A failed"


# ---- 13: derive non-dict fact → "a fact is not a JSON object" ----

def test_derive_non_dict_fact_error(monkeypatch):
    # A prints {"a": 42} — the fact value is 42, not a dict.
    # run_program_full returns ({"a": 42}, None) (valid JSON dict),
    # then derive validates each fact value.
    # Expected: keep["a_program"] == code_a + "\n",
    #   keep["a_error"] == "a fact is not a JSON object"
    code_a = 'import json\nprint(json.dumps({"a": 42}))'
    answer_a = _code_answer(code_a)
    _setup_run(monkeypatch, 0, '{"a": 42}', '')
    gw = FakeGateway([("c1", answer_a)])
    keep = {}
    result = facts.derive(gw, "rules", log=_log, keep=keep)
    # Expected: a_program is the code text with final newline
    assert keep["a_program"] == code_a + "\n"
    # Expected: a_error == "a fact is not a JSON object"
    assert keep["a_error"] == "a fact is not a JSON object"
    # Expected: b_program is None
    assert keep["b_program"] is None
    # Expected: b_error is None
    assert keep["b_error"] is None
    # Expected: result reason is "program A failed"
    assert result["reason"] == "program A failed"


# ---- 14: derive model B uses FACTS_B_ROLE ----

def test_derive_b_uses_facts_b_role(monkeypatch):
    # A prints {"a": {"x": 1}}, B prints same.
    # FACTS_B_ROLE defaults to "coder" → model is config.ROLES["coder"]["model"].
    # Expected: second chat call's model == config.ROLES["coder"]["model"]
    code = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    answer = _code_answer(code)
    _setup_run(monkeypatch, 0, '{"a": {"x": 1}}', '')
    gw = FakeGateway([("c1", answer), ("c2", answer)])
    facts.derive(gw, "rules", log=_log)
    # Expected: first chat uses REF_WRITER model
    assert gw.calls[0][1]["model"] == config.REF_WRITER["model"]
    # Expected: second chat uses FACTS_B_ROLE model
    role = config.FACTS_B_ROLE
    # FACTS_B_ROLE is "coder" by default
    # Expected: model == config.ROLES["coder"]["model"]
    assert gw.calls[1][1]["model"] == config.ROLES[role]["model"]



