"""Decision layer rules for Stratos (pure functions, no model).

Provides three rules used to decide how to react to a failed attempt and which coder role to assign:

- failure_signature(result, detail): what a failed attempt failed on, comparable between attempts.
- should_escalate(history): whether the current role should stop and escalate.
- choose_role(task): which coder role should handle the task (flow words are read from the goal's headline).
"""

import re

# Words/phrases (lower-case) that signal a change of code flow.
FLOW_WORDS = (
    'restructure',
    'reorder',
    'split',
    'refactor',
    'move',
    'rounds',
    'phase',
    'flow',
    '흐름',
    '재구성',
    '순서',
)


def _extract_ids(detail):
    """Return the sorted, de-duplicated list of test ids found in ``detail``.

    A FAILED line looks like ``FAILED tests/test_x.py::test_one - AssertionError: ...`` or
    ``FAILED tests/test_x.py::test_one``; the id is the text after ``FAILED `` up to `` - `` or end of line.
    An ERROR line looks like ``ERROR tests/test_y.py - SyntaxError: ...``; the id is the text after ``ERROR ``
    up to `` - `` or end of line.
    """
    ids = []
    for line in detail.splitlines():
        stripped = line.strip()
        if stripped.startswith('FAILED '):
            rest = stripped[len('FAILED '):]
            ids.append(rest.split(' - ', 1)[0].strip())
        elif stripped.startswith('ERROR '):
            rest = stripped[len('ERROR '):]
            ids.append(rest.split(' - ', 1)[0].strip())
    # Preserve order but de-duplicate, then sort for comparability.
    seen = []
    for i in ids:
        if i not in seen:
            seen.append(i)
    return sorted(seen)


def failure_signature(result, detail):
    """Return what a failed attempt failed on, comparable between attempts."""
    if result != "failed":
        return result
    if not detail:
        return ""

    ids = _extract_ids(detail)
    if ids:
        return ",".join(ids)

    for line in detail.splitlines():
        stripped = line.strip()
        if stripped.startswith('E '):
            return stripped

    return ""


def should_escalate(history):
    """Return whether the current role should stop and escalate.

    ``history`` is ``[(result, detail), ...]`` of the current role's attempts so far, oldest first.
    """
    if len(history) < 2:
        return {"choice": False, "confidence": 0.6, "reason": "not enough attempts to compare"}

    last_result, last_detail = history[-1]
    prev_result, prev_detail = history[-2]

    last_sig = failure_signature(last_result, last_detail)
    prev_sig = failure_signature(prev_result, prev_detail)

    if last_sig and last_sig == prev_sig:
        return {
            "choice": True,
            "confidence": 0.7,
            "reason": "the last two attempts failed the same way: %s" % last_sig,
        }

    return {"choice": False, "confidence": 0.6, "reason": "no repeated failure to escalate"}


def headline(goal):
    """Return the goal's headline: the text before the first blank line, without markup or dotted names."""
    text = re.split(r"\n[ \t]*\n", goal, maxsplit=1)[0]
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r'"[^"\n]*"', " ", text)
    text = re.sub(r"(?<!\w)'[^'\n]*'(?!\w)", " ", text)
    text = re.sub(r"\w+(?:\.\w+)+", " ", text)
    return text


def choose_role(task):
    """Return which coder role should handle the task."""
    files = task.get("files") or []
    goal = task.get("goal") or ""
    goal_headline = headline(goal)
    goal_headline_lower = goal_headline.lower()

    if len(files) >= 2:
        return {
            "choice": "coder_hard",
            "confidence": 0.6,
            "reason": "the task may write %d files, so it needs the harder coder" % len(files),
        }

    for word in FLOW_WORDS:
        if word.isascii() and word.isalpha():
            if re.search(r'\b' + re.escape(word) + r'\b', goal_headline, re.IGNORECASE):
                return {
                    "choice": "coder_hard",
                    "confidence": 0.55,
                    "reason": "the goal mentions a change of flow: '%s'" % word,
                }
        else:
            if word in goal_headline_lower:
                return {
                    "choice": "coder_hard",
                    "confidence": 0.55,
                    "reason": "the goal mentions a change of flow: '%s'" % word,
                }

    return {
        "choice": "coder",
        "confidence": 0.7,
        "reason": "a single straightforward task, handled by the standard coder",
    }
