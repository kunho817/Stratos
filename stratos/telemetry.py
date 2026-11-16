"""Telemetry: one JSON line per event in .stratos/telemetry.jsonl.

Event kinds:
  call     a model request   (call_id, task, role, attempt, model, effort, prompt_tokens, completion_tokens,
                              reasoning_chars, finish, seconds)
  switch   a model change    (model, from_model, seconds)
  outcome  what a call led to (call_id, task, result: passed | failed | no_files | refused, detail)
"""
import json
import time
import uuid
from pathlib import Path


class Telemetry:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, kind, **fields):
        event = {"ts": round(time.time(), 3), "kind": kind, **fields}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def load(self):
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]


def new_call_id():
    return uuid.uuid4().hex[:12]
