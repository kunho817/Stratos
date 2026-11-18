"""Tests for stratos/plantests.py (plan P003, task plantests_core): the planner model drafts the test files of the
tasks in a plan, for a person to read, fix and commit before the tasks run.

TEST_SYSTEM: the system prompt (a str): write pytest test files for the task; answer with FILE blocks
    ("FILE: tests/test_x.py" then a fenced block); a module docstring that describes the behaviour, then test
    functions; fakes (monkeypatch) instead of the network, the GPU and real models; the tests should fail until the
    task is done.
build_messages(task, root, example="tests/test_diagnose.py") -> [{"role": "system", "content": TEST_SYSTEM},
                                                                  {"role": "user", "content": ...}]
    The user content is "\n\n".join of: f"TASK {task['key']}: {task['title']}", task["goal"],
    "PROJECT FILES:\n" + plan.repo_summary(root), context.show_file(root, p, "FILE THE TASK WILL WRITE") for each p in
    task["files"], context.show_file(root, p, "READ-ONLY") for each p in task["protected"] that is not in
    task["tests"], context.show_file(root, example, "EXAMPLE OF THE TEST STYLE") when root/example exists, and last
    "WRITE THESE TEST FILES: " + ", ".join(task["tests"]).
check_draft(root, path) -> (status, detail)
    The file root/path must parse (ast.parse): else ("syntax_error", str(error)). Then
    [sys.executable, "-m", "pytest", "--collect-only", "-q", path] runs in root: exit code 0 -> ("collected", "");
    otherwise, when its output holds "ModuleNotFoundError" or "ImportError" -> ("import_error", the output's last
    2000 characters) (expected while the task's module does not exist yet); else ("error", the last 2000 characters).
draft_tests(gw, plan_id, root, state_dir, log=print) -> list of {"key", "file", "status"}
    Loads the plan (plan.load_plan(state_dir, plan_id); its KeyError is not caught), gw.ensure_model(planner model)
    once, then per task in order: gw.chat(build_messages(task, root), task=f"{plan_id}-{key}", role="test_writer",
    attempt=1, model=..., effort=..., max_tokens=...) with config.PLANNER's settings (plus reasoning_budget when set);
    the raw answer is saved to state_dir/"answers"/f"{plan_id}-{key}-tests.md"; files = patch.parse_files(answer,
    allowed=task["tests"]). Then per path in task["tests"]: not in the answer -> "missing"; root/path already exists
    -> "exists" (never overwritten; a log line says so); else the file is written (folders made) and its status is
    check_draft(root, path)[0]. Each path gets gw.telemetry.record("test_draft", plan=plan_id, key=key, file=path,
    status=status) and one result dict."""
import json
import sys

import pytest

from stratos import config, context, plan, plantests
from stratos.telemetry import Telemetry

TASK = {"key": "core", "title": "Add f", "goal": "Add f to stratos/m.py.", "files": ["stratos/m.py"],
        "tests": ["tests/test_m.py"], "protected": ["stratos/n.py", "tests/test_m.py"], "after": [], "role": None}


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "repo"
    (r / "stratos").mkdir(parents=True)
    (r / "tests").mkdir()
    (r / "stratos" / "n.py").write_text('"""N."""\ndef g(x):\n    return x\n', encoding="utf-8")
    (r / "tests" / "test_diagnose.py").write_text('"""Style."""\n\ndef test_a():\n    assert True\n', encoding="utf-8")
    return r


def test_system_prompt():
    for word in ("pytest", "FILE", "docstring", "fake"):
        assert word in plantests.TEST_SYSTEM


def test_build_messages(root):
    msgs = plantests.build_messages(TASK, root)
    assert [m["role"] for m in msgs] == ["system", "user"] and msgs[0]["content"] == plantests.TEST_SYSTEM
    want = "\n\n".join([
        "TASK core: Add f", "Add f to stratos/m.py.", "PROJECT FILES:\n" + plan.repo_summary(root),
        context.show_file(root, "stratos/m.py", "FILE THE TASK WILL WRITE"),
        context.show_file(root, "stratos/n.py", "READ-ONLY"),
        context.show_file(root, "tests/test_diagnose.py", "EXAMPLE OF THE TEST STYLE"),
        "WRITE THESE TEST FILES: tests/test_m.py",
    ])
    assert msgs[1]["content"] == want


def test_build_messages_without_the_example(root):
    user = plantests.build_messages(TASK, root, example="tests/none.py")[1]["content"]
    assert "EXAMPLE OF THE TEST STYLE" not in user and user.endswith("WRITE THESE TEST FILES: tests/test_m.py")


def test_check_draft(root):
    (root / "tests" / "test_ok.py").write_text("def test_a():\n    assert 1 == 2\n", encoding="utf-8")
    assert plantests.check_draft(root, "tests/test_ok.py") == ("collected", "")
    (root / "tests" / "test_new.py").write_text("import no_such_module_xyz\n\ndef test_a():\n    pass\n", encoding="utf-8")
    status, detail = plantests.check_draft(root, "tests/test_new.py")
    assert status == "import_error" and "no_such_module_xyz" in detail and len(detail) <= 2000
    (root / "tests" / "test_syntax.py").write_text("def test_a(:\n", encoding="utf-8")
    status, detail = plantests.check_draft(root, "tests/test_syntax.py")
    assert status == "syntax_error" and detail
    (root / "tests" / "test_err.py").write_text("raise RuntimeError('boom at import')\n", encoding="utf-8")
    status, detail = plantests.check_draft(root, "tests/test_err.py")
    assert status == "error" and "boom at import" in detail


class FakeGateway:
    def __init__(self, telemetry, answers):
        self.telemetry = telemetry
        self.answers = list(answers)
        self.models, self.calls = [], []

    def ensure_model(self, model):
        self.models.append(model)
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        return f"c{len(self.calls)}", self.answers.pop(0)


def make_plan(state, tasks):
    return plan.save_plan(state, "a feature", tasks)


def test_draft_tests(root, tmp_path, monkeypatch):
    state = tmp_path / "state"
    second = dict(TASK, key="cli", title="Use f", files=["stratos/__main__.py"],
                  tests=["tests/test_diagnose.py", "tests/test_cli_m.py", "tests/test_absent.py"], protected=[])
    pid = make_plan(state, [TASK, second])
    checked = []
    monkeypatch.setattr(plantests, "check_draft", lambda r, p: (checked.append(p), ("import_error", "x"))[1])
    a1 = "FILE: tests/test_m.py\n```python\ndef test_f():\n    assert False\n```\n"
    a2 = ("FILE: tests/test_diagnose.py\n```python\nX = 1\n```\nFILE: tests/test_cli_m.py\n```python\n"
          "def test_cli():\n    pass\n```\nFILE: stratos/evil.py\n```python\nY = 2\n```\n")
    gw = FakeGateway(Telemetry(tmp_path / "t.jsonl"), [a1, a2])
    lines = []
    expected_first = plantests.build_messages(TASK, root)      # before the drafts change the project summary
    out = plantests.draft_tests(gw, pid, root, state, log=lines.append)
    assert out == [{"key": "core", "file": "tests/test_m.py", "status": "import_error"},
                   {"key": "cli", "file": "tests/test_diagnose.py", "status": "exists"},
                   {"key": "cli", "file": "tests/test_cli_m.py", "status": "import_error"},
                   {"key": "cli", "file": "tests/test_absent.py", "status": "missing"}]
    assert gw.models == [config.PLANNER["model"]]
    msgs, kw = gw.calls[0]
    assert msgs == expected_first
    want = {"task": f"{pid}-core", "role": "test_writer", "attempt": 1, "model": config.PLANNER["model"],
            "effort": config.PLANNER["effort"], "max_tokens": config.PLANNER["max_tokens"]}
    if config.PLANNER.get("reasoning_budget") is not None:
        want["reasoning_budget"] = config.PLANNER["reasoning_budget"]
    assert kw == want and gw.calls[1][1]["task"] == f"{pid}-cli"
    assert (root / "tests" / "test_m.py").read_text(encoding="utf-8") == "def test_f():\n    assert False\n"
    assert (root / "tests" / "test_diagnose.py").read_text(encoding="utf-8").startswith('"""Style."""')
    assert not (root / "stratos" / "evil.py").exists()
    assert checked == ["tests/test_m.py", "tests/test_cli_m.py"]
    assert any("tests/test_diagnose.py" in line for line in lines)
    assert (state / "answers" / f"{pid}-core-tests.md").read_text(encoding="utf-8") == a1
    assert (state / "answers" / f"{pid}-cli-tests.md").read_text(encoding="utf-8") == a2
    events = [e for e in gw.telemetry.load() if e["kind"] == "test_draft"]
    assert [(e["plan"], e["key"], e["file"], e["status"]) for e in events] == [
        (pid, "core", "tests/test_m.py", "import_error"), (pid, "cli", "tests/test_diagnose.py", "exists"),
        (pid, "cli", "tests/test_cli_m.py", "import_error"), (pid, "cli", "tests/test_absent.py", "missing")]


def test_unknown_plan(root, tmp_path):
    gw = FakeGateway(Telemetry(tmp_path / "t.jsonl"), [])
    with pytest.raises(KeyError):
        plantests.draft_tests(gw, "P404", root, tmp_path / "state")
