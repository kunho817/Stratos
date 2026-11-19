"""Tests for task drafts_blocks: shorter test drafts, and a header-less answer in several fenced blocks (trial 4).

Orbit (2026-11-19): the game draft was 1,285 lines with 37 tests and hit the length limit (cut in the middle of a
test, dropped as "missing"); the main draft came without a FILE header in two ```python blocks - the imports alone,
then the whole file again - and was dropped too.

plantests.system_prompt(language, test_runner) also says "At most 15 tests per file, one per behaviour; keep each
file under 300 lines."

draft_tests: when the answer has no FILE header and exactly one test file of the task is still to write, and the
answer is not a lone fenced block: when it has two or more fenced blocks (``` lines that open and close), the inner
text of the longest one (most characters; the first of equal ones) is that file. Otherwise as before (an answer that
does not start with a fence is the file itself)."""
from stratos import config, plan, plantests

TASK = {"key": "main", "title": "Main", "goal": "Loop.", "files": ["src/main.js"], "tests": ["tests/main.test.js"],
        "protected": [], "after": [], "role": None}


def test_system_prompt_limits_size():
    text = plantests.system_prompt("javascript", "node --test")
    assert "At most 15 tests per file, one per behaviour; keep each file under 300 lines." in text


class FakeTelemetry:
    def record(self, kind, **fields):
        pass


class FakeGateway:
    def __init__(self, answer):
        self.telemetry = FakeTelemetry()
        self.answer = answer

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        return "c", self.answer


def run(tmp_path, monkeypatch, answer):
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    state = tmp_path / "state"
    monkeypatch.setattr(config, "PLANNER", {"model": "m", "effort": "low", "max_tokens": 100})
    monkeypatch.setattr(plantests, "check_draft", lambda root, path: ("collected", ""))
    pid = plan.save_plan(state, "G", [TASK])
    plantests.draft_tests(FakeGateway(answer), pid, root, state, log=lambda s: None)
    path = root / "tests" / "main.test.js"
    return path.read_text(encoding="utf-8") if path.exists() else None


def test_the_longest_block_is_the_file(tmp_path, monkeypatch):
    whole = 'import { test } from "node:test";\n\ntest("a", () => {});\ntest("b", () => {});\n'
    answer = '```python\nimport { test } from "node:test";\n```\n\nThen the tests:\n\n```python\n' + whole + "```\n"
    assert run(tmp_path, monkeypatch, answer) == whole


def test_a_lone_block_still_works(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, '```js\ntest("a", () => {});\n```\n') == 'test("a", () => {});\n'
