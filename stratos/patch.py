"""Turn a model's answer into file writes.

The model answers with whole files:

    FILE: stratos/report.py
    ```python
    ...the entire file...
    ```

Whole files are easier for small models than diffs. Paths are checked: relative, inside the work tree, an allowed
suffix, one of the task's files when the task lists them, and never a protected file (a model must not rewrite the
tests it is judged by).

A file's content may itself hold ``` fences or a "FILE:" line (Stratos's own prompts do), so a block ends at the
last bare ``` line before the next header, and with `allowed` given only a header naming one of those files counts
(T006's first run, 2026-11-16, cut review.py at a ``` inside a string).
"""
import re
from pathlib import Path, PurePosixPath

from . import config

HEADER_RE = re.compile(r"^\s*FILE:\s*`?([^\s`]+)`?\s*$")


class PatchRefused(Exception):
    pass


def _norm(path):
    return str(PurePosixPath(path.strip().replace("\\", "/")))


def _header_inside_fence(lines, ok):
    """Move a header written as the first line inside a fence (```python / FILE: x.py) in front of the fence:
    Flint wrote T012's files that way."""
    out = list(lines)
    for i in range(len(out) - 1):
        m = HEADER_RE.match(out[i + 1])
        if out[i].lstrip().startswith("```") and out[i].strip() != "```" and m and (ok is None or _norm(m.group(1)) in ok):
            out[i], out[i + 1] = out[i + 1], out[i]
    return out


def parse_files(text, allowed=None):
    """[(path, content)] for every FILE block. allowed: if given, only headers naming one of these paths count."""
    ok = {_norm(a) for a in allowed} if allowed is not None else None
    lines = _header_inside_fence((text or "").splitlines(keepends=True), ok)
    heads = []
    for i, line in enumerate(lines):
        m = HEADER_RE.match(line)
        if m and (ok is None or _norm(m.group(1)) in ok):
            heads.append((i, m.group(1).strip()))
    out = []
    for k, (i, path) in enumerate(heads):
        seg = lines[i + 1: heads[k + 1][0] if k + 1 < len(heads) else len(lines)]
        j = 0
        while j < len(seg) and not seg[j].strip():
            j += 1
        if j == len(seg) or not seg[j].lstrip().startswith("```"):
            continue
        close = max((c for c in range(j + 1, len(seg)) if seg[c].strip() == "```"), default=None)
        if close is None:
            continue
        out.append((path, "".join(seg[j + 1:close])))
    return out


def check_path(path, protected, allowed=None):
    p = PurePosixPath(path.replace("\\", "/"))
    if p.is_absolute() or ":" in path or ".." in p.parts or not p.parts:
        raise PatchRefused(f"path outside the project: {path}")
    if p.suffix not in config.WRITABLE_SUFFIXES:
        raise PatchRefused(f"file type not allowed: {path}")
    if str(p) in {_norm(x) for x in protected}:
        raise PatchRefused(f"protected file: {path}")
    if allowed is not None and str(p) not in {_norm(x) for x in allowed}:
        raise PatchRefused(f"not one of the task's files: {path}")
    return p


def apply_files(root, files, protected, allowed=None):
    """Check every path first, then write; nothing is written when one path is refused."""
    checked = [(check_path(path, protected, allowed), body) for path, body in files]
    written = []
    for p, body in checked:
        dest = Path(root, *p.parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
        written.append(str(p))
    return written
