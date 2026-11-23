"""Tests for task t19_monkeypatch: the monkeypatch guidance sentence is appended to TEST_SYSTEM in
stratos/plantests.py. The appended text is " monkeypatch.setattr takes an object, the attribute name
and the value, or one \"module.attribute\" string and the value; to give a program a file, write a real
file in tmp_path instead of faking open." (with the leading space). Only append; existing content
of TEST_SYSTEM is unchanged. system_prompt() itself does NOT gain the sentence (only TEST_SYSTEM does).
"""

from stratos import config, plantests

APPENDED = (' monkeypatch.setattr takes an object, the attribute name and the value, '
            'or one "module.attribute" string and the value; to give a program a file, '
            'write a real file in tmp_path instead of faking open.')


# ---------------------------------------------------------------------------
# 1. TEST_SYSTEM contains the appended sentence.
# ---------------------------------------------------------------------------

def test_test_system_contains_appended_sentence():
    """TEST_SYSTEM must include the exact monkeypatch guidance sentence."""
    # expected: APPENDED is a substring of TEST_SYSTEM
    assert APPENDED in plantests.TEST_SYSTEM


# ---------------------------------------------------------------------------
# 2. The appended sentence is at the very end of TEST_SYSTEM.
# ---------------------------------------------------------------------------

def test_appended_at_the_end():
    """The appended sentence comes at the end of TEST_SYSTEM."""
    # expected: TEST_SYSTEM ends with APPENDED
    assert plantests.TEST_SYSTEM.endswith(APPENDED)


# ---------------------------------------------------------------------------
# 3. The existing content is preserved (everything before the append).
# ---------------------------------------------------------------------------

def test_existing_content_preserved():
    """The original system_prompt result (before the append) is the prefix of TEST_SYSTEM."""
    base = plantests.system_prompt(config.PROJECT["language"], config.PROJECT["test_runner"])
    # expected: base is a prefix of TEST_SYSTEM (the append adds only the new sentence)
    assert plantests.TEST_SYSTEM.startswith(base)
    # expected: the part after the base is exactly APPENDED
    assert plantests.TEST_SYSTEM[len(base):] == APPENDED


# ---------------------------------------------------------------------------
# 4. system_prompt itself does NOT contain the appended sentence.
# ---------------------------------------------------------------------------

def test_system_prompt_does_not_have_appended():
    """system_prompt(language, test_runner) returns the base prompt without the append."""
    py = plantests.system_prompt("python", "pytest")
    # expected: the monkeypatch guidance is NOT in the function's return value
    assert APPENDED not in py


# ---------------------------------------------------------------------------
# 5. The existing keywords in TEST_SYSTEM are unchanged.
# ---------------------------------------------------------------------------

def test_existing_keywords_preserved():
    """The words that were in TEST_SYSTEM before the append are still present."""
    # expected: the core prompt words remain
    for word in ("pytest", "FILE", "docstring", "monkeypatch", "tmp_path", "faking"):
        assert word in plantests.TEST_SYSTEM


# ---------------------------------------------------------------------------
# 6. TEST_SYSTEM mentions monkeypatch.setattr and tmp_path.
# ---------------------------------------------------------------------------

def test_mentions_monkeypatch_setattr_and_tmp_path():
    """The appended sentence names monkeypatch.setattr and tmp_path."""
    # expected: "monkeypatch.setattr" appears
    assert "monkeypatch.setattr" in plantests.TEST_SYSTEM
    # expected: "tmp_path" appears
    assert "tmp_path" in plantests.TEST_SYSTEM
    # expected: "faking open" appears (the warning about faking open)
    assert "faking open" in plantests.TEST_SYSTEM


# ---------------------------------------------------------------------------
# 7. The string "module.attribute" is present in the appended text.
# ---------------------------------------------------------------------------

def test_module_attribute_string():
    """The appended sentence quotes the string form "module.attribute"."""
    # expected: the phrase one "module.attribute" string is in TEST_SYSTEM
    assert 'one "module.attribute" string' in plantests.TEST_SYSTEM
