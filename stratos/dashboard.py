"""Dashboard: project snapshot and local server.

KEEP, PAGE = Path(__file__).parent / "dashboard.html", default_repos, project, metrics, snapshot, make_server."""
import json
import mimetypes
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from stratos.state import Store
from stratos.telemetry import Telemetry
from stratos import report
import urllib.request
import urllib.parse

KEEP = ("ts", "kind", "task", "role", "attempt", "model", "from_model",
        "result", "seconds", "verdict", "reason", "detail", "finish",
        "completion_tokens")
PAGE = Path(__file__).parent / "dashboard.html"
STALE_S = 1800
TRY_TIMEOUT_S = 10


def default_repos(home):
    home = Path(home)
    result = [home]
    trials = home.parent / "Trials"
    if home.exists() and trials.is_dir():
        for d in sorted(trials.iterdir()):
            if d.is_dir() and (d / ".stratos").is_dir():
                result.append(d)
    return result


def live(repo):
    repo = Path(repo)
    live_dir = repo / ".stratos" / "live"
    current_json = live_dir / "current.json"
    current_txt = live_dir / "current.txt"
    run_log = repo / ".stratos" / "run.log"
    try:
        call = json.loads(current_json.read_text(encoding="utf-8"))
    except Exception:
        call = None
    try:
        text = current_txt.read_text(encoding="utf-8")[-8000:]
    except Exception:
        text = ""
    try:
        log = run_log.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
    except Exception:
        log = []
    return {"call": call, "text": text, "log": "\n".join(log)}


def code_stamp(folder):
    folder = Path(folder)
    stamp = 0.0
    for pattern in ("*.py", "*.html"):
        for f in folder.glob(pattern):
            if f.is_file():
                stamp = max(stamp, f.stat().st_mtime)
    return stamp


def watch_code(folder):
    folder = Path(folder)
    start = code_stamp(folder)

    def _loop():
        while True:
            time.sleep(2)
            if code_stamp(folder) > start:
                os.execv(sys.executable, [sys.executable, "-m", "stratos"] + sys.argv[1:])

    threading.Thread(target=_loop, daemon=True).start()


def try_config(repo):
    repo = Path(repo)
    toml_path = repo / "stratos.toml"
    try:
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    tbl = data.get("try")
    if not isinstance(tbl, dict):
        return None
    if tbl.get("kind") in ("cli", "static"):
        return tbl
    return None


def run_try(repo, text, args=""):
    repo = Path(repo)
    cfg = try_config(repo)
    if cfg is None:
        raise ValueError("not a cli project")
    if cfg.get("kind") != "cli":
        raise ValueError("not a cli project")
    input_name = cfg.get("input_name", "input.txt")
    command = cfg["command"]
    with tempfile.TemporaryDirectory() as td:
        file_path = str(Path(td) / input_name)
        Path(file_path).write_text(text, encoding="utf-8")
        cmd = [str(item).replace("{file}", file_path) for item in command]
        if args:
            cmd.extend(shlex.split(args))
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo)
        # (Claude) the output is read as UTF-8: a Python child on Windows would print in cp949 and fail on "É" or Korean
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        try:
            r = subprocess.run(cmd, cwd=str(repo), env=env,
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               timeout=TRY_TIMEOUT_S, shell=False)
            code = r.returncode
            stdout = r.stdout[:20000]
            stderr = r.stderr[:20000]
        except subprocess.TimeoutExpired:
            code = -1
            stdout = ""
            stderr = f"timed out after {TRY_TIMEOUT_S} s"
    return {"code": code, "stdout": stdout, "stderr": stderr}


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

    cfg = try_config(repo)
    try_kind = cfg["kind"] if cfg else None

    return {
        "name": repo.name,
        "path": str(repo),
        "tasks": tasks,
        "counts": counts,
        "events": events,
        "updated": updated,
        "current": current,
        "stats": stats,
        "efficiency": report.efficiency(all_events),
        "try": try_kind,
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


def make_server(repos, port, metrics=None, home=None):
    def repos_for():
        return repos if repos is not None else default_repos(home)

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
                body = json.dumps(snapshot(repos_for(), metrics)).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
            elif self.path.startswith("/api/live"):
                qs = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(qs)
                name = params.get("project", [None])[0]
                found = None
                for r in repos_for():
                    if Path(r).name == name:
                        found = r
                        break
                if found is None:
                    self.send_response(404)
                    self.end_headers()
                else:
                    body = json.dumps(live(found)).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(body)
            elif self.path.startswith("/try/"):
                parts = self.path.split("/", 3)
                if len(parts) < 4:
                    self.send_response(404)
                    self.end_headers()
                    return
                name = parts[2]
                subpath = parts[3]
                found = None
                for r in repos_for():
                    if Path(r).name == name:
                        found = r
                        break
                if found is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                repo = Path(found)
                cfg = try_config(repo)
                if cfg is None or cfg.get("kind") != "static":
                    self.send_response(404)
                    self.end_headers()
                    return
                file = (repo / subpath).resolve()
                repo_resolved = repo.resolve()
                if not str(file).startswith(str(repo_resolved)):
                    self.send_response(404)
                    self.end_headers()
                    return
                if not file.is_file():
                    self.send_response(404)
                    self.end_headers()
                    return
                ctype = mimetypes.guess_type(str(file))[0] or "application/octet-stream"
                data = file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/api/try":
                qs = parsed.query
                params = urllib.parse.parse_qs(qs)
                name = params.get("project", [None])[0]
                hdr = self.headers.get("X-Stratos", "")
                if hdr != "1":
                    self.send_response(403)
                    self.end_headers()
                    return
                found = None
                for r in repos_for():
                    if Path(r).name == name:
                        found = r
                        break
                if found is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                repo = Path(found)
                cfg = try_config(repo)
                if cfg is None or cfg.get("kind") != "cli":
                    self.send_response(400)
                    self.end_headers()
                    return
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                body = json.loads(raw)
                result = run_try(repo, body.get("text", ""), body.get("args", ""))
                resp = json.dumps(result).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            else:
                self.send_response(404)
                self.end_headers()

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
