"""Tests for task wiki_overview (P3, 2026-11-20, BACKLOG M4 "next: an overview page"): one page that lists every
module with its purpose and what it imports, written without a model from the code map and the module pages.

wiki.overview(cmap, state_dir) -> text:
  "# Project overview\n\n" then one line per code path of the code map (the paths wiki writes pages for, in their
  order): f"- {path}: {purpose}" where purpose is the first bullet line under "## Purpose" of the path's page with
  the leading "- " cut off, or "(no page yet)" when the page does not exist or has no such line; then, when the
  code map's imports for the path are not empty, f" (imports: {', '.join(imports)})".
wiki.build(...) writes overview(cmap, state_dir) to state_dir/wiki/overview.md at the end of every build (also when
no page changed), with no model call for it.
wiki.chunks(state_dir, cmap) also returns, when overview.md exists, a chunk {"id": "wiki:overview", "kind": "wiki",
"source": "overview", "title": "project overview", "text": <its text>} after the module chunks."""
from stratos import wiki


def cmap():
    return {"test_dir": "tests",
            "files": {"pantry/cli.py": [{"name": "main"}], "pantry/units.py": [{"name": "convert"}],
                      "tests/test_units.py": [{"name": "test_a"}]},
            "imports": {"pantry/cli.py": ["units", "recipe"], "pantry/units.py": [], "tests/test_units.py": ["units"]}}


def write_page(state, path, purpose_lines):
    d = state / "wiki"
    d.mkdir(parents=True, exist_ok=True)
    body = "\n".join(purpose_lines)
    (d / wiki.page_name(path)).write_text(f"# {path}\n\n## Purpose\n{body}\n\n## Data shapes\n- x\n", encoding="utf-8")


def test_overview_lines(tmp_path):
    write_page(tmp_path, "pantry/units.py", ["- Converts amounts between units.", "- Second line."])
    text = wiki.overview(cmap(), tmp_path)
    assert text.startswith("# Project overview\n\n")
    lines = text.strip().splitlines()[2:]
    paths = wiki._code_paths(cmap())
    assert len(lines) == len(paths)
    assert "- pantry/units.py: Converts amounts between units." in lines
    assert "- pantry/cli.py: (no page yet) (imports: units, recipe)" in lines


def test_build_writes_the_overview_without_a_model(tmp_path, monkeypatch):
    calls = []

    class GW:
        def ensure_model(self, model):
            calls.append(model)

        def chat(self, messages, **kw):
            calls.append("chat")
            raise AssertionError("no page should be written here")
    root = tmp_path / "repo"
    root.mkdir()
    state = tmp_path / "state"
    wiki.build(GW(), root, state, {"test_dir": "tests", "files": {}, "imports": {}}, log=lambda s: None)
    assert (state / "wiki" / "overview.md").read_text(encoding="utf-8").startswith("# Project overview")
    assert calls == []


def test_chunks_include_the_overview(tmp_path):
    write_page(tmp_path, "pantry/units.py", ["- Converts."])
    (tmp_path / "wiki" / "overview.md").write_text("# Project overview\n\n- pantry/units.py: Converts.\n",
                                                   encoding="utf-8")
    chunks = wiki.chunks(tmp_path, cmap())
    assert chunks[-1] == {"id": "wiki:overview", "kind": "wiki", "source": "overview", "title": "project overview",
                          "text": "# Project overview\n\n- pantry/units.py: Converts.\n"}
    assert [c["id"] for c in chunks[:-1]] == ["wiki:pantry/units.py"]
