"""TRIAGE: decide whether a failing task's assertion is the test's or the code's fault.

After a task fails its tests, ask a quick model whether the failing assertion contradicts the task's goal.
If the assertion is wrong (test_wrong), the retry fixes the test; if the code is wrong (code_wrong), the retry
fixes the code. Returns {"verdict", "test", "reason"} from the model's JSON answer.
"""

import json
import re
import re as _re

from . import config, codemap, decide

SYSTEM = (
    "You are triaging a Stratos task that failed its tests. Read the task's goal, the test files, the code, and the "
    "test output. Decide whether the failing assertion contradicts the task's goal (the test is wrong) or the code "
    "does not meet the goal (the code is wrong). Answer with a single JSON object only, no prose: "
    '{"verdict": "test_wrong"|"code_wrong"|"unclear", "test": "<the test file path, or empty>", "reason": "<why>"}'
)

# Ask the model to answer again when its first answer had no usable verdict or an empty reason.
RETRY = 'Answer with one JSON object only: {"verdict": "test_wrong"|"code_wrong"|"unclear", "test": "<the test file path, or empty>", "reason": "<one sentence>"}. The reason must not be empty.'

_VERDICTS = {"test_wrong", "code_wrong", "unclear"}
_UNCLEAR = {"verdict": "unclear", "test": "", "reason": ""}

# Match a JSON object, allowing the last one in a string of several to be chosen.
_JSON_OBJ = re.compile(r"\{(?:[^{}]|\([^{}]*\)|\[[^\]]*\])*\}")


def test_parts(root, tests, test_output):
    """Return a list of (path, text) for the triage prompt.

    Shows only the failing tests and what they use. When no failing id names any test
    path, every test file is shown whole.
    """
    ids = decide._extract_ids(test_output)

    # Parse each id into (path, name, is_bare)
    parsed = []
    for id_ in ids:
        if "::" in id_:
            path, name = id_.split("::", 1)
            # Cut [...] suffix from name
            name = _re.sub(r"\[.*\]$", "", name)
            parsed.append((path, name, False))
        else:
            parsed.append((id_, "", True))

    # paths = test paths of `tests` with any "::..." cut off, in order
    paths = []
    for t in tests:
        path = t.split("::")[0]
        paths.append(path)

    # shown = the paths some id names
    shown = []
    for p in paths:
        for (ip, iname, is_bare) in parsed:
            if ip == p:
                shown.append(p)
                break

    if not shown:
        # Return all test files whole
        result = []
        for p in paths:
            try:
                text = (root / p).read_text(encoding="utf-8")
            except OSError:
                text = ""
            result.append((p, text))
        return result

    result = []
    for p in shown:
        try:
            text = (root / p).read_text(encoding="utf-8")
        except OSError:
            text = ""

        # Check if this path is named by a bare id
        bare = any(is_bare and ip == p for (ip, iname, is_bare) in parsed)
        if bare or text == "":
            result.append((p, text))
            continue

        # Slim the file
        syms = codemap.scan_python(text)
        # Filter to only function and class symbols
        func_class_syms = [s for s in syms if s["kind"] in ("function", "class")]

        # Failing test names for this path
        failing_names = []
        for (ip, iname, is_bare) in parsed:
            if ip == p and iname:
                failing_names.append(iname)

        # Build symbol name set
        sym_names = {s["name"] for s in func_class_syms}

        # wanted = failing test names that are symbols
        wanted = set()
        for name in failing_names:
            if name in sym_names:
                wanted.add(name)

        # BFS: add names in "uses" of wanted symbols that are symbols, until nothing new
        queue = list(wanted)
        while queue:
            current = queue.pop(0)
            for s in func_class_syms:
                if s["name"] == current:
                    for u in s["uses"]:
                        if u in sym_names and u not in wanted:
                            wanted.add(u)
                            queue.append(u)
                    break

        # header = lines before the first symbol start
        # Compute start for each symbol (walk up decorator lines)
        lines = text.splitlines()
        sym_starts = {}
        for s in func_class_syms:
            start = s["line"] - 1  # 0-based
            while start > 0 and lines[start - 1].lstrip().startswith("@"):
                start -= 1
            sym_starts[s["name"]] = start

        if func_class_syms:
            first_start = min(sym_starts[s["name"]] for s in func_class_syms)
            header = "\n".join(lines[:first_start]).rstrip()
        else:
            header = ""

        # Collect wanted symbols in file order
        wanted_syms = [s for s in func_class_syms if s["name"] in wanted]
        wanted_syms.sort(key=lambda s: sym_starts[s["name"]])

        parts = []
        if header:
            parts.append(header)
        for s in wanted_syms:
            start = sym_starts[s["name"]]
            end = s["end"]
            part = "\n".join(lines[start:end])
            parts.append(part)

        result.append((p, "\n\n".join(parts)))

    return result


def build_messages(task, root, code_files, test_output, consensus=None):
    """Build the system + user messages for the triage call."""
    lines = []
    lines.append("Goal: " + task["goal"])
    lines.append("")
    lines.append("Test files (the failing tests and what they use):")
    for path, text in test_parts(root, task.get("tests", []), test_output):
        lines.append(f"- {path}:")
        lines.append(text)
        lines.append("")
    lines.append("Code files:")
    if code_files:
        for path, content in code_files:
            lines.append(f"- {path}:")
            lines.append(content)
            lines.append("")
    else:
        lines.append("(none)")
        lines.append("")
    if consensus:
        lines.append("Independent attempts: different models wrote their own code for this task and all failed these same tests:")
        for tid in consensus:
            lines.append("- " + tid)
        lines.append("Code from different models that agrees against a test is a sign the test may be wrong; check those tests first.")
        if "(the generator)" in consensus:
            lines.append("Generators written by different models all failed: the code they call (the task's protected source files) may be wrong - check it before blaming the generator.")
        lines.append("")
    lines.append("Test output:")
    lines.append(test_output)
    user = "\n".join(lines)
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def parse(text):
    """Extract the last JSON object in text as a verdict. Anything invalid gives the unclear default."""
    if not text:
        return dict(_UNCLEAR)
    matches = _JSON_OBJ.findall(text)
    if not matches:
        return dict(_UNCLEAR)
    try:
        data = json.loads(matches[-1])
    except (ValueError, TypeError):
        return dict(_UNCLEAR)
    verdict = data.get("verdict")
    if verdict not in _VERDICTS:
        return dict(_UNCLEAR)
    return {"verdict": verdict, "test": data.get("test", ""), "reason": data.get("reason", "")}


def _usable(text):
    """True when parse found a JSON object with a valid verdict and a non-empty reason."""
    answer = parse(text)
    return answer["reason"].strip() != ""


def triage(gw, task, root, code_files, test_output, consensus=None):
    """Ask the triage model whether the failing assertion is the test's or the code's fault; retry once if unusable."""
    triager = config.TRIAGER
    gw.ensure_model(triager["model"])
    messages = build_messages(task, root, code_files, test_output, consensus=consensus)
    kwargs = dict(
        task=task["id"],
        role="triage",
        attempt=1,
        model=triager["model"],
        effort=triager["effort"],
        max_tokens=triager["max_tokens"],
    )
    if triager.get("reasoning_budget") is not None:
        kwargs["reasoning_budget"] = triager["reasoning_budget"]
    _, answer = gw.chat(messages, **kwargs)
    (config.STATE_DIR / "answers").mkdir(parents=True, exist_ok=True)
    (config.STATE_DIR / "answers" / f"{task['id']}-triage-1.md").write_text(answer, encoding="utf-8")
    if not _usable(answer):
        kwargs["attempt"] = 2
        messages = messages + [
            {"role": "assistant", "content": answer},
            {"role": "user", "content": RETRY},
        ]
        _, answer = gw.chat(messages, **kwargs)
        (config.STATE_DIR / "answers" / f"{task['id']}-triage-2.md").write_text(answer, encoding="utf-8")
    return parse(answer)

