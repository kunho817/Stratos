"""Tests for task facts-cmd-save: cmd_facts saves the two programs' outputs and prints a folder note on
non-agreement.

cmd_facts(args, store, parser):
  calls facts.derive(gw, p["goal"], keep=keep) with keep = {};
  after derive returns, saves keep["a"] to <state_dir>/facts/<plan_id>-a.json
    (json.dumps(obj, indent=1, sort_keys=True)) when keep["a"] is not None,
    and keep["b"] to <plan_id>-b.json when keep["b"] is not None;
  a None object is NOT saved;
  on ANY non-agree (none, program failed, or disagree) prints "facts: " + reason,
    then "facts: both outputs are in <the facts folder>";
  on agree the existing agree behaviour is preserved (append, save plan, facts txt, print count)
    AND still saves the a.json / b.json outputs.

OUTDATED: tests/test_facts_cmd_save.py::test_program_a_failed_no_json_saved - the old version asserted that
  no folder note is printed for "program A failed"; the new behaviour prints the folder note for every
  non-agree reason, so the stdout assertion is rewritten.
OUTDATED: tests/test_facts_cmd_save.py::test_program_b_failed_a_saved_b_not - same reason: the folder note
  is now printed for "program B failed".
OUTDATED: tests/test_facts_cmd_save.py::test_none_reason_no_files_saved - same reason: the folder note is
  now printed for "none".
OUTDATED: tests/test_facts_cmd_save.py::test_none_reason_no_folder_note - same reason: "both outputs are in"
  IS printed for the "none" reason.
"""

import json

from stratos import __main__ as cli
from stratos import config
from stratos.telemetry import Telemetry

HEADER = ("\n\nWORKED FACTS (computed by two independent programs from the rules "
          "- read facts from here, never work them out in your head):\n")

RENDERED = "x:\n  1 -> 2\n  3 -> 4\ny:\n  a -> [5]"

OBJ_A = {"x": {"1": 2, "3": 4}, "y": {"a": [5]}}
OBJ_B = {"x": {"1": 2, "3": 4}, "y": {"a": [5]}}


class FakeGateway:
    def __init__(self, tel):
        self.telemetry = tel
        self.models = []
        self.calls = []

    def ensure_model(self, model):
        self.models.append(model)

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        return "c1", "ok"


def _plan(pid="P001", goal="the feature goal", tasks=None):
    if tasks is None:
        tasks = [
            {"key": "T1", "title": "task1", "goal": "do the thing",
             "files": ["a.py"], "tests": ["tests/t1.py"],
             "protected": [], "after": [], "role": "coder"},
            {"key": "T2", "title": "task2", "goal": "already has WORKED FACTS here",
             "files": ["b.py"], "tests": ["tests/t2.py"],
             "protected": [], "after": [], "role": "coder"},
        ]
    return {"id": pid, "goal": goal, "tasks": tasks, "status": "draft", "hash": "abc"}


def _setup(tmp_path, monkeypatch, plan):
    """Point config at tmp_path, write plan file, stub gateway + memory refresh."""
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    (tmp_path / "repo").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("stratos.__main__.Gateway", FakeGateway)
    monkeypatch.setattr(cli, "refresh_memory", lambda: None)
    plans_dir = tmp_path / "state" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / f"{plan['id']}.json").write_text(
        json.dumps(plan, indent=1), encoding="utf-8")
    return tmp_path / "state"


def _make_derive(obj_a, obj_b, reason):
    """Build a derive fake that populates keep["a"] and keep["b"], returns the result."""
    def fake_derive(gw, goal, **kw):
        keep = kw.get("keep", {})
        keep["a"] = obj_a
        keep["b"] = obj_b
        facts_val = obj_a if reason == "agree" else None
        return {"facts": facts_val, "reason": reason}
    return fake_derive


# 1 – derive receives keep={} keyword argument

def test_derive_receives_keep_kwarg(tmp_path, monkeypatch, capsys):
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    seen_kw = []

    def fake_derive(gw, goal, **kw):
        seen_kw.append(kw)
        return {"facts": OBJ_A, "reason": "agree"}

    monkeypatch.setattr(cli.facts, "derive", fake_derive)
    monkeypatch.setattr(cli.facts, "render", lambda f: RENDERED)
    rc = cli.main(["facts", "P001"])
    # Expected: derive called once; kw contains "keep" mapped to {}
    assert len(seen_kw) == 1
    # Expected: keep={} is passed as a keyword argument
    assert "keep" in seen_kw[0]
    # Expected: keep starts as an empty dict
    assert seen_kw[0]["keep"] == {}
    # Expected: rc 0 (agree path)
    assert rc == 0


# 2 – agree saves both a.json and b.json

def test_agree_saves_both_json(tmp_path, monkeypatch, capsys):
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        _make_derive(OBJ_A, OBJ_B, "agree"))
    monkeypatch.setattr(cli.facts, "render", lambda f: RENDERED)
    rc = cli.main(["facts", "P001"])
    # Expected: rc 0
    assert rc == 0
    # Expected: state_dir/facts/P001-a.json exists
    a_path = tmp_path / "state" / "facts" / "P001-a.json"
    # Expected: state_dir/facts/P001-b.json exists
    b_path = tmp_path / "state" / "facts" / "P001-b.json"
    assert a_path.exists()
    assert b_path.exists()
    # Expected: content is json.dumps(obj, indent=1, sort_keys=True)
    # json.dumps(OBJ_A, indent=1, sort_keys=True)
    expected_a = json.dumps(OBJ_A, indent=1, sort_keys=True)
    # json.dumps(OBJ_B, indent=1, sort_keys=True)
    expected_b = json.dumps(OBJ_B, indent=1, sort_keys=True)
    # Expected: a.json content matches json.dumps(OBJ_A, indent=1, sort_keys=True)
    assert a_path.read_text(encoding="utf-8") == expected_a
    # Expected: b.json content matches json.dumps(OBJ_B, indent=1, sort_keys=True)
    assert b_path.read_text(encoding="utf-8") == expected_b


# 3 – disagree saves both a.json and b.json

def test_disagree_saves_both_json(tmp_path, monkeypatch, capsys):
    obj_a = {"x": {"1": 2}}
    obj_b = {"x": {"1": 3}}
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        _make_derive(obj_a, obj_b, "disagree: x 1: 2 vs 3"))
    rc = cli.main(["facts", "P001"])
    # Expected: rc 0
    assert rc == 0
    # Expected: a.json exists (obj_a is not None)
    a_path = tmp_path / "state" / "facts" / "P001-a.json"
    # Expected: b.json exists (obj_b is not None)
    b_path = tmp_path / "state" / "facts" / "P001-b.json"
    assert a_path.exists()
    assert b_path.exists()
    # json.dumps({"x": {"1": 2}}, indent=1, sort_keys=True)
    # Expected: a.json content == json.dumps(obj_a, indent=1, sort_keys=True)
    assert a_path.read_text(encoding="utf-8") == json.dumps(obj_a, indent=1, sort_keys=True)
    # json.dumps({"x": {"1": 3}}, indent=1, sort_keys=True)
    # Expected: b.json content == json.dumps(obj_b, indent=1, sort_keys=True)
    assert b_path.read_text(encoding="utf-8") == json.dumps(obj_b, indent=1, sort_keys=True)


# 4 – program A failed: keep["a"] = None → a.json not saved, b.json not saved
#     (the folder note IS printed, because this is a non-agree reason)

def test_program_a_failed_no_json_saved(tmp_path, monkeypatch, capsys):
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        _make_derive(None, None, "program A failed"))
    rc = cli.main(["facts", "P001"])
    # Expected: rc 0
    assert rc == 0
    # Expected: keep["a"] = None → a.json NOT saved
    a_path = tmp_path / "state" / "facts" / "P001-a.json"
    # Expected: keep["b"] = None (B never ran) → b.json NOT saved
    b_path = tmp_path / "state" / "facts" / "P001-b.json"
    assert not a_path.exists()
    assert not b_path.exists()
    out = capsys.readouterr().out
    # Expected: stdout is "facts: program A failed"
    assert "facts: program A failed" in out
    # Expected: the folder note is printed for a non-agree reason
    facts_dir = str(tmp_path / "state" / "facts")
    assert f"facts: both outputs are in {facts_dir}" in out


# 5 – program B failed: keep["a"] = obj_a, keep["b"] = None
#     (the folder note IS printed, because this is a non-agree reason)

def test_program_b_failed_a_saved_b_not(tmp_path, monkeypatch, capsys):
    obj_a = {"x": {"1": 2}}
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        _make_derive(obj_a, None, "program B failed"))
    rc = cli.main(["facts", "P001"])
    # Expected: rc 0
    assert rc == 0
    # Expected: keep["a"] = obj_a → a.json saved
    a_path = tmp_path / "state" / "facts" / "P001-a.json"
    # Expected: keep["b"] = None → b.json NOT saved
    b_path = tmp_path / "state" / "facts" / "P001-b.json"
    assert a_path.exists()
    # Expected: b.json does not exist (None not saved)
    assert not b_path.exists()
    # json.dumps({"x": {"1": 2}}, indent=1, sort_keys=True)
    # Expected: a.json content == json.dumps(obj_a, indent=1, sort_keys=True)
    assert a_path.read_text(encoding="utf-8") == json.dumps(obj_a, indent=1, sort_keys=True)
    out = capsys.readouterr().out
    # Expected: stdout is "facts: program B failed"
    assert "facts: program B failed" in out
    # Expected: the folder note is printed for a non-agree reason
    facts_dir = str(tmp_path / "state" / "facts")
    assert f"facts: both outputs are in {facts_dir}" in out


# 6 – reason "none": both None, no files saved
#     (the folder note IS printed, because this is a non-agree reason)

def test_none_reason_no_files_saved(tmp_path, monkeypatch, capsys):
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        _make_derive(None, None, "none"))
    rc = cli.main(["facts", "P001"])
    # Expected: rc 0
    assert rc == 0
    # Expected: keep["a"] = None → a.json NOT saved
    a_path = tmp_path / "state" / "facts" / "P001-a.json"
    # Expected: keep["b"] = None → b.json NOT saved
    b_path = tmp_path / "state" / "facts" / "P001-b.json"
    assert not a_path.exists()
    assert not b_path.exists()
    out = capsys.readouterr().out
    # Expected: stdout "facts: none"
    assert "facts: none" in out
    # Expected: the folder note is printed for a non-agree reason
    facts_dir = str(tmp_path / "state" / "facts")
    assert f"facts: both outputs are in {facts_dir}" in out


# 7 – disagree prints reason AND folder note

def test_disagree_prints_reason_and_folder_note(tmp_path, monkeypatch, capsys):
    obj_a = {"x": {"1": 2}}
    obj_b = {"x": {"1": 3}}
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        _make_derive(obj_a, obj_b, "disagree: x 1: 2 vs 3"))
    rc = cli.main(["facts", "P001"])
    # Expected: rc 0
    assert rc == 0
    out = capsys.readouterr().out
    # Expected: first line "facts: disagree: x 1: 2 vs 3"
    assert "facts: disagree: x 1: 2 vs 3" in out
    # Expected: second line "facts: both outputs are in <the facts folder>"
    # The facts folder is Path(config.STATE_DIR) / "facts" = tmp_path / "state" / "facts"
    facts_dir = str(tmp_path / "state" / "facts")
    # Expected: "facts: both outputs are in <facts_dir>"
    assert f"facts: both outputs are in {facts_dir}" in out
    # Expected: exactly 2 lines
    lines = out.strip().split("\n")
    # Expected: line 0 = reason, line 1 = folder note
    assert lines[0] == "facts: disagree: x 1: 2 vs 3"
    assert lines[1] == f"facts: both outputs are in {facts_dir}"
    # Expected: len(lines) == 2
    assert len(lines) == 2


# 8 – agree does NOT print folder note

def test_agree_no_folder_note(tmp_path, monkeypatch, capsys):
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        _make_derive(OBJ_A, OBJ_B, "agree"))
    monkeypatch.setattr(cli.facts, "render", lambda f: RENDERED)
    rc = cli.main(["facts", "P001"])
    # Expected: rc 0
    assert rc == 0
    out = capsys.readouterr().out
    # Expected: "facts: agree, 2 facts added to 1 tasks"
    assert "facts: agree, 2 facts added to 1 tasks" in out
    # Expected: "both outputs are in" does NOT appear
    assert "both outputs are in" not in out


# 9 – non-disagree non-agree still prints the folder note (new behaviour)

def test_none_reason_still_prints_folder_note(tmp_path, monkeypatch, capsys):
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        _make_derive(None, None, "none"))
    rc = cli.main(["facts", "P001"])
    # Expected: rc 0
    assert rc == 0
    out = capsys.readouterr().out
    # Expected: "facts: none" printed
    assert "facts: none" in out
    # Expected: "both outputs are in" IS printed (new behaviour: folder note on every non-agree)
    assert "both outputs are in" in out


# 10 – json format: indent=1, sort_keys=True

def test_json_format_indent1_sort_keys(tmp_path, monkeypatch, capsys):
    obj_a = {"b": {"z": 3, "a": 1}, "a": {"y": 2, "x": 0}}
    # Expected: json.dumps(obj_a, indent=1, sort_keys=True)
    expected = json.dumps(obj_a, indent=1, sort_keys=True)
    # step: sort_keys puts "a" < "b", keys "x" < "y" inside "a", "a" < "z" inside "b"
    # step: indent=1 gives one space per nesting level
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        _make_derive(obj_a, None, "program B failed"))
    rc = cli.main(["facts", "P001"])
    # Expected: rc 0
    assert rc == 0
    a_path = tmp_path / "state" / "facts" / "P001-a.json"
    # Expected: a.json content == json.dumps(obj_a, indent=1, sort_keys=True)
    assert a_path.read_text(encoding="utf-8") == expected
    # Expected: the file has key "a" before key "b" (sort_keys)
    lines = a_path.read_text(encoding="utf-8").split("\n")
    # json.dumps({"b": {"z": 3, "a": 1}, "a": {"y": 2, "x": 0}}, indent=1, sort_keys=True)
    # line 0: {
    # line 1:  "a": {
    # line 2:    "x": 0
    # line 3:    "y": 2
    # line 4:  },
    # line 5:  "b": {
    # line 6:    "a": 1
    # line 7:    "z": 3
    # line 8:  }
    # line 9: }
    # Expected: "a" appears before "b" in the file
    assert lines[1].strip().startswith('"a"')
    # Expected: "b" appears after "a"
    assert lines[5].strip().startswith('"b"')


# 11 – files at the correct state_dir/facts/ paths

def test_files_at_correct_paths(tmp_path, monkeypatch, capsys):
    obj_a = {"x": {"1": 2}}
    obj_b = {"x": {"1": 2}}
    plan = _plan(pid="P042")
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        _make_derive(obj_a, obj_b, "agree"))
    monkeypatch.setattr(cli.facts, "render", lambda f: RENDERED)
    rc = cli.main(["facts", "P042"])
    # Expected: rc 0
    assert rc == 0
    # Expected: a.json at <state_dir>/facts/P042-a.json
    a_path = tmp_path / "state" / "facts" / "P042-a.json"
    # Expected: b.json at <state_dir>/facts/P042-b.json
    b_path = tmp_path / "state" / "facts" / "P042-b.json"
    assert a_path.exists()
    # Expected: b.json path uses plan id "P042"
    assert b_path.exists()


# 12 – agree still appends facts and writes facts txt (existing behaviour preserved)

def test_agree_still_appends_and_writes_txt(tmp_path, monkeypatch, capsys):
    plan = _plan()
    _setup(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(cli.facts, "derive",
                        _make_derive(OBJ_A, OBJ_B, "agree"))
    monkeypatch.setattr(cli.facts, "render", lambda f: RENDERED)
    rc = cli.main(["facts", "P001"])
    # Expected: rc 0
    assert rc == 0
    # Expected: T1 goal has WORKED FACTS appended
    p = json.loads((tmp_path / "state" / "plans" / "P001.json").read_text(encoding="utf-8"))
    # Expected: T1 goal == "do the thing" + HEADER + RENDERED
    assert p["tasks"][0]["goal"] == "do the thing" + HEADER + RENDERED
    # Expected: T2 goal unchanged
    assert p["tasks"][1]["goal"] == "already has WORKED FACTS here"
    # Expected: state_dir/facts/P001.txt exists with RENDERED
    facts_txt = tmp_path / "state" / "facts" / "P001.txt"
    # Expected: facts txt content == RENDERED
    assert facts_txt.exists()
    # Expected: facts txt == RENDERED
    assert facts_txt.read_text(encoding="utf-8") == RENDERED
    # Expected: stdout has agree line
    out = capsys.readouterr().out
    # Expected: "facts: agree, 2 facts added to 1 tasks"
    assert "facts: agree, 2 facts added to 1 tasks" in out
