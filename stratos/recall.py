from stratos import memsearch

SECTIONS = [
    ("code", "RELEVANT CODE", 6),
    ("test", "RELEVANT TESTS", 4),
    ("doc", "PROJECT CONVENTIONS", 3),
    ("episode", "PAST TASKS", 3),
    ("lesson", "LESSONS FROM PEOPLE'S CORRECTIONS", 5),
]


def pack(store, query, embedder=None, cmap=None, budget=12000, sections=None):
    if sections is None:
        sections = SECTIONS

    finished_sections = []

    for kind, heading, n in sections:
        hits = memsearch.search(store, query, embedder, cmap, k=n, kinds={kind})
        if not hits:
            continue

        current_section_text = None

        for h in hits:
            chunk = store.get(h["id"])
            text = chunk["text"]
            if len(text) > 1500:
                text = text[:1500] + "\n..."
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
