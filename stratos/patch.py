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
(T006's first run, 2026-11-16, cut review.py at a ``` inside a string). When the only allowed file is Python and
holds such fences or headers, T025's fallback saves it from the first fence to the last bare ```.
"""
import ast
import re
from pathlib import Path, PurePosixPath

from . import config

HEADER_RE = re.compile(r"^\s*FILE:\s*`?([^\s`]+)`?\s*$")
REMOVAL_WORDS = ("remove", "delete", "drop", "rename", "replace", "삭제", "제거")


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


def _lone_block(lines, allowed):
    """T022: a lone code block belongs to the only allowed file, when nothing else is possible."""
    if allowed is None or len(allowed) != 1:
        return None
    if any(HEADER_RE.match(line) for line in lines):
        return None
    fences = [i for i, line in enumerate(lines) if line.lstrip().startswith("```")]
    if len(fences) != 2 or lines[fences[1]].strip() != "```":
        return None
    return [(_norm(allowed[0]), "".join(lines[fences[0] + 1:fences[1]]))]


def _python_block(lines, allowed):
    """T025: the lone allowed file is Python and holds ``` fences or "FILE:" lines, so the block runs from the
    first fence line to the last bare ``` line, when it parses as Python."""
    if allowed is None or len(allowed) != 1:
        return None
    path = allowed[0]
    if not path.endswith(".py"):
        return None
    openers = [i for i, line in enumerate(lines) if line.lstrip().startswith("```")]
    if not openers:
        return None
    i = openers[0]
    closers = [j for j in range(i + 1, len(lines)) if lines[j].strip() == "```"]
    if not closers:
        return None
    j = closers[-1]
    content = "".join(lines[i + 1:j])
    try:
        ast.parse(content)
    except (SyntaxError, ValueError):
        return None
    if any(HEADER_RE.match(line) and _norm(HEADER_RE.match(line).group(1)) == _norm(path) for line in lines):
        return None
    return [(_norm(path), content)]


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
        # A header alone in its own fence (```python / FILE: x / ```) leaves an empty block here after
        # _header_inside_fence: skip it when the file's own block follows (Tiel, T075/T076, 2026-11-18)
        while j + 1 < len(seg) and seg[j + 1].strip() == "```":
            n = j + 2
            while n < len(seg) and not seg[n].strip():
                n += 1
            if n < len(seg) and seg[n].lstrip().startswith("```") and seg[n].strip() != "```":
                j = n
            else:
                break
        close =max((c for c in range(j + 1, len(seg)) if seg[c].strip() == "```"), default=None)
        if close is None:
            continue
        out.append((path, "".join(seg[j + 1:close])))
    if not out:
        lone = _lone_block(lines, allowed)
        if lone is not None:
            return lone
        py = _python_block(lines, allowed)
        if py is not None:
            return py
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
    """Check every path first, then write; nothing is written when one path is refused.
    An empty file is refused too: Tiel once answered only 'FILE: stratos/loop.py' in a fence and loop.py was
    overwritten with nothing (T027, 2026-11-17)."""
    for path, body in files:
        if not body.strip():
            raise PatchRefused(f"empty file content: {path}")
    checked = [(check_path(path, protected, allowed), body) for path, body in files]
    written = []
    for p, body in checked:
        dest = Path(root, *p.parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
        written.append(str(p))
    return written


def _top_level_names(text):
    """The names of the top-level FunctionDef, AsyncFunctionDef and ClassDef nodes of a module."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def _excused(name, goal):
    """T046: a dropped name is excused only when a sentence of the goal asks for its removal."""
    for sentence in re.split(r"[.!?\n]", goal):
        if not re.search(r"\b" + re.escape(name) + r"\b", sentence):
            continue
        for word in REMOVAL_WORDS:
            if word.isascii():
                if re.search(r"\b" + re.escape(word) + r"\b", sentence, re.IGNORECASE):
                    return True
            elif word in sentence:
                return True
    return False


def dropped_definitions(root, files, goal=""):
    """{path: [names]} of top-level defs/classes an answer silently dropped.

    For every path ending in ".py" whose file already exists under root: the top-level function (def, async def)
    and class names in the existing file that are not top-level definitions in the new content, sorted. A name the
    goal mentions as a whole word is left out. Paths with nothing dropped, new files, non-.py files and files where
    either version does not parse are left out."""
    out = {}
    for path, content in files:
        if not path.endswith(".py"):
            continue
        old_path = Path(root) / path
        if not old_path.is_file():
            continue
        try:
            old_text = old_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        old_names = _top_level_names(old_text)
        new_names = _top_level_names(content)
        if old_names is None or new_names is None:
            continue
        dropped = sorted(old_names - new_names)
        if not dropped:
            continue
        dropped = [name for name in dropped if not _excused(name, goal)]
        if dropped:
            out[_norm(path)] = dropped
    return out
