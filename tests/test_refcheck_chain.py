"""Tests for task refcheck_chain (P7, 2026-11-20, found by Claude reading T186): when plan-tests runs, no task's code
exists yet, so the reference for a task that uses an earlier task's module (Drift: game uses slide.js) would fail on
the missing import and be judged "interface". The references now build on each other, in plan order.

refcheck.check(gw, plan_id, task, root, tests, extra=None) -> the same dict as before plus "files": the list of
(path, content) FILE blocks of this reference. extra: (path, content) pairs written into the copy before this task's
reference files (the earlier tasks' references); this task's own files win on the same path. The copy also leaves
out ".venv", "venv" and folders whose name ends in "-wt".
plantests.draft_tests passes extra = every "files" of the reference checks run before it in this plan (in plan
order), so a later reference can import an earlier one. An "error" result adds nothing."""
import json

from stratos import config, plantests, refcheck

GOOD_A = "FILE: pkg/a.py\n```python\ndef one():\n    return 1\n```\n"
GOOD_B = "FILE: pkg/b.py\n```python\nfrom pkg.a import one\n\n\ndef two():\n    return one() + 1\n```\n"


class GW:
    def __init__(self, answers):
        self.answers = list(answers)

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        return "c", self.answers.pop(0)


def test_extra_files_let_a_reference_import_an_earlier_one(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / ".venv" / "lib").mkdir(parents=True)
    (root / ".venv" / "lib" / "huge.py").write_text("x = 1\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_b.py").write_text("from pkg.b import two\n\n\ndef test_two():\n    assert two() == 2\n",
                                              encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "source_dirs": ["pkg"],
                                            "test_command": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]})
    monkeypatch.setattr(config, "REF_WRITER", {"model": "m", "effort": "low", "max_tokens": 9})
    task_b = {"key": "b", "goal": "two() is one() + 1", "files": ["pkg/b.py"], "tests": ["tests/test_b.py"]}
    alone = refcheck.check(GW([GOOD_B]), "P1", task_b, root, ["tests/test_b.py"])
    assert alone["status"] == "interface"
    chained = refcheck.check(GW([GOOD_B]), "P1", task_b, root, ["tests/test_b.py"],
                             extra=[("pkg/a.py", "def one():\n    return 1\n")])
    assert chained["status"] == "agree"
    assert chained["files"] == [("pkg/b.py", "from pkg.a import one\n\n\ndef two():\n    return one() + 1\n")]


def test_draft_tests_passes_earlier_references(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    monkeypatch.setattr(config, "REF_CHECK", True)
    monkeypatch.setattr(plantests, "check_draft", lambda root, path: ("collected", ""))
    monkeypatch.setattr(plantests, "suite_leaks", lambda root, path, ignore=(): [])
    root = tmp_path / "repo"
    root.mkdir()
    tasks = [{"key": k, "title": k, "goal": "G", "files": [f"pkg/{k}.py"], "tests": [f"tests/test_{k}.py"],
              "protected": [], "after": [], "role": None} for k in ("a", "b", "c")]
    (state / "plans").mkdir(parents=True)
    (state / "plans" / "P001.json").write_text(json.dumps({"id": "P001", "goal": "G", "tasks": tasks,
                                                           "status": "draft", "hash": "h"}), encoding="utf-8")
    seen = []

    def fake_check(gw, plan_id, task, root, tests, extra=None):
        seen.append((task["key"], list(extra or [])))
        if task["key"] == "b":
            return {"status": "error", "total": 0, "failing": [], "first_error": "x", "files": []}
        return {"status": "agree", "total": 1, "failing": [], "first_error": "",
                "files": [(f"pkg/{task['key']}.py", task["key"])]}
    monkeypatch.setattr(refcheck, "check", fake_check)

    class G:
        telemetry = type("T", (), {"record": lambda self, kind, **f: None})()

        def ensure_model(self, model):
            return 0.0

        def chat(self, messages, **kw):
            name = messages[1]["content"].split("WRITE THESE TEST FILES: ")[1].split()[0]
            return "c", f"FILE: {name}\n```python\ndef test_x():\n    assert True\n```\n"
    plantests.draft_tests(G(), "P001", root, state, log=lambda s: None)
    assert seen == [("a", []), ("b", [("pkg/a.py", "a")]), ("c", [("pkg/a.py", "a")])]
