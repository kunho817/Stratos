"""Scheduler for task T003: order tasks so the model changes as rarely as possible."""


def plan(tasks, roles, current_model):
    """Return (order, blocked) for the 'todo' tasks.

    order: ids of todo tasks in run order, greedily preferring the current model.
    blocked: ids of todo tasks that can never run, sorted.
    """
    by_id = {t["id"]: t for t in tasks}

    def model_of(task):
        role = task.get("role", "coder")
        return roles[role]["model"]

    todo = {t["id"]: t for t in tasks if t["status"] == "todo"}
    done = {t["id"] for t in tasks if t["status"] == "done"}

    placed = set()
    order = []
    model = current_model

    while True:
        ready = [tid for tid, t in todo.items()
                 if tid not in placed and all(a in done or a in placed for a in t.get("after", []))]
        if not ready:
            break

        same_model = [tid for tid in ready if model_of(todo[tid]) == model]
        if same_model:
            chosen = min(same_model)
        else:
            chosen = min(ready)

        placed.add(chosen)
        order.append(chosen)
        model = model_of(todo[chosen])

    blocked = sorted(tid for tid in todo if tid not in placed)
    return order, blocked


def switches(order, tasks, roles, current_model):
    """Count model changes running order from current_model (None -> model counts as a change)."""
    by_id = {t["id"]: t for t in tasks}

    def model_of(task):
        role = task.get("role", "coder")
        return roles[role]["model"]

    count = 0
    model = current_model
    for tid in order:
        new_model = model_of(by_id[tid])
        if new_model != model:
            count += 1
            model = new_model
    return count
