"""Tests for task facts-b-model: config.FACTS_B replaces config.FACTS_B_ROLE as program B's model setting.

config.FACTS_B: a model-setting dict {"model", "effort", "max_tokens"} (like ROLES entries).
Default: {"model": "flint-40b-a2.5b-ud-q4_k_xl", "effort": "low", "max_tokens": 24000}.
When STRATOS_FACTS_B names a key of config.ROLES, FACTS_B is that role's setting dict.
Any other env value keeps the default.
config.FACTS_B_ROLE is removed; derive uses config.FACTS_B (model, effort, max_tokens) for program B.

OUTDATED: tests/test_facts.py::test_derive_program_b_fails -
  asserts gw.models == [REF_WRITER["model"], ROLES["coder"]["model"]];
  B now uses FACTS_B["model"] = "flint-40b-a2.5b-ud-q4_k_xl", not ROLES["coder"]["model"].
OUTDATED: tests/test_facts.py::test_derive_agree_checks_gateway_calls -
  asserts kw2["model"] == ROLES["coder"]["model"]; now FACTS_B["model"].
OUTDATED: tests/test_facts_full.py::test_facts_b_role_default -
  tests config.FACTS_B_ROLE == "coder"; FACTS_B_ROLE is removed, FACTS_B is a dict.
OUTDATED: tests/test_facts_full.py::test_facts_b_role_env_var -
  tests FACTS_B_ROLE == "reviewer"; FACTS_B_ROLE removed, FACTS_B = ROLES["reviewer"].
OUTDATED: tests/test_facts_full.py::test_facts_b_role_fallback -
  tests FACTS_B_ROLE fallback to "coder"; FACTS_B_ROLE removed, FACTS_B keeps default.
OUTDATED: tests/test_facts_full.py::test_derive_b_uses_facts_b_role -
  tests second model == ROLES[FACTS_B_ROLE]["model"]; FACTS_B_ROLE removed.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from stratos import config, facts


# ---- helpers ----

def _fake_run(returncode, stdout, stderr):
    def run(cmd, **kw):
        return subprocess.CompletedProcess(
            cmd, returncode, stdout.encode(), stderr.encode())
    return run


def _setup_run(monkeypatch, returncode, stdout, stderr):
    monkeypatch.setattr(facts.subprocess, "run",
                        _fake_run(returncode, stdout, stderr))


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


DEFAULT_B = {"model": "flint-40b-a2.5b-ud-q4_k_xl", "effort": "low", "max_tokens": 24000}

# ---- 1: default FACTS_B when env not set ----

def test_facts_b_default_in_child_process():
    # env STRATOS_FACTS_B not set → FACTS_B is the default dict.
    # Check in a child process because config reads env at import time.
    # Expected: FACTS_B["model"] == "flint-40b-a2.5b-ud-q4_k_xl"
    r = subprocess.run(
        [sys.executable, "-c",
         "import os; os.environ.pop('STRATOS_FACTS_B', None); "
         "from stratos import config; print(config.FACTS_B['model'])"],
        capture_output=True, text=True,
        env=dict(os.environ, STRATOS_FACTS_B=""),
        cwd=str(Path(__file__).resolve().parent.parent))
    # step: env is set to empty string, which is not a key of ROLES → default
    # Expected: printed model is the default Flint model
    assert r.stdout.strip() == "flint-40b-a2.5b-ud-q4_k_xl"


# ---- 2: FACTS_B when env names a valid ROLES key ----

def test_facts_b_env_names_reviewer_role():
    # env STRATOS_FACTS_B = "reviewer", which IS a key of ROLES.
    # FACTS_B must be ROLES["reviewer"].
    # Check in child process.
    # Expected: FACTS_B["model"] == config.ROLES["reviewer"]["model"]
    # ROLES["reviewer"]["model"] == "tiel-coder-35b-a3b-ud-q4_k_xl"
    r = subprocess.run(
        [sys.executable, "-c",
         "from stratos import config; print(config.FACTS_B['model'])"],
        capture_output=True, text=True,
        env=dict(os.environ, STRATOS_FACTS_B="reviewer"),
        cwd=str(Path(__file__).resolve().parent.parent))
    # step: "reviewer" is in ROLES → FACTS_B = ROLES["reviewer"]
    # step: ROLES["reviewer"]["model"] = "tiel-coder-35b-a3b-ud-q4_k_xl"
    # Expected: child prints the reviewer's model
    assert r.stdout.strip() == config.ROLES["reviewer"]["model"]


# ---- 3: FACTS_B when env is not a key of ROLES → default ----

def test_facts_b_env_invalid_keeps_default():
    # env STRATOS_FACTS_B = "painter" → not in ROLES → keeps the default.
    # Check in child process.
    # Expected: FACTS_B["model"] == "flint-40b-a2.5b-ud-q4_k_xl"
    r = subprocess.run(
        [sys.executable, "-c",
         "from stratos import config; print(config.FACTS_B['model'])"],
        capture_output=True, text=True,
        env=dict(os.environ, STRATOS_FACTS_B="painter"),
        cwd=str(Path(__file__).resolve().parent.parent))
    # step: "painter" is not a key of ROLES → FACTS_B = default
    # Expected: child prints the default model
    assert r.stdout.strip() == "flint-40b-a2.5b-ud-q4_k_xl"


# ---- 4: FACTS_B is a dict, not a role-name string ----

def test_facts_b_is_a_model_setting_dict():
    # FACTS_B must be a dict with keys model, effort, max_tokens.
    # Expected: FACTS_B is a dict
    assert isinstance(config.FACTS_B, dict)
    # Expected: has exactly "model", "effort", "max_tokens"
    assert "model" in config.FACTS_B
    assert "effort" in config.FACTS_B
    assert "max_tokens" in config.FACTS_B


# ---- 5: FACTS_B default values ----

def test_facts_b_default_model_value():
    # Default model is "flint-40b-a2.5b-ud-q4_k_xl".
    # step: the benchmark named Flint as the best program B model
    # Expected: config.FACTS_B["model"] == "flint-40b-a2.5b-ud-q4_k_xl"
    assert config.FACTS_B["model"] == "flint-40b-a2.5b-ud-q4_k_xl"


def test_facts_b_default_effort_value():
    # Default effort is "low".
    # Expected: config.FACTS_B["effort"] == "low"
    assert config.FACTS_B["effort"] == "low"


def test_facts_b_default_max_tokens_value():
    # Default max_tokens is 24000.
    # Expected: config.FACTS_B["max_tokens"] == 24000
    assert config.FACTS_B["max_tokens"] == 24000


# ---- 6: derive uses FACTS_B model for B ----

def test_derive_b_model_is_facts_b_model(monkeypatch):
    # Monkeypatch FACTS_B to a known dict with a distinctive model.
    # A prints {"a": {"x": 1}}, B prints same.
    # Expected: second chat call's model == "custom-b-model"
    facts_b = {"model": "custom-b-model", "effort": "medium", "max_tokens": 5000}
    monkeypatch.setattr(config, "FACTS_B", facts_b)
    code = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    answer = _code_answer(code)
    _setup_run(monkeypatch, 0, '{"a": {"x": 1}}', '')
    gw = FakeGateway([("c1", answer), ("c2", answer)])
    facts.derive(gw, "rules", log=_log)
    # step: first chat is REF_WRITER, second chat is FACTS_B
    # Expected: second chat model == "custom-b-model"
    assert gw.calls[1][1]["model"] == "custom-b-model"


# ---- 7: derive uses FACTS_B effort for B ----

def test_derive_b_effort_is_facts_b_effort(monkeypatch):
    # Monkeypatch FACTS_B: effort = "high".
    # Expected: second chat call's effort == "high"
    facts_b = {"model": "m2", "effort": "high", "max_tokens": 1000}
    monkeypatch.setattr(config, "FACTS_B", facts_b)
    code = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    answer = _code_answer(code)
    _setup_run(monkeypatch, 0, '{"a": {"x": 1}}', '')
    gw = FakeGateway([("c1", answer), ("c2", answer)])
    facts.derive(gw, "rules", log=_log)
    # step: FACTS_B["effort"] = "high"
    # Expected: second chat effort == "high"
    assert gw.calls[1][1]["effort"] == "high"


# ---- 8: derive uses FACTS_B max_tokens for B ----

def test_derive_b_max_tokens_is_facts_b_max_tokens(monkeypatch):
    # Monkeypatch FACTS_B: max_tokens = 9999.
    # Expected: second chat call's max_tokens == 9999
    facts_b = {"model": "m3", "effort": "low", "max_tokens": 9999}
    monkeypatch.setattr(config, "FACTS_B", facts_b)
    code = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    answer = _code_answer(code)
    _setup_run(monkeypatch, 0, '{"a": {"x": 1}}', '')
    gw = FakeGateway([("c1", answer), ("c2", answer)])
    facts.derive(gw, "rules", log=_log)
    # step: FACTS_B["max_tokens"] = 9999
    # Expected: second chat max_tokens == 9999
    assert gw.calls[1][1]["max_tokens"] == 9999


# ---- 9: ensure_model is called with FACTS_B model ----

def test_derive_ensure_model_uses_facts_b_model(monkeypatch):
    # FACTS_B model "model-X" must appear in gw.models as the second entry.
    # Expected: gw.models == [REF_WRITER["model"], "model-X"]
    facts_b = {"model": "model-X", "effort": "low", "max_tokens": 1000}
    monkeypatch.setattr(config, "FACTS_B", facts_b)
    code = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    answer = _code_answer(code)
    _setup_run(monkeypatch, 0, '{"a": {"x": 1}}', '')
    gw = FakeGateway([("c1", answer), ("c2", answer)])
    facts.derive(gw, "rules", log=_log)
    # step: ensure_model called with REF_WRITER model, then FACTS_B model
    # Expected: two entries in models
    assert gw.models == [config.REF_WRITER["model"], "model-X"]


# ---- 10: FACTS_B_ROLE does not exist ----

def test_facts_b_role_is_removed():
    # config.FACTS_B_ROLE must no longer exist.
    # Expected: FACTS_B_ROLE is not an attribute of config
    assert not hasattr(config, "FACTS_B_ROLE")


# ---- 11: derive B gets no reasoning_budget when FACTS_B has none ----

def test_derive_b_no_reasoning_budget_from_facts_b(monkeypatch):
    # FACTS_B = {"model":"m", "effort":"low", "max_tokens":1000} (no reasoning_budget key).
    # Expected: second chat receives no reasoning_budget (None)
    facts_b = {"model": "m-no-rb", "effort": "low", "max_tokens": 1000}
    monkeypatch.setattr(config, "FACTS_B", facts_b)
    code = 'import json\nprint(json.dumps({"a": {"x": 1}}))'
    answer = _code_answer(code)
    _setup_run(monkeypatch, 0, '{"a": {"x": 1}}', '')
    gw = FakeGateway([("c1", answer), ("c2", answer)])
    facts.derive(gw, "rules", log=_log)
    # step: FACTS_B has no reasoning_budget key
    # Expected: kw2.get("reasoning_budget") is None
    kw2 = gw.calls[1][1]
    assert kw2.get("reasoning_budget") is None
