r"""Tests for task plantests_outdated (P3, 2026-11-20, BACKLOG trial 4 round 2 a): old tests that pin old behaviour
cost a person five fixes in Orbit round 2 (exactly 3 levels, LEVELS[2] as the last level, ...), and the test writer
never saw them. Now it sees the existing tests that import the files a task writes, and it can name the ones the goal
makes wrong; a person then updates them before the run.

plantests.old_tests(cmap, task) -> sorted paths of the code map files under cmap["test_dir"] + "/" whose imports
include codemap.module_name(f) for some f in task["files"], leaving out the task's own tests.

plantests.build_messages(task, root, example=None, earlier=(), memory=None, old=()): for each path in old that
exists under root, a part context.show_file(root, path, "EXISTING TEST THAT USES THESE FILES (it must keep passing
unless the goal changes what it checks)"), placed right before the "WRITE THESE TEST FILES" part; when old is not
empty the last part also says: "If the goal makes a test in those existing files wrong, name it at the top of your
new file in a comment line: OUTDATED: <path>::<test name> - <reason>". Without old the message is as before.

plantests.outdated(text) -> list of {"test": "<path>::<name>", "reason": ...} for every line matching
r"OUTDATED:\s*(\S+?::.+?)\s+-\s+(.+)$" (a test name may hold spaces; " - " ends it; the comment marker
before it, # or //, is ignored).

draft_tests builds the code map once (codemap.build(root)), passes old=old_tests(cmap, task) to build_messages, and
for each written draft with OUTDATED lines: logs f"{path}: outdated {test}: {reason}" per line, records
gw.telemetry.record("test_outdated", plan=plan_id, key=key, file=path, tests=[...]) and puts "outdated": the list
into that file's results entry (no "outdated" key when there are none)."""
import json
from pathlib import Path

import pytest

from stratos import codemap, config, plantests

TASK = {"key": "levels", "title": "Harder levels", "goal": "Add a fourth level.", "files": ["src/levels.js"],
        "tests": ["tests/levels4.test.js"], "protected": ["tests/levels4.test.js"]}


def test_old_tests():
    cmap = {"test_dir": "tests",
            "files": {"src/levels.js": [], "src/game.js": [], "tests/levels.test.js": [], "tests/game.test.js": [],
                      "tests/levels4.test.js": []},
            "imports": {"src/levels.js": [], "src/game.js": ["levels"], "tests/levels.test.js": ["levels"],
                        "tests/game.test.js": ["game", "vec"], "tests/levels4.test.js": ["levels"]}}
    assert plantests.old_tests(cmap, TASK) == ["tests/levels.test.js"]


def test_build_messages_shows_old_tests(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "levels.test.js").write_text('test("exactly 3 levels", () => {});\n', encoding="utf-8")
    user = plantests.build_messages(TASK, tmp_path, example="tests/none.js", old=["tests/levels.test.js"])[1]["content"]
    label = ("EXISTING TEST THAT USES THESE FILES (it must keep passing unless the goal changes what it checks): "
             "tests/levels.test.js")
    assert label in user
    assert user.index(label) < user.index("WRITE THESE TEST FILES")
    assert "OUTDATED: <path>::<test name> - <reason>" in user
    plain = plantests.build_messages(TASK, tmp_path, example="tests/none.js")[1]["content"]
    assert "EXISTING TEST THAT USES" not in plain and "OUTDATED" not in plain


def test_outdated():
    text = ('// OUTDATED: tests/levels.test.js::exactly 3 levels - the goal adds a fourth\n'
            '# OUTDATED: tests/test_a.py::test_b - b now returns a list\n'
            'test("x", () => {});\n')
    assert plantests.outdated(text) == [
        {"test": "tests/levels.test.js::exactly 3 levels", "reason": "the goal adds a fourth"},
        {"test": "tests/test_a.py::test_b", "reason": "b now returns a list"},
    ]
    assert plantests.outdated("no markers") == []


class FakeTelemetry:
    def __init__(self):
        self.events = []

    def record(self, kind, **fields):
        self.events.append({"kind": kind, **fields})


class FakeGateway:
    def __init__(self, answer):
        self.answer = answer
        self.telemetry = FakeTelemetry()
        self.prompts = []

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        self.prompts.append(messages[1]["content"])
        return "c1", self.answer


def test_draft_tests_reports_outdated(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    monkeypatch.setattr(plantests, "check_draft", lambda root, path: ("collected", ""))
    monkeypatch.setattr(plantests, "suite_leaks", lambda root, path, ignore=(): [])
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_old.py").write_text("from pkg.x import f\n\ndef test_f():\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(codemap, "build", lambda r: {"test_dir": "tests", "files": {"pkg/x.py": [],
                                                     "tests/test_old.py": []},
                                                     "imports": {"pkg/x.py": [], "tests/test_old.py": ["x"]}})
    (state / "plans").mkdir(parents=True)
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"], "tests": ["tests/test_new.py"],
            "protected": [], "after": [], "role": None}
    (state / "plans" / "P001.json").write_text(json.dumps({"id": "P001", "goal": "G", "tasks": [task],
                                                           "status": "draft", "hash": "h"}), encoding="utf-8")
    answer = ("FILE: tests/test_new.py\n```python\n# OUTDATED: tests/test_old.py::test_f - f now takes two arguments\n"
              "def test_g():\n    assert True\n```\n")
    gw = FakeGateway(answer)
    lines = []
    results = plantests.draft_tests(gw, "P001", root, state, log=lines.append)
    assert "EXISTING TEST THAT USES THESE FILES" in gw.prompts[0] and "tests/test_old.py" in gw.prompts[0]
    assert results == [{"key": "a", "file": "tests/test_new.py", "status": "collected",
                        "outdated": [{"test": "tests/test_old.py::test_f", "reason": "f now takes two arguments"}]}]
    assert "tests/test_new.py: outdated tests/test_old.py::test_f: f now takes two arguments" in lines
    (e,) = [e for e in gw.telemetry.events if e["kind"] == "test_outdated"]
    assert e == {"kind": "test_outdated", "plan": "P001", "key": "a", "file": "tests/test_new.py",
                 "tests": ["tests/test_old.py::test_f"]}
