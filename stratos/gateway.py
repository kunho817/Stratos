"""PolyStrata client. Every request and model switch is written to telemetry."""
import json
import time
import urllib.request

from . import config
from .telemetry import new_call_id


class Gateway:
    def __init__(self, telemetry, base_url=config.BASE_URL):
        self.base = base_url.rstrip("/")
        self.telemetry = telemetry

    def _req(self, path, body=None, timeout=config.REQUEST_TIMEOUT_S):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method="POST" if body is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def health(self):
        return self._req("/health", timeout=10)

    def ensure_model(self, model):
        current = self.health().get("model")
        if current == model:
            return 0.0
        t0 = time.time()
        self._req("/api/models/load", {"model": model})
        secs = round(time.time() - t0, 2)
        self.telemetry.record("switch", model=model, from_model=current, seconds=secs)
        return secs

    def chat(self, messages, *, task, role, attempt, model, effort, max_tokens):
        """Returns (call_id, text). text is the answer, or the reasoning when the answer is empty (some models
        leave their output inside the thinking)."""
        call_id = new_call_id()
        t0 = time.time()
        r = self._req("/v1/chat/completions", {"model": model, "messages": messages, "reasoning_effort": effort,
                                               "max_tokens": max_tokens})
        secs = round(time.time() - t0, 2)
        msg = r["choices"][0]["message"]
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        usage = r.get("usage") or {}
        self.telemetry.record("call", call_id=call_id, task=task, role=role, attempt=attempt, model=model,
                              effort=effort, prompt_tokens=usage.get("prompt_tokens"),
                              completion_tokens=usage.get("completion_tokens"), reasoning_chars=len(reasoning),
                              finish=r["choices"][0].get("finish_reason"), seconds=secs)
        return call_id, (content if content.strip() else reasoning)
