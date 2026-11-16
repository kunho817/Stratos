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
