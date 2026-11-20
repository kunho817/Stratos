"""Replay past tasks with a chosen model and judge each answer like the task loop.

This module replays previously-run tasks against a copy of the repository as it was
before the task started, using a chosen model, and judges each answer exactly like the
task loop (loop.check_answer). It is for trying a model (for example a new one) on tasks
with a known outcome; nothing is committed or merged.
"""

import re
import time
from pathlib import Path

from . import config, context, embed, gitops, loop, memstore, recall


def base_commit(repo, task_id):
    log = gitops.git(repo, "log", "--reverse", "--format=%H%x09%s", "main")
    for line in log.splitlines():
        sha, _, subject = line.partition("\t")
        if subject.startswith(task_id + ":"):
            return gitops.git(repo, "rev-parse", sha + "^1")
    return None


def lesson_pack(store, task, embedder=None):
    text = recall.pack(store, task["title"] + "\n" + task["goal"], embedder, None,
                       budget=6000,
                       sections=[("lesson", "LESSONS FROM PEOPLE'S CORRECTIONS", 3)],
                       always_tags={"code"})
    if not text:
        return None
    pattern = re.compile(r"\b" + re.escape(task["id"]) + r"\b")
    lines = text.splitlines()
    kept = [line for line in lines if not pattern.search(line)]
    if not any(line.startswith("- ") for line in kept):
        return None
    return "\n".join(kept)


def replay(tasks, gw, *, model, effort, max_tokens, tries, repo, root, log=print,
           reasoning_budget=None, memory=False):
    root = Path(root)
    results = []
    for task in tasks:
        task_id = task["id"]
        base = base_commit(repo, task_id)
        if base is None:
            results.append({"task": task_id, "result": "no_base", "attempts": 0, "seconds": 0.0})
            continue
        path = root / f"replay-{task_id}"
        if path.exists():
            gitops.git(repo, "worktree", "remove", "--force", str(path))
        gitops.git(repo, "worktree", "add", "--detach", str(path), base)
        seconds = 0.0
        attempts = 0
        result = "no_base"
        failure = None
        pack = None
        if memory and (config.STATE_DIR / "memory.db").exists():
            store = memstore.Store(config.STATE_DIR / "memory.db")
            try:
                pack = lesson_pack(store, task, embed.Embedder())
            finally:
                store.close()
        try:
            for n in range(1, tries + 1):
                attempts = n
                gw.ensure_model(model)
                if pack is not None:
                    messages = context.build_messages(task, path, failure, memory=pack)
                else:
                    messages = context.build_messages(task, path, failure)
                start = time.perf_counter()
                if reasoning_budget is not None:
                    call_id, text = gw.chat(messages, task=task_id, role="replay", attempt=n, model=model,
                                            effort=effort, max_tokens=max_tokens, reasoning_budget=reasoning_budget)
                else:
                    call_id, text = gw.chat(messages, task=task_id, role="replay", attempt=n, model=model,
                                            effort=effort, max_tokens=max_tokens)
                seconds += time.perf_counter() - start
                d = config.STATE_DIR / "replay_answers"
                d.mkdir(parents=True, exist_ok=True)
                (d / f"{task_id}-{call_id}.md").write_text(text or "", encoding="utf-8")
                result, detail = loop.check_answer(task, path, text, getattr(gw, "last_finish", None))
                gw.telemetry.record("outcome", call_id=call_id, task=task_id, result=result, detail=detail[-500:])
                log(f"  {task_id} attempt {n} ({model}): {result}")
                if result == "passed":
                    break
                failure = detail[-3000:]
                gitops.discard_changes(str(path))
        finally:
            gitops.git(repo, "worktree", "remove", "--force", str(path))
            gitops.git(repo, "worktree", "prune")
        results.append({"task": task_id, "result": result, "attempts": attempts, "seconds": seconds})
    return results

