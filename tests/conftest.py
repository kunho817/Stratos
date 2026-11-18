"""Shared test setup: no test reaches the network. Jev's shadow decisions, the diagnosis A/B and text planning are off unless a test turns them on, and
the real HTTP sender fails loudly if anything calls it."""
import pytest

from stratos import config, jev


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(config, "JEV_SHADOW", False)
    monkeypatch.setattr(config, "DIAGNOSE_AB", False)
    monkeypatch.setattr(config, "PLAN_AS_TEXT", False)
    monkeypatch.setattr(config, "PLAN_CONVERTER", None)
    monkeypatch.setattr(config, "TRIAGE", False, raising=False)

    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to call the real Jev API")

    monkeypatch.setattr(jev, "_default_post", refuse)
