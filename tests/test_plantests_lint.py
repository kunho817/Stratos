"""Tests for task drafts_lint (P11, 2026-11-20, trial 11): a draft held a half-written first copy of a test (same name
as the real one, `pass` inside) and no check saw it; drafts also used names they never imported. And old test files
of a task were printed as "missing".

lint.check(root, paths, codes=lint.ERRORS): the ruff codes to select are a parameter now (default as before).
plantests.draft_problems(root, path) -> list of lint lines for a written Python draft: lint.check(root, [path],
codes=("F811", "F821", "F822", "F823")) - a redefined name (a test defined twice) or an undefined name.
plantests.draft_tests: after a .py draft is collected, its problems are logged one per line as f"{path}: lint:
{line}" and saved in its result entry as entry["lint"] (only when there are some; the status stays "collected").
A test path of a task that the answer did not write but that already exists under root gets the status "old"
(not "missing"); "missing" stays for paths that are neither written nor there."""
import pytest

from stratos import lint, plantests


@pytest.fixture
def drafts(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_d.py").write_text(
        "def test_a():\n    pass\n\n\ndef test_a():\n    assert helper() == 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_ok.py").write_text("def test_b():\n    assert 1\n", encoding="utf-8")
    return tmp_path


def test_lint_codes_parameter(drafts):
    if not lint.available():
        pytest.skip("ruff is not installed")
    lines = lint.check(drafts, ["tests/test_d.py"], codes=("F811",))
    assert len(lines) == 1 and "F811" in lines[0]
    assert all("F811" not in x for x in lint.check(drafts, ["tests/test_d.py"]))


def test_draft_tests_logs_lint_and_marks_old_files(tmp_path, monkeypatch):
    import json

    from stratos import codemap, config
    from test_plantests_outdated import FakeGateway
    if not lint.available():
        pytest.skip("ruff is not installed")
    state = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    monkeypatch.setattr(plantests, "check_draft", lambda root, path: ("collected", ""))
    monkeypatch.setattr(plantests, "suite_leaks", lambda root, path, ignore=(): [])
    monkeypatch.setattr(codemap, "build", lambda r: {"test_dir": "tests", "files": {}, "imports": {}})
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_old.py").write_text("def test_o():\n    pass\n", encoding="utf-8")
    (state / "plans").mkdir(parents=True)
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_new.py", "tests/test_old.py", "tests/test_gone.py"],
            "protected": [], "after": [], "role": None}
    (state / "plans" / "P001.json").write_text(json.dumps({"id": "P001", "goal": "G", "tasks": [task],
                                                           "status": "draft", "hash": "h"}), encoding="utf-8")
    answer = "FILE: tests/test_new.py\n```python\ndef test_a():\n    pass\n\n\ndef test_a():\n    assert 1\n```\n"
    lines = []
    results = plantests.draft_tests(FakeGateway(answer), "P001", root, state, log=lines.append)
    by = {r["file"]: r for r in results}
    assert by["tests/test_new.py"]["status"] == "collected"
    assert any("F811" in x for x in by["tests/test_new.py"]["lint"])
    assert any(x.startswith("tests/test_new.py: lint: ") and "F811" in x for x in lines)
    assert by["tests/test_old.py"]["status"] == "old" and "lint" not in by["tests/test_old.py"]
    assert by["tests/test_gone.py"]["status"] == "missing"


def test_draft_problems(drafts):
    if not lint.available():
        pytest.skip("ruff is not installed")
    lines = plantests.draft_problems(drafts, "tests/test_d.py")
    assert any("F811" in x and "test_a" in x for x in lines)
    assert any("F821" in x and "helper" in x for x in lines)
    assert plantests.draft_problems(drafts, "tests/test_ok.py") == []
