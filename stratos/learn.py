"""Local model turns people's corrections into general lessons (memory layer M3b)."""

import json
import math
from pathlib import Path

from stratos import config, lessons, memstore

SYSTEM = (
    "A person corrected a task a coding model did. Write ONE general lesson that would help "
    "future tasks in other projects avoid the same problem, as a single line "
    "\"- [tag, tag] lesson\" (tags short lowercase words such as plan, tests, code, data-flow), "
    "no source in parentheses; if the correction teaches nothing general (a typo of the person, "
    "a one-off), answer the word NONE. "
    "The lesson has at most 25 words and names one concrete action (what to do next time, not what went wrong)."
)

MAX_WORDS = 30
SIMILAR = 0.72


def corrections(tasks, events):
    """For each task in order, for each of its reset_by_human verdict events (n=1,2,...), produce a correction dict."""
    out = []
    for task in tasks:
        n = 0
        for ev in events:
            if ev.get("kind") == "verdict" and ev.get("task") == task["id"] and ev.get("result") == "reset_by_human":
                n += 1
                goal = task["goal"][:800]
                out.append({
                    "id": f"reset:{task['id']}:{n}",
                    "text": f"Task {task['id']}: {task['title']}\nGoal: {goal}\nA person reset this task and said: {ev['reason']}",
                })
    return out


def _fmt(t):
    parts = []
    for field in ("title", "goal", "files", "tests", "after"):
        val = t[field]
        if isinstance(val, list):
            parts.append(f"{field}: {', '.join(val)}")
        else:
            parts.append(f"{field}: {val}")
    return "\n".join(parts)


def plan_corrections(state_dir):
    state_dir = Path(state_dir)
    plans_dir = state_dir / "plans"
    if not plans_dir.is_dir():
        return []
    out = []
    for f in sorted(plans_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        if data.get("status") != "added":
            continue
        if "original" not in data:
            continue
        pid = data["id"]
        goal = data["goal"][:400]
        head = f"Plan {pid} for the goal: {goal}\n"
        orig_list = data["original"]
        now_list = data["tasks"]
        orig_map = {t["key"]: t for t in orig_list}
        now_map = {t["key"]: t for t in now_list}
        orig_keys = [t["key"] for t in orig_list]
        now_keys = [t["key"] for t in now_list]
        for key in orig_keys:
            if key in orig_map and key in now_map:
                if orig_map[key] != now_map[key]:
                    out.append({
                        "id": f"plan:{pid}:{key}",
                        "text": head + "The planner wrote:\n" + _fmt(orig_map[key]) + "\nA person changed it to:\n" + _fmt(now_map[key]),
                    })
            elif key in orig_map and key not in now_map:
                out.append({
                    "id": f"plan:{pid}:{key}",
                    "text": head + "The planner wrote:\n" + _fmt(orig_map[key]) + "\nA person removed this task.",
                })
        for key in now_keys:
            if key in now_map and key not in orig_map:
                out.append({
                    "id": f"plan:{pid}:{key}",
                    "text": head + "The planner did not plan this task; a person added:\n" + _fmt(now_map[key]),
                })
    return out


def messages(correction, existing):
    """Build the chat messages for the learner model."""
    user = "CORRECTION:\n" + correction["text"] + "\n\nLESSONS WE ALREADY HAVE (do not repeat them):\n" + "\n".join(existing)
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def ask(gw, correction, existing):
    """Ask the learner model; return (tags, text) or None."""
    learner = config.LEARNER
    gw.ensure_model(learner["model"])
    msgs = messages(correction, existing)
    _, answer = gw.chat(msgs, task="learn", role="learner", attempt=1,
                        model=learner["model"], effort=learner["effort"], max_tokens=learner["max_tokens"])
    for line in answer.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ["):
            parsed = lessons.parse(stripped)
            if parsed:
                text = parsed[0]["text"]
                if len(text.split()) > MAX_WORDS:
                    return None
                return (parsed[0]["tags"], text)
    return None


def is_duplicate(text, existing_texts, threshold=0.6):
    """True when Jaccard overlap of token sets >= threshold with any existing text."""
    tokens_text = set(memstore.tokenize(text))
    for et in existing_texts:
        tokens_existing = set(memstore.tokenize(et))
        if not tokens_text and not tokens_existing:
            continue
        union = tokens_text | tokens_existing
        if not union:
            continue
        intersection = tokens_text & tokens_existing
        if len(intersection) / len(union) >= threshold:
            return True
    return False


def _cosine(v1, v2):
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(a * a for a in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


def learn(gw, tasks, events, lessons_path, state_dir, project, embedder=None):
    """Process corrections into lessons. Returns counts dict."""
    lessons_path = Path(lessons_path)
    state_dir = Path(state_dir)

    lessons_path.parent.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    learned_path = state_dir / "learned.json"
    if learned_path.exists():
        learned = json.loads(learned_path.read_text(encoding="utf-8"))
    else:
        learned = []

    all_corrections = corrections(tasks, events) + plan_corrections(state_dir)
    todo = [c for c in all_corrections if c["id"] not in learned]

    corrections_count = len(todo)
    added = 0
    duplicates = 0
    skipped = 0

    # read existing lesson lines from the file
    if lessons_path.exists():
        file_text = lessons_path.read_text(encoding="utf-8")
    else:
        file_text = ""

    existing_lines = [l for l in file_text.splitlines() if l.strip().startswith("- [")]
    existing_texts = [l["text"] for l in lessons.parse(file_text)]

    vectors = []
    if embedder is not None:
        if existing_texts:
            vectors = embedder.embed(existing_texts)

    for c in todo:
        result = ask(gw, c, existing_lines)
        if result is None:
            skipped += 1
            learned.append(c["id"])
            continue
        tags, text = result
        if is_duplicate(text, existing_texts):
            duplicates += 1
            learned.append(c["id"])
            continue
        v = None
        if embedder is not None:
            v = embedder.embed([text])[0]
            if any(_cosine(v, ev) >= SIMILAR for ev in vectors):
                duplicates += 1
                learned.append(c["id"])
                continue
        # append the line
        new_line = f"- [{', '.join(tags)}] {text} ({project}: {c['id']})"
        if file_text and not file_text.endswith("\n"):
            file_text += "\n"
        file_text += new_line + "\n"
        lessons_path.write_text(file_text, encoding="utf-8")
        existing_lines.append(new_line)
        existing_texts.append(text)
        if v is not None:
            vectors.append(v)
        added += 1
        learned.append(c["id"])

    learned_path.write_text(json.dumps(learned), encoding="utf-8")

    return {"corrections": corrections_count, "added": added, "duplicates": duplicates, "skipped": skipped}
