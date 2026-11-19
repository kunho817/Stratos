"""Tests for tasks codemap_python and codemap_js: stratos/codemap.py scans a source file into symbols (memory M1).

A symbol is a dict {"name", "kind", "line", "signature", "uses"}: kind "function", "class", "method" or "constant";
line is 1-based; uses is a sorted list of the distinct identifiers the symbol's code mentions (names and attribute
names alike, so `state.gold` gives "gold" and "state"), without the symbol's own name. Symbols come in file order.

scan_python(text) -> list of symbols, [] when the text does not parse:
- a top-level def / async def -> "function", signature f"def {name}({ast.unparse(node.args)})", uses = every
  ast.Name id and ast.Attribute attr inside it, without "self" and "cls";
- a top-level class -> "class" (signature f"class {name}", uses = the names in its bases), and each def directly in
  its body -> "method" named f"{Class}.{method}" with the function's signature and uses;
- a top-level assignment to one UPPER_CASE name (^[A-Z][A-Z0-9_]*$) -> "constant", signature the name, uses = the
  names in the value.

scan_js(text) -> list of symbols for the top-level declarations, i.e. lines that start (no indentation) with
  [export ][async ]function NAME(   -> "function"
  [export ]class NAME               -> "class"
  [export ](const|let|var) NAME =   -> "function" when the rest of the line has "=>" or "function", else "constant"
A declaration's code runs from its line to the line before the next top-level declaration or `import` line (or the
end). Its signature is its first line stripped, cut before a " {" or a trailing "{" and stripped again. Its uses are
the identifiers ([A-Za-z_$][A-Za-z0-9_$]*) of its code after removing // and /* */ comments and the contents of '...'
and "..." strings, without JS keywords (codemap.JS_KEYWORDS, which holds at least: const let var function return if
else for while of in new this class export import from true false null undefined typeof)."""
from stratos import codemap

PY = '''"""Doc."""
import os
from .towers import TOWER_TYPES

LIMIT = os.environ.get("X", 3)
lower = 1


def step(state, dt=0.1):
    """Move."""
    stats = TOWER_TYPES[state.kind]
    return state.gold + stats.damage + helper(dt)


class Store(Base):
    def get(self, key):
        return self.data[key]

    def put(self, key, value):
        self.data[key] = value
'''


def test_python_symbols():
    syms = codemap.scan_python(PY)
    assert [(s["name"], s["kind"], s["line"]) for s in syms] == [
        ("LIMIT", "constant", 5), ("step", "function", 9), ("Store", "class", 15),
        ("Store.get", "method", 16), ("Store.put", "method", 19)]
    by = {s["name"]: s for s in syms}
    assert by["LIMIT"]["signature"] == "LIMIT" and by["LIMIT"]["uses"] == ["environ", "get", "os"]
    assert by["step"]["signature"] == "def step(state, dt=0.1)"
    assert by["step"]["uses"] == ["TOWER_TYPES", "damage", "dt", "gold", "helper", "kind", "state", "stats"]
    assert by["Store"]["signature"] == "class Store" and by["Store"]["uses"] == ["Base"]
    assert by["Store.get"]["signature"] == "def get(self, key)"
    assert by["Store.get"]["uses"] == ["data", "key"]


def test_python_that_does_not_parse():
    assert codemap.scan_python("def f(:\n") == []


JS = '''// towers
import { findPath } from "./path.js";

export const TOWER_TYPES = {
  rapid: { cost: 10 },   // "cheap" one
};

const helper = (a) => a + 1;

export function placeTower(state, x, y) {
  const type = TOWER_TYPES["rapid"];
  /* gold check */
  if (state.gold < type.cost) return state;
  return { ...state, path: findPath(state.map), label: x };
}

export async function load(url) {
  return fetch(url);
}

export class Grid {
  constructor(w) { this.w = w; }
}
'''


def test_js_symbols():
    syms = codemap.scan_js(JS)
    assert [(s["name"], s["kind"], s["line"]) for s in syms] == [
        ("TOWER_TYPES", "constant", 4), ("helper", "function", 8), ("placeTower", "function", 10),
        ("load", "function", 17), ("Grid", "class", 21)]
    by = {s["name"]: s for s in syms}
    assert by["TOWER_TYPES"]["signature"] == "export const TOWER_TYPES ="
    assert by["TOWER_TYPES"]["uses"] == ["cost", "rapid"]
    assert by["helper"]["signature"] == "const helper = (a) => a + 1;"
    assert by["placeTower"]["signature"] == "export function placeTower(state, x, y)"
    assert by["placeTower"]["uses"] == ["TOWER_TYPES", "cost", "findPath", "gold", "label", "map", "path", "state",
                                        "type", "x", "y"]
    assert by["load"]["signature"] == "export async function load(url)"
    assert by["Grid"]["uses"] == ["constructor", "w"]


def test_js_keywords():
    for word in ("const", "return", "function", "export", "this", "null", "typeof", "of"):
        assert word in codemap.JS_KEYWORDS


def test_js_empty():
    assert codemap.scan_js("// nothing here\n") == []
