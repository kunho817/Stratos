"""Tests for the old-test budget of the test writer's prompt (Claude, 2026-11-22, the delegation experiment's
exception: Stratos could not draft tests at all for tasks that change stratos/__main__.py or config.py).

plantests.build_messages shows the full text of every old test that imports a changed file: 42 files (~69k tokens)
for __main__.py, so the prompt went over Swift's context (HTTP 400) - also for the task that was to fix it.

config.OLD_TESTS_CHARS = 48000. build_messages(task, root, ..., old=...): when the text of all old tests (that
exist) fits within config.OLD_TESTS_CHARS, they are shown exactly as before, in the given order. Otherwise they are
ordered by how many of the goal's names they use (most first, ties by path), and shown in full while the running
total of their text stays within the budget; every other one becomes one line:
  "OLD TEST <path> (not shown, <n> lines; uses: <names, comma separated>)" - or "uses: none of the goal's names".
The goal's names: names defined at the top level of the task's changed files (Python def/class/NAME =, JavaScript
export function/class/const) that appear as whole words in the task's goal - plantests.goal_names(root, task),
sorted."""
from stratos import config, plantests


def setup(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("LIMIT = 3\n\n\ndef alpha():\n    pass\n\n\nclass Beta:\n    pass\n\n\n"
                                           "def gamma():\n    pass\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    texts = {"tests/test_a.py": "from pkg.m import alpha\nalpha()\n" + "# pad\n" * 40,
             "tests/test_b.py": "from pkg.m import alpha, Beta\nalpha(); Beta()\n" + "# pad\n" * 40,
             "tests/test_c.py": "from pkg.m import gamma\ngamma()\n" + "# pad\n" * 40}
    for p, t in texts.items():
        (tmp_path / p).write_text(t, encoding="utf-8")
    task = {"key": "k", "title": "t", "goal": "Change alpha and Beta; LIMIT stays.", "files": ["pkg/m.py"],
            "tests": ["tests/test_new.py"], "protected": []}
    return task, list(texts)


def prompt(task, root, old):
    return plantests.build_messages(task, root, old=old)[1]["content"]


def test_goal_names(tmp_path):
    task, _ = setup(tmp_path)
    assert plantests.goal_names(tmp_path, task) == ["Beta", "LIMIT", "alpha"]


def test_everything_fits_as_before(tmp_path, monkeypatch):
    task, old = setup(tmp_path)
    monkeypatch.setattr(config, "OLD_TESTS_CHARS", 10_000)
    text = prompt(task, tmp_path, old)
    assert "not shown" not in text
    assert text.index("tests/test_a.py") < text.index("tests/test_b.py") < text.index("tests/test_c.py")


def test_over_the_budget_the_most_relevant_are_shown(tmp_path, monkeypatch):
    task, old = setup(tmp_path)
    one = len((tmp_path / "tests" / "test_b.py").read_text(encoding="utf-8"))
    monkeypatch.setattr(config, "OLD_TESTS_CHARS", one + 10)     # room for one file
    text = prompt(task, tmp_path, old)
    assert "# pad" in text and "alpha(); Beta()" in text                     # test_b uses 2 of the names: shown
    assert "OLD TEST tests/test_a.py (not shown, 42 lines; uses: alpha)" in text
    assert "OLD TEST tests/test_c.py (not shown, 42 lines; uses: none of the goal's names)" in text
    assert "from pkg.m import gamma" not in text and "from pkg.m import alpha\nalpha()" not in text


def test_the_default_budget():
    assert config.OLD_TESTS_CHARS == 48000
