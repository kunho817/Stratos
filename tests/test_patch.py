import pytest

from stratos import patch

ANSWER = """Here you go.
FILE: stratos/a.py
```python
X = 1
```
FILE: `docs/b.md`
```
hello
```
"""


def test_parse_files_reads_every_block():
    assert patch.parse_files(ANSWER) == [("stratos/a.py", "X = 1\n"), ("docs/b.md", "hello\n")]


def test_parse_files_without_blocks():
    assert patch.parse_files("no files here") == []


@pytest.mark.parametrize("path", ["../x.py", "C:/x.py", "/etc/x.py", "a/../../x.py", "stratos/x.exe"])
def test_bad_paths_are_refused(path):
    with pytest.raises(patch.PatchRefused):
        patch.check_path(path, [])


def test_protected_file_is_refused(tmp_path):
    with pytest.raises(patch.PatchRefused):
        patch.apply_files(tmp_path, [("tests/test_x.py", "x")], ["tests/test_x.py"])
    assert not (tmp_path / "tests").exists()


def test_nothing_written_when_one_path_is_bad(tmp_path):
    with pytest.raises(patch.PatchRefused):
        patch.apply_files(tmp_path, [("ok.py", "x"), ("../bad.py", "y")], [])
    assert not (tmp_path / "ok.py").exists()


NESTED = '''FILE: stratos/review.py
```python
PROMPT = """Answer inside a json block:
```json
{"verdict": "approve"}
```
"""
X = 1
```
'''


def test_content_may_hold_fences():
    assert patch.parse_files(NESTED) == [("stratos/review.py",
                                          'PROMPT = """Answer inside a json block:\n```json\n{"verdict": "approve"}\n```\n"""\nX = 1\n')]


SELF = '''FILE: stratos/context.py
```python
SYSTEM = """Answer like this:

FILE: relative/path.py
```python
<code>
```
"""
```
'''


def test_only_the_tasks_files_count_as_headers():
    files = patch.parse_files(SELF, allowed=["stratos/context.py"])
    assert [p for p, _ in files] == ["stratos/context.py"]
    assert "FILE: relative/path.py" in files[0][1] and files[0][1].rstrip().endswith('"""')


def test_header_on_the_first_line_inside_the_fence():
    text = "Here:\n```python\nFILE: stratos/a.py\nX = 1\n```\n```python\nFILE: stratos/b.py\nY = 2\n```\n"
    assert patch.parse_files(text, allowed=["stratos/a.py", "stratos/b.py"]) == [("stratos/a.py", "X = 1\n"),
                                                                                  ("stratos/b.py", "Y = 2\n")]


# T022: a missing header is forgiven only when nothing else is possible: no header anywhere, exactly one allowed
# file, exactly one code block (exactly two fence lines). Tiel answered T009 and T019 that way.

def test_a_lone_block_belongs_to_the_only_file():
    text = "Here is the updated module:\n```python\nX = 1\n\ndef f():\n    return X\n```\nDone."
    assert patch.parse_files(text, allowed=["stratos/a.py"]) == [("stratos/a.py", "X = 1\n\ndef f():\n    return X\n")]


def test_no_guess_with_two_blocks():
    text = "```python\nX = 1\n```\nUsage:\n```python\nprint(X)\n```\n"
    assert patch.parse_files(text, allowed=["stratos/a.py"]) == []


def test_no_guess_with_two_allowed_files():
    assert patch.parse_files("```python\nX = 1\n```\n", allowed=["stratos/a.py", "stratos/b.py"]) == []


def test_no_guess_without_an_allowed_list():
    assert patch.parse_files("```python\nX = 1\n```\n") == []


def test_a_header_still_wins():
    text = "FILE: stratos/a.py\n```python\nX = 2\n```\n"
    assert patch.parse_files(text, allowed=["stratos/a.py"]) == [("stratos/a.py", "X = 2\n")]


def test_unclosed_block_is_ignored():
    assert patch.parse_files("FILE: a.py\n```python\nx = 1\n") == []


def test_file_outside_the_task_is_refused(tmp_path):
    with pytest.raises(patch.PatchRefused):
        patch.apply_files(tmp_path, [("stratos/other.py", "x")], [], allowed=["stratos/mine.py"])


def test_apply_writes_files(tmp_path):
    assert patch.apply_files(tmp_path, [("pkg/m.py", "Y = 2\n")], []) == ["pkg/m.py"]
    assert (tmp_path / "pkg" / "m.py").read_text(encoding="utf-8") == "Y = 2\n"
