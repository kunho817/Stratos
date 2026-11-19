"""Local model writes a short reference page per code file (memory M4, the LLM wiki)."""

import hashlib
import json
from pathlib import Path

from stratos import codemap, config

SYSTEM = (
    "Write a short reference page for the code file below. Use ONLY facts visible in the code given. "
    "At most 400 words. The page must have exactly these sections, in this order: "
    "## Purpose\n## Data shapes\n## Used by\n## Invariants\n## Traps\n"
    "Use short bullet lines under each heading. Do not add any other headings."
)

MAX_SOURCE = 20000


def page_name(path):
    """Return path with '/' replaced by '__' plus '.md'."""
    return path.replace("/", "__") + ".md"


def used_by(cmap, path):
    """One line per symbol of cmap['files'][path] that has users in other files."""
    lines = []
    for sym in cmap["files"].get(path, []):
        name = sym["name"]
        us = codemap.users(cmap, name)
        others = [u for u in us if not u.startswith(path + ":")]
        if others:
            lines.append(f"- {name}: {', '.join(others)}")
    return "\n".join(lines)


def messages(path, source, used):
    """Build the chat messages for the wiki model."""
    if len(source) > MAX_SOURCE:
        source = source[:MAX_SOURCE] + "\n... (cut)"
    used_text = used if used else "(nothing outside this file)"
    user_content = (
        f"FILE: {path}\n```\n{source}\n```\n\n"
        f"USED BY (from the code map):\n{used_text}"
    )
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_content},
    ]


def clean(answer):
    """Strip the answer; remove surrounding ``` fences if present. Return None if no '## Purpose'."""
    text = answer.strip()
    lines = text.splitlines()
    if lines and lines[0].startswith("```") and lines[-1].startswith("```"):
        text = "\n".join(lines[1:-1]).strip()
    if "## Purpose" not in text:
        return None
    return text


def _code_paths(cmap, only=None):
    """Return the ordered list of code file paths (excluding test files)."""
    test_prefix = cmap["test_dir"] + "/"
    paths = [p for p in cmap["files"] if not p.startswith(test_prefix)]
    if only is not None:
        paths = [p for p in paths if p in only]
    return paths


def _load_index(wiki_dir):
    """Read index.json from wiki_dir, returning {} if missing."""
    idx_path = wiki_dir / "index.json"
    if idx_path.exists():
        return json.loads(idx_path.read_text(encoding="utf-8"))
    return {}


def _save_index(wiki_dir, index):
    """Write index.json (UTF-8 JSON)."""
    (wiki_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")


def _sha(text):
    """Return sha1 hex of text encoded as UTF-8."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def build(gw, root, state_dir, cmap, only=None, log=print):
    """Build wiki pages. Returns {"written", "unchanged", "kept", "failed"}."""
    root = Path(root)
    state_dir = Path(state_dir)
    wiki_dir = state_dir / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    index = _load_index(wiki_dir)

    counts = {"written": 0, "unchanged": 0, "kept": 0, "failed": 0}
    ensure_done = False

    for path in _code_paths(cmap, only):
        source = (root / path).read_text(encoding="utf-8")
        page_path = wiki_dir / page_name(path)

        source_sha = _sha(source)

        if page_path.exists():
            page_text = page_path.read_text(encoding="utf-8")
            page_sha = _sha(page_text)

            if path not in index:
                counts["kept"] += 1
                log(f"wiki: {path}: kept (edited by hand)")
                continue
            if page_sha != index[path]["page"]:
                counts["kept"] += 1
                log(f"wiki: {path}: kept (edited by hand)")
                continue
            if index[path]["source"] == source_sha:
                counts["unchanged"] += 1
                continue

        # need to ask
        if not ensure_done:
            gw.ensure_model(config.WIKI["model"])
            ensure_done = True

        used = used_by(cmap, path)
        msgs = messages(path, source, used)
        kw = {
            "task": "wiki",
            "role": "wiki",
            "attempt": 1,
            "model": config.WIKI["model"],
            "effort": config.WIKI["effort"],
            "max_tokens": config.WIKI["max_tokens"],
        }
        try:
            _, answer = gw.chat(msgs, **kw)
        except Exception:
            counts["failed"] += 1
            log(f"wiki: {path}: failed")
            continue

        cleaned = clean(answer)
        if cleaned is None:
            counts["failed"] += 1
            log(f"wiki: {path}: failed")
            continue

        page_text = f"# {path}\n\n{cleaned}\n"
        page_path.write_text(page_text, encoding="utf-8")
        index[path] = {"source": source_sha, "page": _sha(page_text)}
        _save_index(wiki_dir, index)
        counts["written"] += 1
        log(f"wiki: {path}: written")

    return counts


def chunks(state_dir, cmap):
    """Return wiki chunks for every code path whose page exists."""
    state_dir = Path(state_dir)
    wiki_dir = state_dir / "wiki"
    result = []
    for path in _code_paths(cmap):
        page_path = wiki_dir / page_name(path)
        if not page_path.exists():
            continue
        text = page_path.read_text(encoding="utf-8")
        result.append({
            "id": f"wiki:{path}",
            "kind": "wiki",
            "source": path,
            "title": f"notes: {path}",
            "text": text,
        })
    return result
