"""Warn about a task's test list when adding it: missing or broken test files, a test that belongs to another
waiting task, and old tests that use the files this task changes but are left out of the list."""

import re
from pathlib import Path

from . import plantests, verify


def check(repo, task, others, cmap):
    tests = [t.split("::", 1)[0] for t in task["tests"]]
    lines = []

    # 1. test files that do not exist under repo
    for path in tests:
        if not Path(repo, path).exists():
            lines.append(f"missing test file: {path}")

    # 2. syntax errors in the existing test files
    existing = [p for p in tests if Path(repo, p).exists()]
    for line in verify.syntax_errors(repo, existing):
        lines.append(f"test file has a syntax error: {line}")

    # 3. a test that is the new test of another task that is not done
    for path in tests:
        for o in others:
            if o.get("status") not in ("done", "dropped"):
                ot = o.get("tests")
                if ot and ot[0].split("::", 1)[0] == path:
                    lines.append(
                        f"{path} is the new test of {o['id']}, which is not done: "
                        "leave it out of this task's tests"
                    )
                    break

    # 4. old tests that use the files this task changes
    goal = task.get("goal", "")
    changed = []
    for path in task["files"]:
        for sym in cmap["files"].get(path, []):
            name = sym["name"]
            if name not in changed and re.search(r"\b" + re.escape(name) + r"\b", goal):
                changed.append(name)

    warn4 = []
    for path in plantests.old_tests(cmap, {"files": task["files"], "tests": tests}):
        if changed:
            text = Path(repo, path).read_text(encoding="utf-8")
            used = [name for name in changed if re.search(r"\b" + re.escape(name) + r"\b", text)]
            if used:
                warn4.append(
                    f"{path} uses {', '.join(used)}, which this task changes: "
                    "list it in --tests, and update it now if the goal changes what it checks"
                )
        else:
            warn4.append(
                f"{path} imports a file this task changes: list it in --tests, and update it now "
                "if the goal changes what it checks"
            )

    if len(warn4) > 8:
        lines.extend(warn4[:8])
        lines.append(f"... and {len(warn4) - 8} more old tests")
    else:
        lines.extend(warn4)

    return lines
