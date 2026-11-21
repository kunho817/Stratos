"""Tests for task main_plan_notfound: CLI plan commands catch PlanNotFound, not bare KeyError.

cmd_plan_critique, cmd_plan_add, cmd_plan_tests: replace `except KeyError` with `except PlanNotFound`
(import PlanNotFound from stratos.plan). The "no such plan: <id>" message and the return code (1)
stay the same. A bare KeyError (not PlanNotFound) raised inside those functions is NOT caught by
the "no such plan" handler and propagates. The KeyError catches in cmd_reset, cmd_drop, cmd_accept,
cmd_replay (for store.get, not plan_mod.load_plan) are NOT changed."""

import inspect

import pytest

from stratos import __main__ as cli
from stratos import config
from stratos.plan import PlanNotFound
from stratos.state import Store


class FakeGateway:
    """Stands in for Gateway; no network, no GPU."""

    def __init__(self, tel):
        self.telemetry = tel

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        return "c1", "ok"


def _setup(tmp_path, monkeypatch):
    """Point config at tmp_path and stub the gateway + memory refresh."""
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    (tmp_path / "repo").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("stratos.__main__.Gateway", FakeGateway)
    monkeypatch.setattr(cli, "refresh_memory", lambda: None)


# ---- PlanNotFound IS caught by the "no such plan" handler ----

def test_plan_critique_catches_plan_not_found(tmp_path, monkeypatch, capsys):
    """cmd_plan_critique: PlanNotFound from load_plan → 'no such plan' + rc 1."""
    _setup(tmp_path, monkeypatch)

    def fake_load(state_dir, pid):
        raise PlanNotFound(pid)

    monkeypatch.setattr(cli.plan_mod, "load_plan", fake_load)
    # PlanNotFound is a subclass of KeyError, so the old `except KeyError` also
    # caught it; after the task the handler must be `except PlanNotFound` and
    # still catch PlanNotFound.
    rc = cli.main(["plan-critique", "P404"])
    # Expected: return code 1, stderr "no such plan: P404"
    assert rc == 1
    assert capsys.readouterr().err.strip() == "no such plan: P404"


def test_plan_add_catches_plan_not_found(tmp_path, monkeypatch, capsys):
    """cmd_plan_add: PlanNotFound from load_plan → 'no such plan' + rc 1."""
    _setup(tmp_path, monkeypatch)

    def fake_load(state_dir, pid):
        raise PlanNotFound(pid)

    monkeypatch.setattr(cli.plan_mod, "load_plan", fake_load)
    rc = cli.main(["plan-add", "P404"])
    # Expected: return code 1, stderr "no such plan: P404"
    assert rc == 1
    assert capsys.readouterr().err.strip() == "no such plan: P404"


def test_plan_tests_catches_plan_not_found(tmp_path, monkeypatch, capsys):
    """cmd_plan_tests: PlanNotFound from draft_tests → 'no such plan' + rc 1."""
    _setup(tmp_path, monkeypatch)

    def fake_draft(gw, plan_id, root, state_dir):
        raise PlanNotFound(plan_id)

    monkeypatch.setattr(cli.plantests, "draft_tests", fake_draft)
    rc = cli.main(["plan-tests", "P404"])
    # Expected: return code 1, stderr "no such plan: P404"
    assert rc == 1
    assert capsys.readouterr().err.strip() == "no such plan: P404"


# ---- Bare KeyError must NOT be caught (this fails until the task is done) ----

def test_plan_critique_bare_key_error_propagates(tmp_path, monkeypatch, capsys):
    """cmd_plan_critique: a plain KeyError from load_plan is NOT caught by
    `except PlanNotFound` (KeyError is not a subclass of PlanNotFound)."""
    _setup(tmp_path, monkeypatch)

    def fake_load(state_dir, pid):
        raise KeyError("unrelated dict key")

    monkeypatch.setattr(cli.plan_mod, "load_plan", fake_load)
    # Before the task, `except KeyError` swallows this plain KeyError.
    # After the task, `except PlanNotFound` does not, so it propagates.
    with pytest.raises(KeyError):
        cli.main(["plan-critique", "P404"])
    # "no such plan" must NOT have been printed (the handler did not fire)
    assert "no such plan" not in capsys.readouterr().err


def test_plan_add_bare_key_error_propagates(tmp_path, monkeypatch, capsys):
    """cmd_plan_add: a plain KeyError from load_plan is NOT caught."""
    _setup(tmp_path, monkeypatch)

    def fake_load(state_dir, pid):
        raise KeyError("unrelated dict key")

    monkeypatch.setattr(cli.plan_mod, "load_plan", fake_load)
    # Before the task the old `except KeyError` swallows this.
    # After the task, `except PlanNotFound` does not catch it.
    with pytest.raises(KeyError):
        cli.main(["plan-add", "P404"])
    assert "no such plan" not in capsys.readouterr().err


def test_plan_tests_bare_key_error_propagates(tmp_path, monkeypatch, capsys):
    """cmd_plan_tests: a plain KeyError from draft_tests is NOT caught."""
    _setup(tmp_path, monkeypatch)

    def fake_draft(gw, plan_id, root, state_dir):
        raise KeyError("unrelated dict key")

    monkeypatch.setattr(cli.plantests, "draft_tests", fake_draft)
    # Before the task, `except KeyError` in cmd_plan_tests swallows it.
    # After the task, `except PlanNotFound` does not.
    with pytest.raises(KeyError):
        cli.main(["plan-tests", "P404"])
    assert "no such plan" not in capsys.readouterr().err


# ---- PlanNotFound is imported in __main__.py ----

def test_plan_notfound_is_imported_in_main():
    """__main__.py must import PlanNotFound from the .plan module so
    `except PlanNotFound` is available in the command functions."""
    src = inspect.getsource(cli)
    # The source must contain the import from the sibling plan module
    # Expected import: from .plan import PlanNotFound
    assert "from .plan import" in src
    assert "PlanNotFound" in src


def test_plan_notfound_is_the_same_class(tmp_path):
    """cli.PlanNotFound (the name used in the except clause) is the class
    defined in stratos.plan."""
    assert cli.PlanNotFound is PlanNotFound
    # PlanNotFound is a subclass of KeyError
    assert issubclass(PlanNotFound, KeyError)


# ---- KeyError catches in non-plan commands stay as KeyError ----

def test_reset_still_catches_key_error_from_store(tmp_path, monkeypatch, capsys):
    """cmd_reset's `except KeyError` (for store.get) must NOT be changed to
    `except PlanNotFound`; a plain KeyError from store.get is caught as before."""
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    (tmp_path / "repo").mkdir(parents=True, exist_ok=True)
    # store.get("T999") raises a plain KeyError → caught by `except KeyError`
    rc = cli.main(["reset", "T999", "--reason", "x"])
    # Expected: rc 1, stderr contains "T999"
    assert rc == 1
    assert "T999" in capsys.readouterr().err


def test_drop_still_catches_key_error_from_store(tmp_path, monkeypatch, capsys):
    """cmd_drop's `except KeyError` (for store.get) stays as KeyError."""
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    (tmp_path / "repo").mkdir(parents=True, exist_ok=True)
    rc = cli.main(["drop", "T999", "--reason", "x"])
    # Expected: rc 1, stderr contains "T999"
    assert rc == 1
    assert "T999" in capsys.readouterr().err


def test_accept_still_catches_key_error_from_store(tmp_path, monkeypatch, capsys):
    """cmd_accept's `except KeyError` (for store.get) stays as KeyError."""
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    (tmp_path / "repo").mkdir(parents=True, exist_ok=True)
    rc = cli.main(["accept", "T999", "--reason", "x"])
    # Expected: rc 1, stderr contains "T999"
    assert rc == 1
    assert "T999" in capsys.readouterr().err
