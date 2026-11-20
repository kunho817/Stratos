import ast
import re

def _call(src):
    try:
        tree = ast.parse(src.strip(), mode="eval")
    except SyntaxError:
        return None
    body = tree.body
    if not isinstance(body, ast.Call):
        return None
    func = body.func
    parts = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if not isinstance(func, ast.Name):
        return None
    parts.append(func.id)
    parts.reverse()
    if len(parts) > 1:
        module = ".".join(parts[:-1])
        name = parts[-1]
        prefix = module + "."
        call = src.strip()[len(prefix):]
    else:
        module = None
        name = parts[-1]
        call = src.strip()
    return {"module": module, "name": name, "call": call}


def parse(text):
    imports = []
    plain = []
    other = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("IMPORT "):
            imports.append(line[len("IMPORT "):])
            continue
        # Check raises case
        idx = line.rfind(" raises ")
        if idx != -1:
            left = line[:idx]
            right = line[idx + len(" raises "):]
            m = re.fullmatch(r"([A-Za-z_]\w*)(?::\s?(.*))?", right)
            if m:
                c = _call(left)
                if c is not None:
                    c["kind"] = "raises"
                    c["error"] = m.group(1)
                    c["message"] = m.group(2) if m.group(2) is not None else None
                    plain.append(c)
                    continue
        # Check eq case
        try:
            tree = ast.parse(line.strip(), mode="eval")
        except SyntaxError:
            other.append(line)
            continue
        body = tree.body
        if isinstance(body, ast.Compare) and len(body.ops) == 1 and isinstance(body.ops[0], ast.Eq):
            left_seg = ast.get_source_segment(line.strip(), body.left)
            if left_seg is not None:
                c = _call(left_seg)
                if c is not None:
                    right_seg = ast.get_source_segment(line.strip(), body.comparators[0])
                    c["kind"] = "eq"
                    c["call"] = c["call"]
                    c["expected"] = right_seg
                    plain.append(c)
                    continue
        other.append(line)
    return {"imports": imports, "plain": plain, "other": other}


def render(parsed):
    header_lines = ['"""Tests written by Stratos from the cases Claude gave (stratos/cases.py)."""']
    has_raises = any(c["kind"] == "raises" for c in parsed["plain"])
    if has_raises:
        header_lines.append("import re")
        header_lines.append("import pytest")
    for imp in parsed["imports"]:
        header_lines.append(imp)
    # Collect modules in first-use order with names
    modules = {}
    module_order = []
    for c in parsed["plain"]:
        mod = c["module"]
        if mod is not None:
            if mod not in modules:
                modules[mod] = []
                module_order.append(mod)
            if c["name"] not in modules[mod]:
                modules[mod].append(c["name"])
    for mod in module_order:
        names = sorted(modules[mod])
        header_lines.append("from %s import %s" % (mod, ", ".join(names)))
    # Build functions
    counters = {}
    funcs = []
    for c in parsed["plain"]:
        name = c["name"]
        counters[name] = counters.get(name, 0) + 1
        n = counters[name]
        func_name = "test_%s_%d" % (name, n)
        if c["kind"] == "eq":
            func_body = "def %s():\n    assert %s == %s" % (func_name, c["call"], c["expected"])
        elif c["kind"] == "raises":
            if c["message"] is not None:
                func_body = "def %s():\n    with pytest.raises(%s, match=re.escape(%r)):\n        %s" % (
                    func_name, c["error"], c["message"], c["call"])
            else:
                func_body = "def %s():\n    with pytest.raises(%s):\n        %s" % (
                    func_name, c["error"], c["call"])
        funcs.append(func_body)
    header = "\n".join(header_lines)
    body = "\n\n\n".join(funcs)
    return header + "\n\n\n" + body + "\n"
