"""Tests for task gateway_stream (P12, 2026-11-20, user: "stream what it is doing"): PolyStrata answers
"stream": true with text/event-stream chunks (probe 2026-11-20: delta.content pieces, finish_reason and usage in the
last chunk before "data: [DONE]"). The gateway streams every call and writes the text as it comes into
config.STATE_DIR / "live", which the dashboard shows.

config.STREAM = True (tests/conftest.py turns it off). Gateway.chat with config.STREAM: the body gets
"stream": True and "stream_options": {"include_usage": True}; the lines come from self._stream_lines(path, body)
(an iterable of str lines from the HTTP response); a line "data: <json>" is a chunk, "data: [DONE]" ends, other lines
are skipped. live/current.json is written at the start as {"call_id", "task", "role", "attempt", "model",
"started": <time>} and live/current.txt is emptied; each delta's "reasoning_content" and "content" are appended to
current.txt as they come (flushed), with the line "\\n--- answer ---\\n" written once before the first content that
follows reasoning. The result is built as without streaming: content = the joined content pieces, reasoning = the
joined reasoning pieces, finish = the last non-empty finish_reason, usage from the chunk that has "usage"; the same
"call" telemetry event, last_finish, and the same return value (content, or the reasoning when the content is
blank). At the end current.json gets "finished": <time> added. Without config.STREAM nothing changes."""
import json

from stratos import config, gateway


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
