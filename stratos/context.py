"""Prompt assembly. The system prompt is the same for every coder call, so the start of the prompt stays fixed and
PolyStrata's conversation cache can reuse it; what changes (the task, its files, the last failure) comes after."""
from pathlib import Path

CODER_SYSTEM = """You are the coding model inside Stratos, a harness that edits a Python project.
Answer ONLY with whole files in this exact format, one block per file, and nothing else:

FILE: relative/path.py
```python
<the entire file content>
```

Rules:
- Write complete files, never fragments or diffs.
- Do not change files marked READ-ONLY. Do not add test code, prints or example runs to the files you write.
- Use only the Python standard library unless the task says otherwise.
- Keep the code plain and correct; the task's tests decide whether you succeeded."""


def show_file(root, path, label):
    p = Path(root, path)
    body = p.read_text(encoding="utf-8") if p.exists() else None
    if body is None:
        return f"{label}: {path} (does not exist yet)"
    return f"{label}: {path}\n```\n{body}\n```"


def build_messages(task, root, failure=None):
    parts = [f"TASK {task['id']}: {task['title']}", task["goal"]]
    for path in task["files"]:
        parts.append(show_file(root, path, "FILE YOU MAY WRITE"))
    for path in task["protected"]:
        parts.append(show_file(root, path, "READ-ONLY (the tests that must pass)"))
    if failure:
        parts.append("YOUR PREVIOUS ATTEMPT FAILED. Test output:\n```\n" + failure + "\n```\nFix it.")
    return [{"role": "system", "content": CODER_SYSTEM}, {"role": "user", "content": "\n\n".join(parts)}]
