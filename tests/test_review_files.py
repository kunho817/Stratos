"""Tests for task review_files (P3, 2026-11-20): the reviewer sees which project files exist. In Pantry T006 the
reviewer demanded `from pantry.pantry_mgmt import ...` because the planner's goal named the task key "pantry_mgmt";
pantry/pantry_mgmt.py never existed and the change broke the import.

review.project_files(root, settings=None) -> sorted POSIX paths (relative to root) of every file under each of
settings["source_dirs"] (default config.PROJECT), recursive, leaving out __pycache__ folders and .pyc files.

review.build_messages(task, diff, files=None): with files (a non-empty list), the user message holds, right before
"Diff:", the part "PROJECT FILES (every module that exists; a name that is not here is not a module):\n" followed by
one path per line and a blank line. Without files the message is exactly as before.

loop.review_tasks passes files=review.project_files(wt) for each task's worktree wt."""
from pathlib import Path

from stratos import config, review

TASK = {"id": "T006", "title": "cli", "goal": "use the functions from pantry_mgmt"}


def test_project_files(tmp_path):
    for p in ["pantry/__init__.py", "pantry/cli.py", "pantry/sub/x.py", "pantry/__pycache__/cli.cpython-312.pyc",
              "pantry/old.pyc", "tests/test_cli.py", "README.md"]:
        f = tmp_path / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("", encoding="utf-8")
    settings = {"source_dirs": ["pantry"]}
    assert review.project_files(tmp_path, settings) == ["pantry/__init__.py", "pantry/cli.py", "pantry/sub/x.py"]
    assert review.project_files(tmp_path, {"source_dirs": ["missing"]}) == []


def test_build_messages_with_files():
    user = review.build_messages(TASK, "+x = 1", files=["pantry/cli.py", "pantry/pantry.py"])[1]["content"]
    part = ("PROJECT FILES (every module that exists; a name that is not here is not a module):\n"
            "pantry/cli.py\npantry/pantry.py\n\nDiff:")
    assert part in user


def test_build_messages_without_files_is_unchanged():
    assert review.build_messages(TASK, "+x = 1") == review.build_messages(TASK, "+x = 1", files=None)
    assert "PROJECT FILES" not in review.build_messages(TASK, "+x = 1")[1]["content"]
    assert "PROJECT FILES" not in review.build_messages(TASK, "+x = 1", files=[])[1]["content"]


def test_review_tasks_passes_the_files(tmp_path, monkeypatch):
    from stratos import gitops, loop
    from stratos.state import Store
    from stratos.telemetry import Telemetry

    wt = tmp_path / "wt"
    (wt / "pantry").mkdir(parents=True)
    (wt / "pantry" / "pantry.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "source_dirs": ["pantry"]})
    monkeypatch.setattr(gitops, "commit_diff", lambda w: "+x = 1")
    monkeypatch.setattr(gitops, "finalize_commit_message", lambda w, msg: None)
    store = Store(tmp_path / "state")
    t = store.add_task("cli", "g", ["pantry/cli.py"], [], ["tests/x.py"])
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
    assert "PROJECT FILES" in seen[0] and "pantry/pantry.py" in seen[0]
