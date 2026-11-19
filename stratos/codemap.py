"""Stratos code map: scan a Python source file into a list of symbol dicts."""

import ast
import re


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
