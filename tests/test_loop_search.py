"""Tests for task search_kind (P16, BACKLOG item 16, 2026-11-21): a one-shot coder cannot design data that must meet a
measurable rule (Orbit T007's fourth level, Lumen T002's solvable levels). A "search" task has the model write a small
generator or solver; the harness runs it and keeps what it prints as the data file.

A task with "output": "<path>" (set by `stratos add --output PATH`) is a search task. loop._judge, after the syntax
check of the written files (and before lint and the tests): for each written file it runs the first one in
task["files"] with python (".py") or node (".js", ".mjs") in the worktree (cwd = wt, timeout loop.SEARCH_TIMEOUT_S = 60 s,
PYTHONIOENCODING=utf-8); exit code 0 -> its stdout is written to wt/<output> (folders made) and the steps go on;
a non-zero exit -> "search_failed" with f"The generator {script} failed (exit {code}):\\n" + the last 2000
characters of stderr; a timeout -> "search_failed" with f"The generator {script} ran longer than {SEARCH_TIMEOUT_S} s.". A task
without "output" is judged as before. The output path is never one of the task's files (the model does not write it).
Store.add_task(..., output=None) keeps "output" only when given."""
import json

from stratos import config, loop, verify
from stratos.state import Store

GEN = "FILE: tools/gen.py\n```python\nimport json\nprint(json.dumps([n * n for n in range(4)]))\n```\n"
BAD = "FILE: tools/gen.py\n```python\nimport sys\nprint('half', file=sys.stderr)\nsys.exit(3)\n```\n"
SLOW = "FILE: tools/gen.py\n```python\nimport time\ntime.sleep(5)\n```\n"
TASK = {"id": "T1", "title": "levels", "goal": "write squares", "files": ["tools/gen.py"], "protected": [],
        "tests": ["tests/test_x.py"], "output": "data/squares.json"}


def test_the_generator_output_becomes_the_data_file(tmp_path, monkeypatch):
    monkeypatch.setattr(verify, "run_tests", lambda w, tests: (True, "1 passed"))
    result, detail = loop.check_answer(TASK, tmp_path, GEN)
    assert result == "passed"
    assert json.loads((tmp_path / "data" / "squares.json").read_text(encoding="utf-8")) == [0, 1, 4, 9]


def test_the_output_is_written_as_printed(tmp_path, monkeypatch):
    """(Claude, 2026-11-21, Lantern) on Windows write_text turned the printed "\\n" into "\\r\\n", so the saved file
    differed from the generator's own output."""
    monkeypatch.setattr(verify, "run_tests", lambda w, tests: (True, "1 passed"))
    assert loop.check_answer(TASK, tmp_path, GEN)[0] == "passed"
    assert (tmp_path / "data" / "squares.json").read_bytes() == b"[0, 1, 4, 9]\n"


def test_a_failing_generator(tmp_path, monkeypatch):
    runs = []
    monkeypatch.setattr(verify, "run_tests", lambda w, tests: runs.append(1) or (True, ""))
    result, detail = loop.check_answer(TASK, tmp_path, BAD)
    assert result == "search_failed" and runs == []
    assert detail.startswith("The generator tools/gen.py failed (exit 3):\n") and "half" in detail
    assert not (tmp_path / "data" / "squares.json").exists()


def test_a_long_error_keeps_both_ends(tmp_path, monkeypatch):
    """(Claude, 2026-11-21, Lantern) node prints the error line first and a long stack after it; keep both."""
    long = ("FILE: tools/gen.py\n```python\nimport sys\nprint('TypeError: row.split is not a function', file=sys.stderr)\n"
            "print('x' * 3000, file=sys.stderr)\nprint('Node.js v24', file=sys.stderr)\nsys.exit(1)\n```\n")
    result, detail = loop.check_answer(TASK, tmp_path, long)
    assert result == "search_failed" and "row.split is not a function" in detail and detail.rstrip().endswith("v24")
    assert "\n...\n" in detail


def test_a_slow_generator(tmp_path, monkeypatch):
    monkeypatch.setattr(loop, "SEARCH_TIMEOUT_S", 1)
    result, detail = loop.check_answer(TASK, tmp_path, SLOW)
    assert result == "search_failed" and detail == "The generator tools/gen.py ran longer than 1 s."


def test_plain_tasks_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(verify, "run_tests", lambda w, tests: (True, "ok"))
    plain = {k: v for k, v in TASK.items() if k != "output"}
    assert loop.check_answer(plain, tmp_path, GEN) == ("passed", "ok")
    assert not (tmp_path / "data").exists()


def test_store_keeps_output_only_when_given(tmp_path):
    s = Store(tmp_path / "state")
    a = s.add_task("a", "g", ["tools/gen.py"], [], ["tests/t.py"], output="data/x.json")
    b = s.add_task("b", "g", ["x.py"], [], ["tests/t.py"])
    assert s.get(a["id"])["output"] == "data/x.json" and "output" not in s.get(b["id"])


def test_cli_add_output(tmp_path, monkeypatch):
    from stratos import __main__ as cli
    from stratos import codemap
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path)
    monkeypatch.setattr(codemap, "build", lambda root: {"test_dir": "tests", "files": {}, "imports": {}})
    assert cli.main(["add", "--title", "t", "--goal", "g", "--files", "tools/gen.py", "--tests", "tests/t.py",
                     "--role", "coder", "--output", "data/levels.json"]) == 0
    assert Store(tmp_path / "state").tasks()[-1]["output"] == "data/levels.json"
