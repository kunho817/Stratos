"""Tests for task T053: replay.replay keeps every raw answer, so a failed replay can be explained (Flint failed T009
twice with an IndentationError and nothing showed whether the model or the FILE parser was at fault).

Each answer is written, UTF-8, to config.STATE_DIR / "replay_answers" / f"{task id}-{call id}.md" (the call id joins it
to the call and outcome events of replay.jsonl), right after the chat call and before it is judged. An empty answer
gives an empty file. Real tasks' answers in .stratos/answers are never touched."""
import subprocess

import pytest

from stratos import config, context, gitops, loop, replay
from stratos.telemetry import Telemetry
from test_replay import FakeGateway, TASK, commit


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    (r / "a.py").write_text("A = 1\n", encoding="utf-8")
    commit(r, "init")
    (r / "a.py").write_text("A = 2\n", encoding="utf-8")
    commit(r, "T901: change a")
    return r


def test_answers_are_kept(repo, tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(context, "build_messages", lambda task, wt, failure=None: [])
    seen = []

    def check(task, wt, text, finish=None):
        seen.append(sorted(p.name for p in (state / "replay_answers").iterdir()))
        return ("failed", "x") if text.startswith("first") else ("passed", "ok")
    monkeypatch.setattr(loop, "check_answer", check)
    gw = FakeGateway(Telemetry(tmp_path / "t.jsonl"), ["first answer ünïcode", ""])
    replay.replay([TASK], gw, model="m", effort="none", max_tokens=1, tries=2, repo=repo, root=tmp_path / "wt",
                  log=lambda s: None)
    d = state / "replay_answers"
    assert (d / "T901-c1.md").read_text(encoding="utf-8") == "first answer ünïcode"
    assert (d / "T901-c2.md").read_text(encoding="utf-8") == ""
    assert seen == [["T901-c1.md"], ["T901-c1.md", "T901-c2.md"]]
    assert not (state / "answers").exists()
