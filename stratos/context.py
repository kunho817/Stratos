"""Prompt assembly. The system prompt is the same for every coder call, so the start of the prompt stays fixed and
PolyStrata's conversation cache can reuse it; what changes (the task, its files, the last failure) comes after."""
import ast
from pathlib import Path
from stratos import config


def coder_system(language):
    lang = language
    fence = language.lower()
    return (
        "You are the coding model inside Stratos, a harness that edits a " + lang + " project.\n"
        "Answer ONLY with whole files in this exact format, one block per file, and nothing else:\n"
        "\n"
        "FILE: relative/path.py\n"
        "```" + fence + "\n"
        "<the entire file content>\n"
        "```\n"
        "\n"
        "Rules:\n"
        "- You have no tools and cannot open files: everything you need is in this message. Answer with the files directly.\n"
        "- Write complete files, never fragments or diffs.\n"
        "- Do not change files marked READ-ONLY. Do not add test code, prints or example runs to the files you write.\n"
        "- Use only the " + lang + " standard library unless the task says otherwise.\n"
        "- Keep the code plain and correct; the task's tests decide whether you succeeded."
    )


CODER_SYSTEM = coder_system(config.PROJECT["language"][0].upper() + config.PROJECT["language"][1:])


def show_file(root, path, label):
    p = Path(root, path)
    body = p.read_text(encoding="utf-8") if p.exists() else None
    if body is None:
        return f"{label}: {path} (does not exist yet)"
    return f"{label}: {path}\n```\n{body}\n```"


def related_files(root, files):
    task_paths = set(files)
    found = set()
    for path in files:
        p = Path(root, path)
        if not p.exists():
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, ValueError):
            continue
        parts = path.replace("\\", "/").split("/")
        package_folder = "/".join(parts[:-1])
        package_name = parts[-2] if len(parts) >= 2 else ""
        prefix = package_name + "." if package_name else ""
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level == 1:
                    if node.module is None:
                        names.update(alias.name for alias in node.names)
                    else:
                        names.add(node.module.split(".")[0])
                elif node.level == 0 and node.module is not None:
                    if node.module == package_name:
                        names.update(alias.name for alias in node.names)
                    elif node.module.startswith(prefix) and len(node.module) > len(prefix):
                        names.add(node.module[len(prefix):].split(".")[0])
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(prefix) and len(alias.name) > len(prefix):
                        names.add(alias.name[len(prefix):].split(".")[0])
        for name in names:
            rel = f"{package_folder}/{name}.py" if package_folder else f"{name}.py"
            if rel in task_paths:
                continue
            if Path(root, rel).exists():
                found.add(rel)
    return sorted(found)


def build_messages(task, root, failure=None, memory=None, before=None):
    parts = [f"TASK {task['id']}: {task['title']}", task["goal"]]
    for path in task["files"]:
        parts.append(show_file(root, path, "FILE YOU MAY WRITE"))
    for path in task["protected"]:
        parts.append(show_file(root, path, "READ-ONLY (the tests that must pass)"))
    for path in related_files(root, task["files"]):
        if path in task["files"] or path in task["protected"]:
            continue
        parts.append(show_file(root, path, "READ-ONLY (imported by the files you write)"))
    if memory:
        parts.append("MEMORY (found for this task: lessons and related code):\n" + memory)
    if failure:
        parts.append("YOUR PREVIOUS ATTEMPT FAILED. Test output:\n```\n" + failure + "\n```\nFix it.")
    elif before:
        parts.append("BEFORE YOUR CHANGE THE TESTS FAIL LIKE THIS (make them pass):\n```\n" + before + "\n```")
    return [{"role": "system", "content": CODER_SYSTEM}, {"role": "user", "content": "\n\n".join(parts)}]
