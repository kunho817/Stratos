"""Tests for task T050: `python -m stratos replay <task id> ... [--role R] [--model M] [--effort E] [--max-tokens N]
[--tries K]` tries a model on past tasks with replay.replay (T049) and prints how it did.

--role (default "coder") picks one of config.ROLES; --model, --effort and --max-tokens default to that role's model,
effort and max_tokens. --tries defaults to 2. The task ids must all be known to the Store; an unknown id prints
"no such task: <id>" on stderr and returns 1 without replaying anything. The gateway is Gateway(Telemetry(
config.STATE_DIR / "replay.jsonl")), apart from telemetry.jsonl so the report of real work is not changed. The call is
replay.replay(tasks, gw, model=..., effort=..., max_tokens=..., tries=..., repo=config.REPO, root=config.WORKTREES)
with the Store's task dicts in the order given. For each result it prints
"<task>: <result> (<attempts> attempts, <seconds rounded> s)", then "replay <model>: <passed>/<n> passed, <total
seconds rounded> s", and returns 0."""
import pytest

from stratos import __main__ as cli
from stratos import config, replay
from stratos.state import Store


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(config, "WORKTREES", tmp_path / "wt")
    store = Store(tmp_path / "state")
    a = store.add_task("a", "goal a", ["x.py"], [], ["tests"])
    b = store.add_task("b", "goal b", ["y.py"], [], ["tests"])
    made = []

    class FakeGateway:
        def __init__(self, telemetry):
            self.telemetry = telemetry
            made.append(self)
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    calls = []

    def fake_replay(tasks, gw, **kw):
        calls.append((tasks, gw, kw))
        return [{"task": tasks[0]["id"], "result": "passed", "attempts": 1, "seconds": 10.4},
                {"task": tasks[1]["id"], "result": "failed", "attempts": 2, "seconds": 20.2}][:len(tasks)]
    monkeypatch.setattr(replay, "replay", fake_replay)
    return a["id"], b["id"], made, calls, tmp_path


def test_replay_with_role_defaults(proj, capsys):
    a, b, made, calls, tmp = proj
    assert cli.main(["replay", b, a]) == 0
    tasks, gw, kw = calls[0]
    assert [t["id"] for t in tasks] == [b, a] and tasks[0]["goal"] == "goal b"
    r = config.ROLES["coder"]
    assert kw == {"model": r["model"], "effort": r["effort"], "max_tokens": r["max_tokens"], "tries": 2,
                  "repo": config.REPO, "root": config.WORKTREES}
    assert gw is made[0] and str(gw.telemetry.path).endswith("replay.jsonl")
    out = capsys.readouterr().out
    assert f"{b}: passed (1 attempts, 10 s)" in out and f"{a}: failed (2 attempts, 20 s)" in out
    assert f"replay {r['model']}: 1/2 passed, 31 s" in out


def test_replay_overrides(proj, capsys):
    a, b, made, calls, tmp = proj
    assert cli.main(["replay", a, "--role", "reviewer", "--model", "new-model", "--effort", "low",
                     "--max-tokens", "123", "--tries", "3"]) == 0
    kw = calls[0][2]
    assert (kw["model"], kw["effort"], kw["max_tokens"], kw["tries"]) == ("new-model", "low", 123, 3)
    assert cli.main(["replay", a, "--role", "coder_hard"]) == 0
    assert calls[1][2]["model"] == config.ROLES["coder_hard"]["model"]


def test_unknown_task(proj, capsys):
    a, b, made, calls, tmp = proj
    assert cli.main(["replay", a, "T999"]) == 1
    assert "no such task: T999" in capsys.readouterr().err and calls == []
