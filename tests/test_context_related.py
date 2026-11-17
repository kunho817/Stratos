"""Tests for task T029: the prompt shows, read-only, the package modules that the task's files import.

context.related_files(root, files) -> sorted list of relative paths (with '/'), for every existing file in `files`:
the modules of its own package that it imports, found by parsing it (ast):
  'from . import a, b'      -> <package>/a.py, <package>/b.py
  'from .x import y'        -> <package>/x.py
  'from <pkg> import a'     -> <package>/a.py      (<pkg> = the name of the file's own folder)
  'from <pkg>.x import y'   -> <package>/x.py
  'import <pkg>.x'          -> <package>/x.py
Only files that exist under root count; the task's own files are left out; a file that does not exist yet or does not
parse adds nothing. Other imports (json, ..., relative imports with two or more dots) are ignored.

context.build_messages(task, root, failure) shows each related file that is not already one of the task's files or
protected files, after the protected ones, labelled 'READ-ONLY (imported by the files you write)'.
In T009 and T027 a model that was not shown these files tried to open them itself and failed."""
from stratos import context

LOOP = """\"\"\"loop\"\"\"
import json
from pathlib import Path

from . import config, gitops
from .review import parse
from stratos import patch
import stratos.verify
from . import missing
"""


def make(tmp_path, extra=None):
    pkg = tmp_path / "stratos"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "loop.py").write_text(LOOP, encoding="utf-8")
    for name in ("config", "gitops", "review", "patch", "verify", "unused"):
        (pkg / f"{name}.py").write_text(f"NAME = '{name}'\n", encoding="utf-8")
    for path, body in (extra or {}).items():
        (tmp_path / path).write_text(body, encoding="utf-8")
    return tmp_path


def test_related_files_follow_the_imports(tmp_path):
    root = make(tmp_path)
    assert context.related_files(root, ["stratos/loop.py"]) == [
        "stratos/config.py", "stratos/gitops.py", "stratos/patch.py", "stratos/review.py", "stratos/verify.py"]


def test_the_tasks_own_files_are_left_out(tmp_path):
    root = make(tmp_path)
    assert "stratos/config.py" not in context.related_files(root, ["stratos/loop.py", "stratos/config.py"])


def test_a_new_file_or_a_broken_file_adds_nothing(tmp_path):
    root = make(tmp_path, {"stratos/broken.py": "def (:\n"})
    assert context.related_files(root, ["stratos/new.py"]) == []
    assert context.related_files(root, ["stratos/broken.py"]) == []


def test_build_messages_shows_related_files_once(tmp_path):
    root = make(tmp_path)
    task = {"id": "T009", "title": "t", "goal": "g", "files": ["stratos/loop.py"],
            "protected": ["tests/test_x.py", "stratos/config.py"]}
    user = context.build_messages(task, root)[-1]["content"]
    assert "READ-ONLY (imported by the files you write): stratos/gitops.py" in user
    assert "NAME = 'gitops'" in user
    assert user.count("stratos/config.py") == 1          # already shown as protected
    assert "stratos/unused.py" not in user
    assert user.index("READ-ONLY (the tests that must pass): stratos/config.py") < \
        user.index("READ-ONLY (imported by the files you write): stratos/gitops.py")
