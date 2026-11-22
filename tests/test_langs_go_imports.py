"""Tests for task t6: GoTest.missing_import(output) override in stratos/langs.py.

GoTest.missing_import(output) returns True when the output contains any of:
  - "undefined: "
  - "no required module provides package"
  - "could not import"
In addition to the base Runner behaviour: True when "ModuleNotFoundError" or
"ImportError" appears, or a C# error r"error CS0(103|246|234)\\b" matches.
Non-matching output returns False (not a truthy regex match).
"""

from stratos import langs

GO = {"test_runner": "go test", "test_command": ["go", "test"], "test_dir": "."}
PY = {"test_runner": "pytest", "test_command": ["py", "-m", "pytest", "-q"], "test_dir": "tests"}


def test_go_undefined_phrase_returns_true():
    """Output containing "undefined: " is a missing import."""
    r = langs.GoTest(GO)
    # "undefined: " is one of the three Go phrases
    # Expected: True
    assert r.missing_import("pkg/a.go:5:10: undefined: x") is True


def test_go_undefined_in_longer_output():
    """"undefined: " embedded in a multi-line go build output is detected."""
    r = langs.GoTest(GO)
    output = "go build ./pkg\n# ./pkg\npkg/a.go:12:1: undefined: Foo\npkg/b.go:3:5: undefined: Bar\n"
    # Contains "undefined: "
    # Expected: True
    assert r.missing_import(output) is True


def test_go_no_required_module_phrase():
    """Output containing "no required module provides package" is a missing import."""
    r = langs.GoTest(GO)
    # "no required module provides package" is the second Go phrase
    # Expected: True
    assert r.missing_import("no required module provides package x/y/z\n") is True


def test_go_no_required_module_in_context():
    """The phrase embedded in a go build warning is detected."""
    r = langs.GoTest(GO)
    output = "# ./pkg\nno required module provides package github.com/foo/bar; to add it:\n\tgo get github.com/foo/bar\n"
    # Contains "no required module provides package"
    # Expected: True
    assert r.missing_import(output) is True


def test_go_could_not_import_phrase():
    """Output containing "could not import" is a missing import."""
    r = langs.GoTest(GO)
    # "could not import" is the third Go phrase
    # Expected: True
    assert r.missing_import("could not import x/y/z (no required module)\n") is True


def test_go_could_not_import_in_longer_output():
    """"could not import" within a multi-line go output is detected."""
    r = langs.GoTest(GO)
    output = "go vet ./...\npkg/a.go:4:10: could not import x/y (no required module)\n"
    # Contains "could not import"
    # Expected: True
    assert r.missing_import(output) is True


def test_go_base_module_not_found_preserved():
    """GoTest also detects the base Runner's ModuleNotFoundError."""
    r = langs.GoTest(GO)
    # Base Runner behaviour: "ModuleNotFoundError" in output
    # Expected: True
    assert r.missing_import("E   ModuleNotFoundError: No module named 'pkg.x'") is True


def test_go_base_import_error_preserved():
    """GoTest also detects the base Runner's ImportError."""
    r = langs.GoTest(GO)
    # Base Runner behaviour: "ImportError" in output
    # Expected: True
    assert r.missing_import("ImportError: cannot import name 'y'") is True


def test_go_base_cs0103_preserved():
    """GoTest also detects the base Runner's C# CS0103 error."""
    r = langs.GoTest(GO)
    # Base Runner behaviour: "error CS0103" matches r"error CS0(103|246|234)\\b"
    # Expected: True
    assert r.missing_import("error CS0103: The name 'x' does not exist") is True


def test_go_base_cs0246_preserved():
    """GoTest also detects the base Runner's C# CS0246 error."""
    r = langs.GoTest(GO)
    # Base Runner behaviour: "error CS0246" matches r"error CS0(103|246|234)\\b"
    # Expected: True
    assert r.missing_import("A.cs(3,1): error CS0246: The type or namespace name 'Expense'") is True


def test_go_base_cs0234_preserved():
    """GoTest also detects the base Runner's C# CS0234 error."""
    r = langs.GoTest(GO)
    # Base Runner behaviour: "error CS0234" matches r"error CS0(103|246|234)\\b"
    # Expected: True
    assert r.missing_import("error CS0234: Namespace 'System' does not contain a definition for 'Linq'") is True


def test_go_non_matching_returns_false():
    """Assertion failure output is not a missing import."""
    r = langs.GoTest(GO)
    # "AssertionError" is not any of the base phrases nor the Go phrases
    # Expected: False
    assert r.missing_import("AssertionError: 1 != 2") is False


def test_go_empty_output_returns_false():
    """Empty output is not a missing import."""
    r = langs.GoTest(GO)
    # No phrases present
    # Expected: False
    assert r.missing_import("") is False


def test_go_cs1002_not_matched():
    """C# error CS1002 (; expected) is not in the CS0(103|246|234) pattern, and no Go phrase is present."""
    r = langs.GoTest(GO)
    # "error CS1002" does not match r"error CS0(103|246|234)\\b" (CS1002 ≠ CS0103/CS0246/CS0234)
    # Expected: False
    assert r.missing_import("error CS1002: ; expected") is False


def test_go_all_three_phrases_in_one_output():
    """All three Go phrases in one output; missing_import returns True."""
    r = langs.GoTest(GO)
    output = "undefined: Foo\nno required module provides package bar\ncould not import baz\n"
    # Contains all three phrases
    # Expected: True
    assert r.missing_import(output) is True
