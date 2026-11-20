import json
import subprocess
import sys
from pathlib import Path

ERRORS = ("F821", "F822", "F823")
FIXES = ("F401",)

_available = None


def available():
    global _available
    if _available is None:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "ruff", "--version"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=120,
            )
            _available = r.returncode == 0
        except Exception:
            _available = False
    return _available


def _filter_py(root, paths):
    root = Path(root)
    py = []
    for p in paths:
        if p.endswith(".py"):
            if (root / p).exists():
                py.append(p)
    return py


def check(root, paths):
    py = _filter_py(root, paths)
    if not py or not available():
        return []

    root_path = Path(root)
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--no-cache",
         "--select", ",".join(ERRORS), "--output-format", "json"] + py,
        cwd=str(root_path), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )

    stdout = result.stdout.strip()
    if not stdout:
        return []

    try:
        items = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return []

    resolved = Path(root_path).resolve()
    out = []
    for item in items:
        filename = item.get("filename", "")
        abs_path = Path(filename)
        if not abs_path.is_absolute():
            abs_path = root_path / abs_path
        abs_path = abs_path.resolve()
        try:
            rel = abs_path.relative_to(resolved)
        except ValueError:
            rel = abs_path
        rel_str = rel.as_posix()

        loc = item.get("location", {})
        row = loc.get("row", 0)
        col = loc.get("column", 0)
        code = item.get("code", "")
        message = item.get("message", "")
        out.append(f"{rel_str}:{row}:{col}: {code} {message}")

    return out


def fix(root, paths):
    py = _filter_py(root, paths)
    if not py or not available():
        return []

    root_path = Path(root)

    before = {}
    for p in py:
        before[p] = (root_path / p).read_text(encoding="utf-8")

    subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--no-cache", "--fix",
         "--select", ",".join(FIXES)] + py,
        cwd=str(root_path), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )

    changed = []
    for p in py:
        after = (root_path / p).read_text(encoding="utf-8")
        if after != before[p]:
            changed.append(p)

    return sorted(changed)
