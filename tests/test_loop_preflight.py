r"""Tests for task loop_preflight (P1, 2026-11-20, after the preflight task): write_task runs preflight.check before any
model call and shows the base's failing output in the first prompt; check_answer stops at a syntax error.

1. config.PREFLIGHT (True by default; tests/conftest.py turns it off). When on, write_task calls
   preflight.check(task, wt) right after the worktree is ready (status "running"), before ensure_model and chat.
   - verdict "refuse": store.update(task_id, status="needs_human", preflight=reason); store.decide(task=task_id,
     result="preflight_refused", reason=reason); gw.telemetry.record("preflight", task=task_id, verdict="refuse",
     reason=reason); log f"  preflight: {reason}"; return "needs_human". No model is loaded or asked.
   - verdict "run": gw.telemetry.record("preflight", task=task_id, verdict="run", reason=reason); when its output is
     not empty, every context.build_messages call of this write_task gets before=output[-3000:] (passed as a
     keyword only then: old fakes of build_messages take no `before`).
2. context.build_messages(task, root, failure=None, memory=None, before=None): with `before` and no `failure`, the
   user message ends with "BEFORE YOUR CHANGE THE TESTS FAIL LIKE THIS (make them pass):\n```\n" + before + "\n```".
   With a failure, the failure part is shown as before and `before` is not.
3. check_answer: after patch.apply_files, verify.syntax_errors(wt, written) (written = apply_files's list); when it
   is not empty the result is "syntax_error" with detail "Your files do not compile:\n" + the errors joined by "\n"
   + a hint to check the syntax (worded for edit blocks since task lint_new_and_hints), and the tests are not run. A "length" finish still
   prefixes the cut-off note as for other failures. A syntax_error is a failed attempt like any other (retried)."""
import pytest

from stratos import config, context, gitops, loop, preflight, verify
from stratos.state import Store
from stratos.telemetry import Telemetry

GOOD = "FILE: pkg/a.py\n```python\nX = 1\n```\n"
BROKEN = "FILE: pkg/a.py\n```python\ndef f(:\n    return 1\n```\n"


class FakeGateway:
    def __init__(self, telemetry, answers):
        self.telemetry = telemetry
        self.answers = list(answers)
        self.calls = []
        self.loads = []

    def ensure_model(self, model):
        self.loads.append(model)
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append(messages)
        return f"c{len(self.calls)}", self.answers.pop(0)


@pytest.fixture
def env(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REVIEW", False)
    monkeypatch.setattr(config, "PREFLIGHT", True)
    rec = {"outs": [], "pre": None, "pre_calls": []}

    def worktree(repo, root, tid, bases=None):
        p = tmp_path / "wt" / tid
        p.mkdir(parents=True, exist_ok=True)
        return p
    monkeypatch.setattr(gitops, "ensure_worktree", worktree)
    monkeypatch.setattr(gitops, "dependency_bases", lambda repo, ids: [])
    monkeypatch.setattr(gitops, "diff", lambda w: "")
    monkeypatch.setattr(gitops, "discard_changes", lambda w: None)
    monkeypatch.setattr(gitops, "commit_all", lambda w, message: "sha1")
    monkeypatch.setattr(verify, "run_tests", lambda w, tests: rec["outs"].pop(0))

    def fake_check(task, wt):
        rec["pre_calls"].append((task["id"], wt.name))
        return dict(rec["pre"])
    monkeypatch.setattr(preflight, "check", fake_check)
    store = Store(state)
    store.add_task("t", "make X", ["pkg/a.py"], [], ["tests/x.py"], role="coder")
    return store, Telemetry(state / "telemetry.jsonl"), rec


def run(env, answers):
    store, tel, rec = env
    gw = FakeGateway(tel, answers)
    lines = []
    result = loop.write_task(store, gw, "T001", log=lines.append)
    return result, gw, lines


def test_refused_before_any_model_call(env):
    store, tel, rec = env
    rec["pre"] = {"verdict": "refuse", "reason": "test file missing: tests/x.py", "output": ""}
    result, gw, lines = run(env, [])
    assert result == "needs_human"
    assert gw.calls == [] and gw.loads == []
    assert rec["pre_calls"] == [("T001", "T001")]
    t = store.get("T001")
    assert t["status"] == "needs_human" and t["preflight"] == "test file missing: tests/x.py"
    assert "  preflight: test file missing: tests/x.py" in lines
    events = [e for e in tel.load() if e["kind"] == "preflight"]
    assert len(events) == 1
    assert events[0]["task"] == "T001" and events[0]["verdict"] == "refuse"
    assert events[0]["reason"] == "test file missing: tests/x.py"
    decisions = (config.STATE_DIR / "decisions.jsonl").read_text(encoding="utf-8")
    assert "preflight_refused" in decisions


def test_base_failure_in_first_prompt_only(env):
    store, tel, rec = env
    rec["pre"] = {"verdict": "run", "reason": "tests fail before the change", "output": "x" * 5000 + "NameError: f"}
    rec["outs"] = [(False, "FAILED tests/x.py::t1 - assert 2 == 3"), (True, "ok")]
    result, gw, lines = run(env, [GOOD, GOOD])
    assert result == "done"
    first = gw.calls[0][-1]["content"]
    assert "BEFORE YOUR CHANGE THE TESTS FAIL LIKE THIS (make them pass):" in first
    assert "NameError: f" in first and "x" * 3001 not in first
    second = gw.calls[1][-1]["content"]
    assert "BEFORE YOUR CHANGE" not in second and "assert 2 == 3" in second
    events = [e for e in tel.load() if e["kind"] == "preflight"]
    assert [e["verdict"] for e in events] == ["run"]


def test_no_before_when_tests_already_pass(env):
    store, tel, rec = env
    rec["pre"] = {"verdict": "run", "reason": "tests already pass on the base", "output": ""}
    rec["outs"] = [(True, "ok")]
    result, gw, lines = run(env, [GOOD])
    assert result == "done"
    assert "BEFORE YOUR CHANGE" not in gw.calls[0][-1]["content"]


def test_off(env, monkeypatch):
    store, tel, rec = env
    monkeypatch.setattr(config, "PREFLIGHT", False)
    rec["outs"] = [(True, "ok")]
    result, gw, lines = run(env, [GOOD])
    assert result == "done" and rec["pre_calls"] == []


def test_build_messages_before():
    t = {"id": "T001", "title": "t", "goal": "g", "files": [], "protected": []}
    text = context.build_messages(t, ".", before="E boom")[-1]["content"]
    assert text.endswith("BEFORE YOUR CHANGE THE TESTS FAIL LIKE THIS (make them pass):\n```\nE boom\n```")
    text = context.build_messages(t, ".", failure="F bad", before="E boom")[-1]["content"]
    assert "E boom" not in text and "F bad" in text


def test_syntax_error_skips_the_tests(env, tmp_path):
    store, tel, rec = env
    wt = tmp_path / "wt" / "T001"
    wt.mkdir(parents=True, exist_ok=True)
    t = store.get("T001")
    result, detail = loop.check_answer(t, wt, BROKEN)
    assert result == "syntax_error"
    assert detail.startswith("Your files do not compile:\npkg/a.py: line 1: ")
    # (task lint_new_and_hints changed the hint; Claude updated this test)
    assert detail.endswith("\nCheck the syntax of every file you write; for an existing file, change only the lines "
                           "you need with SEARCH/REPLACE edit blocks.")
    result, detail = loop.check_answer(t, wt, BROKEN, finish="length")
    assert result == "syntax_error" and detail.startswith("Your answer was cut off")


def test_syntax_error_is_retried(env):
    store, tel, rec = env
    rec["pre"] = {"verdict": "run", "reason": "tests already pass on the base", "output": ""}
    rec["outs"] = [(True, "ok")]
    result, gw, lines = run(env, [BROKEN, GOOD])
    assert result == "done"
    assert "Your files do not compile" in gw.calls[1][-1]["content"]
    assert any("syntax_error" in line for line in lines)
