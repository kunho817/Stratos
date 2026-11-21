"""Tests for task refcheck_mutation_skip: in refcheck.mutation(copy, files, tests, limit=None),
a reference file is skipped when no test file's text contains the file's stem (its name without
folder and suffix) as a whole word (\b<stem>\b). A test file that cannot be read counts as not
containing the stem. The returned dict always has "skipped": the list of skipped paths in
files order ([] when none). When every file is skipped the result is
{"total":0,"killed":0,"survivors":[],"skipped":[...]}, and files==[] gives
{"total":0,"killed":0,"survivors":[],"skipped":[]}. Everything else about mutation stays as
it is, so tests/test_refcheck_mutation.py keeps passing. Fakes stand in for subprocess;
no network, GPU, or real models."""

import subprocess

import pytest

from stratos import config, refcheck


SRC_B = "def two():\n    return 1 + 1\n"
SRC_HELPER = "def help():\n    return 1\n"
SRC_UTIL = "def util():\n    return 2\n"
SRC_MAIN_JS = "function main() { return 1 + 1; }\n"

TEST_B = "from pkg.b import two\n\n\ndef test_two():\n    assert two() == 2\n"
TEST_UNRELATED = "from pkg.zzz import zzz\n\n\ndef test_zzz():\n    assert zzz() == 1\n"
TEST_HELPER = "from pkg.helper import help\n\n\ndef test_help():\n    assert help() == 1\n"
TEST_BBB = "def test_bbb():\n    assert True\n"
TEST_MAIN_JS = 'import { main } from "./main.js";\n\nfunction test_main() {\n  assert(main() === 2);\n}\n'


def make_copy(tmp_path, files, test_files):
    """Build a copy dir with source files and test files.
    test_files: list of (path, content) pairs; pass [] for a file that must be absent."""
    copy = tmp_path / "copy"
    for path, content in files:
        p = copy / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    for tpath, tcontent in test_files:
        p = copy / tpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(tcontent, encoding="utf-8")
    return copy


def _mock_run(returncode, stdout, stderr=""):
    """Fake subprocess.run that returns one result object."""
    def run(cmd, **kw):
        class R:
            pass
        r = R()
        r.returncode = returncode
        r.stdout = stdout
        r.stderr = stderr
        return r
    return run


@pytest.fixture(autouse=True)
def stub_env(tmp_path, monkeypatch):
    """Stub the pieces mutation uses so no real subprocess, GPU, or filesystem is needed
    for the test-run part."""
    monkeypatch.setattr(config, "MUTANTS", 12)
    monkeypatch.setattr(config, "MUTANT_TIMEOUT_S", 30)
    monkeypatch.setattr(refcheck.verify, "test_cmd", lambda tests: ["pytest", "x"])
    monkeypatch.setattr(refcheck.verify, "syntax_errors", lambda root, paths: [])
    monkeypatch.setattr(refcheck.verify, "dotnet_scope",
                        lambda root, tests: __import__("contextlib").nullcontext())
    monkeypatch.setattr(refcheck.langs, "child_env", lambda **kw: {})
    monkeypatch.setattr(refcheck.steps, "timed",
                        lambda name: __import__("contextlib").nullcontext())


def _killing_run():
    """TAP output: 1 test, 1 failing → count_tests gives (1, ['test']) → killed."""
    return _mock_run(0, "not ok 1 - test\n# tests 1\n")


def _passing_run():
    """TAP output: 1 test, all ok → count_tests gives (1, []) → survivor."""
    return _mock_run(0, "ok 1 - test\n# tests 1\n")


# ---- 1. Stem IS in a test file's text → file NOT skipped, mutation runs ----

def test_stem_found_not_skipped(tmp_path, monkeypatch):
    """pkg/b.py stem 'b' → regex \\bb\\b matches in 'from pkg.b import two' (dot before b
    is non-word, space after b is non-word) → NOT skipped.  Mutation runs: 1 file,
    limit=1, per_file=max(1,ceil(1/1))=1, mutate.mutants returns 1 mutant, killed by
    the mock run → total=1, killed=1, survivors=[], skipped=[]."""
    monkeypatch.setattr(subprocess, "run", _killing_run())
    copy = make_copy(tmp_path, [("pkg/b.py", SRC_B)],
                     [("tests/test_b.py", TEST_B)])
    r = refcheck.mutation(copy, [("pkg/b.py", SRC_B)], ["tests/test_b.py"], limit=1)
    # stem 'b' found in TEST_B as word between '.' and ' ' → not skipped
    assert r["skipped"] == []
    # 1 file × limit 1 = 1 mutant
    assert r["total"] == 1
    assert r["killed"] == 1
    assert r["survivors"] == []


# ---- 2. Stem NOT in test → skipped ----

def test_stem_not_in_test_skipped(tmp_path, monkeypatch):
    """pkg/helper.py stem 'helper'; test text 'from pkg.b import two' has no
    \\bhelper\\b → skipped. No mutants run → total=0, killed=0, survivors=[],
    skipped=['pkg/helper.py']."""
    copy = make_copy(tmp_path, [("pkg/helper.py", SRC_HELPER)],
                     [("tests/test_b.py", TEST_B)])
    r = refcheck.mutation(copy, [("pkg/helper.py", SRC_HELPER)],
                          ["tests/test_b.py"])
    # helper not found → file skipped, no mutants
    assert r["total"] == 0
    assert r["killed"] == 0
    assert r["survivors"] == []
    assert r["skipped"] == ["pkg/helper.py"]


# ---- 3. Every file skipped ----

def test_all_files_skipped(tmp_path):
    """Files helper, util; test mentions pkg.b → stems helper and util not found.
    Result: {"total":0,"killed":0,"survivors":[],"skipped":["pkg/helper.py","pkg/util.py"]}."""
    copy = make_copy(tmp_path,
                     [("pkg/helper.py", SRC_HELPER), ("pkg/util.py", SRC_UTIL)],
                     [("tests/test_b.py", TEST_B)])
    files = [("pkg/helper.py", SRC_HELPER), ("pkg/util.py", SRC_UTIL)]
    r = refcheck.mutation(copy, files, ["tests/test_b.py"])
    # neither helper nor util in test text → both skipped
    assert r == {"total": 0, "killed": 0, "survivors": [],
                 "skipped": ["pkg/helper.py", "pkg/util.py"]}


# ---- 4. files == [] ----

def test_empty_files():
    """files=[] → {"total":0,"killed":0,"survivors":[],"skipped":[]}. No copy needed."""
    r = refcheck.mutation("/nonexistent", [], [])
    assert r == {"total": 0, "killed": 0, "survivors": [], "skipped": []}


# ---- 5. Unreadable test file counts as not containing ----

def test_unreadable_test_skips(tmp_path):
    """pkg/b.py stem 'b'; test file tests/test_b.py does not exist in the copy.
    Cannot read → not containing → skipped. Result: skipped=['pkg/b.py']."""
    copy = make_copy(tmp_path, [("pkg/b.py", SRC_B)], [])  # no test file created
    r = refcheck.mutation(copy, [("pkg/b.py", SRC_B)], ["tests/test_b.py"])
    # test file absent → stem not found
    assert r["total"] == 0
    assert r["skipped"] == ["pkg/b.py"]


# ---- 6. Whole-word matching: 'b' inside 'bbb' is not a word ----

def test_b_inside_bbb_not_matched(tmp_path):
    """pkg/b.py stem 'b'; test text 'def test_bbb():' contains 'bbb'.
    In 'bbb' the 'b' is surrounded by word chars → \\bb\\b does NOT match →
    the file is skipped. Result: skipped=['pkg/b.py']."""
    copy = make_copy(tmp_path, [("pkg/b.py", SRC_B)],
                     [("tests/test_bbb.py", TEST_BBB)])
    r = refcheck.mutation(copy, [("pkg/b.py", SRC_B)], ["tests/test_bbb.py"])
    # b in bbb: preceded by b, followed by b → not a whole word
    assert r["skipped"] == ["pkg/b.py"]
    assert r["total"] == 0


# ---- 7. pkg.b as word: dot before, space after → matches ----

def test_pkg_dot_b_is_a_word_match(tmp_path, monkeypatch):
    """pkg/b.py stem 'b'; test text 'from pkg.b import two' → 'b' between '.'
    (non-word) and ' ' (non-word) → \\bb\\b matches → NOT skipped."""
    monkeypatch.setattr(subprocess, "run", _killing_run())
    copy = make_copy(tmp_path, [("pkg/b.py", SRC_B)],
                     [("tests/test_b.py", TEST_B)])
    r = refcheck.mutation(copy, [("pkg/b.py", SRC_B)], ["tests/test_b.py"], limit=1)
    assert r["skipped"] == []
    # 1 mutant killed
    assert r["total"] == 1 and r["killed"] == 1


# ---- 8. Mixed: skipped list in files order ----

def test_skipped_in_files_order(tmp_path, monkeypatch):
    """Files [pkg/helper.py, pkg/b.py]; test mentions pkg.b. helper not found →
    skipped; b found → not skipped. skipped=['pkg/helper.py'] (files order).
    Mutation runs for pkg/b.py: limit=1 → 1 mutant killed."""
    monkeypatch.setattr(subprocess, "run", _killing_run())
    copy = make_copy(tmp_path,
                     [("pkg/helper.py", SRC_HELPER), ("pkg/b.py", SRC_B)],
                     [("tests/test_b.py", TEST_B)])
    files = [("pkg/helper.py", SRC_HELPER), ("pkg/b.py", SRC_B)]
    r = refcheck.mutation(copy, files, ["tests/test_b.py"], limit=1)
    # helper skipped, b not → skipped in files order
    assert r["skipped"] == ["pkg/helper.py"]
    # only pkg/b.py mutates: 1 mutant
    assert r["total"] == 1
    assert r["killed"] == 1


# ---- 9. JS stem 'main' found in test ----

def test_js_stem_main_found(tmp_path, monkeypatch):
    """src/main.js → stem 'main'; test text 'import { main } from ...' →
    \\bmain\\b matches (space before, space after) → NOT skipped."""
    monkeypatch.setattr(subprocess, "run", _killing_run())
    copy = make_copy(tmp_path, [("src/main.js", SRC_MAIN_JS)],
                     [("tests/main.test.js", TEST_MAIN_JS)])
    r = refcheck.mutation(copy, [("src/main.js", SRC_MAIN_JS)],
                          ["tests/main.test.js"], limit=1)
    # main found as word → not skipped
    assert r["skipped"] == []
    assert r["total"] == 1 and r["killed"] == 1


# ---- 10. JS stem 'main' NOT in test ----

def test_js_stem_main_not_in_test(tmp_path):
    """src/main.js stem 'main'; test text 'import { other } from "./other.js"'
    → \\bmain\\b not found → skipped."""
    copy = make_copy(tmp_path, [("src/main.js", SRC_MAIN_JS)],
                     [("tests/other.test.js", 'import { other } from "./other.js";\n')])
    r = refcheck.mutation(copy, [("src/main.js", SRC_MAIN_JS)],
                          ["tests/other.test.js"])
    assert r["skipped"] == ["src/main.js"]
    assert r["total"] == 0


# ---- 11. Stem found in the second test file ----

def test_stem_in_second_test(tmp_path, monkeypatch):
    """pkg/helper.py stem 'helper'; tests: [test_a.py (unrelated), test_b.py
    (mentions helper)].  helper found in test_b → NOT skipped.
    1 file, limit=1, 1 mutant killed."""
    monkeypatch.setattr(subprocess, "run", _killing_run())
    copy = make_copy(tmp_path, [("pkg/helper.py", SRC_HELPER)],
                     [("tests/test_a.py", TEST_UNRELATED),
                      ("tests/test_b.py", TEST_HELPER)])
    r = refcheck.mutation(copy, [("pkg/helper.py", SRC_HELPER)],
                          ["tests/test_a.py", "tests/test_b.py"], limit=1)
    # helper found in test_b → not skipped
    assert r["skipped"] == []
    assert r["total"] == 1 and r["killed"] == 1


# ---- 12. Empty tests list → all files skipped ----

def test_empty_tests_all_skipped(tmp_path):
    """files=[pkg/b.py], tests=[] → no test text → stem not found → skipped.
    Result: {"total":0,"killed":0,"survivors":[],"skipped":["pkg/b.py"]}."""
    copy = make_copy(tmp_path, [("pkg/b.py", SRC_B)], [])
    r = refcheck.mutation(copy, [("pkg/b.py", SRC_B)], [])
    assert r == {"total": 0, "killed": 0, "survivors": [],
                 "skipped": ["pkg/b.py"]}


# ---- 13. Non-skipped file keeps existing mutation behaviour ----

def test_non_skipped_mutants_killed(tmp_path, monkeypatch):
    """pkg/b.py (stem b, in test) is NOT skipped. limit=3, per_file=3,
    3 mutants produced, all killed by the mock → total=3, killed=3, survivors=[],
    skipped=[].  Same as the existing strong-tests test."""
    monkeypatch.setattr(subprocess, "run", _killing_run())
    copy = make_copy(tmp_path, [("pkg/b.py", SRC_B)],
                     [("tests/test_b.py", TEST_B)])
    r = refcheck.mutation(copy, [("pkg/b.py", SRC_B)],
                          ["tests/test_b.py"], limit=3)
    # 3 mutants from pkg/b.py (return 2+1, return 1-1, return 1+2), all killed
    assert r["total"] == 3
    assert r["killed"] == 3
    assert r["survivors"] == []
    assert r["skipped"] == []
    # original content written back
    assert (copy / "pkg" / "b.py").read_text(encoding="utf-8") == SRC_B


# ---- 14. Survivor recorded for non-skipped file ----

def test_survivor_for_non_skipped(tmp_path, monkeypatch):
    """pkg/b.py (stem b, in test) not skipped. limit=1, 1 mutant, tests pass
    (mock returns all ok, returncode 0) → survivor recorded."""
    monkeypatch.setattr(subprocess, "run", _passing_run())
    copy = make_copy(tmp_path, [("pkg/b.py", SRC_B)],
                     [("tests/test_b.py", TEST_B)])
    r = refcheck.mutation(copy, [("pkg/b.py", SRC_B)],
                          ["tests/test_b.py"], limit=1)
    # 1 mutant, tests pass → survivor
    assert r["total"] == 1
    assert r["killed"] == 0
    # survivor format: f"{path}:{line}: {old.strip()} -> {new.strip()}"
    assert len(r["survivors"]) == 1
    assert r["survivors"][0].startswith("pkg/b.py:2:")
    assert r["skipped"] == []


# ---- 15. Skipped key present in every result, even when none are skipped ----

def test_skipped_key_always_present(tmp_path, monkeypatch):
    """When no file is skipped the result must still have "skipped": [] ."""
    monkeypatch.setattr(subprocess, "run", _killing_run())
    copy = make_copy(tmp_path, [("pkg/b.py", SRC_B)],
                     [("tests/test_b.py", TEST_B)])
    r = refcheck.mutation(copy, [("pkg/b.py", SRC_B)],
                          ["tests/test_b.py"], limit=1)
    # the dict has the key "skipped"
    assert "skipped" in r
    assert r["skipped"] == []
    # all four keys
    assert set(r.keys()) == {"total", "killed", "survivors", "skipped"}
