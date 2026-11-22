"""Tests for task plan-test-paths: build_messages states test-file paths from config.PROJECT.

In stratos/plan.py, build_messages(goal, summary, conventions=None, system=None, uses=None, memory=None)
adds the line
    "TEST FILES: every test file path starts with <test_dir>/ and ends with <suffix>."
to the user content, where test_dir = config.PROJECT["test_dir"] and
suffix = config.PROJECT["test_suffixes"][0].
When config.PROJECT is absent (None, missing attribute, or dict without the keys), the line is skipped.
The line sits right after "PROJECT FILES:\\n{summary}" and before the rest of the parts.
"""

import pytest

from stratos import config, plan


PROJ = {"test_dir": "tests", "test_suffixes": [".py", ".test.js"]}
LINE = "TEST FILES: every test file path starts with tests/ and ends with .py."


def test_line_present_with_project(tmp_path, monkeypatch):
    """config.PROJECT present → the TEST FILES line appears in the user content."""
    monkeypatch.setattr(config, "PROJECT", PROJ)
    user = plan.build_messages("Goal.", "Summary.")[1]["content"]
    # Step: the line is in the user content.
    assert LINE in user
    # Step: it comes after PROJECT FILES.
    assert user.index("PROJECT FILES:\nSummary.") < user.index(LINE)
    # Step: it comes before FEATURE GOAL.
    assert user.index(LINE) < user.index("FEATURE GOAL:\nGoal.")


def test_line_absent_when_project_none(tmp_path, monkeypatch):
    """config.PROJECT = None → the line is skipped."""
    monkeypatch.setattr(config, "PROJECT", None)
    user = plan.build_messages("Goal.", "Summary.")[1]["content"]
    # Step: no TEST FILES text.
    assert "TEST FILES:" not in user
    # Step: the rest is the original two-part content.
    assert user == "PROJECT FILES:\nSummary.\n\nFEATURE GOAL:\nGoal."


def test_line_absent_when_project_attribute_missing(tmp_path, monkeypatch):
    """config.PROJECT attribute absent → the line is skipped."""
    monkeypatch.delattr(config, "PROJECT", raising=False)
    user = plan.build_messages("Goal.", "Summary.")[1]["content"]
    # Step: no TEST FILES text.
    assert "TEST FILES:" not in user


def test_line_absent_when_project_lacks_keys(tmp_path, monkeypatch):
    """config.PROJECT is a dict without test_dir/test_suffixes → the line is skipped."""
    monkeypatch.setattr(config, "PROJECT", {"source_dirs": ["stratos"]})
    user = plan.build_messages("Goal.", "Summary.")[1]["content"]
    # Step: no TEST FILES text.
    assert "TEST FILES:" not in user


def test_line_absent_when_project_has_empty_suffixes(tmp_path, monkeypatch):
    """test_suffixes is an empty list → the line is skipped."""
    proj = {"test_dir": "tests", "test_suffixes": []}
    monkeypatch.setattr(config, "PROJECT", proj)
    user = plan.build_messages("G", "S")[1]["content"]
    # Step: no TEST FILES text.
    assert "TEST FILES:" not in user


def test_line_uses_first_suffix_only(tmp_path, monkeypatch):
    """Only test_suffixes[0] appears; the second suffix is not in the line."""
    proj = {"test_dir": "src/tests", "test_suffixes": [".test.js", ".py"]}
    monkeypatch.setattr(config, "PROJECT", proj)
    user = plan.build_messages("G", "S")[1]["content"]
    # Step: suffix is ".test.js" (first entry).
    expected = "TEST FILES: every test file path starts with src/tests/ and ends with .test.js."
    assert expected in user
    # Step: the second suffix ".py" does not appear in the TEST FILES line.
    line = [l for l in user.splitlines() if l.startswith("TEST FILES:")]
    assert len(line) == 1
    assert ".py" not in line[0]


def test_line_position_after_project_files(tmp_path, monkeypatch):
    """The TEST FILES line sits immediately after PROJECT FILES, separated by \\n\\n."""
    monkeypatch.setattr(config, "PROJECT", PROJ)
    user = plan.build_messages("G", "S")[1]["content"]
    # Step: the exact sequence is "PROJECT FILES:\nS\n\n" + LINE + "\n\nFEATURE GOAL:\nG".
    assert user == "PROJECT FILES:\nS\n\n" + LINE + "\n\nFEATURE GOAL:\nG"


def test_line_before_conventions(tmp_path, monkeypatch):
    """TEST FILES line comes before PROJECT CONVENTIONS."""
    monkeypatch.setattr(config, "PROJECT", PROJ)
    user = plan.build_messages("G", "S", conventions="Rules.")[1]["content"]
    # Step: order is PROJECT FILES → TEST FILES → CONVENTIONS → FEATURE GOAL.
    assert user.index("PROJECT FILES:\nS") < user.index(LINE) < user.index("PROJECT CONVENTIONS:\nRules.")
    # Step: full string check.
    assert user == "PROJECT FILES:\nS\n\n" + LINE + "\n\nPROJECT CONVENTIONS:\nRules.\n\nFEATURE GOAL:\nG"


def test_line_before_uses(tmp_path, monkeypatch):
    """TEST FILES line comes before the WHO USES WHAT part."""
    monkeypatch.setattr(config, "PROJECT", PROJ)
    uses_head = "WHO USES WHAT (when a task changes a name, every user listed here must be changed or checked too):\n"
    user = plan.build_messages("G", "S", uses="X (a.py): b")[1]["content"]
    # Step: order is PROJECT FILES → TEST FILES → USES → FEATURE GOAL.
    assert user.index(LINE) < user.index(uses_head)
    # Step: full string check.
    assert user == "PROJECT FILES:\nS\n\n" + LINE + "\n\n" + uses_head + "X (a.py): b\n\nFEATURE GOAL:\nG"


def test_line_before_memory(tmp_path, monkeypatch):
    """TEST FILES line comes before the MEMORY part."""
    monkeypatch.setattr(config, "PROJECT", PROJ)
    mem_head = "MEMORY (found for this goal in the project's code, tests, past tasks and people's corrections):\n"
    user = plan.build_messages("G", "S", memory="PACK")[1]["content"]
    # Step: order is PROJECT FILES → TEST FILES → MEMORY → FEATURE GOAL.
    assert user.index(LINE) < user.index(mem_head)
    # Step: full string check.
    assert user == "PROJECT FILES:\nS\n\n" + LINE + "\n\n" + mem_head + "PACK\n\nFEATURE GOAL:\nG"


def test_all_parts_in_order(tmp_path, monkeypatch):
    """When uses, memory, conventions are all present, the order is:
    PROJECT FILES → TEST FILES → USES → MEMORY → CONVENTIONS → FEATURE GOAL."""
    monkeypatch.setattr(config, "PROJECT", PROJ)
    uses_head = "WHO USES WHAT (when a task changes a name, every user listed here must be changed or checked too):\n"
    mem_head = "MEMORY (found for this goal in the project's code, tests, past tasks and people's corrections):\n"
    user = plan.build_messages("G", "S", conventions="C", uses="U", memory="M")[1]["content"]
    # Step: every index is in the right order.
    i_proj = user.index("PROJECT FILES:\nS")
    i_line = user.index(LINE)
    i_uses = user.index(uses_head)
    i_mem = user.index(mem_head)
    i_conv = user.index("PROJECT CONVENTIONS:\nC")
    i_goal = user.index("FEATURE GOAL:\nG")
    # Step: the full chain.
    assert i_proj < i_line < i_uses < i_mem < i_conv < i_goal


def test_no_project_leaves_content_unchanged(tmp_path, monkeypatch):
    """config.PROJECT = None: content is byte-for-byte identical to the version without
    the feature (no TEST FILES line, no extra blank line)."""
    monkeypatch.setattr(config, "PROJECT", None)
    user = plan.build_messages("G", "S", uses="U")[1]["content"]
    uses_head = "WHO USES WHAT (when a task changes a name, every user listed here must be changed or checked too):\n"
    # Step: exactly as before (PROJECT FILES → USES → FEATURE GOAL).
    assert user == "PROJECT FILES:\nS\n\n" + uses_head + "U\n\nFEATURE GOAL:\nG"
