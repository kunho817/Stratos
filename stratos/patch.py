"""Turn a model's answer into file writes.

The model answers with whole files:

    FILE: stratos/report.py
    ```python
    ...the entire file...
    ```

Whole files are easier for small models than diffs. Paths are checked: relative, inside the work tree, an allowed
suffix, and never a protected file (a model must not rewrite the tests it is judged by).
"""
import re
from pathlib import Path, PurePosixPath

from . import config

FILE_RE = re.compile(r"FILE:\s*`?([^\s`]+)`?\s*\n```[A-Za-z0-9_+-]*\n(.*?)```", re.S)


class PatchRefused(Exception):
    pass


def parse_files(text):
    return [(path.strip(), body) for path, body in FILE_RE.findall(text or "")]


def check_path(path, protected):
    p = PurePosixPath(path.replace("\\", "/"))
    if p.is_absolute() or ":" in path or ".." in p.parts or not p.parts:
        raise PatchRefused(f"path outside the project: {path}")
    if p.suffix not in config.WRITABLE_SUFFIXES:
        raise PatchRefused(f"file type not allowed: {path}")
    if str(p) in {str(PurePosixPath(x.replace("\\", "/"))) for x in protected}:
        raise PatchRefused(f"protected file: {path}")
    return p


def apply_files(root, files, protected):
    """Check every path first, then write; nothing is written when one path is refused."""
    checked = [(check_path(path, protected), body) for path, body in files]
    written = []
    for p, body in checked:
        dest = Path(root, *p.parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
        written.append(str(p))
    return written
