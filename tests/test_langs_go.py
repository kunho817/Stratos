"""Tests for task t1: GoTest(Runner) added to stratos/langs.py.

GoTest.test_cmd(tests, parallel=False) returns [*project["test_command"], *packages] where packages are derived
from each test file path (before "::"): the folder prefix with forward slashes, prefixed by "./"; a top-level file
(no directory) gives ".". Packages are deduplicated, preserving first-seen order.

runner(project) with project["test_runner"] == "go test" returns GoTest.
"""

from stratos import langs

GO = {"test_runner": "go test", "test_command": ["go", "test"], "test_dir": "."}


def test_runner_selects_gotest():
    """runner() with test_runner "go test" returns a GoTest instance."""
    # project has test_runner = "go test"
    r = langs.runner(GO)
    # Expected: GoTest instance, and .project is the dict we passed
    assert type(r) is langs.GoTest
    assert r.project is GO


def test_runner_no_go_test_key_is_base_runner():
    """A project with no test_runner key returns the base Runner."""
    # {"test_command": ["x"]} has no "test_runner"
    r = langs.runner({"test_command": ["x"]})
    # Expected: base Runner, not GoTest
    assert type(r) is langs.Runner


def test_go_test_cmd_single_folder():
    """A test in a sub-folder "pkg/a_test.go" yields the file path "pkg/a_test.go"."""
    r = langs.GoTest(GO)
    # test file: "pkg/a_test.go" → file path "pkg/a_test.go"
    # Expected command: ["go", "test", "pkg/a_test.go"]
    got = r.test_cmd(["pkg/a_test.go"])
    assert got == ["go", "test", "pkg/a_test.go"]


def test_go_test_cmd_top_level_file():
    """A top-level test file "main_test.go" yields the file path "main_test.go"."""
    r = langs.GoTest(GO)
    # test file "main_test.go" has no directory → file path "main_test.go"
    # Expected command: ["go", "test", "main_test.go"]
    got = r.test_cmd(["main_test.go"])
    assert got == ["go", "test", "main_test.go"]


def test_go_test_cmd_multiple_files_deduplicate_in_order():
    """Files deduplicate by path; order of first occurrence is preserved."""
    r = langs.GoTest(GO)
    # files: "pkg/a_test.go", "pkg/b_test.go", "main_test.go" (all distinct paths)
    # Expected command: ["go", "test", "pkg/a_test.go", "pkg/b_test.go", "main_test.go"]
    got = r.test_cmd(["pkg/a_test.go", "pkg/b_test.go", "main_test.go"])
    assert got == ["go", "test", "pkg/a_test.go", "pkg/b_test.go", "main_test.go"]


def test_go_test_cmd_strips_double_colon():
    """A path like "pkg/inner_test.go::TestX" strips "::TestX" to give the file path "pkg/inner_test.go"."""
    r = langs.GoTest(GO)
    # "pkg/inner_test.go::TestX" → strip "::TestX" → "pkg/inner_test.go"
    # Expected command: ["go", "test", "pkg/inner_test.go"]
    got = r.test_cmd(["pkg/inner_test.go::TestX"])
    assert got == ["go", "test", "pkg/inner_test.go"]


def test_go_test_cmd_nested_folder_forward_slashes():
    """A test in "pkg/sub/a_test.go" yields the file path "pkg/sub/a_test.go" (forward slashes)."""
    r = langs.GoTest(GO)
    # "pkg/sub/a_test.go" → file path "pkg/sub/a_test.go"
    # Expected command: ["go", "test", "pkg/sub/a_test.go"]
    got = r.test_cmd(["pkg/sub/a_test.go"])
    assert got == ["go", "test", "pkg/sub/a_test.go"]


def test_go_test_cmd_parallel_is_ignored():
    """GoTest.test_cmd ignores the parallel keyword (go test handles parallelism via -parallel flag, not
    package-level parallelism); the command is the same as non-parallel."""
    r = langs.GoTest(GO)
    # parallel=True should not change the output
    # Expected command: ["go", "test", "pkg/a_test.go"]
    got = r.test_cmd(["pkg/a_test.go"], parallel=True)
    assert got == ["go", "test", "pkg/a_test.go"]


def test_go_test_cmd_preserves_first_seen_order():
    """File paths appear in first-seen order."""
    r = langs.GoTest(GO)
    # files: "main_test.go" → "main_test.go", "pkg/a_test.go" → "pkg/a_test.go"
    # Expected command: ["go", "test", "main_test.go", "pkg/a_test.go"]
    got = r.test_cmd(["main_test.go", "pkg/a_test.go"])
    assert got == ["go", "test", "main_test.go", "pkg/a_test.go"]


def test_go_test_cmd_no_tests():
    """An empty tests list yields just the test_command with no packages appended."""
    r = langs.GoTest(GO)
    # no tests → no packages
    # Expected command: ["go", "test"]
    got = r.test_cmd([])
    assert got == ["go", "test"]


def test_go_test_cmd_backslash_normalized():
    """A path with backslashes (Windows-style) is normalized to forward slashes."""
    r = langs.GoTest(GO)
    # "pkg\\sub\\a_test.go" → normalize → "pkg/sub/a_test.go"
    # Expected command: ["go", "test", "pkg/sub/a_test.go"]
    got = r.test_cmd(["pkg\\sub\\a_test.go"])
    assert got == ["go", "test", "pkg/sub/a_test.go"]


def test_go_test_is_runner_subclass():
    """GoTest inherits from Runner."""
    # Expected: GoTest is a subclass of Runner
    assert issubclass(langs.GoTest, langs.Runner)


def test_go_test_with_paths_is_base():
    """GoTest inherits with_paths from Runner unchanged."""
    r = langs.GoTest(GO)
    # with_paths on a command with "{files}"
    # Expected: base behavior replaces "{files}" with paths
    got = r.with_paths(["go", "build", "{files}"], ["pkg/a.go", "pkg/b.go"])
    assert got == ["go", "build", "pkg/a.go", "pkg/b.go"]


def test_go_test_scope_is_base():
    """GoTest.scope is the base context manager (does nothing)."""
    r = langs.GoTest(GO)
    # Expected: scope yields without writing files
    with r.scope("/tmp", ["pkg/a_test.go"]):
        pass  # no exception, no file writes required
