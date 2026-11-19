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
import threading
import time
import urllib.error
import urllib.request

import pytest

from stratos import __main__ as cli
from stratos import config, dashboard
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
    monkeypatch.setattr(dashboard, "make_server", lambda repos, port, metrics=None: made.append(
        (repos, port, metrics is not None)) or FakeServer())
    assert cli.main(["dashboard", "--port", "9001", "--repo", str(tmp_path / "a"), str(tmp_path / "b")]) == 0
    assert made == [([tmp_path / "a", tmp_path / "b"], 9001, True), "served"]
    assert "dashboard: http://127.0.0.1:9001/" in capsys.readouterr().out
    made.clear()
    monkeypatch.setattr(dashboard, "default_repos", lambda home: ["R"] if home == config.STRATOS_HOME else [])
    cli.main(["dashboard"])
    assert made[0] == (["R"], 8765, True)


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
