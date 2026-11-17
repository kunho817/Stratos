"""Replay past tasks with a chosen model and judge each answer like the task loop.

This module replays previously-run tasks against a copy of the repository as it was
before the task started, using a chosen model, and judges each answer exactly like the
task loop (loop.check_answer). It is for trying a model (for example a new one) on tasks
with a known outcome; nothing is committed or merged.
"""

import time
from pathlib import Path

from . import config, context, gitops, loop


def base_commit(repo, task_id):
    log = gitops.git(repo, "log", "--reverse", "--format=%H%x09%s", "main")
    for line in log.splitlines():
        sha, _, subject = line.partition("\t")
        if subject.startswith(task_id + ":"):
            return gitops.git(repo, "rev-parse", sha + "^1")
    return None


def replay(tasks, gw, *, model, effort, max_tokens, tries, repo, root, log=print):
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
        try:
            for n in range(1, tries + 1):
                attempts = n
                gw.ensure_model(model)
                messages = context.build_messages(task, path, failure)
                start = time.perf_counter()
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
