"""Tests for task context_slim (P10, 2026-11-20): coder prompts reached 56-66k tokens on tasks that touch
stratos/__main__.py, because every module a task file imports was shown whole (T179, a reset flag: ~45k tokens of
modules it never needed). Now a long imported module shows only what the task's files use.

context.used_names(root, path, module) -> set of the names the Python file `path` uses from the module file
`module` (both relative paths, "pkg/m.py"): names imported from it (`from pkg.m import a`, `from .m import a`),
and attributes read on it when the module itself is imported (`from pkg import m` / `from . import m` -> `m.x`;
`import pkg.m` -> `pkg.m.x`; `from pkg import m as mm` -> `mm.x`). A file that does not exist or does not parse
gives an empty set.

context.module_excerpt(root, module, names) -> str: for each top-level symbol of the module (codemap.scan_python)
whose name is in `names`, in file order: its text (codemap.symbol_text) when it has at most 30 lines, else its
first 6 lines and then a line "    ...". Parts are joined with "\\n\\n". When other top-level symbols exist, a last
part "# other names in this module: " + their names in file order joined with ", ".

context.build_messages: an imported module (context.related_files) of at most 60 lines is shown whole as before;
a longer one as f"READ-ONLY (imported by the files you write; only the parts they use): {path}\\n```\\n{excerpt}\\n```"
where the names are the union of used_names over the task's existing files plus the module's top-level names that
the goal names as a whole word."""
from stratos import context

BIG = ("\"\"\"big\"\"\"\nimport os\n\nLIMIT = 3\n\n\ndef small(a):\n    return a + LIMIT\n\n\n"
       "def long_one(x):\n" + "".join(f"    x += {i}\n" for i in range(40)) + "    return x\n\n\n"
       "def unused():\n    return 0\n\n\nclass Thing:\n    pass\n" + "".join(f"\n\ndef pad{i}():\n    return {i}\n"
                                                                     for i in range(20)))


def make(tmp_path, user_text):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "big.py").write_text(BIG, encoding="utf-8")
    (pkg / "tiny.py").write_text("NAME = 'tiny'\n", encoding="utf-8")
    (pkg / "main.py").write_text(user_text, encoding="utf-8")
    return tmp_path


def test_used_names_all_import_forms(tmp_path):
    root = make(tmp_path, "from pkg.big import small\nfrom . import big as b\nimport pkg.big\n"
                          "from pkg import tiny\n\nb.LIMIT\npkg.big.long_one(1)\ntiny.NAME\n")
    assert context.used_names(root, "pkg/main.py", "pkg/big.py") == {"small", "LIMIT", "long_one"}
    assert context.used_names(root, "pkg/main.py", "pkg/tiny.py") == {"NAME"}
    assert context.used_names(root, "pkg/none.py", "pkg/big.py") == set()


def test_module_excerpt(tmp_path):
    root = make(tmp_path, "")
    text = context.module_excerpt(root, "pkg/big.py", {"small", "long_one", "LIMIT"})
    parts = text.split("\n\n")
    assert parts[0] == "LIMIT = 3"
    assert parts[1] == "def small(a):\n    return a + LIMIT"
    assert parts[2] == "def long_one(x):\n    x += 0\n    x += 1\n    x += 2\n    x += 3\n    x += 4\n    ..."
    assert parts[3].startswith("# other names in this module: unused, Thing, pad0, pad1, ")
    assert "x += 10" not in text


def test_build_messages_slims_only_long_modules(tmp_path):
    root = make(tmp_path, "from pkg import big, tiny\n\nbig.small(tiny.NAME)\n")
    task = {"id": "T1", "title": "t", "goal": "Also call unused() once.", "files": ["pkg/main.py"], "protected": []}
    user = context.build_messages(task, root)[-1]["content"]
    assert "READ-ONLY (imported by the files you write): pkg/tiny.py\n```\nNAME = 'tiny'\n\n```" in user
    head = "READ-ONLY (imported by the files you write; only the parts they use): pkg/big.py\n```\n"
    assert head in user
    part = user[user.index(head) + len(head):]
    part = part[:part.index("\n```")]
    assert part.startswith("def small(a):\n    return a + LIMIT\n\ndef unused():\n    return 0\n\n# other names")
    assert "def long_one" not in part
