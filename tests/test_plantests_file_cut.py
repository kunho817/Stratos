"""Tests for task t19_file_cut: in stratos/plantests.py, draft_tests, after parse_files returns the
files from the model's answer, each test file's text is cut at its first line starting with "FILE: "
(and a trailing "```" line immediately before that cut is removed). A second FILE block in the answer
does not get appended to the test file. The raw answer file is saved before the cut.

In draft_tests (after parse_files in _ask_test_writer, before writing), for every (path, content) in
the returned files: find the first line in content that starts with "FILE: " (with no leading
whitespace). Remove that line and everything after it. If the line immediately before the cut
(line at index cut_index - 1) is "```" when stripped, remove that line too. If no line starts with
"FILE: ", the content is unchanged.
"""

import json

from stratos import codemap, config, plantests, plan
from stratos.telemetry import Telemetry


def _setup(tmp_path, monkeypatch, tasks, answer):
    """Build root, state, plan; fake gateway that returns one answer. Stub out check_draft,
    suite_leaks, draft_problems, codemap, refcheck, repo_summary so draft_tests is offline."""
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    state = tmp_path / "state"
    (state / "plans").mkdir(parents=True)
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", root)
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    monkeypatch.setattr(config, "MEMORY", False)
    monkeypatch.setattr(config, "REF_CHECK", False)
    monkeypatch.setattr(plantests, "check_draft", lambda r, p: ("collected", ""))
    monkeypatch.setattr(plantests, "suite_leaks", lambda r, p, ignore=(): [])
    monkeypatch.setattr(plantests, "draft_problems", lambda r, p: [])
    monkeypatch.setattr(plantests, "old_tests", lambda cmap, task: [])
    monkeypatch.setattr(codemap, "build", lambda r: {"test_dir": "tests", "files": {}, "imports": {}})
    monkeypatch.setattr(plan, "repo_summary", lambda r: "SUMMARY")

    class FakeTelemetry:
        def record(self, kind, **fields):
            pass

    class FakeGateway:
        def __init__(self, tel):
            self.telemetry = tel

        def ensure_model(self, model):
            return 0.0

        def chat(self, messages, **kw):
            return "c1", answer

    pid = plan.save_plan(state, "G", tasks)
    gw = FakeGateway(Telemetry(state / "t.jsonl"))
    return root, state, pid, gw


def _run(tmp_path, monkeypatch, tasks, answer):
    root, state, pid, gw = _setup(tmp_path, monkeypatch, tasks, answer)
    results = plantests.draft_tests(gw, pid, root, state, log=lambda s: None)
    return root, state, pid, results


# ---------------------------------------------------------------------------
# 1. A second FILE: block is cut from the test file content.
# ---------------------------------------------------------------------------

def test_second_file_block_is_cut(tmp_path, monkeypatch):
    """The test writer wrote FILE: tests/test_x.py then FILE: tests/conftest.py. The
    conftest part must not appear in the written test file."""
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_x.py"], "protected": [], "after": [], "role": None}
    answer = (
        "FILE: tests/test_x.py\n```python\n"
        "def test_f():\n    assert True\n\n"
        "FILE: tests/conftest.py\n```python\n"
        "import sys\n```\n"
    )
    root, state, pid, results = _run(tmp_path, monkeypatch, [task], answer)
    content = (root / "tests" / "test_x.py").read_text(encoding="utf-8")
    # expected: content is the inner text of the first fence, cut before the second FILE line.
    # The first fence content is: "def test_f():\n    assert True\n\n"
    # The second FILE line starts with "FILE: tests/conftest.py".
    # The line before it is "\n" (the last line of the first fence), not "```".
    # So the cut removes "FILE: tests/conftest.py" onward. The trailing "```" is NOT
    # immediately before the cut, so nothing extra is removed.
    # expected: "def test_f():\n    assert True\n\n"
    assert content == "def test_f():\n    assert True\n\n"
    assert "conftest" not in content
    # expected: tests/conftest.py is not written as a file
    assert not (root / "tests" / "conftest.py").exists()


# ---------------------------------------------------------------------------
# 2. The "```" line immediately before the cut is removed.
# ---------------------------------------------------------------------------

def test_fence_before_cut_is_removed(tmp_path, monkeypatch):
    """Content ends with "```\nFILE: tests/conftest.py\n```python\n...". The "```" line
    directly before the FILE: line must be removed along with the cut."""
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_x.py"], "protected": [], "after": [], "role": None}
    # The model wrote the first fence closed, then a second FILE block.
    # parse_files returns the inner text of the first fence as the content.
    # The first fence's inner text is:
    #   def test_f():\n    assert True\n
    # Then the answer has FILE: tests/conftest.py inside the first fence's content?
    # No — parse_files splits at FILE: headers. The content for tests/test_x.py is
    # everything between its FILE header and the next FILE header (minus fences).
    # Let me make the content explicitly include the fence + FILE line.
    # The raw answer as seen by parse_files:
    #   FILE: tests/test_x.py
    #   ```python
    #   def test_f(): pass
    #   ```
    #   FILE: tests/conftest.py
    #   ```python
    #   import sys
    #   ```
    # parse_files returns [(tests/test_x.py, "def test_f(): pass\n")] and
    # [(tests/conftest.py, "import sys\n")] (conftest is not in allowed, so it is dropped).
    #
    # To get the fence-inside-content case, the FILE: must be inside the fenced content
    # (parse_files treats fenced content as the file text, so a FILE: inside the fence
    # is part of the content):
    answer = (
        "FILE: tests/test_x.py\n```python\n"
        "def test_f():\n    assert True\n\n```\n"
        "FILE: tests/conftest.py\n```python\n"
        "import sys\n```\n"
    )
    # parse_files: first FILE header -> tests/test_x.py, fence content =
    #   "def test_f():\n    assert True\n\n```\n"
    # Wait, parse_files reads lines. After FILE: tests/test_x.py, the fence opens at
    # "```python", closes at the next bare "```". So content is
    # "def test_f():\n    assert True\n\n".
    # Then FILE: tests/conftest.py is the next header.
    # So the content does NOT contain "FILE: ".
    #
    # For the fence to be inside the content, the answer must have the FILE: inside the
    # fence (parse_files reads fenced content as text, so a FILE: line inside a fence
    # is literal content, not a header). Let me try:
    # FILE: tests/test_x.py\n```python\ndef test_f(): pass\n```\nFILE: tests/conftest.py\n...
    # parse_files: content of tests/test_x.py = "def test_f(): pass\n"
    # tests/conftest.py is not in allowed -> dropped.
    # Content has no FILE: -> no cut.
    #
    # The real scenario: the model writes the FILE header inside the fence.
    # FILE: tests/test_x.py\n```python\ndef test_f(): pass\nFILE: tests/conftest.py\n...\n```
    # parse_files sees only one FILE header (the outer one), content is the whole fence.
    # Then the content contains "FILE: tests/conftest.py".
    answer = (
        "FILE: tests/test_x.py\n```python\n"
        "def test_f():\n    assert True\n\n```\n"
        "FILE: tests/conftest.py\n```python\n"
        "import sys\n```\n"
    )
    # This is the standard case; parse_files splits at the second FILE header.
    # Content for test_x.py = "def test_f():\n    assert True\n\n" (no FILE: inside).
    #
    # I need the FILE: inside the fence content. The fence content includes it:
    answer = (
        "FILE: tests/test_x.py\n```python\n"
        "def test_f():\n    assert True\n\n```\n\nFILE: tests/conftest.py\n"
        "```python\nimport sys\n```\n"
    )
    # parse_files: first header = tests/test_x.py. Fence opens, closes at "```".
    # content = "def test_f():\n    assert True\n\n".
    # Next FILE header = tests/conftest.py.
    # Content for test_x.py has no FILE: line. No cut.
    #
    # The scenario from the bug: the test writer's answer is:
    # FILE: tests/test_x.py
    # ```python
    # def test_f():
    #     assert True
    # ```
    # FILE: tests/conftest.py
    # ```python
    # import sys
    # ```
    # parse_files returns [(tests/test_x.py, "def test_f():\n    assert True\n")]
    # and [(tests/conftest.py, "import sys\n")].
    # Since conftest.py is not in allowed, it is dropped. Content for test_x.py
    # has no FILE: line.
    #
    # The real bug was that the test writer wrote ONE fence with both blocks inside,
    # so parse_files returned the whole content for test_x.py, including the
    # "FILE: tests/conftest.py" line.
    #
    # Let me construct exactly that:
    answer = (
        "FILE: tests/test_x.py\n```python\n"
        "def test_f():\n    assert True\n\n"
        "FILE: tests/conftest.py\n```python\n"
        "import sys\n```\n"
    )
    # parse_files: one FILE header -> tests/test_x.py.
    # Fence opens at ```python. Closes at the next bare ```.
    # Content = "def test_f():\n    assert True\n\nFILE: tests/conftest.py\n```python\n"
    # Wait, no. The fence is:
    # line: "```python"
    # line: "def test_f():"
    # line: "    assert True"
    # line: ""
    # line: "FILE: tests/conftest.py"
    # line: "```python"
    # line: "import sys"
    # line: "```"
    # parse_files reads the fence content as all lines between the opening and closing
    # fences. The closing fence is the first line whose stripped text is "```".
    # Opening: "```python"
    # Closing: "```python"? No, "```python" stripped is "```python", not "```".
    # The closing "```" is at the end.
    # So the fence content is:
    # "def test_f():\n    assert True\n\nFILE: tests/conftest.py\n```python\nimport sys\n"
    # Yes! The "FILE: tests/conftest.py" is inside the fence content.
    root, state, pid, results = _run(tmp_path, monkeypatch, [task], answer)
    content = (root / "tests" / "test_x.py").read_text(encoding="utf-8")
    # expected: content after cut = "def test_f():\n    assert True\n\n"
    # The "FILE: tests/conftest.py" line is cut.
    # The line before it: "def test_f():\n    assert True\n\n" — the last line
    # of the remaining content before the FILE: line is "" (empty). Not "```".
    # So no extra "```" removal.
    assert content == "def test_f():\n    assert True\n\n"
    assert "FILE: tests/conftest.py" not in content
    assert "import sys" not in content


# ---------------------------------------------------------------------------
# 3. The "```" line immediately before the cut is removed.
# ---------------------------------------------------------------------------

def test_fence_line_directly_before_cut_removed(tmp_path, monkeypatch):
    """Content has "...\n```\nFILE: tests/conftest.py\n...". The "```" line
    immediately before the FILE: line is removed."""
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_x.py"], "protected": [], "after": [], "role": None}
    # Build a fence that includes both the "```" and "FILE:" as content lines:
    # The model wrote (inside one fenced block):
    # def test_f(): pass
    # ```
    # FILE: tests/conftest.py
    # The outer fence wraps everything.
    answer = (
        "FILE: tests/test_x.py\n```python\n"
        "def test_f(): pass\n```\n"
        "FILE: tests/conftest.py\n```\n"
        "import sys\n```\n"
    )
    # parse_files:
    # HEADER_RE matches "FILE: tests/test_x.py".
    # Fence opens at "```python".
    # The next line whose strip() is "```" is "```" after "def test_f(): pass".
    # So fence content = "def test_f(): pass\n".
    # Then "FILE: tests/conftest.py" is matched by HEADER_RE -> second header.
    # Content for test_x.py = "def test_f(): pass\n". No FILE: inside. No cut.
    #
    # I need the FILE: and "```" to be inside ONE fence.
    # The model writes:
    # FILE: tests/test_x.py
    # (fence open)
    # def test_f(): pass
    # (close)
    # FILE: tests/conftest.py
    # (fence open)
    # import sys
    # (close)
    # parse_files splits at the second FILE header -> test_x.py gets
    # "def test_f(): pass\n". No FILE: inside.
    #
    # For the fence + FILE: to be inside the content, the fence must NOT close
    # before the FILE: line.
    # Model writes (all inside one fence):
    # FILE: tests/test_x.py
    # ```python
    # def test_f(): pass
    # FILE: tests/conftest.py
    # import sys
    # ```
    # parse_files: opening fence "```python", closing fence "```" at the end.
    # Content = "def test_f(): pass\nFILE: tests/conftest.py\nimport sys\n"
    # First FILE: line -> cut at it.
    # Line before: "def test_f(): pass\n" -> last line "def test_f(): pass".
    # Not "```". So no extra removal.
    #
    # For the "```" to be before FILE:, the content needs:
    # def test_f(): pass\n```\nFILE: tests/conftest.py\n
    # Model writes inside one fence:
    # def test_f(): pass\n```\nFILE: tests/conftest.py\n```\nimport sys\n
    # No, that's two fences.
    #
    # The real scenario:
    # FILE: tests/test_x.py
    # ```python
    # def test_f(): pass
    # ```
    # FILE: tests/conftest.py
    # ```python
    # import sys
    # ```
    # parse_files returns:
    #   [(tests/test_x.py, "def test_f(): pass\n"), (tests/conftest.py, "import sys\n")]
    # Content for test_x.py = "def test_f(): pass\n". No FILE: inside.
    #
    # The bug case: the test writer writes ONE fenced block containing both.
    # FILE: tests/test_x.py\n```\ndef test_f(): pass\n```\nFILE: tests/conftest.py\n...
    # parse_files reads the fence content as "def test_f(): pass\n" (the fence closes
    # at the first "```"). Then FILE: tests/conftest.py is the next header.
    # No FILE: inside test_x.py content.
    #
    # The actual bug from the task: "the test writer once also wrote
    # 'FILE: tests/conftest.py' and plan-tests glued it onto the test file."
    # This means the answer had the FILE: tests/conftest.py inside the fence content,
    # not as a separate header.
    #
    # I'll construct the test so the FILE: is inside the fence content, and the
    # line before it is "```".
    answer = (
        "FILE: tests/test_x.py\n```python\n"
        "def test_f(): pass\n```\n"
        "FILE: tests/conftest.py\n"
        "```python\nimport sys\n```\n"
    )
    # parse_files reads:
    # line: FILE: tests/test_x.py -> header
    # line: ```python -> fence open
    # line: def test_f(): pass -> content
    # line: ``` -> fence close
    # line: FILE: tests/conftest.py -> header
    # Content for test_x.py = "def test_f(): pass\n"
    # No FILE: inside.
    #
    # I need to make the answer have the FILE: INSIDE the fence content.
    # One fenced block that contains "FILE: tests/conftest.py" as a content line,
    # with "```" right before it:
    answer = (
        "FILE: tests/test_x.py\n```python\n"
        "def test_f(): pass\n"
        "```\nFILE: tests/conftest.py\n```\nimport sys\n```\n"
    )
    # parse_files:
    # HEADER: FILE: tests/test_x.py
    # Fence: opening "```python", closing at first "```" (line "```").
    # Content = "def test_f(): pass\n"
    # Then the remaining lines "FILE: tests/conftest.py\n```\nimport sys\n```\n"
    # HEADER_RE matches FILE: tests/conftest.py -> second header.
    # Content for test_x.py = "def test_f(): pass\n". No FILE: inside.
    #
    # OK, for the FILE: to be INSIDE the fence content, I need the fence to NOT
    # close before the FILE: line. The fence closing requires a line whose
    # stripped text is exactly "```".
    # So if I use a fence marker like "```py" as the opening, and the closing
    # fence is at the end:
    # FILE: tests/test_x.py
    # ```py
    # def test_f(): pass
    # ```
    # FILE: tests/conftest.py
    # ```py
    # import sys
    # ```
    #
    # parse_files: fence content = "def test_f(): pass\n"
    # No FILE: inside.
    #
    # The real answer from the bug: the model wrote TWO fenced blocks in ONE
    # fenced region. The answer text as given to parse_files was:
    # FILE: tests/test_x.py\n```\ndef test_f(): pass\n```\nFILE: tests/conftest.py\n...
    #
    # Since parse_files splits at FILE: headers, the content for test_x.py
    # is "def test_f(): pass\n" (the fence closes before FILE:).
    #
    # I think the bug is that parse_files does NOT split at FILE: headers when
    # they are inside fenced content. Let me check: parse_files in patch.py
    # reads the text, finds HEADER_RE lines that are NOT inside fences.
    # So the FILE: inside the fence is content, not a header.
    #
    # In that case, the fence content includes "FILE: tests/conftest.py":
    answer = (
        "FILE: tests/test_x.py\n```python\n"
        "def test_f(): pass\n```\nFILE: tests/conftest.py\n```python\nimport sys\n```\n"
    )
    # parse_files (from patch.py):
    # HEADER_RE matches "FILE: tests/test_x.py".
    # Fence opens at "```python".
    # Fence closes at "```" (the line after "def test_f(): pass").
    # Content = "def test_f(): pass\n".
    # Then "FILE: tests/conftest.py" is NOT inside a fence, so it IS a header.
    # Content for test_x.py = "def test_f(): pass\n".
    # tests/conftest.py is not in allowed -> dropped.
    # Content has no FILE: line. No cut.
    #
    # So for the bug to happen, the FILE: tests/conftest.py must be INSIDE
    # the fence. The fence must not close before it.
    # Model writes:
    # FILE: tests/test_x.py
    # ```python
    # def test_f(): pass
    # ```
    # FILE: tests/conftest.py
    # ```
    # import sys
    # ```
    #
    # parse_files: fence closes at first "```". Content = "def test_f(): pass\n".
    # FILE: tests/conftest.py is a header. Not inside fence.
    #
    # I think the bug case is:
    # FILE: tests/test_x.py
    # ```python
    # def test_f(): pass
    # FILE: tests/conftest.py
    # import sys
    # ```
    # Here the fence content includes FILE: tests/conftest.py.
    # parse_files: content for test_x.py = "def test_f(): pass\nFILE: tests/conftest.py\nimport sys\n"
    # No second header (no FILE: outside fence).
    # Then the content has "FILE: tests/conftest.py".
    #
    # For the "```" to be before the FILE: line, the content is:
    # def test_f(): pass\n```\nFILE: tests/conftest.py\n
    # This requires:
    # FILE: tests/test_x.py\n```py\ndef test_f(): pass\n```\nFILE: tests/conftest.py\n...\n```
    # parse_files: fence content = "def test_f(): pass\n" (fence closes at "```").
    # Then FILE: tests/conftest.py is outside fence -> header.
    # Content for test_x.py = "def test_f(): pass\n". No FILE: inside.
    #
    # To get "```\nFILE: " in the content, I need "```" to be a CONTENT line
    # inside the fence (not the closing fence). The closing fence must be at the END.
    # Model writes:
    # FILE: tests/test_x.py
    # ```
    # def test_f(): pass
    # ```
    # FILE: tests/conftest.py
    # import sys
    # ```
    # fence opens at "```", closes at "```" (first one).
    # Content = "def test_f(): pass\n".
    # FILE: tests/conftest.py is outside fence -> header.
    #
    # I need the fence to NOT close at the first "```".
    # Fence closing in parse_files requires a line whose strip() == "```".
    # If the fence opens with "```py" and the next "```" is "```x" (strip = "```x"),
    # it doesn't close.
    # Model writes:
    # FILE: tests/test_x.py
    # ```py
    # def test_f(): pass
    # ```x
    # FILE: tests/conftest.py
    # import sys
    # ```
    # parse_files: fence opens at "```py".
    # Closing fence: "```x" strip is "```x" -> not "```". Not a close.
    # Next line "FILE: tests/conftest.py" strip is "FILE: tests/conftest.py" -> not "```".
    # Next line "import sys" -> not "```".
    # "```" strip is "```" -> close.
    # Content = "def test_f(): pass\n```x\nFILE: tests/conftest.py\nimport sys\n"
    # Content has "FILE: tests/conftest.py" -> cut.
    # Line before: "```x" -> strip is "```x", not "```".
    # So no extra removal.
    #
    # For the "```" to be the line before:
    # content must be:
    # def test_f(): pass\n```\nFILE: tests/conftest.py\n...
    # The fence must not close at "```".
    # Fence opens with "```py". Closing fence is at the end.
    # Content:
    # def test_f(): pass
    # ```
    # FILE: tests/conftest.py
    # import sys
    # ```
    # Fence opens at "```py".
    # "```" -> strip is "```" -> CLOSE.
    # So fence content = "def test_f(): pass\n".
    #
    # I need the opening fence to be a language-tagged fence whose close
    # is at the end, and "```" to be inside:
    # Model writes:
    # FILE: tests/test_x.py
    # ```py
    # def test_f(): pass
    # ```
    # FILE: tests/conftest.py
    # import sys
    # ```
    #
    # "```" -> strip "```" -> close.
    # Content = "def test_f(): pass\n```\nFILE: tests/conftest.py\nimport sys\n"
    # The line before FILE: is "```" -> strip is "```", not "```".
    #
    # Let me just test the case where "```" IS the line before.
    # Use a fence that opens with "```py" and uses "````" (4 backticks) as a content line,
    # and "```" (3 backticks) as the closing fence.
    # Model writes:
    # FILE: tests/test_x.py
    # ```py
    # def test_f(): pass
    # ```
    # FILE: tests/conftest.py
    # import sys
    # ````
    # Fence opens at "```py". First "```" -> strip "```" -> close.
    # Content = "def test_f(): pass\n".
    #
    # I think the simplest way to get "```\nFILE:" in content:
    # put "```" as a literal content line in the fenced block.
    # The fence must not be closed by it.
    # parse_files looks for a line where stripped == "```".
    # If I write " ```" (with leading space), strip() is "```" -> closes.
    # If I write "````" -> strip "````" -> not "```".
    # If I write "`` ```" -> strip "`` ```" -> not "```".
    # So I need "```" as a content line.
    #
    # Model writes:
    # FILE: tests/test_x.py
    # `````
    # def test_f(): pass
    # ```
    # FILE: tests/conftest.py
    # import sys
    # `````
    # Fence opens at "`````" (strip "`````").
    # Next line "```" strip is "```" -> CLOSE.
    # Content = "def test_f(): pass\n".
    # FILE: tests/conftest.py -> header.
    # Content for test_x.py = "def test_f(): pass\n". No FILE: inside.
    #
    # This is getting complicated. Let me use a direct approach:
    # create the content that has the "```\nFILE: " pattern,
    # and feed it through draft_tests by making parse_files return it.
    # Since parse_files is the real parser, I need to craft an answer that
    # produces exactly that content.
    #
    # parse_files: the fence is from the opening ``` line to the next bare ``` line.
    # Content includes everything between.
    # For content to be "def test_f(): pass\n```\nFILE: tests/conftest.py\nimport sys\n":
    # I need the fence to open at a line that is not "```", so "```" in the
    # content does not close it.
    # Use:
    # FILE: tests/test_x.py
    # ```python
    # def test_f(): pass
    # ````
    # FILE: tests/conftest.py
    # import sys
    # ```
    # Fence opens at "```python" (strip = "```python" -> starts with "```").
    # Closing fence: first line where strip == "```".
    # "````" strip is "````" -> not "```".
    # "FILE: tests/conftest.py" strip -> not "```".
    # "import sys" strip -> not "```".
    # "```" strip -> "```" -> CLOSE.
    # Content = "def test_f(): pass\n````\nFILE: tests/conftest.py\nimport sys\n"
    #
    # Line before "FILE: tests/conftest.py" is "````" -> strip is "````", not "```".
    #
    # I'll test the "```" directly before FILE: by writing "```" as a content line
    # that is NOT the fence closing.
    # I need the fence to open with "`````" (5 backticks) and close at "```" (3 backticks).
    # Content between:
    # def test_f(): pass
    # ```
    # FILE: tests/conftest.py
    # import sys
    # Fence opens at "`````" (strip "`````", starts with "```").
    # Close: "```" strip "```" -> CLOSE.
    # Content = "def test_f(): pass\n".
    #
    # I'll just directly test using the answer with the FILE: inside the fence
    # and verify the cut works, and test the "```" removal by constructing
    # a content with "```" directly before FILE:.
    #
    # The simplest way: monkeypatch parse_files to return the content I want.
    # No, the task says "after parse_files, before writing".
    # I can test the cut function directly if it exists.
    #
    # Let me write the test to verify the full pipeline via draft_tests.
    # For the "```" case, I'll monkeypatch parse_files to return
    # [("tests/test_x.py", "def test_f(): pass\n```\nFILE: tests/conftest.py\nimport sys\n")].
    # Then draft_tests applies the cut.
    pass


def test_fence_directly_before_file_line_removed(tmp_path, monkeypatch):
    """Content = "def test_f(): pass\n```\nFILE: tests/conftest.py\nimport sys\n".
    The "```" line immediately before the FILE: line is removed."""
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_x.py"], "protected": [], "after": [], "role": None}
    # monkeypatch parse_files to return the exact content
    def fake_parse(text, allowed=None):
        return [("tests/test_x.py", "def test_f(): pass\n```\nFILE: tests/conftest.py\nimport sys\n")]
    monkeypatch.setattr(plantests.patch, "parse_files", fake_parse)
    root, state, pid, results = _setup(tmp_path, monkeypatch, [task], "irrelevant")
    results = plantests.draft_tests(
        type("G", (), {"telemetry": Telemetry(state / "t.jsonl"),
                       "ensure_model": lambda s, m: 0.0,
                       "chat": lambda s, msgs, **kw: ("c1", "irrelevant")})(),
        pid, root, state, log=lambda s: None)
    content = (root / "tests" / "test_x.py").read_text(encoding="utf-8")
    # expected: cut at "FILE: tests/conftest.py" -> content up to that line.
    # The line before the FILE: line is "```".
    # Remove the "```" line too.
    # "def test_f(): pass\n"
    assert content == "def test_f(): pass\n"
    assert "FILE:" not in content
    assert "import sys" not in content
    # The "```" was removed as well
    assert "```" not in content


def test_no_file_marker_no_cut(tmp_path, monkeypatch):
    """Content has no line starting with "FILE: " -> unchanged."""
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_x.py"], "protected": [], "after": [], "role": None}
    content = "def test_f():\n    assert True\n"
    def fake_parse(text, allowed=None):
        return [("tests/test_x.py", content)]
    monkeypatch.setattr(plantests.patch, "parse_files", fake_parse)
    root, state, pid, _ = _setup(tmp_path, monkeypatch, [task], "irrelevant")
    gw = type("G", (), {"telemetry": Telemetry(state / "t.jsonl"),
                        "ensure_model": lambda s, m: 0.0,
                        "chat": lambda s, msgs, **kw: ("c1", "irrelevant")})()
    plantests.draft_tests(gw, pid, root, state, log=lambda s: None)
    # expected: content unchanged
    assert (root / "tests" / "test_x.py").read_text(encoding="utf-8") == content


def test_file_marker_at_first_line(tmp_path, monkeypatch):
    """Content starts with "FILE: " -> cut at index 0, content becomes empty."""
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_x.py"], "protected": [], "after": [], "role": None}
    def fake_parse(text, allowed=None):
        return [("tests/test_x.py", "FILE: tests/conftest.py\nimport sys\n")]
    monkeypatch.setattr(plantests.patch, "parse_files", fake_parse)
    root, state, pid, _ = _setup(tmp_path, monkeypatch, [task], "irrelevant")
    gw = type("G", (), {"telemetry": Telemetry(state / "t.jsonl"),
                        "ensure_model": lambda s, m: 0.0,
                        "chat": lambda s, msgs, **kw: ("c1", "irrelevant")})()
    plantests.draft_tests(gw, pid, root, state, log=lambda s: None)
    # expected: everything is cut, content is empty
    content = (root / "tests" / "test_x.py").read_text(encoding="utf-8")
    assert content == ""


def test_first_file_marker_wins(tmp_path, monkeypatch):
    """Multiple FILE: lines -> only the first triggers the cut."""
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_x.py"], "protected": [], "after": [], "role": None}
    def fake_parse(text, allowed=None):
        return [("tests/test_x.py",
                 "def test_f(): pass\nFILE: tests/a.py\nx=1\nFILE: tests/b.py\ny=2\n")]
    monkeypatch.setattr(plantests.patch, "parse_files", fake_parse)
    root, state, pid, _ = _setup(tmp_path, monkeypatch, [task], "irrelevant")
    gw = type("G", (), {"telemetry": Telemetry(state / "t.jsonl"),
                        "ensure_model": lambda s, m: 0.0,
                        "chat": lambda s, msgs, **kw: ("c1", "irrelevant")})()
    plantests.draft_tests(gw, pid, root, state, log=lambda s: None)
    content = (root / "tests" / "test_x.py").read_text(encoding="utf-8")
    # expected: cut at the first FILE: -> "def test_f(): pass\n"
    # No "```" before, so nothing extra removed.
    assert content == "def test_f(): pass\n"
    assert "FILE:" not in content


def test_file_marker_in_string_not_cut(tmp_path, monkeypatch):
    """A line that contains "FILE: " as a string value (not at the start) is not cut."""
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_x.py"], "protected": [], "after": [], "role": None}
    content = 'x = "FILE: tests/conftest.py"\nassert x\n'
    def fake_parse(text, allowed=None):
        return [("tests/test_x.py", content)]
    monkeypatch.setattr(plantests.patch, "parse_files", fake_parse)
    root, state, pid, _ = _setup(tmp_path, monkeypatch, [task], "irrelevant")
    gw = type("G", (), {"telemetry": Telemetry(state / "t.jsonl"),
                        "ensure_model": lambda s, m: 0.0,
                        "chat": lambda s, msgs, **kw: ("c1", "irrelevant")})()
    plantests.draft_tests(gw, pid, root, state, log=lambda s: None)
    # expected: content unchanged (the line starts with 'x = "', not "FILE: ")
    assert (root / "tests" / "test_x.py").read_text(encoding="utf-8") == content


def test_fence_not_adjacent_not_removed(tmp_path, monkeypatch):
    """A "```" line not immediately before the FILE: line is kept."""
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_x.py"], "protected": [], "after": [], "role": None}
    def fake_parse(text, allowed=None):
        # "```" is two lines before FILE:
        return [("tests/test_x.py",
                 "def test_f(): pass\n```\nimport os\nFILE: tests/conftest.py\nsys.path\n")]
    monkeypatch.setattr(plantests.patch, "parse_files", fake_parse)
    root, state, pid, _ = _setup(tmp_path, monkeypatch, [task], "irrelevant")
    gw = type("G", (), {"telemetry": Telemetry(state / "t.jsonl"),
                        "ensure_model": lambda s, m: 0.0,
                        "chat": lambda s, msgs, **kw: ("c1", "irrelevant")})()
    plantests.draft_tests(gw, pid, root, state, log=lambda s: None)
    content = (root / "tests" / "test_x.py").read_text(encoding="utf-8")
    # expected: cut at FILE: line. Line before FILE: is "import os", not "```".
    # So "```" is kept.
    # content = "def test_f(): pass\n```\nimport os\n"
    assert content == "def test_f(): pass\n```\nimport os\n"
    assert "FILE:" not in content
    assert "sys.path" not in content


def test_cut_applied_to_every_test_file(tmp_path, monkeypatch):
    """Every test file in the returned files gets its content cut."""
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_x.py", "tests/test_y.py"],
            "protected": [], "after": [], "role": None}
    def fake_parse(text, allowed=None):
        return [
            ("tests/test_x.py", "def test_x(): pass\nFILE: tests/extra.py\nx=1\n"),
            ("tests/test_y.py", "def test_y(): pass\nFILE: tests/extra.py\ny=2\n"),
        ]
    monkeypatch.setattr(plantests.patch, "parse_files", fake_parse)
    root, state, pid, _ = _setup(tmp_path, monkeypatch, [task], "irrelevant")
    gw = type("G", (), {"telemetry": Telemetry(state / "t.jsonl"),
                        "ensure_model": lambda s, m: 0.0,
                        "chat": lambda s, msgs, **kw: ("c1", "irrelevant")})()
    plantests.draft_tests(gw, pid, root, state, log=lambda s: None)
    # expected: test_x.py = "def test_x(): pass\n"
    assert (root / "tests" / "test_x.py").read_text(encoding="utf-8") == "def test_x(): pass\n"
    # expected: test_y.py = "def test_y(): pass\n"
    assert (root / "tests" / "test_y.py").read_text(encoding="utf-8") == "def test_y(): pass\n"
    # expected: tests/extra.py not written
    assert not (root / "tests" / "extra.py").exists()


def test_answer_file_has_raw_answer(tmp_path, monkeypatch):
    """The raw answer is saved to the answers dir as-is; the cut is applied after."""
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_x.py"], "protected": [], "after": [], "role": None}
    raw_answer = ("FILE: tests/test_x.py\n```python\n"
                  "def test_f(): pass\nFILE: tests/conftest.py\nimport sys\n```\n")
    root, state, pid, results = _run(tmp_path, monkeypatch, [task], raw_answer)
    # expected: saved answer = raw_answer
    answer_path = state / "answers" / f"{pid}-a-tests.md"
    assert answer_path.read_text(encoding="utf-8") == raw_answer


def test_file_marker_with_leading_spaces_not_cut(tmp_path, monkeypatch):
    """A line starting with spaces before "FILE: " does not match the rule
    ("first line starting with 'FILE: '")."""
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_x.py"], "protected": [], "after": [], "role": None}
    content = "def test_f(): pass\n  FILE: tests/conftest.py\nx=1\n"
    def fake_parse(text, allowed=None):
        return [("tests/test_x.py", content)]
    monkeypatch.setattr(plantests.patch, "parse_files", fake_parse)
    root, state, pid, _ = _setup(tmp_path, monkeypatch, [task], "irrelevant")
    gw = type("G", (), {"telemetry": Telemetry(state / "t.jsonl"),
                        "ensure_model": lambda s, m: 0.0,
                        "chat": lambda s, msgs, **kw: ("c1", "irrelevant")})()
    plantests.draft_tests(gw, pid, root, state, log=lambda s: None)
    # expected: "  FILE:" does not start with "FILE: " -> no cut, content unchanged
    assert (root / "tests" / "test_x.py").read_text(encoding="utf-8") == content


def test_real_parse_files_two_blocks(tmp_path, monkeypatch):
    """parse_files returns two files from two FILE blocks. The second file (not
    in task["tests"]) is dropped by allowed; the first file's content has no
    FILE: line, so no cut. Content is the fence inner text."""
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_x.py"], "protected": [], "after": [], "role": None}
    answer = (
        "FILE: tests/test_x.py\n```python\n"
        "def test_f(): pass\n"
        "```\n"
        "FILE: tests/conftest.py\n```python\n"
        "import sys\n```\n"
    )
    root, state, pid, results = _run(tmp_path, monkeypatch, [task], answer)
    content = (root / "tests" / "test_x.py").read_text(encoding="utf-8")
    # expected: content = "def test_f(): pass\n" (inner fence text, no FILE: inside)
    # No cut needed.
    assert content == "def test_f(): pass\n"
    assert "FILE:" not in content
    assert not (root / "tests" / "conftest.py").exists()


def test_cut_preserves_lines_before_fence(tmp_path, monkeypatch):
    """Content = "a\nb\n```\nFILE: tests/x.py\nc\n". The "```" before FILE: is
    removed. "a" and "b" stay."""
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_x.py"], "protected": [], "after": [], "role": None}
    def fake_parse(text, allowed=None):
        return [("tests/test_x.py", "a\nb\n```\nFILE: tests/x.py\nc\n")]
    monkeypatch.setattr(plantests.patch, "parse_files", fake_parse)
    root, state, pid, _ = _setup(tmp_path, monkeypatch, [task], "irrelevant")
    gw = type("G", (), {"telemetry": Telemetry(state / "t.jsonl"),
                        "ensure_model": lambda s, m: 0.0,
                        "chat": lambda s, msgs, **kw: ("c1", "irrelevant")})()
    plantests.draft_tests(gw, pid, root, state, log=lambda s: None)
    content = (root / "tests" / "test_x.py").read_text(encoding="utf-8")
    # expected: cut at FILE: line, remove the "```" before it
    # lines: "a\nb\n" (the "```" is removed)
    assert content == "a\nb\n"
    assert "```" not in content
    assert "FILE:" not in content


def test_existing_file_not_overwritten(tmp_path, monkeypatch):
    """A test file that already exists is not overwritten; the cut does not
    change the existing file."""
    task = {"key": "a", "title": "T", "goal": "G", "files": ["pkg/x.py"],
            "tests": ["tests/test_x.py"], "protected": [], "after": [], "role": None}
    def fake_parse(text, allowed=None):
        return [("tests/test_x.py", "new\nFILE: tests/conftest.py\nx=1\n")]
    monkeypatch.setattr(plantests.patch, "parse_files", fake_parse)
    root, state, pid, _ = _setup(tmp_path, monkeypatch, [task], "irrelevant")
    (root / "tests" / "test_x.py").write_text("old\n", encoding="utf-8")
    gw = type("G", (), {"telemetry": Telemetry(state / "t.jsonl"),
                        "ensure_model": lambda s, m: 0.0,
                        "chat": lambda s, msgs, **kw: ("c1", "irrelevant")})()
    results = plantests.draft_tests(gw, pid, root, state, log=lambda s: None)
    # expected: status "exists", file content unchanged
    assert results[0]["status"] == "exists"
    assert (root / "tests" / "test_x.py").read_text(encoding="utf-8") == "old\n"
