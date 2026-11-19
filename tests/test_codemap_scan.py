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
        ("Store.get", "method", 16), ("Store.put", "method", 19), ("(top level)", "script", 6)]  # lower = 1
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


# --- task codemap_top_level (2026-11-19): declarations end at their closing brace; the rest is "(top level)" ---
# On the tower defense trial, main.js's DOM loop (after the last declaration) was counted as part of handleSelect,
# and node tests (all top-level test(...) calls) used nothing. Now:
# - scan_js: a declaration ends at the first line (from its own line on) where the count of "{" minus "}" so far,
#   counted after removing comments and the contents of '...', "..." and `...` strings, is 0 and either a "{" has been
#   seen or the stripped line ends with ";" - or, at the latest, before the next declaration or import line.
# - The code that is in no declaration and is not an import line (scan_js) / every top-level statement that is not a
#   def, class, constant, import or the module docstring (scan_python) makes one more symbol, last in the list:
#   {"name": "(top level)", "kind": "script", "line": <its first such line>, "signature": "(top level)", "uses": ...},
#   only when its uses are not empty.

JS_MAIN = '''import { step } from "./step.js";

export function handle(s) {
  return s.x;
}

if (typeof document !== "undefined") {
  let state = start();
  function loop() {
    state = step(state, 0.1);
  }
}
'''


def test_js_declaration_ends_at_its_brace():
    syms = codemap.scan_js(JS_MAIN)
    assert [(s["name"], s["kind"], s["line"]) for s in syms] == [("handle", "function", 3),
                                                                  ("(top level)", "script", 7)]
    assert syms[0]["uses"] == ["s", "x"]
    assert syms[1]["signature"] == "(top level)"
    assert syms[1]["uses"] == ["document", "loop", "start", "state", "step"]


def test_js_tests_are_top_level_code():
    text = 'import { test } from "node:test";\nimport { step } from "../src/step.js";\n\n' \
           'test("moves", () => {\n  assert.equal(step(1).x, 2);\n});\n'
    (sym,) = codemap.scan_js(text)
    # (task codemap_tests: a test(...) call is now its own "test" symbol)
    assert (sym["name"], sym["kind"], sym["line"]) == ("test: moves", "test", 4)
    assert sym["uses"] == ["assert", "equal", "step", "test", "x"]


def test_js_one_line_declarations_end_at_their_semicolon():
    syms = codemap.scan_js("const A = 1;\nrun(A);\nconst B = {\n  a: A,\n};\n")
    assert [(s["name"], s["uses"]) for s in syms] == [("A", []), ("B", ["A", "a"]), ("(top level)", ["A", "run"])]


def test_python_top_level_code():
    text = '"""Doc."""\nimport sys\n\n\ndef main():\n    return 1\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'
    syms = codemap.scan_python(text)
    assert [(s["name"], s["kind"], s["line"]) for s in syms] == [("main", "function", 5), ("(top level)", "script", 9)]
    assert syms[1]["uses"] == ["__name__", "exit", "main", "sys"]


def test_js_a_declaration_that_never_closes_runs_to_the_next_one():
    """Review of T105: with no ";" and no braces (code written without semicolons) the declaration kept only its
    own line and the rest went to "(top level)"; it must run to the line before the next declaration."""
    text = "const f = (a) =>\n  helper(a)\nexport function g() {\n  return 1;\n}\n"
    syms = codemap.scan_js(text)
    assert [(s["name"], s["uses"]) for s in syms] == [("f", ["a", "helper"]), ("g", [])]


# --- task codemap_tests (2026-11-19): a JS test call is its own symbol ---
# Indexing the tower defense, a whole test file was one "(top level)" chunk and crowded out the code in search.
# Now a top-level line (no indentation) matching ^(test|it|describe)\(\s*(['"`])(.*?)\2 starts a symbol
# {"name": f"test: {title}", "kind": "test", "line", "end", "signature": the line stripped and cut like a declaration's,
# "uses"}; it ends by the same walk as a declaration (depth 0 with a brace seen or a line ending with ";"), at the
# latest before the next declaration, test or import line. Its lines are not "(top level)" code. Symbols stay in line
# order, "(top level)" last.

def test_js_test_calls_are_symbols():
    text = ('import { step } from "../src/step.js";\n\nconst S = 1;\n\n'
            'test("moves one cell", () => {\n  step(S);\n});\n\n'
            "describe('waves', () => {\n  it(\"spawns\", () => {\n    waveDef(1);\n  });\n});\n\nsetup();\n")
    syms = codemap.scan_js(text)
    assert [(s["name"], s["kind"], s["line"], s["end"]) for s in syms] == [
        ("S", "constant", 3, 3), ("test: moves one cell", "test", 5, 7), ("test: waves", "test", 9, 13),
        ("(top level)", "script", 15, 15)]
    by = {s["name"]: s for s in syms}
    assert by["test: moves one cell"]["uses"] == ["S", "step", "test"]
    assert by["test: moves one cell"]["signature"] == 'test("moves one cell", () =>'
    assert by["test: waves"]["uses"] == ["describe", "it", "waveDef"]
    assert by["(top level)"]["uses"] == ["setup"]
