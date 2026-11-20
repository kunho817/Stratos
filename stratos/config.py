"""Stratos settings: where PolyStrata is, which model plays which role, and how hard to try.

Role defaults come from the 2026-11-16 measurements (see the Stratos design doc): Tiel Coder was the fastest coder
with near-perfect answers, Flint the most accurate (10/10 on the LeetCode variants) but the slowest.
2026-11-18: coder_hard moved from Flint to Qwen3.8-Flash-Next Coder IQ1_M after `stratos replay` on six hard tasks
(three runs, effort low, two tries): Coder 17/18 at ~129 s per call, Flint 8/12 at ~216 s per call. Flint stays installed.
Later the same day: coder_hard moved again, to Swift 1.5 IQ2_XS (UkisAI's fine-tune of Qwen3.8-Flash-Next that thinks
shorter) with a 3000-token reasoning budget: 12/12 first try at ~51 s per task (Coder with the same budget: 12/12, ~74 s).
"""
import os
from pathlib import Path

BASE_URL = os.environ.get("STRATOS_BASE_URL", "http://127.0.0.1:8080")

ROLES = {
    "coder": {"model": "tiel-coder-35b-a3b-ud-q4_k_xl", "effort": "none", "max_tokens": 6000},
    # Swift 1.5 runs on PolyStrata's separate engine (engine\strata.exe): switching to it takes ~60-100 s (Flint ~27 s).
    # It writes ~4,300 tokens per call with the budget; Windows has only ~13 GB of memory left while it is loaded
    "coder_hard": {"model": "swift-1.5-iq2_xs", "effort": "low", "max_tokens": 24000, "reasoning_budget": 3000},
    # reads the diff after the tests pass; a different model from the coders, so it does not share their blind spots
    "reviewer": {"model": "qwen3.6-35b-a3b-ud-q3_k_m", "effort": "low", "max_tokens": 4000},
}

REVIEW = True   # review every diff that passes its tests; high/medium issues send it back as a failed attempt
REVIEW_ROUNDS = 3   # write -> review rounds before a task the reviewer keeps rejecting goes to a person

# attempts per task, by the task's role: the role's own model first, then one cross-check by a different model
# (the design's rule: cross-check only hard tasks, i.e. the ones that keep failing)
ATTEMPT_PLANS = {
    "coder": [("coder", 2), ("coder_hard", 2)],  # Tiel passed only 10 of 56 third attempts; two Swift attempts instead
    "coder_hard": [("coder_hard", 2), ("coder", 1)],
}
ATTEMPT_PLAN = ATTEMPT_PLANS["coder"]   # the plan before tasks had roles

TEST_TIMEOUT_S = 300
VERIFY_RUNS = 3          # each with a different PYTHONHASHSEED; all must pass
REQUEST_TIMEOUT_S = 900

# Jev (TypeSafe AI's cloud decision model) runs in shadow mode: asked alongside the rules and recorded in telemetry,
# never followed. Only a summary of the task is sent (goal, file paths). STRATOS_JEV=0 turns it off.
JEV_SHADOW = os.environ.get("STRATOS_JEV", "1") != "0"

# A/B of a failure diagnosis (2026-11-18): after a failed coder (Tiel) attempt that will be retried, half of the retries
# (diagnose.use_hint) also get a short diagnosis by AgentWorld; report compares the two halves. STRATOS_DIAGNOSE=0 off.
# Offline on 17 tasks: retries with the diagnosis passed 7/19, without 5/19 (too few to be sure)
DIAGNOSE_AB = os.environ.get("STRATOS_DIAGNOSE", "1") != "0"
# the diagnosis A/B is over (with a diagnosis 9 of 36 retries passed, without 2 of 32), every eligible retry gets one
DIAGNOSE_ALWAYS = os.environ.get("STRATOS_DIAGNOSE_ALWAYS", "1") != "0"
DIAGNOSER = {"model": "qwen3.6-35b-a3b-ud-q4_k_m", "effort": "low", "max_tokens": 1500}

# The planner (2026-11-18) splits a feature goal into Stratos tasks (stratos plan); a person checks the plan before
# `stratos plan-add` adds it. Swift is the strongest model here; planning gets more room to think than coding
PLANNER = {"model": "swift-1.5-iq2_xs", "effort": "medium", "max_tokens": 24000, "reasoning_budget": 8000}

# PLAN_CRITIC: reviews a plan before its tests are drafted; Flint named 17 of 24 known plan problems in experiment b
PLAN_CRITIC = {"model": "flint-40b-a2.5b-ud-q4_k_xl", "effort": "low", "max_tokens": 12000}
# STRATOS_PLAN_CRITIQUE=0 turns the plan critique off (run from CLI after plan, and via plan-critique)
PLAN_CRITIQUE = os.environ.get("STRATOS_PLAN_CRITIQUE", "1") != "0"

# Text planning (2026-11-18): the planner writes the plan as Key:/Title:/Goal:... text, which plan.parse_text_plan
# reads (AgentWorld as a JSON converter broke the JSON on quotes in goals twice). PLAN_CONVERTER is only the fallback
# for text that is not in that format; None: no fallback. PLAN_AS_TEXT False: the planner writes the JSON itself
PLAN_AS_TEXT = True
PLAN_CONVERTER = {"model": "qwen3.6-35b-a3b-ud-q4_k_m", "effort": "none", "max_tokens": 8000}

# checks drafted tests before any code is written; the drafts come from the same model, so no switch
DRAFT_CHECKER = {"model": "swift-1.5-iq2_xs", "effort": "low", "max_tokens": 12000}
# STRATOS_DRAFT_CHECK=0 turns the draft checker off; on by default
DRAFT_CHECK = os.environ.get("STRATOS_DRAFT_CHECK", "1") != "0"

# TRIAGE (2026-11-18): after a task fails its tests, a quick model decides whether the failing assertion is the test's
# fault (test_wrong) or the code's (code_wrong), so the retry targets the right file. STRATOS_TRIAGE=0 turns it off.
TRIAGE = os.environ.get("STRATOS_TRIAGE", "1") != "0"
TRIAGER = {"model": "swift-1.5-iq2_xs", "effort": "low", "max_tokens": 8000, "reasoning_budget": 3000}

# run each task's tests on its base before any model call (preflight); refuse impossible tasks early. STRATOS_PREFLIGHT=0 off.
PREFLIGHT = os.environ.get("STRATOS_PREFLIGHT", "1") != "0"

# ruff on the Python files a model writes: undefined names stop an attempt before the tests, unused imports are
# removed after they pass. STRATOS_LINT=0 turns it off.
LINT = os.environ.get("STRATOS_LINT", "1") != "0"

# feed the memory's context packs to the models
MEMORY = True

# CPU embedding model for the memory; jina's code model found 7/8 expected chunks in a top 5, bge-small 5/8
EMBED = {"model": "jinaai/jina-embeddings-v2-base-code", "cache_dir": r"C:\PolyStrata-data\embeddings", "max_chars": 2000}

_stratos_repo = os.environ.get("STRATOS_REPO")
if _stratos_repo:
    REPO = Path(_stratos_repo)
    WORKTREES = REPO.parent / (REPO.name + "-wt")
else:
    REPO = Path(__file__).resolve().parent.parent
    WORKTREES = REPO.parent / "Stratos-wt"

STRATOS_HOME = Path(__file__).resolve().parent.parent
LESSONS = STRATOS_HOME / "LESSONS.md"   # general lessons shared by every project

STATE_DIR = REPO / ".stratos"

from stratos import project

PROJECT = project.load_settings(REPO)
WRITABLE_SUFFIXES = set(PROJECT["writable_suffixes"])

# the model that turns people's corrections into general lessons (M3b); same model as reviewer, loaded at end of run
LEARNER = {"model": "qwen3.6-35b-a3b-ud-q3_k_m", "effort": "none", "max_tokens": 600}
# the coder's model writes the module notes of the wiki
WIKI = {"model": "tiel-coder-35b-a3b-ud-q4_k_xl", "effort": "none", "max_tokens": 3000}

