"""Dashboard: project snapshot and local server.

KEEP, PAGE = Path(__file__).parent / "dashboard.html", default_repos, project, metrics, snapshot, make_server."""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from stratos.state import Store
from stratos.telemetry import Telemetry
import urllib.request

KEEP = ("ts", "kind", "task", "role", "attempt", "model", "from_model",
        "result", "seconds", "verdict", "reason", "detail", "finish",
        "completion_tokens")
PAGE = Path(__file__).parent / "dashboard.html"
STALE_S = 1800


def default_repos(home):
    home = Path(home)
    result = [home]
    trials = home.parent / "Trials"
    if home.exists() and trials.is_dir():
        for d in sorted(trials.iterdir()):
            if d.is_dir() and (d / ".stratos").is_dir():
                result.append(d)
    return result


def project(repo):
    repo = Path(repo)
    state_dir = repo / ".stratos"
    tasks_raw = Store(state_dir).tasks()
    tasks = []
    for t in tasks_raw:
        triage = t.get("triage")
        triage_verdict = triage["verdict"] if isinstance(triage, dict) else None
        tasks.append({
            "id": t["id"],
            "title": t["title"],
            "status": t["status"],
            "role": t.get("role"),
            "triage": triage_verdict,
        })
    counts = {}
    for t in tasks:
        s = t["status"]
        counts[s] = counts.get(s, 0) + 1

    all_events = Telemetry(state_dir / "telemetry.jsonl").load()
    last_60 = all_events[-60:]
    events = []
    for ev in last_60:
        trimmed = {}
        for k in KEEP:
            if k in ev:
                v = ev[k]
                if k in ("reason", "detail"):
                    v = str(v)[:300]
                trimmed[k] = v
        events.append(trimmed)

    updated = float(all_events[-1]["ts"]) if all_events else 0.0

    # Find current: single backward pass over all_events to find the newest start
    newest_start_idx = None
    for i in range(len(all_events) - 1, -1, -1):
        if all_events[i]["kind"] in ("call_start", "switch_start"):
            newest_start_idx = i
            break

    current = None
    if newest_start_idx is not None:
        ev = all_events[newest_start_idx]
        kind = ev["kind"]
        # Check if this start is finished by a later event
        finished = False
        if kind == "call_start":
            cid = ev.get("call_id")
            for j in range(newest_start_idx + 1, len(all_events)):
                if all_events[j]["kind"] == "call" and all_events[j].get("call_id") == cid:
                    finished = True
                    break
        elif kind == "switch_start":
            for j in range(newest_start_idx + 1, len(all_events)):
                if all_events[j]["kind"] == "switch":
                    finished = True
                    break

        if not finished:
            ts = float(ev["ts"])
            if time.time() - ts < STALE_S:
                if kind == "call_start":
                    current = {"kind": "call", "task": ev.get("task"),
                               "role": ev.get("role"),
                               "attempt": ev.get("attempt"),
                               "model": ev.get("model"),
                               "since": ts}
                else:
                    current = {"kind": "switch", "model": ev.get("model"),
                               "from_model": ev.get("from_model"),
                               "since": ts}

    # Stats
    calls_count = 0
    model_seconds = 0.0
    switch_seconds = 0.0
    for ev in all_events:
        if ev["kind"] == "call":
            calls_count += 1
            model_seconds += float(ev.get("seconds", 0))
        elif ev["kind"] == "switch":
            switch_seconds += float(ev.get("seconds", 0))

    stats = {
        "calls": calls_count,
        "model_seconds": round(model_seconds, 1),
        "switch_seconds": round(switch_seconds, 1),
    }

    return {
        "name": repo.name,
        "path": str(repo),
        "tasks": tasks,
        "counts": counts,
        "events": events,
        "updated": updated,
        "current": current,
        "stats": stats,
    }


def metrics(base_url):
    try:
        with urllib.request.urlopen(base_url + "/metrics", timeout=2) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return {
            "model": body["engine"]["model"],
            "live": body["live"],
            "hardware": body["hardware"],
            "totals": body["totals"],
            "history": {
                "gpu_util": body["history"]["gpu_util"][-60:],
                "gpu_mem_used": body["history"]["gpu_mem_used"][-60:],
            },
        }
    except Exception:
        return None


def snapshot(repos, metrics=None):
    projects = [project(r) for r in repos]
    projects.sort(key=lambda p: p["updated"], reverse=True)
    engine = metrics() if metrics is not None else None
    return {
        "time": time.time(),
        "projects": projects,
        "engine": engine,
    }


def make_server(repos, port, metrics=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            if self.path == "/":
                body = PAGE.read_text(encoding="utf-8").encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/state":
                body = json.dumps(snapshot(repos, metrics)).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
