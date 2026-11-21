"""Tests for task T062: `stratos plan --goal-file F [--tries N]` and `stratos plan-add <plan id>` (stratos/plan.py, T061).

plan: reads the goal file, gw = Gateway(Telemetry(config.STATE_DIR / "telemetry.jsonl")), gw.ensure_model(planner
    model), messages = plan.build_messages(goal, plan.repo_summary(config.REPO)), then up to --tries (default 2)
    calls gw.chat(messages, task="plan", role="planner", attempt=n, model=..., effort=..., max_tokens=...) with the
    settings of config.PLANNER, plus reasoning_budget=config.PLANNER["reasoning_budget"] when that is present and not
    None. The answer goes through plan.parse_plan. A PlanError adds the answer as {"role": "assistant", ...} and
    {"role": "user", "content": f"Your plan was invalid: {e}. Answer with the corrected JSON plan only."} to the
    messages and tries again. On success: pid = plan.save_plan(config.STATE_DIR, goal, tasks); prints
    f"plan {pid}: {len(tasks)} tasks", then per task f"  {key}. {title}" and a line with its files and tests; returns 0.
    When every try is invalid: prints "plan invalid: <reason>" on stderr, saves nothing, returns 1.
plan-add: loads the plan (unknown id: "no such plan: <id>" on stderr, return 1; status not "draft": "plan <id> was
    already added" on stderr, return 1). Adds each task in order exactly as `stratos add` does (role None -> the rules'
    role decision with its telemetry and Jev shadow, like add without --role), with "after" keys turned into the task
    ids just added. Then plan.mark_added(config.STATE_DIR, pid, {key: task id}), a telemetry event
    record("plan", plan=pid, tasks=<count>, edited=plan.edited(<the plan as loaded>)), prints "added <id>: <title>"
    per task (like add), returns 0. The add command's body is shared with plan-add, so add behaves as before."""
import json
import sys
from pathlib import Path

import pytest

from stratos import __main__ as cli, config, plan, plantests
from stratos.__main__ import main
from stratos.state import Store
from stratos.telemetry import Telemetry


GOOD = {"tasks": [
    {"key": "a", "title": "Add f", "goal": "Add f to x.", "files": ["stratos/x.py"], "tests": ["tests/test_x.py"]},
    {"key": "b", "title": "Use f", "goal": "Call f in y.", "files": ["stratos/y.py", "stratos/z.py"],
     "tests": ["tests/test_y.py"], "protected": ["stratos/x.py"], "after": ["a"], "role": "coder"},
]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    monkeypatch.setattr(plan, "repo_summary", lambda root: "SUMMARY")
    made = []

    class FakeGateway:
        answers = []

        def __init__(self, telemetry):
            self.telemetry = telemetry
            self.models, self.calls = [], []
            made.append(self)

        def ensure_model(self, model):
            self.models.append(model)
            return 0.0

        def chat(self, messages, **kw):
            self.calls.append((list(messages), kw))
            return f"c{len(self.calls)}", FakeGateway.answers.pop(0)
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    goal = tmp_path / "goal.txt"
    goal.write_text("Make it fly.", encoding="utf-8")
    return FakeGateway, made, goal, tmp_path


def test_plan_saves_a_valid_plan(env, capsys):
    gw_cls, made, goal, tmp = env
    gw_cls.answers = ["```json\n" + json.dumps(GOOD) + "\n```"]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    gw = made[0]
    assert gw.models == [config.PLANNER["model"]]
    messages, kw = gw.calls[0]
    assert messages == plan.build_messages("Make it fly.", "SUMMARY")
    want = {"task": "plan", "role": "planner", "attempt": 1, "model": config.PLANNER["model"],
            "effort": config.PLANNER["effort"], "max_tokens": config.PLANNER["max_tokens"]}
    if config.PLANNER.get("reasoning_budget") is not None:
        want["reasoning_budget"] = config.PLANNER["reasoning_budget"]
    assert kw == want
    assert str(gw.telemetry.path).endswith("telemetry.jsonl")
    p = plan.load_plan(config.STATE_DIR, "P001")
    assert p["status"] == "draft" and p["goal"] == "Make it fly." and [t["key"] for t in p["tasks"]] == ["a", "b"]
    out = capsys.readouterr().out
    assert "plan P001: 2 tasks" in out and "  a. Add f" in out and "  b. Use f" in out
    assert "stratos/z.py" in out and "tests/test_y.py" in out


def test_plan_retries_with_the_reason(env, capsys):
    gw_cls, made, goal, tmp = env
    bad = json.dumps({"tasks": [{"title": "x", "goal": "g", "files": [], "tests": ["tests/t.py"]}]})
    gw_cls.answers = [bad, json.dumps(GOOD)]
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    first, _ = made[0].calls[0]
    second, kw = made[0].calls[1]
    assert kw["attempt"] == 2
    assert second[:2] == first and second[2] == {"role": "assistant", "content": bad}
    assert second[3]["role"] == "user" and second[3]["content"].startswith("Your plan was invalid: ")
    assert second[3]["content"].endswith(". Answer with the corrected JSON plan only.")
    assert plan.load_plan(config.STATE_DIR, "P001")["tasks"][0]["key"] == "a"


def test_plan_gives_up(env, capsys):
    gw_cls, made, goal, tmp = env
    gw_cls.answers = ["no plan", "still no plan", "never"]
    assert cli.main(["plan", "--goal-file", str(goal), "--tries", "3"]) == 1
    assert len(made[0].calls) == 3
    assert "plan invalid: " in capsys.readouterr().err
    assert not (config.STATE_DIR / "plans").exists() or not list((config.STATE_DIR / "plans").glob("*.json"))


def test_plan_add(env, capsys):
    tasks = plan.parse_plan(json.dumps(GOOD))
    tasks[0]["role"] = None
    pid = plan.save_plan(config.STATE_DIR, "Make it fly.", tasks)
    assert cli.main(["plan-add", pid]) == 0
    store = Store(config.STATE_DIR)
    t1, t2 = store.get("T001"), store.get("T002")
    assert (t1["title"], t1["goal"], t1["files"], t1["tests"], t1["protected"], t1["after"]) == \
        ("Add f", "Add f to x.", ["stratos/x.py"], ["tests/test_x.py"], ["tests/test_x.py"], [])  # P010: tests protected
    assert t1["role"] == "coder"                      # the rules' choice for a one-file task without flow words
    assert t1.get("role_decision", {}).get("choice") == "coder"
    assert (t2["role"], t2["after"], t2["protected"], t2["files"]) == \
        ("coder", ["T001"], ["stratos/x.py", "tests/test_y.py"], ["stratos/y.py", "stratos/z.py"])
    p = plan.load_plan(config.STATE_DIR, pid)
    assert p["status"] == "added" and p["task_ids"] == {"a": "T001", "b": "T002"}
    events = Telemetry(config.STATE_DIR / "telemetry.jsonl").load()
    assert [e["task"] for e in events if e["kind"] == "decision" and e.get("decision") == "role"] == ["T001"]
    (pe,) = [e for e in events if e["kind"] == "plan"]
    assert (pe["plan"], pe["tasks"], pe["edited"]) == (pid, 2, False)
    out = capsys.readouterr().out
    assert "added T001: Add f" in out and "added T002: Use f" in out


def test_plan_add_records_an_edited_plan(env):
    pid = plan.save_plan(config.STATE_DIR, "Make it fly.", plan.parse_plan(json.dumps(GOOD)))
    path = config.STATE_DIR / "plans" / f"{pid}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tasks"][1]["goal"] = "Call f in y, and log it."
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert cli.main(["plan-add", pid]) == 0
    assert Store(config.STATE_DIR).get("T002")["goal"] == "Call f in y, and log it."
    (pe,) = [e for e in Telemetry(config.STATE_DIR / "telemetry.jsonl").load() if e["kind"] == "plan"]
    assert pe["edited"] is True


def test_plan_add_refuses_unknown_and_added_plans(env, capsys):
    assert cli.main(["plan-add", "P404"]) == 1
    assert "no such plan: P404" in capsys.readouterr().err
    pid = plan.save_plan(config.STATE_DIR, "g", plan.parse_plan(json.dumps(GOOD)))
    assert cli.main(["plan-add", pid]) == 0
    capsys.readouterr()
    assert cli.main(["plan-add", pid]) == 1
    assert f"plan {pid} was already added" in capsys.readouterr().err
    assert len(Store(config.STATE_DIR).tasks()) == 2


def test_plan_add_keeps_a_search_output(env, capsys):
    """(Claude, 2026-11-21, Lantern) a plan task's "output" (a search task, P16) reaches the stored task."""
    tasks = plan.parse_plan(json.dumps(GOOD))
    tasks[0]["output"] = "data/levels.json"
    pid = plan.save_plan(config.STATE_DIR, "Make it fly.", tasks)
    assert cli.main(["plan-add", pid]) == 0
    store = Store(config.STATE_DIR)
    assert store.get("T001")["output"] == "data/levels.json" and "output" not in store.get("T002")


# ---- was test_cli_plan_answers.py ----
# Tests for task cli-plan-save-answers: save raw planner answers as plan-<call_id>.md.
#
# In the plan command flow in stratos/__main__.py, after each model call that produces a plan draft,
# write the raw answer text to .stratos/answers/plan-<call_id>.md (call_id from the gateway telemetry).
# Ensure the answers directory is created if missing. This lets a failed plan be explained later.
#
# Requirements:
#   - After gw.chat returns (call_id, text), write text to STATE_DIR / "answers" / f"plan-{call_id}.md".
#   - The answers directory must be created if it does not exist.
#   - Every attempt (including failed/invalid ones) saves its raw answer.
#   - The file content is exactly the raw text returned by gw.chat (no trimming, no formatting).
#   - Files are named plan-<call_id>.md using the call_id from the gateway.


# ---------- helpers ----------

class NullTelemetry:
    def record(self, kind, **fields):
        pass


class FakeGateway:
    """Fake gateway that records calls and returns pre-set (call_id, text) tuples."""

    def __init__(self, responses):
        """responses: list of (call_id, text) tuples, consumed in order."""
        self.telemetry = NullTelemetry()   # plan records "plan_parse" events through gw.telemetry (T076)
        self._responses = list(responses)
        self._idx = 0
        self.calls = []  # (messages, kw) tuples

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        call_id, text = self._responses[self._idx]
        self._idx += 1
        self.calls.append((messages, kw))
        return call_id, text


VALID_PLAN_JSON = json.dumps({"tasks": [
    {"key": "1", "title": "First", "goal": "Do A", "files": ["a.py"], "tests": ["tests/test_a.py"]},
    {"key": "2", "title": "Second", "goal": "Do B", "files": ["b.py"], "tests": ["tests/test_b.py"]},
]})


INVALID_PLAN = "This is not a valid JSON plan."


def _setup(tmp_path, monkeypatch):
    """Set up config paths and fake the gateway so main() runs the plan command offline."""
    state_dir = tmp_path / ".stratos"
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr("stratos.config.STATE_DIR", state_dir)
    monkeypatch.setattr("stratos.config.REPO", repo)
    monkeypatch.setattr("stratos.config.WORKTREES", tmp_path / "worktrees")
    # Ensure PLAN prompt parts work without a real repo
    monkeypatch.setattr("stratos.plan.repo_summary", lambda root: "(empty repo)")
    return state_dir


def _goal_file(tmp_path, goal_text):
    p = tmp_path / "goal.md"
    p.write_text(goal_text, encoding="utf-8")
    return str(p)


# ---------- tests ----------

def test_answers_directory_created(tmp_path, monkeypatch):
    """The .stratos/answers/ directory is created (if missing) during the plan flow."""
    state_dir = _setup(tmp_path, monkeypatch)
    answers_dir = state_dir / "answers"
    assert not answers_dir.exists()

    goal = _goal_file(tmp_path, "Build feature X")
    gw = FakeGateway([("abc123def456", VALID_PLAN_JSON)])
    monkeypatch.setattr("stratos.__main__.Gateway", lambda tel: gw)
    monkeypatch.setattr("stratos.__main__.Telemetry", lambda p: None)

    main(["plan", "--goal-file", goal])

    assert answers_dir.is_dir(), "answers directory must be created"


def test_plan_answer_saved_on_success(tmp_path, monkeypatch):
    """After a successful plan call, plan-<call_id>.md contains the raw text."""
    state_dir = _setup(tmp_path, monkeypatch)
    goal = _goal_file(tmp_path, "Build feature X")

    call_id = "a1b2c3d4e5f6"
    raw_text = VALID_PLAN_JSON
    gw = FakeGateway([(call_id, raw_text)])
    monkeypatch.setattr("stratos.__main__.Gateway", lambda tel: gw)
    monkeypatch.setattr("stratos.__main__.Telemetry", lambda p: None)

    main(["plan", "--goal-file", goal])

    saved = state_dir / "answers" / f"plan-{call_id}.md"
    assert saved.exists(), f"expected {saved} to exist"
    assert saved.read_text(encoding="utf-8") == raw_text


def test_plan_answer_saved_on_invalid_plan(tmp_path, monkeypatch):
    """Even when the plan is invalid (parse fails), the raw answer is saved for later explanation."""
    state_dir = _setup(tmp_path, monkeypatch)
    goal = _goal_file(tmp_path, "Build feature X")

    call_id_fail = "deadbeef1111"
    gw = FakeGateway([
        (call_id_fail, INVALID_PLAN),          # attempt 1: invalid
        ("validcall12345", VALID_PLAN_JSON),   # attempt 2: valid
    ])
    monkeypatch.setattr("stratos.__main__.Gateway", lambda tel: gw)
    monkeypatch.setattr("stratos.__main__.Telemetry", lambda p: None)

    main(["plan", "--goal-file", goal, "--tries", "2"])

    saved_fail = state_dir / "answers" / f"plan-{call_id_fail}.md"
    assert saved_fail.exists(), "failed plan raw answer must be saved"
    assert saved_fail.read_text(encoding="utf-8") == INVALID_PLAN

    saved_ok = state_dir / "answers" / "plan-validcall12345.md"
    assert saved_ok.exists()
    assert saved_ok.read_text(encoding="utf-8") == VALID_PLAN_JSON


def test_all_attempts_save_answers(tmp_path, monkeypatch):
    """Every model call in the plan loop saves its raw text, keyed by its call_id."""
    state_dir = _setup(tmp_path, monkeypatch)
    goal = _goal_file(tmp_path, "Build feature Y")

    responses = [
        ("call1111aaaa", "not a plan"),
        ("call2222bbbb", "still not a plan"),
        ("call3333cccc", VALID_PLAN_JSON),
    ]
    gw = FakeGateway(responses)
    monkeypatch.setattr("stratos.__main__.Gateway", lambda tel: gw)
    monkeypatch.setattr("stratos.__main__.Telemetry", lambda p: None)

    main(["plan", "--goal-file", goal, "--tries", "3"])

    answers_dir = state_dir / "answers"
    for cid, txt in responses:
        f = answers_dir / f"plan-{cid}.md"
        assert f.exists(), f"answer for {cid} not saved"
        assert f.read_text(encoding="utf-8") == txt


def test_filename_uses_call_id_from_gateway(tmp_path, monkeypatch):
    """The filename plan-<call_id>.md uses exactly the call_id returned by gw.chat."""
    state_dir = _setup(tmp_path, monkeypatch)
    goal = _goal_file(tmp_path, "Z")

    unique_id = "feedfacecafe"
    gw = FakeGateway([(unique_id, VALID_PLAN_JSON)])
    monkeypatch.setattr("stratos.__main__.Gateway", lambda tel: gw)
    monkeypatch.setattr("stratos.__main__.Telemetry", lambda p: None)

    main(["plan", "--goal-file", goal])

    answers = list((state_dir / "answers").glob("plan-*.md"))
    assert len(answers) == 1
    assert answers[0].name == f"plan-{unique_id}.md"


def test_answer_content_is_raw_no_trim(tmp_path, monkeypatch):
    """The saved file contains the raw text exactly, preserving whitespace."""
    state_dir = _setup(tmp_path, monkeypatch)
    goal = _goal_file(tmp_path, "W")

    raw = "  \n  {\"key\":\"1\",\"title\":\"T\",\"goal\":\"G\",\"files\":[],\"tests\":[]}\n  "
    cid = "1000000000ab"
    gw = FakeGateway([(cid, raw)])
    monkeypatch.setattr("stratos.__main__.Gateway", lambda tel: gw)
    monkeypatch.setattr("stratos.__main__.Telemetry", lambda p: None)
    # parse_plan will succeed on the stripped version
    # (P010: a task always has a test file, as parse_plan requires; check_new_tests reads the first one)
    monkeypatch.setattr("stratos.plan.parse_plan", lambda text: [{"key": "1", "title": "T", "goal": "G",
                                                                   "files": [], "tests": ["tests/test_t.py"]}])

    main(["plan", "--goal-file", goal])

    saved = state_dir / "answers" / f"plan-{cid}.md"
    assert saved.read_text(encoding="utf-8") == raw


# ---- was test_cli_plan_tests.py ----
# Tests for `stratos plan-tests <plan id>` (plan P003, task plantests_cli).
#
# It calls plantests.draft_tests(gw, plan_id, config.REPO, config.STATE_DIR) with
# gw = Gateway(Telemetry(config.STATE_DIR / "telemetry.jsonl")), prints f"{key} {file}: {status}" for each result and
# returns 0. An unknown plan id (draft_tests raises KeyError) prints "no such plan: <id>" on stderr and returns 1.


def setup(tmp_path, monkeypatch, result):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    made, calls = [], []

    class FakeGateway:
        def __init__(self, telemetry):
            self.telemetry = telemetry
            made.append(self)
    monkeypatch.setattr(cli, "Gateway", FakeGateway)

    def fake_draft(gw, plan_id, root, state_dir, log=print):
        calls.append((gw, plan_id, root, state_dir))
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(plantests, "draft_tests", fake_draft)
    return made, calls


def test_prints_the_results(tmp_path, monkeypatch, capsys):
    made, calls = setup(tmp_path, monkeypatch, [{"key": "core", "file": "tests/test_m.py", "status": "import_error"},
                                                {"key": "cli", "file": "tests/test_c.py", "status": "exists"}])
    assert cli.main(["plan-tests", "P003"]) == 0
    gw, pid, root, state = calls[0]
    assert gw is made[0] and str(gw.telemetry.path).endswith("telemetry.jsonl")
    assert (pid, root, state) == ("P003", config.REPO, config.STATE_DIR)
    out = capsys.readouterr().out
    assert "core tests/test_m.py: import_error" in out and "cli tests/test_c.py: exists" in out


def test_unknown_plan(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, KeyError("P404"))
    assert cli.main(["plan-tests", "P404"]) == 1
    assert "no such plan: P404" in capsys.readouterr().err
