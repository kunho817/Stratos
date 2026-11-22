"""Tests for task refcheck-budget: refcheck.build_messages respects config.REF_EXISTING_CHARS budget.

config.REF_EXISTING_CHARS = 60000 is added to stratos/config.py.
In refcheck.build_messages(task, root):
  - When the total text length of all existing source files (in source_dirs, not in task files,
    filtered by writable_suffixes, excluding __pycache__/bin/obj) fits within the budget,
    the prompt is exactly as today (all shown in full, sorted by path).
  - Otherwise: files whose stem (filename without suffix) appears as a whole word in the task goal
    come first (sorted by path among matched), then the rest in today's sorted path order.
    Each shown in full while the running total of text lengths stays within budget;
    files beyond the budget become one line "EXISTING FILE <path> (not shown, <n> lines)".
  - The task's own files (shown as FILE YOU MAY CHANGE) are not in the existing set and
    do not count toward the budget.
"""

import re
from pathlib import Path

from stratos import config, refcheck

# Task with goal word "add"; task file pkg/calc.py
TASK = {"key": "add", "goal": "Write add in pkg/calc.py.",
        "files": ["pkg/calc.py"], "tests": ["tests/test_calc.py"]}


def _build(tmp_path, monkeypatch, budget, source_files):
    """Create a project root with pkg/ containing __init__.py and the given source files.
    source_files: list of (filename, text) written under pkg/.
    Returns root. config.PROJECT and REF_EXISTING_CHARS are monkeypatched."""
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    for name, text in source_files:
        (root / "pkg" / name).write_text(text, encoding="utf-8")
    (root / "tests").mkdir()
    monkeypatch.setattr(config, "PROJECT",
                        {**config.PROJECT, "source_dirs": ["pkg"],
                         "writable_suffixes": [".py"]})
    monkeypatch.setattr(config, "REF_EXISTING_CHARS", budget)
    return root


# ---- 1: config.REF_EXISTING_CHARS is 60000 ----

def test_ref_existing_chars_is_60000():
    # The task adds config.REF_EXISTING_CHARS = 60000
    assert config.REF_EXISTING_CHARS == 60000


# ---- 2: total text fits within budget → prompt as today ----

def test_fits_within_budget_same_as_today(tmp_path, monkeypatch):
    # Two small files: text total 15 + 10 = 25 ≤ budget 60000
    # __init__.py text "" = 0 chars; total = 0 + 15 + 10 = 25 ≤ 60000
    # → all shown in full, in sorted path order
    root = _build(tmp_path, monkeypatch, 60000,
                  [("util.py", "ZERO = 0\n"), ("beta.py", "X = 1\n")])
    user = refcheck.build_messages(TASK, root)[1]["content"]
    # Sorted paths: pkg/__init__.py, pkg/beta.py, pkg/util.py
    # task file pkg/calc.py excluded from existing
    i_init = user.index("pkg/__init__.py")
    i_beta = user.index("pkg/beta.py")
    i_util = user.index("pkg/util.py")
    # sorted order preserved
    assert i_init < i_beta < i_util
    # shown in full (backtick fence present)
    assert "EXISTING FILE pkg/util.py:\n```\nZERO = 0\n\n```" in user
    assert "EXISTING FILE pkg/beta.py:\n```\nX = 1\n\n```" in user
    # no "not shown" lines
    assert "(not shown" not in user


# ---- 3: over budget, matching stem comes first ----

def test_over_budget_stem_match_first(tmp_path, monkeypatch):
    # Goal "Write add in pkg/calc.py." → whole word "add"
    # pkg/add.py: stem "add" → match.  pkg/beta.py: stem "beta" → no match.
    # Budget 50: add.py text = 30 chars, beta.py text = 30 chars.
    # Total = 0(init) + 30 + 30 = 60 > 50.
    # Order: add.py (matched), beta.py (unmatched) — add.py before beta.py.
    # add.py: 0 + 30 = 30 ≤ 50 → full.
    # beta.py: 30 + 30 = 60 > 50 → not shown.
    # "x" * 30 → splitlines = 1 line.
    root = _build(tmp_path, monkeypatch, 50,
                  [("add.py", "x" * 30), ("beta.py", "x" * 30)])
    user = refcheck.build_messages(TASK, root)[1]["content"]
    # add.py index < beta.py index
    assert user.index("pkg/add.py") < user.index("pkg/beta.py")
    # add.py shown in full (backtick fence)
    assert "EXISTING FILE pkg/add.py:\n```\n" in user
    # beta.py → not shown, 1 line
    assert "EXISTING FILE pkg/beta.py (not shown, 1 lines)" in user
    # add.py full content present
    assert "x" * 30 in user


# ---- 4: not-shown line format ----

def test_not_shown_format(tmp_path, monkeypatch):
    # Budget 10. File big.py: text "aaaa\nbbbb\ncccc\ncccc" → 4 lines, 20 chars.
    # __init__.py: 0 chars. Running: 0 + 20 = 20 > 10 → not shown.
    # len("aaaa\nbbbb\ncccc\ncccc".splitlines()) = 4.
    text = "aaaa\nbbbb\ncccc\ncccc"
    root = _build(tmp_path, monkeypatch, 10, [("big.py", text)])
    user = refcheck.build_messages(TASK, root)[1]["content"]
    # __init__.py (0 chars) fits: 0 ≤ 10 → shown.
    # big.py: 0 + 20 = 20 > 10 → not shown.
    assert "EXISTING FILE pkg/big.py (not shown, 4 lines)" in user


# ---- 5: whole-word matching, not substring ----

def test_whole_word_not_substring(tmp_path, monkeypatch):
    # Goal "Write add in pkg/calc.py." → word "add".
    # pkg/add.py: stem "add" → whole word match ✓.
    # pkg/addres.py: stem "addres" → NOT a whole word in "add" ✓.
    # Budget 15: add.py 10 chars, addres.py 10 chars.
    # __init__.py 0. Total 0 + 10 + 10 = 20 > 15.
    # Order: add.py (matched), addres.py (unmatched).
    # add.py: 0 + 10 = 10 ≤ 15 → full. addres.py: 10 + 10 = 20 > 15 → not shown.
    root = _build(tmp_path, monkeypatch, 15,
                  [("add.py", "x" * 10), ("addres.py", "x" * 10)])
    user = refcheck.build_messages(TASK, root)[1]["content"]
    # add.py before addres.py
    assert user.index("pkg/add.py") < user.index("pkg/addres.py")
    # add.py full
    assert "EXISTING FILE pkg/add.py:\n```\n" in user
    # addres.py not shown
    assert "EXISTING FILE pkg/addres.py (not shown, 1 lines)" in user


# ---- 6: non-matching files in today's sorted order ----

def test_non_matching_sorted_order(tmp_path, monkeypatch):
    # Goal "Make it work." — no stems match.
    # Files: z.py, a.py, m.py (sorted: a, m, z).
    # Budget 15: a.py 10, m.py 10, z.py 10.
    # Running: a → 0+10=10 ≤ 15 full. m → 10+10=20 > 15 not shown. z → not shown.
    root = _build(tmp_path, monkeypatch, 15,
                  [("a.py", "x" * 10), ("m.py", "x" * 10), ("z.py", "x" * 10)])
    user = refcheck.build_messages(TASK, root)[1]["content"]
    # sorted order: a before m before z
    assert user.index("pkg/a.py") < user.index("pkg/m.py")
    assert user.index("pkg/m.py") < user.index("pkg/z.py")
    assert "EXISTING FILE pkg/a.py:\n```\n" in user
    assert "EXISTING FILE pkg/m.py (not shown, 1 lines)" in user
    assert "EXISTING FILE pkg/z.py (not shown, 1 lines)" in user


# ---- 7: running total exactly equals budget → all shown ----

def test_exact_budget_all_shown(tmp_path, monkeypatch):
    # Budget 20. a.py text 10, b.py text 10.
    # __init__.py 0. Total = 0 + 10 + 10 = 20 = budget.
    # Running: 0+10=10 ≤ 20 → a full. 10+10=20 ≤ 20 → b full.
    root = _build(tmp_path, monkeypatch, 20,
                  [("a.py", "x" * 10), ("b.py", "x" * 10)])
    user = refcheck.build_messages(TASK, root)[1]["content"]
    assert "EXISTING FILE pkg/a.py:\n```\n" in user
    assert "EXISTING FILE pkg/b.py:\n```\n" in user
    assert "(not shown" not in user


# ---- 8: exceeds budget at last file → last not shown ----

def test_exceeds_at_last_file(tmp_path, monkeypatch):
    # Budget 25. Three files: a.py 10, b.py 10, c.py 10.
    # __init__.py 0.
    # Running: a: 0+10=10 ≤ 25 full. b: 10+10=20 ≤ 25 full. c: 20+10=30 > 25 not shown.
    root = _build(tmp_path, monkeypatch, 25,
                  [("a.py", "x" * 10), ("b.py", "x" * 10), ("c.py", "x" * 10)])
    user = refcheck.build_messages(TASK, root)[1]["content"]
    # sorted (no matching stems in goal): a, b, c
    assert user.index("pkg/a.py") < user.index("pkg/b.py")
    assert user.index("pkg/b.py") < user.index("pkg/c.py")
    assert "EXISTING FILE pkg/a.py:\n```\n" in user
    assert "EXISTING FILE pkg/b.py:\n```\n" in user
    assert "EXISTING FILE pkg/c.py (not shown, 1 lines)" in user


# ---- 9: task files are not counted in the budget ----

def test_task_files_not_in_budget(tmp_path, monkeypatch):
    # pkg/calc.py is the task file → excluded from existing.
    # Two small existing files: a.py 5, b.py 5. Total = 0 + 5 + 5 = 10 ≤ 10.
    # Budget 10 → all fit.
    root = _build(tmp_path, monkeypatch, 10,
                  [("a.py", "x" * 5), ("b.py", "x" * 5)])
    # pkg/calc.py does not exist on disk
    user = refcheck.build_messages(TASK, root)[1]["content"]
    # task file pkg/calc.py is NOT shown as EXISTING FILE
    assert "EXISTING FILE pkg/calc.py" not in user
    # all small existing files shown in full
    assert "EXISTING FILE pkg/a.py:\n```\n" in user
    assert "EXISTING FILE pkg/b.py:\n```\n" in user
    assert "(not shown" not in user


# ---- 10: no existing source files → budget irrelevant ----

def test_no_existing_files(tmp_path, monkeypatch):
    # Only pkg/__init__.py (text "" = 0 chars). Budget 5.
    # 0 ≤ 5 → fits. No EXISTING FILE lines beyond __init__.py.
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests").mkdir()
    monkeypatch.setattr(config, "PROJECT",
                        {**config.PROJECT, "source_dirs": ["pkg"],
                         "writable_suffixes": [".py"]})
    monkeypatch.setattr(config, "REF_EXISTING_CHARS", 5)
    user = refcheck.build_messages(TASK, root)[1]["content"]
    assert "EXISTING FILE pkg/__init__.py:\n```\n\n```" in user
    assert "(not shown" not in user


# ---- 11: multiple matching stems in sorted order ----

def test_multiple_matching_stems_sorted(tmp_path, monkeypatch):
    # Goal mentions "add" and "util" as whole words.
    goal = "Write add and util helpers in the project."
    task = dict(TASK, goal=goal)
    # Files: pkg/util.py (stem "util"), pkg/add.py (stem "add"), pkg/beta.py (stem "beta").
    # Matching stems: add, util. Sorted paths: pkg/add.py, pkg/util.py.
    # Non-matching: pkg/beta.py.
    # Budget 15: add 5, util 5, beta 5.
    # Running: add: 0+5=5 ≤ 15. util: 5+5=10 ≤ 15. beta: 10+5=15 ≤ 15.
    # All fit! 15 = 15.
    root = _build(tmp_path, monkeypatch, 15,
                  [("add.py", "x" * 5), ("util.py", "x" * 5), ("beta.py", "x" * 5)])
    user = refcheck.build_messages(task, root)[1]["content"]
    # add.py before util.py (both matched, sorted)
    assert user.index("pkg/add.py") < user.index("pkg/util.py")
    # util.py before beta.py
    assert user.index("pkg/util.py") < user.index("pkg/beta.py")
    # all shown in full
    assert "EXISTING FILE pkg/add.py:\n```\n" in user
    assert "EXISTING FILE pkg/util.py:\n```\n" in user
    assert "EXISTING FILE pkg/beta.py:\n```\n" in user
    assert "(not shown" not in user


# ---- 12: budget 0 → all files not shown ----

def test_budget_zero_all_not_shown(tmp_path, monkeypatch):
    # Budget 0. Any file with non-empty text exceeds → not shown.
    # __init__.py text "" → 0 chars. 0 + 0 = 0 ≤ 0 → shown.
    # a.py text 1 char → 0 + 1 = 1 > 0 → not shown.
    root = _build(tmp_path, monkeypatch, 0, [("a.py", "x")])
    user = refcheck.build_messages(TASK, root)[1]["content"]
    # __init__.py (0 chars) fits
    assert "EXISTING FILE pkg/__init__.py:\n```\n\n```" in user
    # a.py: 0 + 1 = 1 > 0 → not shown
    assert "EXISTING FILE pkg/a.py (not shown, 1 lines)" in user


# ---- 13: goal with no matching stems → sorted path order ----

def test_no_stems_match_sorted_order(tmp_path, monkeypatch):
    # Goal: "Make it work." → no stems match.
    # Files: z.py, a.py, m.py. Sorted: a, m, z.
    # Budget large (60000) → all fit.
    root = _build(tmp_path, monkeypatch, 60000,
                  [("a.py", "x" * 10), ("m.py", "x" * 10), ("z.py", "x" * 10)])
    user = refcheck.build_messages(TASK, root)[1]["content"]
    assert user.index("pkg/a.py") < user.index("pkg/m.py")
    assert user.index("pkg/m.py") < user.index("pkg/z.py")
    # all full
    assert "(not shown" not in user
