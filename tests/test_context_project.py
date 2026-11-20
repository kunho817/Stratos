"""Tests for the project's language in CODER_SYSTEM (plan P008, context_system_language).

context.coder_system(language) returns the coders' system prompt for a project in that language; the language name
is used as written in the settings (e.g. "Python", "JavaScript") and lower-cased as the code fence's tag.
context.CODER_SYSTEM = coder_system(<config.PROJECT["language"] with its first letter upper-cased>), and with
Stratos's default ("python") it is exactly BEFORE below, last line included (tests/test_context_system.py).
(Updated by Claude for task loop_edits, 2026-11-20: the edit-block format for existing files.)
(The test runner is named in plantests.TEST_SYSTEM, not here: the coder already sees the tests it must pass.)"""
from stratos import context

BEFORE = """You are the coding model inside Stratos, a harness that edits a Python project.
Answer ONLY with file blocks in one of these two formats, and nothing else.

A new file, or a short one written whole:
FILE: relative/path.py
```python
<the entire file content>
```

A change to a file that already exists:
FILE: relative/path.py
<<<<<<< SEARCH
<lines copied exactly from the file as shown>
=======
<the lines that replace them>
>>>>>>> REPLACE

Rules:
- You have no tools and cannot open files: everything you need is in this message. Answer with the files directly.
- For an existing file use edit blocks: each SEARCH is copied exactly from the file shown (indentation included), is found exactly once, and holds only a few lines around the change; use several blocks for several changes.
- A whole file must be complete, never a fragment.
- Do not change files marked READ-ONLY. Do not add test code, prints or example runs to the files you write.
- Use only the Python standard library unless the task says otherwise.
- Keep the code plain and correct; the task's tests decide whether you succeeded."""


def test_stratos_default_is_unchanged():
    assert context.CODER_SYSTEM == BEFORE
    assert context.coder_system("Python") == BEFORE


def test_another_language():
    s = context.coder_system("JavaScript")
    assert "edits a JavaScript project." in s
    assert "```javascript\n" in s and "```python" not in s
    assert "Use only the JavaScript standard library" in s
    assert "Python" not in s
    assert s.splitlines()[-1] == BEFORE.splitlines()[-1]
    assert s.count("\n") == BEFORE.count("\n")
