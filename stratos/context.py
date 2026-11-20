"""Prompt assembly. The system prompt is the same for every coder call, so the start of the prompt stays fixed and
PolyStrata's conversation cache can reuse it; what changes (the task, its files, the last failure) comes after."""
import ast
import re
from pathlib import Path
from stratos import codemap, config


def coder_system(language):
    lang = language
    fence = language.lower()
    return (
        "You are the coding model inside Stratos, a harness that edits a " + lang + " project.\n"
        "Answer ONLY with file blocks in one of these two formats, and nothing else.\n"
        "\n"
        "A new file, or a short one written whole:\n"
        "FILE: relative/path.py\n"
        "```" + fence + "\n"
        "<the entire file content>\n"
        "```\n"
        "\n"
        "A change to a file that already exists:\n"
        "FILE: relative/path.py\n"
        "<<<<<<< SEARCH\n"
        "<lines copied exactly from the file as shown>\n"
        "=======\n"
        "<the lines that replace them>\n"
        ">>>>>>> REPLACE\n"
        "\n"
        "Rules:\n"
        "- You have no tools and cannot open files: everything you need is in this message. Answer with the files directly.\n"
        "- For an existing file use edit blocks: each SEARCH is copied exactly from the file shown (indentation included), is found exactly once, and holds only a few lines around the change; use several blocks for several changes.\n"
        "- A whole file must be complete, never a fragment.\n"
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


def used_names(root, path, module):
    """Return the set of names the file at `path` uses from the module file `module`.

    Both are relative paths like 'pkg/m.py'. The dotted name of 'pkg/m.py' is 'pkg.m'.
    Returns set() when the file is missing or does not parse."""
    p = Path(root, path)
    if not p.exists():
        return set()
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"))
    except (SyntaxError, ValueError):
        return set()

    # dotted name of module: pkg/m.py -> pkg.m
    mod_parts = module.replace("\\", "/").split("/")
    dotted = ".".join(seg.replace(".py", "") for seg in mod_parts)

    # package of path: pkg/main.py -> package_name = "pkg"
    path_parts = path.replace("\\", "/").split("/")
    package_name = path_parts[-2] if len(path_parts) >= 2 else ""

    # local_names: names bound to the module object itself (e.g. from . import big as b -> "b")
    local_names = set()
    # names_used: names used as symbols from the module directly
    names_used = set()
    # import_dotted: set of dotted prefixes for "import pkg.m" (no alias)
    import_dotted = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # Resolve the full module name of the import
            if node.level > 0:
                if node.module is None:
                    full_mod = package_name
                else:
                    full_mod = package_name + "." + node.module if package_name else node.module
            else:
                full_mod = node.module

            if full_mod == dotted:
                # Direct import of symbols from the module
                for alias in node.names:
                    names_used.add(alias.name)
            elif dotted.startswith(full_mod + "."):
                # from pkg import big when dotted is pkg.big
                suffix = dotted[len(full_mod) + 1:]
                for alias in node.names:
                    if alias.name == suffix:
                        local = alias.asname if alias.asname else alias.name
                        local_names.add(local)

        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == dotted:
                    if alias.asname:
                        local_names.add(alias.asname)
                    else:
                        import_dotted.add(dotted)
                elif dotted.startswith(alias.name + "."):
                    # import pkg when dotted is pkg.big: pkg.big.attr is pkg.big.attr
                    # We treat this as pkg.big being accessed via pkg.big
                    pass

    # Walk for attributes
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            # Check local_names: e.g. b.LIMIT where b is in local_names
            if isinstance(node.value, ast.Name) and node.value.id in local_names:
                names_used.add(node.attr)
            # Check import_dotted: e.g. pkg.big.long_one
            # Structure: Attribute(value=Attribute(value=Name("pkg"), attr="big"), attr="long_one")
            if isinstance(node.value, ast.Attribute):
                inner = node.value
                if isinstance(inner.value, ast.Name):
                    prefix = inner.value.id + "." + inner.attr
                    if prefix in import_dotted:
                        names_used.add(node.attr)

    return names_used


def module_excerpt(root, module, names):
    """Return an excerpt of the module file showing only the parts relevant to `names`."""
    p = Path(root, module)
    text = p.read_text(encoding="utf-8")
    syms = codemap.scan_python(text)

    parts = []
    other = []
    for sym in syms:
        name = sym["name"]
        if name in names:
            stext = codemap.symbol_text(text, sym)
            lines = stext.split("\n")
            if len(lines) > 30:
                parts.append("\n".join(lines[:6]) + "\n    ...")
            else:
                parts.append(stext)
        else:
            other.append(name)

    if other:
        parts.append("# other names in this module: " + ", ".join(other))

    return "\n\n".join(parts)


def _abs_modules(root, path):
    """Find module paths referenced by absolute imports in the given file.

    For every ast.ImportFrom with level 0, uses node.module and node.module + '.' + each imported name.
    For every ast.Import, uses alias.name.
    Adds f"{parts[0]}/{parts[1]}.py" when the dotted name has at least two parts and that file exists under root."""
    p = Path(root, path)
    if not p.exists():
        return set()
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"))
    except (SyntaxError, ValueError):
        return set()
    found = set()

    def add(parts):
        if len(parts) >= 2:
            rel = f"{parts[0]}/{parts[1]}.py"
            if Path(root, rel).exists():
                found.add(rel)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module is not None:
                add(node.module.split("."))
                for alias in node.names:
                    full = node.module + "." + alias.name
                    add(full.split("."))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name.split("."))
    return found


def goal_modules(root, goal):
    """Return sorted list of package module paths that exist under root for dotted names in goal.

    Matches r'\\b([A-Za-z_]\\w*)\\.([A-Za-z_]\\w*)(?:\\.[A-Za-z_]\\w*)*' and builds f'{g1}/{g2}.py'
    when it exists under root."""
    results = set()
    for m in re.finditer(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)(?:\.[A-Za-z_]\w*)*", goal):
        g1, g2 = m.group(1), m.group(2)
        rel = f"{g1}/{g2}.py"
        if Path(root, rel).exists():
            results.add(rel)
    return sorted(results)


def related_files(root, files, extra=()):
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

    test_dir = config.PROJECT["test_dir"] + "/"

    for path in extra:
        p = Path(root, path)
        if not p.exists():
            continue
        norm = path.replace("\\", "/")
        if norm.startswith(test_dir):
            found |= _abs_modules(root, path)
        else:
            # Add the path itself
            if path not in task_paths:
                found.add(path)
            # Old import-following for it
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except (SyntaxError, ValueError):
                continue
            parts = norm.split("/")
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

    return sorted(found - set(files))


def build_messages(task, root, failure=None, memory=None, before=None):
    parts = [f"TASK {task['id']}: {task['title']}", task["goal"]]
    for path in task["files"]:
        parts.append(show_file(root, path, "FILE YOU MAY WRITE"))
    for path in task["protected"]:
        parts.append(show_file(root, path, "READ-ONLY (the tests that must pass)"))
    for path in related_files(root, task["files"], extra=list(task["protected"]) + goal_modules(root, task["goal"])):
        if path in task["files"] or path in task["protected"]:
            continue
        p = Path(root, path)
        body = p.read_text(encoding="utf-8") if p.exists() else None
        if body is None:
            parts.append(f"READ-ONLY (imported by the files you write): {path} (does not exist yet)")
            continue
        if len(body.split("\n")) <= 60:
            parts.append(f"READ-ONLY (imported by the files you write): {path}\n```\n{body}\n```")
        else:
            names = set()
            for f in task["files"]:
                names |= used_names(root, f, path)
            syms = codemap.scan_python(body)
            top_level_names = [s["name"] for s in syms]
            for name in top_level_names:
                if re.search(r"\b" + re.escape(name) + r"\b", task["goal"]):
                    names.add(name)
            parts.append(f"READ-ONLY (imported by the files you write; only the parts they use): {path}\n```\n{module_excerpt(root, path, names)}\n```")
    if memory:
        parts.append("MEMORY (found for this task: lessons and related code):\n" + memory)
    if failure:
        parts.append("YOUR PREVIOUS ATTEMPT FAILED and was not kept: the files above are as they were before it, so send every change again. Test output:\n```\n" + failure + "\n```\nFix it.")
    elif before:
        parts.append("BEFORE YOUR CHANGE THE TESTS FAIL LIKE THIS (make them pass):\n```\n" + before + "\n```")
    return [{"role": "system", "content": CODER_SYSTEM}, {"role": "user", "content": "\n\n".join(parts)}]
