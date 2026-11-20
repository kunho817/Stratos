"""Tests for task dashboard_live (P12, 2026-11-20, user: "only progress is dull - stream what it does, show the terminal
log"). The gateway streams each answer into .stratos/live/ (task gateway_stream); the run log is .stratos/run.log
(task runlog). The dashboard serves them.

dashboard.live(repo) -> {"call": <the JSON of .stratos/live/current.json, or None>, "text": the last 8000 characters
of .stratos/live/current.txt ("" when missing), "log": the last 200 lines of .stratos/run.log joined with "\\n"
("" when missing)}.
make_server(repos, port, metrics=None, home=None): when repos is None the project list is
default_repos(home) again on every request (a new trial shows up without a restart). GET /api/live?project=<name>
answers live(<the repo with that name>) as JSON (404 for an unknown name). The page is read from disk on every
request (as before), so a changed dashboard.html needs no restart.
dashboard.code_stamp(folder) -> the newest modification time of the *.py and *.html files in the folder (the
stratos package); `stratos dashboard` restarts itself (os.execv with the same arguments) when it grows."""
import json
import threading
import time
import urllib.request

from stratos import dashboard


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
