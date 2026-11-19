"""Tests for task codemap_imports: users are counted only in files that import the defining module (memory M1).

Found by the first wiki run (2026-11-19): users() matches by name only, so plan.py's page said diagnose.py, triage.py,
wiki.py ... use plan.build_messages - they have their own build_messages. The same noise reached the planner's
WHO USES WHAT and the search expansion.

codemap.imports_python(text) -> sorted distinct list of module names a Python file imports: for `import a.b.c` (or
`import a.b.c as x`) the last part "c"; for `from a.b import x, y` the last part of the module ("b") and the names
x and y; for `from . import x` (no module) the names. Anywhere in the file (also inside functions). A file that does
not parse -> [].
codemap.imports_js(text) -> sorted distinct list of the stems of the module specifiers of `import ... from "<spec>"`,
`export ... from "<spec>"`, `import "<spec>"`, `import("<spec>")` and `require("<spec>")` (quotes ' or "):
the last path part without its extension ("./towers.js" -> "towers", "../src/ui/render.mjs" -> "render").
codemap.module_name(path) -> the stem of the path's last part, except that "__init__" and "index" give the folder
name ("pkg/__init__.py" -> "pkg", "src/ui/index.js" -> "ui", "top.py" -> "top").

build adds "imports": {path: imports_python or imports_js of that file} for every file in "files" (same order).

users(cmap, name, path=None): path None -> as before. With path (where name is defined): only users whose file is
path itself or whose file's imports (cmap["imports"]) contain module_name(path); a cmap without "imports" -> as
before. uses_summary passes each symbol's path."""
from stratos import codemap

SETTINGS = {"source_dirs": ["src"], "test_dir": "tests"}


def test_imports_python():
    text = ("import os\nimport stratos.codemap as cm\nfrom stratos import plan as plan_mod, config\n"
            "from .gateway import Gateway\nfrom . import learn\n\n"
            "def f():\n    import json\n    return 1\n")
    assert codemap.imports_python(text) == sorted({"os", "codemap", "stratos", "plan", "config", "gateway", "Gateway",
                                                   "learn", "json"})
    assert codemap.imports_python("def broken(:\n") == []


def test_imports_js():
    text = ('import { a, b } from "./towers.js";\nimport * as g from \'../src/grid.js\';\n'
            'export { c } from "./ui/render.mjs";\nimport "./side.js";\nconst m = await import("./lazy.js");\n'
            'const fs = require("fs");\nconst s = "not from ./fake.js";\n')
    assert codemap.imports_js(text) == ["fs", "grid", "lazy", "render", "side", "towers"]


def test_module_name():
    assert codemap.module_name("pkg/__init__.py") == "pkg"
    assert codemap.module_name("src/ui/index.js") == "ui"
    assert codemap.module_name("top.py") == "top"
    assert codemap.module_name("src/towers.js") == "towers"


def project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "plan.py").write_text("def build_messages(g):\n    return [g]\n", encoding="utf-8")
    (tmp_path / "src" / "triage.py").write_text(
        "def build_messages(t):\n    return [t]\n\ndef ask(t):\n    return build_messages(t)\n", encoding="utf-8")
    (tmp_path / "src" / "cli.py").write_text(
        "from src import plan as plan_mod\n\ndef main():\n    return plan_mod.build_messages(1)\n", encoding="utf-8")
    (tmp_path / "tests" / "test_plan.py").write_text(
        "from src import plan\n\ndef test_b():\n    assert plan.build_messages(1)\n", encoding="utf-8")
    return tmp_path


def test_build_records_imports(tmp_path):
    cmap = codemap.build(project(tmp_path), SETTINGS)
    assert list(cmap["imports"]) == list(cmap["files"])
    assert cmap["imports"]["src/cli.py"] == ["plan", "src"]
    assert cmap["imports"]["src/plan.py"] == []


def test_users_by_definition(tmp_path):
    cmap = codemap.build(project(tmp_path), SETTINGS)
    everyone = ["src/cli.py:main", "src/triage.py:ask", "tests/test_plan.py:test_b"]
    assert codemap.users(cmap, "build_messages") == everyone
    assert codemap.users(cmap, "build_messages", "src/plan.py") == ["src/cli.py:main", "tests/test_plan.py:test_b"]
    assert codemap.users(cmap, "build_messages", "src/triage.py") == ["src/triage.py:ask"]
    old = {"test_dir": "tests", "files": cmap["files"]}
    assert codemap.users(old, "build_messages", "src/plan.py") == everyone


def test_uses_summary_by_definition(tmp_path):
    summary = codemap.uses_summary(codemap.build(project(tmp_path), SETTINGS))
    assert summary.splitlines() == [
        "build_messages (src/plan.py): used by src/cli.py:main; tests: tests/test_plan.py",
        "build_messages (src/triage.py): used by src/triage.py:ask; tests: none",
    ]
