"""Stratos settings: where PolyStrata is, which model plays which role, and how hard to try.

Role defaults come from the 2026-11-16 measurements (see the Stratos design doc): Tiel Coder was the fastest coder
with near-perfect answers, Flint the most accurate (10/10 on the LeetCode variants) but the slowest.
"""
import os
from pathlib import Path

BASE_URL = os.environ.get("STRATOS_BASE_URL", "http://127.0.0.1:8080")

ROLES = {
    "coder": {"model": "tiel-coder-35b-a3b-ud-q4_k_xl", "effort": "none", "max_tokens": 6000},
    "coder_hard": {"model": "flint-40b-a2.5b-ud-q4_k_xl", "effort": "high", "max_tokens": 12000},
}

# attempts per task: the role's own model first, then one cross-check by a different model (the design's rule:
# cross-check only hard tasks, i.e. the ones that keep failing)
ATTEMPT_PLAN = [("coder", 3), ("coder_hard", 1)]

# files a model may write (anything else in its answer is refused)
WRITABLE_SUFFIXES = {".py", ".md", ".toml", ".txt", ".json"}

TEST_TIMEOUT_S = 300
REQUEST_TIMEOUT_S = 900

REPO = Path(__file__).resolve().parent.parent
STATE_DIR = REPO / ".stratos"
WORKTREES = REPO.parent / "Stratos-wt"
