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
import inspect
import json
import subprocess

import pytest

from stratos import config, context, lint, plan, plantests
from stratos.plantests import check_draft
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
    expected_first = plantests.build_messages(TASK, root, feature="a feature")      # before the drafts change the project summary
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


# ---- was test_plantests_check_draft.py ----
# Tests for check_draft in stratos/plantests.py.
#
# check_draft(root, path) runs pytest --collect-only on the given file.
# It calls subprocess.run with encoding='utf-8', errors='replace', and timeout=120.
# If the subprocess times out, check_draft returns ('error', 'draft check timed out').
# Normal pass/fail logic (syntax_error, collected, import_error, error) stays unchanged.


def test_check_draft_passes_encoding_errors_timeout(tmp_path, monkeypatch):
    """subprocess.run must be called with encoding='utf-8', errors='replace', timeout=120."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def test_a(): pass\n", encoding="utf-8")

    captured_kwargs = {}

    def fake_run(cmd, **kwargs):
        captured_kwargs.update(kwargs)

        class FakeResult:
            returncode = 0
            stdout = "1 test collected\n"
            stderr = ""

        return FakeResult()

    monkeypatch.setattr("stratos.plantests.subprocess.run", fake_run)
    result = check_draft(str(tmp_path), "tests/test_x.py")

    assert result == ("collected", "")
    assert captured_kwargs["encoding"] == "utf-8"
    assert captured_kwargs["errors"] == "replace"
    assert captured_kwargs["timeout"] == 120
    assert captured_kwargs["cwd"] == str(tmp_path)
    assert captured_kwargs["capture_output"] is True


def test_check_draft_timeout(tmp_path, monkeypatch):
    """When the subprocess times out, check_draft returns ('error', 'draft check timed out')."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def test_a(): pass\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 120)

    monkeypatch.setattr("stratos.plantests.subprocess.run", fake_run)
    result = check_draft(str(tmp_path), "tests/test_x.py")

    assert result == ("error", "draft check timed out")


def test_check_draft_syntax_error(tmp_path):
    """A file that cannot be parsed returns ('syntax_error', msg)."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def broken(:\n", encoding="utf-8")

    result = check_draft(str(tmp_path), "tests/test_x.py")
    assert result[0] == "syntax_error"


def test_check_draft_collects_ok(tmp_path, monkeypatch):
    """A valid test file that collects successfully returns ('collected', '')."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def test_a(): pass\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        class FakeResult:
            returncode = 0
            stdout = "1 test collected\n"
            stderr = ""

        return FakeResult()

    monkeypatch.setattr("stratos.plantests.subprocess.run", fake_run)
    result = check_draft(str(tmp_path), "tests/test_x.py")
    assert result == ("collected", "")


def test_check_draft_import_error(tmp_path, monkeypatch):
    """A file that fails to import returns ('import_error', tail)."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("import nonexistent_mod_xyz\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        class FakeResult:
            returncode = 2
            stdout = "ModuleNotFoundError: No module named 'nonexistent_mod_xyz'\n"
            stderr = ""

        return FakeResult()

    monkeypatch.setattr("stratos.plantests.subprocess.run", fake_run)
    result = check_draft(str(tmp_path), "tests/test_x.py")
    assert result[0] == "import_error"
    assert "nonexistent_mod_xyz" in result[1]


def test_check_draft_pytest_error(tmp_path, monkeypatch):
    """A file that collects with a generic failure returns ('error', tail)."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def test_a(): pass\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        class FakeResult:
            returncode = 1
            stdout = ""
            stderr = "FAILED tests/test_x.py\n"

        return FakeResult()

    monkeypatch.setattr("stratos.plantests.subprocess.run", fake_run)
    result = check_draft(str(tmp_path), "tests/test_x.py")
    assert result[0] == "error"


def test_check_draft_timeout_preserves_cmd(tmp_path, monkeypatch):
    """The timeout result is the same whatever timeout value the error carries."""
    p = tmp_path / "tests" / "test_x.py"
    p.parent.mkdir()
    p.write_text("def test_a(): pass\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))

    monkeypatch.setattr("stratos.plantests.subprocess.run", fake_run)
    result = check_draft(str(tmp_path), "tests/test_x.py")

    assert result == ("error", "draft check timed out")


# ---- was test_plantests_lint.py ----
# Tests for task drafts_lint (P11, 2026-11-20, trial 11): a draft held a half-written first copy of a test (same name
# as the real one, `pass` inside) and no check saw it; drafts also used names they never imported. And old test files
# of a task were printed as "missing".
#
# lint.check(root, paths, codes=lint.ERRORS): the ruff codes to select are a parameter now (default as before).
# plantests.draft_problems(root, path) -> list of lint lines for a written Python draft: lint.check(root, [path],
# codes=("F811", "F821", "F822", "F823")) - a redefined name (a test defined twice) or an undefined name.
# plantests.draft_tests: after a .py draft is collected, its problems are logged one per line as f"{path}: lint:
# {line}" and saved in its result entry as entry["lint"] (only when there are some; the status stays "collected").
# A test path of a task that the answer did not write but that already exists under root gets the status "old"
# (not "missing"); "missing" stays for paths that are neither written nor there.


@pytest.fixture
def drafts(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_d.py").write_text(
        "def test_a():\n    pass\n\n\ndef test_a():\n    assert helper() == 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_ok.py").write_text("def test_b():\n    assert 1\n", encoding="utf-8")
    return tmp_path


def test_lint_codes_parameter(drafts):
    if not lint.available():
        pytest.skip("ruff is not installed")
    lines = lint.check(drafts, ["tests/test_d.py"], codes=("F811",))
    assert len(lines) == 1 and "F811" in lines[0]
    assert all("F811" not in x for x in lint.check(drafts, ["tests/test_d.py"]))


def test_draft_tests_logs_lint_and_marks_old_files(tmp_path, monkeypatch):
    from stratos import codemap, config
    from test_plantests_outdated import FakeGateway
    if not lint.available():
        pytest.skip("ruff is not installed")
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    monkeypatch.setattr(plantests, "check_draft", lambda root, path: ("collected", ""))
    monkeypatch.setattr(plantests, "suite_leaks", lambda root, path, ignore=(): [])
    monkeypatch.setattr(codemap, "build", lambda r: {"test_dir": "tests", "files": {}, "imports": {}})
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_old.py").write_text("def test_o():\n    pass\n", encoding="utf-8")
    (state / "plans").mkdir(parents=True)
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_new.py", "tests/test_old.py", "tests/test_gone.py"],
            "protected": [], "after": [], "role": None}
    (state / "plans" / "P001.json").write_text(json.dumps({"id": "P001", "goal": "G", "tasks": [task],
                                                           "status": "draft", "hash": "h"}), encoding="utf-8")
    answer = "FILE: tests/test_new.py\n```python\ndef test_a():\n    pass\n\n\ndef test_a():\n    assert 1\n```\n"
    lines = []
    results = plantests.draft_tests(FakeGateway(answer), "P001", root, state, log=lines.append)
    by = {r["file"]: r for r in results}
    assert by["tests/test_new.py"]["status"] == "collected"
    assert any("F811" in x for x in by["tests/test_new.py"]["lint"])
    assert any(x.startswith("tests/test_new.py: lint: ") and "F811" in x for x in lines)
    assert by["tests/test_old.py"]["status"] == "old" and "lint" not in by["tests/test_old.py"]
    assert by["tests/test_gone.py"]["status"] == "missing"


def test_draft_problems(drafts):
    if not lint.available():
        pytest.skip("ruff is not installed")
    lines = plantests.draft_problems(drafts, "tests/test_d.py")
    assert any("F811" in x and "test_a" in x for x in lines)
    assert any("F821" in x and "helper" in x for x in lines)
    assert plantests.draft_problems(drafts, "tests/test_ok.py") == []


# ---- was test_plantests_one_call.py ----
# Tests for task plantests_one_call (P11 cleanup, 2026-11-20, found by Claude reading T208): T208 copied the whole
# test-writer call (messages, kwargs, gw.chat, the answer file, the header-less fallbacks - 25 lines) into the cases
# branch, so draft_tests asked the model in two places.
#
# plantests._ask_test_writer(gw, plan_id, task, messages, model_cfg, answers_dir, root) -> files: the model call and
# the reading of its answer as they were (kwargs with reasoning_budget when set, the answer saved as
# f"{plan_id}-{task['key']}-tests.md", patch.parse_files with allowed=task["tests"], the header-less fallbacks for a
# single new test file). draft_tests calls it (once, or once per branch) - for tasks without cases and for tasks whose cases are
# not all plain calls (with the CASES part added to the messages first). Behaviour is unchanged.


def test_one_model_call():
    assert inspect.getsource(plantests.draft_tests).count("gw.chat(") == 0
    # (Claude: at most 2 - one per branch is fine; the 25 copied lines were the problem, not two short calls)
    assert 1 <= inspect.getsource(plantests.draft_tests).count("_ask_test_writer(") <= 2
    assert inspect.getsource(plantests._ask_test_writer).count("gw.chat(") == 1


# ---- was test_plantests_project.py ----
# Tests for task plantests_project_settings: stratos/plantests.py reads config.PROJECT for
# example_test, draft_check_command, language, and test_runner. For Stratos's defaults the
# prompt still says pytest, but the values come from config.PROJECT, not hard-coded strings.
#
# plantests.system_prompt(language, test_runner) builds the test writer's system prompt;
# TEST_SYSTEM = system_prompt(config.PROJECT["language"], config.PROJECT["test_runner"]).


def test_config_project_has_required_keys():
    """config.PROJECT must define language, test_runner, example_test, draft_check_command."""
    for key in ("language", "test_runner", "example_test", "draft_check_command"):
        assert key in config.PROJECT, f"config.PROJECT missing key {key}"


def test_stratos_defaults_in_project_config():
    """For Stratos, config.PROJECT names Python and pytest, and points at the existing example."""
    assert config.PROJECT["test_runner"] == "pytest"
    assert config.PROJECT["language"] == "python"
    assert config.PROJECT["example_test"] == "tests/test_diagnose.py"
    assert isinstance(config.PROJECT["draft_check_command"], list)
    assert "--collect-only" in config.PROJECT["draft_check_command"]


def test_test_system_names_language_and_runner():
    """TEST_SYSTEM must include config.PROJECT['language'] and config.PROJECT['test_runner']."""
    assert config.PROJECT["language"].lower() in plantests.TEST_SYSTEM.lower()
    assert config.PROJECT["test_runner"] in plantests.TEST_SYSTEM


def test_test_system_says_pytest_for_stratos_defaults():
    """With Stratos defaults, TEST_SYSTEM mentions pytest."""
    assert "pytest" in plantests.TEST_SYSTEM


def test_test_system_for_non_python_project():
    """For a Rust project the prompt names Rust and cargo test, not pytest."""
    text = plantests.system_prompt("Rust", "cargo test")
    assert "Rust" in text and "cargo test" in text and "pytest" not in text
    assert plantests.TEST_SYSTEM == plantests.system_prompt(config.PROJECT["language"], config.PROJECT["test_runner"]) + plantests.APPENDED
