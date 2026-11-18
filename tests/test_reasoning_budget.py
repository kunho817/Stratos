"""Tests for task T056: a reasoning budget (T054's Gateway.chat(..., reasoning_budget=N)) reaches the model from the
task loop, from replay.replay and from `stratos replay`.

- loop: a role in config.ROLES may hold "reasoning_budget": N. write_task then calls gw.chat(..., reasoning_budget=N);
  for a role without the key (or with None) it calls gw.chat exactly as before, without a reasoning_budget argument.
- replay.replay(tasks, gw, *, model, effort, max_tokens, tries, repo, root, log=print, reasoning_budget=None) passes
  reasoning_budget=N to gw.chat when it is not None, and no reasoning_budget argument when it is None.
- `stratos replay ... --reasoning-budget N` (int) defaults to the role's "reasoning_budget" (None when the role has
  none). When the value is not None, replay.replay gets reasoning_budget=N; when it is None, replay.replay is called
  without that argument, as before."""
import subprocess

import pytest

from stratos import __main__ as cli
from stratos import config, context, gitops, loop, replay, verify
from stratos.state import Store
from stratos.telemetry import Telemetry

WRITER = "FILE: pkg/a.py\n```python\nX = 1\n```\n"


class FakeGateway:
    def __init__(self, telemetry, answers):
        self.telemetry = telemetry
        self.answers = list(answers)
        self.calls = []
        self.last_finish = "stop"

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append(kw)
        return f"c{len(self.calls)}", self.answers.pop(0)


# ---------------------------------------------------------------- loop

@pytest.fixture
def loop_env(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REVIEW", False)

    def worktree(repo, root, tid, bases=None):
        p = tmp_path / "wt" / tid
        p.mkdir(parents=True, exist_ok=True)
        return p
    monkeypatch.setattr(gitops, "ensure_worktree", worktree)
    monkeypatch.setattr(gitops, "dependency_bases", lambda repo, ids: [])
    monkeypatch.setattr(gitops, "diff", lambda w: "diff --git a/pkg/a.py b/pkg/a.py\n+X = 1\n")
    monkeypatch.setattr(gitops, "discard_changes", lambda w: None)
    monkeypatch.setattr(gitops, "commit_all", lambda w, message: "sha1")
    monkeypatch.setattr(verify, "run_tests", lambda w, tests: (True, "1 passed"))
    store = Store(state)
    store.add_task("t", "make X", ["pkg/a.py"], [], ["tests/x.py"], role="coder")
    return store, Telemetry(state / "telemetry.jsonl")


def roles_with(budget):
    roles = {name: dict(r) for name, r in config.ROLES.items()}
    roles["coder"].pop("reasoning_budget", None)
    if budget is not None:
        roles["coder"]["reasoning_budget"] = budget
    return roles


def test_loop_passes_the_role_budget(loop_env, monkeypatch):
    store, tel = loop_env
    monkeypatch.setattr(config, "ROLES", roles_with(500))
    gw = FakeGateway(tel, [WRITER])
    loop.write_task(store, gw, "T001", log=lambda *a: None)
    assert gw.calls[0]["reasoning_budget"] == 500
    assert gw.calls[0]["model"] == config.ROLES["coder"]["model"]


def test_loop_without_a_budget_calls_as_before(loop_env, monkeypatch):
    store, tel = loop_env
    monkeypatch.setattr(config, "ROLES", roles_with(None))
    gw = FakeGateway(tel, [WRITER])
    loop.write_task(store, gw, "T001", log=lambda *a: None)
    assert "reasoning_budget" not in gw.calls[0]


def test_loop_with_none_in_the_role_calls_as_before(loop_env, monkeypatch):
    store, tel = loop_env
    roles = roles_with(None)
    roles["coder"]["reasoning_budget"] = None
    monkeypatch.setattr(config, "ROLES", roles)
    gw = FakeGateway(tel, [WRITER])
    loop.write_task(store, gw, "T001", log=lambda *a: None)
    assert "reasoning_budget" not in gw.calls[0]


# ---------------------------------------------------------------- replay.replay

@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    (r / "a.py").write_text("A = 1\n", encoding="utf-8")
    gitops.git(r, "add", "-A")
    gitops.git(r, *gitops.BOT, "commit", "-q", "-m", "init")
    (r / "a.py").write_text("A = 2\n", encoding="utf-8")
    gitops.git(r, "add", "-A")
    gitops.git(r, *gitops.BOT, "commit", "-q", "-m", "T901: change a")
    return r


TASK = {"id": "T901", "title": "a", "files": ["a.py"], "protected": [], "tests": ["test_a.py"], "goal": "Change A."}


@pytest.fixture
def quiet_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(context, "build_messages", lambda task, wt, failure=None: [{"role": "user", "content": "x"}])
    monkeypatch.setattr(loop, "check_answer", lambda task, wt, text, finish=None: ("passed", "ok"))


def test_replay_passes_a_budget(repo, tmp_path, quiet_replay):
    gw = FakeGateway(Telemetry(tmp_path / "t.jsonl"), ["answer"])
    out = replay.replay([TASK], gw, model="m1", effort="low", max_tokens=99, tries=1, repo=repo,
                        root=tmp_path / "wt", log=lambda *a: None, reasoning_budget=300)
    assert out[0]["result"] == "passed"
    assert gw.calls[0]["reasoning_budget"] == 300 and gw.calls[0]["max_tokens"] == 99


def test_replay_without_a_budget_calls_as_before(repo, tmp_path, quiet_replay):
    gw = FakeGateway(Telemetry(tmp_path / "t.jsonl"), ["answer"])
    replay.replay([TASK], gw, model="m1", effort="low", max_tokens=99, tries=1, repo=repo, root=tmp_path / "wt",
                  log=lambda *a: None)
    assert "reasoning_budget" not in gw.calls[0]


# ---------------------------------------------------------------- stratos replay

@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(config, "WORKTREES", tmp_path / "wt")
    store = Store(tmp_path / "state")
    a = store.add_task("a", "goal a", ["x.py"], [], ["tests"])

    class Gw:
        def __init__(self, telemetry):
            self.telemetry = telemetry
    monkeypatch.setattr(cli, "Gateway", Gw)
    calls = []

    def fake_replay(tasks, gw, **kw):
        calls.append(kw)
        return [{"task": t["id"], "result": "passed", "attempts": 1, "seconds": 1.0} for t in tasks]
    monkeypatch.setattr(replay, "replay", fake_replay)
    return a["id"], calls


def test_cli_budget_flag(cli_env, capsys):
    tid, calls = cli_env
    assert cli.main(["replay", tid, "--reasoning-budget", "300"]) == 0
    assert calls[0]["reasoning_budget"] == 300
    assert f"{tid}: passed" in capsys.readouterr().out


def test_cli_budget_defaults_to_the_role(cli_env, monkeypatch):
    tid, calls = cli_env
    monkeypatch.setattr(config, "ROLES", roles_with(800))
    assert cli.main(["replay", tid]) == 0
    assert calls[0]["reasoning_budget"] == 800


def test_cli_without_any_budget_calls_as_before(cli_env, monkeypatch):
    tid, calls = cli_env
    monkeypatch.setattr(config, "ROLES", roles_with(None))
    assert cli.main(["replay", tid]) == 0
    assert "reasoning_budget" not in calls[0]
