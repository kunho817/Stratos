"""Tests for task lessons_index: general lessons from LESSONS.md go into every project's memory (memory M3b).

config.STRATOS_HOME = Path(config.__file__).resolve().parent.parent (the Stratos folder) and config.LESSONS =
STRATOS_HOME / "LESSONS.md" (it does not depend on STRATOS_REPO: the lessons are shared by every project). Tests
point config.LESSONS at a missing file (conftest) unless they set it.

lessons.parse(text) -> list of {"tags", "text", "source"}, one per line that starts with "- [" : tags = the
comma-separated words inside the first [...], stripped; the rest of the line, stripped, is the lesson; when it ends
with ")" and holds " (", source = the text inside the last " (...)" and the lesson text is what comes before it,
stripped; else source = "". Other lines are left out.
lessons.chunks(text) -> one chunk per parsed lesson: {"id": "guide:" + sha1(lesson text).hexdigest()[:12],
"kind": "guide", "source": "LESSONS.md", "title": ", ".join(tags), "text": f"[{', '.join(tags)}] {lesson text}"}.

memindex.index_project(root, store, embedder=None, settings=None, lessons_path=None): lessons_path None ->
config.LESSONS. When that file exists, lessons.chunks(its text) are upserted with the project's chunks (counted in
"chunks" and "changed") and remove_except("guide", their ids) is added to "removed" (also when it does not exist:
then with no ids). They are embedded with the rest.

recall.SECTIONS gets ("guide", "GENERAL LESSONS (from earlier projects)", 4) right before the lesson section."""
from stratos import config, lessons, memindex, memstore, recall

TEXT = """# Stratos lessons

Intro line.

- [plan, old-tests] Name the tests that pin the old behaviour. (tower defense: waves.test.js)
- [tests,floats]   Compare floats with a tolerance.
- not a lesson
- [code] Keep (every) function. (T046)
"""


def test_config_path():
    assert (config.STRATOS_HOME / "stratos" / "config.py").exists()
    assert (config.STRATOS_HOME / "LESSONS.md").exists()


def test_parse():
    assert lessons.parse(TEXT) == [
        {"tags": ["plan", "old-tests"], "text": "Name the tests that pin the old behaviour.",
         "source": "tower defense: waves.test.js"},
        {"tags": ["tests", "floats"], "text": "Compare floats with a tolerance.", "source": ""},
        {"tags": ["code"], "text": "Keep (every) function.", "source": "T046"},
    ]


def test_chunks():
    cs = lessons.chunks(TEXT)
    assert [c["kind"] for c in cs] == ["guide"] * 3
    assert cs[0]["title"] == "plan, old-tests"
    assert cs[0]["text"] == "[plan, old-tests] Name the tests that pin the old behaviour."
    assert cs[0]["id"].startswith("guide:") and len(cs[0]["id"]) == 18
    assert cs[0]["source"] == "LESSONS.md"
    assert len({c["id"] for c in cs}) == 3


def test_the_real_lessons_file_parses():
    assert len(lessons.parse((config.STRATOS_HOME / "LESSONS.md").read_text(encoding="utf-8"))) >= 10


def test_index_project_takes_the_lessons(tmp_path):
    (tmp_path / "LESSONS.md").write_text(TEXT, encoding="utf-8")
    store = memstore.Store(tmp_path / "memory.db")
    counts = memindex.index_project(tmp_path / "empty", store, None, {"source_dirs": ["src"], "test_dir": "tests"},
                                    lessons_path=tmp_path / "LESSONS.md")
    assert (counts["chunks"], counts["changed"]) == (3, 3)
    assert [c["kind"] for c in store.all()] == ["guide"] * 3
    (tmp_path / "LESSONS.md").write_text("- [code] Keep (every) function. (T046)\n", encoding="utf-8")
    counts = memindex.index_project(tmp_path / "empty", store, None, {"source_dirs": ["src"], "test_dir": "tests"},
                                    lessons_path=tmp_path / "LESSONS.md")
    assert (counts["chunks"], counts["changed"], counts["removed"]) == (1, 0, 2)
    counts = memindex.index_project(tmp_path / "empty", store, None, {"source_dirs": ["src"], "test_dir": "tests"},
                                    lessons_path=tmp_path / "none.md")
    assert counts["removed"] == 1 and store.all() == []
    store.close()


def test_recall_section():
    kinds = [s[0] for s in recall.SECTIONS]
    assert kinds.index("guide") == kinds.index("lesson") - 1
    assert ("guide", "GENERAL LESSONS (from earlier projects)", 4) in recall.SECTIONS
