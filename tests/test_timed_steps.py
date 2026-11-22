"""Tests for task timed_steps: six functions are wrapped in steps.timed so their
elapsed time is recorded as a "step" telemetry event.

refresh_memory -> "memory"; upkeep.after_run -> "upkeep"; codemap.build -> "codemap";
gitops.ensure_worktree -> "worktree"; gitops.commit_all -> "git"; preflight.check ->
"preflight".

Each test installs a fake telemetry via steps.use(tel), calls the function, and
checks that a "step" event with the matching name was recorded. Fakes stand in for
the gateway, git, embedder, and test runner; no GPU, repository, or network is needed."""
import subprocess
from pathlib import Path

import pytest

from stratos import __main__ as cli
from stratos import codemap, config, embed, gitops, memindex, preflight, steps, upkeep, verify


class FakeTel:
    def __init__(self):
        self.events = []

    def record(self, kind, **fields):
        self.events.append({"kind": kind, **fields})


@pytest.fixture(autouse=True)
def reset_steps():
    yield
    steps.use(None)


@pytest.fixture
def tel():
    t = FakeTel()
    steps.use(t)
    return t


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    (r / "a.py").write_text("A = 1\n", encoding="utf-8")
    gitops.git(r, "add", "-A")
    gitops.git(r, *gitops.BOT, "commit", "-q", "-m", "init")
    return r


def test_refresh_memory_records_the_step(tel, monkeypatch, tmp_path, capsys):
    # config.MEMORY must be True for the body to run; REPO and STATE_DIR go to tmp_path.
    # memindex.refresh and embed.Embedder are mocked so no real model or disk index is touched.
    monkeypatch.setattr(config, "MEMORY", True)
    monkeypatch.setattr(config, "REPO", tmp_path)
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(embed, "Embedder", lambda: None)
    monkeypatch.setattr(memindex, "refresh", lambda repo, state, emb: {"changed": 0, "embedded": 0})
    cli.refresh_memory()
    # Expect: exactly one "step" event; name must be "memory".
    step_events = [e for e in tel.events if e["kind"] == "step"]
    assert len(step_events) == 1
    assert step_events[0]["name"] == "memory"


def test_upkeep_after_run_records_the_step(tel, monkeypatch, tmp_path):
    # AUTO_LEARN and AUTO_WIKI off so the body finishes quickly (no model calls,
    # no codemap.build inside wiki). The timed wrapper still records.
    monkeypatch.setattr(config, "AUTO_LEARN", False)
    monkeypatch.setattr(config, "AUTO_WIKI", False)
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", tmp_path)

    class FakeStore:
        def tasks(self):
            return []

    # gw is unused when both flags are off; finished=[] skips the wiki branch.
    upkeep.after_run(None, FakeStore(), [])
    # Expect: one "step" event with name "upkeep".
    step_events = [e for e in tel.events if e["kind"] == "step"]
    assert len(step_events) == 1
    assert step_events[0]["name"] == "upkeep"


def test_codemap_build_records_the_step(tel, tmp_path):
    # settings: source_dirs = ["pkg"], test_dir = "tests"; one .py file to scan.
    settings = {"source_dirs": ["pkg"], "test_dir": "tests"}
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    codemap.build(tmp_path, settings)
    # Expect: one "step" event with name "codemap".
    step_events = [e for e in tel.events if e["kind"] == "step"]
    assert len(step_events) == 1
    assert step_events[0]["name"] == "codemap"


def test_ensure_worktree_records_the_step(tel, repo, tmp_path):
    # A real git repo in tmp_path (from the fixture); ensure_worktree creates a
    # worktree at root/T001 on branch stratos/T001.
    root = tmp_path / "wt"
    gitops.ensure_worktree(repo, root, "T001")
    # Expect: one "step" event with name "worktree".
    step_events = [e for e in tel.events if e["kind"] == "step"]
    assert len(step_events) == 1
    assert step_events[0]["name"] == "worktree"


def test_commit_all_records_the_step(tel, repo, tmp_path):
    # ensure_worktree also records "worktree"; commit_all records "git" as the
    # last step. We check "git" is present.
    root = tmp_path / "wt"
    wt = gitops.ensure_worktree(repo, root, "T001")
    (wt / "new.py").write_text("X = 1\n", encoding="utf-8")
    gitops.commit_all(wt, "T001 work")
    # Expect: "git" is among the recorded step names.
    step_names = [e["name"] for e in tel.events if e["kind"] == "step"]
    assert "git" in step_names


def test_preflight_check_records_the_step(tel, tmp_path, monkeypatch):
    # wt has the test file so check passes the existence and syntax checks;
    # a fake run returns (False, plain failure text) so missing_imports is empty
    # (no "cannot import", "No module named", "Cannot find module" in the output),
    # and check reaches its final return.
    wt = tmp_path / "wt"
    tests_dir = wt / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    task = {"id": "T001", "goal": "g", "files": ["pkg/a.py"], "tests": ["tests/test_a.py"]}
    monkeypatch.setattr(verify, "syntax_errors", lambda wt, paths: [])

    def fake_run(w, tests):
        # Output has no import-error patterns, so missing_imports returns [].
        return False, "FAILED tests/test_a.py::test_a - assert False\n"

    preflight.check(task, wt, run=fake_run)
    # Expect: one "step" event with name "preflight".
    step_events = [e for e in tel.events if e["kind"] == "step"]
    assert len(step_events) == 1
    assert step_events[0]["name"] == "preflight"
