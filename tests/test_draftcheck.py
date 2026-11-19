r"""Tests for task draftcheck (P2, 2026-11-20): stratos/draftcheck.py asks a model to point at drafted tests that are
wrong before any code is written. Experiment (a) (BACKLOG P2): with this prompt Swift found 13 of 20 known wrong
tests with 1-3 false alarms in 108; on fresh drafts it lacked the other tasks' goals (a false alarm in Lumen's
main), so the whole plan is shown.

draftcheck.SYSTEM: a system prompt that contains "WRONG: <the test's name exactly as written> | <one-sentence
reason>" and "NONE" (the answer format), and names the kinds of wrong tests: miscalculated expected values, a test
that contradicts the goal or itself, an impossible setup, invented data or rules, state left by another test or
time that does not pass.

draftcheck.test_names(text, path) -> the test names in the draft, in order: for a path ending ".py" the names of
`def test_<x>(` (also indented, for methods); otherwise the string of each `test("<name>"` / `test('<name>'` /
test(`<name>` at the start of a line (after indentation).

draftcheck.build_messages(plan, task, root, draft) -> [{"role": "system", "content": SYSTEM}, {"role": "user", ...}]:
the user message holds, in this order: "GOAL OF THE TASK THESE TESTS ARE FOR:\n" + task["goal"]; when the plan has
other tasks, "OTHER TASKS OF THIS PLAN:" followed by one f"{key}: {title}\n{goal}" entry per other task (plan order);
each file of task["files"] and each of task["protected"] that is not one of task["tests"], when it exists under root,
as context.show_file(root, path, "PROJECT FILE"); and last f"DRAFTED TEST FILE {path}:\n```\n{draft}\n```" for the
task's first test path.

draftcheck.parse(answer, names) -> list of {"test": name, "reason": reason}: one per line matching
r"^\s*WRONG:\s*(.+?)\s*\|\s*(.*)$"; the name (quotes and backticks stripped) must equal one of names, else the first
of names that contains it or that it contains; names that match nothing are dropped (the model invented them); a
name only once (the first line wins); "NONE" or no lines -> [].

draftcheck.check(gw, plan_id, plan, task, root, path) -> the flags: reads the draft at root/path,
gw.ensure_model(config.DRAFT_CHECKER["model"]), gw.chat(build_messages(...), task=f"{plan_id}-{task['key']}",
role="draft_checker", attempt=1, model=..., effort=..., max_tokens=..., and reasoning_budget=... only when
config.DRAFT_CHECKER has one), and returns parse(answer, test_names(draft, path)).
config.DRAFT_CHECKER = {"model": "swift-1.5-iq2_xs", "effort": "low", "max_tokens": 12000} (the drafts are written by
the same model, so no switch)."""
from stratos import config, draftcheck

JS = '''// draft
import { test } from "node:test";
test("adds two numbers", () => {});
  test('nested name', () => {});
test(`template name`, () => {});
const x = test("not at line start");
'''

PY = '''def test_a():
    pass


class TestB:
    def test_b(self):
        pass


def helper_test_c():
    pass
'''

PLAN = {"id": "P001", "tasks": [
    {"key": "levels", "title": "Level data", "goal": "Write levels.js with 4 levels.", "files": ["src/levels.js"],
     "tests": ["tests/levels.test.js"], "protected": ["tests/levels.test.js"]},
    {"key": "game", "title": "Game state", "goal": "Write game.js with cycleMirror.", "files": ["src/game.js"],
     "tests": ["tests/game.test.js"], "protected": ["tests/game.test.js", "src/grid.js"]},
]}


def test_system_prompt():
    assert "WRONG: <the test's name exactly as written> | <one-sentence reason>" in draftcheck.SYSTEM
    assert "NONE" in draftcheck.SYSTEM


def test_test_names():
    assert draftcheck.test_names(JS, "tests/a.test.js") == ["adds two numbers", "nested name", "template name"]
    assert draftcheck.test_names(PY, "tests/test_a.py") == ["test_a", "test_b"]


def test_build_messages(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "grid.js").write_text("export const G = 1;\n", encoding="utf-8")
    task = PLAN["tasks"][1]
    msgs = draftcheck.build_messages(PLAN, task, tmp_path, 'test("x", () => {});')
    assert msgs[0] == {"role": "system", "content": draftcheck.SYSTEM}
    user = msgs[1]["content"]
    goal = user.index("GOAL OF THE TASK THESE TESTS ARE FOR:\nWrite game.js with cycleMirror.")
    other = user.index("OTHER TASKS OF THIS PLAN:")
    level = user.index("levels: Level data\nWrite levels.js with 4 levels.")
    grid = user.index("PROJECT FILE: src/grid.js")
    draft = user.index('DRAFTED TEST FILE tests/game.test.js:\n```\ntest("x", () => {});\n```')
    assert goal < other < level < grid < draft
    assert "src/game.js" not in user  # the task's own file does not exist yet: not shown
    assert "game: Game state" not in user  # its own task is not an "other" task


def test_parse():
    names = ["adds two numbers", "level 2: three targets", "nested name"]
    answer = "\n".join([
        "Looking at the tests:",
        "WRONG: adds two numbers | 2 + 2 is 4, not 5",
        "WRONG: \"level 2\" | invents level data",
        "WRONG: something invented | no such test",
        "WRONG: adds two numbers | again",
        "  WRONG: `nested name` |   depends on the previous test",
    ])
    assert draftcheck.parse(answer, names) == [
        {"test": "adds two numbers", "reason": "2 + 2 is 4, not 5"},
        {"test": "level 2: three targets", "reason": "invents level data"},
        {"test": "nested name", "reason": "depends on the previous test"},
    ]
    assert draftcheck.parse("NONE", names) == []
    assert draftcheck.parse("", names) == []


class FakeGateway:
    def __init__(self, answer):
        self.answer = answer
        self.loaded = []
        self.calls = []

    def ensure_model(self, model):
        self.loaded.append(model)
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        return "c1", self.answer


def test_check(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DRAFT_CHECKER", {"model": "m-check", "effort": "low", "max_tokens": 100})
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "game.test.js").write_text(JS, encoding="utf-8")
    gw = FakeGateway("WRONG: nested name | shares state\nWRONG: made up | x")
    flags = draftcheck.check(gw, "P001", PLAN, PLAN["tasks"][1], tmp_path, "tests/game.test.js")
    assert flags == [{"test": "nested name", "reason": "shares state"}]
    assert gw.loaded == ["m-check"]
    (messages, kw), = gw.calls
    assert kw == {"task": "P001-game", "role": "draft_checker", "attempt": 1, "model": "m-check", "effort": "low",
                  "max_tokens": 100}
    assert "DRAFTED TEST FILE tests/game.test.js" in messages[1]["content"]
    monkeypatch.setattr(config, "DRAFT_CHECKER", {"model": "m", "effort": "low", "max_tokens": 1, "reasoning_budget": 9})
    draftcheck.check(gw, "P001", PLAN, PLAN["tasks"][1], tmp_path, "tests/game.test.js")
    assert gw.calls[-1][1]["reasoning_budget"] == 9


def test_default_checker():
    assert config.DRAFT_CHECKER["model"] == config.PLANNER["model"]
