"""Tests for task T058: the task loop runs the diagnosis A/B (stratos/diagnose.py, T057) on the coder's retries.

In write_task, after a failed attempt and its escalation decision (rules, and Jev when on), when config.DIAGNOSE_AB
is on, the attempt's role is "coder", the rules did not choose to move on, and the role has another try left:
- next = attempt + 1; used = diagnose.use_hint(task_id, next)
- used: diff = gitops.diff(wt), taken before the attempt's changes are discarded; hint = diagnose.diagnose(gw, task,
  diff, detail, next); the next attempt's failure text becomes diagnose.with_hint(failure, hint), and a log line says
  a diagnosis was added. If diagnose.diagnose raises, the retry goes on without it (used False, error=str(e)).
- telemetry: record("diagnosis", task=task_id, attempt=next, used=used, chars=len(hint) or 0, plus error=... when
  diagnose.diagnose raised).
Nothing of this happens when DIAGNOSE_AB is off, for coder_hard attempts, on the role's last try, or when the
rules escalate. Fakes stand in for the gateway, git and the test runner."""
import pytest

from stratos import config, diagnose, gitops, loop, verify
from stratos.state import Store
from stratos.telemetry import Telemetry

WRITER = "FILE: pkg/a.py\n```python\nX = 1\n```\n"


class FakeGateway:
    def __init__(self, telemetry, n):
        self.telemetry = telemetry
        self.answers = [WRITER] * n
        self.calls = []

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append({"messages": messages, **kw})
        return f"c{len(self.calls)}", self.answers.pop(0)


@pytest.fixture
def env(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REVIEW", False)
    monkeypatch.setattr(config, "DIAGNOSE_AB", True)
    order = []
    rec = {"outs": [], "order": order, "diag": []}

    def worktree(repo, root, tid, bases=None):
        p = tmp_path / "wt" / tid
        p.mkdir(parents=True, exist_ok=True)
        return p
    monkeypatch.setattr(gitops, "ensure_worktree", worktree)
    monkeypatch.setattr(gitops, "dependency_bases", lambda repo, ids: [])

    def diff(w):
        order.append("diff")
        return "THE DIFF"
    monkeypatch.setattr(gitops, "diff", diff)
    monkeypatch.setattr(gitops, "discard_changes", lambda w: order.append("discard"))
    monkeypatch.setattr(gitops, "commit_all", lambda w, message: "sha1")

    def run_tests(w, tests):
        return rec["outs"].pop(0)
    monkeypatch.setattr(verify, "run_tests", run_tests)

    def fake_diagnose(gw, task, diff, detail, attempt):
        rec["diag"].append((task["id"], diff, detail, attempt))
        if rec.get("raise"):
            raise RuntimeError("server down")
        return "HINT"
    monkeypatch.setattr(diagnose, "diagnose", fake_diagnose)
    store = Store(state)
    store.add_task("t", "make X", ["pkg/a.py"], [], ["tests/x.py"], role="coder")
    return store, Telemetry(state / "telemetry.jsonl"), rec, monkeypatch


def diag_events(tel):
    return [e for e in tel.load() if e["kind"] == "diagnosis"]


def run(env, outs, use):
    store, tel, rec, mp = env
    rec["outs"] = list(outs)
    mp.setattr(diagnose, "use_hint", lambda tid, attempt: use)
    gw = FakeGateway(tel, len(outs))
    result = loop.write_task(store, gw, "T001", log=lambda *a: None)
    return result, gw


def test_used_hint_goes_into_the_retry(env):
    store, tel, rec, _ = env
    result, gw = run(env, [(False, "FAILED tests/x.py::t1"), (True, "1 passed")], True)
    assert result == "done"
    assert rec["diag"] == [("T001", "THE DIFF", "FAILED tests/x.py::t1", 2)]
    assert rec["order"][:2] == ["diff", "discard"]
    retry = gw.calls[1]["messages"][1]["content"]
    assert diagnose.with_hint("FAILED tests/x.py::t1", "HINT") in retry
    (e,) = diag_events(tel)
    assert (e["task"], e["attempt"], e["used"], e["chars"]) == ("T001", 2, True, 4) and "error" not in e


def test_unused_half_retries_as_before(env):
    store, tel, rec, _ = env
    result, gw = run(env, [(False, "FAILED tests/x.py::t1"), (True, "1 passed")], False)
    assert result == "done" and rec["diag"] == []
    assert "DIAGNOSIS" not in gw.calls[1]["messages"][1]["content"]
    assert "FAILED tests/x.py::t1" in gw.calls[1]["messages"][1]["content"]
    (e,) = diag_events(tel)
    assert (e["task"], e["attempt"], e["used"], e["chars"]) == ("T001", 2, False, 0)


def test_a_failing_diagnoser_does_not_stop_the_retry(env):
    store, tel, rec, _ = env
    rec["raise"] = True
    result, gw = run(env, [(False, "FAILED tests/x.py::t1"), (True, "1 passed")], True)
    assert result == "done" and len(gw.calls) == 2
    assert "DIAGNOSIS" not in gw.calls[1]["messages"][1]["content"]
    (e,) = diag_events(tel)
    assert e["used"] is False and e["chars"] == 0 and "server down" in e["error"]


def test_no_diagnosis_on_the_last_coder_try_or_for_coder_hard(env):
    store, tel, rec, _ = env
    # three different coder failures (no escalation), then the coder_hard cross-check fails too
    outs = [(False, f"FAILED tests/x.py::t{i}") for i in range(1, 5)]
    result, gw = run(env, outs, True)
    assert result == "needs_human"
    assert [c["role"] for c in gw.calls] == ["coder", "coder", "coder", "coder_hard"]
    assert [d[3] for d in rec["diag"]] == [2, 3]
    assert [e["attempt"] for e in diag_events(tel)] == [2, 3]


def test_no_diagnosis_when_the_rules_escalate(env):
    store, tel, rec, _ = env
    same = (False, "FAILED tests/x.py::t1")
    result, gw = run(env, [same, same, (True, "1 passed")], True)
    assert [c["role"] for c in gw.calls] == ["coder", "coder", "coder_hard"]
    assert [e["attempt"] for e in diag_events(tel)] == [2]


def test_off_switch(env, monkeypatch):
    store, tel, rec, _ = env
    monkeypatch.setattr(config, "DIAGNOSE_AB", False)
    result, gw = run(env, [(False, "FAILED tests/x.py::t1"), (True, "1 passed")], True)
    assert result == "done" and rec["diag"] == [] and diag_events(tel) == []
