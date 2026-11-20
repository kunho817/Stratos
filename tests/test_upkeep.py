"""Tests for task upkeep (P14, 2026-11-20, user: memory must keep improving; found: `memory learn` and `memory wiki` ran
only by hand - LESSONS.md had not learned since Pantry round 2, and no trial had a wiki).

upkeep.pending(tasks, events, state_dir, repo) -> the ids of the corrections not learned yet: learn.corrections +
learn.plan_corrections + learn.draft_corrections(repo), minus the ids in state_dir/learned.json.
upkeep.after_run(gw, store, finished, log=print): called by run-all after its passes, with the ids of the tasks that
ended "done" in this run:
- config.AUTO_LEARN and pending(...) not empty -> learn.learn(gw, tasks, events, config.LESSONS, config.STATE_DIR,
  config.REPO.name, embedder=embed.Embedder(), repo=config.REPO) and log f"memory learn: {added} lessons from {n}
  corrections" (n = len(pending)); nothing pending -> no learner call, nothing logged;
- config.AUTO_WIKI and finished not empty -> wiki.build(gw, config.REPO, config.STATE_DIR,
  codemap.build(config.REPO)) and log f"wiki: {written} written, {unchanged} unchanged";
- then, when either ran, the memory index is refreshed (refresh(), a function passed in, default no-op);
- any exception inside is logged as f"upkeep: {e}" and never raised.
config.AUTO_LEARN = True and config.AUTO_WIKI = True (tests/conftest.py turns both off)."""
import json

from stratos import codemap, config, embed, learn, upkeep, wiki


class Store:
    def tasks(self):
        return []


def setup(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_a.py").write_text("X = 1  # (Claude: a note)\n", encoding="utf-8")
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", repo)
    monkeypatch.setattr(config, "AUTO_LEARN", True)
    monkeypatch.setattr(config, "AUTO_WIKI", True)
    monkeypatch.setattr(embed, "Embedder", lambda: "EMB")
    monkeypatch.setattr(codemap, "build", lambda root: {"files": {}})
    calls = []
    monkeypatch.setattr(learn, "learn", lambda gw, tasks, events, lessons, state_dir, project, embedder=None, repo=None:
                        calls.append(("learn", project, embedder, repo)) or {"corrections": 1, "added": 1,
                                                                             "duplicates": 0, "skipped": 0})
    monkeypatch.setattr(wiki, "build", lambda gw, root, state_dir, cmap, only=None, log=print:
                        calls.append(("wiki", root)) or {"written": 2, "unchanged": 5, "kept": 0, "failed": 0})
    return state, repo, calls


def test_pending(tmp_path, monkeypatch):
    state, repo, _ = setup(tmp_path, monkeypatch)
    assert upkeep.pending([], [], state, repo) == ["draft:tests/test_a.py:(module):1"]
    (state / "learned.json").write_text(json.dumps(["draft:tests/test_a.py:(module):1"]), encoding="utf-8")
    assert upkeep.pending([], [], state, repo) == []


def test_after_run_learns_and_builds_the_wiki(tmp_path, monkeypatch):
    state, repo, calls = setup(tmp_path, monkeypatch)
    lines, refreshed = [], []
    upkeep.after_run("GW", Store(), ["T1"], log=lines.append, refresh=lambda: refreshed.append(1))
    assert calls == [("learn", "repo", "EMB", repo), ("wiki", repo)]
    assert lines == ["memory learn: 1 lessons from 1 corrections", "wiki: 2 written, 5 unchanged"]
    assert refreshed == [1]


def test_nothing_to_do(tmp_path, monkeypatch):
    state, repo, calls = setup(tmp_path, monkeypatch)
    (state / "learned.json").write_text(json.dumps(["draft:tests/test_a.py:(module):1"]), encoding="utf-8")
    lines, refreshed = [], []
    upkeep.after_run("GW", Store(), [], log=lines.append, refresh=lambda: refreshed.append(1))
    assert calls == [] and lines == [] and refreshed == []


def test_errors_are_logged_not_raised(tmp_path, monkeypatch):
    state, repo, calls = setup(tmp_path, monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("model gone")
    monkeypatch.setattr(learn, "learn", boom)
    lines = []
    upkeep.after_run("GW", Store(), [], log=lines.append)
    assert lines == ["upkeep: model gone"]


def test_run_all_calls_it():
    import inspect

    from stratos import __main__ as cli
    src = inspect.getsource(cli._main)
    assert "upkeep.after_run(gw, store, " in src and "refresh=refresh_memory" in src


def test_switches():
    from pathlib import Path
    text = Path(config.__file__).read_text(encoding="utf-8")
    assert "\nAUTO_LEARN = True" in text and "\nAUTO_WIKI = True" in text
    assert config.AUTO_LEARN is False and config.AUTO_WIKI is False   # tests/conftest.py
