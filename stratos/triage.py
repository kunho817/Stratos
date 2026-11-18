"""TRIAGE: decide whether a failing task's assertion is the test's or the code's fault.

After a task fails its tests, ask a quick model whether the failing assertion contradicts the task's goal.
If the assertion is wrong (test_wrong), the retry fixes the test; if the code is wrong (code_wrong), the retry
fixes the code. Returns {"verdict", "test", "reason"} from the model's JSON answer.
"""

import json
import re

from .config import TRIAGER

SYSTEM = (
    "You are triaging a Stratos task that failed its tests. Read the task's goal, the test files, the code, and the "
    "test output. Decide whether the failing assertion contradicts the task's goal (the test is wrong) or the code "
    "does not meet the goal (the code is wrong). Answer with a single JSON object only, no prose: "
    '{"verdict": "test_wrong"|"code_wrong"|"unclear", "test": "<the test file path, or empty>", "reason": "<why>"}'
)

_VERDICTS = {"test_wrong", "code_wrong", "unclear"}
_UNCLEAR = {"verdict": "unclear", "test": "", "reason": ""}

# Match a JSON object, allowing the last one in a string of several to be chosen.
_JSON_OBJ = re.compile(r"\{(?:[^{}]|\([^{}]*\)|\[[^\]]*\])*\}")


def build_messages(task, root, code_files, test_output):
    """Build the system + user messages for the triage call."""
    lines = []
    lines.append("Goal: " + task["goal"])
    lines.append("")
    lines.append("Test files:")
    for test_path in task.get("tests", []):
        try:
            text = (root / test_path).read_text()
        except OSError:
            text = ""
        lines.append(f"- {test_path}:")
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


def triage(gw, task, root, code_files, test_output):
    """Ask the triage model whether the failing assertion is the test's or the code's fault; return parse(answer)."""
    gw.ensure_model(TRIAGER["model"])
    messages = build_messages(task, root, code_files, test_output)
    _, answer = gw.chat(
        messages,
        task=task["id"],
        role="triage",
        attempt=1,
        model=TRIAGER["model"],
        effort=TRIAGER["effort"],
        max_tokens=TRIAGER["max_tokens"],
        reasoning_budget=TRIAGER["reasoning_budget"],
    )
    return parse(answer)
