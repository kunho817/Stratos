"""Tests for task codemap_build: the code map of a project and "who uses what" (memory M1).

build(root, settings=None) -> {"test_dir": settings["test_dir"], "files": {path: [symbols]}} with settings =
config.PROJECT by default. It reads (UTF-8) every file under each of settings["source_dirs"] and under
settings["test_dir"], recursively: ".py" files with scan_python, ".js" and ".mjs" files with scan_js, others are
left out. path is the POSIX path relative to root; "files" is in sorted path order. Missing folders are skipped.

users(cmap, name) -> sorted list of f"{path}:{symbol name}" for every symbol whose uses contain name.

uses_summary(cmap, max_chars=6000) -> str. For every file not under the test dir (path not starting with
test_dir + "/"), in path order, for every symbol of kind "function", "class" or "constant" (not "method") that has
at least one user: one line
    f"{name} ({path}): used by {', '.join(code users) or 'nothing'}; tests: {', '.join(test files) or 'none'}"
where code users are its users outside the test dir (as users() gives them) and test files are the distinct paths
of its users inside the test dir, sorted. Lines are joined with "\n". When the text would be longer than max_chars,
it keeps the first lines that fit within max_chars and adds a last line "... (cut)". No lines: ""."""
from stratos import codemap


SETTINGS = {"source_dirs": ["src"], "test_dir": "tests"}


def project(tmp_path):
    (tmp_path / "src" / "ui").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "towers.js").write_text(
        "export const TOWER_TYPES = { rapid: { damage: 2 } };\n\n"
        "export function towerStats(t) {\n  return TOWER_TYPES[t.type];\n}\n", encoding="utf-8")
    (tmp_path / "src" / "step.js").write_text(
        'import { TOWER_TYPES } from "./towers.js";\n\n'
        "export function step(s) {\n  return TOWER_TYPES.rapid.damage + s.gold;\n}\n", encoding="utf-8")
    (tmp_path / "src" / "ui" / "render.js").write_text(
        "export function draw(ctx, s) {\n  ctx.fill(s.gold);\n}\n", encoding="utf-8")
    (tmp_path / "src" / "notes.txt").write_text("TOWER_TYPES\n", encoding="utf-8")
    (tmp_path / "tests" / "step.test.js").write_text(
        'import { step } from "../src/step.js";\n\n'
        'test("s", () => {\n  step({ gold: 1 });\n});\n', encoding="utf-8")
    # (task codemap_imports: a user counts only when its file imports the defining module)
    (tmp_path / "tests" / "helper.py").write_text("from towers import towerStats\n\n\ndef use():\n    return towerStats(1)\n",
                                                  encoding="utf-8")
    return tmp_path


def test_build(tmp_path):
    cmap = codemap.build(project(tmp_path), SETTINGS)
    assert cmap["test_dir"] == "tests"
    assert list(cmap["files"]) == ["src/step.js", "src/towers.js", "src/ui/render.js", "tests/helper.py",
                                   "tests/step.test.js"]
    assert [s["name"] for s in cmap["files"]["src/towers.js"]] == ["TOWER_TYPES", "towerStats"]
    assert [s["name"] for s in cmap["files"]["tests/helper.py"]] == ["use"]


def test_missing_folders(tmp_path):
    assert codemap.build(tmp_path, SETTINGS) == {"test_dir": "tests", "files": {}, "imports": {}}


def test_users(tmp_path):
    cmap = codemap.build(project(tmp_path), SETTINGS)
    assert codemap.users(cmap, "TOWER_TYPES") == ["src/step.js:step", "src/towers.js:towerStats"]
    assert codemap.users(cmap, "gold") == ["src/step.js:step", "src/ui/render.js:draw", "tests/step.test.js:test: s"]
    assert codemap.users(cmap, "nobody") == []


def test_uses_summary(tmp_path):
    cmap = codemap.build(project(tmp_path), SETTINGS)
    # (codemap_top_level: the test's top-level test(...) call now counts as a use of step)
    assert codemap.uses_summary(cmap) == "\n".join([
        "step (src/step.js): used by nothing; tests: tests/step.test.js",
        "TOWER_TYPES (src/towers.js): used by src/step.js:step, src/towers.js:towerStats; tests: none",
        "towerStats (src/towers.js): used by nothing; tests: tests/helper.py",
    ])


def test_step_is_used_by_a_test_only(tmp_path):
    p = project(tmp_path)
    (p / "tests" / "step.test.js").write_text('import { step } from "../src/step.js";\nstep(1);\n'
                                             "export function t() {\n  return step(2);\n}\n", encoding="utf-8")
    summary = codemap.uses_summary(codemap.build(p, SETTINGS))
    assert "step (src/step.js): used by nothing; tests: tests/step.test.js" in summary.splitlines()


def test_cut(tmp_path):
    cmap = codemap.build(project(tmp_path), SETTINGS)
    first = "step (src/step.js): used by nothing; tests: tests/step.test.js"
    assert codemap.uses_summary(cmap, max_chars=len(first) + 5) == first + "\n... (cut)"
    assert codemap.uses_summary({"test_dir": "tests", "files": {}}) == ""


# ---- was test_codemap_end.py ----
# Tests for task codemap_end: every code map symbol also has "end", its last line (memory M2 cuts code into chunks).
#
# scan_python: "end" = node.end_lineno for functions, classes, methods and constants; for "(top level)" the
# end_lineno of the last collected statement.
# scan_js: "end" = the 1-based number of the declaration's last line (the line its walk ended on); for "(top level)"
# the 1-based number of the last non-blank line that belongs to the top-level code.
# A JS "(top level)" symbol also has "lines": the sorted 1-based numbers of its top-level code lines (in no declaration
# and not import lines), from "line" to "end".
# codemap.symbol_text(text, sym) -> the lines of text with the numbers in sym["lines"] when the symbol has it, else
# the lines sym["line"] .. sym["end"], joined with a newline.


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
        ("g", 3, 5), ("K", 7, 7), ("test: x", 10, 12), ("(top level)", 8, 8)]   # (codemap_tests)
    by = {s["name"]: s for s in syms}
    assert codemap.symbol_text(JS, by["g"]) == "export function g(s) {\n  return a(s);\n}"
    assert by["(top level)"]["lines"] == [8]
    assert codemap.symbol_text(JS, by["(top level)"]) == "run(K);"
    assert codemap.symbol_text(JS, by["test: x"]) == 'test("x", () => {\n  g(1);\n});'
