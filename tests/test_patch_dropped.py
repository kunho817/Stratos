"""Tests for task T043: notice when an answer silently drops existing top-level definitions.

In T041 Tiel was asked to add a function at the end of stratos/report.py and twice wrote a file holding only the new
function: summarize and the others were gone, and the tests failed only on import errors.

patch.dropped_definitions(root, files, goal="") -> {path: [names]}
    files: [(path, content), ...] as parse_files returns them. For every path ending in ".py" whose file already
    exists under root: the names of the top-level functions (def, async def) and classes in the existing file that
    are not top-level definitions in the new content, sorted. A name the goal mentions as a whole word
    (\b<name>\b) is left out: the goal may ask to remove or rename it. Paths with nothing dropped, new files, non-.py
    files and files where either version does not parse (ast) are left out of the result.
"""
from stratos import patch

OLD = '''"""m"""
import json


def summarize(events):
    return 1


async def fetch():
    return 2


class Report:
    pass


def decision_accuracy(events):
    def inner():
        return 3
    return inner()
'''


def make(tmp_path, text=OLD, name="stratos/report.py"):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return tmp_path


def test_dropped_functions_and_classes(tmp_path):
    root = make(tmp_path)
    new = 'def decision_accuracy(events):\n    return 0\n\n\ndef escalation_accuracy(events):\n    return 1\n'
    assert patch.dropped_definitions(root, [("stratos/report.py", new)]) == {
        "stratos/report.py": ["Report", "fetch", "summarize"]}


def test_nothing_dropped(tmp_path):
    root = make(tmp_path)
    new = OLD + "\n\ndef escalation_accuracy(events):\n    return 1\n"
    assert patch.dropped_definitions(root, [("stratos/report.py", new)]) == {}


def test_nested_functions_do_not_count(tmp_path):
    root = make(tmp_path)
    new = OLD.replace("    def inner():\n        return 3\n    return inner()\n", "    return 3\n")
    assert patch.dropped_definitions(root, [("stratos/report.py", new)]) == {}


def test_names_in_the_goal_may_go(tmp_path):
    root = make(tmp_path)
    new = OLD.replace("class Report:\n    pass\n", "")
    assert patch.dropped_definitions(root, [("stratos/report.py", new)], goal="Remove the Report class.") == {}
    assert patch.dropped_definitions(root, [("stratos/report.py", new)], goal="Reports are fine.") == {
        "stratos/report.py": ["Report"]}


def test_new_files_other_files_and_broken_code_are_skipped(tmp_path):
    root = make(tmp_path)
    make(tmp_path, "x: 1\n", "notes.md")
    files = [("stratos/new.py", "def f():\n    pass\n"), ("notes.md", ""),
             ("stratos/report.py", "def (:\n")]
    assert patch.dropped_definitions(root, files) == {}
    make(tmp_path, "def (:\n", "stratos/broken.py")
    assert patch.dropped_definitions(root, [("stratos/broken.py", "x = 1\n")]) == {}


# T046: a name the goal merely mentions ("count the same way as decision_accuracy", "leave summarize unchanged") must
# still be kept. A dropped name is excused only when it appears in a sentence of the goal that also holds a removal
# word: one of patch.REMOVAL_WORDS. Sentences are split at '.', '!', '?' and line breaks. Latin removal words match
# as whole words, case-insensitive; Korean ones match anywhere in the sentence. The name itself matches as a whole word.

def test_a_mere_mention_does_not_excuse_a_drop(tmp_path):
    root = make(tmp_path)
    new = OLD.replace("class Report:\n    pass\n", "")
    dropped = {"stratos/report.py": ["Report"]}
    assert patch.dropped_definitions(root, [("stratos/report.py", new)], goal="Count it the way Report does.") == dropped
    assert patch.dropped_definitions(root, [("stratos/report.py", new)],
                                     goal="Leave Report unchanged. Remove the old helper.") == dropped
    assert patch.dropped_definitions(root, [("stratos/report.py", new)], goal="Rename Report to Summary.") == {}
    assert patch.dropped_definitions(root, [("stratos/report.py", new)], goal="Report 클래스를 삭제한다.") == {}
    assert patch.dropped_definitions(root, [("stratos/report.py", new)], goal="First this.\nDelete Report.") == {}


def test_removal_words():
    for w in ("remove", "delete", "drop", "rename", "replace", "삭제", "제거"):
        assert w in patch.REMOVAL_WORDS
