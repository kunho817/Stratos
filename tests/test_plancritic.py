r"""Tests for task plancritic (P3, 2026-11-20): a second model reviews a plan before the tests are drafted.
Experiment (b) (scratchpad critique_eval.py): on the planner's original plans of Lumen and Pantry (12 problems Claude
fixed by hand, 2 runs each), Flint named 17 of 24, Tiel 12, Swift 9, Qwen3.6 8; Flint's extra lines were mostly real
too (argparse exits 2, not 1, on "abc"). Advisory: the problems are shown to the person who edits the plan.

plancritic.SYSTEM: the experiment's prompt; it contains "PROBLEM: <task key> | <one sentence>" and names: a file no
task writes, a missing After, data shapes no goal defines, a parameter that makes no sense, a pure module that prints,
a rule of the feature goal no task covers, an input that would crash.

plancritic.plan_text(tasks) -> one block per task joined by "\n\n": f"Key: {key}\nTitle: {title}\nFiles: {files
joined by ', '}\nTests: {tests joined by ', '}\nAfter: {after joined by ', ' or 'none'}\nGoal: {goal}".

plancritic.build_messages(goal, conventions, tasks) -> [system SYSTEM, user]: the user message is
f"FEATURE GOAL:\n{goal}\n\nPROJECT CONVENTIONS:\n{conventions}\n\nPLAN:\n{plan_text(tasks)}"; without conventions
(None or "") the PROJECT CONVENTIONS part is left out.

plancritic.parse(answer) -> [{"task": key, "problem": text}] for each line matching
r"^\s*PROBLEM:\s*(.+?)\s*\|\s*(.+)$" (key and text stripped), in order; duplicates (same key and text) once.

plancritic.critique(gw, goal, root, tasks) -> parse(answer): conventions from root/CONVENTIONS.md when it exists;
gw.ensure_model(config.PLAN_CRITIC["model"]); gw.chat(build_messages(...), task="plan", role="plan_critic", attempt=1,
model=..., effort=..., max_tokens=...).
config.PLAN_CRITIC = {"model": "flint-40b-a2.5b-ud-q4_k_xl", "effort": "low", "max_tokens": 12000}."""
from stratos import config, plancritic

TASKS = [
    {"key": "units", "title": "Units", "goal": "Write convert(amount, a, b, gw).", "files": ["pantry/units.py"],
     "tests": ["tests/test_units.py"], "after": []},
    {"key": "cli", "title": "CLI", "goal": "Wire the commands.", "files": ["pantry/cli.py", "pantry/x.py"],
     "tests": ["tests/test_cli.py"], "after": ["units"]},
]


def test_system_prompt():
    assert "PROBLEM: <task key> | <one sentence>" in plancritic.SYSTEM
    for words in ("After", "shape", "print"):
        assert words in plancritic.SYSTEM


def test_plan_text():
    assert plancritic.plan_text(TASKS) == (
        "Key: units\nTitle: Units\nFiles: pantry/units.py\nTests: tests/test_units.py\nAfter: none\n"
        "Goal: Write convert(amount, a, b, gw).\n\n"
        "Key: cli\nTitle: CLI\nFiles: pantry/cli.py, pantry/x.py\nTests: tests/test_cli.py\nAfter: units\n"
        "Goal: Wire the commands.")


def test_build_messages():
    msgs = plancritic.build_messages("Build Pantry.", "## Layout\n- pure", TASKS)
    assert msgs[0] == {"role": "system", "content": plancritic.SYSTEM}
    assert msgs[1]["content"] == ("FEATURE GOAL:\nBuild Pantry.\n\nPROJECT CONVENTIONS:\n## Layout\n- pure\n\nPLAN:\n"
                                  + plancritic.plan_text(TASKS))
    assert "PROJECT CONVENTIONS" not in plancritic.build_messages("G", None, TASKS)[1]["content"]
    assert "PROJECT CONVENTIONS" not in plancritic.build_messages("G", "", TASKS)[1]["content"]


def test_parse():
    answer = "\n".join(["Here are the problems:", "PROBLEM: units | convert has a parameter gw that makes no sense.",
                        "", "  PROBLEM: cli |  No task writes pantry/__main__.py.  ",
                        "PROBLEM: units | convert has a parameter gw that makes no sense.", "PROBLEM: no bar here"])
    assert plancritic.parse(answer) == [
        {"task": "units", "problem": "convert has a parameter gw that makes no sense."},
        {"task": "cli", "problem": "No task writes pantry/__main__.py."},
    ]
    assert plancritic.parse("") == []


def test_critique(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLAN_CRITIC", {"model": "m-crit", "effort": "low", "max_tokens": 50})
    (tmp_path / "CONVENTIONS.md").write_text("pure modules", encoding="utf-8")
    seen = []

    class GW:
        def ensure_model(self, model):
            seen.append(model)
            return 0.0

        def chat(self, messages, **kw):
            seen.append((messages[1]["content"], kw))
            return "c1", "PROBLEM: cli | x"
    assert plancritic.critique(GW(), "Goal.", tmp_path, TASKS) == [{"task": "cli", "problem": "x"}]
    assert seen[0] == "m-crit"
    content, kw = seen[1]
    assert "PROJECT CONVENTIONS:\npure modules" in content
    assert kw == {"task": "plan", "role": "plan_critic", "attempt": 1, "model": "m-crit", "effort": "low",
                  "max_tokens": 50}


def test_default_critic():
    assert config.PLAN_CRITIC["model"] == "flint-40b-a2.5b-ud-q4_k_xl"
