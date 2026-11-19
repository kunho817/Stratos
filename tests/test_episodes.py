"""Tests for task episodes: past tasks and people's corrections become memory chunks (memory M3a).

episodes.episode(task, events) -> chunk {"id": f"episode:{id}", "kind": "episode", "source": "tasks.json",
"title": f"{id}: {title}", "text"}; events are the telemetry events of that task (any order kept as given). text is
"\n".join of these lines, each only when it has content:
  f"{id}: {title} ({status}, {attempts} attempts, role {role})"   (attempts = task.get("attempts", 0))
  "Goal: " + goal, cut to 600 characters
  "Files: " + ", ".join(files)
  "Results: " + ", ".join(f"{result} x{n}") over the "outcome" events' results in order of first appearance
  "Failing tests: " + ", ".join(the distinct ids decide._extract_ids finds in the "failed" outcomes' details, the
                    details in order and each one's ids in the (sorted) order _extract_ids gives, at most 8)
  "Review: " + detail cut to 300 characters, one line per "outcome" event with result "review_changes"
  "Triage: " + f"{verdict} - {reason}", one line per "triage" event
  "Reset by a person: " + reason, one line per "verdict" event with result "reset_by_human"
episodes.reset_lessons(task, events) -> one chunk per "verdict" event with result "reset_by_human", n = 1, 2, ...:
{"id": f"lesson:reset:{id}:{n}", "kind": "lesson", "source": "tasks.json", "title": f"{id}: {title}",
 "text": f"{id} {title}: {reason}"}.
episodes.history_chunks(tasks, events) -> for every task whose status is not "todo", in task order: its episode, then
its reset lessons; events are given to each task filtered by event["task"] == its id."""
from stratos import episodes

TASK = {"id": "T113", "title": "codemap: JS test calls are symbols", "goal": "G" * 700, "files": ["stratos/codemap.py"],
        "status": "done", "attempts": 4, "role": "coder_hard"}
EVENTS = [
    {"kind": "call", "task": "T113"},
    {"kind": "outcome", "task": "T113", "result": "failed",
     "detail": "FAILED tests/test_codemap_scan.py::test_a - x\nFAILED tests/test_codemap_end.py::test_b"},
    {"kind": "triage", "task": "T113", "verdict": "code_wrong", "test": "", "reason": "signature unset"},
    {"kind": "verdict", "task": "T113", "result": "reset_by_human", "reason": "named groups made \\3 the title"},
    {"kind": "outcome", "task": "T113", "result": "failed", "detail": "FAILED tests/test_codemap_scan.py::test_a"},
    {"kind": "outcome", "task": "T113", "result": "passed", "detail": "ok"},
    {"kind": "outcome", "task": "T113", "result": "review_changes", "detail": "- [low] R" * 100},
    {"kind": "verdict", "task": "T113", "result": "reset_by_human", "reason": "older tests pinned test(...)"},
]


def test_episode():
    c = episodes.episode(TASK, EVENTS)
    assert (c["id"], c["kind"], c["source"], c["title"]) == (
        "episode:T113", "episode", "tasks.json", "T113: codemap: JS test calls are symbols")
    assert c["text"].split("\n") == [
        "T113: codemap: JS test calls are symbols (done, 4 attempts, role coder_hard)",
        "Goal: " + "G" * 600,
        "Files: stratos/codemap.py",
        "Results: failed x2, passed x1, review_changes x1",
        "Failing tests: tests/test_codemap_end.py::test_b, tests/test_codemap_scan.py::test_a",
        "Review: " + ("- [low] R" * 100)[:300],
        "Triage: code_wrong - signature unset",
        "Reset by a person: named groups made \\3 the title",
        "Reset by a person: older tests pinned test(...)",
    ]


def test_a_quiet_episode():
    task = dict(TASK, goal="g", files=[], attempts=None)
    task.pop("attempts")
    c = episodes.episode(task, [])
    assert c["text"] == "T113: codemap: JS test calls are symbols (done, 0 attempts, role coder_hard)\nGoal: g"


def test_reset_lessons():
    ls = episodes.reset_lessons(TASK, EVENTS)
    assert [(l["id"], l["kind"], l["text"]) for l in ls] == [
        ("lesson:reset:T113:1", "lesson", "T113 codemap: JS test calls are symbols: named groups made \\3 the title"),
        ("lesson:reset:T113:2", "lesson", "T113 codemap: JS test calls are symbols: older tests pinned test(...)")]
    assert ls[0]["title"] == "T113: codemap: JS test calls are symbols"


def test_history_chunks():
    other = dict(TASK, id="T114", title="stem", status="todo")
    third = dict(TASK, id="T115", title="cap", status="needs_human")
    events = EVENTS + [{"kind": "verdict", "task": "T115", "result": "reset_by_human", "reason": "r"}]
    ids = [c["id"] for c in episodes.history_chunks([TASK, other, third], events)]
    assert ids == ["episode:T113", "lesson:reset:T113:1", "lesson:reset:T113:2", "episode:T115",
                   "lesson:reset:T115:1"]
