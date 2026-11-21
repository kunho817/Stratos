"""Tests for task refcheck_mutation_skip: mutation skips reference files that no test imports.

Before generating mutants for a reference file, mutation(copy, files, tests, limit=None)
reads each test file from disk under copy and checks whether it imports the file's stem
(the filename without its extension: pkg/b.py -> "b", pkg/sub/b.js -> "b").

Import detection per language (determined by the reference file's extension):
  Python (.py): test text contains literal "import <stem>", "from X.<stem> import",
    or "from <stem> import".
  JavaScript (.js): an import/require whose path ends in "<stem>.js" or "<stem>".
  Any other language (.cs, .go, .rs, .txt …): the stem appears in the test text.

A file with no importer is skipped (no mutants generated for it).
If all files are skipped: return {"total": 0, "killed": 0, "survivors": [], "skipped": [paths]}.
Otherwise add "skipped" (possibly []) to the existing return dict.
Fakes replace subprocess.run, verify.syntax_errors, verify.dotnet_scope, verify.test_cmd
and the config — no network, GPU, real models, or real pytest runs.
"""

import contextlib
import subprocess

import pytest

from stratos import config, refcheck, verify


SRC_B = "def two():\n    return 1 + 1\n"
SRC_C = "def three():\n    return 1 + 2\n"


def build_copy(tmp_path, ref_files, test_files):
    """Create a copy dir with reference files and test files on disk."""
    copy = tmp_path / "copy"
    for path, content in ref_files:
        p = copy / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    for path, content in test_files:
        p = copy / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return copy


def patch_env(monkeypatch, passing=True):
    """No syntax errors, nullcontext dotnet scope, fake test_cmd, fake subprocess.run."""
    monkeypatch.setattr(verify, "syntax_errors", lambda root, paths: [])
    monkeypatch.setattr(
        verify,
        "test_cmd",
        lambda tests: ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"] + tests,
    )
    monkeypatch.setattr(verify, "dotnet_scope", lambda root, tests: contextlib.nullcontext())
    monkeypatch.setattr(config, "MUTANTS", 12)
    monkeypatch.setattr(config, "MUTANT_TIMEOUT_S", 30)
    monkeypatch.setattr(
        config,
        "PROJECT",
        {**config.PROJECT, "test_runner": "pytest",
         "test_command": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"],
         "source_dirs": ["pkg"]},
    )

    class Result:
        returncode = 0 if passing else 1
        stdout = "1 passed in 0.1s\n" if passing else "1 failed in 0.1s\n"
        stderr = ""

    monkeypatch.setattr(refcheck.subprocess, "run", lambda cmd, **kw: Result())


# ---- 1. Python: stem IS imported → mutation proceeds, skipped is [] ----

def test_python_imported_file_not_skipped(tmp_path, monkeypatch):
    """pkg/b.py stem 'b'; test reads 'from pkg.b import two' → match.
    Mutation runs mutants for b.py. Result gains skipped=[]."""
    patch_env(monkeypatch)
    copy = build_copy(
        tmp_path,
        [("pkg/b.py", SRC_B)],
        [("tests/test_b.py", "from pkg.b import two\n\ndef test_two():\n    assert two() == 2\n")],
    )
    r = refcheck.mutation(copy, [("pkg/b.py", SRC_B)], ["tests/test_b.py"], limit=3)
    # stem "b" is found in "from pkg.b import" → not skipped
    # 3 mutants generated (limit=3), all killed (test fails for every mutant)
    # Expected: total=3, killed=3, survivors=[], skipped=[]
    assert r["total"] == 3
    assert r["killed"] == 3
    assert r["survivors"] == []
    # skipped key must be present
    assert r["skipped"] == []


# ---- 2. Python: stem NOT imported → file skipped, all-skipped dict ----

def test_python_file_not_imported_all_skipped(tmp_path, monkeypatch):
    """pkg/b.py stem 'b'; only test imports pkg.c → no importer.
    All files skipped → {"total": 0, "killed": 0, "survivors": [], "skipped": ["pkg/b.py"]}."""
    patch_env(monkeypatch)
    copy = build_copy(
        tmp_path,
        [("pkg/b.py", SRC_B)],
        [("tests/test_c.py", "from pkg.c import three\n\ndef test_c():\n    assert three() == 3\n")],
    )
    r = refcheck.mutation(copy, [("pkg/b.py", SRC_B)], ["tests/test_c.py"], limit=3)
    # stem "b" does NOT appear in "from pkg.c import three"
    # Expected: all skipped → special dict
    assert r == {"total": 0, "killed": 0, "survivors": [], "skipped": ["pkg/b.py"]}


# ---- 3. Python: "import b" literal in test text ----

def test_python_import_b_literal(tmp_path, monkeypatch):
    """Test text 'import b' → literal match. Mutation proceeds.
    skipped=[] present."""
    patch_env(monkeypatch)
    copy = build_copy(
        tmp_path,
        [("pkg/b.py", SRC_B)],
        [("tests/test_b.py", "import b\n\ndef test_b():\n    assert b.two() == 2\n")],
    )
    r = refcheck.mutation(copy, [("pkg/b.py", SRC_B)], ["tests/test_b.py"], limit=3)
    # "import b" is a literal substring → match
    # Expected: not skipped
    assert r["total"] == 3
    assert r["skipped"] == []


# ---- 4. Python: "from b import" literal ----

def test_python_from_b_import(tmp_path, monkeypatch):
    """Test text 'from b import two' → literal match. Not skipped."""
    patch_env(monkeypatch)
    copy = build_copy(
        tmp_path,
        [("pkg/b.py", SRC_B)],
        [("tests/test_b.py", "from b import two\n\ndef test_b():\n    assert two() == 2\n")],
    )
    r = refcheck.mutation(copy, [("pkg/b.py", SRC_B)], ["tests/test_b.py"], limit=3)
    # "from b import" is a literal substring → match
    # Expected: not skipped, total=3
    assert r["total"] == 3
    assert r["skipped"] == []


# ---- 5. Mixed: some skipped, some not ----

def test_mixed_skipped_and_imported(tmp_path, monkeypatch):
    """pkg/a.py stem 'a' is imported; pkg/b.py stem 'b' is not.
    Result: total > 0, skipped contains only ["pkg/b.py"]."""
    patch_env(monkeypatch)
    src_a = "def one():\n    return 1\n"
    src_b = "def two():\n    return 1 + 1\n"
    copy = build_copy(
        tmp_path,
        [("pkg/a.py", src_a), ("pkg/b.py", src_b)],
        [("tests/test_a.py", "from pkg.a import one\n\ndef test_a():\n    assert one() == 1\n")],
    )
    r = refcheck.mutation(copy, [("pkg/a.py", src_a), ("pkg/b.py", src_b)],
                          ["tests/test_a.py"], limit=4)
    # pkg/a.py stem 'a' is in "from pkg.a import" → not skipped
    # pkg/b.py stem 'b' is NOT in the test text → skipped
    # Expected: skipped = ["pkg/b.py"]
    # Expected: mutants only from pkg/a.py (limit=4, per_file = ceil(4/1)=4 for the remaining 1 file)
    assert r["skipped"] == ["pkg/b.py"]
    assert r["total"] > 0


# ---- 6. Nested path: pkg/sub/b.py → stem b ----

def test_nested_path_stem(tmp_path, monkeypatch):
    """pkg/sub/b.py → stem 'b'. Test contains 'from pkg.sub.b import two' → match.
    Not skipped."""
    patch_env(monkeypatch)
    copy = build_copy(
        tmp_path,
        [("pkg/sub/b.py", SRC_B)],
        [("tests/test_b.py", "from pkg.sub.b import two\n\ndef test_b():\n    assert two() == 2\n")],
    )
    r = refcheck.mutation(copy, [("pkg/sub/b.py", SRC_B)], ["tests/test_b.py"], limit=3)
    # stem is "b" (Path("pkg/sub/b.py").stem == "b")
    # "from pkg.sub.b import" contains "from pkg.sub.b import" → the pattern "from X.<stem> import"
    # Expected: not skipped
    assert r["skipped"] == []
    assert r["total"] == 3


# ---- 7. JavaScript: import path ends in stem ----

def test_js_import_ends_in_stem(tmp_path, monkeypatch):
    """pkg/b.js stem 'b'; test has require('./b') → path ends in 'b' → match. Not skipped."""
    patch_env(monkeypatch)
    src_js = "function two() { return 1 + 1; }\n"
    test_js = "const { two } = require('./b');\ntest('two', () => { assert(two() === 2); });\n"
    copy = build_copy(
        tmp_path,
        [("pkg/b.js", src_js)],
        [("tests/test_b.js", test_js)],
    )
    r = refcheck.mutation(copy, [("pkg/b.js", src_js)], ["tests/test_b.js"], limit=3)
    # JS rule: require path './b' ends in 'b' → match
    # Expected: not skipped
    assert r["skipped"] == []
    assert r["total"] == 3


# ---- 8. JavaScript: import path ends in stem.js ----

def test_js_import_ends_in_stem_js(tmp_path, monkeypatch):
    """pkg/b.js stem 'b'; test has import from './b.js' → path ends in 'b.js' → match."""
    patch_env(monkeypatch)
    src_js = "function two() { return 1 + 1; }\n"
    test_js = "import { two } from './b.js';\ntest('two', () => { assert(two() === 2); });\n"
    copy = build_copy(
        tmp_path,
        [("pkg/b.js", src_js)],
        [("tests/test_b.js", test_js)],
    )
    r = refcheck.mutation(copy, [("pkg/b.js", src_js)], ["tests/test_b.js"], limit=3)
    # path './b.js' ends in 'b.js' → match
    # Expected: not skipped
    assert r["skipped"] == []
    assert r["total"] == 3


# ---- 9. JavaScript: NOT imported → skipped ----

def test_js_file_not_imported_skipped(tmp_path, monkeypatch):
    """pkg/b.js stem 'b'; test imports './c' → no match. All skipped."""
    patch_env(monkeypatch)
    src_js = "function two() { return 1 + 1; }\n"
    test_js = "import { three } from './c';\ntest('c', () => { assert(three() === 3); });\n"
    copy = build_copy(
        tmp_path,
        [("pkg/b.js", src_js)],
        [("tests/test_b.js", test_js)],
    )
    r = refcheck.mutation(copy, [("pkg/b.js", src_js)], ["tests/test_b.js"], limit=3)
    # path './c' does not end in 'b' or 'b.js' → no match
    # Expected: all skipped
    assert r == {"total": 0, "killed": 0, "survivors": [], "skipped": ["pkg/b.js"]}


# ---- 10. Other language (C#): stem in test text ----

def test_other_language_stem_in_text(tmp_path, monkeypatch):
    """pkg/calc.cs stem 'calc'; test text contains 'Calc' (case-insensitive not required,
    task says 'stem appears in test text'). Use exact lower-case 'calc' in test text.
    Not skipped."""
    patch_env(monkeypatch)
    src_cs = "public static int Two() { return 2; }\n"
    test_cs = "using calc;\n[Fact]\npublic void Test() { Assert.Equal(2, calc.Two()); }\n"
    copy = build_copy(
        tmp_path,
        [("pkg/calc.cs", src_cs)],
        [("tests/CalcTests.cs", test_cs)],
    )
    r = refcheck.mutation(copy, [("pkg/calc.cs", src_cs)], ["tests/CalcTests.cs"], limit=3)
    # stem "calc" appears in the test text → match
    # Expected: not skipped
    assert r["skipped"] == []
    assert r["total"] == 3


# ---- 11. Other language: stem NOT in test text → skipped ----

def test_other_language_stem_not_in_text(tmp_path, monkeypatch):
    """pkg/calc.cs stem 'calc'; test text has 'math' only → no match. All skipped."""
    patch_env(monkeypatch)
    src_cs = "public static int Two() { return 2; }\n"
    test_cs = "using math;\n[Fact]\npublic void Test() { Assert.Equal(2, math.Add()); }\n"
    copy = build_copy(
        tmp_path,
        [("pkg/calc.cs", src_cs)],
        [("tests/MathTests.cs", test_cs)],
    )
    r = refcheck.mutation(copy, [("pkg/calc.cs", src_cs)], ["tests/MathTests.cs"], limit=3)
    # stem "calc" does NOT appear in test text
    # Expected: all skipped
    assert r == {"total": 0, "killed": 0, "survivors": [], "skipped": ["pkg/calc.cs"]}


# ---- 12. Multiple test files: at least one imports → not skipped ----

def test_multiple_tests_one_importer(tmp_path, monkeypatch):
    """pkg/b.py stem 'b'; test_a imports pkg.a, test_b imports pkg.b → at least one
    importer exists. Not skipped."""
    patch_env(monkeypatch)
    src_a = "def one():\n    return 1\n"
    copy = build_copy(
        tmp_path,
        [("pkg/a.py", src_a)],
        [("tests/test_a.py", "from pkg.a import one\n\ndef test_a():\n    assert one() == 1\n"),
         ("tests/test_b.py", "import b\n\ndef test_b():\n    pass\n")],
    )
    # stem is 'a'; test_a imports pkg.a → match
    r = refcheck.mutation(copy, [("pkg/a.py", src_a)], ["tests/test_a.py", "tests/test_b.py"], limit=3)
    # Expected: not skipped, total = 3
    assert r["skipped"] == []
    assert r["total"] == 3


# ---- 13. Empty files → existing early return (no skipped key added) ----

def test_empty_files_early_return(tmp_path, monkeypatch):
    """files=[] → existing early return {"total": 0, "killed": 0, "survivors": []}.
    The task says 'add skipped to the existing return dict', so the result also has skipped=[]."""
    patch_env(monkeypatch)
    copy = tmp_path / "copy"
    copy.mkdir()
    r = refcheck.mutation(copy, [], ["tests/test_b.py"], limit=3)
    # no files → nothing to check → skipped=[] added to the existing dict
    assert r["total"] == 0
    assert r["killed"] == 0
    assert r["survivors"] == []
    assert r["skipped"] == []


# ---- 14. Survivors + skipped coexist in the result ----

def test_survivors_and_skipped_coexist(tmp_path, monkeypatch):
    """pkg/a.py imported (weak test → survivors), pkg/b.py not imported (skipped).
    Result has both survivors and skipped."""
    patch_env(monkeypatch, passing=True)  # tests pass for all mutants (weak)
    src_a = "def one():\n    return 1\n"
    src_b = "def two():\n    return 1 + 1\n"
    copy = build_copy(
        tmp_path,
        [("pkg/a.py", src_a), ("pkg/b.py", src_b)],
        [("tests/test_a.py", "from pkg.a import one\n\ndef test_a():\n    assert one is not None\n")],
    )
    r = refcheck.mutation(copy, [("pkg/a.py", src_a), ("pkg/b.py", src_b)],
                          ["tests/test_a.py"], limit=4)
    # pkg/a.py stem 'a' → imported; pkg/b.py stem 'b' → not
    # Expected: skipped contains "pkg/b.py"
    assert "pkg/b.py" in r["skipped"]
    # Expected: survivors present (tests pass for all mutants of pkg/a.py)
    assert len(r["survivors"]) > 0


# ---- 15. Multiple files, all skipped → all paths in skipped list ----

def test_all_skipped_multiple_paths(tmp_path, monkeypatch):
    """pkg/a.py stem 'a', pkg/b.py stem 'b'; test imports pkg.c → neither is imported.
    Result: {"total": 0, "killed": 0, "survivors": [], "skipped": ["pkg/a.py", "pkg/b.py"]}."""
    patch_env(monkeypatch)
    src_a = "def one():\n    return 1\n"
    src_b = "def two():\n    return 1 + 1\n"
    copy = build_copy(
        tmp_path,
        [("pkg/a.py", src_a), ("pkg/b.py", src_b)],
        [("tests/test_c.py", "from pkg.c import three\n\ndef test_c():\n    assert three() == 3\n")],
    )
    r = refcheck.mutation(copy, [("pkg/a.py", src_a), ("pkg/b.py", src_b)],
                          ["tests/test_c.py"], limit=4)
    # stem 'a' not in test text, stem 'b' not in test text
    # Expected: all skipped, in files order
    # Expected: total=0, killed=0, survivors=[], skipped=["pkg/a.py", "pkg/b.py"]
    assert r == {"total": 0, "killed": 0, "survivors": [], "skipped": ["pkg/a.py", "pkg/b.py"]}
