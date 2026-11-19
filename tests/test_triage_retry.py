"""Tests for task triage_retry: triage asks once more when its answer has no usable verdict or no reason.

T016 of the tower defense trial (2026-11-19) got "unclear" with an empty reason; the answer was not kept, so nobody
could tell whether the model said nothing or the JSON was not read.

triage.triage(gw, task, root, code_files, test_output):
- every raw answer is saved as config.STATE_DIR / "answers" / f"{task['id']}-triage-{n}.md" (n = 1, 2; folders
  made);
- when the first answer has no JSON object with a valid verdict, or its reason is empty (after strip), a second
  call is made with the same messages plus {"role": "assistant", "content": <first answer>} and
  {"role": "user", "content": triage.RETRY}, and the same keyword arguments except attempt=2;
- the result is parse(<second answer>) then; one retry only. A good first answer makes no second call.
triage.RETRY names the JSON keys verdict, test and reason and says the reason must not be empty."""
import pytest

from stratos import config, triage

TASK = {"id": "T009", "goal": "g", "tests": []}
GOOD = '{"verdict": "test_wrong", "test": "tests/a.py", "reason": "the expected value is off by one"}'


class FakeGateway:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append((list(messages), kw))
        return f"c{len(self.calls)}", self.answers.pop(0)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "TRIAGER", {"model": "m", "effort": "low", "max_tokens": 100})
    return tmp_path


def run(answers, root):
    gw = FakeGateway(answers)
    return gw, triage.triage(gw, TASK, root, [], "not ok 1 - t")


def test_a_good_answer_needs_no_retry(env):
    gw, result = run([GOOD], env)
    assert result["verdict"] == "test_wrong" and len(gw.calls) == 1
    assert (config.STATE_DIR / "answers" / "T009-triage-1.md").read_text(encoding="utf-8") == GOOD


@pytest.mark.parametrize("first", ["I think the test is wrong.",
                                   '{"verdict": "code_wrong", "test": "", "reason": "  "}',
                                   '{"verdict": "maybe", "test": "", "reason": "x"}'])
def test_a_retry(env, first):
    gw, result = run([first, GOOD], env)
    assert result == {"verdict": "test_wrong", "test": "tests/a.py", "reason": "the expected value is off by one"}
    (m1, kw1), (m2, kw2) = gw.calls
    assert m2 == m1 + [{"role": "assistant", "content": first}, {"role": "user", "content": triage.RETRY}]
    assert kw2 == dict(kw1, attempt=2) and kw1["attempt"] == 1
    assert (config.STATE_DIR / "answers" / "T009-triage-2.md").read_text(encoding="utf-8") == GOOD


def test_one_retry_only(env):
    gw, result = run(["no", "still no"], env)
    assert len(gw.calls) == 2 and result["verdict"] == "unclear"


def test_the_retry_text():
    for word in ("verdict", "test", "reason", "empty"):
        assert word in triage.RETRY
