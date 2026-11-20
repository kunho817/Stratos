"""refcheck: an independent reference implementation checks drafted tests."""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from stratos import config, decide, patch

SYSTEM = (
    "You write the source files of one task of a project from its goal alone "
    "(you do not see its tests). Answer with each whole file in this format "
    "and nothing else:\nFILE: <path>\n```\n<content>\n```"
)


def build_messages(task, root):
    parts = ["GOAL:\n" + task["goal"], "WRITE THESE FILES: " + ", ".join(task["files"])]
    task_files_set = set(task["files"])
    existing = []
    for d in config.PROJECT["source_dirs"]:
        dir_path = Path(root) / d
        if not dir_path.is_dir():
            continue
        for f in dir_path.rglob("*"):
            if not f.is_file():
                continue
            if "__pycache__" in f.parts:
                continue
            if f.suffix == ".pyc":
                continue
            rel = str(Path(f).relative_to(root)).replace("\\", "/")
            if rel in task_files_set:
                continue
            existing.append((rel, f))
    existing.sort(key=lambda x: x[0])
    for rel, f in existing:
        text = f.read_text(encoding="utf-8")
        parts.append(f"EXISTING FILE {rel}:\n```\n{text}\n```")
    conv_path = Path(root) / "CONVENTIONS.md"
    if conv_path.exists():
        parts.append("CONVENTIONS:\n" + conv_path.read_text(encoding="utf-8"))
    user_content = "\n\n".join(parts)
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_content},
    ]


def count_tests(output):
    tap = re.findall(r"^\s*(not ok|ok) \d+ - (.+)$", output, re.M)
    if tap:
        total = len(tap)
        failing = [name.strip() for ok, name in tap if ok == "not ok"]
        return (total, failing)
    # pytest: find the last line that has numbers before passed/failed/errors
    lines = output.splitlines()
    last_line = None
    for line in lines:
        if re.search(r"\d+\s+(passed|failed|errors?)\b", line):
            last_line = line
    if last_line is not None:
        nums = re.findall(r"(\d+) (passed|failed|errors?)\b", last_line)
        total = sum(int(n) for n, _ in nums)
    else:
        total = 0
    failing = decide._extract_ids(output)
    return (total, failing)


def judge(total, failing):
    if not failing:
        return "agree"
    if len(failing) * 2 > total:
        return "interface"
    return "flagged"


def check(gw, plan_id, task, root, tests, extra=None):
    tmp = Path(tempfile.mkdtemp())
    try:
        copy = tmp / "p"
        shutil.copytree(
            root,
            copy,
            ignore=shutil.ignore_patterns(".git", ".stratos", "node_modules", "__pycache__",
                                          ".venv", "venv", "*-wt"),
        )
        cfg = config.REF_WRITER
        gw.ensure_model(cfg["model"])
        _, answer = gw.chat(
            build_messages(task, root),
            task=f"{plan_id}-{task['key']}",
            role="reference",
            attempt=1,
            model=cfg["model"],
            effort=cfg["effort"],
            max_tokens=cfg["max_tokens"],
        )
        files = patch.parse_files(answer, task["files"])
        if not files:
            return {"status": "error", "total": 0, "failing": [], "first_error": "no file in the answer",
                    "files": []}
        if extra:
            for path, content in extra:
                dest = Path(copy) / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
        for path, content in files:
            dest = Path(copy) / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        cmd = config.PROJECT["test_command"] + tests
        try:
            r = subprocess.run(
                cmd,
                cwd=str(copy),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=config.TEST_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return {"status": "error", "total": 0, "failing": [], "first_error": "tests timed out",
                    "files": []}
        out = r.stdout + r.stderr
        total, failing = count_tests(out)
        first_error = ""
        for line in out.splitlines():
            if "Error" in line or "assert" in line:
                first_error = line.strip()[:200]
                break
        return {"status": judge(total, failing), "total": total, "failing": failing,
                "first_error": first_error, "files": files}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
