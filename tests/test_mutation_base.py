"""Tests for task mutation-base: refcheck.mutation's base parameter filters mutants to reference-written lines.

refcheck.mutation(copy, files, tests, limit=None, base=None):
  base is dict {path: original text} or None.
  A mutant of file path is kept only when the stripped text of its "old" line is NOT in base[path]'s stripped lines
  (meaning the mutant lies on a line the reference wrote). base None, or path missing from base → every line counts
  (today's behaviour, all mutants kept).
refcheck.check: when status "agree" and config.MUTATION, computes
  base = {path: root[path].read_text() for each path in files that is a file under root}
  and passes base=base to mutation(copy, files, tests, base=base).
"""

import subprocess
from pathlib import Path

from stratos import config, refcheck

# Source with two mutable lines; the reference adds line 3, leaving line 2 unchanged from original
SRC = "def two():\n    return 1\n    return 1 + 1\n"
# Original file: line 2 "return 1" exists; line 3 is new
BASE_ORIGINAL = "def two():\n    return 1\n"
TEST_FILE = "from pkg.mod import two\n\n\ndef test_two():\n    assert two() == 3\n"


def _make_copy(tmp_path, src=SRC, test_text=TEST_FILE):
    copy = tmp_path / "copy"
    (copy / "pkg").mkdir(parents=True)
    (copy / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (copy / "pkg" / "mod.py").write_text(src, encoding="utf-8")
    (copy / "tests").mkdir()
    (copy / "tests" / "test_mod.py").write_text(test_text, encoding="utf-8")
    return copy


def _kill(cmd, **kw):
    """Subprocess.run mock: tests fail (returncode 1) → every mutant is killed."""
    return subprocess.CompletedProcess(
        cmd, 1,
        stdout="FAILED tests/test_mod.py::test_two - assert 3 == 2\n1 failed, 0 passed in 0.1s",
        stderr="",
    )


def _env(tmp_path, monkeypatch):
    """Shared setup: fake syntax check (no errors), fake subprocess (always kill), test_cmd, child_env, dotnet_scope."""
    monkeypatch.setattr(refcheck.verify, "syntax_errors", lambda root, paths: [])
    monkeypatch.setattr(subprocess, "run", _kill)
    monkeypatch.setattr(refcheck.verify, "test_cmd", lambda tests: ["pytest"] + list(tests))
    monkeypatch.setattr(refcheck.verify, "dotnet_scope", lambda root, tests: __import__("contextlib", fromlist=["nullcontext"]).nullcontext())
    monkeypatch.setattr(refcheck.langs, "child_env", lambda **kw: {})


def _patch_check_env(tmp_path, monkeypatch):
    """Patch config for refcheck.check to use pytest, MUTATION on, no dotnet."""
    monkeypatch.setattr(config, "PROJECT", {
        **config.PROJECT,
        "source_dirs": ["pkg"],
        "test_runner": "pytest",
        "test_command": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        "writable_suffixes": [".py"],
    })
    monkeypatch.setattr(config, "REF_WRITER", {"model": "m", "effort": "low", "max_tokens": 99})
    monkeypatch.setattr(config, "MUTATION", True)
    monkeypatch.setattr(config, "MUTANTS", 12)
    monkeypatch.setattr(config, "MUTANT_TIMEOUT_S", 30)
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "TEST_TIMEOUT_S", 30)


class _GW:
    def __init__(self, answer):
        self._answer = answer

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        return "c1", self._answer


# ---- Test 1: base None keeps every mutant ----

def test_base_none_keeps_every_mutant(tmp_path, monkeypatch):
    # SRC has line-2 integer mutation (1→2) + line-3 operator/integer mutations (3)
    # total mutants = 4. base=None → no filtering → all 4 kept, all killed.
    copy = _make_copy(tmp_path)
    _env(tmp_path, monkeypatch)
    r = refcheck.mutation(copy, [("pkg/mod.py", SRC)], ["tests/test_mod.py"], limit=12, base=None)
    # 4 mutants generated, no filtering, all killed
    assert r["total"] == 4
    assert r["killed"] == 4


# ---- Test 2: path missing from base → all mutants kept ----

def test_path_missing_from_base_keeps_all(tmp_path, monkeypatch):
    # base has a dict, but "pkg/mod.py" is not a key → all mutants kept
    copy = _make_copy(tmp_path)
    _env(tmp_path, monkeypatch)
    base = {"pkg/other.py": "def x():\n    pass\n"}
    r = refcheck.mutation(copy, [("pkg/mod.py", SRC)], ["tests/test_mod.py"], limit=12, base=base)
    # path not in base → no filtering → 4 mutants kept
    assert r["total"] == 4
    assert r["killed"] == 4


# ---- Test 3: mutant old line found in base → skipped ----

def test_mutant_on_base_line_is_skipped(tmp_path, monkeypatch):
    # base: "def two():\n    return 1\n" → stripped lines: {"def two():", "return 1"}
    # Line-2 mutant: old="    return 1", stripped="return 1" → IN base → SKIPPED
    # Line-3 mutants (3): old="    return 1 + 1", stripped="return 1 + 1" → NOT in base → KEPT
    # Expected total: 3, all killed
    copy = _make_copy(tmp_path)
    _env(tmp_path, monkeypatch)
    base = {"pkg/mod.py": BASE_ORIGINAL}
    r = refcheck.mutation(copy, [("pkg/mod.py", SRC)], ["tests/test_mod.py"], limit=12, base=base)
    # line-2 mutant (1) filtered out; 3 line-3 mutants kept and killed
    assert r["total"] == 3
    assert r["killed"] == 3


# ---- Test 4: mutant old line NOT in base → kept ----

def test_mutant_line_not_in_base_is_kept(tmp_path, monkeypatch):
    # base: "def two():\n    return 99\n" → stripped lines: {"def two():", "return 99"}
    # Line-2: stripped "return 1" NOT in base → kept (1 mutant)
    # Line-3: stripped "return 1 + 1" NOT in base → kept (3 mutants)
    # Expected: 4 total, all killed
    copy = _make_copy(tmp_path)
    _env(tmp_path, monkeypatch)
    base = {"pkg/mod.py": "def two():\n    return 99\n"}
    r = refcheck.mutation(copy, [("pkg/mod.py", SRC)], ["tests/test_mod.py"], limit=12, base=base)
    # base has no matching lines → all 4 mutants kept
    assert r["total"] == 4
    assert r["killed"] == 4


# ---- Test 5: two files, one filtered by base, one not in base ----

def test_multiple_files_partial_base(tmp_path, monkeypatch):
    # File a: "def a():\n    return 1\n" — 1 integer mutant on "return 1"
    # File b: "def b():\n    return 2 + 3\n" — 3 mutants (operator/integer on "2 + 3")
    # base has a.py original "def a():\n    pass\n" (stripped: "def a():", "pass")
    #   "return 1" NOT in base → a's 1 mutant kept
    # b.py not in base → all 3 mutants kept
    copy = tmp_path / "copy"
    (copy / "pkg").mkdir(parents=True)
    (copy / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    src_a = "def a():\n    return 1\n"
    src_b = "def b():\n    return 2 + 3\n"
    (copy / "pkg" / "a.py").write_text(src_a, encoding="utf-8")
    (copy / "pkg" / "b.py").write_text(src_b, encoding="utf-8")
    (copy / "tests").mkdir()
    (copy / "tests" / "test_ab.py").write_text(
        "from pkg.a import a\nfrom pkg.b import b\n\n\ndef test_a():\n    assert a() == 1\n\n\ndef test_b():\n    assert b() == 5\n",
        encoding="utf-8",
    )
    _env(tmp_path, monkeypatch)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 1,
        stdout="FAILED - assert\n1 failed, 0 passed in 0.1s",
        stderr="",
    ))
    base = {"pkg/a.py": "def a():\n    pass\n"}
    r = refcheck.mutation(copy, [("pkg/a.py", src_a), ("pkg/b.py", src_b)], ["tests/test_ab.py"], limit=12, base=base)
    # a's line-2 mutant: stripped "return 1" not in base {"def a():", "pass"} → kept (1)
    # b not in base → all kept (3)
    # total = 1 + 3 = 4
    assert r["total"] == 4
    assert r["killed"] == 4


# ---- Test 6: base stripped-line matching is whitespace-insensitive ----

def test_stripped_matching_ignores_whitespace(tmp_path, monkeypatch):
    # base line has extra whitespace: "    return 1" (4 spaces indent in base)
    # mutant old: "    return 1" (4 spaces) → stripped "return 1" == stripped base "return 1"
    # → skipped
    copy = _make_copy(tmp_path)
    _env(tmp_path, monkeypatch)
    base = {"pkg/mod.py": "def two():\nreturn 1\n"}
    # base stripped lines: {"def two():", "return 1"}
    # line-2 mutant stripped: "return 1" → IN base → skipped
    # line-3 mutants stripped: "return 1 + 1" → NOT in base → kept (3)
    r = refcheck.mutation(copy, [("pkg/mod.py", SRC)], ["tests/test_mod.py"], limit=12, base=base)
    # 3 kept (line-3 mutants), line-2 filtered
    assert r["total"] == 3


# ---- Test 7: check() computes base from existing files under root ----

def test_check_passes_base_for_existing_files(tmp_path, monkeypatch):
    # pkg/mod.py exists in root with BASE_ORIGINAL → base = {pkg/mod.py: BASE_ORIGINAL}
    # Reference adds "return 1 + 1" → all tests pass → mutation runs with base filtering
    # Line-2 mutants filtered (in base), line-3 mutants kept → total 3
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "mod.py").write_text(BASE_ORIGINAL, encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_mod.py").write_text(TEST_FILE, encoding="utf-8")
    _patch_check_env(tmp_path, monkeypatch)

    calls = []
    def mock_run(cmd, **kw):
        calls.append(cmd)
        if len(calls) == 1:
            # the reference's own tests pass
            return subprocess.CompletedProcess(cmd, 0, stdout="1 passed in 0.1s", stderr="")
        # mutation test runs: fail
        return subprocess.CompletedProcess(cmd, 1, stdout="FAILED - assert\n1 failed, 0 passed in 0.1s", stderr="")
    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(refcheck.verify, "syntax_errors", lambda root, paths: [])
    monkeypatch.setattr(refcheck.verify, "test_cmd", lambda tests: ["pytest"] + list(tests))
    monkeypatch.setattr(refcheck.verify, "dotnet_scope", lambda root, tests: __import__("contextlib", fromlist=["nullcontext"]).nullcontext())
    monkeypatch.setattr(refcheck.langs, "child_env", lambda **kw: {})

    ref_answer = "FILE: pkg/mod.py\n```python\ndef two():\n    return 1\n    return 1 + 1\n```\n"
    task = {"key": "mod", "goal": "Add return 1+1", "files": ["pkg/mod.py"], "tests": ["tests/test_mod.py"]}
    r = refcheck.check(_GW(ref_answer), "P1", task, root, ["tests/test_mod.py"])
    # status agree, mutation with base filtering
    assert r["status"] == "agree"
    # base = {pkg/mod.py: BASE_ORIGINAL}; line-2 filtered, 3 line-3 mutants kept
    assert r["mutation"]["total"] == 3
    assert r["mutation"]["killed"] == 3


# ---- Test 8: check() for a new file (not under root) → base excludes it ----

def test_check_new_file_not_in_base(tmp_path, monkeypatch):
    # pkg/mod.py does NOT exist under root → base = {} → path not in base → all mutants kept
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    # pkg/mod.py absent
    (root / "tests").mkdir()
    (root / "tests" / "test_mod.py").write_text(TEST_FILE, encoding="utf-8")
    _patch_check_env(tmp_path, monkeypatch)

    calls = []
    def mock_run(cmd, **kw):
        calls.append(cmd)
        if len(calls) == 1:
            return subprocess.CompletedProcess(cmd, 0, stdout="1 passed in 0.1s", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="FAILED - assert\n1 failed, 0 passed in 0.1s", stderr="")
    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(refcheck.verify, "syntax_errors", lambda root, paths: [])
    monkeypatch.setattr(refcheck.verify, "test_cmd", lambda tests: ["pytest"] + list(tests))
    monkeypatch.setattr(refcheck.verify, "dotnet_scope", lambda root, tests: __import__("contextlib", fromlist=["nullcontext"]).nullcontext())
    monkeypatch.setattr(refcheck.langs, "child_env", lambda **kw: {})

    ref_answer = "FILE: pkg/mod.py\n```python\ndef two():\n    return 1\n    return 1 + 1\n```\n"
    task = {"key": "mod", "goal": "New file", "files": ["pkg/mod.py"], "tests": ["tests/test_mod.py"]}
    r = refcheck.check(_GW(ref_answer), "P1", task, root, ["tests/test_mod.py"])
    assert r["status"] == "agree"
    # new file, not in base → all 4 mutants kept
    assert r["mutation"]["total"] == 4
    assert r["mutation"]["killed"] == 4
