"""Tests for task T030: the coder system prompt is the fixed start of every coding request (its wording is part of the
contract, and PolyStrata reuses its cached computation). T029's coder changed its last line unasked; it must read:"""
from stratos import context

LAST_LINE = "- Keep the code plain and correct; the task's tests decide whether you succeeded."


def test_last_line_of_the_system_prompt():
    assert context.CODER_SYSTEM.splitlines()[-1] == LAST_LINE


def test_rules_are_all_there():
    for rule in ("- You have no tools and cannot open files", "- A whole file must be complete, never a fragment.",
                 "- Do not change files marked READ-ONLY.", "- Use only the Python standard library"):
        assert rule in context.CODER_SYSTEM
