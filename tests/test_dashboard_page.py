"""Tests for task dashboard_page (P12, 2026-11-20, user: "something worth watching - stream what it does, show the
terminal log, let me try what was built"). stratos/dashboard.html gets, next to its panels:

- a project picker <select id="projectPick"> (options = the project names of /api/state; default the most recently
  updated; the choice is kept across polls) - every panel shows the picked project instead of projects[0];
- <section id="stream">: what the model is writing now - polls fetch("/api/live?project=" + encodeURIComponent(name))
  every 700 ms, shows call.task / call.role / call.model / call.attempt in its title, the text in a monospace <pre>
  that keeps scrolled to the bottom, the part before the line "--- answer ---" (the thinking) dimmed; a finished call
  (call.finished set) is labelled as finished;
- <section id="terminal">: the run log (live.log) as a dark terminal-like <pre>, scrolled to the bottom, lines with
  "passed" or ": done" green, "failed", "error" or "needs_human" red, "model switch" dimmed;
- <section id="try">: for a project whose "try" is "cli" a <textarea id="tryText">, an <input id="tryArgs">, a button
  that POSTs JSON {"text", "args"} to "/api/try?project=" + name with the header "X-Stratos": "1" and shows code,
  stdout and stderr; for "static" an <iframe> of "/try/" + name + "/index.html" and a link to open it; otherwise a
  line saying the project has no [try] table in its stratos.toml.
All text through esc() (no raw HTML from the server). The page stays one file with inline CSS and JS."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from stratos import dashboard

PAGE = Path(dashboard.__file__).parent / "dashboard.html"


def test_page_has_the_new_panels():
    html = PAGE.read_text(encoding="utf-8")
    for needle in ('id="projectPick"', 'id="stream"', 'id="terminal"', 'id="try"', 'id="tryText"', 'id="tryArgs"',
                   "/api/live?project=", "/api/try?project=", '"X-Stratos"', "--- answer ---", "/try/"):
        assert needle in html, needle


def test_script_compiles():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    html = PAGE.read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert scripts
    r = subprocess.run([node, "--check", "-"], input="\n".join(scripts), capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
