"""Check drafted tests before code is written. For each test, reason by hand about what must happen,
then compare with the test's setup and expected values. Flag only wrong tests."""
import re
from pathlib import Path
from stratos import config, context

SYSTEM = (
    "You check drafted unit tests before any code is written. For every test, work out by hand what the "
    "goal and the shown project files say must happen, step by step, and compare it with the test's setup "
    "and expected values. A test is WRONG when: its expected value is miscalculated; it contradicts the "
    "goal or itself; its setup is impossible or does not reach the case it names (e.g. a timer that has not "
    "run out, an object already gone); it invents data or rules the goal does not give; or it depends on "
    "state left by another test or on time that does not pass. Do not flag style, missing tests or names you "
    "merely find unclear.\n"
    "Answer with one line per wrong test, exactly:\n"
    "WRONG: <the test's name exactly as written> | <one-sentence reason>\n"
    "and nothing else. If every test is right, answer exactly: NONE"
)


def test_names(text, path):
    if path.endswith(".py"):
        return re.findall(r"^\s*def (test_\w+)\(", text, re.M)
    return [m.group(2) for m in re.finditer(r"^\s*test\(\s*([\"'`])(.+?)\1", text, re.M)]


def build_messages(plan, task, root, draft):
    parts = ["GOAL OF THE TASK THESE TESTS ARE FOR:\n" + task["goal"]]
    others = [t for t in plan["tasks"] if t["key"] != task["key"]]
    if others:
        parts.append("OTHER TASKS OF THIS PLAN:")
        for t in others:
            parts.append(f"{t['key']}: {t['title']}\n{t['goal']}")
    seen = set()
    for p in task["files"] + [p for p in task["protected"] if p not in task["tests"]]:
        if p in seen:
            continue
        seen.add(p)
        if Path(root, p).exists():
            parts.append(context.show_file(root, p, "PROJECT FILE"))
    parts.append(f"DRAFTED TEST FILE {task['tests'][0]}:\n```\n{draft}\n```")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n\n".join(parts)}]


def parse(answer, names):
    results = []
    flagged = set()
    for line in answer.split("\n"):
        m = re.match(r"^\s*WRONG:\s*(.+?)\s*\|\s*(.*)$", line)
        if not m:
            continue
        raw_name = m.group(1).strip("\"'`")
        matched = None
        if raw_name in names:
            matched = raw_name
        else:
            for n in names:
                if raw_name in n or n in raw_name:
                    matched = n
                    break
        if matched is None:
            continue
        if matched in flagged:
            continue
        flagged.add(matched)
        reason = m.group(2).strip()
        results.append({"test": matched, "reason": reason})
    return results


def check(gw, plan_id, plan, task, root, path):
    draft = Path(root, path).read_text(encoding="utf-8")
    cfg = config.DRAFT_CHECKER
    gw.ensure_model(cfg["model"])
    kw = dict(
        task=f"{plan_id}-{task['key']}",
        role="draft_checker",
        attempt=1,
        model=cfg["model"],
        effort=cfg["effort"],
        max_tokens=cfg["max_tokens"],
    )
    if "reasoning_budget" in cfg:
        kw["reasoning_budget"] = cfg["reasoning_budget"]
    _, answer = gw.chat(build_messages(plan, task, root, draft), **kw)
    return parse(answer, test_names(draft, path))
