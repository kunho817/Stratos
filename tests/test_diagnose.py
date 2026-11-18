"""Tests for task T057: stratos/diagnose.py, a short diagnosis of a failed attempt by a local model (AgentWorld,
config.DIAGNOSER), used in an A/B: half of the coder's retries get it (T058).

use_hint(task_id, attempt) -> bool
    Which half: int(hashlib.sha256(f"{task_id}:{attempt}".encode("utf-8")).hexdigest(), 16) % 2 == 0.
    The same arguments always give the same answer.
SYSTEM
    The system prompt (a str): it asks for what went wrong and what the next attempt must do differently, in at most
    120 words, without code blocks.
build_messages(task, diff, detail) -> [{"role": "system", "content": SYSTEM}, {"role": "user", "content": ...}]
    The user content is f"GOAL:\n{task['goal']}\n\nDIFF:\n{d}\n\nTEST OUTPUT:\n{detail[-3000:]}" where d is
    diff[-4000:], or "(no change was written)" when diff is empty or only whitespace.
with_hint(failure, hint) -> failure + "\n\nA REVIEWER READ YOUR DIFF AND THIS OUTPUT. DIAGNOSIS:\n" + hint
diagnose(gw, task, diff, detail, attempt) -> str
    gw.ensure_model(config.DIAGNOSER["model"]), then gw.chat(build_messages(task, diff, detail), task=task["id"],
    role="diagnoser", attempt=attempt, model=config.DIAGNOSER["model"], effort=config.DIAGNOSER["effort"],
    max_tokens=config.DIAGNOSER["max_tokens"]); returns the answer text stripped of surrounding whitespace."""
import hashlib

from stratos import config, diagnose

TASK = {"id": "T900", "goal": "Make X equal 2."}


def test_use_hint_is_the_hash_parity():
    for tid, attempt in [("T001", 1), ("T001", 2), ("T057", 3), ("T123", 9), ("X", 0)]:
        want = int(hashlib.sha256(f"{tid}:{attempt}".encode("utf-8")).hexdigest(), 16) % 2 == 0
        assert diagnose.use_hint(tid, attempt) is want
        assert diagnose.use_hint(tid, attempt) is want


def test_use_hint_splits_roughly_in_half():
    picks = [diagnose.use_hint(f"T{i:03d}", a) for i in range(100) for a in (1, 2)]
    assert 70 < sum(picks) < 130


def test_build_messages():
    msgs = diagnose.build_messages(TASK, "diff --git a/x\n+X = 3\n", "E   assert 3 == 2")
    assert [m["role"] for m in msgs] == ["system", "user"] and msgs[0]["content"] == diagnose.SYSTEM
    assert "120 words" in diagnose.SYSTEM
    assert msgs[1]["content"] == "GOAL:\nMake X equal 2.\n\nDIFF:\ndiff --git a/x\n+X = 3\n\n\nTEST OUTPUT:\nE   assert 3 == 2"


def test_build_messages_without_a_diff_and_long_text():
    msgs = diagnose.build_messages(TASK, "  \n", "y" * 5000)
    user = msgs[1]["content"]
    assert "DIFF:\n(no change was written)\n\nTEST OUTPUT:\n" in user
    assert user.endswith("y" * 3000) and "y" * 3001 not in user
    long = diagnose.build_messages(TASK, "a" * 3000 + "b" * 4000, "out")[1]["content"]
    assert "b" * 4000 in long and "a" not in long.split("DIFF:\n", 1)[1].split("\n\nTEST OUTPUT:")[0]


def test_with_hint():
    assert diagnose.with_hint("FAILED t", "use Y") == "FAILED t\n\nA REVIEWER READ YOUR DIFF AND THIS OUTPUT. DIAGNOSIS:\nuse Y"


class FakeGateway:
    def __init__(self):
        self.models, self.calls = [], []

    def ensure_model(self, model):
        self.models.append(model)
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        return "c1", "\n  The test wants 2.  \n"


def test_diagnose_calls_the_diagnoser():
    gw = FakeGateway()
    out = diagnose.diagnose(gw, TASK, "+X = 3", "E   assert 3 == 2", 4)
    assert out == "The test wants 2."
    d = config.DIAGNOSER
    assert gw.models == [d["model"]]
    messages, kw = gw.calls[0]
    assert messages == diagnose.build_messages(TASK, "+X = 3", "E   assert 3 == 2")
    assert kw == {"task": "T900", "role": "diagnoser", "attempt": 4, "model": d["model"], "effort": d["effort"],
                  "max_tokens": d["max_tokens"]}
