"""Shared lessons parser (memory layer M3b).

LESSONS.md holds general lessons learned from corrections people made to plans, test drafts and tasks, shared by
every project Stratos works on. parse(text) turns each lesson line into a dict; chunks(text) turns those into the
"guide" chunks the memory indexes so the planner, test writer and coders see the ones that match their task.
"""

import hashlib


def parse(text):
    """Parse LESSONS.md text into a list of {"tags", "text", "source"} dicts, one per lesson line.

    A lesson line starts with "- [": tags are the comma-separated words inside the first [...], stripped; the rest of
    the line, stripped, is the lesson; when it ends with ")" and holds " (", source is the text inside the last
    " (...)" and the lesson text is what comes before it, stripped; else source is "". Other lines are left out.
    """
    lessons = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("- ["):
            continue
        close = line.index("]")
        tags = [t.strip() for t in line[3:close].split(",") if t.strip()]
        rest = line[close + 1:].strip()
        source = ""
        if rest.endswith(")") and " (" in rest:
            i = rest.rfind(" (")
            source = rest[i + 2:-1].strip()
            rest = rest[:i].strip()
        lessons.append({"tags": tags, "text": rest, "source": source})
    return lessons


def chunks(text):
    """Turn LESSONS.md text into "guide" chunks, one per parsed lesson."""
    chunks = []
    for lesson in parse(text):
        text_ = lesson["text"]
        tags = lesson["tags"]
        chunks.append({
            "id": "guide:" + hashlib.sha1(text_.encode("utf-8")).hexdigest()[:12],
            "kind": "guide",
            "source": "LESSONS.md",
            "title": ", ".join(tags),
            "text": f"[{', '.join(tags)}] {text_}",
        })
    return chunks
