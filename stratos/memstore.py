import array
import hashlib
import math
import re
import sqlite3
from pathlib import Path


def stem(token):
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text):
    tokens = []
    for word in re.findall(r"[A-Za-z0-9_$]+", text):
        tokens.append(stem(word.lower()))
        parts = []
        for piece in re.split(r"[_$]", word):
            sub = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", piece)
            parts.extend(sub)
        if len(parts) > 1:
            tokens.extend(stem(p.lower()) for p in parts)
    return tokens


def bm25(query_tokens, docs_tokens, k1=1.5, b=0.75):
    N = len(docs_tokens)
    if N == 0:
        return []
    avgdl = sum(len(d) for d in docs_tokens) / N
    distinct_terms = set(query_tokens)
    scores = [0.0] * N
    for term in distinct_terms:
        n = sum(1 for d in docs_tokens if term in d)
        if n == 0:
            continue
        idf = math.log(1 + (N - n + 0.5) / (n + 0.5))
        for i, d in enumerate(docs_tokens):
            f = d.count(term)
            if f == 0:
                continue
            dl = len(d)
            denom = f + k1 * (1 - b + b * dl / avgdl)
            scores[i] += idf * f * (k1 + 1) / denom
    return scores


class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS chunks("
            "id TEXT PRIMARY KEY, kind TEXT, source TEXT, title TEXT, text TEXT, hash TEXT)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS vectors("
            "id TEXT PRIMARY KEY, model TEXT, hash TEXT, vec BLOB)"
        )
        self.conn.commit()

    def upsert(self, chunk):
        h = hashlib.sha256(chunk["text"].encode()).hexdigest()
        row = self.conn.execute(
            "SELECT hash FROM chunks WHERE id = ?", (chunk["id"],)
        ).fetchone()
        if row is not None and row[0] == h:
            return False
        self.conn.execute(
            "INSERT OR REPLACE INTO chunks(id, kind, source, title, text, hash) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (chunk["id"], chunk["kind"], chunk["source"], chunk["title"], chunk["text"], h),
        )
        self.conn.commit()
        return True

    def get(self, id):
        row = self.conn.execute(
            "SELECT id, kind, source, title, text, hash FROM chunks WHERE id = ?", (id,)
        ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "kind": row[1], "source": row[2], "title": row[3], "text": row[4], "hash": row[5]}

    def all(self, kind=None):
        if kind is not None:
            rows = self.conn.execute(
                "SELECT id, kind, source, title, text, hash FROM chunks WHERE kind = ? ORDER BY id",
                (kind,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, kind, source, title, text, hash FROM chunks ORDER BY id"
            ).fetchall()
        return [
            {"id": r[0], "kind": r[1], "source": r[2], "title": r[3], "text": r[4], "hash": r[5]}
            for r in rows
        ]

    def remove_except(self, kind, keep_ids):
        placeholders = ",".join("?" for _ in keep_ids)
        # Find chunks to remove
        rows = self.conn.execute(
            "SELECT id FROM chunks WHERE kind = ? AND id NOT IN (%s)" % placeholders,
            (kind,) + tuple(keep_ids),
        ).fetchall()
        to_remove = [r[0] for r in rows]
        if not to_remove:
            return 0
        for cid in to_remove:
            self.conn.execute("DELETE FROM vectors WHERE id = ?", (cid,))
        self.conn.execute(
            "DELETE FROM chunks WHERE kind = ? AND id NOT IN (%s)" % placeholders,
            (kind,) + tuple(keep_ids),
        )
        self.conn.commit()
        return len(to_remove)

    def set_vector(self, id, model, hash, vec):
        blob = array.array("f", vec).tobytes()
        self.conn.execute(
            "INSERT OR REPLACE INTO vectors(id, model, hash, vec) VALUES(?, ?, ?, ?)",
            (id, model, hash, blob),
        )
        self.conn.commit()

    def vectors(self, model):
        rows = self.conn.execute(
            "SELECT v.id, v.vec FROM vectors v JOIN chunks c ON c.id = v.id "
            "WHERE v.model = ? AND v.hash = c.hash",
            (model,),
        ).fetchall()
        result = {}
        for r in rows:
            a = array.array("f")
            a.frombytes(r[1])
            result[r[0]] = list(a)
        return result

    def stale(self, model):
        chunks = self.conn.execute(
            "SELECT id, hash FROM chunks ORDER BY id"
        ).fetchall()
        stale_ids = []
        for cid, chash in chunks:
            vrow = self.conn.execute(
                "SELECT hash FROM vectors WHERE id = ? AND model = ?", (cid, model)
            ).fetchone()
            if vrow is None or vrow[0] != chash:
                stale_ids.append(cid)
        return stale_ids

    def close(self):
        self.conn.close()
