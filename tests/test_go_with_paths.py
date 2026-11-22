"""Tests for task go_with_paths: GoTest.with_paths in stratos/langs.py.

GoTest.with_paths(cmd, paths) mirrors Dotnet's rule:
  - If "{files}" is NOT in cmd, return list(cmd) unchanged (paths are NOT appended).
    go build/vet take package paths like "./...", not .go file paths, so appending .go files fails.
  - If "{files}" IS in cmd, delegate to super().with_paths(cmd, paths) (base Runner behaviour:
    every "{files}" token is replaced by the paths in order).
"""

from stratos import langs

GO = {"test_runner": "go test", "test_command": ["go", "test"], "test_dir": "."}


def test_go_with_paths_no_files_returns_cmd_unchanged():
    """No '{files}' in cmd: paths are NOT appended; the command is returned as-is."""
    r = langs.GoTest(GO)
    # cmd has no "{files}": ["go", "build", "./..."], paths = ["calc/a.go"]
    # Expected: list(cmd) = ["go", "build", "./..."], paths not appended
    got = r.with_paths(["go", "build", "./..."], ["calc/a.go"])
    assert got == ["go", "build", "./..."]


def test_go_with_paths_no_files_returns_a_new_list():
    """No '{files}': the returned list is a new object, not the cmd argument itself."""
    r = langs.GoTest(GO)
    # cmd = ["go", "vet", "./..."]
    cmd = ["go", "vet", "./..."]
    # Expected: a new list equal to cmd, not the same object
    got = r.with_paths(cmd, ["calc/a.go"])
    assert got == ["go", "vet", "./..."]
    # Expected: got is NOT cmd (identity check: a new list was created)
    assert got is not cmd


def test_go_with_paths_no_files_multiple_paths_not_appended():
    """No '{files}': many paths must not be appended to the command."""
    r = langs.GoTest(GO)
    # cmd = ["go", "build", "./..."], paths = ["calc/a.go", "calc/b.go", "main.go"]
    # Expected: only cmd elements, no paths appended
    got = r.with_paths(["go", "build", "./..."], ["calc/a.go", "calc/b.go", "main.go"])
    # Expected: ["go", "build", "./..."]
    assert got == ["go", "build", "./..."]


def test_go_with_paths_no_files_empty_paths():
    """No '{files}': even with empty paths, the command is returned unchanged."""
    r = langs.GoTest(GO)
    # cmd = ["go", "build"], paths = []
    # Expected: ["go", "build"]
    got = r.with_paths(["go", "build"], [])
    # Expected: ["go", "build"]
    assert got == ["go", "build"]


def test_go_with_paths_files_substitutes():
    """'{files}' in cmd: base Runner behaviour replaces '{files}' with the paths."""
    r = langs.GoTest(GO)
    # cmd = ["go", "build", "{files}"], paths = ["pkg/a.go", "pkg/b.go"]
    # Expected: base behaviour → ["go", "build", "pkg/a.go", "pkg/b.go"]
    got = r.with_paths(["go", "build", "{files}"], ["pkg/a.go", "pkg/b.go"])
    # Expected: ["go", "build", "pkg/a.go", "pkg/b.go"]
    assert got == ["go", "build", "pkg/a.go", "pkg/b.go"]


def test_go_with_paths_files_preserves_surrounding_items():
    """'{files}' in cmd: items before and after '{files}' are kept."""
    r = langs.GoTest(GO)
    # cmd = ["tool", "{files}", "--x"], paths = ["a.go", "b.go"]
    # Expected: base behaviour → ["tool", "a.go", "b.go", "--x"]
    got = r.with_paths(["tool", "{files}", "--x"], ["a.go", "b.go"])
    # Expected: ["tool", "a.go", "b.go", "--x"]
    assert got == ["tool", "a.go", "b.go", "--x"]


def test_go_with_paths_files_multiple_files_tokens():
    """Multiple '{files}' tokens: each is replaced by the paths (base Runner behaviour)."""
    r = langs.GoTest(GO)
    # cmd = ["x", "{files}", "y", "{files}"], paths = ["a.go"]
    # Expected: base behaviour → ["x", "a.go", "y", "a.go"]
    got = r.with_paths(["x", "{files}", "y", "{files}"], ["a.go"])
    # Expected: ["x", "a.go", "y", "a.go"]
    assert got == ["x", "a.go", "y", "a.go"]
