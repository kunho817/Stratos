"""Second-model plan review: a model reviews a plan before tests are drafted."""

import re
from pathlib import Path

from stratos import config

SYSTEM = (
    "You review a plan that splits a feature into coding tasks, before any test or code is written. "
    "Find concrete problems that would make a task fail or the feature wrong: "
    "a file the feature needs that no task writes; "
    "a task that uses a function or data another task writes without that task in its After; "
    "data passed between tasks (arguments, return values, file formats) whose shape no goal defines, "
    "or that two goals describe differently; "
    "a parameter or name that makes no sense for this project; "
    "a module the conventions say is pure that prints or reads files; "
    "a rule of the feature goal no task covers; "
    "an input the feature allows that would crash (zero, empty, missing). "
    "Do not suggest style changes or extra features.\n"
    "Answer with one line per problem, exactly:\n"
    "PROBLEM: <task key> | <one sentence>\n"
    "and nothing else."
)


def plan_text(tasks):
    blocks = []
    for t in tasks:
        after = t.get("after") or []
        after_str = ", ".join(after) if after else "none"
        block = (
            f"Key: {t['key']}\n"
            f"Title: {t['title']}\n"
            f"Files: {', '.join(t['files'])}\n"
            f"Tests: {', '.join(t['tests'])}\n"
            f"After: {after_str}\n"
            f"Goal: {t['goal']}"
        )
        blocks.append(block)
    return "\n\n".join(blocks)


def build_messages(goal, conventions, tasks):
    user = "FEATURE GOAL:\n" + goal + "\n\n"
    if conventions:
        user += "PROJECT CONVENTIONS:\n" + conventions + "\n\n"
    user += "PLAN:\n" + plan_text(tasks)
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def parse(answer):
    results = []
    seen = set()
    for m in re.finditer(r"^\s*PROBLEM:\s*(.+?)\s*\|\s*(.+)$", answer or "", re.M):
        task = m.group(1).strip()
        problem = m.group(2).strip()
        entry = (task, problem)
        if entry not in seen:
            seen.add(entry)
            results.append({"task": task, "problem": problem})
    return results


def critique(gw, goal, root, tasks):
    conventions_path = Path(root, "CONVENTIONS.md")
    conventions = conventions_path.read_text(encoding="utf-8") if conventions_path.exists() else None
    cfg = config.PLAN_CRITIC
    gw.ensure_model(cfg["model"])
    _, answer = gw.chat(
        build_messages(goal, conventions, tasks),
        task="plan",
        role="plan_critic",
        attempt=1,
        model=cfg["model"],
        effort=cfg["effort"],
        max_tokens=cfg["max_tokens"],
    )
    return parse(answer)
