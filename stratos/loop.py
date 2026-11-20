"""The task loop: build the prompt, ask the model, apply its files, run the tests, retry or commit.

Attempts follow the task's role's plan: the role's model a few times, then one cross-check by a different model.
A task that still fails is handed to a person (status needs_human). The loop is split into a write phase (the
attempts, committing a candidate when a review is on) and a review phase (judging the candidates)."""
from pathlib import Path

from . import codemap, config, context, decide, diagnose, embed, gitops, jev, memstore, patch, preflight, recall, review, triage, verify

CODER_SECTIONS = [
    ("guide", "GENERAL LESSONS (from earlier projects)", 3),
    ("lesson", "LESSONS FROM PEOPLE'S CORRECTIONS", 3),
    ("wiki", "MODULE NOTES (written by a model from the code; check the code)", 2),
    ("code", "RELEVANT CODE", 5),
]


def save_answer(task_id, attempt, text):
    """Keep every raw model answer (.stratos/answers/<task>-a<n>.md): without them a failure cannot be explained."""
    d = config.STATE_DIR / "answers"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{task_id}-a{attempt}.md").write_text(text or "", encoding="utf-8")


def attempt_plan(task):
    """The attempt schedule for this task, chosen by its role."""
    return config.ATTEMPT_PLANS[task.get("role", "coder")]


def task_memory(task):
    """Return a context pack from memory for this task, or None."""
    if not config.MEMORY:
        return None
    mem_path = config.STATE_DIR / "memory.db"
    if not mem_path.exists():
        return None
    try:
        store = memstore.Store(mem_path)
        try:
            return recall.pack(store, task["title"] + "\n" + task["goal"], embed.Embedder(),
                              codemap.build(config.REPO), budget=6000, sections=CODER_SECTIONS,
                              always_tags={"code"})
        finally:
            store.close()
    except Exception:
        return None


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
                errors = verify.syntax_errors(wt, written)
                if errors:
                    result, detail = "syntax_error", (
                        "Your files do not compile:\n"
                        + "\n".join(errors)
                        + "\nWrite each file completely and check its syntax.")
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
    memory = task_memory(task)
    bases = gitops.dependency_bases(config.REPO, task.get("after", []))
    try:
        wt = gitops.ensure_worktree(config.REPO, config.WORKTREES, task_id, bases=bases)
    except gitops.BaseConflict as e:
        store.update(task_id, status="needs_human", conflict=str(e))
        store.decide(task=task_id, result="base_conflict", detail=str(e))
        log(f"  task {task_id}: base conflict, handing to a person ({e})")
        return "needs_human"
    store.update(task_id, status="running", worktree=str(wt))
    before = None
    if config.PREFLIGHT:
        pre = preflight.check(task, wt)
        if pre["verdict"] == "refuse":
            store.update(task_id, status="needs_human", preflight=pre["reason"])
            store.decide(task=task_id, result="preflight_refused", reason=pre["reason"])
            gw.telemetry.record("preflight", task=task_id, verdict="refuse", reason=pre["reason"])
            log(f"  preflight: {pre['reason']}")
            return "needs_human"
        gw.telemetry.record("preflight", task=task_id, verdict="run", reason=pre["reason"])
        if pre["output"]:
            before = pre["output"][-3000:]
    failure = task.get("review_feedback")
    attempt = task.get("attempts", 0)
    last_failed_text = None
    last_failed_detail = None
    failed_ids = {}
    for role, tries in attempt_plan(task):
        r = config.ROLES[role]
        history = []
        for i in range(tries):
            attempt += 1
            switch = gw.ensure_model(r["model"])
            if switch:
                log(f"  model switch to {r['model']}: {switch:.1f} s")
            budget = r.get("reasoning_budget")
            extra = {"before": before} if before else {}
            if budget is not None:
                call_id, text = gw.chat(context.build_messages(task, wt, failure, memory=memory, **extra), task=task_id, role=role,
                                        attempt=attempt, model=r["model"], effort=r["effort"], max_tokens=r["max_tokens"],
                                        reasoning_budget=budget)
            else:
                call_id, text = gw.chat(context.build_messages(task, wt, failure, memory=memory, **extra), task=task_id, role=role,
                                        attempt=attempt, model=r["model"], effort=r["effort"], max_tokens=r["max_tokens"])
            save_answer(task_id, attempt, text)
            result, detail = check_answer(task, wt, text, getattr(gw, "last_finish", None))
            if result == "failed":
                last_failed_text = text
                last_failed_detail = detail
                failed_ids.setdefault(r["model"], set()).update(decide._extract_ids(detail))
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
            history.append((result, detail))
            d = decide.should_escalate(history)
            gw.telemetry.record("decision", decision="escalate", decider="rules", task=task_id, attempt=attempt,
                                role=role, choice=d["choice"], confidence=d["confidence"], reason=d["reason"])
            if config.JEV_SHADOW:
                j = jev.should_escalate(task, history)
                if j is None:
                    j = {"choice": None, "confidence": None, "reason": "jev unavailable", "input_tokens": 0}
                gw.telemetry.record("decision", decision="escalate", decider="jev", task=task_id, attempt=attempt,
                                    role=role, choice=j["choice"], confidence=j["confidence"],
                                    reason=j["reason"], input_tokens=j["input_tokens"])
            diag_needed = (config.DIAGNOSE_AB and role == "coder" and not d["choice"]
                           and i < tries - 1)
            if diag_needed:
                diff = gitops.diff(wt)
            gitops.discard_changes(wt)
            failure = detail[-3000:]
            if diag_needed:
                next_attempt = attempt + 1
                used = diagnose.use_hint(task_id, next_attempt)
                hint = None
                diag_error = None
                if used:
                    try:
                        hint = diagnose.diagnose(gw, task, diff, detail, next_attempt)
                        failure = diagnose.with_hint(failure, hint)
                        log(f"  attempt {attempt}: diagnosis added for attempt {next_attempt}")
                    except Exception as e:
                        used = False
                        diag_error = str(e)
                chars = len(hint) if used else 0
                kw = dict(task=task_id, attempt=next_attempt, used=used, chars=chars)
                if diag_error is not None:
                    kw["error"] = diag_error
                gw.telemetry.record("diagnosis", **kw)
            if d["choice"]:
                log(f"  attempt {attempt}: same failure again, moving to the cross-check")
                break

    models = sorted(m for m in failed_ids if failed_ids[m])
    if len(models) >= 2:
        consensus = sorted(set.intersection(*(failed_ids[m] for m in models)))
    else:
        consensus = []

    if consensus:
        store.update(task_id, consensus=consensus)
        gw.telemetry.record("consensus", task=task_id, tests=consensus, models=models)
        log(f"  consensus: {', '.join(models)} all failed {', '.join(consensus)}")

    if config.TRIAGE and last_failed_text is not None:
        code_files = patch.parse_files(last_failed_text, task["files"] or None)
        try:
            extra = {"consensus": consensus} if consensus else {}
            triage_result = triage.triage(gw, task, wt, code_files, last_failed_detail, **extra)
            store.update(task_id, triage=triage_result)
            gw.telemetry.record("triage", task=task_id, verdict=triage_result["verdict"],
                                test=triage_result["test"], reason=triage_result["reason"])
            log(f"  triage: {triage_result['verdict']} - {triage_result['reason']}")
        except Exception as e:
            log(f"  triage: {e}")
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
        imports_text = review.import_lines(wt, review.changed_paths(diff_text))
        try:
            rv_call, rv_text = gw.chat(review.build_messages(task, diff_text, files=review.project_files(wt),
                                       imports=imports_text), task=task_id, role="reviewer",
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
        gw.telemetry.record("outcome", call_id=rv_call, task=task_id, result="review_" + verdict,
                            detail=review.format_issues(rv)[-500:])
        store.decide(task=task_id, attempt=attempt, role="reviewer", model=rv_role["model"],
                     result="review_" + verdict, issues=len(rv["issues"]))
        if review.is_blocking(rv):
            gitops.undo_last_commit(wt)
            store.update(task_id, status="todo", commit=None,
                         review_feedback="The tests passed, but a code review found problems. Fix them:\n"
                                         + review.format_issues(rv))
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

