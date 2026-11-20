"""Tests for task refcheck_crash (P11, 2026-11-20, trial 11): a reference implementation that crashed (Quill toc: the
parameter `toc` hid the module `toc`, so every test raised AttributeError inside the reference) was reported as
"the goal may leave the interface open" - twice in one trial, once hiding a wrong test.

refcheck.crash_line(output, files) -> str: pytest prints, for each failure, a line "<path>:<n>: <ErrorName>" for the
frame that raised (backslashes on Windows). The crash line is the first such line whose path (with "/") is one of
`files` and whose error is not AssertionError. It is returned when there are at least as many such lines (any
error but AssertionError, any of `files`) as failing tests (refcheck.count_tests) and at least one test fails;
otherwise "".
refcheck.check: when the crash line is not "", the status is "crashed" and first_error is the crash line (total and
failing as counted). plan-tests logs f"{key}: the reference implementation crashed ({first_error}) - this says
nothing about the tests"."""
from stratos import refcheck

OUT = """tests\\test_a.py:5:
E       AttributeError: 'bool' object has no attribute 'unique'

pkg\\a.py:2: AttributeError
tests\\test_a.py:9:
E       AttributeError: 'bool' object has no attribute 'unique'

pkg\\a.py:2: AttributeError
FAILED tests/test_a.py::test_1 - AttributeError: 'bool' object has no attribu...
FAILED tests/test_a.py::test_2 - AttributeError: 'bool' object has no attribu...
2 failed in 0.1s
"""


def test_crash_in_the_reference():
    assert refcheck.crash_line(OUT, ["pkg/a.py"]) == "pkg/a.py:2: AttributeError"


def test_not_a_crash():
    one_crash = OUT.replace("pkg\\a.py:2: AttributeError\nFAILED", "tests\\test_a.py:9: AssertionError\nFAILED")
    assert refcheck.crash_line(one_crash, ["pkg/a.py"]) == ""          # only 1 of 2 failures crashed there
    assert refcheck.crash_line(OUT, ["pkg/b.py"]) == ""                # not in the reference's files
    asserts = OUT.replace("pkg\\a.py:2: AttributeError", "pkg\\a.py:2: AssertionError")
    assert refcheck.crash_line(asserts, ["pkg/a.py"]) == ""
    assert refcheck.crash_line("1 passed in 0.1s", ["pkg/a.py"]) == ""


class GW:
    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        return "c1", "FILE: pkg/a.py\n```python\ndef f(toc=False):\n    return toc.unique([1])\n```\n"


def test_check_reports_crashed(tmp_path, monkeypatch):
    from stratos import config
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_a.py").write_text("from pkg.a import f\n\n\ndef test_1():\n    assert f() == 1\n\n\n"
                                              "def test_2():\n    assert f(True) == 2\n", encoding="utf-8")
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "source_dirs": ["pkg"],
                                            "test_command": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]})
    monkeypatch.setattr(config, "REF_WRITER", {"model": "m", "effort": "low", "max_tokens": 9})
    task = {"key": "a", "title": "a", "goal": "g", "files": ["pkg/a.py"], "tests": ["tests/test_a.py"]}
    r = refcheck.check(GW(), "P1", task, root, ["tests/test_a.py"])
    assert r["status"] == "crashed" and r["total"] == 2
    assert r["first_error"] == "pkg/a.py:2: AttributeError"
