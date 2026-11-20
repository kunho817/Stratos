"""Tests for task plantests_cases (P11, 2026-11-20): a plan task may carry "cases" (a list of case lines, the format of
stratos/cases.py) that Claude writes instead of reviewing a model's draft.

plantests.draft_tests: for a task whose "cases" list is not empty:
- parsed = cases.parse("\\n".join(task["cases"])); when parsed["other"] is empty, the first test path of the task
  (when it does not exist yet) is written as cases.render(parsed) WITHOUT a model call, logged as
  f"{path}: written from {n} cases (no model)", and then checked like any draft (check_draft, lint, ...);
- when some lines are not plain calls, the test writer is asked as before, and its user message ends with the part
  "CASES (write one test for each, with exactly these values):\\n" + the case lines joined by "\\n".
Tasks without "cases" are drafted as before."""
import json

from stratos import codemap, config, plantests
from test_plantests_outdated import FakeGateway


def setup(tmp_path, monkeypatch, task):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    monkeypatch.setattr(plantests, "check_draft", lambda root, path: ("collected", ""))
    monkeypatch.setattr(plantests, "suite_leaks", lambda root, path, ignore=(): [])
    monkeypatch.setattr(codemap, "build", lambda r: {"test_dir": "tests", "files": {}, "imports": {}})
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (state / "plans").mkdir(parents=True)
    base = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/m.py"], "tests": ["tests/test_m.py"],
            "protected": [], "after": [], "role": None}
    base.update(task)
    (state / "plans" / "P001.json").write_text(json.dumps({"id": "P001", "goal": "G", "tasks": [base],
                                                           "status": "draft", "hash": "h"}), encoding="utf-8")
    return root, state


def test_plain_cases_need_no_model(tmp_path, monkeypatch):
    root, state = setup(tmp_path, monkeypatch, {"cases": ["pkg.m.f(1) == 2", "pkg.m.f(-1) raises ValueError"]})
    gw = FakeGateway("should not be used")
    lines = []
    results = plantests.draft_tests(gw, "P001", root, state, log=lines.append)
    assert gw.prompts == []
    assert "tests/test_m.py: written from 2 cases (no model)" in lines
    assert results[0]["file"] == "tests/test_m.py" and results[0]["status"] == "collected"
    text = (root / "tests" / "test_m.py").read_text(encoding="utf-8")
    assert "from pkg.m import f" in text and "def test_f_2():" in text


def test_other_lines_go_to_the_test_writer(tmp_path, monkeypatch):
    root, state = setup(tmp_path, monkeypatch, {"cases": ["pkg.m.f(1) == 2", "f reads the file it is given"]})
    gw = FakeGateway("FILE: tests/test_m.py\n```python\ndef test_x():\n    assert True\n```\n")
    plantests.draft_tests(gw, "P001", root, state, log=lambda s: None)
    assert len(gw.prompts) == 1
    assert gw.prompts[0].endswith("CASES (write one test for each, with exactly these values):\n"
                                  "pkg.m.f(1) == 2\nf reads the file it is given")
