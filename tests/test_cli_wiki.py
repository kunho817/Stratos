"""Tests for task cli_wiki: `stratos memory wiki [--only PATH ...]` writes the module notes (memory M4).

`memory wiki` does not open the memory store. It calls wiki.build(Gateway(Telemetry(config.STATE_DIR /
"telemetry.jsonl")), config.REPO, config.STATE_DIR, codemap.build(config.REPO), only=<the --only paths or None>)
(all through their modules), prints f"wiki: {written} written, {unchanged} unchanged, {kept} kept (edited by hand),
{failed} failed", and returns 0. Then, when config.MEMORY is on, refresh_memory() so the new pages are searchable."""
from stratos import __main__ as cli
from stratos import codemap, config, wiki


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(codemap, "build", lambda root: {"root": str(root)})

    class FakeGateway:
        def __init__(self, telemetry):
            self.telemetry = telemetry
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    calls = []

    def build(gw, root, state_dir, cmap, only=None, log=print):
        calls.append((type(gw).__name__, root, state_dir, cmap, only))
        return {"written": 2, "unchanged": 1, "kept": 1, "failed": 0}
    monkeypatch.setattr(wiki, "build", build)
    refreshed = []
    monkeypatch.setattr(cli, "refresh_memory", lambda: refreshed.append(1))
    return calls, refreshed


def test_memory_wiki(tmp_path, monkeypatch, capsys):
    calls, refreshed = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "MEMORY", True)
    assert cli.main(["memory", "wiki"]) == 0
    assert calls == [("FakeGateway", tmp_path / "repo", tmp_path / "state", {"root": str(tmp_path / "repo")}, None)]
    assert "wiki: 2 written, 1 unchanged, 1 kept (edited by hand), 0 failed" in capsys.readouterr().out
    assert refreshed == [1]
    assert not (tmp_path / "state" / "memory.db").exists()


def test_memory_wiki_only(tmp_path, monkeypatch):
    calls, refreshed = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "MEMORY", False)
    assert cli.main(["memory", "wiki", "--only", "src/a.py", "src/b.py"]) == 0
    assert calls[0][4] == ["src/a.py", "src/b.py"]
    assert refreshed == []
