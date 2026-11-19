"""Stratos code map: scan a Python source file into a list of symbol dicts."""

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

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = f"def {node.name}({ast.unparse(node.args)})"
            uses = _collect_uses(node, node.name)
            symbols.append({"name": node.name, "kind": "function", "line": node.lineno, "signature": sig, "uses": uses})

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

        elif isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target = node.targets[0]
                if re.match(r'^[A-Z][A-Z0-9_]*$', target.id):
                    uses = _collect_uses(node.value, target.id)
                    symbols.append({"name": target.id, "kind": "constant", "line": node.lineno,
                                    "signature": target.id, "uses": uses})

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
    symbols = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        m = _DECL_RE.match(line)
        if not m:
            i += 1
            continue

        name = m.group("name")
        decl_line = i
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

        j = i + 1
        while j < n:
            nxt = lines[j]
            if _DECL_RE.match(nxt) or nxt.lstrip().startswith("import"):
                break
            j += 1

        code = "\n".join(lines[i:j])
        signature = _signature(line)
        uses = _uses(code, name)
        symbols.append({"name": name, "kind": kind, "line": decl_line + 1,
                        "signature": signature, "uses": uses})
        i = j

    return symbols


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
