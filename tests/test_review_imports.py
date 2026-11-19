"""Tests for task review_imports (P4, 2026-11-20): the reviewer sees the import lines of every changed file.
Experiment (c) (scratchpad review_eval.py, 10 review cases from trials 5-7 with a known verdict, 2 runs): Qwen3.6
9/10 and 9/10, Tiel 8/8, Swift 6/5, Flint 4/4 - the reviewer stays. Every model called Pantry T013-a11 wrong for
"json.dumps without import json": the import was already in the file, so it was not in the diff.

review.import_lines(root, paths) -> text: for each path (in order) that exists under root and ends with .py, .js or
.mjs, a block f"{path}:\n" + the lines of the file (after the change) that start at column 0 with "import " or
"from " (for .py) or with "import " (for .js/.mjs), joined by "\n"; a file with no such line gives
f"{path}:\n(no imports)". Blocks are joined by "\n\n". No paths give "".

review.build_messages(task, diff, files=None, imports=None): with imports (non-empty text), the part
"IMPORTS OF THE CHANGED FILES (after the change; lines outside the diff exist too):\n" + imports + "\n\n" comes right
before "Diff:" (after the PROJECT FILES part when both are given). Without imports the message is as before.

review.changed_paths(diff) -> the paths of the "+++ b/<path>" lines of a unified diff, in order, each once.
loop.review_tasks passes imports=review.import_lines(wt, review.changed_paths(diff_text))."""
from stratos import review

TASK = {"id": "T013", "title": "json", "goal": "Add --json; import json at the top."}
DIFF = "--- a/pantry/cli.py\n+++ b/pantry/cli.py\n@@ -90,1 +90,2 @@\n+    print(json.dumps(x))\n"


def test_import_lines(tmp_path):
    (tmp_path / "pantry").mkdir()
    (tmp_path / "pantry" / "cli.py").write_text(
        '"""cli"""\nimport argparse\nimport json\nfrom pantry.units import convert\n\n\ndef f():\n    import os\n',
        encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.js").write_text('import { b } from "./b.js";\nconst x = 1;\n', encoding="utf-8")
    (tmp_path / "src" / "c.js").write_text("const y = 2;\n", encoding="utf-8")
    text = review.import_lines(tmp_path, ["pantry/cli.py", "src/a.js", "src/c.js", "README.md", "gone.py"])
    assert text == ("pantry/cli.py:\nimport argparse\nimport json\nfrom pantry.units import convert\n\n"
                    "src/a.js:\nimport { b } from \"./b.js\";\n\nsrc/c.js:\n(no imports)")
    assert review.import_lines(tmp_path, []) == ""


def test_changed_paths():
    diff = DIFF + "--- a/x.py\n+++ b/x.py\n@@\n+1\n--- a/pantry/cli.py\n+++ b/pantry/cli.py\n"
    assert review.changed_paths(diff) == ["pantry/cli.py", "x.py"]
    assert review.changed_paths("") == []


def test_build_messages_with_imports():
    user = review.build_messages(TASK, DIFF, files=["pantry/cli.py"], imports="pantry/cli.py:\nimport json")[1]["content"]
    part = ("IMPORTS OF THE CHANGED FILES (after the change; lines outside the diff exist too):\n"
            "pantry/cli.py:\nimport json\n\nDiff:")
    assert part in user
    assert user.index("PROJECT FILES") < user.index("IMPORTS OF THE CHANGED FILES")
    assert review.build_messages(TASK, DIFF) == review.build_messages(TASK, DIFF, imports=None)
    assert "IMPORTS OF" not in review.build_messages(TASK, DIFF, imports="")[1]["content"]
