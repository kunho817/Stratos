"""Tests for task refcheck (P7, 2026-11-20): an independent reference implementation checks drafted tests.
Experiment (scratchpad ref_eval.py, 4 cases with 5 known wrong tests, Tiel and Swift, 2 runs each): the reference,
written from the goal and the other source files without seeing the tests, failed every wrong test in every run (20/20);
when it failed most tests the goal had left the interface open (Drift slide: 14 of 14 every run - direction names vs
DIRS values, the start cell in the path), so that case is one "interface" warning, not 14 flags.

refcheck.SYSTEM: asks for the task's files from the goal alone, in FILE blocks ("FILE: <path>" then a fence).
refcheck.build_messages(task, root) -> [system, user]; the user message holds "GOAL:\n" + goal, then
"WRITE THESE FILES: " + ", ".join(task["files"]), then each existing file under the project's source_dirs (config.PROJECT)
that is not one of task["files"] as f"EXISTING FILE {path}:\n```\n{text}\n```" (POSIX paths, sorted), then
"CONVENTIONS:\n" + CONVENTIONS.md when it exists. Never a test file.
refcheck.count_tests(output) -> (total, failing ids): TAP ("ok N - name" / "not ok N - name") or pytest (total =
the "N passed" + "M failed" + "K error"/"K errors" numbers of the LAST line that has any of them - pytest also
prints "Interrupted: 1 error during collection" above its summary; failing ids from decide._extract_ids, which also
reads "ERROR <file>" lines of a file that could not be imported).
refcheck.judge(total, failing) -> "agree" when no failing, "interface" when len(failing) * 2 > total, else "flagged".
refcheck.check(gw, plan_id, task, root, tests) -> {"status", "total", "failing", "first_error"}: copies root to a
temporary folder (without .git, .stratos, node_modules, __pycache__), asks config.REF_WRITER (gw.ensure_model, then
gw.chat(..., task=f"{plan_id}-{task['key']}", role="reference", attempt=1, model, effort, max_tokens)), writes the FILE
blocks for task["files"] there, runs config.PROJECT["test_command"] + tests once in that folder (timeout
config.TEST_TIMEOUT_S), and judges. No usable FILE block -> status "error" with first_error "no file in the answer".
first_error: the first line of the output that contains "Error" or "assert" ("" when none), at most 200 characters.
config.REF_WRITER = {"model": "tiel-coder-35b-a3b-ud-q4_k_xl", "effort": "low", "max_tokens": 12000}."""
import pytest

from stratos import config, refcheck

TASK = {"key": "add", "title": "add", "goal": "Write pkg/calc.py with add(a, b) returning a + b and double(x) = 2 * x.",
        "files": ["pkg/calc.py"], "tests": ["tests/test_calc.py"]}
TESTS = '''from pkg.calc import add, double


def test_add():
    assert add(2, 3) == 5


def test_double():
    assert double(4) == 8


def test_wrong():
    assert add(2, 2) == 5
'''
GOOD = "FILE: pkg/calc.py\n```python\ndef add(a, b):\n    return a + b\n\n\ndef double(x):\n    return 2 * x\n```\n"
OTHER = "FILE: pkg/calc.py\n```python\ndef plus(a, b):\n    return a + b\n```\n"


class GW:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def ensure_model(self, model):
        self.calls.append(("load", model))
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append(("chat", messages, kw))
        return "c1", self.answer


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "util.py").write_text("ZERO = 0\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_calc.py").write_text(TESTS, encoding="utf-8")
    (root / "CONVENTIONS.md").write_text("pure modules", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "source_dirs": ["pkg"],
                                            "test_command": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]})
    monkeypatch.setattr(config, "REF_WRITER", {"model": "m-ref", "effort": "low", "max_tokens": 99})
    return root


def test_build_messages(project):
    user = refcheck.build_messages(TASK, project)[1]["content"]
    assert user.startswith("GOAL:\n" + TASK["goal"])
    assert "WRITE THESE FILES: pkg/calc.py" in user
    assert "EXISTING FILE pkg/util.py:\n```\nZERO = 0\n\n```" in user
    assert "CONVENTIONS:\npure modules" in user
    assert "test_calc" not in user and "assert add" not in user


def test_count_tests_and_judge():
    tap = "ok 1 - a\nnot ok 2 - b\nok 3 - c\n# tests 3\n"
    assert refcheck.count_tests(tap) == (3, ["b"])
    py = "FAILED tests/x.py::test_b - assert 1 == 2\n1 failed, 2 passed in 0.1s"
    assert refcheck.count_tests(py) == (3, ["tests/x.py::test_b"])
    broken = ("ERROR tests/x.py - ImportError: cannot import name 'add'\n!!! Interrupted: 1 error during collection !!!"
              "\n1 error in 0.2s")
    assert refcheck.count_tests(broken) == (1, ["tests/x.py"])
    assert refcheck.judge(3, []) == "agree"
    assert refcheck.judge(3, ["b"]) == "flagged"
    assert refcheck.judge(4, ["a", "b"]) == "flagged"
    assert refcheck.judge(3, ["a", "b"]) == "interface"


def test_check_flags_the_wrong_test(project):
    gw = GW(GOOD)
    r = refcheck.check(gw, "P001", TASK, project, ["tests/test_calc.py"])
    assert r["status"] == "flagged" and r["total"] == 3
    assert r["failing"] == ["tests/test_calc.py::test_wrong"]
    assert gw.calls[0] == ("load", "m-ref")
    kw = gw.calls[1][2]
    assert kw == {"task": "P001-add", "role": "reference", "attempt": 1, "model": "m-ref", "effort": "low",
                  "max_tokens": 99}
    assert not (project / "pkg" / "calc.py").exists()  # the project itself is not touched


def test_check_interface_when_most_fail(project):
    r = refcheck.check(GW(OTHER), "P001", TASK, project, ["tests/test_calc.py"])
    assert r["status"] == "interface"
    assert "Error" in r["first_error"] or "assert" in r["first_error"]


def test_check_error_without_a_file(project):
    r = refcheck.check(GW("I cannot."), "P001", TASK, project, ["tests/test_calc.py"])
    # (task refcheck_chain added "files" to every result; Claude updated this old test)
    assert r == {"status": "error", "total": 0, "failing": [], "first_error": "no file in the answer", "files": [], "output": ""}


def test_default_writer():
    # (task refcheck_swift, 2026-11-20: Swift - Tiel's edit blocks came out malformed; Claude updated this test)
    assert config.REF_WRITER["model"] == "swift-1.5-iq2_xs"
