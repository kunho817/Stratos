"""Tests for task plan_js_and_test_paths: repo_summary accepts a settings dict with
source_dirs, test_dir, test_suffixes; parse_plan accepts test paths starting with
test_dir + "/" and ending with one of test_suffixes.

repo_summary(root, settings=None)
    settings is a dict with keys "source_dirs" (list of dir names), "test_dir" (str),
    "test_suffixes" (list of str). settings=None means config.PROJECT.
    For each dir in source_dirs, list files in root/<dir> sorted.
    Python files: as before (docstring first line, def/class lines).
    .js/.mjs files: "  export function name(args)" for each export function,
    "  export class Name" for each export class (found by regex).
    Then list files in root/<test_dir> whose name ends with any suffix in test_suffixes.

parse_plan(text)
    Uses config.PROJECT for test_dir and test_suffixes.
    tests entries must start with test_dir + "/" and end with one of test_suffixes.
    With Stratos defaults (test_dir="tests", test_suffixes=[".py"]) same as before.
"""
import json
import re

import pytest

from stratos import config, plan


def make_project(tmp_path, source_dirs, test_dir, test_suffixes, files):
    """Create a fake project tree under tmp_path. Returns tmp_path."""
    for d in source_dirs:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    (tmp_path / test_dir).mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp_path


def test_repo_summary_accepts_settings_parameter(tmp_path):
    """repo_summary(root, settings=...) should work, not raise TypeError."""
    tmp = make_project(
        tmp_path=tmp_path,
        source_dirs=["src"],
        test_dir="test",
        test_suffixes=[".py"],
        files={"src/a.py": '"""Module A."""\ndef foo():\n    pass\n',
               "test/test_a.py": "import a\n"},
    )
    settings = {"source_dirs": ["src"], "test_dir": "test", "test_suffixes": [".py"]}
    out = plan.repo_summary(tmp, settings=settings)
    assert "src/a.py - Module A." in out
    assert "  def foo()" in out
    assert "test/test_a.py" in out


def test_repo_summary_multiple_source_dirs(tmp_path):
    """All dirs in source_dirs are listed."""
    tmp = make_project(
        tmp_path=tmp_path,
        source_dirs=["lib", "core"],
        test_dir="tests",
        test_suffixes=[".py"],
        files={
            "lib/x.py": '"""X."""\ndef bar():\n    pass\n',
            "core/y.py": '"""Y."""\nclass Baz:\n    pass\n',
            "tests/test_x.py": "",
        },
    )
    settings = {"source_dirs": ["lib", "core"], "test_dir": "tests", "test_suffixes": [".py"]}
    out = plan.repo_summary(tmp, settings=settings)
    assert "lib/x.py - X." in out
    assert "core/y.py - Y." in out
    assert "  def bar()" in out
    assert "  class Baz" in out
    assert "tests/test_x.py" in out


def test_repo_summary_js_export_function(tmp_path):
    """A .js file lists export functions as '  export function name(args)'."""
    js_content = """\
import foo from './foo.js';

export function hello(name) {
  return name;
}

export function add(a, b) {
  return a + b;
}

export default hello;
"""
    tmp = make_project(
        tmp_path=tmp_path,
        source_dirs=["app"],
        test_dir="tests",
        test_suffixes=[".py"],
        files={"app/util.js": js_content, "tests/test_x.py": ""},
    )
    settings = {"source_dirs": ["app"], "test_dir": "tests", "test_suffixes": [".py"]}
    out = plan.repo_summary(tmp, settings=settings)
    assert "app/util.js" in out
    assert "  export function hello(name)" in out
    assert "  export function add(a, b)" in out


def test_repo_summary_mjs_export_class(tmp_path):
    """A .mjs file lists export class as '  export class Name'."""
    mjs_content = """\
export class MyWidget extends Base {
  constructor() {}
}

export function helper() {}
"""
    tmp = make_project(
        tmp_path=tmp_path,
        source_dirs=["app"],
        test_dir="tests",
        test_suffixes=[".py"],
        files={"app/widget.mjs": mjs_content, "tests/test_x.py": ""},
    )
    settings = {"source_dirs": ["app"], "test_dir": "tests", "test_suffixes": [".py"]}
    out = plan.repo_summary(tmp, settings=settings)
    assert "app/widget.mjs" in out
    assert "  export class MyWidget" in out
    assert "  export function helper()" in out


def test_repo_summary_test_suffixes_js(tmp_path):
    """test_dir listing includes files matching any suffix in test_suffixes."""
    tmp = make_project(
        tmp_path=tmp_path,
        source_dirs=["app"],
        test_dir="spec",
        test_suffixes=[".js", ".py"],
        files={
            "app/main.py": '"""Main."""\n',
            "spec/test_main.js": "",
            "spec/test_main.py": "",
            "spec/other.txt": "",
        },
    )
    settings = {"source_dirs": ["app"], "test_dir": "spec", "test_suffixes": [".js", ".py"]}
    out = plan.repo_summary(tmp, settings=settings)
    assert "spec/test_main.js" in out
    assert "spec/test_main.py" in out
    assert "spec/other.txt" not in out


def test_repo_summary_default_settings_is_config_project(monkeypatch, tmp_path):
    """When settings=None, use config.PROJECT."""
    proj = {"source_dirs": ["mylib"], "test_dir": "mytests", "test_suffixes": [".py"]}
    monkeypatch.setattr(config, "PROJECT", proj)
    (tmp_path / "mylib").mkdir()
    (tmp_path / "mytests").mkdir()
    (tmp_path / "mylib" / "a.py").write_text('"""A."""\ndef foo():\n    pass\n', encoding="utf-8")
    (tmp_path / "mytests" / "test_a.py").write_text("", encoding="utf-8")
    out = plan.repo_summary(tmp_path)
    assert "mylib/a.py - A." in out
    assert "mytests/test_a.py" in out


def test_repo_summary_stratos_defaults_unchanged(tmp_path):
    """With Stratos defaults (source_dirs=["stratos"], test_dir="tests", test_suffixes=[".py"]),
    the output matches the old behaviour."""
    tmp = make_project(
        tmp_path=tmp_path,
        source_dirs=["stratos"],
        test_dir="tests",
        test_suffixes=[".py"],
        files={
            "stratos/foo.py": '"""Foo module."""\ndef bar(x):\n    pass\nclass Baz:\n    pass\n',
            "tests/test_foo.py": "",
        },
    )
    settings = {"source_dirs": ["stratos"], "test_dir": "tests", "test_suffixes": [".py"]}
    out = plan.repo_summary(tmp, settings=settings)
    assert "stratos/foo.py - Foo module." in out
    assert "  def bar(x)" in out
    assert "  class Baz" in out
    assert "tests/test_foo.py" in out


def test_parse_plan_accepts_test_dir_prefix(tmp_path, monkeypatch):
    """parse_plan validates tests against config.PROJECT test_dir prefix."""
    proj = {"source_dirs": ["stratos"], "test_dir": "mytests", "test_suffixes": [".py"]}
    monkeypatch.setattr(config, "PROJECT", proj)
    tasks = [{"key": "T1", "title": "x", "goal": "g",
             "files": ["src/a.py"], "tests": ["mytests/test_a.py"],
             "protected": [], "after": [], "role": "coder"}]
    text = json.dumps({"tasks": tasks})
    result = plan.parse_plan(text)
    assert result[0]["tests"] == ["mytests/test_a.py"]


def test_parse_plan_rejects_wrong_test_dir(tmp_path, monkeypatch):
    """Tests not starting with test_dir + '/' are rejected."""
    proj = {"source_dirs": ["stratos"], "test_dir": "mytests", "test_suffixes": [".py"]}
    monkeypatch.setattr(config, "PROJECT", proj)
    tasks = [{"key": "T1", "title": "x", "goal": "g",
             "files": ["src/a.py"], "tests": ["tests/test_a.py"],
             "protected": [], "after": [], "role": "coder"}]
    text = json.dumps({"tasks": tasks})
    with pytest.raises(plan.PlanError):
        plan.parse_plan(text)


def test_parse_plan_accepts_js_test_suffix(tmp_path, monkeypatch):
    """parse_plan accepts tests ending with .js when .js is in test_suffixes."""
    proj = {"source_dirs": ["app"], "test_dir": "spec", "test_suffixes": [".js", ".py"]}
    monkeypatch.setattr(config, "PROJECT", proj)
    tasks = [{"key": "T1", "title": "x", "goal": "g",
             "files": ["app/a.py"], "tests": ["spec/test_a.js"],
             "protected": [], "after": [], "role": "coder"}]
    text = json.dumps({"tasks": tasks})
    result = plan.parse_plan(text)
    assert result[0]["tests"] == ["spec/test_a.js"]


def test_parse_plan_rejects_unknown_suffix(tmp_path, monkeypatch):
    """Tests with a suffix not in test_suffixes are rejected."""
    proj = {"source_dirs": ["app"], "test_dir": "spec", "test_suffixes": [".py"]}
    monkeypatch.setattr(config, "PROJECT", proj)
    tasks = [{"key": "T1", "title": "x", "goal": "g",
             "files": ["app/a.py"], "tests": ["spec/test_a.js"],
             "protected": [], "after": [], "role": "coder"}]
    text = json.dumps({"tasks": tasks})
    with pytest.raises(plan.PlanError):
        plan.parse_plan(text)


def test_parse_plan_stratos_defaults_same_as_before():
    """With Stratos defaults the rule is tests/ + .py, same as the existing tests."""
    tasks = [{"key": "T1", "title": "x", "goal": "g",
             "files": ["stratos/a.py"], "tests": ["tests/test_a.py"],
             "protected": [], "after": [], "role": "coder"}]
    text = json.dumps({"tasks": tasks})
    result = plan.parse_plan(text)
    assert result[0]["tests"] == ["tests/test_a.py"]
