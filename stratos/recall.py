from stratos import memsearch

CUT = {"code": 1000, "test": 800, "wiki": 2000}

SECTIONS = [
    ("guide", "GENERAL LESSONS (from earlier projects)", 4),
    ("lesson", "LESSONS FROM PEOPLE'S CORRECTIONS", 5),
    ("wiki", "MODULE NOTES (written by a model from the code; check the code)", 3),
    ("episode", "PAST TASKS", 3),
    ("doc", "PROJECT CONVENTIONS", 3),
    ("code", "RELEVANT CODE", 6),
    ("test", "RELEVANT TESTS", 4),
]


def pack(store, query, embedder=None, cmap=None, budget=12000, sections=None, always_tags=None):
    if sections is None:
        sections = SECTIONS

    finished_sections = []

    if always_tags:
        heading = "GENERAL LESSONS (from earlier projects)"
        lines = []
        for chunk in store.all("guide"):
            tags = set(chunk["title"].split(", "))
            if tags & always_tags:
                line = f"- {chunk['text']}"
                new_lines = lines + [line]
                section_text = heading + ":\n" + "\n".join(new_lines)
                total = section_text
                if finished_sections:
                    total = "\n\n".join([section_text] + finished_sections)
                if len(total) <= budget:
                    lines = new_lines

        if lines:
            section_text = heading + ":\n" + "\n".join(lines)
            finished_sections.append(section_text)

    for kind, heading, n in sections:
        if always_tags and kind == "guide":
            continue

        hits = memsearch.search(store, query, embedder, cmap, k=n, kinds={kind})
        if not hits:
            continue

        current_section_text = None

        for h in hits:
            chunk = store.get(h["id"])
            text = chunk["text"]
            limit = CUT.get(kind, 1500)
            if len(text) > limit:
                text = text[:limit] + "\n..."
            entry = f"--- {h['title']} ({h['why']})\n{text}"

            if current_section_text is None:
                new_section = f"{heading}:\n{entry}"
            else:
                new_section = current_section_text + "\n\n" + entry

            if finished_sections:
                total = "\n\n".join(finished_sections) + "\n\n" + new_section
            else:
                total = new_section

            if len(total) <= budget:
                current_section_text = new_section

        if current_section_text is not None:
            finished_sections.append(current_section_text)

    return "\n\n".join(finished_sections)

