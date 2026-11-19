"""Tests for tasks learn_plans and learn_quality: the learner also learns from plans a person edited, writes short
concrete lessons, and finds duplicates by meaning (memory M3b, second step).

First live run (2026-11-19): 32 lessons proposed, 8 kept; about 6 restated one lesson in other words (Jaccard missed
them), many were vague. Embedding check (jina-v2-base-code): unrelated lessons up to 0.68 cosine, paraphrases
0.65-0.76 -> learn.SIMILAR = 0.72.

plan.save_plan(state_dir, goal, tasks) also stores "original": a deep copy of the tasks as the planner gave them
(so a person's edits to "tasks" can be compared later).

learn.SYSTEM additionally asks for at most 25 words and one concrete action (what to do, not what went wrong).
learn.MAX_WORDS = 30: learn.ask returns None when the parsed lesson text has more than MAX_WORDS words
(text.split()).

learn.plan_corrections(state_dir) -> list of corrections from state_dir / "plans" / "*.json" (sorted by file name;
missing folder -> []), only plans with status "added" that have "original". With orig = {t["key"]: t} of
"original" and now = {t["key"]: t} of "tasks":
- a key in both whose task differs (any field): {"id": f"plan:{pid}:{key}", "text": head + f"The planner wrote:\n
  {fmt(orig task)}\nA person changed it to:\n{fmt(now task)}"};
- a key only in orig: id the same, text head + f"The planner wrote:\n{fmt(orig task)}\nA person removed this task."
- a key only in now: id the same, text head + f"The planner did not plan this task; a person added:\n{fmt(now task)}"
in the order: orig keys (in orig order) then the added keys (in tasks order). head = f"Plan {pid} for the goal:
{goal cut to 400 characters}\n". fmt(t) = "\n".join(f"{field}: {value}") for field in ("title", "goal", "files",
"tests", "after") with lists joined by ", ".

learn.learn(gw, tasks, events, lessons_path, state_dir, project, embedder=None): the corrections are corrections(tasks,
events) followed by plan_corrections(state_dir). With an embedder: the texts of the lessons in the file are embedded
once (embedder.embed(list)) before the first correction; a new lesson is also a duplicate when the cosine
similarity of embedder.embed([text])[0] with any of them is >= SIMILAR; an added lesson's vector joins them.
Without an embedder: as before (Jaccard only).

`stratos memory learn` passes embedder=embed.Embedder()."""
import json

from stratos import __main__ as cli
from stratos import config, embed, learn, plan

T_A = {"key": "a", "title": "Sell", "goal": "Sell a tower.", "files": ["src/t.js"], "tests": ["tests/s.test.js"],
       "protected": [], "after": [], "role": None}
T_B = dict(T_A, key="b", title="Panel", goal="Show it.", tests=["tests/p.test.js"])


def test_save_plan_keeps_the_original(tmp_path):
    tasks = [dict(T_A)]
    pid = plan.save_plan(tmp_path, "G", tasks)
    tasks[0]["goal"] = "changed after saving"
    data = plan.load_plan(tmp_path, pid)
    assert data["original"] == [T_A] and data["tasks"] == [T_A]


def test_system_and_word_limit(monkeypatch):
    assert "25 words" in learn.SYSTEM and "action" in learn.SYSTEM
    assert learn.MAX_WORDS == 30
    monkeypatch.setattr(config, "LEARNER", {"model": "m", "effort": "none", "max_tokens": 50})

    class GW:
        def ensure_model(self, m):
            return 0.0

        def chat(self, messages, **kw):
            return "c", "- [code] " + " ".join(["word"] * 31)
    assert learn.ask(GW(), {"id": "x", "text": "t"}, []) is None


def write_plan(state, pid, status, original, tasks, goal="Make selling work." + "x" * 500):
    (state / "plans").mkdir(parents=True, exist_ok=True)
    data = {"id": pid, "goal": goal, "tasks": tasks, "status": status, "hash": ""}
    if original is not None:
        data["original"] = original
    (state / "plans" / f"{pid}.json").write_text(json.dumps(data), encoding="utf-8")


def test_plan_corrections(tmp_path):
    assert learn.plan_corrections(tmp_path) == []
    changed = dict(T_A, goal="Sell a tower and recompute the path.")
    added = dict(T_B, key="c", title="Path")
    write_plan(tmp_path, "P002", "added", [T_A, T_B], [changed, added])
    write_plan(tmp_path, "P001", "added", [T_A], [T_A])            # not edited
    write_plan(tmp_path, "P003", "draft", [T_A], [changed])        # not added yet
    write_plan(tmp_path, "P004", "added", None, [changed])         # an old plan without "original"
    cs = learn.plan_corrections(tmp_path)
    assert [c["id"] for c in cs] == ["plan:P002:a", "plan:P002:b", "plan:P002:c"]
    head = "Plan P002 for the goal: " + ("Make selling work." + "x" * 500)[:400] + "\n"
    fmt_a = "title: Sell\ngoal: Sell a tower.\nfiles: src/t.js\ntests: tests/s.test.js\nafter: "
    assert cs[0]["text"] == (head + "The planner wrote:\n" + fmt_a + "\nA person changed it to:\n" +
                             fmt_a.replace("Sell a tower.", "Sell a tower and recompute the path."))
    assert cs[1]["text"].endswith("\nA person removed this task.")
    assert cs[2]["text"].startswith(head + "The planner did not plan this task; a person added:\ntitle: Path\n")


class FakeEmbedder:
    name = "fake"

    def __init__(self, vectors):
        self.vectors = vectors
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return [self.vectors[t] for t in texts]


class FakeGateway:
    def __init__(self, answers):
        self.answers = list(answers)

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        return "c", self.answers.pop(0)


EVENTS = [{"kind": "verdict", "task": "T001", "result": "reset_by_human", "reason": "r1"},
          {"kind": "verdict", "task": "T001", "result": "reset_by_human", "reason": "r2"}]
TASKS = [{"id": "T001", "title": "t", "goal": "g"}]


def test_learn_finds_duplicates_by_meaning(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LEARNER", {"model": "m", "effort": "none", "max_tokens": 50})
    lessons_path = tmp_path / "LESSONS.md"
    lessons_path.write_text("- [tests] Old tests pin old rules. (td)\n", encoding="utf-8")
    emb = FakeEmbedder({"Old tests pin old rules.": [1.0, 0.0],
                        "Update the tests that encode the previous rule.": [0.8, 0.6],     # cosine 0.8
                        "Recompute paths when a cell frees up.": [0.0, 1.0],
                        "Free cells need a new path.": [0.1, 0.995]})                    # close to the second
    gw = FakeGateway(["- [tests] Update the tests that encode the previous rule.",
                      "- [code] Recompute paths when a cell frees up.",
                      "- [code] Free cells need a new path."])
    write_plan(tmp_path / "state", "P001", "added", [T_A], [dict(T_A, goal="other")])
    out = learn.learn(gw, TASKS, EVENTS, lessons_path, tmp_path / "state", "p", embedder=emb)
    assert out == {"corrections": 3, "added": 1, "duplicates": 2, "skipped": 0}
    assert emb.calls[0] == ["Old tests pin old rules."]
    assert lessons_path.read_text(encoding="utf-8").splitlines()[-1] == (
        "- [code] Recompute paths when a cell frees up. (p: reset:T001:2)")
    learned = json.loads((tmp_path / "state" / "learned.json").read_text(encoding="utf-8"))
    assert learned == ["reset:T001:1", "reset:T001:2", "plan:P001:a"]


def test_cli_passes_an_embedder(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(embed, "Embedder", lambda: "EMB")
    seen = []
    monkeypatch.setattr(learn, "learn", lambda *a, **k: seen.append(k.get("embedder")) or
                        {"corrections": 0, "added": 0, "duplicates": 0, "skipped": 0})
    monkeypatch.setattr(cli, "Gateway", lambda telemetry: None)
    assert cli.main(["memory", "learn"]) == 0
    assert seen == ["EMB"]
