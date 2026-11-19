"""Tests for task preflight_package (P1, 2026-11-20, found by Claude reading T155's diff): `from stratos import
preflight` with stratos/preflight.py missing fails with "cannot import name 'preflight' from 'stratos'
(...\\stratos\\__init__.py)". preflight.missing_imports must not report the package's __init__.py then - that would
refuse every task that writes a new module.

Rule: for a Python "cannot import name 'X' from '<module>' (<file>)" whose file is an __init__.py, the entry is the
submodule <folder of the __init__>/X.py when that file does not exist; when it exists (the name is missing from the
package itself) or X is defined elsewhere, the entry stays the __init__.py.
Also: paths are made relative to Path(wt).resolve() (a wt given as a relative path works)."""
import os

from stratos import preflight


def make(root, files):
    for path, text in files.items():
        p = root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def test_new_submodule_is_the_entry(tmp_path):
    wt = make(tmp_path, {"stratos/__init__.py": "", "stratos/verify.py": "", "tests/test_p.py": ""})
    out = f"E   ImportError: cannot import name 'preflight' from 'stratos' ({wt / 'stratos' / '__init__.py'})"
    assert preflight.missing_imports(out, wt, ["tests/test_p.py"]) == ["stratos/preflight.py"]


def test_new_module_task_runs(tmp_path):
    wt = make(tmp_path, {"stratos/__init__.py": "", "tests/test_p.py": "from stratos import preflight\n"})
    out = f"E   ImportError: cannot import name 'preflight' from 'stratos' ({wt / 'stratos' / '__init__.py'})"
    task = {"id": "T1", "files": ["stratos/preflight.py"], "tests": ["tests/test_p.py"], "protected": []}
    r = preflight.check(task, wt, run=lambda w, t: (False, out))
    assert r["verdict"] == "run" and r["reason"] == "tests fail before the change"


def test_existing_submodule_keeps_the_init(tmp_path):
    wt = make(tmp_path, {"stratos/__init__.py": "", "stratos/verify.py": ""})
    out = f"ImportError: cannot import name 'verify' from 'stratos' ({wt / 'stratos' / '__init__.py'})"
    assert preflight.missing_imports(out, wt, []) == ["stratos/__init__.py"]


def test_relative_wt(tmp_path, monkeypatch):
    wt = make(tmp_path / "w", {"pkg/__init__.py": "", "pkg/a.py": ""})
    monkeypatch.chdir(tmp_path)
    out = f"ImportError: cannot import name 'f' from 'pkg.a' ({wt / 'pkg' / 'a.py'})"
    assert preflight.missing_imports(out, os.path.join("w"), []) == ["pkg/a.py"]
