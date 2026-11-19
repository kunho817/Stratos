"""Short diagnosis of a failed coding attempt for an A/B test."""

import hashlib

from stratos import config

SYSTEM = ("You are a code reviewer. Tell the coder what went wrong in the failed attempt and what "
          "the next attempt must do differently, concretely (function names, the exact test expectation), "
          "in at most 120 words, without code blocks.")


def use_hint(task_id, attempt):
    if config.DIAGNOSE_ALWAYS:
        return True
    return int(hashlib.sha256(f"{task_id}:{attempt}".encode("utf-8")).hexdigest(), 16) % 2 == 0


def build_messages(task, diff, detail):
    if not diff.strip():
        d = "(no change was written)"
    else:
        d = diff[-4000:]
    user = f"GOAL:\n{task['goal']}\n\nDIFF:\n{d}\n\nTEST OUTPUT:\n{detail[-3000:]}"
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def with_hint(failure, hint):
    return failure + "\n\nA REVIEWER READ YOUR DIFF AND THIS OUTPUT. DIAGNOSIS:\n" + hint


def diagnose(gw, task, diff, detail, attempt):
    d = config.DIAGNOSER
    gw.ensure_model(d["model"])
    messages = build_messages(task, diff, detail)
    result = gw.chat(messages, task=task["id"], role="diagnoser", attempt=attempt,
                     model=d["model"], effort=d["effort"], max_tokens=d["max_tokens"])
    if isinstance(result, tuple):
        return result[1].strip()
    return result.strip()
