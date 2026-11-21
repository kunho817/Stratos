"""Tests for task search_consensus (P17 b, 2026-11-21, trial 15): Lantern's generators by Tiel and Swift all failed (10
of 14 were right - the solver they called was wrong), but a search failure names no test, so no consensus was found and
triage blamed the generator.

loop: an attempt that ends "search_failed" counts for consensus under the id "(the generator)" (like a failing test of
that model) and is the last failed answer for triage, like "failed". triage.build_messages: when consensus holds
"(the generator)", after the consensus lines it adds "Generators written by different models all failed: the code
they call (the task's protected source files) may be wrong - check it before blaming the generator."."""
from stratos import triage

TASK = {"id": "T7", "goal": "levels", "tests": []}


def test_triage_names_the_callee():
    user = triage.build_messages(TASK, ".", [], "The generator tools/gen.mjs ran longer than 60 s.",
                                 consensus=["(the generator)"])[1]["content"]
    assert ("Generators written by different models all failed: the code they call (the task's protected source "
            "files) may be wrong - check it before blaming the generator.") in user
    plain = triage.build_messages(TASK, ".", [], "x", consensus=["tests/a.py::t"])[1]["content"]
    assert "Generators written by" not in plain


def test_loop_counts_search_failures_for_consensus():
    import inspect

    from stratos import loop
    src = inspect.getsource(loop)
    assert '"(the generator)"' in src
    assert 'result in ("failed", "search_failed")' in src
