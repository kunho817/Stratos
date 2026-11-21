"""Tests for task T061: stratos/plan.py, the planner's pure parts: the prompt, reading and checking a plan, keeping
plans on disk. A plan splits a feature goal into Stratos tasks; a person checks it before it is added (T062).

SYSTEM: the planner's system prompt (a str). It asks for JSON only, describes the task fields below, and says each
    task should be small (one function or one file), name its test files under tests/, and list in "after" the keys
    of earlier tasks it builds on.
repo_summary(root) -> str
    One line per .py file directly in root/"stratos", sorted by name: "stratos/<name> - <first line of its module
    docstring>" (ast.get_docstring), or "stratos/<name>" when it has none; then one line per .py file directly in
    root/"tests", sorted: "tests/<name>". Lines joined with "\n".
build_messages(goal, summary) -> [{"role": "system", "content": SYSTEM},
                                  {"role": "user", "content": f"PROJECT FILES:\n{summary}\n\nFEATURE GOAL:\n{goal}"}]
parse_plan(text) -> list of task dicts; raises PlanError (a ValueError) with a readable reason.
    The JSON is the last ```json fenced block in text when there is one, else the text from the first "{" to the
    last "}". It must be an object whose "tasks" is a non-empty list. Each task: "title" and "goal" non-empty strings;
    "files" a non-empty list of strings; "tests" a non-empty list of strings that start with "tests/" and end with
    ".py"; optional "protected" (list of strings, default []), "after" (list of keys of EARLIER tasks, default []),
    "role" ("coder", "coder_hard" or null; default None), "key" (string; default str(position), counting from 1).
    Keys must be unique. A reason names the task's key when one task is wrong. Returned dicts have exactly the keys
    key, title, goal, files, tests, protected, after, role.
PlanError
plan_hash(tasks) -> hashlib.sha256(json.dumps(tasks, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
save_plan(state_dir, goal, tasks) -> plan id
    Writes state_dir/"plans"/f"{pid}.json" (folder made when missing), pid = f"P{n:03d}" with n = number of .json
    files already there + 1, content {"id", "goal", "tasks", "status": "draft", "hash": plan_hash(tasks)} as UTF-8
    JSON (indent 1, ensure_ascii False).
load_plan(state_dir, pid) -> the dict; KeyError(pid) when the file does not exist.
edited(plan) -> plan_hash(plan["tasks"]) != plan["hash"]  (a person changed the tasks after the planner wrote them)
mark_added(state_dir, pid, task_ids) -> sets "status": "added" and "task_ids": task_ids (key -> task id) in the file."""
import json
import re

import pytest

from stratos import __main__ as cli, codemap, config, embed, memstore, plan, recall


GOOD = {"tasks": [
    {"key": "a", "title": "Add f", "goal": "Add f to x.", "files": ["stratos/x.py"], "tests": ["tests/test_x.py"]},
    {"key": "b", "title": "Use f", "goal": "Call f in y.", "files": ["stratos/y.py"], "tests": ["tests/test_y.py"],
     "protected": ["stratos/x.py"], "after": ["a"], "role": "coder_hard"},
]}


def test_system_prompt():
    assert isinstance(plan.SYSTEM, str) and "JSON" in plan.SYSTEM
    for word in ("title", "goal", "files", "tests", "after", "tests/"):
        assert word in plan.SYSTEM


def test_repo_summary(tmp_path):
    (tmp_path / "stratos").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "stratos" / "b.py").write_text('"""Bee module.\n\nMore text."""\nX = 1\n', encoding="utf-8")
    (tmp_path / "stratos" / "a.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "stratos" / "notes.txt").write_text("not python", encoding="utf-8")
    (tmp_path / "tests" / "test_b.py").write_text("", encoding="utf-8")
    (tmp_path / "tests" / "test_a.py").write_text("", encoding="utf-8")
    assert plan.repo_summary(tmp_path) == "stratos/a.py\nstratos/b.py - Bee module.\ntests/test_a.py\ntests/test_b.py"


def test_build_messages():
    msgs = plan.build_messages("Make it fly.", "stratos/a.py")
    assert msgs == [{"role": "system", "content": plan.SYSTEM},
                    {"role": "user", "content": "PROJECT FILES:\nstratos/a.py\n\nFEATURE GOAL:\nMake it fly."}]


def test_parse_a_fenced_plan_and_defaults():
    text = "Here is the plan.\n```json\n" + json.dumps(GOOD) + "\n```\n"
    tasks = plan.parse_plan(text)
    assert tasks[0] == {"key": "a", "title": "Add f", "goal": "Add f to x.", "files": ["stratos/x.py"],
                        "tests": ["tests/test_x.py"], "protected": [], "after": [], "role": None}
    assert tasks[1]["after"] == ["a"] and tasks[1]["role"] == "coder_hard" and tasks[1]["protected"] == ["stratos/x.py"]


def test_last_fenced_block_wins_and_bare_json_works():
    draft = {"tasks": [{"title": "Old", "goal": "g", "files": ["f.py"], "tests": ["tests/t.py"]}]}
    text = "```json\n" + json.dumps(draft) + "\n```\nBetter:\n```json\n" + json.dumps(GOOD) + "\n```"
    assert [t["key"] for t in plan.parse_plan(text)] == ["a", "b"]
    bare = "Sure! " + json.dumps({"tasks": [{"title": "T", "goal": "g", "files": ["f.py"], "tests": ["tests/t.py"]},
                                            {"title": "U", "goal": "h", "files": ["g.py"], "tests": ["tests/u.py"],
                                             "after": ["1"]}]}) + " Done."
    tasks = plan.parse_plan(bare)
    assert [t["key"] for t in tasks] == ["1", "2"] and tasks[1]["after"] == ["1"]


@pytest.mark.parametrize("change, word", [
    (lambda p: p.update(tasks=[]), "tasks"),
    (lambda p: p["tasks"][0].update(title=""), "a"),
    (lambda p: p["tasks"][0].pop("goal"), "a"),
    (lambda p: p["tasks"][1].update(files=[]), "b"),
    (lambda p: p["tasks"][1].update(tests=["test_y.py"]), "b"),
    (lambda p: p["tasks"][1].update(tests=["tests/test_y.txt"]), "b"),
    (lambda p: p["tasks"][1].update(after=["zz"]), "b"),
    (lambda p: p["tasks"][0].update(after=["b"]), "a"),
    (lambda p: p["tasks"][1].update(role="reviewer"), "b"),
    (lambda p: p["tasks"][1].update(key="a"), "a"),
])
def test_bad_plans_are_refused(change, word):
    bad = json.loads(json.dumps(GOOD))
    change(bad)
    with pytest.raises(plan.PlanError) as e:
        plan.parse_plan(json.dumps(bad))
    assert word in str(e.value)
    assert isinstance(e.value, ValueError)


def test_no_json_at_all():
    with pytest.raises(plan.PlanError):
        plan.parse_plan("I cannot plan this.")
    with pytest.raises(plan.PlanError):
        plan.parse_plan("```json\n{not json}\n```")
    with pytest.raises(plan.PlanError):
        plan.parse_plan("[1, 2]")


def test_save_load_edit_and_mark(tmp_path):
    tasks = plan.parse_plan(json.dumps(GOOD))
    pid = plan.save_plan(tmp_path, "Make it fly.", tasks)
    assert pid == "P001"
    assert plan.save_plan(tmp_path, "Another.", tasks[:1]) == "P002"
    p = plan.load_plan(tmp_path, "P001")
    assert p["id"] == "P001" and p["goal"] == "Make it fly." and p["tasks"] == tasks and p["status"] == "draft"
    assert p["hash"] == plan.plan_hash(tasks) and not plan.edited(p)
    path = tmp_path / "plans" / "P001.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tasks"][0]["title"] = "Add f, carefully"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert plan.edited(plan.load_plan(tmp_path, "P001"))
    plan.mark_added(tmp_path, "P001", {"a": "T010", "b": "T011"})
    p = plan.load_plan(tmp_path, "P001")
    assert p["status"] == "added" and p["task_ids"] == {"a": "T010", "b": "T011"}
    assert p["tasks"][0]["title"] == "Add f, carefully"
    with pytest.raises(KeyError):
        plan.load_plan(tmp_path, "P009")


def test_plan_hash():
    import hashlib
    tasks = [{"key": "1", "title": "한글"}]
    want = hashlib.sha256(json.dumps(tasks, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    assert plan.plan_hash(tasks) == want


# ---- was test_plan_fix.py ----
# Tests for task plan_fix: the plan's mechanical rules are fixed by code instead of sent back (Ledger round 2).
#
# Swift planned Ledger round 2 three times and every time gave tasks an existing test file first (it extends modules,
# so it extends their test files), and once wrote "After: T004", a past task's id it saw in the memory pack.
#
# plan.fix_new_tests(tasks, root, settings=None) -> list of messages; it changes tasks in place. settings None ->
# config.PROJECT. For each task in order, first = task["tests"][0]: when Path(root, first) exists or an earlier task
# already starts with the same file, a new file name is put in front of task["tests"]: slug = the task key lowercased
# with every run of characters other than a-z and 0-9 replaced by "_" and "_" stripped at both ends; suffix =
# settings["test_suffixes"][0]; the name is f"{test_dir}/test_{slug}.py" when suffix is ".py", else
# f"{test_dir}/{slug}{suffix}"; when that name exists or is already some task's test file, "_2", "_3", ... is added
# to the slug until it is free. The message is f"Task {key}: added the new test file {name} ({first} already
# existed)" or f"Task {key}: added the new test file {name} ({first} is task {other}'s first test file)".
#
# plan.parse_text_plan: an After item that is not a key of an earlier task but matches ^T\d+$ (a past task's id) is
# dropped instead of refused.
#
# `stratos plan`: after a plan is read, it calls fix_new_tests(tasks, config.REPO) instead of check_new_tests and
# prints each message; the plan is saved with the fixed test lists.


PY = {"test_dir": "tests", "test_suffixes": [".py"]}


JS = {"test_dir": "tests", "test_suffixes": [".test.js"]}


def task(key, tests):
    return {"key": key, "title": "t", "goal": "g", "files": ["src/a.py"], "tests": list(tests)}


def test_an_existing_first_file_gets_a_new_one(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_cli.py").write_text("", encoding="utf-8")
    tasks = [task("CLI new-commands", ["tests/test_cli.py"]), task("b", ["tests/test_b.py"])]
    msgs = plan.fix_new_tests(tasks, tmp_path, PY)
    assert tasks[0]["tests"] == ["tests/test_cli_new_commands.py", "tests/test_cli.py"]
    assert tasks[1]["tests"] == ["tests/test_b.py"]
    assert msgs == ["Task CLI new-commands: added the new test file tests/test_cli_new_commands.py "
                    "(tests/test_cli.py already existed)"]


def test_a_shared_first_file_and_a_taken_name(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("", encoding="utf-8")
    tasks = [task("a", ["tests/test_y.py"]), task("x", ["tests/test_y.py"])]
    msgs = plan.fix_new_tests(tasks, tmp_path, PY)
    assert tasks[1]["tests"] == ["tests/test_x_2.py", "tests/test_y.py"]
    assert msgs == ["Task x: added the new test file tests/test_x_2.py (tests/test_y.py is task a's first test file)"]


def test_js_names(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "towers.test.js").write_text("", encoding="utf-8")
    tasks = [task("tower_levels", ["tests/towers.test.js"])]
    plan.fix_new_tests(tasks, tmp_path, JS)
    assert tasks[0]["tests"] == ["tests/tower_levels.test.js", "tests/towers.test.js"]


def test_nothing_to_fix(tmp_path):
    tasks = [task("a", ["tests/test_a.py"])]
    assert plan.fix_new_tests(tasks, tmp_path, PY) == [] and tasks[0]["tests"] == ["tests/test_a.py"]


def test_settings_default_to_the_project(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "test_dir": "tests", "test_suffixes": [".test.js"]})
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "a.test.js").write_text("", encoding="utf-8")
    tasks = [task("k", ["tests/a.test.js"])]
    plan.fix_new_tests(tasks, tmp_path)
    assert tasks[0]["tests"][0] == "tests/k.test.js"


def test_past_task_ids_in_after_are_dropped():
    text = ("Key: a\nTitle: A\nGoal: g\nFiles: stratos/a.py\nTests: tests/test_a.py\nAfter: T004\n\n"
            "Key: b\nTitle: B\nGoal: g\nFiles: stratos/b.py\nTests: tests/test_b.py\nAfter: a, T012\n")
    tasks = plan.parse_text_plan(text)
    assert [t["after"] for t in tasks] == [[], ["a"]]


# ---- was test_plan_memory.py ----
# Tests for task plan_memory: the planner gets a context pack from memory (memory M5).
#
# config.MEMORY = True by default (tests turn it off in conftest unless they turn it on).
#
# plan.build_messages(goal, summary, conventions=None, system=None, uses=None, memory=None): a non-empty memory adds
# the part "
#
# MEMORY (found for this goal in the project's code, tests, past tasks and people's corrections):
# " +
# memory right after the WHO USES WHAT part (or after PROJECT FILES when there is none), before the conventions.
#
# `stratos plan`: cmap = codemap.build(config.REPO) once (uses = codemap.uses_summary(cmap) as before). When
# config.MEMORY is on and config.STATE_DIR / "memory.db" exists: store = memstore.Store(that path), memory =
# recall.pack(store, goal, embed.Embedder(), cmap), store closed (all through the modules). Any exception there is
# printed to stderr as f"memory: {e}" and the plan goes on with memory None. Off, or no memory.db: memory None.


HEAD = "MEMORY (found for this goal in the project's code, tests, past tasks and people's corrections):\n"


ANSWER = '{"tasks": [{"key": "a", "title": "T", "goal": "G", "files": ["stratos/x.py"], "tests": ["tests/test_n.py"]}]}'


def test_build_messages_with_memory():
    user = plan.build_messages("G", "S", conventions="C", uses="U", memory="M")[1]["content"]
    assert user == ("PROJECT FILES:\nS\n\nWHO USES WHAT (when a task changes a name, every user listed here must be "
                    "changed or checked too):\nU\n\n" + HEAD + "M\n\nPROJECT CONVENTIONS:\nC\n\nFEATURE GOAL:\nG")
    assert plan.build_messages("G", "S", memory="M")[1]["content"] == "PROJECT FILES:\nS\n\n" + HEAD + "M\n\nFEATURE GOAL:\nG"
    assert plan.build_messages("G", "S", memory="") == plan.build_messages("G", "S")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "REPO", tmp_path / "repo")
    (tmp_path / "repo").mkdir()
    (tmp_path / "state").mkdir()
    monkeypatch.setattr(plan, "repo_summary", lambda root: "SUMMARY")
    builds = []
    monkeypatch.setattr(codemap, "build", lambda root: builds.append(root) or {"test_dir": "tests", "files": {}})
    monkeypatch.setattr(codemap, "uses_summary", lambda cmap: "")
    seen = []

    class FakeGateway:
        def __init__(self, telemetry):
            self.telemetry = telemetry

        def ensure_model(self, model):
            return 0.0

        def chat(self, messages, **kw):
            seen.append(messages)
            return "c1", ANSWER
    monkeypatch.setattr(cli, "Gateway", FakeGateway)
    monkeypatch.setattr(embed, "Embedder", lambda: "EMB")
    # (task memory_refresh: `plan` refreshes the memory first; these tests are about the pack, so no refresh)
    from stratos import memindex
    monkeypatch.setattr(memindex, "refresh", lambda *a: {"chunks": 0, "changed": 0, "removed": 0, "embedded": 0},
                        raising=False)
    goal = tmp_path / "goal.txt"
    goal.write_text("Make it fly.", encoding="utf-8")
    return seen, builds, goal


def test_the_plan_gets_the_pack(env, monkeypatch):
    seen, builds, goal = env
    monkeypatch.setattr(config, "MEMORY", True)
    memstore.Store(config.STATE_DIR / "memory.db").close()
    packs = []
    monkeypatch.setattr(recall, "pack", lambda store, query, embedder, cmap, always_tags=None: packs.append(
        (query, embedder, cmap, always_tags)) or "PACK")
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    # (task recall_tags: the planner gets every "plan" lesson)
    assert packs == [("Make it fly.", "EMB", {"test_dir": "tests", "files": {}}, {"plan"})]
    assert len(builds) == 1
    assert seen[0] == plan.build_messages("Make it fly.", "SUMMARY", memory="PACK")


def test_no_memory_db(env, monkeypatch):
    seen, builds, goal = env
    monkeypatch.setattr(config, "MEMORY", True)
    monkeypatch.setattr(recall, "pack", lambda *a: pytest.fail("no memory.db, no recall"))
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    assert seen[0] == plan.build_messages("Make it fly.", "SUMMARY")


def test_memory_off(env, monkeypatch):
    seen, builds, goal = env
    monkeypatch.setattr(config, "MEMORY", False)
    memstore.Store(config.STATE_DIR / "memory.db").close()
    monkeypatch.setattr(recall, "pack", lambda *a: pytest.fail("memory is off"))
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0


def test_a_failing_recall_is_reported(env, monkeypatch, capsys):
    seen, builds, goal = env
    monkeypatch.setattr(config, "MEMORY", True)
    memstore.Store(config.STATE_DIR / "memory.db").close()

    def boom(*a, **k):
        raise RuntimeError("no model")
    monkeypatch.setattr(recall, "pack", boom)
    assert cli.main(["plan", "--goal-file", str(goal)]) == 0
    assert "memory: no model" in capsys.readouterr().err
    assert seen[0] == plan.build_messages("Make it fly.", "SUMMARY")


# ---- was test_plan_overlap.py ----
# Tests for task T065: plan.parse_plan refuses a task that lists the same path in "files" and "protected".
#
# The second real plan (P002) gave a task its own file as read-only too. A file the task writes cannot also be
# read-only, so parse_plan raises PlanError, naming the task's key and the path.


def test_overlap_is_refused():
    bad = {"tasks": [{"key": "draft", "title": "t", "goal": "g", "files": ["stratos/a.py", "stratos/b.py"],
                      "tests": ["tests/test_a.py"], "protected": ["stratos/c.py", "stratos/b.py"]}]}
    with pytest.raises(plan.PlanError) as e:
        plan.parse_plan(json.dumps(bad))
    assert "draft" in str(e.value) and "stratos/b.py" in str(e.value)


def test_no_overlap_is_fine():
    ok = {"tasks": [{"key": "k", "title": "t", "goal": "g", "files": ["stratos/a.py"], "tests": ["tests/test_a.py"],
                     "protected": ["stratos/c.py"]}]}
    assert plan.parse_plan(json.dumps(ok))[0]["protected"] == ["stratos/c.py"]


# ---- was test_plan_project.py ----
# Tests for task plan_js_and_test_paths: repo_summary accepts a settings dict with
# source_dirs, test_dir, test_suffixes; parse_plan accepts test paths starting with
# test_dir + "/" and ending with one of test_suffixes.
#
# repo_summary(root, settings=None)
#     settings is a dict with keys "source_dirs" (list of dir names), "test_dir" (str),
#     "test_suffixes" (list of str). settings=None means config.PROJECT.
#     For each dir in source_dirs, list files in root/<dir> sorted.
#     Python files: as before (docstring first line, def/class lines).
#     .js/.mjs files: "  export function name(args)" for each export function,
#     "  export class Name" for each export class (found by regex).
#     Then list files in root/<test_dir> whose name ends with any suffix in test_suffixes.
#
# parse_plan(text)
#     Uses config.PROJECT for test_dir and test_suffixes.
#     tests entries must start with test_dir + "/" and end with one of test_suffixes.
#     With Stratos defaults (test_dir="tests", test_suffixes=[".py"]) same as before.


def make_project(tmp_path, source_dirs, test_dir, test_suffixes, files):
    """Create a fake project tree under tmp_path. Returns tmp_path."""
    for d in source_dirs:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    (tmp_path / test_dir).mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp_path


def test_repo_summary_accepts_settings_parameter(tmp_path):
    """repo_summary(root, settings=...) should work, not raise TypeError."""
    tmp = make_project(
        tmp_path=tmp_path,
        source_dirs=["src"],
        test_dir="test",
        test_suffixes=[".py"],
        files={"src/a.py": '"""Module A."""\ndef foo():\n    pass\n',
               "test/test_a.py": "import a\n"},
    )
    settings = {"source_dirs": ["src"], "test_dir": "test", "test_suffixes": [".py"]}
    out = plan.repo_summary(tmp, settings=settings)
    assert "src/a.py - Module A." in out
    assert "  def foo()" in out
    assert "test/test_a.py" in out


def test_repo_summary_multiple_source_dirs(tmp_path):
    """All dirs in source_dirs are listed."""
    tmp = make_project(
        tmp_path=tmp_path,
        source_dirs=["lib", "core"],
        test_dir="tests",
        test_suffixes=[".py"],
        files={
            "lib/x.py": '"""X."""\ndef bar():\n    pass\n',
            "core/y.py": '"""Y."""\nclass Baz:\n    pass\n',
            "tests/test_x.py": "",
        },
    )
    settings = {"source_dirs": ["lib", "core"], "test_dir": "tests", "test_suffixes": [".py"]}
    out = plan.repo_summary(tmp, settings=settings)
    assert "lib/x.py - X." in out
    assert "core/y.py - Y." in out
    assert "  def bar()" in out
    assert "  class Baz" in out
    assert "tests/test_x.py" in out


def test_repo_summary_js_export_function(tmp_path):
    """A .js file lists export functions as '  export function name(args)'."""
    js_content = """\
import foo from './foo.js';

export function hello(name) {
  return name;
}

export function add(a, b) {
  return a + b;
}

export default hello;
"""
    tmp = make_project(
        tmp_path=tmp_path,
        source_dirs=["app"],
        test_dir="tests",
        test_suffixes=[".py"],
        files={"app/util.js": js_content, "tests/test_x.py": ""},
    )
    settings = {"source_dirs": ["app"], "test_dir": "tests", "test_suffixes": [".py"]}
    out = plan.repo_summary(tmp, settings=settings)
    assert "app/util.js" in out
    assert "  export function hello(name)" in out
    assert "  export function add(a, b)" in out


def test_repo_summary_mjs_export_class(tmp_path):
    """A .mjs file lists export class as '  export class Name'."""
    mjs_content = """\
export class MyWidget extends Base {
  constructor() {}
}

export function helper() {}
"""
    tmp = make_project(
        tmp_path=tmp_path,
        source_dirs=["app"],
        test_dir="tests",
        test_suffixes=[".py"],
        files={"app/widget.mjs": mjs_content, "tests/test_x.py": ""},
    )
    settings = {"source_dirs": ["app"], "test_dir": "tests", "test_suffixes": [".py"]}
    out = plan.repo_summary(tmp, settings=settings)
    assert "app/widget.mjs" in out
    assert "  export class MyWidget" in out
    assert "  export function helper()" in out


def test_repo_summary_test_suffixes_js(tmp_path):
    """test_dir listing includes files matching any suffix in test_suffixes."""
    tmp = make_project(
        tmp_path=tmp_path,
        source_dirs=["app"],
        test_dir="spec",
        test_suffixes=[".js", ".py"],
        files={
            "app/main.py": '"""Main."""\n',
            "spec/test_main.js": "",
            "spec/test_main.py": "",
            "spec/other.txt": "",
        },
    )
    settings = {"source_dirs": ["app"], "test_dir": "spec", "test_suffixes": [".js", ".py"]}
    out = plan.repo_summary(tmp, settings=settings)
    assert "spec/test_main.js" in out
    assert "spec/test_main.py" in out
    assert "spec/other.txt" not in out


def test_repo_summary_default_settings_is_config_project(monkeypatch, tmp_path):
    """When settings=None, use config.PROJECT."""
    proj = {"source_dirs": ["mylib"], "test_dir": "mytests", "test_suffixes": [".py"]}
    monkeypatch.setattr(config, "PROJECT", proj)
    (tmp_path / "mylib").mkdir()
    (tmp_path / "mytests").mkdir()
    (tmp_path / "mylib" / "a.py").write_text('"""A."""\ndef foo():\n    pass\n', encoding="utf-8")
    (tmp_path / "mytests" / "test_a.py").write_text("", encoding="utf-8")
    out = plan.repo_summary(tmp_path)
    assert "mylib/a.py - A." in out
    assert "mytests/test_a.py" in out


def test_repo_summary_stratos_defaults_unchanged(tmp_path):
    """With Stratos defaults (source_dirs=["stratos"], test_dir="tests", test_suffixes=[".py"]),
    the output matches the old behaviour."""
    tmp = make_project(
        tmp_path=tmp_path,
        source_dirs=["stratos"],
        test_dir="tests",
        test_suffixes=[".py"],
        files={
            "stratos/foo.py": '"""Foo module."""\ndef bar(x):\n    pass\nclass Baz:\n    pass\n',
            "tests/test_foo.py": "",
        },
    )
    settings = {"source_dirs": ["stratos"], "test_dir": "tests", "test_suffixes": [".py"]}
    out = plan.repo_summary(tmp, settings=settings)
    assert "stratos/foo.py - Foo module." in out
    assert "  def bar(x)" in out
    assert "  class Baz" in out
    assert "tests/test_foo.py" in out


def test_parse_plan_accepts_test_dir_prefix(tmp_path, monkeypatch):
    """parse_plan validates tests against config.PROJECT test_dir prefix."""
    proj = {"source_dirs": ["stratos"], "test_dir": "mytests", "test_suffixes": [".py"]}
    monkeypatch.setattr(config, "PROJECT", proj)
    tasks = [{"key": "T1", "title": "x", "goal": "g",
             "files": ["src/a.py"], "tests": ["mytests/test_a.py"],
             "protected": [], "after": [], "role": "coder"}]
    text = json.dumps({"tasks": tasks})
    result = plan.parse_plan(text)
    assert result[0]["tests"] == ["mytests/test_a.py"]


def test_parse_plan_rejects_wrong_test_dir(tmp_path, monkeypatch):
    """Tests not starting with test_dir + '/' are rejected."""
    proj = {"source_dirs": ["stratos"], "test_dir": "mytests", "test_suffixes": [".py"]}
    monkeypatch.setattr(config, "PROJECT", proj)
    tasks = [{"key": "T1", "title": "x", "goal": "g",
             "files": ["src/a.py"], "tests": ["tests/test_a.py"],
             "protected": [], "after": [], "role": "coder"}]
    text = json.dumps({"tasks": tasks})
    with pytest.raises(plan.PlanError):
        plan.parse_plan(text)


def test_parse_plan_accepts_js_test_suffix(tmp_path, monkeypatch):
    """parse_plan accepts tests ending with .js when .js is in test_suffixes."""
    proj = {"source_dirs": ["app"], "test_dir": "spec", "test_suffixes": [".js", ".py"]}
    monkeypatch.setattr(config, "PROJECT", proj)
    tasks = [{"key": "T1", "title": "x", "goal": "g",
             "files": ["app/a.py"], "tests": ["spec/test_a.js"],
             "protected": [], "after": [], "role": "coder"}]
    text = json.dumps({"tasks": tasks})
    result = plan.parse_plan(text)
    assert result[0]["tests"] == ["spec/test_a.js"]


def test_parse_plan_rejects_unknown_suffix(tmp_path, monkeypatch):
    """Tests with a suffix not in test_suffixes are rejected."""
    proj = {"source_dirs": ["app"], "test_dir": "spec", "test_suffixes": [".py"]}
    monkeypatch.setattr(config, "PROJECT", proj)
    tasks = [{"key": "T1", "title": "x", "goal": "g",
             "files": ["app/a.py"], "tests": ["spec/test_a.js"],
             "protected": [], "after": [], "role": "coder"}]
    text = json.dumps({"tasks": tasks})
    with pytest.raises(plan.PlanError):
        plan.parse_plan(text)


def test_parse_plan_stratos_defaults_same_as_before():
    """With Stratos defaults the rule is tests/ + .py, same as the existing tests."""
    tasks = [{"key": "T1", "title": "x", "goal": "g",
             "files": ["stratos/a.py"], "tests": ["tests/test_a.py"],
             "protected": [], "after": [], "role": "coder"}]
    text = json.dumps({"tasks": tasks})
    result = plan.parse_plan(text)
    assert result[0]["tests"] == ["tests/test_a.py"]


# ---- was test_plan_rules.py ----
# Tests for task T063: plan.SYSTEM teaches the planner Stratos's own task rules.
#
# The first real plan (P001, 2026-11-18) broke them: five tasks wrote the same new file with no "after" between them
# (their branches would conflict), one-line helpers were whole tasks, one task's only file was a test file, and a
# function that calls the model did not take the gateway. SYSTEM now holds these sentences, word for word:


RULES = [
    "Tasks that write the same file must be chained: each one lists the previous one in \"after\".",
    "The tests of a task are written before the task runs, so never make a task whose files are only test files.",
    "Keep related small functions of one module in one task; a task should be worth a model call and a review.",
    "A function that calls a model takes the gateway as a parameter (gw), so tests can pass a fake.",
    "Prefer 2 to 6 tasks for a feature.",
]


def test_rules_are_in_the_system_prompt():
    for rule in RULES:
        assert rule in plan.SYSTEM


def test_the_format_is_still_described():
    for word in ("JSON", "title", "goal", "files", "tests", "after", "protected", "role", "tests/"):
        assert word in plan.SYSTEM


# ---- was test_plan_summary.py ----
# Tests for task T064: plan.repo_summary also lists each stratos module's public functions and classes.
#
# The second real plan (P002) invented APIs (load_plan in state.py, gw.ask) because the planner only saw each module's
# first docstring line. Now, right after a module's line, repo_summary adds one line per top-level public definition,
# in file order: "  def <name>(<ast.unparse(node.args)>)" for a function (async ones too), "  class <name>" for a
# class. Names starting with "_" are left out. Test files are still listed by name only.


SOURCE = '''"""Mod docstring."""
import os

X = 1


def load(state_dir, pid, *, strict=False):
    return 1


def _private(a):
    return a


class Store:
    def method(self):
        pass


async def fetch(url, timeout=10):
    return url
'''


def test_signatures_follow_the_module_line(tmp_path):
    (tmp_path / "stratos").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "stratos" / "m.py").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "stratos" / "a.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_m.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    assert plan.repo_summary(tmp_path) == "\n".join([
        "stratos/a.py",
        "stratos/m.py - Mod docstring.",
        "  def load(state_dir, pid, *, strict=False)",
        "  class Store",
        "  def fetch(url, timeout=10)",
        "tests/test_m.py",
    ])


def test_a_file_that_does_not_parse_is_listed_alone(tmp_path):
    (tmp_path / "stratos").mkdir()
    (tmp_path / "stratos" / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    assert plan.repo_summary(tmp_path) == "stratos/bad.py"


def test_the_real_project_shows_real_apis():
    from stratos import config
    s = plan.repo_summary(config.REPO)
    assert "  def load_plan(state_dir, pid)" in s
    assert "  class Gateway" in s
    assert "  def chat(" not in s              # methods are not top-level definitions


# ---- was test_plan_text.py ----
# Tests for task T075: plan.parse_text_plan(text), reading a plan the planner wrote as text (plan.TEXT_SYSTEM).
#
# AgentWorld, asked to turn such text into JSON, copied goals that hold double quotes without escaping them and broke
# the JSON twice (2026-11-18). The format is regular, so code reads it:
#
# - A line "<Field>: <value>" starts a field, for the fields Key, Title, Goal, Files, Tests, Protected, After, Role
#   (case as written). The label may be preceded by spaces, "-", "*", "#" or wrapped in "**" (e.g. "**Key:**" or
#   "- Key:"). A line that starts no field continues the previous field's value (joined with "
# "); blank lines end
#   nothing. Each "Key:" line starts a new task; text before the first "Key:" is ignored.
# - Values are stripped. Files, Tests, Protected and After are comma-separated lists; items are stripped, surrounding
#   backticks are removed, empty items dropped. Role "coder" or "coder_hard" (backticks removed); anything else
#   (empty, "none", "null", "-") is None. Missing fields are left out, so parse_plan's defaults and checks apply.
# - The tasks are then checked exactly like a JSON plan: the result is parse_plan(json.dumps({"tasks": [...]})), so its
#   PlanError reasons apply (for example an "after" key that is not earlier).
# - No "Key:" line at all raises PlanFormatError (a subclass of PlanError): the text is not in the format.


TEXT = '''Here is my plan.

Key: summary
Title: plan_summary in report.py
Goal: Add a pure function plan_summary(plans, events). Count "test_draft" events
by their "status" field.
Files: stratos/report.py
Tests: tests/test_report_plans.py
Protected: stratos/plan.py, `stratos/telemetry.py`
After:
Role: coder

- **Key:** cli
- **Title:** stratos report --plans
- **Goal:** Print "no plans yet" when there are none.
- **Files:** `stratos/__main__.py`
- **Tests:** tests/test_cli_report_plans.py
- **Protected:** stratos/report.py
- **After:** summary
- **Role:** `coder_hard`
'''


def test_reads_both_styles():
    tasks = plan.parse_text_plan(TEXT)
    assert tasks == [
        {"key": "summary", "title": "plan_summary in report.py",
         "goal": 'Add a pure function plan_summary(plans, events). Count "test_draft" events\nby their "status" field.',
         "files": ["stratos/report.py"], "tests": ["tests/test_report_plans.py"],
         "protected": ["stratos/plan.py", "stratos/telemetry.py"], "after": [], "role": "coder"},
        {"key": "cli", "title": "stratos report --plans", "goal": 'Print "no plans yet" when there are none.',
         "files": ["stratos/__main__.py"], "tests": ["tests/test_cli_report_plans.py"],
         "protected": ["stratos/report.py"], "after": ["summary"], "role": "coder_hard"},
    ]


@pytest.mark.parametrize("role", ["", "none", "null", "-", "anything"])
def test_other_roles_are_none(role):
    text = f"Key: a\nTitle: t\nGoal: g\nFiles: stratos/a.py\nTests: tests/test_a.py\nRole: {role}\n"
    assert plan.parse_text_plan(text)[0]["role"] is None


def test_missing_optional_fields_use_the_defaults():
    tasks = plan.parse_text_plan("Key: a\nTitle: t\nGoal: g\nFiles: stratos/a.py, , stratos/b.py\nTests: tests/test_a.py")
    assert tasks[0]["files"] == ["stratos/a.py", "stratos/b.py"]
    assert (tasks[0]["protected"], tasks[0]["after"], tasks[0]["role"]) == ([], [], None)


def test_plan_checks_still_apply():
    bad = "Key: a\nTitle: t\nGoal: g\nFiles: stratos/a.py\nTests: tests/test_a.py\nAfter: zz\n"
    with pytest.raises(plan.PlanError) as e:
        plan.parse_text_plan(bad)
    assert not isinstance(e.value, plan.PlanFormatError) and "zz" in str(e.value)
    with pytest.raises(plan.PlanError):
        plan.parse_text_plan("Key: a\nTitle: t\nGoal: g\nFiles: tests/test_a.py\nTests: tests/test_b.py\n")


def test_not_the_format():
    for text in ["", "I could not plan this.", '{"tasks": []}']:
        with pytest.raises(plan.PlanFormatError):
            plan.parse_text_plan(text)
    assert issubclass(plan.PlanFormatError, plan.PlanError)


def test_none_words_in_list_fields_mean_empty():
    """Memory A/B (2026-11-19): 4 of 9 plans failed because Swift wrote "After: none" or "After: (none)". In the list
    fields (Files, Tests, Protected, After) an item that is, case-insensitively, one of none, (none), -, n/a, nothing,
    [] is dropped, so such a field is empty."""
    text = ("Key: a\nTitle: A\nGoal: g\nFiles: stratos/a.py\nTests: tests/test_a.py\nProtected: None\nAfter: none\n\n"
            "Key: b\nTitle: B\nGoal: g\nFiles: stratos/b.py\nTests: tests/test_b.py\nProtected: -\nAfter: (none)\n\n"
            "Key: c\nTitle: C\nGoal: g\nFiles: stratos/c.py\nTests: tests/test_c.py\nProtected: n/a\nAfter: a, b, []\n")
    tasks = plan.parse_text_plan(text)
    assert [(t["key"], t["protected"], t["after"]) for t in tasks] == [("a", [], []), ("b", [], []), ("c", [], ["a", "b"])]


# ---- was test_plan_two_stage.py ----
# Tests for task T071: plan.py for two-stage planning and the project's conventions, and a stricter parse_plan.
#
# An offline comparison (2026-11-18, three feature goals) found that plans improve when the planner sees the project's
# conventions (CONVENTIONS.md) and writes the plan as text that AgentWorld turns into JSON; and that every variant
# still made tasks whose only files are test files, which the prompt rules did not stop.
#
# - parse_plan refuses a task whose files are all under "tests/", and a task whose files include one of its own
#   "tests" paths (tests are written before the task runs). The PlanError names the task's key.
# - build_messages(goal, summary, conventions=None, system=None): system None means SYSTEM. When conventions is given,
#   the user content is f"PROJECT FILES:
# {summary}
#
# PROJECT CONVENTIONS:
# {conventions}
#
# FEATURE GOAL:
# {goal}";
#   without it, as before.
# - TEXT_SYSTEM: the planner prompt for the text stage. It asks for plain text, no JSON, one block per task with the
#   lines "Key:", "Title:", "Goal:", "Files:", "Tests:", "Protected:", "After:" and "Role:", explains them like SYSTEM
#   does, and holds the same rule sentences as SYSTEM (every line of SYSTEM from "Tasks that write the same file" on).
# - CONVERT_SYSTEM: the converter prompt: turn the plan text into JSON {"tasks": [...]} with the fields key, title,
#   goal, files, tests, protected, after, role; copy every goal word for word; answer with JSON only.
# - convert_messages(text) -> [{"role": "system", "content": CONVERT_SYSTEM}, {"role": "user", "content": text}].


def one(**task):
    base = {"key": "k", "title": "t", "goal": "g", "files": ["stratos/a.py"], "tests": ["tests/test_a.py"]}
    base.update(task)
    return json.dumps({"tasks": [base]})


def test_a_task_of_only_test_files_is_refused():
    with pytest.raises(plan.PlanError) as e:
        plan.parse_plan(one(key="tests_only", files=["tests/test_a.py", "tests/test_b.py"], tests=["tests/test_c.py"]))
    assert "tests_only" in str(e.value)


def test_a_task_that_writes_its_own_tests_is_refused():
    with pytest.raises(plan.PlanError) as e:
        plan.parse_plan(one(key="mixed", files=["stratos/a.py", "tests/test_a.py"]))
    assert "mixed" in str(e.value) and "tests/test_a.py" in str(e.value)


def test_a_normal_task_still_passes():
    assert plan.parse_plan(one())[0]["files"] == ["stratos/a.py"]


def test_build_messages_with_conventions_and_system():
    msgs = plan.build_messages("Fly.", "stratos/a.py", conventions="Use gw.chat.")
    assert msgs[0] == {"role": "system", "content": plan.SYSTEM}
    assert msgs[1]["content"] == "PROJECT FILES:\nstratos/a.py\n\nPROJECT CONVENTIONS:\nUse gw.chat.\n\nFEATURE GOAL:\nFly."
    assert plan.build_messages("Fly.", "s", system=plan.TEXT_SYSTEM)[0]["content"] == plan.TEXT_SYSTEM
    assert plan.build_messages("Fly.", "s") == plan.build_messages("Fly.", "s", conventions=None, system=None)
    assert plan.build_messages("Fly.", "s")[1]["content"] == "PROJECT FILES:\ns\n\nFEATURE GOAL:\nFly."


def test_text_system():
    t = plan.TEXT_SYSTEM
    assert "plain text" in t and "no JSON" in t
    for field in ("Key:", "Title:", "Goal:", "Files:", "Tests:", "Protected:", "After:", "Role:"):
        assert field in t
    rules = plan.SYSTEM[plan.SYSTEM.index("Tasks that write the same file"):]
    for line in rules.splitlines():
        assert line in t


def test_convert_system_and_messages():
    c = plan.CONVERT_SYSTEM
    assert "JSON" in c and '"tasks"' in c and "word for word" in c
    for field in ("key", "title", "goal", "files", "tests", "protected", "after", "role"):
        assert field in c
    assert plan.convert_messages("Key: a\nTitle: x") == [{"role": "system", "content": c},
                                                         {"role": "user", "content": "Key: a\nTitle: x"}]
