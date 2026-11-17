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

    call_outcomes = {}
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
            if later_task != task or later_role not in ("coder", "coder_hard"):
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
