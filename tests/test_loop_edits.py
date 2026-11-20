"""Tests for task loop_edits (P8, 2026-11-20, after patch_edits): the coder answers existing files with edit blocks.

context.coder_system(language) also says: for a file that already exists, answer with SEARCH/REPLACE edit blocks
(the format with "<<<<<<< SEARCH", "=======", ">>>>>>> REPLACE"), the SEARCH lines copied exactly from the file shown
and found exactly once, a few lines around each change; for a new file, the whole file as before. The text contains
"<<<<<<< SEARCH" and "copied exactly".

loop.check_answer: edits = patch.parse_edits(text, allowed); whole-file blocks for paths that have edits are ignored
(a fenced edit section must not become the file's content). The edited files are rendered with patch.render_edits
and then go through the same steps as whole files (dropped definitions, apply_files with its protected check,
syntax, lint, tests). An EditMismatch gives result "edit_mismatch" with detail str(error) + "\nCopy the SEARCH lines
exactly from the file as shown above, or write the whole file." Nothing in the answer -> "no_files" as before."""
from stratos import config, context, loop, verify

SRC = "def a():\n    return 1\n\n\ndef b():\n    return 2\n"
TASK = {"id": "T001", "title": "t", "goal": "make a return 10", "files": ["pkg/m.py", "pkg/new.py"],
        "protected": ["tests/x.py"], "tests": ["tests/x.py"]}


def setup(tmp_path, monkeypatch, outs):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text(SRC, encoding="utf-8")
    runs = []
    monkeypatch.setattr(verify, "run_tests", lambda w, tests: runs.append(1) or outs.pop(0))
    return runs


def block(s, r):
    return f"<<<<<<< SEARCH\n{s}\n=======\n{r}\n>>>>>>> REPLACE\n"


def test_system_prompt_describes_edits():
    text = context.coder_system("Python")
    assert "<<<<<<< SEARCH" in text and ">>>>>>> REPLACE" in text and "copied exactly" in text


def test_an_edit_is_applied_and_tested(tmp_path, monkeypatch):
    runs = setup(tmp_path, monkeypatch, [(True, "1 passed")])
    answer = "FILE: pkg/m.py\n" + block("    return 1", "    return 10")
    assert loop.check_answer(TASK, tmp_path, answer) == ("passed", "1 passed")
    assert (tmp_path / "pkg" / "m.py").read_text(encoding="utf-8") == SRC.replace("return 1\n", "return 10\n")


def test_a_fenced_edit_section_does_not_become_the_file(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, [(True, "ok")])
    answer = "FILE: pkg/m.py\n```python\n" + block("    return 1", "    return 10") + "```\n"
    assert loop.check_answer(TASK, tmp_path, answer)[0] == "passed"
    text = (tmp_path / "pkg" / "m.py").read_text(encoding="utf-8")
    assert "SEARCH" not in text and "return 10" in text


def test_edits_and_a_new_whole_file_together(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, [(True, "ok")])
    answer = ("FILE: pkg/m.py\n" + block("    return 1", "    return 10")
              + "FILE: pkg/new.py\n```python\nN = 1\n```\n")
    assert loop.check_answer(TASK, tmp_path, answer)[0] == "passed"
    assert (tmp_path / "pkg" / "new.py").read_text(encoding="utf-8") == "N = 1\n"


def test_a_mismatch_is_reported(tmp_path, monkeypatch):
    runs = setup(tmp_path, monkeypatch, [])
    answer = "FILE: pkg/m.py\n" + block("    return 99", "    return 10")
    result, detail = loop.check_answer(TASK, tmp_path, answer)
    assert result == "edit_mismatch" and runs == []
    assert detail.startswith("pkg/m.py: the SEARCH text was found 0 times")
    assert detail.endswith("\nCopy the SEARCH lines exactly from the file as shown above, or write the whole file.")
    assert (tmp_path / "pkg" / "m.py").read_text(encoding="utf-8") == SRC


def test_dropped_definitions_are_still_caught(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, [])
    answer = "FILE: pkg/m.py\n" + block("\n\ndef b():\n    return 2", "")
    assert loop.check_answer(TASK, tmp_path, answer)[0] == "dropped_defs"


def test_an_edit_of_a_protected_file_is_refused(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, [])
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "x.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    task = dict(TASK, files=["pkg/m.py", "tests/x.py"])
    answer = "FILE: tests/x.py\n" + block("    assert True", "    assert 1")
    assert loop.check_answer(task, tmp_path, answer)[0] == "refused"
