"""Stratos code map (memory layer M1) for Python and JavaScript files.

Scan a source file into a list of symbol dicts."""

import ast
import re
from pathlib import Path, PurePosixPath

import stratos.config as config


JS_KEYWORDS = frozenset({
    "break", "case", "catch", "class", "const", "continue", "debugger", "default",
    "delete", "do", "else", "export", "extends", "finally", "for", "function", "if",
    "import", "in", "instanceof", "let", "new", "return", "super", "switch", "this",
    "throw", "try", "typeof", "var", "void", "while", "with", "yield", "async", "await",
    "of", "from", "true", "false", "null", "undefined", "static", "get", "set",
})

_DECL_RE = re.compile(
    r"^(?P<export>export\s+)?(?P<async>async\s+)?(?P<kind>function|class|const|let|var)"
    r"\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?P<tail>.*)$"
)

_TEST_RE = re.compile(r"""^(test|it|describe)\(\s*(['"`])(.*?)\2""")


def scan_python(text):
    """Scan Python source text into a list of symbol dicts in file order.

    Each symbol is {"name", "kind", "line", "signature", "uses", "end"}.
    Returns [] if the text does not parse.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []

    symbols = []
    top_level = []

    for idx, node in enumerate(tree.body):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = f"def {node.name}({ast.unparse(node.args)})"
            uses = _collect_uses(node, node.name)
            symbols.append({"name": node.name, "kind": "function", "line": node.lineno,
                            "signature": sig, "uses": uses, "end": node.end_lineno})

        elif isinstance(node, ast.ClassDef):
            # uses = names in its bases
            uses = set()
            for base in node.bases:
                for n in ast.walk(base):
                    if isinstance(n, ast.Name):
                        uses.add(n.id)
            uses = sorted(uses)
            symbols.append({"name": node.name, "kind": "class", "line": node.lineno,
                            "signature": f"class {node.name}", "uses": uses, "end": node.end_lineno})

            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sig = f"def {item.name}({ast.unparse(item.args)})"
                    uses = _collect_uses(item, item.name)
                    symbols.append({"name": f"{node.name}.{item.name}", "kind": "method",
                                    "line": item.lineno, "signature": sig, "uses": uses,
                                    "end": item.end_lineno})

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            continue

        elif isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target = node.targets[0]
                if re.match(r'^[A-Z][A-Z0-9_]*$', target.id):
                    uses = _collect_uses(node.value, target.id)
                    symbols.append({"name": target.id, "kind": "constant", "line": node.lineno,
                                    "signature": target.id, "uses": uses, "end": node.end_lineno})
                    continue
            top_level.append(node)

        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str) and idx == 0:
            continue

        else:
            top_level.append(node)

    if top_level:
        uses = set()
        for stmt in top_level:
            for n in ast.walk(stmt):
                if isinstance(n, ast.Name):
                    uses.add(n.id)
                elif isinstance(n, ast.Attribute):
                    uses.add(n.attr)
        uses = sorted(uses)
        last = top_level[-1]
        symbols.append({"name": "(top level)", "kind": "script", "line": top_level[0].lineno,
                        "signature": "(top level)", "uses": uses, "end": last.end_lineno})

    return symbols


def _collect_uses(node, own_name):
    """Walk node and collect all Name ids and Attribute attrs, sorted and distinct,
    excluding 'self', 'cls', and the symbol's own name."""
    ids = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            ids.add(n.id)
        elif isinstance(n, ast.Attribute):
            ids.add(n.attr)
    ids.discard("self")
    ids.discard("cls")
    ids.discard(own_name)
    return sorted(ids)


def scan_js(text):
    """Scan JavaScript source text into a list of top-level declaration symbols.

    Each symbol is {"name", "kind", "line", "signature", "uses", "end"}.
    Returns [] when there are no top-level declarations.
    """
    lines = text.splitlines()
    n = len(lines)

    # Locate every top-level declaration line.
    decls = []
    for i, line in enumerate(lines):
        m = _DECL_RE.match(line)
        if m:
            decls.append((i, m))

    # Locate test call lines.
    tests = []
    for i, line in enumerate(lines):
        m = _TEST_RE.match(line)
        if m:
            tests.append((i, m))

    # Locate import lines.
    import_lines = set()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("import "):
            import_lines.add(i)

    # Boundaries include declaration lines, test lines, and import lines.
    boundaries = sorted(set([i for i, _ in decls]) | set([i for i, _ in tests]) | import_lines)

    # Build all symbols in line order (declarations and tests mixed together).
    all_lines = [(i, m, 'decl') for i, m in decls] + [(i, m, 'test') for i, m in tests]
    all_lines.sort(key=lambda x: x[0])

    symbols = []
    covered = set()

    for i, m, typ in all_lines:
        if typ == 'decl':
            name = m.group("name")
            if m.group("kind") == "function":
                kind = "function"
            elif m.group("kind") == "class":
                kind = "class"
            else:
                rest = m.group("tail")
                if "=>" in rest or "function" in rest:
                    kind = "function"
                else:
                    kind = "constant"
            own_name = name
        else:
            title = m.group(3)
            name = f"test: {title}"
            kind = "test"
            own_name = name

        # The latest boundary is the next declaration, test, or import line.
        next_idx = n
        for b in boundaries:
            if b > i:
                next_idx = b
                break

        # Walk lines; depth ends the declaration at its closing brace or semicolon.
        depth = 0
        brace_seen = False
        end = min(n, next_idx) - 1
        for j in range(i, min(n, next_idx)):
            stripped = _strip_js_line(lines[j])
            opens = stripped.count("{")
            closes = stripped.count("}")
            if opens:
                brace_seen = True
            depth += opens - closes
            if depth == 0 and (brace_seen or stripped.strip().endswith(";")):
                end = j
                break

        code = "\n".join(lines[i:end + 1])
        for j in range(i, end + 1):
            covered.add(j)

        signature = _signature(lines[i])
        uses = _uses(code, own_name)
        symbols.append({"name": name, "kind": kind, "line": i + 1,
                        "signature": signature, "uses": uses, "end": end + 1})

    # Top-level code: lines in no declaration, test, or import.
    top_lines = []
    first_line = None
    last_line = None
    for i in range(n):
        if i in covered or i in import_lines:
            continue
        top_lines.append(lines[i])
        if first_line is None and lines[i].strip():
            first_line = i
        if lines[i].strip():
            last_line = i

    if first_line is not None:
        uses = _uses("\n".join(top_lines), "(top level)")
        if uses:
            symbols.append({"name": "(top level)", "kind": "script", "line": first_line + 1,
                            "signature": "(top level)", "uses": uses, "end": last_line + 1,
                            "lines": list(range(first_line + 1, last_line + 2))})

    return symbols


def _strip_js_line(line):
    """Remove // comments and the contents of '...', "..." and `...` strings."""
    out = re.sub(r"//.*", "", line)
    out = re.sub(r"'[^']*'", "", out)
    out = re.sub(r'"[^"]*"', "", out)
    out = re.sub(r"`[^`]*`", "", out)
    return out


def _signature(line):
    sig = line.strip()
    if sig.endswith("{"):
        sig = sig[:-1].strip()
    else:
        idx = sig.find(" {")
        if idx != -1:
            sig = sig[:idx].strip()
    return sig


def _uses(code, own_name):
    code = re.sub(r"/\*.*?\*/", " ", code, flags=re.S)
    code = re.sub(r"//[^\n]*", " ", code)
    code = re.sub(r"'[^']*'", " ", code)
    code = re.sub(r'"[^"]*"', " ", code)
    code = re.sub(r"`[^`]*`", " ", code)
    ids = set(re.findall(r"[A-Za-z_$][A-Za-z0-9_$]*", code))
    ids.discard(own_name)
    ids -= JS_KEYWORDS
    return sorted(ids)


def imports_python(text):
    """Return the sorted distinct list of module names a Python file imports."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module.split(".")[-1])
            for alias in node.names:
                names.add(alias.name)
    return sorted(names)


def imports_js(text):
    """Return the sorted distinct list of module stems imported in a JS file."""
    specs = []
    for m in re.finditer(r"import\s+[\s\S]*?\s+from\s*['\"]([^'\"]+)['\"]", text):
        specs.append(m.group(1))
    for m in re.finditer(r"export\s+[\s\S]*?\s+from\s*['\"]([^'\"]+)['\"]", text):
        specs.append(m.group(1))
    for m in re.finditer(r"import\s*['\"]([^'\"]+)['\"]", text):
        specs.append(m.group(1))
    for m in re.finditer(r"import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", text):
        specs.append(m.group(1))
    for m in re.finditer(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", text):
        specs.append(m.group(1))
    stems = set()
    for spec in specs:
        last = spec.split("/")[-1]
        dot = last.rfind(".")
        if dot != -1:
            last = last[:dot]
        stems.add(last)
    return sorted(stems)


def module_name(path):
    """Return the module name for a path: stem of last part, folder name for __init__/index."""
    p = PurePosixPath(path)
    stem = p.stem
    if stem == "__init__" or stem == "index":
        return p.parent.name
    return stem


def symbol_text(text, sym):
    """Return the source lines of sym from text.

    When sym has "lines", the lines with those 1-based numbers; otherwise the lines
    from sym["line"] to sym["end"], joined with a newline."""
    lines = text.splitlines()
    if "lines" in sym:
        return "\n".join(lines[n - 1] for n in sym["lines"])
    return "\n".join(lines[sym["line"] - 1:sym["end"]])


def build(root, settings=None):
    """Build the code map of a project: scan every source and test file into symbols."""
    if settings is None:
        settings = config.PROJECT

    root = Path(root)
    files = {}
    imports = {}

    dirs = list(settings["source_dirs"])
    if settings["test_dir"]:
        dirs.append(settings["test_dir"])

    for rel in dirs:
        base = Path(root) / rel
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix == ".py":
                text = path.read_text(encoding="utf-8")
                symbols = scan_python(text)
            elif suffix in (".js", ".mjs"):
                text = path.read_text(encoding="utf-8")
                symbols = scan_js(text)
            else:
                continue
            relpath = path.relative_to(root).as_posix()
            files[relpath] = symbols
            if suffix == ".py":
                imports[relpath] = imports_python(text)
            else:
                imports[relpath] = imports_js(text)

    sorted_files = dict(sorted(files.items()))
    imports_dict = {path: imports[path] for path in sorted_files}
    return {"test_dir": settings["test_dir"], "files": sorted_files, "imports": imports_dict}


def users(cmap, name, path=None):
    """Return the sorted list of f"{path}:{symbol name}" for every symbol whose uses contain name."""
    results = []
    for p, syms in cmap["files"].items():
        for sym in syms:
            if name in sym["uses"]:
                results.append((p, sym["name"]))

    if path is not None and "imports" in cmap:
        module = module_name(path)
        filtered = []
        for p, sym_name in results:
            if p == path:
                filtered.append(f"{p}:{sym_name}")
            elif module in cmap["imports"].get(p, []):
                filtered.append(f"{p}:{sym_name}")
        return sorted(filtered)

    return sorted(f"{p}:{sym_name}" for p, sym_name in results)


def uses_summary(cmap, max_chars=6000):
    """Return a summary of who uses each code symbol, truncated to max_chars."""
    test_dir = cmap["test_dir"]
    lines = []
    for path, syms in cmap["files"].items():
        if path.startswith(test_dir + "/"):
            continue
        for sym in syms:
            if sym["kind"] not in ("function", "class", "constant"):
                continue
            us = users(cmap, sym["name"], path)
            if not us:
                continue
            code = [u for u in us if not u.startswith(test_dir + "/")]
            tests = sorted({u.split(":")[0] for u in us if u.startswith(test_dir + "/")})
            lines.append(
                f"{sym['name']} ({path}): used by {', '.join(code) or 'nothing'}; "
                f"tests: {', '.join(tests) or 'none'}"
            )

    if not lines:
        return ""

    joined = "\n".join(lines)
    if len(joined) <= max_chars:
        return joined

    kept = []
    for line in lines:
        candidate = "\n".join(kept + [line])
        if len(candidate) > max_chars:
            break
        kept.append(line)
    return "\n".join(kept + ["... (cut)"])
