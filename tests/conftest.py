"""Shared test setup: no test reaches the network. Jev's shadow decisions, the diagnosis A/B, text planning, the preflight check and the draft check are off unless a test turns them on, and
the real HTTP sender fails loudly if anything calls it. config.STATE_DIR is a fresh temporary folder unless a test sets
its own, so nothing a test writes reaches the real .stratos (2026-11-19)."""
import pytest

from stratos import config, jev


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path_factory):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path_factory.mktemp("state"))
    monkeypatch.setattr(config, "JEV_SHADOW", False)
    monkeypatch.setattr(config, "DIAGNOSE_AB", False)
    monkeypatch.setattr(config, "PLAN_AS_TEXT", False)
    monkeypatch.setattr(config, "PLAN_CONVERTER", None)
    monkeypatch.setattr(config, "TRIAGE", False, raising=False)
    monkeypatch.setattr(config, "PREFLIGHT", False, raising=False)
    monkeypatch.setattr(config, "DRAFT_CHECK", False, raising=False)
    monkeypatch.setattr(config, "MEMORY", False, raising=False)
    monkeypatch.setattr(config, "LESSONS", tmp_path_factory.mktemp("lessons") / "LESSONS.md", raising=False)

    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to call the real Jev API")

    monkeypatch.setattr(jev, "_default_post", refuse)
