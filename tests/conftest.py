"""Shared test setup: no test reaches the network. Jev's shadow decisions, the diagnosis A/B, text planning, the preflight check, the draft check and the plan critique are off unless a test turns them on, and
the real HTTP sender fails loudly if anything calls it. config.STATE_DIR is a fresh temporary folder unless a test sets
its own, so nothing a test writes reaches the real .stratos (2026-11-19)."""
import pytest

from stratos import config, jev


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path_factory):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path_factory.mktemp("state"))
    monkeypatch.setattr(config, "JEV_SHADOW", False)
    monkeypatch.setattr(config, "DIAGNOSE_AB", False)
    monkeypatch.setattr(config, "DIAGNOSE_ALWAYS", False, raising=False)
    # the loop tests check the loop's mechanics with the attempt plan they were written for (3 Tiel tries, then 1
    # Swift try); tests/test_p4_policy.py checks the real policy in config.py's source
    monkeypatch.setattr(config, "ATTEMPT_PLANS", {"coder": [("coder", 3), ("coder_hard", 1)],
                                                  "coder_hard": [("coder_hard", 2), ("coder", 1)]})
    monkeypatch.setattr(config, "PLAN_AS_TEXT", False)
    monkeypatch.setattr(config, "PLAN_CONVERTER", None)
    monkeypatch.setattr(config, "TRIAGE", False, raising=False)
    monkeypatch.setattr(config, "PREFLIGHT", False, raising=False)
    monkeypatch.setattr(config, "PLAN_CRITIQUE", False, raising=False)
    monkeypatch.setattr(config, "LINT", False, raising=False)
    monkeypatch.setattr(config, "REF_CHECK", False, raising=False)
    monkeypatch.setattr(config, "MUTATION", False, raising=False)   # T241: mutants run the tests many times
    monkeypatch.setattr(config, "MEMORY", False, raising=False)
    monkeypatch.setattr(config, "STREAM", False, raising=False)   # task gateway_stream: old fakes replace _req
    monkeypatch.setattr(config, "AUTO_LEARN", False, raising=False)   # task upkeep
    monkeypatch.setattr(config, "AUTO_WIKI", False, raising=False)
    monkeypatch.setattr(config, "CHECK", False, raising=False)   # task loop_checker: no real pyright in the tests
    monkeypatch.setattr(config, "LESSONS", tmp_path_factory.mktemp("lessons") / "LESSONS.md", raising=False)

    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to call the real Jev API")

    monkeypatch.setattr(jev, "_default_post", refuse)
