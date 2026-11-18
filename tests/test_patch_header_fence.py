"""Harness fix (2026-11-18): a FILE header alone in its own fence, then the file in the next fence.

Tiel answered T075 and T076 like this:

    ```python
    FILE: stratos/plan.py
    ```

    ```python
    ...the file...
    ```

The header was moved in front of its fence (T012's rule), which left an empty block, and the file was written from
that empty block's opening fence to the last bare fence, so it began with "```" and did not parse. An empty block
right after the header is now skipped when another opening fence follows."""
from stratos import patch

ANSWER = ("Let me rewrite it.\n\n```python\nFILE: stratos/plan.py\n```\n\n```python\n\"\"\"Doc.\"\"\"\n"
          "X = 1\n```\n")


def test_header_in_its_own_fence():
    assert patch.parse_files(ANSWER, ["stratos/plan.py"]) == [("stratos/plan.py", '"""Doc."""\nX = 1\n')]
    assert patch.parse_files(ANSWER) == [("stratos/plan.py", '"""Doc."""\nX = 1\n')]


def test_two_files_each_with_a_header_fence():
    text = ("```python\nFILE: a.py\n```\n```python\nA = 1\n```\n\n"
            "```python\nFILE: b.py\n```\n\n```python\nB = 2\n```\n")
    assert patch.parse_files(text, ["a.py", "b.py"]) == [("a.py", "A = 1\n"), ("b.py", "B = 2\n")]


def test_a_really_empty_file_block_is_left_alone():
    # an empty block with no second block after it stays empty (apply_files refuses empty files)
    assert patch.parse_files("FILE: a.py\n```python\n```\n", ["a.py"]) == [("a.py", "")]


def test_the_usual_form_still_works():
    assert patch.parse_files("FILE: a.py\n```python\nA = 1\n```\n", ["a.py"]) == [("a.py", "A = 1\n")]
