"""Tests for `stratos plan-tests <plan id>` (plan P003, task plantests_cli).

It calls plantests.draft_tests(gw, plan_id, config.REPO, config.STATE_DIR) with
gw = Gateway(Telemetry(config.STATE_DIR / "telemetry.jsonl")), prints f"{key} {file}: {status}" for each result and
returns 0. An unknown plan id (draft_tests raises KeyError) prints "no such plan: <id>" on stderr and returns 1."""
from stratos import __main__ as cli
from stratos import config, plantests


def setup(tmp_path, monkeypatch, result):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    made, calls = [], []

    class FakeGateway:
        def __init__(self, telemetry):
            self.telemetry = telemetry
            made.append(self)
    monkeypatch.setattr(cli, "Gateway", FakeGateway)

    def fake_draft(gw, plan_id, root, state_dir, log=print):
        calls.append((gw, plan_id, root, state_dir))
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(plantests, "draft_tests", fake_draft)
    return made, calls


def test_prints_the_results(tmp_path, monkeypatch, capsys):
    made, calls = setup(tmp_path, monkeypatch, [{"key": "core", "file": "tests/test_m.py", "status": "import_error"},
                                                {"key": "cli", "file": "tests/test_c.py", "status": "exists"}])
    assert cli.main(["plan-tests", "P003"]) == 0
    gw, pid, root, state = calls[0]
    assert gw is made[0] and str(gw.telemetry.path).endswith("telemetry.jsonl")
    assert (pid, root, state) == ("P003", config.REPO, config.STATE_DIR)
    out = capsys.readouterr().out
    assert "core tests/test_m.py: import_error" in out and "cli tests/test_c.py: exists" in out


def test_unknown_plan(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, KeyError("P404"))
    assert cli.main(["plan-tests", "P404"]) == 1
    assert "no such plan: P404" in capsys.readouterr().err
