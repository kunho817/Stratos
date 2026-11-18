"""Tests for task T054: Gateway.chat(..., reasoning_budget=None) can cap a model's thinking.

PolyStrata's chat endpoint accepts "reasoning_budget_tokens": N, which closes the thinking after N tokens (measured
2026-11-18 on Qwen3.8-Flash-Next Coder: 9,685 tokens / 261 s without it, 1,081 tokens / 27 s with 300).

chat gets a keyword argument reasoning_budget (default None). When it is not None, the request body also holds
"reasoning_budget_tokens": reasoning_budget and the telemetry "call" event also holds reasoning_budget=<the value>.
When it is None, neither the body nor the event has that key, so everything else stays as it was."""
from stratos.gateway import Gateway
from stratos.telemetry import Telemetry

REPLY = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 5, "completion_tokens": 7}}


def make(tmp_path):
    gw = Gateway(Telemetry(tmp_path / "t.jsonl"), base_url="http://127.0.0.1:1")
    sent = []

    def req(path, body=None, timeout=None):
        sent.append((path, body))
        return REPLY
    gw._req = req
    return gw, sent


def ask(gw, **kw):
    return gw.chat([{"role": "user", "content": "hi"}], task="T1", role="coder", attempt=1, model="m",
                   effort="low", max_tokens=100, **kw)


def test_without_a_budget_nothing_changes(tmp_path):
    gw, sent = make(tmp_path)
    call_id, text = ask(gw)
    assert text == "ok"
    path, body = sent[0]
    assert path == "/v1/chat/completions"
    assert body == {"model": "m", "messages": [{"role": "user", "content": "hi"}], "reasoning_effort": "low",
                    "max_tokens": 100}
    (event,) = [e for e in gw.telemetry.load() if e["kind"] == "call"]
    assert event["call_id"] == call_id and "reasoning_budget" not in event


def test_explicit_none_is_the_same_as_no_budget(tmp_path):
    gw, sent = make(tmp_path)
    ask(gw, reasoning_budget=None)
    assert "reasoning_budget_tokens" not in sent[0][1]
    assert all("reasoning_budget" not in e for e in gw.telemetry.load())


def test_a_budget_goes_into_the_request_and_the_telemetry(tmp_path):
    gw, sent = make(tmp_path)
    ask(gw, reasoning_budget=300)
    body = sent[0][1]
    assert body["reasoning_budget_tokens"] == 300
    assert body["max_tokens"] == 100 and body["reasoning_effort"] == "low"
    (event,) = [e for e in gw.telemetry.load() if e["kind"] == "call"]
    assert event["reasoning_budget"] == 300 and event["completion_tokens"] == 7 and event["effort"] == "low"
