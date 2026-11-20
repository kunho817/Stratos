"""Tests for task review_whole (P5, 2026-11-20, BACKLOG item 18): the reviewer judged hunks without the code around
them - Lumen T012 was blocked three times for "moves rises on rejected clicks" while every rejection returned early,
above the hunk; Pantry T013-a11 for a missing import that was there.

review.whole_files(root, paths, max_lines=300) -> (text, short): for each path in order that exists under root and
has fewer than max_lines lines, a block f"FILE AFTER THE CHANGE: {path}\n```\n{content}\n```" (content without a
trailing newline); text joins the blocks with "\n\n" ("" when none); short is the list of those paths.

review.build_messages(task, diff, files=None, imports=None, whole=None): with whole (non-empty text), the part
"WHOLE CHANGED FILES (judge the diff with the code around it):\n" + whole + "\n\n" comes right before "Diff:" (after
the PROJECT FILES and IMPORTS parts). Without it the message is as before.

loop.review_tasks: paths = review.changed_paths(diff_text); whole, short = review.whole_files(wt, paths);
imports = review.import_lines(wt, [p for p in paths if p not in short]); both are passed to build_messages."""
from stratos import review

TASK = {"id": "T012", "title": "moves", "goal": "count only real changes"}


def test_whole_files(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "game.js").write_text("export function f() {\n  return 1;\n}\n", encoding="utf-8")
    (tmp_path / "src" / "big.js").write_text("x\n" * 400, encoding="utf-8")
    text, short = review.whole_files(tmp_path, ["src/game.js", "src/big.js", "src/gone.js"])
    assert short == ["src/game.js"]
    assert text == "FILE AFTER THE CHANGE: src/game.js\n```\nexport function f() {\n  return 1;\n}\n```"
    assert review.whole_files(tmp_path, ["src/big.js"], max_lines=500)[1] == ["src/big.js"]
    assert review.whole_files(tmp_path, []) == ("", [])


def test_build_messages_with_whole_files():
    whole = "FILE AFTER THE CHANGE: src/game.js\n```\nif (bad) return state;\nmoves + 1\n```"
    user = review.build_messages(TASK, "+moves + 1", files=["src/game.js"], imports="src/x.js:\nimport { y }",
                                 whole=whole)[1]["content"]
    part = "WHOLE CHANGED FILES (judge the diff with the code around it):\n" + whole + "\n\nDiff:"
    assert part in user
    assert user.index("PROJECT FILES") < user.index("IMPORTS OF") < user.index("WHOLE CHANGED FILES")
    assert review.build_messages(TASK, "+x") == review.build_messages(TASK, "+x", whole=None)
    assert "WHOLE CHANGED" not in review.build_messages(TASK, "+x", whole="")[1]["content"]


def test_review_tasks_shows_short_files_whole(tmp_path, monkeypatch):
    from stratos import config, gitops, loop
    from stratos.state import Store
    from stratos.telemetry import Telemetry

    wt = tmp_path / "wt"
    (wt / "src").mkdir(parents=True)
    (wt / "src" / "game.js").write_text('import { a } from "./a.js";\nexport const MOVES = 1;\n', encoding="utf-8")
    (wt / "src" / "big.js").write_text('import { b } from "./b.js";\n' + "x\n" * 400, encoding="utf-8")
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "source_dirs": ["src"]})
    diff = "--- a/src/game.js\n+++ b/src/game.js\n+x\n--- a/src/big.js\n+++ b/src/big.js\n+y\n"
    monkeypatch.setattr(gitops, "commit_diff", lambda w: diff)
    monkeypatch.setattr(gitops, "finalize_commit_message", lambda w, msg: None)
    store = Store(tmp_path / "state")
    t = store.add_task("moves", "g", ["src/game.js"], [], ["tests/x.js"])
    store.update(t["id"], status="awaiting_review", worktree=str(wt), commit="abc", attempts=1)
    seen = []

    class GW:
        telemetry = Telemetry(tmp_path / "t.jsonl")

        def ensure_model(self, model):
            return 0.0

        def chat(self, messages, **kw):
            seen.append(messages[1]["content"])
            return "c1", '{"verdict": "approve", "issues": []}'
    loop.review_tasks(store, GW(), [t["id"]], log=lambda s: None)
    user = seen[0]
    assert "FILE AFTER THE CHANGE: src/game.js" in user and "export const MOVES = 1;" in user
    assert "FILE AFTER THE CHANGE: src/big.js" not in user
    assert 'src/big.js:\nimport { b } from "./b.js";' in user
    assert 'src/game.js:\nimport { a }' not in user
