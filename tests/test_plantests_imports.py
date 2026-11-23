"""Tests for task P025: the import block in stratos/plantests.py must appear exactly once,
right after the module docstring. The duplicate block (import re ... from stratos import langs, steps)
is removed, leaving a single copy."""

import re
from pathlib import Path

SOURCE = (Path(__file__).parent.parent / "stratos" / "plantests.py").read_text(encoding="utf-8")

# The full import block pattern that must appear exactly once.
# It spans from "import re" through "from stratos import langs, steps".
IMPORT_BLOCK = re.compile(
    r"import re\nimport subprocess\nimport urllib\.error\nfrom pathlib import Path\n\n"
    r"from \. import codemap, config, context, decide, embed, lint, memstore, plan, patch, recall, refcheck\n"
    r"from \. import cases\nfrom \. import verify\nfrom stratos import langs, steps"
)


def test_import_re_appears_exactly_once():
    # Count how many times "import re" appears as a standalone line in the source.
    lines = SOURCE.splitlines()
    # "import re" as a line: stripped == "import re"
    count = sum(1 for line in lines if line.strip() == "import re")
    # The task removes the second copy, so exactly one should remain.
    assert count == 1


def test_import_re_before_any_def():
    # The first occurrence of "import re" must come before the first "def " line.
    first_import = None
    first_def = None
    for i, line in enumerate(SOURCE.splitlines()):
        if first_import is None and line.strip() == "import re":
            first_import = i
        if first_def is None and re.match(r"^def\s", line):
            first_def = i
        if first_import is not None and first_def is not None:
            break
    # "import re" must exist and must be before any def.
    assert first_import is not None, "no 'import re' found in plantests.py"
    assert first_def is not None, "no 'def' found in plantests.py"
    assert first_import < first_def


def test_full_import_block_appears_exactly_once():
    # The exact import block (import re through from stratos import langs, steps)
    # must appear exactly once.
    matches = list(IMPORT_BLOCK.finditer(SOURCE))
    assert len(matches) == 1, f"import block found {len(matches)} times (expected 1)"


def test_import_block_is_right_after_docstring():
    # The docstring is the first thing in the file; the import block starts immediately after it.
    lines = SOURCE.splitlines()
    # Find end of the module docstring: the first triple-quote closing.
    # Module docstring is """...""" at the top.
    # Locate the line index where the closing triple-quote of the docstring ends.
    in_docstring = False
    docstring_end = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('"""') and not in_docstring:
            in_docstring = True
            # Check if it closes on the same line
            if stripped.endswith('"""') and len(stripped) > 3:
                docstring_end = i
                break
        elif in_docstring and stripped.endswith('"""'):
            docstring_end = i
            break
    assert docstring_end is not None, "no module docstring found"
    # The next non-blank line after the docstring must be "import re".
    next_line_idx = docstring_end + 1
    # Skip blank lines
    while next_line_idx < len(lines) and lines[next_line_idx].strip() == "":
        next_line_idx += 1
    assert lines[next_line_idx].strip() == "import re", (
        f"expected 'import re' right after docstring, got: {lines[next_line_idx]!r}"
    )


def test_no_duplicate_import_lines():
    # Each import line in the block must appear exactly once as a standalone statement.
    import_lines = [
        "import re",
        "import subprocess",
        "import urllib.error",
        "from pathlib import Path",
        "from . import cases",
        "from . import verify",
        "from stratos import langs, steps",
    ]
    lines = SOURCE.splitlines()
    for target in import_lines:
        count = sum(1 for line in lines if line.strip() == target)
        # Each import line appears exactly once.
        # "import re" alone is 1; "import subprocess" alone is 1; etc.
        assert count == 1, f"{target!r} appears {count} times (expected 1)"
