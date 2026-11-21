"""Tests for task cases_js (P17, 2026-11-21, trial 15): cases.py wrote pytest files only, and the JS test writer flipped
the wrong board columns in 7 of 15 Lantern tests. The same case lines (parsed as before) can become a node:test file.

cases.render(parsed, language="python"): language "javascript" gives a node:test file:
  line 1 "// Tests written by Stratos from the cases Claude gave (stratos/cases.py).",
  'import { test } from "node:test";', 'import assert from "node:assert/strict";', then the IMPORT lines as written,
  then per module (first-use order) f'import {{ {", ".join(sorted names)} }} from "../{module with "." -> "/"}.js";',
  then a blank line and one test per case, named f"{name} {n}" (n per name from 1):
  eq:     f'test("{name} {n}", () => {{\\n  assert.deepEqual({call}, {expected});\\n}});'
  raises: f'test("{name} {n}", () => {{\\n  assert.throws(() => {call}, (e) => e instanceof {error}' + (message is
          None ? "" : f' && e.message.includes({json.dumps(message)})') + ');\\n});'
  tests separated by one blank line, the file ending with one newline. language "python" is as before.
`stratos cases FILE --out PATH` uses "javascript" when PATH ends with ".js" or ".mjs"; plan-tests uses
config.PROJECT["language"]."""
import shutil
import subprocess

import pytest

from stratos import cases

TEXT = """IMPORT import { EMPTY } from "../src/consts.js";
src.board.press(["....", "....", "....", "...."], 0, 0) == ["##..", "#...", "....", "...."]
src.board.solved(["....", "....", "....", "...."]) == true
src.solver.minPresses(["#...", "....", "....", "...."]) == -1
src.board.press(null, 0, 0) raises TypeError
src.board.parse("x") raises Error: bad board "x"
"""


def test_render_javascript():
    text = cases.render(cases.parse(TEXT), language="javascript")
    lines = text.splitlines()
    assert lines[:6] == ["// Tests written by Stratos from the cases Claude gave (stratos/cases.py).",
                         'import { test } from "node:test";', 'import assert from "node:assert/strict";',
                         'import { EMPTY } from "../src/consts.js";',
                         'import { parse, press, solved } from "../src/board.js";',
                         'import { minPresses } from "../src/solver.js";']
    assert ('test("press 1", () => {\n  assert.deepEqual(press(["....", "....", "....", "...."], 0, 0), '
            '["##..", "#...", "....", "...."]);\n});') in text
    assert 'test("solved 1", () => {\n  assert.deepEqual(solved(["....", "....", "....", "...."]), true);\n});' in text
    assert ('test("press 2", () => {\n  assert.throws(() => press(null, 0, 0), (e) => e instanceof TypeError);\n});'
            in text)
    assert ('assert.throws(() => parse("x"), (e) => e instanceof Error && e.message.includes("bad board \\"x\\""));'
            in text)
    assert text.endswith("});\n")
    assert cases.render(cases.parse("m.f(1) == 2\n")).startswith('"""Tests written by Stratos')


def test_the_js_file_runs(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (tmp_path / "src" / "m.js").write_text(
        "export function f(x) { if (x < 0) throw new RangeError(`bad ${x}`); return [x, x * 2]; }\n", encoding="utf-8")
    body = cases.render(cases.parse("src.m.f(2) == [2, 4]\nsrc.m.f(-1) raises RangeError: bad -1\nsrc.m.f(3) == [3, 7]\n"),
                        language="javascript")
    (tmp_path / "tests" / "m.test.js").write_text(body, encoding="utf-8")
    r = subprocess.run([node, "--test", "--test-reporter=tap", "tests/m.test.js"], cwd=tmp_path, capture_output=True,
                       text=True, encoding="utf-8")
    assert "# pass 2" in r.stdout and "# fail 1" in r.stdout, r.stdout
