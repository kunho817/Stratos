"""Tests for task langs_not_in_std: GoTest.missing_import detects "is not in std" in stratos/langs.py.

Go reports a package folder with no Go source files as e.g.
  "package rota/rota is not in std"
This is Go's way of saying "no code yet" (the package exists as a folder but has no
importable Go files), so it is treated as a missing import.

GoTest.missing_import(output) returns True when the output contains any of:
  - "undefined: "
  - "no required module provides package"
  - "could not import"
  - "is not in std"
In addition to the base Runner behaviour: True when "ModuleNotFoundError" or
"ImportError" appears, or a C# error r"error CS0(103|246|234)\\b" matches.
Non-matching output returns False.
"""

from stratos import langs

GO = {"test_runner": "go test", "test_command": ["go", "test"], "test_dir": "."}


def test_go_not_in_std_returns_true():
    """Go's "package X is not in std" message is a missing import."""
    r = langs.GoTest(GO)
    # Step: output contains the exact Go message for a folder with no Go files.
    output = "package rota/rota is not in std\n"
    # Step: "is not in std" is one of the Go phrases GoTest checks → True.
    assert r.missing_import(output) is True


def test_go_not_in_std_in_multi_line_output():
    """"is not in std" embedded in a multi-line go build output is detected."""
    r = langs.GoTest(GO)
    # Step: a realistic go build error block containing the phrase on one line.
    output = "go build ./...\n# ./rota\npackage rota/rota is not in std\nexit status 1\n"
    # Step: "is not in std" is present in the multi-line string → True.
    assert r.missing_import(output) is True


def test_go_not_in_std_as_substring():
    """"is not in std" appearing inside a longer sentence is detected (substring match)."""
    r = langs.GoTest(GO)
    # Step: the phrase is part of a longer sentence.
    output = "warning: package x/y is not in std, try go get\n"
    # Step: "is not in std" is a substring → True.
    assert r.missing_import(output) is True


def test_go_not_in_std_absent_returns_false():
    """Output that does not contain "is not in std" (and no other phrase) returns False."""
    r = langs.GoTest(GO)
    # Step: a plain assertion failure, none of the five phrases present.
    output = "AssertionError: 1 != 2\n"
    # Step: no phrase matched → False.
    assert r.missing_import(output) is False


def test_go_not_in_std_is_not_in_base_runner():
    """The base Runner does NOT detect "is not in std" (GoTest-only phrase)."""
    # Step: a plain Runner (not GoTest) gets the string.
    base = langs.Runner({"test_command": ["x"]})
    # Step: "is not in std" is not ModuleNotFoundError, ImportError, or CS0x → False.
    assert base.missing_import("package x/y is not in std") is False


def test_go_not_in_std_with_undefined_phrase():
    """An output containing BOTH "is not in std" and "undefined: " returns True."""
    r = langs.GoTest(GO)
    # Step: two Go phrases in one output.
    output = "pkg/a.go:3:1: undefined: Foo\npackage rota/rota is not in std\n"
    # Step: "undefined: " is found first in the loop → True.
    assert r.missing_import(output) is True


def test_go_not_in_std_with_no_required_module():
    """An output with "no required module provides package" and "is not in std" returns True."""
    r = langs.GoTest(GO)
    # Step: both phrases present.
    output = "no required module provides package x/y\npackage rota is not in std\n"
    # Step: "no required module provides package" is found in the loop → True.
    assert r.missing_import(output) is True


def test_go_not_in_std_with_could_not_import():
    """An output with "could not import" and "is not in std" returns True."""
    r = langs.GoTest(GO)
    # Step: both phrases present.
    output = "could not import a/b\npackage c is not in std\n"
    # Step: "could not import" is found in the loop → True.
    assert r.missing_import(output) is True


def test_go_undefined_phrase_still_works():
    """The existing "undefined: " phrase is still detected."""
    r = langs.GoTest(GO)
    # Step: "undefined: " is in the output.
    output = "pkg/a.go:5:10: undefined: x\n"
    # Step: "undefined: " matched → True.
    assert r.missing_import(output) is True


def test_go_no_required_module_still_works():
    """The existing "no required module provides package" phrase is still detected."""
    r = langs.GoTest(GO)
    # Step: the phrase is present.
    output = "no required module provides package x/y\n"
    # Step: matched → True.
    assert r.missing_import(output) is True


def test_go_could_not_import_still_works():
    """The existing "could not import" phrase is still detected."""
    r = langs.GoTest(GO)
    # Step: the phrase is present.
    output = "could not import x/y\n"
    # Step: matched → True.
    assert r.missing_import(output) is True


def test_go_base_module_not_found_preserved():
    """GoTest still detects the base Runner's ModuleNotFoundError."""
    r = langs.GoTest(GO)
    # Step: "ModuleNotFoundError" triggers base Runner.
    output = "E   ModuleNotFoundError: No module named 'pkg.x'\n"
    # Step: super().missing_import finds it → True.
    assert r.missing_import(output) is True


def test_go_base_import_error_preserved():
    """GoTest still detects the base Runner's ImportError."""
    r = langs.GoTest(GO)
    # Step: "ImportError" triggers base Runner.
    output = "ImportError: cannot import name 'y'\n"
    # Step: super().missing_import finds it → True.
    assert r.missing_import(output) is True


def test_go_empty_output_returns_false():
    """Empty output contains none of the phrases."""
    r = langs.GoTest(GO)
    # Step: empty string → no match.
    assert r.missing_import("") is False


def test_go_cs0246_preserved():
    """GoTest still detects the base Runner's C# CS0246 error."""
    r = langs.GoTest(GO)
    # Step: "error CS0246" matches the base regex.
    output = "A.cs(3,1): error CS0246: The type or namespace name 'Expense'\n"
    # Step: super().missing_import matches → True.
    assert r.missing_import(output) is True
