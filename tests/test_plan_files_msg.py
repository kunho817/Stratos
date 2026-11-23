"""Tests for task t19_files_msg: in stratos/plan.py, the validation that produces
"Task <key>: files must be a non-empty list of strings." changes to
"Task <key>: files must be a non-empty list of strings - every task writes at least
one source file; put work that only writes tests into the task that writes the code
it tests." This message is sent back to the planner as a retry prompt.

The new message replaces the old one in both the isinstance/len check and the
all(isinstance) check for files. The message is embedded in the retry user turn
by cmd_plan as f"Your plan was invalid: {e}. Answer with the corrected JSON plan only."
"""

import json

import pytest

from stratos import __main__ as cli
from stratos import config, plan
from stratos.telemetry import Telemetry

GOOD = {"tasks": [
    {"key": "a", "title": "Add f", "goal": "Add f to x.", "files": ["stratos/x.py"],
     "tests": ["tests/test_x.py"]},
    {"key": "b", "title": "Use f", "goal": "Call f in y.", "files": ["stratos/y.py"],
     "tests": ["tests/test_y.py"], "after": ["a"], "role": "coder"},
]}

NEW_MSG_SUFFIX = (
    " - every task writes at least one source file; "
    "put work that only writes tests into the task that writes the code it tests."
)


def _plan(text):
    """Shorthand: parse_plan on a JSON string."""
    return plan.parse_plan(json.dumps(text)) if isinstance(text, dict) else plan.parse_plan(text)


def _bad_plan(files_value):
    """Return a plan dict with task "a" having the given files value."""
    return {"tasks": [{"key": "a", "title": "T", "goal": "g",
                       "files": files_value, "tests": ["tests/test_a.py"]}]}


# ---------------------------------------------------------------------------
# 1. Empty files list gives the new message.
# ---------------------------------------------------------------------------

def test_empty_files_gives_the_new_message():
    """files=[] raises PlanError with the new full message."""
    with pytest.raises(plan.PlanError) as e:
        _plan(_bad_plan([]))
    # expected: the message is exactly:
    # "Task a: files must be a non-empty list of strings - every task writes at least
    #  one source file; put work that only writes tests into the task that writes the code it tests."
    expected = "Task a: files must be a non-empty list of strings" + NEW_MSG_SUFFIX
    assert str(e.value) == expected
    # expected: the old message is NOT the full text
    assert str(e.value) != "Task a: files must be a non-empty list of strings."


# ---------------------------------------------------------------------------
# 2. files is not a list (e.g. a string) gives the new message.
# ---------------------------------------------------------------------------

def test_non_list_files_gives_the_new_message():
    """files="x.py" (a string, not a list) raises PlanError with the new message."""
    with pytest.raises(plan.PlanError) as e:
        _plan(_bad_plan("x.py"))
    # expected: the same new message as for an empty list
    expected = "Task a: files must be a non-empty list of strings" + NEW_MSG_SUFFIX
    assert str(e.value) == expected


# ---------------------------------------------------------------------------
# 3. files contains a non-string item gives the new message.
# ---------------------------------------------------------------------------

def test_files_with_non_strings_gives_the_new_message():
    """files=["a.py", 1] raises PlanError with the new message."""
    with pytest.raises(plan.PlanError) as e:
        _plan(_bad_plan(["a.py", 1]))
    # expected: the same new message
    expected = "Task a: files must be a non-empty list of strings" + NEW_MSG_SUFFIX
    assert str(e.value) == expected


# ---------------------------------------------------------------------------
# 4. The key appears in the message.
# ---------------------------------------------------------------------------

def test_key_is_in_the_message():
    """A task named "zz" has its key in the message."""
    bad = {"tasks": [{"key": "zz", "title": "T", "goal": "g",
                      "files": [], "tests": ["tests/test_zz.py"]}]}
    with pytest.raises(plan.PlanError) as e:
        _plan(bad)
    # expected: "Task zz:" is at the start
    assert str(e.value).startswith("Task zz:")


# ---------------------------------------------------------------------------
# 5. The message names the source-file rule.
# ---------------------------------------------------------------------------

def test_message_mentions_source_file_rule():
    """The message says every task writes at least one source file."""
    with pytest.raises(plan.PlanError) as e:
        _plan(_bad_plan([]))
    # expected: the phrase "every task writes at least one source file" is present
    assert "every task writes at least one source file" in str(e.value)


# ---------------------------------------------------------------------------
# 6. The message tells the planner to put tests-only work into the code task.
# ---------------------------------------------------------------------------

def test_message_mentions_put_work():
    """The message says put work that only writes tests into the task that writes the code it tests."""
    with pytest.raises(plan.PlanError) as e:
        _plan(_bad_plan([]))
    # expected: the phrase "put work that only writes tests" is present
    assert "put work that only writes tests" in str(e.value)
    # expected: the phrase "the task that writes the code it tests" is present
    assert "the task that writes the code it tests" in str(e.value)


# ---------------------------------------------------------------------------
# 7. The message keeps the original prefix before the new explanation.
# ---------------------------------------------------------------------------

def test_message_keeps_original_prefix():
    """The new message starts with "Task <key>: files must be a non-empty list of strings"."""
    with pytest.raises(plan.PlanError) as e:
        _plan(_bad_plan([]))
    # expected: the prefix is "Task a: files must be a non-empty list of strings"
    assert str(e.value).startswith("Task a: files must be a non-empty list of strings")
    # expected: a separator " - " follows the prefix
    assert str(e.value)[len("Task a: files must be a non-empty list of strings")] == " -"


# ---------------------------------------------------------------------------
# 8. Both validation paths (non-list and non-string items) produce the same text.
# ---------------------------------------------------------------------------

def test_same_message_for_non_list_and_non_strings():
    """files="x" and files=["x", 1] give the exact same error text."""
    msg1 = _plan(_bad_plan("x"))
    # not reached; use raises
    try:
        _plan(_bad_plan("x"))
    except plan.PlanError as e1:
        msg1 = str(e1)
    try:
        _plan(_bad_plan(["x", 1]))
    except plan.PlanError as e2:
        msg2 = str(e2)
    # expected: both messages are identical
    assert msg1 == msg2


# ---------------------------------------------------------------------------
# 9. The retry prompt sent back to the planner contains the new message.
# ---------------------------------------------------------------------------

@pytest.fixture
def env(tmp_path, monkeypatch):
    """Set up config paths and a fake gateway so cmd_plan runs offline."""
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(plan, "repo_summary", lambda root: "SUMMARY")
    made = []

    class FakeGateway:
        answers = []

        def __init__(self, telemetry):
            self.telemetry = telemetry
            made.append(self)

        def ensure_model(self, model):
            return 0.0

        def chat(self, messages, **kw):
            self.calls.append((list(messages), kw))
            return f"c{len(self.calls)}", FakeGateway.answers.pop(0)
    FakeGateway.calls = []
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    goal = tmp_path / "goal.txt"
    goal.write_text("Make it fly.", encoding="utf-8")
    return FakeGateway, made, goal


def test_retry_prompt_contains_the_new_message(env, capsys):
    """When files=[] is the first answer, the retry user turn embeds the new message."""
    gw_cls, made, goal = env
    # first answer: files=[] → PlanError with the new message; second answer: valid
    bad = json.dumps({"tasks": [{"key": "a", "title": "T", "goal": "g",
                                 "files": [], "tests": ["tests/test_a.py"]}]})
    good = json.dumps(GOOD)
    gw_cls.answers = [bad, good]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    # expected: the second chat call's user turn contains the new message
    second_messages = made[0].calls[1][0]
    # the user turn is the 4th message (index 3):
    # messages[3] = {"role": "user", "content": "Your plan was invalid: <new message>. Answer with ..."}
    user_turn = second_messages[3]["content"]
    # expected: the user turn starts with "Your plan was invalid: "
    assert user_turn.startswith("Your plan was invalid: ")
    # expected: the new message (the key part) is inside the user turn
    assert "every task writes at least one source file" in user_turn
    assert "the task that writes the code it tests" in user_turn
    # expected: ends with ". Answer with the corrected JSON plan only."
    assert user_turn.endswith(". Answer with the corrected JSON plan only.")


# ---------------------------------------------------------------------------
# 10. The message for a task with key "b" names "b" in the retry prompt.
# ---------------------------------------------------------------------------

def test_retry_prompt_names_the_task_key(env):
    """When task b has files=[], the retry prompt names key b."""
    gw_cls, made, goal = env
    bad = json.dumps({"tasks": [{"key": "b", "title": "B", "goal": "g",
                                 "files": [], "tests": ["tests/test_b.py"]}]})
    good = json.dumps({"tasks": [{"key": "c", "title": "C", "goal": "g",
                                   "files": ["stratos/c.py"], "tests": ["tests/test_c.py"]}]})
    gw_cls.answers = [bad, good]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    user_turn = made[0].calls[1][0][3]["content"]
    # expected: the key "b" is in the retry message
    assert "Task b:" in user_turn


# ---------------------------------------------------------------------------
# 11. A valid plan is unaffected: the message is not raised for good tasks.
# ---------------------------------------------------------------------------

def test_valid_plan_is_not_affected():
    """A plan with non-empty files list of strings passes; the new message is absent."""
    tasks = _plan(GOOD)
    # expected: two tasks returned
    assert len(tasks) == 2
    # expected: task a's files is ["stratos/x.py"]
    assert tasks[0]["files"] == ["stratos/x.py"]
    # expected: task b's files is ["stratos/y.py"]
    assert tasks[1]["files"] == ["stratos/y.py"]
