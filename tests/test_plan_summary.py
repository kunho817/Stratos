"""Tests for task T064: plan.repo_summary also lists each stratos module's public functions and classes.

The second real plan (P002) invented APIs (load_plan in state.py, gw.ask) because the planner only saw each module's
first docstring line. Now, right after a module's line, repo_summary adds one line per top-level public definition,
in file order: "  def <name>(<ast.unparse(node.args)>)" for a function (async ones too), "  class <name>" for a
class. Names starting with "_" are left out. Test files are still listed by name only."""
from stratos import plan

SOURCE = '''"""Mod docstring."""
import os

X = 1


def load(state_dir, pid, *, strict=False):
    return 1


def _private(a):
    return a


class Store:
    def method(self):
        pass


async def fetch(url, timeout=10):
    return url
'''


def test_signatures_follow_the_module_line(tmp_path):
    (tmp_path / "stratos").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "stratos" / "m.py").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "stratos" / "a.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_m.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    assert plan.repo_summary(tmp_path) == "\n".join([
        "stratos/a.py",
        "stratos/m.py - Mod docstring.",
        "  def load(state_dir, pid, *, strict=False)",
        "  class Store",
        "  def fetch(url, timeout=10)",
        "tests/test_m.py",
    ])


def test_a_file_that_does_not_parse_is_listed_alone(tmp_path):
    (tmp_path / "stratos").mkdir()
    (tmp_path / "stratos" / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    assert plan.repo_summary(tmp_path) == "stratos/bad.py"


def test_the_real_project_shows_real_apis():
    from stratos import config
    s = plan.repo_summary(config.REPO)
    assert "  def load_plan(state_dir, pid)" in s
    assert "  class Gateway" in s
    assert "  def chat(" not in s              # methods are not top-level definitions
