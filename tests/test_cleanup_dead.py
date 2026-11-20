"""Tests for task cleanup_dead (P13, 2026-11-20, user: "clean out unused functions and features"). Found by Claude:
gitops.append_to_commit_message and plan.check_new_tests were called only by their own tests (T021 and P010 replaced
them with finalize_commit_message and fix_new_tests), config.ATTEMPT_PLAN was read by nothing since tasks have
roles, and the model draft checker (draftcheck.py, config.DRAFT_CHECK / DRAFT_CHECKER) has been off by default
since P7, when the reference check (refcheck) replaced it. All of them go, with their tests."""

import inspect

from stratos import config, gitops, plan, plantests


def test_gone():
    assert not hasattr(gitops, "append_to_commit_message")
    assert not hasattr(plan, "check_new_tests")
    for name in ("ATTEMPT_PLAN", "DRAFT_CHECK", "DRAFT_CHECKER"):
        assert not hasattr(config, name), name
    # (stratos/draftcheck.py itself is deleted by Claude after the merge: tasks cannot delete files)
    assert "draftcheck" not in inspect.getsource(plantests)


def test_what_replaced_them_stays():
    assert hasattr(gitops, "finalize_commit_message") and hasattr(plan, "fix_new_tests")
    assert "coder" in config.ATTEMPT_PLANS and config.REF_CHECK in (True, False)
