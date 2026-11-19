"""Stratos code map (memory layer M1) for Python and JavaScript files.

Scan a source file into a list of symbol dicts."""

import ast
import re
from pathlib import Path

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


def scan_python(text):
    """Scan Python source text into a list of symbol dicts in file order.

    Each symbol is {"name", "kind", "line", "signature", "uses"}.
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
                            "signature": sig, "uses": uses})

        elif isinstance(node, ast.ClassDef):
            # uses = names in its bases
            uses = set()
            for base in node.bases:
                for n in ast.walk(base):
                    if isinstance(n, ast.Name):
                        uses.add(n.id)
            uses = sorted(uses)
            symbols.append({"name": node.name, "kind": "class", "line": node.lineno,
                            "signature": f"class {node.name}", "uses": uses})

            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sig = f"def {item.name}({ast.unparse(item.args)})"
                    uses = _collect_uses(item, item.name)
                    symbols.append({"name": f"{node.name}.{item.name}", "kind": "method",
                                    "line": item.lineno, "signature": sig, "uses": uses})

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            continue

        elif isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target = node.targets[0]
                if re.match(r'^[A-Z][A-Z0-9_]*$', target.id):
                    uses = _collect_uses(node.value, target.id)
                    symbols.append({"name": target.id, "kind": "constant", "line": node.lineno,
                                    "signature": target.id, "uses": uses})
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
        symbols.append({"name": "(top level)", "kind": "script", "line": top_level[0].lineno,
                        "signature": "(top level)", "uses": uses})

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

    Each symbol is {"name", "kind", "line", "signature", "uses"}.
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

    # Locate import lines.
    import_lines = set()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("import "):
            import_lines.add(i)

    boundaries = sorted(set([i for i, _ in decls]) | import_lines)

    symbols = []
    covered = set()

    for i, m in decls:
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

        # The latest boundary is the next declaration or import line.
        next_idx = n
        for b in boundaries:
            if b > i:
                next_idx = b
                break

        # Walk lines; depth ends the declaration at its closing brace or semicolon.
        depth = 0
        brace_seen = False
        end = i
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
        uses = _uses(code, name)
        symbols.append({"name": name, "kind": kind, "line": i + 1,
                        "signature": signature, "uses": uses})

    # Top-level code: lines in no declaration and not import lines.
    top_lines = []
    first_line = None
    for i in range(n):
        if i in covered or i in import_lines:
            continue
        top_lines.append(lines[i])
        if first_line is None and lines[i].strip():
            first_line = i

    if first_line is not None:
        uses = _uses("\n".join(top_lines), "(top level)")
        if uses:
            symbols.append({"name": "(top level)", "kind": "script", "line": first_line + 1,
                            "signature": "(top level)", "uses": uses})

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


def build(root, settings=None):
    """Build the code map of a project: scan every source and test file into symbols."""
    if settings is None:
        settings = config.PROJECT

    root = Path(root)
    files = {}

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
                symbols = scan_python(path.read_text(encoding="utf-8"))
            elif suffix in (".js", ".mjs"):
                symbols = scan_js(path.read_text(encoding="utf-8"))
            else:
                continue
            relpath = path.relative_to(root).as_posix()
            files[relpath] = symbols

    return {"test_dir": settings["test_dir"], "files": dict(sorted(files.items()))}


def users(cmap, name):
    """Return the sorted list of f"{path}:{symbol name}" for every symbol whose uses contain name."""
    return sorted(
        f"{path}:{sym['name']}"
        for path, syms in cmap["files"].items()
        for sym in syms
        if name in sym["uses"]
    )


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
            us = users(cmap, sym["name"])
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
