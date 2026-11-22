"""Tests for GoTest.test_cmd returning test file paths (not package folders).

GoTest.test_cmd(tests, parallel=False) returns [*project["test_command"], *files] where files
are the test file paths themselves (the part before '::', backslashes normalized to '/',
deduplicated in first-seen order). Go compiles each named file independently, so passing
file paths avoids the whole-folder rebuild problem.

runner(project) with project["test_runner"] == "go test" returns GoTest.
"""

from stratos import config, langs

GO = {"test_runner": "go test", "test_command": ["go", "test"], "test_dir": "."}


def test_runner_selects_gotest():
    """runner() with test_runner 'go test' returns GoTest, and test_cmd returns file paths."""
    r = langs.runner(GO)
    # Expected: GoTest instance, .project is the dict passed
    assert type(r) is langs.GoTest
    assert r.project is GO
    # "pkg/a_test.go" → file path "pkg/a_test.go" (not "./pkg")
    # Expected command: ["go", "test", "pkg/a_test.go"]
    got = r.test_cmd(["pkg/a_test.go"])
    assert got == ["go", "test", "pkg/a_test.go"]


def test_runner_no_go_test_key_is_base_runner():
    """A project with no test_runner key returns the base Runner."""
    # {"test_command": ["x"]} has no "test_runner"
    r = langs.runner({"test_command": ["x"]})
    # Expected: base Runner, not GoTest
    assert type(r) is langs.Runner


def test_go_test_cmd_single_file_path():
    """A test in a sub-folder yields the file path itself, not a package folder."""
    r = langs.GoTest(GO)
    # "pkg/a_test.go" → strip "::" → "pkg/a_test.go" → no backslashes → file path
    # Expected command: ["go", "test", "pkg/a_test.go"]
    got = r.test_cmd(["pkg/a_test.go"])
    assert got == ["go", "test", "pkg/a_test.go"]


def test_go_test_cmd_top_level_file_path():
    """A top-level test file yields the file path itself, not '.'."""
    r = langs.GoTest(GO)
    # "main_test.go" → file path "main_test.go"
    # Expected command: ["go", "test", "main_test.go"]
    got = r.test_cmd(["main_test.go"])
    assert got == ["go", "test", "main_test.go"]


def test_go_test_cmd_strips_double_colon():
    """'pkg/inner_test.go::TestX' strips '::TestX' to give the file path 'pkg/inner_test.go'."""
    r = langs.GoTest(GO)
    # "pkg/inner_test.go::TestX" → split("::")[0] → "pkg/inner_test.go"
    # Expected command: ["go", "test", "pkg/inner_test.go"]
    got = r.test_cmd(["pkg/inner_test.go::TestX"])
    assert got == ["go", "test", "pkg/inner_test.go"]


def test_go_test_cmd_nested_folder_forward_slashes():
    """'pkg/sub/a_test.go' yields 'pkg/sub/a_test.go' with forward slashes."""
    r = langs.GoTest(GO)
    # "pkg/sub/a_test.go" → file path "pkg/sub/a_test.go"
    # Expected command: ["go", "test", "pkg/sub/a_test.go"]
    got = r.test_cmd(["pkg/sub/a_test.go"])
    assert got == ["go", "test", "pkg/sub/a_test.go"]


def test_go_test_cmd_backslash_normalized():
    """Windows backslashes in 'pkg\\sub\\a_test.go' are normalized to forward slashes."""
    r = langs.GoTest(GO)
    # "pkg\\sub\\a_test.go" → replace("\\", "/") → "pkg/sub/a_test.go"
    # Expected command: ["go", "test", "pkg/sub/a_test.go"]
    got = r.test_cmd(["pkg\\sub\\a_test.go"])
    assert got == ["go", "test", "pkg/sub/a_test.go"]


def test_go_test_cmd_parallel_is_ignored():
    """parallel=True does not change the output; the file path is returned as-is."""
    r = langs.GoTest(GO)
    # parallel=True → same result as parallel=False
    # "pkg/a_test.go" → file path "pkg/a_test.go"
    # Expected command: ["go", "test", "pkg/a_test.go"]
    got = r.test_cmd(["pkg/a_test.go"], parallel=True)
    assert got == ["go", "test", "pkg/a_test.go"]


def test_go_test_cmd_preserves_first_seen_order():
    """File paths appear in first-seen order: 'main_test.go' before 'pkg/a_test.go'."""
    r = langs.GoTest(GO)
    # files: "main_test.go" → "main_test.go" (seen first)
    #        "pkg/a_test.go" → "pkg/a_test.go" (seen second)
    # Expected command: ["go", "test", "main_test.go", "pkg/a_test.go"]
    got = r.test_cmd(["main_test.go", "pkg/a_test.go"])
    assert got == ["go", "test", "main_test.go", "pkg/a_test.go"]


def test_go_test_cmd_deduplicates_by_file_path():
    """Duplicate file paths (after stripping '::') are removed, keeping first-seen order."""
    r = langs.GoTest(GO)
    # "pkg/a_test.go" → "pkg/a_test.go" (first, added)
    # "pkg/a_test.go::TestX" → "pkg/a_test.go" (dup, skip)
    # "pkg/b_test.go" → "pkg/b_test.go" (new, added)
    # deduplicated: ["pkg/a_test.go", "pkg/b_test.go"]
    # Expected command: ["go", "test", "pkg/a_test.go", "pkg/b_test.go"]
    got = r.test_cmd(["pkg/a_test.go", "pkg/a_test.go::TestX", "pkg/b_test.go"])
    assert got == ["go", "test", "pkg/a_test.go", "pkg/b_test.go"]


def test_go_test_cmd_no_tests():
    """An empty tests list yields just the test_command with no file paths appended."""
    r = langs.GoTest(GO)
    # no tests → no files
    # Expected command: ["go", "test"]
    got = r.test_cmd([])
    assert got == ["go", "test"]


def test_go_test_is_runner_subclass():
    """GoTest inherits from Runner."""
    # Expected: GoTest is a subclass of Runner
    assert issubclass(langs.GoTest, langs.Runner)


def test_go_test_with_paths_is_base():
    """GoTest inherits with_paths from Runner unchanged."""
    r = langs.GoTest(GO)
    # with_paths with "{files}" → base behaviour replaces "{files}" with paths
    # Expected: ["go", "build", "pkg/a.go", "pkg/b.go"]
    got = r.with_paths(["go", "build", "{files}"], ["pkg/a.go", "pkg/b.go"])
    assert got == ["go", "build", "pkg/a.go", "pkg/b.go"]


def test_go_test_scope_is_base():
    """GoTest.scope is the base context manager (does nothing)."""
    r = langs.GoTest(GO)
    # Expected: scope yields without writing files
    with r.scope("/tmp", ["pkg/a_test.go"]):
        pass  # no exception, no file writes required
