"""Tests for task dashboard: `stratos dashboard` serves a live status page on 127.0.0.1 (user, 2026-11-19: "something
to watch while waiting").

dashboard.default_repos(home) -> [home] + the folders of home.parent / "Trials" that contain a ".stratos" folder,
sorted by name (Path objects).

dashboard.project(repo) -> dict for one project, read from repo / ".stratos" (tasks.json through state.Store, and
telemetry.jsonl through telemetry.Telemetry):
- "name": repo.name, "path": str(repo)
- "tasks": [{"id", "title", "status", "role", "triage"}] in store order; "triage" is task["triage"]["verdict"] when
  the task has a triage dict, else None; "role" None when missing.
- "counts": {status: number of tasks}
- "events": the last 60 telemetry events, each with only the keys of KEEP that it has (KEEP = ("ts", "kind", "task",
  "role", "attempt", "model", "from_model", "result", "seconds", "verdict", "reason", "detail", "finish",
  "completion_tokens")); "reason" and "detail" cut to 300 characters.
- "updated": the "ts" of the last event (as a float), 0.0 with no events.
- "current": what is running now, from all events: the last "call_start" event with no later "call" event of the
  same call_id -> {"kind": "call", "task", "role", "attempt", "model", "since": its ts}; otherwise the last
  "switch_start" event with no later "switch" event -> {"kind": "switch", "model", "from_model", "since": its ts};
  otherwise None. Only the newest unfinished one counts (a start followed by a later finished call is not current).
- "stats": {"calls": number of "call" events, "model_seconds": sum of their "seconds", "switch_seconds": sum of the
  "seconds" of "switch" events} (floats, rounded to 1 decimal).

dashboard.metrics(base_url) -> GET base_url + "/metrics" (timeout 2 s) -> {"model": engine.model, "live": live,
"hardware": hardware, "totals": totals, "history": {"gpu_util": last 60 of history.gpu_util, "gpu_mem_used": last 60
of history.gpu_mem_used}}; any error -> None.

dashboard.snapshot(repos, metrics=None) -> {"time": time.time(), "projects": [project(r) for r in repos] sorted by
"updated" (newest first), "engine": metrics() when metrics is given, else None}.

dashboard.make_server(repos, port, metrics=None) -> an http.server.ThreadingHTTPServer bound to ("127.0.0.1",
port) (never another address). GET "/" -> 200, "text/html; charset=utf-8", the text of dashboard.PAGE (the file
stratos/dashboard.html next to the module, read on every request); GET "/api/state" -> 200,
"application/json; charset=utf-8", json of snapshot(repos, metrics); other paths -> 404.

`stratos dashboard [--port 8765] [--repo PATH ...]`: repos = the --repo paths (Path) or
default_repos(config.STRATOS_HOME); server = dashboard.make_server(repos, port, metrics=<a function calling
dashboard.metrics(config.BASE_URL)>); prints f"dashboard: http://127.0.0.1:{port}/" and calls server.serve_forever()."""
import json
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from stratos import __main__ as cli, config, dashboard
from stratos.state import Store
from stratos.telemetry import Telemetry


def test_default_repos(tmp_path):
    home = tmp_path / "Stratos"
    home.mkdir()
    for name in ("Zeta", "Alpha", "NoState"):
        (tmp_path / "Trials" / name).mkdir(parents=True)
    (tmp_path / "Trials" / "Zeta" / ".stratos").mkdir()
    (tmp_path / "Trials" / "Alpha" / ".stratos").mkdir()
    assert dashboard.default_repos(home) == [home, tmp_path / "Trials" / "Alpha", tmp_path / "Trials" / "Zeta"]
    assert dashboard.default_repos(tmp_path / "Lonely") == [tmp_path / "Lonely"]


def make_project(tmp_path):
    repo = tmp_path / "Orbit"
    state = repo / ".stratos"
    store = Store(state)
    store.add_task("Levels", "g", [], [], ["tests/a.test.js"], role="coder")
    store.add_task("Game", "g", [], [], ["tests/b.test.js"])
    store.update("T001", status="needs_human", triage={"verdict": "code_wrong", "test": "x", "reason": "r"})
    store.update("T002", status="done")
    tel = Telemetry(state / "telemetry.jsonl")
    return repo, tel


def test_project(tmp_path):
    repo, tel = make_project(tmp_path)
    tel.record("switch_start", model="swift", from_model="tiel")
    tel.record("switch", model="swift", from_model="tiel", seconds=20.04)
    tel.record("call_start", call_id="c1", task="T001", role="coder", attempt=1, model="swift")
    tel.record("call", call_id="c1", task="T001", role="coder", attempt=1, model="swift", seconds=30.0,
               completion_tokens=900, prompt_tokens=5, finish="stop")
    tel.record("outcome", call_id="c1", task="T001", result="failed", detail="x" * 400)
    tel.record("call_start", call_id="c2", task="T001", role="coder", attempt=2, model="swift")
    p = dashboard.project(repo)
    assert p["name"] == "Orbit" and p["path"] == str(repo)
    assert p["tasks"] == [{"id": "T001", "title": "Levels", "status": "needs_human", "role": "coder",
                           "triage": "code_wrong"},
                          {"id": "T002", "title": "Game", "status": "done", "role": "coder", "triage": None}]
    assert p["counts"] == {"needs_human": 1, "done": 1}
    assert len(p["events"]) == 6
    assert "prompt_tokens" not in p["events"][3] and p["events"][3]["completion_tokens"] == 900
    assert len(p["events"][4]["detail"]) == 300
    assert p["updated"] == p["events"][-1]["ts"]
    assert p["current"]["kind"] == "call" and p["current"]["task"] == "T001" and p["current"]["attempt"] == 2
    assert p["current"]["since"] == p["events"][-1]["ts"]
    assert p["stats"] == {"calls": 1, "model_seconds": 30.0, "switch_seconds": 20.0}


def test_current_switch_and_nothing(tmp_path):
    repo, tel = make_project(tmp_path)
    assert dashboard.project(repo)["current"] is None and dashboard.project(repo)["updated"] == 0.0
    tel.record("call_start", call_id="c1", task="T001", role="coder", attempt=1, model="tiel")
    tel.record("call", call_id="c1", task="T001", role="coder", attempt=1, model="tiel", seconds=1)
    assert dashboard.project(repo)["current"] is None
    tel.record("switch_start", model="qwen", from_model="tiel")
    cur = dashboard.project(repo)["current"]
    assert cur["kind"] == "switch" and cur["model"] == "qwen" and cur["from_model"] == "tiel"


def test_events_are_the_last_60(tmp_path):
    repo, tel = make_project(tmp_path)
    for i in range(70):
        tel.record("decision", task=f"T{i:03d}", choice="x")
    events = dashboard.project(repo)["events"]
    assert len(events) == 60 and events[0]["task"] == "T010" and "choice" not in events[0]


def test_metrics(monkeypatch):
    body = {"engine": {"model": "tiel"}, "live": {"state": "generating", "generated": 5},
            "hardware": {"gpu_util": 99}, "totals": {"requests": 3},
            "history": {"gpu_util": list(range(100)), "gpu_mem_used": list(range(70)), "cpu": [1]}}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(body).encode("utf-8")
    seen = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=None: seen.append((url, timeout)) or Resp())
    m = dashboard.metrics("http://h:1")
    assert seen == [("http://h:1/metrics", 2)]
    assert m == {"model": "tiel", "live": body["live"], "hardware": body["hardware"], "totals": body["totals"],
                 "history": {"gpu_util": list(range(40, 100)), "gpu_mem_used": list(range(10, 70))}}

    def boom(url, timeout=None):
        raise urllib.error.URLError("down")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert dashboard.metrics("http://h:1") is None


def test_snapshot_orders_by_update(tmp_path, monkeypatch):
    a, tel_a = make_project(tmp_path / "a")
    b, tel_b = make_project(tmp_path / "b")
    tel_a.record("decision", task="T1")
    time.sleep(0.02)   # (ts has 3 decimals)
    tel_b.record("decision", task="T1")
    snap = dashboard.snapshot([a, b], metrics=lambda: {"model": "m"})
    assert [p["path"] for p in snap["projects"]] == [str(b), str(a)]
    assert snap["engine"] == {"model": "m"} and snap["time"] > 0
    assert dashboard.snapshot([a])["engine"] is None


@pytest.fixture
def server(tmp_path):
    repo, tel = make_project(tmp_path)
    srv = dashboard.make_server([repo], 0, metrics=lambda: None)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def get(srv, path):
    host, port = srv.server_address
    return urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=5)


def test_server(server):
    assert server.server_address[0] == "127.0.0.1"
    page = get(server, "/")
    assert page.headers["Content-Type"] == "text/html; charset=utf-8"
    assert page.read().decode("utf-8") == dashboard.PAGE.read_text(encoding="utf-8")
    state = get(server, "/api/state")
    assert state.headers["Content-Type"] == "application/json; charset=utf-8"
    data = json.loads(state.read().decode("utf-8"))
    assert data["projects"][0]["name"] == "Orbit" and data["engine"] is None
    with pytest.raises(urllib.error.HTTPError) as e:
        get(server, "/nope")
    assert e.value.code == 404


def test_page_exists():
    assert dashboard.PAGE.name == "dashboard.html" and dashboard.PAGE.exists()


def test_cli(tmp_path, monkeypatch, capsys):
    made = []

    class FakeServer:
        def serve_forever(self):
            made.append("served")
    # (task dashboard_live: without --repo the server gets repos=None and home, so new trials show up without a
    # restart, and a watcher restarts the server when the code changes; Claude updated this test)
    monkeypatch.setattr(dashboard, "make_server", lambda repos, port, metrics=None, home=None: made.append(
        (repos, port, metrics is not None, home)) or FakeServer())
    monkeypatch.setattr(dashboard, "watch_code", lambda folder: made.append(("watch", folder)))
    assert cli.main(["dashboard", "--port", "9001", "--repo", str(tmp_path / "a"), str(tmp_path / "b")]) == 0
    assert made[0] == ([tmp_path / "a", tmp_path / "b"], 9001, True, None) and made[-1] == "served"
    assert "dashboard: http://127.0.0.1:9001/" in capsys.readouterr().out
    made.clear()
    cli.main(["dashboard"])
    assert made[0] == (None, 8765, True, config.STRATOS_HOME)
    assert ("watch", Path(dashboard.__file__).parent) in made


def test_current_is_only_the_newest_start(tmp_path, monkeypatch):
    """(task dashboard_current) A run killed in the middle of a call leaves a call_start with no call. Only the newest
    start event (call_start or switch_start, whichever is later) can be current: it is current when no "call" with its
    call_id (for call_start) or no "switch" (for switch_start) comes after it, and it is less than
    dashboard.STALE_S = 1800 seconds old (time.time() - its ts); otherwise "current" is None. The events are read once
    (no scan per start event)."""
    repo, tel = make_project(tmp_path)
    tel.record("call_start", call_id="dead", task="T001", role="coder", attempt=1, model="tiel")   # killed run
    tel.record("call_start", call_id="c2", task="T002", role="coder", attempt=1, model="tiel")
    tel.record("call", call_id="c2", task="T002", role="coder", attempt=1, model="tiel", seconds=1)
    assert dashboard.project(repo)["current"] is None
    tel.record("switch_start", model="swift", from_model="tiel")
    tel.record("switch", model="swift", from_model="tiel", seconds=3)
    tel.record("call_start", call_id="c3", task="T002", role="coder_hard", attempt=2, model="swift")
    assert dashboard.project(repo)["current"]["task"] == "T002"
    assert dashboard.STALE_S == 1800
    now = __import__("time").time()
    monkeypatch.setattr(dashboard.time, "time", lambda: now + 1801)
    assert dashboard.project(repo)["current"] is None


# ---- was test_dashboard_live.py ----
# Tests for task dashboard_live (P12, 2026-11-20, user: "only progress is dull - stream what it does, show the terminal
# log"). The gateway streams each answer into .stratos/live/ (task gateway_stream); the run log is .stratos/run.log
# (task runlog). The dashboard serves them.
#
# dashboard.live(repo) -> {"call": <the JSON of .stratos/live/current.json, or None>, "text": the last 8000 characters
# of .stratos/live/current.txt ("" when missing), "log": the last 200 lines of .stratos/run.log joined with "\n"
# ("" when missing)}.
# make_server(repos, port, metrics=None, home=None): when repos is None the project list is
# default_repos(home) again on every request (a new trial shows up without a restart). GET /api/live?project=<name>
# answers live(<the repo with that name>) as JSON (404 for an unknown name). The page is read from disk on every
# request (as before), so a changed dashboard.html needs no restart.
# dashboard.code_stamp(folder) -> the newest modification time of the *.py and *.html files in the folder (the
# stratos package); `stratos dashboard` restarts itself (os.execv with the same arguments) when it grows.


def make_repo(root, name, live=True):
    repo = root / name
    (repo / ".stratos" / "live").mkdir(parents=True)
    (repo / ".stratos" / "tasks.json").write_text("[]", encoding="utf-8")
    (repo / ".stratos" / "telemetry.jsonl").write_text("", encoding="utf-8")
    if live:
        (repo / ".stratos" / "live" / "current.json").write_text(
            json.dumps({"call_id": "c1", "task": "T1", "role": "coder", "model": "m", "started": 1.0}),
            encoding="utf-8")
        (repo / ".stratos" / "live" / "current.txt").write_text("x" * 9000 + "END", encoding="utf-8")
        (repo / ".stratos" / "run.log").write_text("".join(f"l{i}\n" for i in range(300)), encoding="utf-8")
    return repo


def test_live(tmp_path):
    repo = make_repo(tmp_path, "Stratos")
    got = dashboard.live(repo)
    assert got["call"]["task"] == "T1"
    assert len(got["text"]) == 8000 and got["text"].endswith("END")
    lines = got["log"].split("\n")
    assert len(lines) == 200 and lines[0] == "l100" and lines[-1] == "l299"
    empty = dashboard.live(make_repo(tmp_path, "Other", live=False))
    assert empty == {"call": None, "text": "", "log": ""}


def test_code_stamp(tmp_path):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    first = dashboard.code_stamp(tmp_path)
    time.sleep(0.05)
    (tmp_path / "page.html").write_text("y", encoding="utf-8")
    assert dashboard.code_stamp(tmp_path) > first


def test_server_live_and_new_projects(tmp_path):
    home = tmp_path / "Stratos"
    make_repo(tmp_path, "Stratos")
    (tmp_path / "Trials").mkdir()
    server = dashboard.make_server(None, 0, home=home)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        def get(path):
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
                return json.loads(r.read().decode("utf-8"))
        assert get("/api/live?project=Stratos")["call"]["role"] == "coder"
        assert [p["name"] for p in get("/api/state")["projects"]] == ["Stratos"]
        make_repo(tmp_path / "Trials", "Newgame", live=False)
        assert sorted(p["name"] for p in get("/api/state")["projects"]) == ["Newgame", "Stratos"]
        try:
            get("/api/live?project=Nope")
            raise AssertionError("expected 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        server.shutdown()
        server.server_close()


# ---- was test_dashboard_page.py ----
# Tests for task dashboard_page (P12, 2026-11-20, user: "something worth watching - stream what it does, show the
# terminal log, let me try what was built"). stratos/dashboard.html gets, next to its panels:
#
# - a project picker <select id="projectPick"> (options = the project names of /api/state; default the most recently
#   updated; the choice is kept across polls) - every panel shows the picked project instead of projects[0];
# - <section id="stream">: what the model is writing now - polls fetch("/api/live?project=" + encodeURIComponent(name))
#   every 700 ms, shows call.task / call.role / call.model / call.attempt in its title, the text in a monospace <pre>
#   that keeps scrolled to the bottom, the part before the line "--- answer ---" (the thinking) dimmed; a finished call
#   (call.finished set) is labelled as finished;
# - <section id="terminal">: the run log (live.log) as a dark terminal-like <pre>, scrolled to the bottom, lines with
#   "passed" or ": done" green, "failed", "error" or "needs_human" red, "model switch" dimmed;
# - <section id="try">: for a project whose "try" is "cli" a <textarea id="tryText">, an <input id="tryArgs">, a button
#   that POSTs JSON {"text", "args"} to "/api/try?project=" + name with the header "X-Stratos": "1" and shows code,
#   stdout and stderr; for "static" an <iframe> of "/try/" + name + "/index.html" and a link to open it; otherwise a
#   line saying the project has no [try] table in its stratos.toml.
# All text through esc() (no raw HTML from the server). The page stays one file with inline CSS and JS.


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
