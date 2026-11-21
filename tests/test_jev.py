"""Tests for task T032: stratos/jev.py, a client for Jev (TypeSafe AI's System One decision model). No network here:
every test passes a fake `post`.

API (docs.typesafe.ai/api): POST https://api.typesafe.ai/v1/systemone, header "Authorization: Bearer <key>",
body {"model", "state", "questions": {name: question}}; a "choice" question has "criteria" {option: description} and
its answer is {"type": "choice", "choice", "confidence", "probabilities"}; a "noul" question is a yes/no and its answer
is {"type": "noul", "noul": probability of yes}. The response also carries "model" and "usage": {"input_tokens", ...}.

URL, MODEL ("jev-1.14.0", pinned so the probabilities stay comparable)

api_key() -> str | None
    TYPESAFE_API_KEY from the environment; on Windows, when it is not there, the user's stored variable
    (HKEY_CURRENT_USER\\Environment), because a session started before the key was set does not see it. None if absent.

ask(state, questions, key=None, post=None, timeout=10, retries=2, sleep=time.sleep) -> dict
    Never raises. post(url, body: bytes, headers: dict, timeout) -> (status: int, body: bytes); the default uses
    urllib. key defaults to api_key(). Returns {"ok": True, "answers", "model", "input_tokens", "seconds"} on HTTP 200,
    else {"ok": False, "error": str, "seconds"}. A missing key gives ok False without calling post. Status 429 and
    529 and exceptions raised by post are retried up to `retries` more times, sleeping 1 s, 2 s, ... between tries;
    other statuses (400, 401, 422, ...) are not retried. The error text carries the status code (or the exception).

role_request(task) -> (state, questions)
    Only a summary of the task goes out: state is {"goal": task goal, "files": task files, "file_count": n}; nothing
    read from disk. One question "role", type "choice", with exactly the criteria keys "coder" and "coder_hard".

choose_role(task, **ask_kwargs) -> decision | None
    {"choice": the answer's choice, "confidence": the answer's confidence, "reason": text naming Jev and the
    probabilities} like decide.choose_role, plus "input_tokens"; None when ask fails or the answer is malformed.
"""
import json

from stratos import jev


ROLE_ANSWER = {"model": "jev-1.14.0",
               "answers": {"role": {"type": "choice", "choice": "coder", "confidence": 0.9,
                                    "probabilities": {"coder": 0.95, "coder_hard": 0.05}}},
               "usage": {"input_tokens": 385, "output_tokens": 50}}


TASK = {"id": "T900", "files": ["stratos/a.py"], "goal": "Add a helper that counts words."}


class FakePost:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, url, body, headers, timeout):
        self.calls.append({"url": url, "body": json.loads(body.decode("utf-8")), "headers": headers,
                           "timeout": timeout})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def ok(payload):
    return (200, json.dumps(payload).encode("utf-8"))


def no_sleep(seconds):
    pass


def test_constants():
    assert jev.URL == "https://api.typesafe.ai/v1/systemone"
    assert jev.MODEL == "jev-1.14.0"


def test_api_key_from_environment(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k-123")
    assert jev.api_key() == "k-123"


def test_ask_sends_the_documented_request():
    post = FakePost(ok(ROLE_ANSWER))
    state, questions = {"goal": "x"}, {"q": {"type": "noul", "instructions": "y?"}}
    r = jev.ask(state, questions, key="k-1", post=post, sleep=no_sleep)
    assert r["ok"] is True and r["answers"] == ROLE_ANSWER["answers"]
    assert r["model"] == "jev-1.14.0" and r["input_tokens"] == 385 and r["seconds"] >= 0
    call = post.calls[0]
    assert call["url"] == jev.URL
    assert call["headers"]["Authorization"] == "Bearer k-1"
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["body"] == {"model": jev.MODEL, "state": state, "questions": questions}
    assert call["timeout"] == 10


def test_missing_key_does_not_call(monkeypatch):
    monkeypatch.setattr(jev, "api_key", lambda: None)
    post = FakePost()
    r = jev.ask({}, {"q": {"type": "noul", "instructions": "y?"}}, post=post, sleep=no_sleep)
    assert r["ok"] is False and r["error"] and post.calls == []


def test_retries_on_429_529_and_exceptions():
    post = FakePost((429, b'{"detail": "slow down"}'), (529, b"{}"), ok(ROLE_ANSWER))
    slept = []
    r = jev.ask({}, {}, key="k", post=post, sleep=slept.append)
    assert r["ok"] is True and len(post.calls) == 3 and slept == [1, 2]
    post = FakePost(TimeoutError("timed out"), ok(ROLE_ANSWER))
    assert jev.ask({}, {}, key="k", post=post, sleep=no_sleep)["ok"] is True


def test_gives_up_after_the_retries():
    post = FakePost((529, b"{}"), (529, b"{}"), (529, b"{}"), ok(ROLE_ANSWER))
    r = jev.ask({}, {}, key="k", post=post, sleep=no_sleep)
    assert r["ok"] is False and "529" in r["error"] and len(post.calls) == 3
    post = FakePost(OSError("down"), OSError("down"), OSError("down"))
    r = jev.ask({}, {}, key="k", post=post, sleep=no_sleep)
    assert r["ok"] is False and "down" in r["error"]


def test_no_retry_on_client_errors():
    for status in (400, 401, 422):
        post = FakePost((status, b'{"detail": "bad"}'), ok(ROLE_ANSWER))
        r = jev.ask({}, {}, key="k", post=post, sleep=no_sleep)
        assert r["ok"] is False and str(status) in r["error"] and len(post.calls) == 1


def test_bad_json_is_an_error_not_an_exception():
    r = jev.ask({}, {}, key="k", post=FakePost((200, b"not json")), sleep=no_sleep)
    assert r["ok"] is False and r["error"]


def test_role_request_sends_only_a_summary():
    state, questions = jev.role_request(TASK)
    assert state == {"goal": TASK["goal"], "files": TASK["files"], "file_count": 1}
    assert list(questions) == ["role"]
    q = questions["role"]
    assert q["type"] == "choice" and set(q["criteria"]) == {"coder", "coder_hard"} and q["instructions"]


def test_choose_role():
    post = FakePost(ok(ROLE_ANSWER))
    d = jev.choose_role(TASK, key="k", post=post, sleep=no_sleep)
    assert d["choice"] == "coder" and d["confidence"] == 0.9 and d["input_tokens"] == 385
    assert "jev" in d["reason"].lower()
    assert post.calls[0]["body"]["questions"]["role"]["type"] == "choice"


def test_choose_role_none_on_failure_or_malformed_answer():
    assert jev.choose_role(TASK, key="k", post=FakePost((401, b"{}")), sleep=no_sleep) is None
    broken = {"model": "jev-1.14.0", "answers": {}, "usage": {"input_tokens": 1}}
    assert jev.choose_role(TASK, key="k", post=FakePost(ok(broken)), sleep=no_sleep) is None


# ---- was test_jev_prompt.py ----
# Tests for task T033: the role question asks about the LOCAL coding models (T032's said "Choose the Jev model",
# which is not what is being chosen), and role_request reads the task plainly.


def test_the_question_is_about_the_local_coding_models():
    _, questions = jev.role_request({"goal": "g", "files": ["stratos/a.py"]})
    text = questions["role"]["instructions"]
    assert "local coding model" in text.lower()
    assert "jev" not in text.lower()


def test_a_task_without_files():
    state, _ = jev.role_request({"goal": "g"})
    assert state == {"goal": "g", "files": [], "file_count": 0}
