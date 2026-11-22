"""Tests for task plan_go_test_paths: Go test runner drops the test_dir prefix in parse_plan's test-path check.

In stratos/plan.py, parse_plan validates each task's "tests" list. When
config.PROJECT.get("test_runner") == "go test", a test path only needs to end with one of
test_suffixes; the "starts with <test_dir>/" requirement is dropped. For every other runner
(pytest, node, dotnet, or no test_runner key), the full check (prefix AND suffix) is unchanged.
"""

import json

import pytest

from stratos import config, plan


GO = {"test_dir": "rota", "test_suffixes": ["_test.go"], "test_runner": "go test"}
PY = {"test_dir": "tests", "test_suffixes": [".py"]}


def one_task(tests, key="a", files=None):
    """Build a single-task plan JSON with the given tests list."""
    if files is None:
        files = ["rota/calc.go"]
    return json.dumps({"tasks": [{"key": key, "title": "t", "goal": "g",
                                  "files": files, "tests": tests,
                                  "protected": [], "after": [], "role": "coder"}]})


def test_go_test_accepts_path_outside_test_dir(tmp_path, monkeypatch):
    """go test: 'calc_test.go' (no 'rota/' prefix) passes — only the suffix matters."""
    monkeypatch.setattr(config, "PROJECT", GO)
    # Step: "calc_test.go" does NOT start with "rota/" and ends with "_test.go" → accepted.
    result = plan.parse_plan(one_task(["calc_test.go"]))
    # Step: the test list is kept as-is.
    assert result[0]["tests"] == ["calc_test.go"]


def test_go_test_suffix_check_still_applies(tmp_path, monkeypatch):
    """go test: a path without a valid suffix is still rejected."""
    monkeypatch.setattr(config, "PROJECT", GO)
    # Step: "calc.go" ends with ".go", not "_test.go" → rejected.
    with pytest.raises(plan.PlanError) as exc:
        plan.parse_plan(one_task(["calc.go"]))
    # Step: the message names the task key.
    assert "a" in str(exc.value)
    # Step: the suffix "_test.go" appears in the message.
    assert "_test.go" in str(exc.value)


def test_go_test_all_tests_must_have_suffix(tmp_path, monkeypatch):
    """go test: every entry in the tests list must end with a valid suffix."""
    monkeypatch.setattr(config, "PROJECT", GO)
    # Step: first test "calc_test.go" is fine, second "helper.go" is not → rejected.
    with pytest.raises(plan.PlanError):
        plan.parse_plan(one_task(["calc_test.go", "helper.go"]))


def test_go_test_path_with_prefix_also_passes(tmp_path, monkeypatch):
    """go test: a path that DOES start with test_dir/ is not forbidden, just not required."""
    monkeypatch.setattr(config, "PROJECT", GO)
    # Step: "rota/calc_test.go" has both prefix and suffix → accepted.
    result = plan.parse_plan(one_task(["rota/calc_test.go"]))
    # Step: the path is preserved.
    assert result[0]["tests"] == ["rota/calc_test.go"]


def test_pytest_rejects_path_without_prefix(tmp_path, monkeypatch):
    """pytest: 'calc_test.py' without the 'tests/' prefix is rejected (unchanged rule)."""
    monkeypatch.setattr(config, "PROJECT", PY)
    # Step: "calc_test.py" lacks "tests/" prefix → rejected.
    with pytest.raises(plan.PlanError) as exc:
        plan.parse_plan(one_task(["calc_test.py"], files=["calc.py"]))
    # Step: the error names the task key.
    assert "a" in str(exc.value)


def test_pytest_accepts_path_with_prefix(tmp_path, monkeypatch):
    """pytest: 'tests/test_a.py' passes (prefix + suffix, unchanged)."""
    monkeypatch.setattr(config, "PROJECT", PY)
    # Step: "tests/test_a.py" starts with "tests/" and ends with ".py" → accepted.
    result = plan.parse_plan(one_task(["tests/test_a.py"], files=["stratos/a.py"]))
    # Step: the test list is kept.
    assert result[0]["tests"] == ["tests/test_a.py"]


def test_no_test_runner_key_keeps_prefix_check(tmp_path, monkeypatch):
    """When test_runner is absent from PROJECT, the prefix check stays (pytest behaviour)."""
    proj = {"test_dir": "tests", "test_suffixes": [".py"]}
    monkeypatch.setattr(config, "PROJECT", proj)
    # Step: "test_a.py" has no "tests/" prefix → rejected.
    with pytest.raises(plan.PlanError):
        plan.parse_plan(one_task(["test_a.py"], files=["a.py"]))


def test_node_runner_keeps_prefix_check(tmp_path, monkeypatch):
    """node --test runner: the prefix check stays as before."""
    proj = {"test_dir": "spec", "test_suffixes": [".test.js"], "test_runner": "node --test"}
    monkeypatch.setattr(config, "PROJECT", proj)
    # Step: "x.test.js" lacks "spec/" prefix → rejected.
    with pytest.raises(plan.PlanError):
        plan.parse_plan(one_task(["x.test.js"], files=["x.js"]))


def test_dotnet_runner_keeps_prefix_check(tmp_path, monkeypatch):
    """dotnet test runner: the prefix check stays as before."""
    proj = {"test_dir": "tests", "test_suffixes": [".cs"], "test_runner": "dotnet test"}
    monkeypatch.setattr(config, "PROJECT", proj)
    # Step: "a_test.cs" lacks "tests/" prefix → rejected.
    with pytest.raises(plan.PlanError):
        plan.parse_plan(one_task(["a_test.cs"], files=["a.cs"]))


def test_go_test_multi_task_plan(tmp_path, monkeypatch):
    """go test: two tasks with tests outside the test_dir both pass."""
    monkeypatch.setattr(config, "PROJECT", GO)
    tasks = [
        {"key": "a", "title": "A", "goal": "g", "files": ["rota/a.go"],
         "tests": ["a_test.go"], "protected": [], "after": [], "role": "coder"},
        {"key": "b", "title": "B", "goal": "g", "files": ["rota/b.go"],
         "tests": ["b_test.go"], "protected": [], "after": ["a"], "role": "coder"},
    ]
    text = json.dumps({"tasks": tasks})
    result = plan.parse_plan(text)
    # Step: task a tests = ["a_test.go"] (no prefix, valid suffix).
    assert result[0]["tests"] == ["a_test.go"]
    # Step: task b tests = ["b_test.go"] (no prefix, valid suffix).
    assert result[1]["tests"] == ["b_test.go"]


def test_go_test_empty_tests_rejected(tmp_path, monkeypatch):
    """go test: an empty tests list is rejected (unchanged, the non-empty check is first)."""
    monkeypatch.setattr(config, "PROJECT", GO)
    # Step: tests = [] → PlanError "tests must be a non-empty list".
    with pytest.raises(plan.PlanError):
        plan.parse_plan(one_task([]))


def test_go_test_files_can_be_under_test_dir(tmp_path, monkeypatch):
    """go test: files under test_dir are allowed (only the 'all files under test_dir'
    rule applies, same as before — it is not about test paths)."""
    monkeypatch.setattr(config, "PROJECT", GO)
    # Step: files=["rota/calc.go"] is under "rota/" → not all-under-test_dir, fine.
    result = plan.parse_plan(one_task(["calc_test.go"], files=["rota/calc.go"]))
    # Step: files preserved.
    assert result[0]["files"] == ["rota/calc.go"]
    # Step: tests preserved.
    assert result[0]["tests"] == ["calc_test.go"]
