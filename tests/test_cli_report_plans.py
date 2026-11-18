"""Tests for report --plans (plan P006, task report-plans-cli): the `report` subcommand gains a --plans flag that prints a
one-line summary per plan file in .stratos/plans/, sorted by id.

Format per plan:
  PLAN <id> | tasks <n> | <status> | <edited> | drafts: collected <n>, import_error <n>,
  syntax_error <n>, error <n>, exists <n>, missing <n>

- <status> comes from the plan file; <edited> from report.plans_summary (the telemetry "plan" events).
- Draft counts come from telemetry events of kind "test_draft" for that plan id.
- If no plan files exist, print "no plans yet".
- The usage docstring at the top of __main__.py must include the new flag line.
"""

import json
import pytest

from stratos import __main__ as cli
from stratos import config
from stratos.telemetry import Telemetry


def _write_plan(state_dir, pid, goal, tasks, status="draft", plan_hash="abc123"):
    plans_dir = state_dir / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    content = {
        "id": pid,
        "goal": goal,
        "tasks": tasks,
        "status": status,
        "hash": plan_hash,
    }
    (plans_dir / f"{pid}.json").write_text(json.dumps(content), encoding="utf-8")
    return content


def _make_task(key, title, goal, files, tests, protected=None, after=None, role="coder"):
    t = {"key": key, "title": title, "goal": goal, "files": files, "tests": tests,
         "protected": protected or [], "after": after or [], "role": role}
    return t


def _write_telemetry_events(state_dir, events):
    """Write events as JSONL lines (append mode style)."""
    tel_path = state_dir / "telemetry.jsonl"
    tel_path.parent.mkdir(parents=True, exist_ok=True)
    with tel_path.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


@pytest.fixture(autouse=True)
def tmp_state(monkeypatch, tmp_path):
    state = tmp_path / ".stratos"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr(config, "REPO", tmp_path)
    return state


def test_report_plans_no_plans_yet(tmp_state, capsys):
    """When plans/ is empty or does not exist, print 'no plans yet'."""
    rc = cli.main(["report", "--plans"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no plans yet" in out


def test_report_plans_single_plan(tmp_state, capsys):
    """One plan file produces one line in the expected format."""
    tasks = [_make_task("a", "Write foo", "add foo", ["stratos/foo.py"], ["tests/test_foo.py"])]
    _write_plan(tmp_state, "P001", "add foo", tasks, status="draft", plan_hash="hash_aaa")
    # no test_draft events
    _write_telemetry_events(tmp_state, [])

    rc = cli.main(["report", "--plans"])
    assert rc == 0
    out = capsys.readouterr().out
    line = out.strip().splitlines()[0]
    assert line.startswith("PLAN P001")
    assert "tasks 1" in line
    assert "draft" in line
    assert "False" in line  # not edited
    assert "collected 0" in line


def test_report_plans_sorted_by_id(tmp_state, capsys):
    """Multiple plans are printed sorted by id."""
    tasks1 = [_make_task("a", "T1", "g", ["x.py"], ["tests/x.py"])]
    tasks2 = [_make_task("a", "T1", "g", ["y.py"], ["tests/y.py"]),
              _make_task("b", "T2", "g", ["z.py"], ["tests/z.py"])]
    _write_plan(tmp_state, "P002", "g2", tasks2, status="added", plan_hash="h2")
    _write_plan(tmp_state, "P001", "g1", tasks1, status="draft", plan_hash="h1")
    _write_telemetry_events(tmp_state, [])

    rc = cli.main(["report", "--plans"])
    assert rc == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("PLAN P001")
    assert lines[1].startswith("PLAN P002")
    assert "tasks 2" in lines[1]
    assert "added" in lines[1]


def test_report_plans_edited(tmp_state, capsys):
    """A plan whose "plan" telemetry event says edited shows True."""
    tasks = [_make_task("a", "T", "g", ["x.py"], ["tests/x.py"])]
    _write_plan(tmp_state, "P001", "g", tasks, status="added", plan_hash="h")
    _write_telemetry_events(tmp_state, [{"ts": 1, "kind": "plan", "plan": "P001", "tasks": 1, "edited": True}])

    rc = cli.main(["report", "--plans"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.split(" | ")[3] == "True"


def test_report_plans_not_edited(tmp_state, capsys):
    """Without an edited "plan" event the plan shows False, whatever its stored hash says."""
    tasks = [_make_task("a", "T", "g", ["x.py"], ["tests/x.py"])]
    _write_plan(tmp_state, "P001", "g", tasks, status="draft", plan_hash="not_the_real_hash")
    _write_telemetry_events(tmp_state, [{"ts": 1, "kind": "plan", "plan": "P001", "tasks": 1, "edited": False}])

    rc = cli.main(["report", "--plans"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.split(" | ")[3] == "False"
    assert "True" not in out


def test_report_plans_draft_counts(tmp_state, capsys):
    """test_draft telemetry events are counted per plan and printed in the draft summary."""
    tasks = [_make_task("a", "T1", "g", ["x.py"], ["tests/x.py"])]
    _write_plan(tmp_state, "P001", "g", tasks, status="added", plan_hash="h")

    events = [
        {"ts": 1, "kind": "test_draft", "plan": "P001", "key": "a",
         "file": "tests/test_x.py", "status": "collected"},
        {"ts": 2, "kind": "test_draft", "plan": "P001", "key": "a",
         "file": "tests/test_x.py", "status": "import_error"},
        {"ts": 3, "kind": "test_draft", "plan": "P001", "key": "a",
         "file": "tests/test_x.py", "status": "collected"},
        {"ts": 4, "kind": "test_draft", "plan": "P001", "key": "a",
         "file": "tests/test_y.py", "status": "missing"},
        {"ts": 5, "kind": "test_draft", "plan": "P001", "key": "a",
         "file": "tests/test_z.py", "status": "exists"},
        {"ts": 6, "kind": "test_draft", "plan": "P001", "key": "a",
         "file": "tests/test_w.py", "status": "syntax_error"},
        {"ts": 7, "kind": "test_draft", "plan": "P001", "key": "a",
         "file": "tests/test_v.py", "status": "error"},
    ]
    _write_telemetry_events(tmp_state, events)

    rc = cli.main(["report", "--plans"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert "collected 2" in out
    assert "import_error 1" in out
    assert "syntax_error 1" in out
    assert "error 1" in out
    assert "exists 1" in out
    assert "missing 1" in out
    assert "PLAN P001" in out


def test_report_plans_drafts_only_own_plan(tmp_state, capsys):
    """Draft events for a different plan are not counted for this plan."""
    tasks = [_make_task("a", "T", "g", ["x.py"], ["tests/x.py"])]
    _write_plan(tmp_state, "P001", "g", tasks, status="draft", plan_hash="h")

    events = [
        {"ts": 1, "kind": "test_draft", "plan": "P002", "key": "a",
         "file": "tests/y.py", "status": "collected"},
    ]
    _write_telemetry_events(tmp_state, events)

    rc = cli.main(["report", "--plans"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert "collected 0" in out


def test_report_plans_format_line(tmp_state, capsys):
    """The full output line matches the required format exactly."""
    tasks = [
        _make_task("a", "T1", "g", ["x.py"], ["tests/x.py"]),
        _make_task("b", "T2", "g", ["y.py"], ["tests/y.py"]),
        _make_task("c", "T3", "g", ["z.py"], ["tests/z.py"]),
    ]
    _write_plan(tmp_state, "P003", "goal", tasks, status="added", plan_hash="h")
    events = [
        {"ts": 1, "kind": "test_draft", "plan": "P003", "key": "a",
         "file": "tests/test_a.py", "status": "collected"},
        {"ts": 2, "kind": "test_draft", "plan": "P003", "key": "b",
         "file": "tests/test_b.py", "status": "exists"},
        {"ts": 3, "kind": "test_draft", "plan": "P003", "key": "c",
         "file": "tests/test_c.py", "status": "missing"},
    ]
    _write_telemetry_events(tmp_state, events)

    rc = cli.main(["report", "--plans"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    line = out.splitlines()[0]
    # PLAN P003 | tasks 3 | added | False | drafts: collected 1, import_error 0,
    # syntax_error 0, error 0, exists 1, missing 1
    parts = line.split(" | ")
    assert parts[0] == "PLAN P003"
    assert parts[1] == "tasks 3"
    assert parts[2] == "added"
    assert parts[3] == "False"
    assert parts[4].startswith("drafts:")
    assert "collected 1" in parts[4]
    assert "import_error 0" in parts[4]
    assert "syntax_error 0" in parts[4]
    assert "error 0" in parts[4]
    assert "exists 1" in parts[4]
    assert "missing 1" in parts[4]


def test_usage_text_has_plans_flag():
    """The module docstring at the top of __main__.py includes the report --plans usage line."""
    doc = cli.__doc__
    assert "--plans" in doc


def test_report_plans_returns_zero(tmp_state, capsys):
    """report --plans returns exit code 0."""
    tasks = [_make_task("a", "T", "g", ["x.py"], ["tests/x.py"])]
    _write_plan(tmp_state, "P001", "g", tasks, status="draft", plan_hash="h")
    _write_telemetry_events(tmp_state, [])

    rc = cli.main(["report", "--plans"])
    assert rc == 0


def test_report_plans_with_plain_report_still_works(tmp_state, capsys):
    """report without --plans still prints the telemetry summary (no regression)."""
    events = [
        {"ts": 1, "kind": "call", "call_id": "c1", "task": "T001", "role": "coder",
         "attempt": 1, "model": "m", "effort": "e", "prompt_tokens": 10,
         "completion_tokens": 5, "reasoning_chars": 0, "finish": "stop", "seconds": 1.0},
    ]
    _write_telemetry_events(tmp_state, events)

    rc = cli.main(["report"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "calls:" in out


def test_report_plans_imports_plans_summary():
    """plans_summary must be importable from stratos.report."""
    from stratos.report import plans_summary
    assert callable(plans_summary)
