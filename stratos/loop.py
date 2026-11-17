"""The task loop: build the prompt, ask the model, apply its files, run the tests, retry or commit.

Attempts follow the task's role's plan: the role's model a few times, then one cross-check by a different model.
A task that still fails is handed to a person (status needs_human). The loop is split into a write phase (the
attempts, committing a candidate when a review is on) and a review phase (judging the candidates)."""
from pathlib import Path

from . import config, context, decide, gitops, jev, patch, review, verify


def save_answer(task_id, attempt, text):
    """Keep every raw model answer (.stratos/answers/<task>-a<n>.md): without them a failure cannot be explained."""
    d = config.STATE_DIR / "answers"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{task_id}-a{attempt}.md").write_text(text or "", encoding="utf-8")


def attempt_plan(task):
    """The attempt schedule for this task, chosen by its role."""
    return config.ATTEMPT_PLANS[task.get("role", "coder")]


def check_answer(task, wt, text, finish=None):
    """Judge one model answer: parse its FILE blocks, apply them, run the tests; (result, detail)."""
    allowed = task["files"] or None
    files = patch.parse_files(text, allowed)
    if not files:
        result, detail = "no_files", "the answer held no FILE blocks for the task's files"
        if finish == "tool_calls":
            detail = ("You tried to call a tool, but there are no tools here and you cannot open files. "
                      "Everything you need is in this message: answer with the FILE blocks directly.")
    else:
        dropped = patch.dropped_definitions(wt, files, task["goal"])
        if dropped:
            result, detail = "dropped_defs", (
                "Your answer drops existing definitions that the goal did not ask to remove:\n"
                + "\n".join(f"{path}: {', '.join(names)}" for path, names in sorted(dropped.items()))
                + "\nWrite each file completely: keep everything that is already in it and add or change only what the goal asks.")
        else:
            try:
                written = patch.apply_files(wt, files, task["protected"], allowed)
            except patch.PatchRefused as e:
                result, detail = "refused", str(e)
            else:
                ok, out = verify.run_tests(wt, task["tests"])
                result, detail = ("passed" if ok else "failed"), out
    if finish == "length" and result != "passed":
        detail = ("Your answer was cut off: it reached the length limit. Think briefly and write only the "
                  "files the task needs, completely.\n" + detail)
    return result, detail


def write_task(store, gw, task_id, log=print):
    """Run the task's attempts until the tests pass, without a review; commit a candidate when a review is on."""
    task = store.get(task_id)
    bases = gitops.dependency_bases(config.REPO, task.get("after", []))
    try:
        wt = gitops.ensure_worktree(config.REPO, config.WORKTREES, task_id, bases=bases)
    except gitops.BaseConflict as e:
        store.update(task_id, status="needs_human", conflict=str(e))
        store.decide(task=task_id, result="base_conflict", detail=str(e))
        log(f"  task {task_id}: base conflict, handing to a person ({e})")
        return "needs_human"
    store.update(task_id, status="running", worktree=str(wt))
    failure = task.get("review_feedback")
    attempt = task.get("attempts", 0)
    for role, tries in attempt_plan(task):
        r = config.ROLES[role]
        history = []
        for _ in range(tries):
            attempt += 1
            switch = gw.ensure_model(r["model"])
            if switch:
                log(f"  model switch to {r['model']}: {switch:.1f} s")
            call_id, text = gw.chat(context.build_messages(task, wt, failure), task=task_id, role=role,
                                    attempt=attempt, model=r["model"], effort=r["effort"], max_tokens=r["max_tokens"])
            save_answer(task_id, attempt, text)
            result, detail = check_answer(task, wt, text, getattr(gw, "last_finish", None))
            gw.telemetry.record("outcome", call_id=call_id, task=task_id, result=result, detail=detail[-500:])
            store.decide(task=task_id, attempt=attempt, role=role, model=r["model"], result=result)
            log(f"  attempt {attempt} ({role}, {r['model']}): {result}")
            if result == "passed":
                written_by = f"Written by {r['model']} (attempt {attempt}); tests: {' '.join(task['tests'])}"
                if config.REVIEW:
                    sha = gitops.commit_all(wt, f"{task_id}: {task['title']} (candidate, awaiting review)\n\n{written_by}")
                    store.update(task_id, status="awaiting_review", commit=sha, attempts=attempt, model=r["model"], review_feedback=None)
                    return "candidate"
                sha = gitops.commit_all(wt, f"{task_id}: {task['title']}\n\n{written_by}")
                store.update(task_id, status="done", commit=sha, attempts=attempt, model=r["model"])
                return "done"
            gitops.discard_changes(wt)
            failure = detail[-3000:]
            history.append((result, detail))
            d = decide.should_escalate(history)
            gw.telemetry.record("decision", decision="escalate", decider="rules", task=task_id, attempt=attempt, role=role, choice=d["choice"], confidence=d["confidence"], reason=d["reason"])
            if config.JEV_SHADOW:
                j = jev.should_escalate(task, history)
                if j is None:
                    j = {"choice": None, "confidence": None, "reason": "jev unavailable", "input_tokens": 0}
                gw.telemetry.record("decision", decision="escalate", decider="jev", task=task_id, attempt=attempt, role=role, choice=j["choice"], confidence=j["confidence"], reason=j["reason"], input_tokens=j["input_tokens"])
            if d["choice"]:
                log(f"  attempt {attempt}: same failure again, moving to the cross-check")
                break
    store.update(task_id, status="needs_human", attempts=attempt)
    return "needs_human"


def review_tasks(store, gw, task_ids, log=print):
    """Judge the candidates of the given tasks: one reviewer model load for many tasks."""
    if not task_ids:
        return {}
    rv_role = config.ROLES["reviewer"]
    rv_switch = gw.ensure_model(rv_role["model"])
    if rv_switch:
        log(f"  model switch to {rv_role['model']}: {rv_switch:.1f} s")
    results = {}
    for task_id in task_ids:
        task = store.get(task_id)
        wt = Path(task["worktree"])
        diff_text = gitops.commit_diff(wt)
        attempt = task.get("attempts", 0)
        try:
            rv_call, rv_text = gw.chat(review.build_messages(task, diff_text), task=task_id, role="reviewer",
                                       attempt=attempt, model=rv_role["model"], effort=rv_role["effort"],
                                       max_tokens=rv_role["max_tokens"])
        except Exception as e:   # a timed-out reviewer (T052) must not stop the batch; the candidate waits for the next run
            store.decide(task=task_id, attempt=attempt, role="reviewer", model=rv_role["model"],
                         result="review_error", detail=str(e)[:300])
            log(f"  task {task_id}: review call failed ({e}); it stays awaiting_review")
            results[task_id] = "review_error"
            continue
        save_answer(task_id, f"{attempt}-review", rv_text)
        rv = review.parse(rv_text)
        verdict = rv["verdict"]
        gw.telemetry.record("outcome", call_id=rv_call, task=task_id, result="review_" + verdict, detail=review.format_issues(rv)[-500:])
        store.decide(task=task_id, attempt=attempt, role="reviewer", model=rv_role["model"],
                     result="review_" + verdict, issues=len(rv["issues"]))
        if review.is_blocking(rv):
            gitops.undo_last_commit(wt)
            store.update(task_id, status="todo", commit=None,
                         review_feedback="The tests passed, but a code review found problems. Fix them:\n" + review.format_issues(rv))
            result = "rejected"
        else:
            rv_msg = f"Review: {verdict}"
            issues = review.format_issues(rv)
            if issues:
                rv_msg += "\n" + issues
            gitops.finalize_commit_message(wt, rv_msg)
            store.update(task_id, status="done", review=verdict)
            result = "done"
        log(f"  task {task_id}: {result}")
        results[task_id] = result
    return results


def run_all(store, gw, task_ids, log=print):
    """Run the given tasks in rounds of (write all, then review all). Candidates left awaiting_review by an
    earlier run (its review call failed) are reviewed first."""
    waiting = [tid for tid in task_ids if store.get(tid)["status"] == "awaiting_review"]
    if waiting:
        review_tasks(store, gw, waiting, log=log)
    for _ in range(config.REVIEW_ROUNDS):
        runnable = []
        for tid in task_ids:
            task = store.get(tid)
            if task["status"] != "todo":
                continue
            if all(store.get(a)["status"] == "done" for a in task.get("after", [])):
                runnable.append(tid)
        if not runnable:
            break
        candidates = []
        for tid in runnable:
            if write_task(store, gw, tid, log=log) == "candidate":
                candidates.append(tid)
        if candidates:
            review_tasks(store, gw, candidates, log=log)
    final = {}
    for tid in task_ids:
        task = store.get(tid)
        if task["status"] == "todo" and task.get("review_feedback"):
            store.update(tid, status="needs_human")
            task = store.get(tid)
        final[tid] = task["status"]
    return final


def run_task(store, gw, task_id, log=print):
    """Write, then review, then write again ... for up to config.REVIEW_ROUNDS rounds."""
    for _ in range(config.REVIEW_ROUNDS):
        r = write_task(store, gw, task_id, log=log)
        if r != "candidate":
            return r
        if review_tasks(store, gw, [task_id], log=log)[task_id] == "done":
            return "done"
    store.update(task_id, status="needs_human")
    return "needs_human"
