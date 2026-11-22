"""run-all learns lessons and updates the wiki after its passes."""

import json
from pathlib import Path

from stratos import codemap, config, embed, learn, steps, wiki
from stratos.telemetry import Telemetry


def pending(tasks, events, state_dir, repo):
    """Ids of corrections not learned yet, in order: task resets, plan edits, draft notes."""
    all_corrections = learn.corrections(tasks, events) + learn.plan_corrections(state_dir) + learn.draft_corrections(repo)
    learned_path = Path(state_dir) / "learned.json"
    if learned_path.exists():
        learned = json.loads(learned_path.read_text(encoding="utf-8"))
    else:
        learned = []
    return [c["id"] for c in all_corrections if c["id"] not in learned]


def after_run(gw, store, finished, log=print, refresh=lambda: None):
    with steps.timed("upkeep"):
        try:
            tasks = store.tasks()
            events = Telemetry(config.STATE_DIR / "telemetry.jsonl").load()
            ran = False
            if config.AUTO_LEARN:
                todo = pending(tasks, events, config.STATE_DIR, config.REPO)
                if todo:
                    r = learn.learn(gw, tasks, events, config.LESSONS, config.STATE_DIR,
                                    config.REPO.name, embedder=embed.Embedder(), repo=config.REPO)
                    log(f"memory learn: {r['added']} lessons from {len(todo)} corrections")
                    ran = True
            if config.AUTO_WIKI and finished:
                c = wiki.build(gw, config.REPO, config.STATE_DIR, codemap.build(config.REPO))
                log(f"wiki: {c['written']} written, {c['unchanged']} unchanged")
                ran = True
            if ran:
                refresh()
        except Exception as e:
            log(f"upkeep: {e}")
