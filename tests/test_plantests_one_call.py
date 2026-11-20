"""Tests for task plantests_one_call (P11 cleanup, 2026-11-20, found by Claude reading T208): T208 copied the whole
test-writer call (messages, kwargs, gw.chat, the answer file, the header-less fallbacks - 25 lines) into the cases
branch, so draft_tests asked the model in two places.

plantests._ask_test_writer(gw, plan_id, task, messages, model_cfg, answers_dir, root) -> files: the model call and
the reading of its answer as they were (kwargs with reasoning_budget when set, the answer saved as
f"{plan_id}-{task['key']}-tests.md", patch.parse_files with allowed=task["tests"], the header-less fallbacks for a
single new test file). draft_tests calls it (once, or once per branch) - for tasks without cases and for tasks whose cases are
not all plain calls (with the CASES part added to the messages first). Behaviour is unchanged."""
import inspect

from stratos import plantests


def test_one_model_call():
    assert inspect.getsource(plantests.draft_tests).count("gw.chat(") == 0
    # (Claude: at most 2 - one per branch is fine; the 25 copied lines were the problem, not two short calls)
    assert 1 <= inspect.getsource(plantests.draft_tests).count("_ask_test_writer(") <= 2
    assert inspect.getsource(plantests._ask_test_writer).count("gw.chat(") == 1
