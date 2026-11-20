"""Tests for task retry_not_kept (P8, 2026-11-20, found in T192): with edit blocks, a failed attempt is thrown away and
the next one starts from the files as they were - but the model thought its edits had stayed and sent only the fix
(an import), so the tests failed the same way. The retry message says so.

context.build_messages(task, root, failure=...): the failure part is
"YOUR PREVIOUS ATTEMPT FAILED and was not kept: the files above are as they were before it, so send every change "
"again. Test output:\n```\n" + failure + "\n```\nFix it."
(it still starts with "YOUR PREVIOUS ATTEMPT FAILED", which tests/test_loop_memory.py reads)."""
from stratos import context

TASK = {"id": "T1", "title": "t", "goal": "g", "files": [], "protected": []}


def test_retry_message_says_the_attempt_was_not_kept():
    user = context.build_messages(TASK, ".", failure="F boom")[-1]["content"]
    assert user.endswith("YOUR PREVIOUS ATTEMPT FAILED and was not kept: the files above are as they were before it, "
                         "so send every change again. Test output:\n```\nF boom\n```\nFix it.")
