"""Tests for task T054: Gateway.chat(..., reasoning_budget=None) can cap a model's thinking.

PolyStrata's chat endpoint accepts "reasoning_budget_tokens": N, which closes the thinking after N tokens (measured
2026-11-18 on Qwen3.8-Flash-Next Coder: 9,685 tokens / 261 s without it, 1,081 tokens / 27 s with 300).

chat gets a keyword argument reasoning_budget (default None). When it is not None, the request body also holds
"reasoning_budget_tokens": reasoning_budget and the telemetry "call" event also holds reasoning_budget=<the value>.
When it is None, neither the body nor the event has that key, so everything else stays as it was."""
import json

from stratos import config, gateway
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


# ---- was test_gateway_live.py ----
# Tests for task gateway_live: the gateway says when a call or a model switch starts (for the dashboard).
#
# Gateway.chat records ("call_start", call_id=<the same id as the "call" event>, task, role, attempt, model) right
# before the request is sent. Gateway.ensure_model records ("switch_start", model=<new>, from_model=<current>) right
# before the load request, only when a switch is needed. The existing "call" and "switch" events stay as they are.


class Fake(Gateway):
    def __init__(self, telemetry, current="a"):
        super().__init__(telemetry, base_url="http://x")
        self.current = current
        self.seen = []

    def _req(self, path, body=None, timeout=None):
        kinds = [e["kind"] for e in self.telemetry.load()]
        self.seen.append((path, kinds))
        if path == "/health":
            return {"model": self.current}
        if path == "/api/models/load":
            self.current = body["model"]
            return {}
        return {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1}}


def test_call_start(tmp_path):
    gw = Fake(Telemetry(tmp_path / "t.jsonl"))
    call_id, text = gw.chat([{"role": "user", "content": "x"}], task="T1", role="coder", attempt=2, model="a",
                            effort="none", max_tokens=10)
    events = gw.telemetry.load()
    assert [e["kind"] for e in events] == ["call_start", "call"]
    start = events[0]
    assert {k: start[k] for k in ("call_id", "task", "role", "attempt", "model")} == {
        "call_id": call_id, "task": "T1", "role": "coder", "attempt": 2, "model": "a"}
    # the start event is written before the request goes out
    assert gw.seen == [("/v1/chat/completions", ["call_start"])]


def test_switch_start(tmp_path):
    gw = Fake(Telemetry(tmp_path / "t.jsonl"), current="a")
    assert gw.ensure_model("a") == 0.0
    assert gw.telemetry.load() == []
    gw.ensure_model("b")
    events = gw.telemetry.load()
    assert [e["kind"] for e in events] == ["switch_start", "switch"]
    assert events[0]["model"] == "b" and events[0]["from_model"] == "a"
    assert ("/api/models/load", ["switch_start"]) in gw.seen


# ---- was test_gateway_stream.py ----
# Tests for task gateway_stream (P12, 2026-11-20, user: "stream what it is doing"): PolyStrata answers
# "stream": true with text/event-stream chunks (probe 2026-11-20: delta.content pieces, finish_reason and usage in the
# last chunk before "data: [DONE]"). The gateway streams every call and writes the text as it comes into
# config.STATE_DIR / "live", which the dashboard shows.
#
# config.STREAM = True (tests/conftest.py turns it off). Gateway.chat with config.STREAM: the body gets
# "stream": True and "stream_options": {"include_usage": True}; the lines come from self._stream_lines(path, body)
# (an iterable of str lines from the HTTP response); a line "data: <json>" is a chunk, "data: [DONE]" ends, other lines
# are skipped. live/current.json is written at the start as {"call_id", "task", "role", "attempt", "model",
# "started": <time>} and live/current.txt is emptied; each delta's "reasoning_content" and "content" are appended to
# current.txt as they come (flushed), with the line "\n--- answer ---\n" written once before the first content that
# follows reasoning. The result is built as without streaming: content = the joined content pieces, reasoning = the
# joined reasoning pieces, finish = the last non-empty finish_reason, usage from the chunk that has "usage"; the same
# "call" telemetry event, last_finish, and the same return value (content, or the reasoning when the content is
# blank). At the end current.json gets "finished": <time> added. Without config.STREAM nothing changes.


class Tel:
    def __init__(self):
        self.events = []

    def record(self, kind, **f):
        self.events.append({"kind": kind, **f})


def chunk(delta=None, finish=None, usage=None):
    c = {"choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}]}
    if usage:
        c["usage"] = usage
    return "data: " + json.dumps(c)


def test_streamed_call(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "STREAM", True)
    lines = [": ping", chunk({"role": "assistant", "content": ""}), chunk({"reasoning_content": "think "}),
             chunk({"reasoning_content": "more"}), chunk({"content": "FILE: a.py"}), "",
             chunk({"content": "\nX = 1\n"}), chunk({}, finish="stop", usage={"prompt_tokens": 7, "completion_tokens": 3}),
             "data: [DONE]", chunk({"content": "after done"})]
    seen = {}

    def fake_stream(self, path, body):
        seen["path"], seen["body"] = path, body
        live = config.STATE_DIR / "live"
        assert json.loads((live / "current.json").read_text(encoding="utf-8"))["task"] == "T1"
        for ln in lines:
            yield ln
    monkeypatch.setattr(gateway.Gateway, "_stream_lines", fake_stream)
    tel = Tel()
    gw = gateway.Gateway(tel)
    call_id, text = gw.chat([{"role": "user", "content": "hi"}], task="T1", role="coder", attempt=2, model="m",
                            effort="low", max_tokens=99)
    assert text == "FILE: a.py\nX = 1\n"
    assert seen["path"] == "/v1/chat/completions"
    assert seen["body"]["stream"] is True and seen["body"]["stream_options"] == {"include_usage": True}
    live = config.STATE_DIR / "live"
    assert (live / "current.txt").read_text(encoding="utf-8") == "think more\n--- answer ---\nFILE: a.py\nX = 1\n"
    meta = json.loads((live / "current.json").read_text(encoding="utf-8"))
    assert meta["call_id"] == call_id and meta["role"] == "coder" and meta["attempt"] == 2 and "finished" in meta
    (call,) = [e for e in tel.events if e["kind"] == "call"]
    assert call["prompt_tokens"] == 7 and call["completion_tokens"] == 3 and call["finish"] == "stop"
    assert call["reasoning_chars"] == len("think more")
    assert gw.last_finish == "stop"


def test_reasoning_only_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "STREAM", True)
    lines = [chunk({"reasoning_content": "FILE: b.py"}), chunk({}, finish="length"), "data: [DONE]"]
    monkeypatch.setattr(gateway.Gateway, "_stream_lines", lambda self, path, body: iter(lines))
    _, text = gateway.Gateway(Tel()).chat([], task="T", role="r", attempt=1, model="m", effort="low", max_tokens=5)
    assert text == "FILE: b.py"


def test_null_pieces_and_errors(tmp_path, monkeypatch):
    """(Claude, reading T214) A chunk may carry "reasoning_content": null or "content": null; those add nothing. An
    error while reading the stream still closes current.txt and is raised."""
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "STREAM", True)
    lines = [chunk({"reasoning_content": None, "content": None}), chunk({"reasoning_content": "r"}),
             chunk({"content": "A", "reasoning_content": None}), chunk({}, finish="stop"), "data: [DONE]"]
    monkeypatch.setattr(gateway.Gateway, "_stream_lines", lambda self, path, body: iter(lines))
    _, text = gateway.Gateway(Tel()).chat([], task="T", role="r", attempt=1, model="m", effort="low", max_tokens=5)
    assert text == "A"

    def broken(self, path, body):
        yield chunk({"content": "half"})
        raise OSError("connection reset")
    monkeypatch.setattr(gateway.Gateway, "_stream_lines", broken)
    try:
        gateway.Gateway(Tel()).chat([], task="T", role="r", attempt=1, model="m", effort="low", max_tokens=5)
        raise AssertionError("expected OSError")
    except OSError:
        pass
    live = config.STATE_DIR / "live" / "current.txt"
    live.unlink()   # closed: Windows refuses to delete a file that is still open


def test_on_by_default_off_in_tests():
    from pathlib import Path
    assert "\nSTREAM = True" in Path(config.__file__).read_text(encoding="utf-8")
    assert config.STREAM is False   # tests/conftest.py
