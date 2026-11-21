r"""Run a static checker and read its errors.

checker.parse(output, root, paths) -> sorted unique lines f"{path}:{line}: {message}" for the errors in `paths`:
an output line is an error when it matches either
  colon form: r"^\s*(?P<file>.+?):(?P<line>\d+)(?::\d+)?\s*-?\s*error\s*:?\s*(?P<msg>.+)$" (pyright, gcc style), or
  paren form: r"^\s*(?P<file>.+?)\((?P<line>\d+),\d+\)\s*:\s*error\s+(?P<msg>.+)$" (tsc, dotnet, msbuild);
the file is resolved against root and turned into a path relative to root with "/"; errors in other files are
dropped; the message is stripped, and a trailing " [<something>]" (msbuild's project) is cut.
checker.check(root, paths) -> [] when config.PROJECT.get("check_command") is empty or paths is empty; otherwise it
runs the command with every "{files}" item replaced by the paths (or the paths appended when no item is "{files}"),
cwd=root, timeout 120 s (a timeout gives []), and returns parse(stdout + stderr, root, paths)."""
import os
import re
import subprocess
from pathlib import Path

from stratos import config

_COLON = re.compile(r"^\s*(?P<file>.+?):(?P<line>\d+)(?::\d+)?\s*-?\s*error\s*:?\s*(?P<msg>.+)$")
_PAREN = re.compile(r"^\s*(?P<file>.+?)\((?P<line>\d+),\d+\)\s*:\s*error\s+(?P<msg>.+)$")
_TRAILING = re.compile(r"\s*\[[^\]]*\]$")


def parse(output, root, paths):
    wanted = {p.replace("\\", "/") for p in paths}
    root = Path(root)
    lines = []
    for line in output.splitlines():
        m = _COLON.match(line) or _PAREN.match(line)
        if m is None:
            continue
        rel = m.group("file")
        if not os.path.isabs(rel):
            rel = os.path.join(str(root), rel)
        rel = os.path.relpath(rel, str(root)).replace("\\", "/")
        if rel not in wanted:
            continue
        msg = _TRAILING.sub("", m.group("msg")).strip()
        lines.append(f"{rel}:{m.group('line')}: {msg}")
    return sorted(set(lines))


def check(root, paths):
    cmd = config.PROJECT.get("check_command")
    if not cmd or not paths:
        return []
    if "{files}" in cmd:
        cmd = [item for x in cmd for item in (paths if x == "{files}" else [x])]
    elif config.PROJECT.get("test_runner") == "dotnet":
        # (Claude, 2026-11-21, Settle) dotnet build takes a project, not .cs files (MSB4025): build it as given
        cmd = list(cmd)
    else:
        cmd = list(cmd) + list(paths)
    try:
        r = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120,
                           env={**os.environ, "DOTNET_CLI_UI_LANGUAGE": "en"})
    except (subprocess.TimeoutExpired, OSError):
        return []
    return parse(r.stdout + r.stderr, root, paths)
