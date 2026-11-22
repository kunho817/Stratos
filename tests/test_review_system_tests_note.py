"""Tests for task review_system_tests_note: REVIEW_SYSTEM gets the sentence
" The task's tests were written before the code and are not part of the diff: never report missing, unchanged
or unwritten tests." appended to its end. The rest of REVIEW_SYSTEM stays as it is.

The appended sentence tells the reviewer that the task's tests pre-date the code and are not in the diff, so
it must never report a test as missing, unchanged, or unwritten.
"""
from stratos import review

# The exact sentence to be appended (with the leading space that joins it to the previous sentence).
SENTENCE = (" The task's tests were written before the code and are not part of the diff: "
            "never report missing, unchanged or unwritten tests.")

# Key fragments that must survive the append (taken from the current REVIEW_SYSTEM at run time).
ORIGINAL_TAIL = "An issue whose quote is not a line of the diff or of the whole changed files does not count."


def test_the_sentence_is_in_review_system():
    # After the task, SENTENCE is a substring of REVIEW_SYSTEM.
    # Before the task it is absent, so this fails.
    assert SENTENCE in review.REVIEW_SYSTEM


def test_the_sentence_is_at_the_end():
    # The sentence is appended to the end, so REVIEW_SYSTEM ends with it.
    # Expected: REVIEW_SYSTEM.rstrip() == ... + SENTENCE.strip() → endswith SENTENCE.lstrip()
    assert review.REVIEW_SYSTEM.rstrip().endswith(SENTENCE.strip())


def test_sentence_follows_the_previous_sentence():
    # The original last sentence "…does not count." is immediately before the appended one.
    # The join: "…does not count. The task's tests…" (one space between).
    idx = review.REVIEW_SYSTEM.index(SENTENCE.strip())
    # character just before SENTENCE.strip() is the space that joins them
    assert review.REVIEW_SYSTEM[idx - 1] == " "
    # the text just before that space ends with "does not count."
    assert review.REVIEW_SYSTEM[idx - len(SENTENCE.strip()) - 1:idx - 1].endswith("does not count.")


def test_rest_of_review_system_unchanged_before_the_append():
    # The part before the appended sentence must be exactly the original REVIEW_SYSTEM.
    # The original ends with ORIGINAL_TAIL; the new text is original + SENTENCE.
    # Take the portion of REVIEW_SYSTEM up to and including ORIGINAL_TAIL.
    # That portion must equal the original REVIEW_SYSTEM (verified by checking key markers).
    head = review.REVIEW_SYSTEM[:len(review.REVIEW_SYSTEM) - len(SENTENCE)]
    # head must end with the original tail
    assert head.endswith(ORIGINAL_TAIL)
    # spot-check: key phrases from the original are all present in head
    for phrase in ("Check every changed line against the goal.",
                   "Use approve when there are no high or medium issues.",
                   'is ALWAYS medium, even when it looks small or harmless, never low'):
        assert phrase in head


def test_build_messages_system_prompt_has_the_sentence():
    # build_messages returns [system, user]; system content == REVIEW_SYSTEM.
    # So the sentence must appear in the system message.
    msgs = review.build_messages({"id": "T1", "title": "t", "goal": "g"}, "+x = 1")
    system = msgs[0]["content"]
    assert SENTENCE in system


def test_build_messages_rest_of_system_unchanged():
    # The system prompt in build_messages must still contain the original key sentences.
    msgs = review.build_messages({"id": "T1", "title": "t", "goal": "g"}, "+x = 1")
    system = msgs[0]["content"]
    for phrase in ("Check every changed line against the goal.",
                   "Use approve when there are no high or medium issues."):
        assert phrase in system


def test_sentence_mentions_missing_tests():
    # The sentence explicitly says "never report missing" tests.
    assert "never report missing" in review.REVIEW_SYSTEM


def test_sentence_mentions_unchanged_tests():
    # The sentence says "unchanged" as well.
    assert "unchanged" in review.REVIEW_SYSTEM


def test_sentence_mentions_unwritten_tests():
    # The sentence says "unwritten" tests.
    assert "unwritten" in review.REVIEW_SYSTEM


def test_sentence_is_not_in_the_user_message():
    # The sentence belongs to the system prompt, not the user content.
    msgs = review.build_messages({"id": "T1", "title": "t", "goal": "g"}, "+x = 1")
    user = msgs[1]["content"]
    assert SENTENCE.strip() not in user


def test_parse_still_works_after_the_change():
    # parse must keep working: the appended sentence does not affect parsing.
    r = review.parse('{"verdict": "approve", "issues": []}')
    assert r == {"verdict": "approve", "issues": []}


def test_is_blocking_still_works_after_the_change():
    # is_blocking logic is unaffected.
    issue = {"severity": "high", "file": "a.py", "problem": "p", "quote": "x"}
    assert review.is_blocking({"issues": [issue]}) is True


def test_format_issues_still_works_after_the_change():
    r = {"issues": [{"severity": "high", "file": "a.py", "problem": "p", "quote": "x"}]}
    assert review.format_issues(r) == "- [high] a.py: p"
