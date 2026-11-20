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
        self.telemetry.record("switch_start", model=model, from_model=current)
        t0 = time.time()
        self._req("/api/models/load", {"model": model})
        secs = round(time.time() - t0, 2)
        self.telemetry.record("switch", model=model, from_model=current, seconds=secs)
        return secs

    def _stream_lines(self, path, body=None, timeout=config.REQUEST_TIMEOUT_S):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method="POST" if body is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for line in r:
                yield line.decode("utf-8", errors="replace").rstrip()

    def chat(self, messages, *, task, role, attempt, model, effort, max_tokens, reasoning_budget=None):
        """Returns (call_id, text). text is the answer, or the reasoning when the answer is empty (some models
        leave their output inside the thinking)."""
        call_id = new_call_id()
        self.telemetry.record("call_start", call_id=call_id, task=task, role=role, attempt=attempt, model=model)
        t0 = time.time()
        body = {"model": model, "messages": messages, "reasoning_effort": effort, "max_tokens": max_tokens}
        if reasoning_budget is not None:
            body["reasoning_budget_tokens"] = reasoning_budget

        if config.STREAM:
            body["stream"] = True
            body["stream_options"] = {"include_usage": True}
            live = config.STATE_DIR / "live"
            live.mkdir(parents=True, exist_ok=True)
            meta = {"call_id": call_id, "task": task, "role": role, "attempt": attempt, "model": model,
                    "started": t0}
            (live / "current.json").write_text(json.dumps(meta), encoding="utf-8")
            fh = (live / "current.txt").open("w", encoding="utf-8")
            reasoning_parts = []
            content_parts = []
            usage = {}
            finish = None
            answer_marker_written = False
            for line in self._stream_lines("/v1/chat/completions", body):
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if "usage" in chunk:
                    usage = chunk["usage"]
                choices = chunk.get("choices")
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                if "reasoning_content" in delta:
                    rc = delta["reasoning_content"]
                    reasoning_parts.append(rc)
                    fh.write(rc)
                    fh.flush()
                c = delta.get("content")
                if c:
                    if not answer_marker_written and reasoning_parts:
                        fh.write("\n--- answer ---\n")
                        answer_marker_written = True
                    content_parts.append(c)
                    fh.write(c)
                    fh.flush()
                fr = choices[0].get("finish_reason")
                if fr:
                    finish = fr
            fh.close()
            content = "".join(content_parts)
            reasoning = "".join(reasoning_parts)
            secs = round(time.time() - t0, 2)
            self.last_finish = finish
            event = dict(call_id=call_id, task=task, role=role, attempt=attempt, model=model, effort=effort,
                         prompt_tokens=usage.get("prompt_tokens"),
                         completion_tokens=usage.get("completion_tokens"), reasoning_chars=len(reasoning),
                         finish=finish, seconds=secs)
            if reasoning_budget is not None:
                event["reasoning_budget"] = reasoning_budget
            self.telemetry.record("call", **event)
            meta["finished"] = time.time()
            (live / "current.json").write_text(json.dumps(meta), encoding="utf-8")
            return call_id, (content if content.strip() else reasoning)

        r = self._req("/v1/chat/completions", body)
        secs = round(time.time() - t0, 2)
        msg = r["choices"][0]["message"]
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        usage = r.get("usage") or {}
        self.last_finish = r["choices"][0].get("finish_reason")   # "tool_calls": the model wanted a tool (Flint, T009)
        event = dict(call_id=call_id, task=task, role=role, attempt=attempt, model=model, effort=effort,
                     prompt_tokens=usage.get("prompt_tokens"),
                     completion_tokens=usage.get("completion_tokens"), reasoning_chars=len(reasoning),
                     finish=r["choices"][0].get("finish_reason"), seconds=secs)
        if reasoning_budget is not None:
            event["reasoning_budget"] = reasoning_budget
        self.telemetry.record("call", **event)
        return call_id, (content if content.strip() else reasoning)
