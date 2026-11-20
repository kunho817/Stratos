"""Tests for task refcheck_swift (P8, 2026-11-20): on Pantry round 3's drafts the Tiel references broke their own
edit blocks (several "=======" in one block), the rewritten files did not compile, and all three tasks were judged
"interface". With Swift writing the references (scratchpad recheck_pantry3.py): recipe_comments and cli_count agree
(0 of 13, 0 of 14) and list_markdown flags exactly the two tests Claude had found wrong by hand.

config.REF_WRITER = {"model": "swift-1.5-iq2_xs", "effort": "low", "max_tokens": 24000, "reasoning_budget": 3000};
refcheck.check passes reasoning_budget to gw.chat when REF_WRITER has one.
refcheck.check runs verify.syntax_errors(copy, <the paths it wrote>) before the tests: any error gives
{"status": "error", "total": 0, "failing": [], "first_error": "the reference does not compile: " + the first error,
"files": []} - a reference that does not compile says nothing about the tests."""
from stratos import config, refcheck

TASK = {"key": "a", "title": "a", "goal": "g", "files": ["pkg/a.py"], "tests": ["tests/test_a.py"]}


class GW:
    def __init__(self, answer):
        self.answer = answer
        self.kw = None

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        self.kw = kw
        return "c1", self.answer


def project(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_a.py").write_text("from pkg.a import f\n\n\ndef test_f():\n    assert f() == 1\n",
                                              encoding="utf-8")
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "source_dirs": ["pkg"],
                                            "test_command": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]})
    return root


def test_default_writer_is_swift_with_a_budget():
    assert config.REF_WRITER == {"model": "swift-1.5-iq2_xs", "effort": "low", "max_tokens": 24000,
                                 "reasoning_budget": 3000}


def test_the_budget_is_passed(tmp_path, monkeypatch):
    root = project(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "REF_WRITER", {"model": "m", "effort": "low", "max_tokens": 9, "reasoning_budget": 7})
    gw = GW("FILE: pkg/a.py\n```python\ndef f():\n    return 1\n```\n")
    assert refcheck.check(gw, "P1", TASK, root, ["tests/test_a.py"])["status"] == "agree"
    assert gw.kw["reasoning_budget"] == 7


def test_a_reference_that_does_not_compile_is_an_error(tmp_path, monkeypatch):
    root = project(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "REF_WRITER", {"model": "m", "effort": "low", "max_tokens": 9})
    r = refcheck.check(GW("FILE: pkg/a.py\n```python\ndef f(:\n    return 1\n```\n"), "P1", TASK, root,
                       ["tests/test_a.py"])
    assert r["status"] == "error" and r["files"] == [] and r["total"] == 0
    assert r["first_error"].startswith("the reference does not compile: pkg/a.py: line 1: ")
