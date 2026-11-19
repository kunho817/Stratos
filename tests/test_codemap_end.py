"""Tests for task codemap_end: every code map symbol also has "end", its last line (memory M2 cuts code into chunks).

scan_python: "end" = node.end_lineno for functions, classes, methods and constants; for "(top level)" the
end_lineno of the last collected statement.
scan_js: "end" = the 1-based number of the declaration's last line (the line its walk ended on); for "(top level)"
the 1-based number of the last non-blank line that belongs to the top-level code.
A JS "(top level)" symbol also has "lines": the sorted 1-based numbers of its top-level code lines (in no declaration
and not import lines), from "line" to "end".
codemap.symbol_text(text, sym) -> the lines of text with the numbers in sym["lines"] when the symbol has it, else
the lines sym["line"] .. sym["end"], joined with a newline."""
from stratos import codemap

PY = '''import os

LIMITS = {
    "a": 1,
}


def f(x):
    y = x + 1
    return y


class C:
    def m(self):
        return 1

print(f(1))
'''


def test_python_end():
    syms = codemap.scan_python(PY)
    assert [(s["name"], s["line"], s["end"]) for s in syms] == [
        ("LIMITS", 3, 5), ("f", 8, 10), ("C", 13, 15), ("C.m", 14, 15), ("(top level)", 17, 17)]
    by = {s["name"]: s for s in syms}
    assert codemap.symbol_text(PY, by["f"]) == "def f(x):\n    y = x + 1\n    return y"


JS = '''import { a } from "./a.js";

export function g(s) {
  return a(s);
}

const K = 3;
run(K);

test("x", () => {
  g(1);
});
'''


def test_js_end():
    syms = codemap.scan_js(JS)
    assert [(s["name"], s["line"], s["end"]) for s in syms] == [
        ("g", 3, 5), ("K", 7, 7), ("(top level)", 8, 12)]
    by = {s["name"]: s for s in syms}
    assert codemap.symbol_text(JS, by["g"]) == "export function g(s) {\n  return a(s);\n}"
    assert by["(top level)"]["lines"] == [8, 9, 10, 11, 12]
    assert codemap.symbol_text(JS, by["(top level)"]) == 'run(K);\n\ntest("x", () => {\n  g(1);\n});'
