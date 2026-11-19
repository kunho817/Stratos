"""Tests for task gateway_live: the gateway says when a call or a model switch starts (for the dashboard).

Gateway.chat records ("call_start", call_id=<the same id as the "call" event>, task, role, attempt, model) right
before the request is sent. Gateway.ensure_model records ("switch_start", model=<new>, from_model=<current>) right
before the load request, only when a switch is needed. The existing "call" and "switch" events stay as they are."""
from stratos.gateway import Gateway
from stratos.telemetry import Telemetry


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
