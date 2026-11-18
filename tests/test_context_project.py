"""Tests for the project's language in CODER_SYSTEM (plan P008, context_system_language).

context.coder_system(language) returns the coders' system prompt for a project in that language; the language name
is used as written in the settings (e.g. "Python", "JavaScript") and lower-cased as the code fence's tag.
context.CODER_SYSTEM = coder_system(<config.PROJECT["language"] with its first letter upper-cased>), and with
Stratos's default ("python") it is exactly the text it was before, last line included (tests/test_context_system.py).
(The test runner is named in plantests.TEST_SYSTEM, not here: the coder already sees the tests it must pass.)"""
from stratos import context

BEFORE = """You are the coding model inside Stratos, a harness that edits a Python project.
Answer ONLY with whole files in this exact format, one block per file, and nothing else:

FILE: relative/path.py
```python
<the entire file content>
```

Rules:
- You have no tools and cannot open files: everything you need is in this message. Answer with the files directly.
- Write complete files, never fragments or diffs.
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
