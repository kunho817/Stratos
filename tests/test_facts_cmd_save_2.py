"""Tests for task facts_cmd_save: cmd_facts writes program and error files.

In cmd_facts, after derive returns, write into the same facts folder:
  <plan>-a.py and <plan>-b.py for each program in keep that is not None,
  <plan>-a-error.txt and <plan>-b-error.txt for each error in keep that is not None.
<plan> is args.plan_id, exactly as for the existing <plan>-a.json and <plan>-b.json files.
Return value and printed lines stay as today.
"""

import json

from stratos import __main__ as cli
from stratos import config

HEADER = ("\n\nWORKED FACTS (computed by two independent programs from the rules "
          "- read facts from here, never work them out in your head):\n")

RENDERED = "x:\n  1 -> 2\n  3 -> 4\ny:\n  a -> [5]"
OBJ_A = {"x": {"1": 2, "3": 4}, "y": {"a": [5]}}
OBJ_B = {"x": {"1": 2, "3": 4}, "y": {"a": [5]}}

PROGRAM_A = 'import json\nprint(json.dumps({"x": {"1": 2, "3": 4}, "y": {"a": [5]}}))'
PROGRAM_B = 'import json\nprint(json.dumps({"x": {"1": 2, "3": 4}, "y": {"a": [5]}}))'


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


def _run(tmp_path, monkeypatch, plan, keep_data, result):
    """Set up, stub derive + render, run cli.main(["facts", pid]).
    Return (rc, facts_dir, captured_stdout)."""
    def fake_derive(gw, goal, **kw):
        keep = kw.get("keep", {})
        keep.update(keep_data)
        return result

    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    (tmp_path / "repo").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("stratos.__main__.Gateway", FakeGateway)
    monkeypatch.setattr(cli, "refresh_memory", lambda: None)
    monkeypatch.setattr(cli.facts, "derive", fake_derive)
    monkeypatch.setattr(cli.facts, "render", lambda f: RENDERED)
    plans_dir = tmp_path / "state" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / f"{plan['id']}.json").write_text(
        json.dumps(plan, indent=1), encoding="utf-8")
    rc = cli.main(["facts", plan["id"]])
    facts_dir = tmp_path / "state" / "facts"
    return rc, facts_dir


# ---- 1: both programs non-None → .py files written ----

def test_both_programs_written(tmp_path, monkeypatch, capsys):
    # keep: a_program=PROGRAM_A, b_program=PROGRAM_B
    # Expected: P001-a.py exists, content == PROGRAM_A
    # Expected: P001-b.py exists, content == PROGRAM_B
    keep = {"a": OBJ_A, "b": OBJ_B,
            "a_program": PROGRAM_A, "b_program": PROGRAM_B,
            "a_error": None, "b_error": None}
    rc, facts_dir = _run(tmp_path, monkeypatch, _plan(), keep,
                         {"facts": OBJ_A, "reason": "agree"})
    # Expected: rc 0
    assert rc == 0
    # Expected: P001-a.py content == PROGRAM_A
    a_py = facts_dir / "P001-a.py"
    assert a_py.exists()
    assert a_py.read_text(encoding="utf-8") == PROGRAM_A
    # Expected: P001-b.py content == PROGRAM_B
    b_py = facts_dir / "P001-b.py"
    assert b_py.exists()
    assert b_py.read_text(encoding="utf-8") == PROGRAM_B


# ---- 2: both errors non-None → .txt files written ----

def test_both_errors_written(tmp_path, monkeypatch, capsys):
    # keep: a_error="exit code 1: boom", b_error="no output"
    # Expected: P001-a-error.txt content == "exit code 1: boom"
    # Expected: P001-b-error.txt content == "no output"
    keep = {"a": OBJ_A, "b": OBJ_B,
            "a_program": PROGRAM_A, "b_program": PROGRAM_B,
            "a_error": "exit code 1: boom", "b_error": "no output"}
    rc, facts_dir = _run(tmp_path, monkeypatch, _plan(), keep,
                         {"facts": OBJ_A, "reason": "agree"})
    # Expected: a-error.txt == "exit code 1: boom"
    a_err = facts_dir / "P001-a-error.txt"
    assert a_err.exists()
    assert a_err.read_text(encoding="utf-8") == "exit code 1: boom"
    # Expected: b-error.txt == "no output"
    b_err = facts_dir / "P001-b-error.txt"
    assert b_err.exists()
    assert b_err.read_text(encoding="utf-8") == "no output"


# ---- 3: a_program None → a.py not written ----

def test_a_program_none_not_written(tmp_path, monkeypatch, capsys):
    # keep: a_program=None, b_program=PROGRAM_B
    # Expected: P001-a.py NOT exists
    # Expected: P001-b.py exists with PROGRAM_B
    keep = {"a": None, "b": OBJ_B,
            "a_program": None, "b_program": PROGRAM_B,
            "a_error": None, "b_error": None}
    rc, facts_dir = _run(tmp_path, monkeypatch, _plan(), keep,
                         {"facts": None, "reason": "program A failed"})
    # Expected: a.py not present
    assert not (facts_dir / "P001-a.py").exists()
    # Expected: b.py present
    assert (facts_dir / "P001-b.py").exists()


# ---- 4: a_error None → a-error.txt not written ----

def test_a_error_none_not_written(tmp_path, monkeypatch, capsys):
    # keep: a_error=None, b_error="exit code 2: crash"
    # Expected: P001-a-error.txt NOT exists
    # Expected: P001-b-error.txt content == "exit code 2: crash"
    keep = {"a": OBJ_A, "b": None,
            "a_program": PROGRAM_A, "b_program": None,
            "a_error": None, "b_error": "exit code 2: crash"}
    rc, facts_dir = _run(tmp_path, monkeypatch, _plan(), keep,
                         {"facts": None, "reason": "program B failed"})
    # Expected: a-error.txt not present
    assert not (facts_dir / "P001-a-error.txt").exists()
    # Expected: b-error.txt present
    b_err = facts_dir / "P001-b-error.txt"
    assert b_err.exists()
    # Expected: content == "exit code 2: crash"
    assert b_err.read_text(encoding="utf-8") == "exit code 2: crash"


# ---- 5: plan id used in filenames ----

def test_plan_id_in_filename(tmp_path, monkeypatch, capsys):
    # plan_id = "P042"
    # Expected: filenames P042-a.py, P042-b.py, P042-a-error.txt, P042-b-error.txt
    keep = {"a": OBJ_A, "b": OBJ_B,
            "a_program": PROGRAM_A, "b_program": PROGRAM_B,
            "a_error": "errA", "b_error": "errB"}
    rc, facts_dir = _run(tmp_path, monkeypatch, _plan(pid="P042"), keep,
                         {"facts": OBJ_A, "reason": "agree"})
    # Expected: all four files use plan id P042
    assert (facts_dir / "P042-a.py").exists()
    assert (facts_dir / "P042-b.py").exists()
    assert (facts_dir / "P042-a-error.txt").exists()
    assert (facts_dir / "P042-b-error.txt").exists()


# ---- 6: files in the facts folder ----

def test_files_in_facts_folder(tmp_path, monkeypatch, capsys):
    # Expected: .py and .txt files are in state_dir/"facts", same as .json
    keep = {"a": OBJ_A, "b": OBJ_B,
            "a_program": PROGRAM_A, "b_program": PROGRAM_B,
            "a_error": "e", "b_error": "e2"}
    rc, facts_dir = _run(tmp_path, monkeypatch, _plan(), keep,
                         {"facts": OBJ_A, "reason": "agree"})
    # Expected: a.json, a.py, a-error.txt all in facts_dir
    assert (facts_dir / "P001-a.json").exists()
    # Expected: .py in the same folder as .json
    assert (facts_dir / "P001-a.py").exists()
    # Expected: .txt in the same folder as .json
    assert (facts_dir / "P001-a-error.txt").exists()


# ---- 7: agree writes json + program files together ----

def test_agree_writes_json_and_program(tmp_path, monkeypatch, capsys):
    # Agree path: all keys set
    # Expected: P001-a.json, P001-b.json, P001-a.py, P001-b.py, P001.txt all exist
    keep = {"a": OBJ_A, "b": OBJ_B,
            "a_program": PROGRAM_A, "b_program": PROGRAM_B,
            "a_error": None, "b_error": None}
    rc, facts_dir = _run(tmp_path, monkeypatch, _plan(), keep,
                         {"facts": OBJ_A, "reason": "agree"})
    # Expected: json files present
    assert (facts_dir / "P001-a.json").exists()
    assert (facts_dir / "P001-b.json").exists()
    # Expected: program files present
    assert (facts_dir / "P001-a.py").exists()
    # Expected: facts txt present (agree writes it)
    assert (facts_dir / "P001.txt").exists()


# ---- 8: disagree writes program and error files ----

def test_disagree_writes_program_and_error(tmp_path, monkeypatch, capsys):
    # Disagree: all keys set
    # Expected: .py and .txt files present; no P001.txt (not agree path)
    obj_a = {"x": {"1": 2}}
    obj_b = {"x": {"1": 3}}
    keep = {"a": obj_a, "b": obj_b,
            "a_program": PROGRAM_A, "b_program": PROGRAM_B,
            "a_error": "exit code 1: x", "b_error": "no output"}
    rc, facts_dir = _run(tmp_path, monkeypatch, _plan(), keep,
                         {"facts": None, "reason": "disagree: x 1: 2 vs 3"})
    # Expected: rc 0
    assert rc == 0
    # Expected: program files present
    assert (facts_dir / "P001-a.py").exists()
    assert (facts_dir / "P001-b.py").exists()
    # Expected: error files present
    assert (facts_dir / "P001-a-error.txt").exists()
    # Expected: b-error.txt content == "no output"
    assert facts_dir / "P001-b-error.txt"
    b_err = facts_dir / "P001-b-error.txt"
    # Expected: content == "no output"
    assert b_err.read_text(encoding="utf-8") == "no output"
    # Expected: no P001.txt (not agree)
    assert not (facts_dir / "P001.txt").exists()


# ---- 9: .py content is exactly the program string ----

def test_py_content_exact(tmp_path, monkeypatch, capsys):
    # PROGRAM_A = 'import json\nprint(json.dumps({"x": {"1": 2, "3": 4}, "y": {"a": [5]}}))'
    # Expected: P001-a.py content == PROGRAM_A byte-for-byte
    keep = {"a": OBJ_A, "b": OBJ_B,
            "a_program": PROGRAM_A, "b_program": None,
            "a_error": None, "b_error": None}
    rc, facts_dir = _run(tmp_path, monkeypatch, _plan(), keep,
                         {"facts": OBJ_A, "reason": "agree"})
    # Expected: content matches the program string exactly
    assert facts_dir / "P001-a.py"
    content = (facts_dir / "P001-a.py").read_text(encoding="utf-8")
    # Expected: content == PROGRAM_A
    assert content == PROGRAM_A
    # Expected: b.py not written (None)
    assert not (facts_dir / "P001-b.py").exists()


# ---- 10: .txt content is exactly the error string ----

def test_txt_content_exact(tmp_path, monkeypatch, capsys):
    # a_error = "output is not JSON: not json"
    # Expected: P001-a-error.txt content == "output is not JSON: not json"
    keep = {"a": None, "b": None,
            "a_program": None, "b_program": None,
            "a_error": "output is not JSON: not json", "b_error": None}
    rc, facts_dir = _run(tmp_path, monkeypatch, _plan(), keep,
                         {"facts": None, "reason": "program A failed"})
    # Expected: a-error.txt content == "output is not JSON: not json"
    a_err = facts_dir / "P001-a-error.txt"
    # Expected: content == the error string
    assert a_err.read_text(encoding="utf-8") == "output is not JSON: not json"
    # Expected: b-error.txt not present (None)
    assert not (facts_dir / "P001-b-error.txt").exists()


# ---- 11: return code unchanged on agree ----

def test_rc_unchanged_on_agree(tmp_path, monkeypatch, capsys):
    # Expected: rc == 0 on agree
    keep = {"a": OBJ_A, "b": OBJ_B,
            "a_program": PROGRAM_A, "b_program": None,
            "a_error": None, "b_error": None}
    rc, facts_dir = _run(tmp_path, monkeypatch, _plan(), keep,
                         {"facts": OBJ_A, "reason": "agree"})
    # Expected: rc 0 (agree path returns 0)
    assert rc == 0


# ---- 12: return code unchanged on non-agree ----

def test_rc_unchanged_on_non_agree(tmp_path, monkeypatch, capsys):
    # Expected: rc == 0 on non-agree
    keep = {"a": None, "b": None,
            "a_program": None, "b_program": None,
            "a_error": "exit code 1: boom", "b_error": None}
    rc, facts_dir = _run(tmp_path, monkeypatch, _plan(), keep,
                         {"facts": None, "reason": "program A failed"})
    # Expected: rc 0 (non-agree returns 0)
    assert rc == 0


# ---- 13: printed lines unchanged on agree ----

def test_printed_lines_unchanged_on_agree(tmp_path, monkeypatch, capsys):
    # n=2 fact names, m=1 task (T1 lacks WORKED FACTS, T2 has it)
    # Expected stdout: "facts: agree, 2 facts added to 1 tasks"
    keep = {"a": OBJ_A, "b": OBJ_B,
            "a_program": PROGRAM_A, "b_program": None,
            "a_error": None, "b_error": None}
    rc, facts_dir = _run(tmp_path, monkeypatch, _plan(), keep,
                         {"facts": OBJ_A, "reason": "agree"})
    # Expected: stdout is exactly "facts: agree, 2 facts added to 1 tasks"
    out = capsys.readouterr().out
    # Expected: the agree line
    assert out.strip() == "facts: agree, 2 facts added to 1 tasks"


# ---- 14: printed lines unchanged on non-agree ----

def test_printed_lines_unchanged_on_non_agree(tmp_path, monkeypatch, capsys):
    # reason="disagree: x 1: 2 vs 3"
    # Expected: stdout has "facts: disagree: x 1: 2 vs 3" and "facts: both outputs are in"
    obj_a = {"x": {"1": 2}}
    obj_b = {"x": {"1": 3}}
    keep = {"a": obj_a, "b": obj_b,
            "a_program": PROGRAM_A, "b_program": PROGRAM_B,
            "a_error": None, "b_error": None}
    rc, facts_dir = _run(tmp_path, monkeypatch, _plan(), keep,
                         {"facts": None, "reason": "disagree: x 1: 2 vs 3"})
    # Expected: the reason line
    out = capsys.readouterr().out
    assert "facts: disagree: x 1: 2 vs 3" in out
    # Expected: the folder note
    facts_str = str(facts_dir)
    # Expected: "facts: both outputs are in <facts_dir>"
    assert f"facts: both outputs are in {facts_str}" in out


# ---- 15: all four files when all four keys are non-None ----

def test_all_four_files_present(tmp_path, monkeypatch, capsys):
    # a_program, b_program, a_error, b_error all non-None
    # Expected: P001-a.py, P001-b.py, P001-a-error.txt, P001-b-error.txt
    keep = {"a": OBJ_A, "b": OBJ_B,
            "a_program": PROGRAM_A, "b_program": PROGRAM_B,
            "a_error": "exit code 1: boom", "b_error": "timed out after 20 s"}
    rc, facts_dir = _run(tmp_path, monkeypatch, _plan(), keep,
                         {"facts": OBJ_A, "reason": "agree"})
    # Expected: all four files exist
    # Expected: a.py content == PROGRAM_A
    assert facts_dir / "P001-a.py"
    # Expected: b.py content == PROGRAM_B
    assert facts_dir / "P001-b.py"
    # Expected: a-error.txt content == "exit code 1: boom"
    a_err = facts_dir / "P001-a-error.txt"
    assert a_err.read_text(encoding="utf-8") == "exit code 1: boom"
    # Expected: b-error.txt content == "timed out after 20 s"
    b_err = facts_dir / "P001-b-error.txt"
    # Expected: content == "timed out after 20 s"
    assert b_err.read_text(encoding="utf-8") == "timed out after 20 s"
