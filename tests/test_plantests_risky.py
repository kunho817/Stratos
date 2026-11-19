"""Tests for task risky_drafts: plantests.risky_patterns and the "risky" draft status (plan P010).

Four of P009's six test drafts had to be fixed or rewritten, all for global state that leaks into later tests:
importlib.reload, replacing a module in sys.modules, a hand-made pytest.MonkeyPatch(), and `config.X = ...` without
monkeypatch.

risky_patterns(text) -> list of labels, each at most once, in this fixed order:
  "importlib.reload"       importlib.reload( or "from importlib import reload"
  "sys.modules"            sys.modules[...] = ..., del sys.modules[...], sys.modules.pop/update/setdefault/clear(
  "os.environ assignment"  os.environ[...] = ..., del os.environ[...], os.environ.pop/update/setdefault/clear(
  "config assignment"      a line that starts (after indentation) with config.NAME = or config.NAME[...] = ...
  "own MonkeyPatch"        MonkeyPatch()
Lines whose first non-space character is "#" are ignored. Reading (os.environ.get, config.X == 1, a docstring that
only names sys.modules) is not risky.

draft_tests: a written .py draft whose check_draft status is "collected" and that has risky patterns gets the status
"risky" instead; it is still written. The log line is f"{path}: risky: {', '.join(labels)}" and the "test_draft"
telemetry event gets risks=labels. Other statuses and non-.py drafts are unchanged and get no risks field."""
import json
from pathlib import Path

import pytest

from stratos import config, plantests


def test_a_clean_draft():
    text = ("import os\nfrom stratos import config\n\n\ndef test_a(monkeypatch, tmp_path):\n"
            "    monkeypatch.setattr(config, 'STATE_DIR', tmp_path)\n    monkeypatch.setenv('X', '1')\n"
            "    assert os.environ.get('X') == '1'\n    assert config.TRIAGE == config.TRIAGE\n")
    assert plantests.risky_patterns(text) == []


def test_reload():
    assert plantests.risky_patterns("import importlib\nimportlib.reload(config)\n") == ["importlib.reload"]
    assert plantests.risky_patterns("from importlib import reload\n") == ["importlib.reload"]


def test_sys_modules():
    assert plantests.risky_patterns('sys.modules["stratos.triage"] = fake\n') == ["sys.modules"]
    assert plantests.risky_patterns('del sys.modules["stratos.triage"]\n') == ["sys.modules"]
    assert plantests.risky_patterns('sys.modules.pop("stratos.triage")\n') == ["sys.modules"]
    assert plantests.risky_patterns('"""The old draft replaced stratos.triage in sys.modules."""\n') == []


def test_environ():
    assert plantests.risky_patterns('os.environ["STRATOS_REPO"] = str(tmp_path)\n') == ["os.environ assignment"]
    assert plantests.risky_patterns('os.environ.update({"A": "1"})\n') == ["os.environ assignment"]
    assert plantests.risky_patterns('del os.environ["A"]\n') == ["os.environ assignment"]
    assert plantests.risky_patterns('x = os.environ["A"]\nif os.environ["A"] == "1":\n    pass\n') == []


def test_config_assignment():
    assert plantests.risky_patterns("def test_a(tmp_path):\n    config.STATE_DIR = tmp_path\n") == \
        ["config assignment"]
    assert plantests.risky_patterns('config.PROJECT["language"] = "js"\n') == ["config assignment"]
    assert plantests.risky_patterns("assert config.TRIAGE == True\nold = config.TRIAGE\n") == []


def test_own_monkeypatch():
    assert plantests.risky_patterns("mp = pytest.MonkeyPatch()\n") == ["own MonkeyPatch"]


def test_comments_are_ignored():
    assert plantests.risky_patterns("# config.STATE_DIR = tmp_path\n    # importlib.reload(x)\n") == []


def test_every_kind_once_in_order():
    text = ("mp = pytest.MonkeyPatch()\nconfig.A = 1\nconfig.B = 2\nos.environ['A'] = '1'\n"
            "sys.modules['x'] = y\nimportlib.reload(config)\n")
    assert plantests.risky_patterns(text) == \
        ["importlib.reload", "sys.modules", "os.environ assignment", "config assignment", "own MonkeyPatch"]


class FakeTelemetry:
    def __init__(self):
        self.events = []

    def record(self, kind, **fields):
        self.events.append({"kind": kind, **fields})


class FakeGateway:
    def __init__(self, answer):
        self.answer = answer
        self.telemetry = FakeTelemetry()

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        return "c1", self.answer


@pytest.fixture
def env(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    monkeypatch.setattr(plantests, "check_draft", lambda root, path: ("collected", ""))
    # the suite check of a later task must not run a real test suite here
    monkeypatch.setattr(plantests, "suite_leaks", lambda root, path: [], raising=False)
    root = tmp_path / "repo"
    root.mkdir()

    def write_plan(tests):
        plans = state / "plans"
        plans.mkdir(parents=True, exist_ok=True)
        task = {"key": "a", "title": "T", "goal": "G", "files": ["stratos/x.py"], "tests": tests,
                "protected": [], "after": [], "role": None}
        (plans / "P001.json").write_text(json.dumps({"id": "P001", "goal": "G", "tasks": [task],
                                                     "status": "draft", "hash": "h"}), encoding="utf-8")
    return state, root, write_plan


RISKY = "FILE: tests/test_x.py\n```python\nfrom stratos import config\n\n\ndef test_a(tmp_path):\n" \
        "    config.STATE_DIR = tmp_path\n```\n"
CLEAN = "FILE: tests/test_x.py\n```python\ndef test_a():\n    assert True\n```\n"


def test_a_risky_draft(env):
    state, root, write_plan = env
    write_plan(["tests/test_x.py"])
    gw = FakeGateway(RISKY)
    lines = []
    results = plantests.draft_tests(gw, "P001", root, state, log=lines.append)
    assert results == [{"key": "a", "file": "tests/test_x.py", "status": "risky"}]
    assert Path(root, "tests/test_x.py").exists()
    assert "tests/test_x.py: risky: config assignment" in lines
    (e,) = gw.telemetry.events
    assert (e["kind"], e["status"], e["risks"]) == ("test_draft", "risky", ["config assignment"])


def test_a_clean_draft_has_no_risks_field(env):
    state, root, write_plan = env
    write_plan(["tests/test_x.py"])
    gw = FakeGateway(CLEAN)
    results = plantests.draft_tests(gw, "P001", root, state, log=lambda s: None)
    assert results[0]["status"] == "collected"
    assert "risks" not in gw.telemetry.events[0]


def test_a_draft_that_does_not_collect_stays_as_it_is(env, monkeypatch):
    state, root, write_plan = env
    monkeypatch.setattr(plantests, "check_draft", lambda root, path: ("import_error", "boom"))
    write_plan(["tests/test_x.py"])
    gw = FakeGateway(RISKY)
    assert plantests.draft_tests(gw, "P001", root, state, log=lambda s: None)[0]["status"] == "import_error"
    assert "risks" not in gw.telemetry.events[0]
