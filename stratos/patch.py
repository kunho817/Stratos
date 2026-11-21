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
import difflib
import re
from pathlib import Path, PurePosixPath

from . import config

HEADER_RE = re.compile(r"^\s*FILE:\s*`?([^\s`]+)`?\s*$")
REMOVAL_WORDS = ("remove", "delete", "drop", "rename", "replace", "삭제", "제거")

START_RE = re.compile(r"^<{5,9}\s*SEARCH$")
DIVIDER_RE = re.compile(r"^={5,9}$")
END_RE = re.compile(r"^(>{5,9}|={5,9}|<{5,9})\s*REPLACE$")


def _read_blocks(section):
    """[(search, replace)] for the SEARCH/REPLACE blocks in a FILE section, read line by line.

    A block starts at a line that, after strip(), is 5-9 "<" then optional spaces then "SEARCH"; the divider is a
    line that, after strip(), is 5-9 "="; the block ends at a line that, after strip(), is 5-9 of ">", "=" or "<"
    then optional spaces then "REPLACE". search = the lines between start and divider, replace = the lines between
    divider and end, each joined without its last newline. A block with a second divider before its end, or with no
    divider or no end, is not used."""
    lines = section.splitlines()
    out = []
    i = 0
    n = len(lines)
    while i < n:
        if not START_RE.match(lines[i].strip()):
            i += 1
            continue
        start = i
        i += 1
        divider = None
        end = None
        second_divider = False
        while i < n:
            s = lines[i].strip()
            if DIVIDER_RE.match(s):
                if divider is None:
                    divider = i
                else:
                    second_divider = True
            elif END_RE.match(s):
                end = i
                break
            i += 1
        if divider is None or end is None or second_divider:
            continue
        search = "\n".join(lines[start + 1:divider])
        replace = "\n".join(lines[divider + 1:end])
        out.append((search, replace))
        i = end + 1
    return out


class PatchRefused(Exception):
    pass


class EditMismatch(Exception):
    def __init__(self, path, search, found, closest):
        self.path = path
        self.search = search
        self.found = found
        self.closest = closest
        msg = f"{path}: the SEARCH text was found {found} times (it must be found exactly once)"
        if closest:
            msg += f"; the closest line is {closest}"
        super().__init__(msg)


def _norm(path):
    return str(PurePosixPath(path.strip().replace("\\", "/")))


def _header_inside_fence(lines, ok):
    """Move a header written as the first line inside a fence (```python / FILE: x.py) in front of the fence:
    Flint wrote T012's files that way."""
    out = list(lines)
    fences_before = 0   # counted on the original lines: an even count before a bare ``` makes it an opening fence
    for i in range(len(out) - 1):
        is_fence = lines[i].lstrip().startswith("```")
        m = HEADER_RE.match(out[i + 1])
        if is_fence and m and (ok is None or _norm(m.group(1)) in ok):
            if out[i].strip() != "```":
                out[i], out[i + 1] = out[i + 1], out[i]
            elif fences_before % 2 == 0 and i + 2 < len(out) and not out[i + 2].lstrip().startswith("```"):
                # (Claude, 2026-11-21, Lantern) a bare opening fence, the header, then the content with no fence of
                # its own: ``` / FILE: x / content / ```
                out[i], out[i + 1] = out[i + 1], out[i]
        if is_fence:
            fences_before += 1
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
        # ... or never closed at all: ```python / FILE: x / ```python / file (Swift, T090, 2026-11-19)
        if j + 1 < len(seg) and seg[j + 1].lstrip().startswith("```") and seg[j + 1].strip() != "```":
            j += 1
        close =max((c for c in range(j + 1, len(seg)) if seg[c].strip() == "```"), default=None)
        if close is None:
            continue
        # (Claude, 2026-11-21) the next header wrapped in its own fence: "```" / "" / "```" + next FILE - the first
        # fence closes this file, the last one opens the wrapper (Sieve P002 drafts kept a stray fence)
        if k + 1 < len(heads) and all(not s.strip() for s in seg[close + 1:]):
            prev = close - 1
            while prev > j and not seg[prev].strip():
                prev -= 1
            if prev > j and seg[prev].strip() == "```":
                close = prev
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


def parse_edits(text, allowed=None):
    """Find SEARCH/REPLACE blocks in FILE sections. Returns [(path, [(search, replace), ...])] in answer order.
    A path met again appends its blocks to its first entry."""
    ok = {_norm(a) for a in allowed} if allowed is not None else None
    lines = (text or "").splitlines(keepends=True)
    heads = []
    for i, line in enumerate(lines):
        m = HEADER_RE.match(line)
        if m:
            heads.append((i, m.group(1).strip()))
    result = []
    seen = {}
    for k, (i, path) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        section = "".join(lines[i + 1:end])
        if ok is not None and _norm(path) not in ok:
            continue
        blocks = _read_blocks(section)
        if not blocks:
            continue
        norm = _norm(path)
        if norm in seen:
            result[seen[norm]][1].extend(blocks)
        else:
            seen[norm] = len(result)
            result.append((path, list(blocks)))
    return result


def read_answer(root, text, allowed=None):
    """The answer's edits, whole-file blocks, rendered files (None on a mismatch), and the EditMismatch (None when
    the edits apply). Nothing is written."""
    edits = parse_edits(text, allowed)
    edited = {p for p, _ in edits}
    whole = [f for f in parse_files(text, allowed) if f[0] not in edited]
    try:
        files = render_edits(root, edits) + whole
        error = None
    except EditMismatch as e:
        files = None
        error = e
    return {"edits": edits, "whole": whole, "files": files, "error": error}


def answer_files(root, text, allowed=None):
    """The files an answer would write: its edit blocks rendered against the files under root, then its whole-file
    blocks for paths that have no edit blocks; when the edits do not apply (EditMismatch), only the whole-file blocks.
    Nothing is written."""
    r = read_answer(root, text, allowed)
    return r["files"] if r["error"] is None else r["whole"]


def render_edits(root, edits):
    """Apply SEARCH/REPLACE blocks to existing files. Returns [(path, new_text)]. Nothing is written."""
    results = []
    for path, blocks in edits:
        p = Path(root, path)
        if not p.is_file():
            raise EditMismatch(path, blocks[0][0], 0, "")
        text = p.read_text(encoding="utf-8")
        for search, replace in blocks:
            n = text.count(search)
            if n != 1:
                first_line = next((ln.strip() for ln in search.splitlines() if ln.strip()), "")
                best_ratio = -1.0
                closest = ""
                for idx, line in enumerate(text.splitlines()):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    ratio = difflib.SequenceMatcher(None, first_line, stripped).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        closest = f"line {idx + 1}: {stripped}"
                raise EditMismatch(path, search, n, closest)
            text = text.replace(search, replace, 1)
        results.append((path, text))
    return results


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

