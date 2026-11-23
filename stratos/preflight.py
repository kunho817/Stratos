"""Preflight check a task's tests on its base before any model call.

A task that no coder can pass is handed to a person at once instead of after several
attempts and model switches. Evidence: of 85 first-try failures in 4 projects, 36 tasks
were later reset by a person; causes seen: a test that imports a module another task
writes (Orbit T003, a missing After), test files with syntax errors.
"""
import re
from pathlib import Path

from . import steps, verify


def _cut_suffix(path):
    """Cut any '::...' suffix off a test path."""
    return path.split("::", 1)[0]


def check(task, wt, run=None):
    """Run a task's tests on its base; return {"verdict", "reason", "output"}."""
    with steps.timed("preflight"):
        wt = Path(wt)
        paths = [_cut_suffix(t) for t in task["tests"]]

        # (1) a test path that does not exist under wt
        for path in paths:
            if not (wt / path).exists():
                return {"verdict": "refuse", "reason": f"test file missing: {path}", "output": ""}

        # (2) syntax errors in the test files
        errors = verify.syntax_errors(wt, paths)
        if errors:
            return {"verdict": "refuse", "reason": "test file has a syntax error: " + errors[0], "output": ""}

        # (3) the tests already pass on the base
        run = run or verify.run_tests
        passed, out = run(wt, task["tests"])
        if passed:
            return {"verdict": "run", "reason": "tests already pass on the base", "output": ""}

        # (4) the tests import something this task does not write, or need a missing module
        for entry in missing_imports(out, wt, task["tests"]):
            if entry.startswith("module:"):
                name = entry[len("module:"):]
                if _is_explained_by_task_files(name, task["files"]):
                    continue
                return {"verdict": "refuse", "reason": f"the tests need module {name}, which is not installed", "output": out}
            if entry not in task["files"]:
                return {"verdict": "refuse",
                        "reason": f"the tests import {entry}, which this task does not write: add the task that writes it "
                                  "to After, or the file to Files",
                        "output": out}

        # (5) the tests fail before the change
        return {"verdict": "run", "reason": "tests fail before the change", "output": out}


_PY_CANNOT_IMPORT = re.compile(r"cannot import name '(\w+)' from '([\w.]+)' \(([^)]+)\)")
_PY_NO_MODULE = re.compile(r"No module named '([\w.]+)'")
_NODE_CANNOT_FIND = re.compile(r"Cannot find module '([^']+)'")
_NODE_NO_EXPORT = re.compile(r"The requested module '([^']+)' does not provide an export named")


def _to_relative(p, wt):
    """Make an absolute path repo-relative POSIX, or None if outside wt."""
    try:
        p = Path(p).resolve()
    except ValueError:
        return None
    try:
        return p.relative_to(Path(wt).resolve()).as_posix()
    except ValueError:
        return None


def _module_path(name, wt):
    """The module's path as a file under wt, or None if the module is not part of the project."""
    first = name.split(".", 1)[0]
    if (wt / first).is_dir() or (wt / (first + ".py")).is_file():
        return (name.replace(".", "/") + ".py")
    return None


def _is_explained_by_task_files(name, task_files):
    """True if module name (dots as slashes) equals a task file path stripped of '.py',
    or is a folder prefix that holds one of the task's files."""
    slashed = name.replace(".", "/")
    for f in task_files:
        stripped = f[:-3] if f.endswith(".py") else f
        if slashed == stripped:
            return True
        if f.startswith(slashed + "/"):
            return True
    return False


def _node_spec_path(spec, wt, js_folder):
    """Resolve a relative node spec against js_folder, then make it relative to wt."""
    return _to_relative(Path(wt, js_folder, spec), wt)


def _import_line_ok(pos, output):
    """Check if the line containing position pos is a real import error line.

    After stripping leading whitespace, an optional "E" followed by whitespace,
    and leading whitespace, the line must start with "ModuleNotFoundError:" or
    "ImportError:".
    """
    start = output.rfind("\n", 0, pos) + 1
    end = output.find("\n", pos)
    if end == -1:
        end = len(output)
    line = output[start:end]
    stripped = line.lstrip()
    if stripped.startswith("E") and len(stripped) > 1 and stripped[1] in " \t":
        stripped = stripped[1:].lstrip()
    return stripped.startswith("ModuleNotFoundError:") or stripped.startswith("ImportError:")


def missing_imports(output, wt, tests):
    """Repo-relative POSIX paths the tests import that do not exist or lack a name, in output order, no repeats."""
    wt = Path(wt).resolve()
    js_tests = [t for t in tests if _cut_suffix(t).lower().endswith((".js", ".mjs", ".cjs"))]
    js_folder = str(Path(_cut_suffix(js_tests[0])).parent) if js_tests else ""

    matches = []
    for rx in (_PY_CANNOT_IMPORT, _PY_NO_MODULE, _NODE_CANNOT_FIND, _NODE_NO_EXPORT):
        for m in rx.finditer(output):
            matches.append((m.start(), m))
    matches.sort(key=lambda pair: pair[0])

    seen = set()
    result = []

    def add(entry):
        if entry not in seen:
            seen.add(entry)
            result.append(entry)

    for _, m in matches:
        if m.re is _PY_CANNOT_IMPORT:
            name, file = m.group(1), m.group(3)
            rel = _to_relative(file, wt)
            if rel is not None and rel.endswith("__init__.py"):
                sub = Path(rel).parent / (name + ".py")
                if not (wt / sub).exists():
                    rel = sub.as_posix()
            if rel is not None:
                add(rel)
        elif m.re is _PY_NO_MODULE:
            if not _import_line_ok(m.start(), output):
                continue
            name = m.group(1)
            rel = _module_path(name, wt)
            if rel is not None:
                add(rel)
            else:
                add("module:" + name)
        elif m.re is _NODE_CANNOT_FIND:
            raw = m.group(1)
            raw = raw[len("file:///"):] if raw.startswith("file:///") else raw[len("file://"):] if raw.startswith("file://") else raw
            rel = _to_relative(raw, wt)
            if rel is not None:
                add(rel)
        elif m.re is _NODE_NO_EXPORT:
            rel = _node_spec_path(m.group(1), wt, js_folder)
            if rel is not None:
                add(rel)

    return result
