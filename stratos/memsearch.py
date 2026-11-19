import math

from stratos import memstore, codemap


def search(store, query, embedder=None, cmap=None, k=10, kinds=None):
    chunks = store.all()
    if kinds is not None:
        chunks = [c for c in chunks if c["kind"] in kinds]
    if not chunks:
        return []

    # Keyword ranking
    query_tokens = memstore.tokenize(query)
    docs_tokens = [memstore.tokenize(c["title"] + " " + c["text"]) for c in chunks]
    scores = memstore.bm25(query_tokens, docs_tokens)
    keyword_rank = {}
    kw_list = [(chunks[i]["id"], scores[i]) for i in range(len(chunks)) if scores[i] > 0]
    kw_list.sort(key=lambda x: (-x[1], x[0]))
    for rank, (cid, _) in enumerate(kw_list, 1):
        keyword_rank[cid] = rank

    # Vector ranking
    vector_rank = {}
    if embedder is not None:
        q = embedder.embed_query(query)
        q_norm = math.sqrt(sum(x * x for x in q))
        vecs = store.vectors(embedder.name)
        vec_list = []
        for cid, v in vecs.items():
            if cid not in {c["id"] for c in chunks}:
                continue
            v_norm = math.sqrt(sum(x * x for x in v))
            if v_norm == 0.0:
                sim = 0.0
            elif q_norm == 0.0:
                sim = 0.0
            else:
                sim = sum(a * b for a, b in zip(q, v)) / (q_norm * v_norm)
            vec_list.append((cid, sim))
        vec_list.sort(key=lambda x: (-x[1], x[0]))
        for rank, (cid, _) in enumerate(vec_list, 1):
            vector_rank[cid] = rank

    # Fusion
    chunk_map = {c["id"]: c for c in chunks}
    fused = {}
    for cid in set(list(keyword_rank.keys()) + list(vector_rank.keys())):
        score = 0.0
        why_parts = []
        if cid in keyword_rank:
            score += 1.0 / (60 + keyword_rank[cid])
            why_parts.append("keyword")
        if cid in vector_rank:
            score += 1.0 / (60 + vector_rank[cid])
            why_parts.append("vector")
        if "keyword" in why_parts and "vector" in why_parts:
            why = "keyword+vector"
        elif "keyword" in why_parts:
            why = "keyword"
        else:
            why = "vector"
        fused[cid] = {"id": cid, "title": chunk_map[cid]["title"], "score": score, "why": why}

    # Sort by score desc, id asc, take top k
    hits = sorted(fused.values(), key=lambda x: (-x["score"], x["id"]))
    hits = hits[:k]

    # Expansion
    if cmap is not None:
        seen_ids = set(h["id"] for h in hits)
        expansion = []
        for hit in hits:
            cid = hit["id"]
            if cid.startswith("code:") or cid.startswith("test:"):
                parts = cid.split(":", 2)
                if len(parts) == 3:
                    kind, path, name = parts
                    code_users = []
                    test_users = []
                    for u in codemap.users(cmap, name, path):
                        candidate = f"code:{u}"
                        if store.get(candidate) is None:
                            candidate = f"test:{u}"
                        if store.get(candidate) is None:
                            continue
                        if kinds is not None and store.get(candidate)["kind"] not in kinds:
                            continue
                        if candidate.startswith("code:"):
                            code_users.append(candidate)
                        else:
                            test_users.append(candidate)
                    for candidate in code_users[:3] + test_users[:2]:
                        if candidate in seen_ids:
                            continue
                        seen_ids.add(candidate)
                        expansion.append({
                            "id": candidate,
                            "title": store.get(candidate)["title"],
                            "score": hit["score"] / 2.0,
                            "why": f"uses {name}",
                        })
        hits.extend(expansion)

    return hits
