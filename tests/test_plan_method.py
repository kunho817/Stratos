"""Tests for task t19_method: the METHOD guidance sentence is appended to plan.SYSTEM and plan.TEXT_SYSTEM
in stratos/plan.py. The appended text (with a leading space) is:
" When a task holds an algorithm (a search, a schedule, a simulation, an ordering with tie-breaks), end its
goal with a line METHOD: the steps that meet the rules (the data kept, the order things are tried in, what
is skipped) - no code."
Only append; existing content of both strings is unchanged. TEXT_SYSTEM embeds _RULES (the substring of
SYSTEM from "Tasks that write the same file" onward), so the append to SYSTEM flows into TEXT_SYSTEM via _RULES.
"""

from stratos import plan

APPENDED = (' When a task holds an algorithm (a search, a schedule, a simulation, an ordering with '
            'tie-breaks), end its goal with a line METHOD: the steps that meet the rules '
            '(the data kept, the order things are tried in, what is skipped) - no code.')


# ---------------------------------------------------------------------------
# 1. The appended sentence is in SYSTEM.
# ---------------------------------------------------------------------------

def test_system_contains_appended_sentence():
    """plan.SYSTEM must include the exact METHOD guidance sentence."""
    # expected: APPENDED is a substring of SYSTEM
    assert APPENDED in plan.SYSTEM


# ---------------------------------------------------------------------------
# 2. The appended sentence is at the very end of SYSTEM.
# ---------------------------------------------------------------------------

def test_appended_at_the_end_of_system():
    """The appended sentence comes at the end of SYSTEM."""
    # expected: SYSTEM ends with APPENDED
    assert plan.SYSTEM.endswith(APPENDED)


# ---------------------------------------------------------------------------
# 3. The appended sentence is in TEXT_SYSTEM.
# ---------------------------------------------------------------------------

def test_text_system_contains_appended_sentence():
    """plan.TEXT_SYSTEM must include the exact METHOD guidance sentence (via _RULES)."""
    # expected: APPENDED is a substring of TEXT_SYSTEM
    assert APPENDED in plan.TEXT_SYSTEM


# ---------------------------------------------------------------------------
# 4. The appended sentence is at the very end of TEXT_SYSTEM.
# ---------------------------------------------------------------------------

def test_appended_at_the_end_of_text_system():
    """TEXT_SYSTEM ends with the appended sentence (it is the tail of _RULES)."""
    # expected: TEXT_SYSTEM ends with APPENDED
    assert plan.TEXT_SYSTEM.endswith(APPENDED)


# ---------------------------------------------------------------------------
# 5. The existing prefix of SYSTEM is preserved.
# ---------------------------------------------------------------------------

def test_existing_system_content_preserved():
    """The original SYSTEM text is preserved: its old sentences are still present and the
    appended METHOD sentence is the last text."""
    # expected: a few old SYSTEM sentences are still in SYSTEM
    for old in ("You are a planner.",
                "Each task should be small (one function or one file).",
                "after lists keys of earlier tasks it builds on.",
                "protected lists files it may read but not change.",
                "Tasks that write the same file must be chained",
                "Prefer 2 to 6 tasks for a feature."):
        assert old in plan.SYSTEM
    # expected: a few old TEXT_SYSTEM sentences are still in TEXT_SYSTEM
    for old in ("Answer with plain text, no JSON.",
                "Key:", "Title:", "Goal:", "Files:", "Tests:",
                "Protected:", "After:", "Role:", "Rules:"):
        assert old in plan.TEXT_SYSTEM
    # expected: both strings end with the appended METHOD sentence
    assert plan.SYSTEM.endswith(APPENDED)
    assert plan.TEXT_SYSTEM.endswith(APPENDED)


# ---------------------------------------------------------------------------
# 6. The existing rules section in SYSTEM is preserved.
# ---------------------------------------------------------------------------

def test_existing_rules_preserved_in_system():
    """The rules from "Tasks that write the same file" up to "Prefer 2 to 6 tasks for a feature."
    are still in SYSTEM."""
    # expected: the five rule sentences are present
    for rule in ("Tasks that write the same file must be chained",
                 "never make a task whose files are only test files",
                 "a task should be worth a model call and a review",
                 "takes the gateway as a parameter (gw)",
                 "Prefer 2 to 6 tasks for a feature."):
        assert rule in plan.SYSTEM
    # expected: "Prefer 2 to 6 tasks for a feature." appears before the appended sentence
    # so it is NOT the last text in SYSTEM
    assert plan.SYSTEM.index("Prefer 2 to 6 tasks for a feature.") < plan.SYSTEM.index("When a task holds an algorithm")


# ---------------------------------------------------------------------------
# 7. _RULES starts at "Tasks that write the same file" and includes the append.
# ---------------------------------------------------------------------------

def test_rules_starts_at_the_same_marker_and_includes_append():
    """_RULES (the substring of SYSTEM from "Tasks that write the same file" onward)
    must start at that marker and end with the appended sentence."""
    # _RULES is not exported, so recompute from SYSTEM
    rules = plan.SYSTEM[plan.SYSTEM.index("Tasks that write the same file"):]
    # expected: rules starts with the marker
    assert rules.startswith("Tasks that write the same file")
    # expected: rules ends with the appended sentence
    assert rules.endswith(APPENDED)


# ---------------------------------------------------------------------------
# 8. Key words from the appended sentence.
# ---------------------------------------------------------------------------

def test_key_words_present():
    """The appended sentence contains its key words."""
    for word in ("METHOD", "algorithm", "search", "schedule", "simulation",
                 "ordering", "tie-breaks"):
        # expected: each key word is in SYSTEM (which contains APPENDED)
        assert word in plan.SYSTEM


# ---------------------------------------------------------------------------
# 9. The METHOD line content words.
# ---------------------------------------------------------------------------

def test_method_line_phrases():
    """The appended sentence names the data kept, order things are tried in,
    what is skipped, and no code."""
    for phrase in ("data kept", "order things are tried in", "what is skipped", "no code"):
        # expected: each phrase appears in the appended text
        assert phrase in plan.SYSTEM


# ---------------------------------------------------------------------------
# 10. The sentence starts with a leading space.
# ---------------------------------------------------------------------------

def test_leading_space():
    """The appended sentence begins with a space (it follows "feature." directly)."""
    # expected: the space is between "feature." and "When a task"
    # In SYSTEM: ...feature. When a task holds...
    # The space is part of APPENDED.
    # expected: the character right after "feature." in SYSTEM is a space
    idx = plan.SYSTEM.index("Prefer 2 to 6 tasks for a feature.")
    after = plan.SYSTEM[idx + len("Prefer 2 to 6 tasks for a feature."):]
    # expected: after the original last rule, the append begins with " When a task"
    assert after == APPENDED


# ---------------------------------------------------------------------------
# 11. TEXT_SYSTEM structure preserved (plain text prompt lines).
# ---------------------------------------------------------------------------

def test_text_system_fields_preserved():
    """TEXT_SYSTEM still has the planner text-format fields."""
    for field in ("Key:", "Title:", "Goal:", "Files:", "Tests:",
                  "Protected:", "After:", "Role:"):
        # expected: every field label is in TEXT_SYSTEM
        assert field in plan.TEXT_SYSTEM
    # expected: the "plain text" / "no JSON" instruction is present
    assert "plain text" in plan.TEXT_SYSTEM
    assert "no JSON" in plan.TEXT_SYSTEM
    # expected: "Rules:" label is present before _RULES
    assert "Rules:" in plan.TEXT_SYSTEM


# ---------------------------------------------------------------------------
# 12. Append only, not inserted.
# ---------------------------------------------------------------------------

def test_append_is_not_in_the_middle_of_system():
    """The appended sentence is the last text in SYSTEM, not inserted mid-way."""
    # expected: SYSTEM's last 10 characters are inside APPENDED
    assert plan.SYSTEM[-10:] in APPENDED


# ---------------------------------------------------------------------------
# 13. Append is not in the middle of TEXT_SYSTEM.
# ---------------------------------------------------------------------------

def test_append_is_not_in_the_middle_of_text_system():
    """The appended sentence is the last text in TEXT_SYSTEM."""
    # expected: TEXT_SYSTEM's last 10 characters are inside APPENDED
    assert plan.TEXT_SYSTEM[-10:] in APPENDED


# ---------------------------------------------------------------------------
# 14. TEXT_SYSTEM prefix (before _RULES) is intact.
# ---------------------------------------------------------------------------

def test_text_system_prefix_preserved():
    """The part of TEXT_SYSTEM before the _RULES append is unchanged."""
    # The prefix ends at "Rules:\n"
    idx = plan.TEXT_SYSTEM.index("Rules:\n")
    prefix = plan.TEXT_SYSTEM[:idx]
    # expected: the prefix contains the text-format instructions
    assert "plain text" in prefix
    assert "Key:" in prefix
    # expected: the prefix does not contain the appended sentence
    assert APPENDED not in prefix


# ---------------------------------------------------------------------------
# 15. No code in the METHOD guidance.
# ---------------------------------------------------------------------------

def test_no_code_in_method_guidance():
    """The appended sentence says "no code" and contains no code syntax."""
    # expected: the sentence explicitly says no code
    assert "no code" in APPENDED
    # expected: no parentheses used for function calls (code markers)
    # The sentence uses parentheses for prose grouping, not code
    # Check: no "def ", "class ", "import ", "->", "()" (code signatures)
    for code_marker in ("def ", "class ", "import ", "->"):
        assert code_marker not in APPENDED
