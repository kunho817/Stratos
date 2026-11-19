"""Tests for task wiki: a local model writes a short reference page per code file (memory M4, the LLM wiki).

config.WIKI = {"model": "tiel-coder-35b-a3b-ud-q4_k_xl", "effort": "none", "max_tokens": 3000} (the coder's model).

wiki.SYSTEM: the system prompt. It asks for a page with exactly these sections, in this order: "## Purpose",
"## Data shapes", "## Used by", "## Invariants", "## Traps"; only facts visible in the code given; at most 400 words.
wiki.MAX_SOURCE = 20000: a source longer than this is cut to MAX_SOURCE characters + "\n... (cut)".

wiki.page_name(path) -> path with every "/" replaced by "__", + ".md" ("src/a.js" -> "src__a.js.md").

wiki.used_by(cmap, path) -> str: one line per symbol of cmap["files"][path] (in order) that has users in OTHER files:
f"- {name}: {', '.join(those users)}" with the users from codemap.users(cmap, name) (called through the codemap
module) minus those that start with path + ":". Lines joined with "\n"; none -> "".

wiki.messages(path, source, used) -> [{"role": "system", "content": SYSTEM}, {"role": "user", "content":
f"FILE: {path}\n```\n{source (cut as above)}\n```\n\nUSED BY (from the code map):\n{used or '(nothing outside this
file)'}"}].

wiki.clean(answer) -> str or None: strips the answer; when it starts with a ``` line and ends with a ``` line those
two lines are removed (and the rest stripped again). No "## Purpose" in it -> None. Otherwise the text.

wiki.build(gw, root, state_dir, cmap, only=None, log=print) -> {"written", "unchanged", "kept", "failed"}:
pages live in state_dir / "wiki" (made when missing); state_dir / "wiki" / "index.json" (UTF-8 JSON, {} when
missing) maps a file path to {"source": sha1 hex of the source text, "page": sha1 hex of the page text written}.
Code files only: every path of cmap["files"] (in order) that does not start with cmap["test_dir"] + "/"; when only is
given, only paths in it. For each: source = (root / path) read as UTF-8; page = wiki dir / page_name(path).
- the page exists and the sha1 of its text differs from index[path]["page"] (or path is not in the index): a person
  edited it -> "kept", log(f"wiki: {path}: kept (edited by hand)"), nothing asked.
- the page exists and index[path]["source"] equals the source's sha1 -> "unchanged".
- otherwise ask: gw.ensure_model(WIKI model) (once per build, before the first ask), then gw.chat(messages(path,
  source, used_by(cmap, path)), task="wiki", role="wiki", attempt=1, model, effort, max_tokens) -> (call_id, answer).
  clean(answer) None (or chat raising) -> "failed", log(f"wiki: {path}: failed"). Otherwise the page text
  f"# {path}\n\n{cleaned}\n" is written (UTF-8), index[path] = {"source": ..., "page": sha1 of that text},
  "written", log(f"wiki: {path}: written").
index.json is written after every written page.

wiki.chunks(state_dir, cmap) -> for every code path of cmap (same filter, in order) whose page exists:
{"id": f"wiki:{path}", "kind": "wiki", "source": path, "title": f"notes: {path}", "text": the page text}."""
import hashlib
import json

import pytest

from stratos import codemap, config, wiki

CMAP = {"test_dir": "tests", "files": {
    "src/a.py": [{"name": "load", "kind": "function", "signature": "def load(p)", "uses": [], "line": 1, "end": 2},
                 {"name": "LIMIT", "kind": "constant", "signature": "LIMIT = 3", "uses": [], "line": 3, "end": 3}],
    "src/b.py": [{"name": "run", "kind": "function", "signature": "def run()", "uses": ["load"], "line": 1, "end": 2}],
    "tests/test_a.py": [{"name": "test_load", "kind": "function", "signature": "def test_load()", "uses": ["load"],
                         "line": 1, "end": 2}],
}}
PAGE = "## Purpose\nLoads things.\n\n## Data shapes\n-\n\n## Used by\n-\n\n## Invariants\n-\n\n## Traps\n-"


def sha(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def test_config_and_system():
    assert config.WIKI == {"model": "tiel-coder-35b-a3b-ud-q4_k_xl", "effort": "none", "max_tokens": 3000}
    heads = ["## Purpose", "## Data shapes", "## Used by", "## Invariants", "## Traps"]
    positions = [wiki.SYSTEM.index(h) for h in heads]
    assert positions == sorted(positions)
    assert "400" in wiki.SYSTEM
    assert wiki.MAX_SOURCE == 20000


def test_page_name():
    assert wiki.page_name("src/a.js") == "src__a.js.md"
    assert wiki.page_name("top.py") == "top.py.md"


def test_used_by():
    assert wiki.used_by(CMAP, "src/a.py") == "- load: src/b.py:run, tests/test_a.py:test_load"
    assert wiki.used_by(CMAP, "src/b.py") == ""


def test_used_by_ignores_the_file_itself(monkeypatch):
    monkeypatch.setattr(codemap, "users", lambda cmap, name: ["src/a.py:other", "src/c.py:x"] if name == "load" else [])
    assert wiki.used_by(CMAP, "src/a.py") == "- load: src/c.py:x"


def test_messages():
    m = wiki.messages("src/a.py", "X = 1", "- load: b")
    assert m[0] == {"role": "system", "content": wiki.SYSTEM}
    assert m[1]["content"] == "FILE: src/a.py\n```\nX = 1\n```\n\nUSED BY (from the code map):\n- load: b"
    assert m[1]["content"] == wiki.messages("src/a.py", "X = 1", "- load: b")[1]["content"]
    assert wiki.messages("p", "s", "")[1]["content"].endswith("USED BY (from the code map):\n(nothing outside this file)")
    long = wiki.messages("p", "y" * 20005, "")[1]["content"]
    assert "y" * 20000 + "\n... (cut)\n```" in long and "y" * 20001 not in long


def test_clean():
    assert wiki.clean("  " + PAGE + "\n ") == PAGE
    assert wiki.clean("```markdown\n" + PAGE + "\n```") == PAGE
    assert wiki.clean("```\n\n" + PAGE + "\n\n```\n") == PAGE
    assert wiki.clean("Some notes without the sections") is None
    assert wiki.clean("") is None


class FakeGateway:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []
        self.loaded = []

    def ensure_model(self, model):
        self.loaded.append(model)
        return 0.0

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return "c1", answer


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "a.py").write_text("def load(p):\n    pass\nLIMIT = 3\n", encoding="utf-8")
    (root / "src" / "b.py").write_text("def run():\n    load()\n", encoding="utf-8")
    (root / "tests" / "test_a.py").write_text("def test_load():\n    load()\n", encoding="utf-8")
    return root, tmp_path / "state"


def test_build_writes_pages(repo):
    root, state = repo
    gw = FakeGateway(["```markdown\n" + PAGE + "\n```", PAGE.replace("Loads", "Runs")])
    lines = []
    counts = wiki.build(gw, root, state, CMAP, log=lines.append)
    assert counts == {"written": 2, "unchanged": 0, "kept": 0, "failed": 0}
    assert gw.loaded == [config.WIKI["model"]]
    assert len(gw.calls) == 2
    messages, kw = gw.calls[0]
    assert messages == wiki.messages("src/a.py", "def load(p):\n    pass\nLIMIT = 3\n", wiki.used_by(CMAP, "src/a.py"))
    assert kw == {"task": "wiki", "role": "wiki", "attempt": 1, "model": config.WIKI["model"],
                  "effort": config.WIKI["effort"], "max_tokens": config.WIKI["max_tokens"]}
    page = (state / "wiki" / "src__a.py.md").read_text(encoding="utf-8")
    assert page == "# src/a.py\n\n" + PAGE + "\n"
    assert not (state / "wiki" / "tests__test_a.py.md").exists()
    index = json.loads((state / "wiki" / "index.json").read_text(encoding="utf-8"))
    assert index["src/a.py"] == {"source": sha("def load(p):\n    pass\nLIMIT = 3\n"), "page": sha(page)}
    assert lines == ["wiki: src/a.py: written", "wiki: src/b.py: written"]


def test_build_skips_unchanged_and_keeps_hand_edits(repo):
    root, state = repo
    wiki.build(FakeGateway([PAGE, PAGE]), root, state, CMAP, log=lambda s: None)
    page_b = state / "wiki" / "src__b.py.md"
    page_b.write_text(page_b.read_text(encoding="utf-8") + "\nA person's note.\n", encoding="utf-8")
    (root / "src" / "b.py").write_text("def run():\n    load(1)\n", encoding="utf-8")   # changed, but edited page
    gw = FakeGateway([])
    lines = []
    assert wiki.build(gw, root, state, CMAP, log=lines.append) == {"written": 0, "unchanged": 1, "kept": 1, "failed": 0}
    assert gw.calls == [] and gw.loaded == []
    assert lines == ["wiki: src/b.py: kept (edited by hand)"]
    assert "A person's note." in page_b.read_text(encoding="utf-8")


def test_build_rewrites_a_changed_file(repo):
    root, state = repo
    wiki.build(FakeGateway([PAGE, PAGE]), root, state, CMAP, log=lambda s: None)
    (root / "src" / "a.py").write_text("def load(p, q):\n    pass\n", encoding="utf-8")
    gw = FakeGateway([PAGE.replace("Loads", "Now loads")])
    assert wiki.build(gw, root, state, CMAP, log=lambda s: None) == {"written": 1, "unchanged": 1, "kept": 0,
                                                                      "failed": 0}
    assert "Now loads" in (state / "wiki" / "src__a.py.md").read_text(encoding="utf-8")


def test_build_failures_and_only(repo):
    root, state = repo
    gw = FakeGateway(["no sections here", RuntimeError("model gone")])
    lines = []
    assert wiki.build(gw, root, state, CMAP, log=lines.append) == {"written": 0, "unchanged": 0, "kept": 0,
                                                                    "failed": 2}
    assert lines == ["wiki: src/a.py: failed", "wiki: src/b.py: failed"]
    assert not (state / "wiki" / "src__a.py.md").exists()
    gw = FakeGateway([PAGE])
    assert wiki.build(gw, root, state, CMAP, only=["src/b.py"], log=lambda s: None)["written"] == 1
    assert len(gw.calls) == 1 and "FILE: src/b.py" in gw.calls[0][0][1]["content"]


def test_chunks(repo):
    root, state = repo
    assert wiki.chunks(state, CMAP) == []
    wiki.build(FakeGateway([PAGE]), root, state, CMAP, only=["src/a.py"], log=lambda s: None)
    text = (state / "wiki" / "src__a.py.md").read_text(encoding="utf-8")
    assert wiki.chunks(state, CMAP) == [{"id": "wiki:src/a.py", "kind": "wiki", "source": "src/a.py",
                                         "title": "notes: src/a.py", "text": text}]
