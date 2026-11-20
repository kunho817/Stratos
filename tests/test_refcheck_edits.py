"""Tests for task refcheck_edits (P8, 2026-11-20, found in trial Pantry round 3): the reference writer never saw the
files it had to change (build_messages left the task's own files out) and had to write them whole - its cli.py broke
and all three tasks of the round got false flags (13 of 14, 1 of 1 "interface"). Now it sees them and answers with
edit blocks, like the coder.

refcheck.SYSTEM: says the writer does not see the tests and gives both formats - edit blocks (contains
"<<<<<<< SEARCH" and ">>>>>>> REPLACE") for a file that exists, the whole file in a FILE block for a new one.
refcheck.build_messages(task, root): after "WRITE THESE FILES: ...", each of task["files"] that exists under root is
shown as f"FILE YOU MAY CHANGE {path}:\n```\n{text}\n```" (before the other EXISTING FILE parts); a task file that
does not exist is not shown. Never a test file.
refcheck.check: reads the answer like loop.check_answer does - patch.parse_edits rendered with patch.render_edits,
plus whole files from patch.parse_files for paths without edits; an EditMismatch gives status "error" with
first_error str(error) and "files": []; nothing usable -> status "error", "no file in the answer". The answer is saved
as config.STATE_DIR / "answers" / f"{plan_id}-{task['key']}-reference.md"."""
from stratos import config, refcheck

TASK = {"key": "cli", "title": "cli", "goal": "add a double command", "files": ["pkg/cli.py"],
        "tests": ["tests/test_cli.py"]}
CLI = "def main(argv):\n    if argv[0] == 'one':\n        return 1\n    return 0\n"
TESTS = ("from pkg.cli import main\n\n\ndef test_one():\n    assert main(['one']) == 1\n\n\n"
         "def test_double():\n    assert main(['double']) == 2\n")
EDIT = ("FILE: pkg/cli.py\n<<<<<<< SEARCH\n    if argv[0] == 'one':\n        return 1\n=======\n"
        "    if argv[0] == 'one':\n        return 1\n    if argv[0] == 'double':\n        return 2\n>>>>>>> REPLACE\n")
BAD_EDIT = "FILE: pkg/cli.py\n<<<<<<< SEARCH\n    if argv[0] == 'two':\n=======\n    pass\n>>>>>>> REPLACE\n"


class GW:
    def __init__(self, answer):
        self.answer = answer

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        return "c1", self.answer


def project(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "cli.py").write_text(CLI, encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_cli.py").write_text(TESTS, encoding="utf-8")
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "source_dirs": ["pkg"],
                                            "test_command": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]})
    monkeypatch.setattr(config, "REF_WRITER", {"model": "m", "effort": "low", "max_tokens": 9})
    return root


def test_system_prompt_has_both_formats():
    assert "<<<<<<< SEARCH" in refcheck.SYSTEM and ">>>>>>> REPLACE" in refcheck.SYSTEM
    assert "FILE:" in refcheck.SYSTEM and "tests" in refcheck.SYSTEM


def test_the_files_to_change_are_shown(tmp_path, monkeypatch):
    root = project(tmp_path, monkeypatch)
    user = refcheck.build_messages(dict(TASK, files=["pkg/cli.py", "pkg/new.py"]), root)[1]["content"]
    shown = f"FILE YOU MAY CHANGE pkg/cli.py:\n```\n{CLI}\n```"
    assert shown in user
    assert user.index(shown) < user.index("EXISTING FILE pkg/__init__.py")
    assert "pkg/new.py:" not in user and "test_double" not in user


def test_an_edit_answer_is_used_and_saved(tmp_path, monkeypatch):
    root = project(tmp_path, monkeypatch)
    r = refcheck.check(GW(EDIT), "P003", TASK, root, ["tests/test_cli.py"])
    assert r["status"] == "agree" and r["total"] == 2
    assert r["files"][0][0] == "pkg/cli.py" and "'double'" in r["files"][0][1]
    saved = tmp_path / "state" / "answers" / "P003-cli-reference.md"
    assert saved.read_text(encoding="utf-8") == EDIT
    assert (root / "pkg" / "cli.py").read_text(encoding="utf-8") == CLI


def test_a_mismatch_is_an_error(tmp_path, monkeypatch):
    root = project(tmp_path, monkeypatch)
    r = refcheck.check(GW(BAD_EDIT), "P003", TASK, root, ["tests/test_cli.py"])
    assert r["status"] == "error" and r["files"] == []
    assert r["first_error"].startswith("pkg/cli.py: the SEARCH text was found 0 times")
