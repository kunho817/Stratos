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


def test_apply_writes_files(tmp_path):
    assert patch.apply_files(tmp_path, [("pkg/m.py", "Y = 2\n")], []) == ["pkg/m.py"]
    assert (tmp_path / "pkg" / "m.py").read_text(encoding="utf-8") == "Y = 2\n"
