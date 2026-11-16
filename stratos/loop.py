"""The task loop: build the prompt, ask the model, apply its files, run the tests, retry or commit.

Attempts follow the task's role's plan: the role's model a few times, then one cross-check by a different model.
A task that still fails is handed to a person (status needs_human)."""
from . import config, context, gitops, patch, verify


def save_answer(task_id, attempt, text):
    """Keep every raw model answer (.stratos/answers/<task>-a<n>.md): without them a failure cannot be explained."""
    d = config.STATE_DIR / "answers"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{task_id}-a{attempt}.md").write_text(text or "", encoding="utf-8")


def attempt_plan(task):
    """The attempt schedule for this task, chosen by its role."""
    return config.ATTEMPT_PLANS[task.get("role", "coder")]


def run_task(store, gw, task_id, log=print):
    task = store.get(task_id)
    wt = gitops.ensure_worktree(config.REPO, config.WORKTREES, task_id)
    store.update(task_id, status="running", worktree=str(wt))
    failure = None
    attempt = 0
    for role, tries in attempt_plan(task):
        r = config.ROLES[role]
        for _ in range(tries):
            attempt += 1
            switch = gw.ensure_model(r["model"])
            if switch:
                log(f"  model switch to {r['model']}: {switch:.1f} s")
            call_id, text = gw.chat(context.build_messages(task, wt, failure), task=task_id, role=role,
                                    attempt=attempt, model=r["model"], effort=r["effort"], max_tokens=r["max_tokens"])
            save_answer(task_id, attempt, text)
            allowed = task["files"] or None
            files = patch.parse_files(text, allowed)
            if not files:
                result, detail = "no_files", "the answer held no FILE blocks for the task's files"
            else:
                try:
                    written = patch.apply_files(wt, files, task["protected"], allowed)
                except patch.PatchRefused as e:
                    result, detail = "refused", str(e)
                else:
                    ok, out = verify.run_tests(wt, task["tests"])
                    result, detail = ("passed" if ok else "failed"), out
            gw.telemetry.record("outcome", call_id=call_id, task=task_id, result=result, detail=detail[-500:])
            store.decide(task=task_id, attempt=attempt, role=role, model=r["model"], result=result)
            log(f"  attempt {attempt} ({role}, {r['model']}): {result}")
            if result == "passed":
                sha = gitops.commit_all(wt, f"{task_id}: {task['title']}\n\nWritten by {r['model']} "
                                            f"(attempt {attempt}); tests: {' '.join(task['tests'])}")
                store.update(task_id, status="done", commit=sha, attempts=attempt, model=r["model"])
                return "done"
            gitops.discard_changes(wt)
            failure = detail[-3000:]
    store.update(task_id, status="needs_human", attempts=attempt)
    return "needs_human"
