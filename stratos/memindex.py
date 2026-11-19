from pathlib import Path

import stratos.codemap as codemap
import stratos.episodes as episodes


def index_history(store, tasks, events):
    chunks = episodes.history_chunks(tasks, events)

    changed = 0
    for chunk in chunks:
        if store.upsert(chunk):
            changed += 1

    episode_ids = [c["id"] for c in chunks if c["kind"] == "episode"]
    lesson_ids = [c["id"] for c in chunks if c["kind"] == "lesson"]

    removed = store.remove_except("episode", episode_ids) + store.remove_except("lesson", lesson_ids)

    return {"chunks": len(chunks), "changed": changed, "removed": removed}


def index_project(root, store, embedder=None, settings=None):
    root = Path(root)
    cmap = codemap.build(root, settings)

    chunks = []

    for path, symbols in cmap["files"].items():
        file_text = (root / path).read_text(encoding="utf-8")
        kind = "test" if path.startswith(cmap["test_dir"] + "/") else "code"
        for sym in symbols:
            cid = f"{kind}:{path}:{sym['name']}"
            text = f"{path}\n{sym['signature']}\n" + codemap.symbol_text(file_text, sym)
            chunks.append({
                "id": cid,
                "kind": kind,
                "source": path,
                "title": f"{path}:{sym['name']}",
                "text": text,
            })

    conv_path = root / "CONVENTIONS.md"
    if conv_path.exists():
        conv_text = conv_path.read_text(encoding="utf-8")
        lines = conv_text.splitlines()
        sections = []
        current = []
        for line in lines:
            if line.startswith("## "):
                sections.append(current)
                current = [line]
            else:
                current.append(line)
        sections.append(current)

        for n, section_lines in enumerate(sections):
            section_text = "\n".join(section_lines).strip()
            if n == 0:
                if not section_text:
                    continue
                title = "CONVENTIONS.md"
            else:
                title = section_lines[0][3:].strip()
            cid = f"doc:CONVENTIONS.md:{n}"
            chunks.append({
                "id": cid,
                "kind": "doc",
                "source": "CONVENTIONS.md",
                "title": title,
                "text": section_text,
            })

    changed = 0
    for chunk in chunks:
        if store.upsert(chunk):
            changed += 1

    ids_by_kind = {"code": [], "test": [], "doc": []}
    for chunk in chunks:
        ids_by_kind[chunk["kind"]].append(chunk["id"])

    removed = 0
    for kind in ("code", "test", "doc"):
        removed += store.remove_except(kind, ids_by_kind[kind])

    embedded = 0
    if embedder is not None:
        stale_ids = store.stale(embedder.name)
        embedded = len(stale_ids)
        for i in range(0, len(stale_ids), 32):
            batch = stale_ids[i:i + 32]
            texts = [store.get(cid)["text"] for cid in batch]   # stale chunks may come from index_history too
            vectors = embedder.embed(texts)
            for cid, vec in zip(batch, vectors):
                h = store.get(cid)["hash"]
                store.set_vector(cid, embedder.name, h, vec)

    return {"chunks": len(chunks), "changed": changed, "removed": removed, "embedded": embedded}
