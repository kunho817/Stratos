"""Episodes layer for Stratos (memory M3a): past tasks and people's corrections become memory chunks.

- episode(task, events): a single chunk summarising one task's history from its telemetry events.
- reset_lessons(task, events): one chunk per human reset, a lesson for next time.
- history_chunks(tasks, events): every non-todo task's episode followed by its reset lessons.
"""

from stratos import decide


def episode(task, events):
    """Build the episode chunk for one task from its telemetry events."""
    tid = task["id"]
    title = task.get("title", "")
    status = task.get("status", "")
    attempts = task.get("attempts", 0)
    role = task.get("role", "")

    lines = []

    lines.append(f"{tid}: {title} ({status}, {attempts} attempts, role {role})")

    goal = task.get("goal") or ""
    if goal:
        lines.append("Goal: " + goal[:600])

    files = task.get("files") or []
    if files:
        lines.append("Files: " + ", ".join(files))

    # Outcome results, counting keeping the order of first appearance.
    result_counts = {}
    for e in events:
        if e.get("kind") == "outcome":
            r = e.get("result")
            if r is None:
                continue
            result_counts[r] = result_counts.get(r, 0) + 1
    if result_counts:
        parts = ", ".join(f"{r} x{n}" for r, n in result_counts.items())
        lines.append("Results: " + parts)

    # Failing test ids: distinct ids from the "failed" outcomes' details.
    failing = []
    seen = set()
    for e in events:
        if e.get("kind") == "outcome" and e.get("result") == "failed":
            detail = e.get("detail") or ""
            for fid in decide._extract_ids(detail):
                if fid not in seen:
                    seen.add(fid)
                    failing.append(fid)
                if len(failing) >= 8:
                    break
        if len(failing) >= 8:
            break
    if failing:
        lines.append("Failing tests: " + ", ".join(failing[:8]))

    # Review lines, one per "review_changes" outcome.
    review_lines = []
    for e in events:
        if e.get("kind") == "outcome" and e.get("result") == "review_changes":
            detail = e.get("detail") or ""
            if detail:
                review_lines.append("Review: " + detail[:300])
    lines.extend(review_lines)

    # Triage lines, one per "triage" event.
    triage_lines = []
    for e in events:
        if e.get("kind") == "triage":
            verdict = e.get("verdict", "")
            reason = e.get("reason", "")
            triage_lines.append(f"Triage: {verdict} - {reason}")
    lines.extend(triage_lines)

    # Reset lines, one per "reset_by_human" verdict.
    reset_lines = []
    for e in events:
        if e.get("kind") == "verdict" and e.get("result") == "reset_by_human":
            reason = e.get("reason", "")
            reset_lines.append("Reset by a person: " + reason)
    lines.extend(reset_lines)

    return {
        "id": f"episode:{tid}",
        "kind": "episode",
        "source": "tasks.json",
        "title": f"{tid}: {title}",
        "text": "\n".join(line for line in lines if line),
    }


def reset_lessons(task, events):
    """Return one lesson chunk per human reset of this task."""
    tid = task["id"]
    title = task.get("title", "")
    lessons = []
    n = 0
    for e in events:
        if e.get("kind") == "verdict" and e.get("result") == "reset_by_human":
            n += 1
            reason = e.get("reason", "")
            lessons.append({
                "id": f"lesson:reset:{tid}:{n}",
                "kind": "lesson",
                "source": "tasks.json",
                "title": f"{tid}: {title}",
                "text": f"{tid} {title}: {reason}",
            })
    return lessons


def history_chunks(tasks, events):
    """Return every non-todo task's episode then its reset lessons, in task order."""
    chunks = []
    for task in tasks:
        if task.get("status") == "todo":
            continue
        tid = task["id"]
        evs = [e for e in events if e.get("task") == tid]
        chunks.append(episode(task, evs))
        chunks.extend(reset_lessons(task, evs))
    return chunks
