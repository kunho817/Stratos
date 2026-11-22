"""Summarize telemetry written by stratos/telemetry.py."""


def summarize(events, since=None):
    if since is None:
        events = [e for e in events]
    else:
        events = [e for e in events if "ts" in e and e["ts"] >= since]

    calls = 0
    prompt_tokens = 0
    completion_tokens = 0
    switches = 0
    switch_seconds = 0.0
    by_model = {}
    outcomes = {}
    wasted_tokens = 0
    human_verdicts = 0

    call_tokens = {}
    passed_since_verdict = {}

    for event in events:
        kind = event.get("kind")

        if kind == "call":
            calls += 1
            model = event.get("model")
            p = event.get("prompt_tokens") or 0
            c = event.get("completion_tokens") or 0
            prompt_tokens += p
            completion_tokens += c
            seconds = event.get("seconds", 0) or 0

            bucket = by_model.setdefault(
                model,
                {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "seconds": 0.0},
            )
            bucket["calls"] += 1
            bucket["prompt_tokens"] += p
            bucket["completion_tokens"] += c
            bucket["seconds"] += seconds

            call_id = event.get("call_id")
            call_tokens[call_id] = p + c

        elif kind == "switch":
            switches += 1
            switch_seconds += event.get("seconds", 0) or 0

        elif kind == "outcome":
            result = event.get("result")
            outcomes[result] = outcomes.get(result, 0) + 1
            call_id = event.get("call_id")
            if result != "passed":
                wasted_tokens += call_tokens.get(call_id, 0)
            else:
                task = event.get("task")
                passed_since_verdict.setdefault(task, []).append(call_id)

        elif kind == "verdict":
            human_verdicts += 1
            task = event.get("task")
            for call_id in passed_since_verdict.pop(task, []):
                outcomes["passed"] -= 1
                if outcomes["passed"] == 0:
                    del outcomes["passed"]
                outcomes["discarded"] = outcomes.get("discarded", 0) + 1
                wasted_tokens += call_tokens.get(call_id, 0)

    return {
        "calls": calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "switches": switches,
        "switch_seconds": switch_seconds,
        "by_model": by_model,
        "outcomes": outcomes,
        "wasted_tokens": wasted_tokens,
        "human_verdicts": human_verdicts,
    }


def role_truth(events):
    role_map = {}
    for event in events:
        if event.get("kind") == "call" and event.get("role") in ("coder", "coder_hard"):
            role_map[event["call_id"]] = (event["task"], event["role"])

    coder_pass = {}
    coder_fail = {}
    hard_pass = {}
    for event in events:
        if event.get("kind") != "outcome":
            continue
        call_id = event.get("call_id")
        if call_id not in role_map:
            continue
        task, role = role_map[call_id]
        if role == "coder":
            if event.get("result") == "passed":
                coder_pass[task] = True
            else:
                coder_fail[task] = True
        elif role == "coder_hard":
            if event.get("result") == "passed":
                hard_pass[task] = True

    result = {}
    for task in set(coder_pass) | set(coder_fail) | set(hard_pass):
        if task in coder_pass:
            result[task] = "coder"
        elif task in coder_fail and task in hard_pass:
            result[task] = "coder_hard"

    return result


def decision_accuracy(events, threshold=0.3):
    last = {}
    for event in events:
        if event.get("kind") == "decision" and event.get("decision") == "role":
            decider = event.get("decider", "rules")
            last[(event["task"], decider)] = event

    truth = role_truth(events)

    by_decider = {}
    for (task, decider), event in last.items():
        bucket = by_decider.setdefault(decider, {
            "decisions": 0,
            "judged": 0,
            "correct": 0,
            "confident_judged": 0,
            "confident_correct": 0,
        })
        bucket["decisions"] += 1
        choice = event.get("choice")
        if choice is not None and task in truth:
            confident = (event.get("confidence") or 0) >= threshold
            bucket["judged"] += 1
            if confident:
                bucket["confident_judged"] += 1
            if choice == truth[task]:
                bucket["correct"] += 1
                if confident:
                    bucket["confident_correct"] += 1

    return by_decider


def escalation_accuracy(events, threshold=0.7):
    call_map = {}
    for event in events:
        if event.get("kind") == "call" and event.get("role") in ("coder", "coder_hard"):
            call_map[event.get("call_id")] = (event.get("task"), event.get("role"))

    by_decider = {}
    for i, event in enumerate(events):
        if event.get("kind") != "decision" or event.get("decision") != "escalate":
            continue
        decider = event.get("decider") or "rules"
        task = event.get("task")
        role = event.get("role")
        choice = event.get("choice")

        bucket = by_decider.setdefault(decider, {
            "decisions": 0,
            "judged": 0,
            "correct": 0,
            "confident_judged": 0,
            "confident_correct": 0,
        })
        bucket["decisions"] += 1
        if choice is None:
            continue

        truth = None
        for later in events[i + 1:]:
            if later.get("kind") != "outcome" or later.get("result") != "passed":
                continue
            later_call_id = later.get("call_id")
            if later_call_id not in call_map:
                continue
            later_task, later_role = call_map[later_call_id]
            if later_task != task:
                continue
            truth = later_role != role
            break

        if truth is None:
            continue

        bucket["judged"] += 1
        confident = (event.get("confidence") or 0) >= threshold
        if confident:
            bucket["confident_judged"] += 1
        if choice == truth:
            bucket["correct"] += 1
            if confident:
                bucket["confident_correct"] += 1

    return by_decider


def replay_summary(events):
    """Summarize how each model did in `stratos replay`."""
    runs_by_key = {}
    open_runs = {}
    call_run = {}

    for event in events:
        kind = event.get("kind")
        if kind == "call":
            budget = event.get("reasoning_budget")
            key = (event.get("model"), event.get("effort"), budget, event.get("task"))
            attempt = event.get("attempt")
            if attempt is None:
                attempt = 1
            seconds = event.get("seconds") or 0
            if attempt == 1 or key not in open_runs:
                run = {"passed": False, "attempts": 0, "seconds": 0.0}
                runs_by_key.setdefault(key, []).append(run)
                open_runs[key] = run
            run = open_runs[key]
            run["attempts"] += 1
            run["seconds"] += seconds
            call_run[event.get("call_id")] = run
        elif kind == "outcome":
            run = call_run.get(event.get("call_id"))
            if run is not None and event.get("result") == "passed":
                run["passed"] = True

    summary = {}
    for (model, effort, budget, task), runs in runs_by_key.items():
        task_stats = {
            "runs": len(runs),
            "passed": sum(1 for run in runs if run["passed"]),
            "attempts": sum(run["attempts"] for run in runs),
            "seconds": sum(run["seconds"] for run in runs),
        }
        if budget is not None:
            key = f"{model} effort={effort} budget={budget}"
        else:
            key = f"{model} effort={effort}"
        bucket = summary.setdefault(
            key,
            {"runs": 0, "passed": 0, "attempts": 0, "seconds": 0.0, "tasks": {}},
        )
        bucket["runs"] += len(runs)
        bucket["passed"] += task_stats["passed"]
        bucket["attempts"] += task_stats["attempts"]
        bucket["seconds"] += task_stats["seconds"]
        bucket["tasks"][task] = task_stats

    return summary


def diagnosis_ab(events):
    """Count diagnosis A/B: for each diagnosis event, find the first later call with same task/attempt,
    then the outcome for that call. used=True goes to hinted, used=False to plain.
    Missing call or outcome means the diagnosis is not counted."""
    hinted = {"retries": 0, "passed": 0}
    plain = {"retries": 0, "passed": 0}

    for i, event in enumerate(events):
        if event.get("kind") != "diagnosis":
            continue
        task = event.get("task")
        attempt = event.get("attempt")
        used = event.get("used")
        bucket = hinted if used else plain

        # find first later call with same task and attempt
        found_call = None
        for j in range(i + 1, len(events)):
            ev = events[j]
            if ev.get("kind") == "call" and ev.get("task") == task and ev.get("attempt") == attempt:
                found_call = ev
                break

        if found_call is None:
            continue

        call_id = found_call.get("call_id")

        # find outcome with same call_id
        found_outcome = None
        for j in range(i + 1, len(events)):
            ev = events[j]
            if ev.get("kind") == "outcome" and ev.get("call_id") == call_id:
                found_outcome = ev
                break

        if found_outcome is None:
            continue

        bucket["retries"] += 1
        if found_outcome.get("result") == "passed":
            bucket["passed"] += 1

    return {"hinted": hinted, "plain": plain}


_PLAN_DRAFT_STATUSES = (
    "collected",
    "import_error",
    "syntax_error",
    "error",
    "exists",
    "missing",
)


def plans_summary(plans, events):
    edited_by_plan = {}
    drafts_by_plan = {}
    for event in events:
        kind = event.get("kind")
        plan_id = event.get("plan")
        if kind == "plan" and plan_id is not None:
            if event.get("edited"):
                edited_by_plan[plan_id] = True
        elif kind == "test_draft" and plan_id is not None:
            status = event.get("status")
            if status not in _PLAN_DRAFT_STATUSES:
                continue
            drafts_by_plan.setdefault(plan_id, {}).setdefault(status, 0)
            drafts_by_plan[plan_id][status] += 1

    result = []
    for plan in plans:
        plan_id = plan.get("id")
        drafts = {status: 0 for status in _PLAN_DRAFT_STATUSES}
        for status, count in drafts_by_plan.get(plan_id, {}).items():
            drafts[status] = count
        result.append({
            "id": plan_id,
            "tasks_count": len(plan.get("tasks", [])),
            "status": plan.get("status"),
            "edited": bool(edited_by_plan.get(plan_id, False)),
            "drafts": drafts,
        })
    return result


WASTE_CAUSES = ("tests_failed", "cut_off", "no_files", "dropped_defs", "other_failure", "discarded")


def efficiency(events):
    # Build call index: call_id -> event
    call_by_id = {}
    for event in events:
        if event.get("kind") == "call":
            call_by_id[event["call_id"]] = event

    # Build outcome index: call_id -> first outcome event
    outcome_by_call = {}
    for event in events:
        if event.get("kind") == "outcome":
            cid = event["call_id"]
            if cid not in outcome_by_call:
                outcome_by_call[cid] = event

    # For each task, the index of its last reset_by_human verdict
    reset_index = {}
    for i, event in enumerate(events):
        if event.get("kind") == "verdict" and event.get("result") == "reset_by_human":
            task = event.get("task")
            reset_index[task] = i

    # Assign cause to each call
    by_cause = {}
    all_completion_tokens = 0
    model_seconds = 0.0
    switch_seconds = 0.0

    for i, event in enumerate(events):
        kind = event.get("kind")
        if kind == "call":
            c = event.get("completion_tokens") or 0
            s = event.get("seconds") or 0
            all_completion_tokens += c
            model_seconds += s

            cid = event["call_id"]
            outcome = outcome_by_call.get(cid)
            task = event.get("task")

            if outcome is None:
                cause = "support"
            else:
                result = outcome.get("result")
                if result == "passed":
                    if task in reset_index and reset_index[task] > i:
                        cause = "discarded"
                    else:
                        cause = "useful"
                elif result in ("review_approve", "review_changes"):
                    cause = "review"
                elif result == "failed":
                    cause = "tests_failed"
                elif result == "no_files":
                    if event.get("finish") == "length":
                        cause = "cut_off"
                    else:
                        cause = "no_files"
                elif result == "dropped_defs":
                    cause = "dropped_defs"
                else:
                    cause = "other_failure"

            bucket = by_cause.setdefault(cause, {"calls": 0, "completion_tokens": 0, "seconds": 0.0})
            bucket["calls"] += 1
            bucket["completion_tokens"] += c
            bucket["seconds"] += s

        elif kind == "switch":
            switch_seconds += event.get("seconds") or 0

    # waste
    waste_tokens = 0
    waste_seconds = 0.0
    for cause in WASTE_CAUSES:
        if cause in by_cause:
            waste_tokens += by_cause[cause]["completion_tokens"]
            waste_seconds += by_cause[cause]["seconds"]

    if all_completion_tokens > 0:
        share = round(waste_tokens / all_completion_tokens, 3)
    else:
        share = 0.0

    waste = {"completion_tokens": waste_tokens, "seconds": round(waste_seconds, 1), "share": share}

    # time: active seconds from sessions
    ts_values = sorted(e["ts"] for e in events if "ts" in e)
    active_seconds = 0.0
    if ts_values:
        session_start = ts_values[0]
        prev = ts_values[0]
        for ts in ts_values[1:]:
            if ts - prev > 600:
                active_seconds += prev - session_start
                session_start = ts
            prev = ts
        active_seconds += prev - session_start

    model_seconds = round(model_seconds, 1)
    switch_seconds = round(switch_seconds, 1)
    active_seconds = round(active_seconds, 1)

    step_seconds = {}
    for event in events:
        if event.get("kind") == "step":
            step_seconds[event["name"]] = step_seconds.get(event["name"], 0.0) + (event.get("seconds") or 0)
    step_seconds = {name: round(sec, 1) for name, sec in sorted(step_seconds.items())}

    # Build command intervals
    command_starts = {}
    command_events_exist = False
    intervals = []
    for event in events:
        if event.get("kind") == "command":
            command_events_exist = True
            name = event.get("name")
            phase = event.get("phase")
            ts = event.get("ts", 0)
            if phase == "start":
                command_starts.setdefault(name, []).append(ts)
            elif phase == "end":
                stack = command_starts.get(name, [])
                if stack:
                    start_ts = stack.pop()
                    intervals.append((start_ts, ts))

    # Merge intervals
    if intervals:
        intervals.sort()
        merged = []
        for start, end in intervals:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
    else:
        merged = []

    # Compute covered time within sessions
    if not command_events_exist:
        idle_seconds = 0.0
    else:
        # Build sessions
        sessions = []
        if ts_values:
            session_start = ts_values[0]
            prev = ts_values[0]
            for ts in ts_values[1:]:
                if ts - prev > 600:
                    sessions.append((session_start, prev))
                    session_start = ts
                prev = ts
            sessions.append((session_start, prev))

        covered = 0.0
        for sess_start, sess_end in sessions:
            for iv_start, iv_end in merged:
                lo = max(sess_start, iv_start)
                hi = min(sess_end, iv_end)
                if lo < hi:
                    covered += hi - lo

        idle_seconds = round(active_seconds - covered, 1)

    step_sum = sum(step_seconds.values())
    other_seconds = round(max(0, active_seconds - model_seconds - switch_seconds - step_sum - idle_seconds), 1)

    time_info = {
        "model_seconds": model_seconds,
        "switch_seconds": switch_seconds,
        "active_seconds": active_seconds,
        "idle_seconds": idle_seconds,
        "other_seconds": other_seconds,
        "steps": step_seconds,
    }

    # first_try
    coder_calls = []
    for event in events:
        if event.get("kind") == "call" and event.get("role") in ("coder", "coder_hard"):
            cid = event["call_id"]
            outcome = outcome_by_call.get(cid)
            task = event.get("task")
            coder_calls.append((cid, task, event["role"], outcome))

    # Find first coder/coder_hard call per task (by event order)
    first_coder_by_task = {}
    for cid, task, role, outcome in coder_calls:
        if task is not None and task not in first_coder_by_task:
            first_coder_by_task[task] = (cid, role, outcome)

    tasks_count = 0
    passed_count = 0
    by_role = {}

    for task, (cid, role, outcome) in first_coder_by_task.items():
        tasks_count += 1
        is_passed = outcome is not None and outcome.get("result") == "passed"
        if is_passed:
            passed_count += 1
        if role not in by_role:
            by_role[role] = [0, 0]
        by_role[role][1] += 1
        if is_passed:
            by_role[role][0] += 1

    first_try = {"tasks": tasks_count, "passed": passed_count, "by_role": by_role}

    # attempts: mean number of coder/coder_hard outcomes for tasks whose last such outcome is "passed"
    coder_outcomes_by_task = {}
    for cid, task, role, outcome in coder_calls:
        if task is not None:
            coder_outcomes_by_task.setdefault(task, []).append(outcome)

    passed_task_counts = []
    for task, outcome_list in coder_outcomes_by_task.items():
        # last outcome
        last_outcome = outcome_list[-1]
        if last_outcome is not None and last_outcome.get("result") == "passed":
            passed_task_counts.append(len(outcome_list))

    if passed_task_counts:
        attempts = round(sum(passed_task_counts) / len(passed_task_counts), 2)
    else:
        attempts = 0.0

    # cut_off: calls with finish "length"
    cut_off_calls = 0
    cut_off_tokens = 0
    for event in events:
        if event.get("kind") == "call" and event.get("finish") == "length":
            cut_off_calls += 1
            cut_off_tokens += event.get("completion_tokens") or 0

    cut_off = {"calls": cut_off_calls, "completion_tokens": cut_off_tokens}

    # top_tasks: top 5 tasks by completion tokens across all calls
    task_tokens = {}
    task_seconds = {}
    task_calls = {}
    for event in events:
        if event.get("kind") == "call":
            task = event.get("task")
            c = event.get("completion_tokens") or 0
            s = event.get("seconds") or 0
            if task not in task_tokens:
                task_tokens[task] = 0
                task_seconds[task] = 0.0
                task_calls[task] = 0
            task_tokens[task] += c
            task_seconds[task] += s
            task_calls[task] += 1

    top_sorted = sorted(task_tokens.keys(), key=lambda t: task_tokens[t], reverse=True)
    top_tasks = []
    for t in top_sorted[:5]:
        top_tasks.append({
            "task": t,
            "completion_tokens": task_tokens[t],
            "seconds": round(task_seconds[t], 1),
            "calls": task_calls[t],
        })

    return {
        "by_cause": by_cause,
        "waste": waste,
        "time": time_info,
        "first_try": first_try,
        "attempts": attempts,
        "cut_off": cut_off,
        "top_tasks": top_tasks,
    }


def format_efficiency(e):
    lines = ["efficiency:"]
    total_tokens = sum(b["completion_tokens"] for b in e["by_cause"].values())
    w = e["waste"]
    lines.append(f"  generated: {total_tokens} tokens, waste {w['completion_tokens']} ({w['share']*100:.1f}%) in {w['seconds']:.0f} s")
    lines.append("  by cause:")
    sorted_causes = sorted(e["by_cause"].keys(), key=lambda c: e["by_cause"][c]["completion_tokens"], reverse=True)
    for cause in sorted_causes:
        b = e["by_cause"][cause]
        lines.append(f"    {cause}: {b['calls']} calls, {b['completion_tokens']} tokens, {b['seconds']:.0f} s")
    t = e["time"]
    parts = [f"model {t['model_seconds']:.0f} s", f"switches {t['switch_seconds']:.0f} s"]
    if t["steps"]:
        for name, sec in t["steps"].items():
            parts.append(f"{name} {sec:.0f} s")
    if t["idle_seconds"] > 0:
        parts.append(f"idle {t['idle_seconds']:.0f} s")
    parts.append(f"other {t['other_seconds']:.0f} s of {t['active_seconds']:.0f} s active")
    lines.append("  time: " + ", ".join(parts))
    ft = e["first_try"]
    first_try_line = f"  first try: {ft['passed']}/{ft['tasks']} tasks"
    first_try_line += "".join(f", {role} {p}/{n}" for role, (p, n) in sorted(ft["by_role"].items()))
    lines.append(first_try_line)
    lines.append(f"  attempts per passed task: {e['attempts']}")
    co = e["cut_off"]
    lines.append(f"  cut off at the length limit: {co['calls']} calls, {co['completion_tokens']} tokens")
    lines.append("  most expensive tasks:")
    for tt in e["top_tasks"]:
        task_str = tt["task"] if tt["task"] is not None else "-"
        lines.append(f"    {task_str}: {tt['completion_tokens']} tokens, {tt['seconds']:.0f} s, {tt['calls']} calls")
    return lines


def review_quality(events):
    models = {}
    for event in events:
        if event.get("kind") == "call":
            models[event["call_id"]] = event.get("model")

    by_model = {}
    first_order = []
    open_blocks = {}

    def get_model(call_id):
        return models.get(call_id, "?")

    def ensure(model):
        if model not in by_model:
            by_model[model] = {"reviews": 0, "blocks": 0, "overruled": 0}
            first_order.append(model)

    for event in events:
        kind = event.get("kind")
        if kind == "outcome":
            result = event.get("result")
            if result in ("review_approve", "review_changes"):
                model = get_model(event.get("call_id"))
                ensure(model)
                by_model[model]["reviews"] += 1
                task = event.get("task")
                if result == "review_changes":
                    by_model[model]["blocks"] += 1
                    open_blocks.setdefault(task, []).append(model)
                elif result == "review_approve":
                    open_blocks[task] = []
        elif kind == "verdict":
            if event.get("result") == "done_by_human":
                task = event.get("task")
                for model in open_blocks.get(task, []):
                    ensure(model)
                    by_model[model]["overruled"] += 1
                open_blocks[task] = []

    result = {}
    for model in first_order:
        result[model] = by_model[model]
    return result


def format_reviews(q):
    lines = []
    for model in q:
        d = q[model]
        lines.append(f"{model}: {d['reviews']} reviews, {d['blocks']} blocks, {d['overruled']} overruled by a person")
    return lines
