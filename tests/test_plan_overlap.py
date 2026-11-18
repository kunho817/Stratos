"""Tests for task T065: plan.parse_plan refuses a task that lists the same path in "files" and "protected".

The second real plan (P002) gave a task its own file as read-only too. A file the task writes cannot also be
read-only, so parse_plan raises PlanError, naming the task's key and the path."""
import json

import pytest

from stratos import plan


def test_overlap_is_refused():
    bad = {"tasks": [{"key": "draft", "title": "t", "goal": "g", "files": ["stratos/a.py", "stratos/b.py"],
                      "tests": ["tests/test_a.py"], "protected": ["stratos/c.py", "stratos/b.py"]}]}
    with pytest.raises(plan.PlanError) as e:
        plan.parse_plan(json.dumps(bad))
    assert "draft" in str(e.value) and "stratos/b.py" in str(e.value)


def test_no_overlap_is_fine():
    ok = {"tasks": [{"key": "k", "title": "t", "goal": "g", "files": ["stratos/a.py"], "tests": ["tests/test_a.py"],
                     "protected": ["stratos/c.py"]}]}
    assert plan.parse_plan(json.dumps(ok))[0]["protected"] == ["stratos/c.py"]
