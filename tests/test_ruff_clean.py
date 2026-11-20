"""Tests for task ruff_clean (P7, 2026-11-20): the stratos package has no pyflakes findings (ruff's F rules) - no
undefined names, unused imports or unused variables. When the lint step went in, ruff found 5 in Stratos itself:
unused `sys` in plantests.py and verify.py, unused locals `module` (preflight.py), `call_outcomes` (report.py) and
`by_id` (scheduler.py). Keeping the package clean keeps the lint step's own signal clear."""
import subprocess
import sys
from pathlib import Path

import pytest

from stratos import lint

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(not lint.available(), reason="ruff is not installed")
def test_no_pyflakes_findings_in_stratos():
    r = subprocess.run([sys.executable, "-m", "ruff", "check", "--no-cache", "--select", "F",
                        "--output-format", "concise", "stratos"], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout
