"""Tests for task dashboard_try (P12, 2026-11-20, user: "let me test what was built from the dashboard"). Each trial can
say in its stratos.toml how to try it:

    [try]
    kind = "cli"                                   # a command run on text pasted in the page
    command = ["python", "-m", "quill", "{file}"]  # "{file}" = a temporary file holding the text
    input_name = "input.md"                        # that file's name (default "input.txt")
or  kind = "static" with index = "index.html"      # a web game served from the repo

dashboard.try_config(repo) -> the [try] table of repo/stratos.toml (tomllib) or None (no file, no table, a kind other
than "cli"/"static").
dashboard.run_try(repo, text, args="") -> {"code", "stdout", "stderr"} for a "cli" project: the text is written
(UTF-8) to a new temporary folder as input_name; the command is the configured list with "{file}" replaced by that
path, plus shlex.split(args) appended; it runs without a shell, cwd=repo, env PYTHONPATH=repo, timeout 10 s
(code -1 and stderr "timed out after 10 s"), with PYTHONIOENCODING=utf-8 and PYTHONUTF8=1 (Claude: a Python child printed in cp949 and failed on non-ASCII text); stdout and stderr are cut to 20000 characters. A project that is not
"cli" raises ValueError.
Server: POST /api/try?project=<name> with a JSON body {"text": ..., "args": ...} answers run_try as JSON; it needs
the header "X-Stratos: 1" (403 without it - a page on another site cannot add it without a CORS preflight, which
this server never allows); 404 for an unknown project, 400 for a project that is not "cli".
GET /try/<name>/<path> serves a file of a "static" project (Content-Type from mimetypes), 404 for paths outside the
repo, missing files, or projects that are not "static". GET /api/state gives each project "try": its kind or None."""
import json
import sys
import threading
import urllib.error
import urllib.request

from stratos import dashboard

CLI_TOML = '[try]\nkind = "cli"\ncommand = ["{py}", "-m", "echoer", "{{file}}"]\ninput_name = "in.md"\n'


def make(root, name, toml):
    repo = root / name
    (repo / ".stratos").mkdir(parents=True)
    (repo / ".stratos" / "tasks.json").write_text("[]", encoding="utf-8")
    (repo / ".stratos" / "telemetry.jsonl").write_text("", encoding="utf-8")
    if toml is not None:
        (repo / "stratos.toml").write_text(toml, encoding="utf-8")
    return repo


def cli_repo(root):
    repo = make(root, "Echo", CLI_TOML.format(py=sys.executable.replace("\\", "/")))
    (repo / "echoer").mkdir()
    (repo / "echoer" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "echoer" / "__main__.py").write_text(
        "import sys\nname = sys.argv[1]\nprint(name.endswith('in.md'), open(name, encoding='utf-8').read().upper(),"
        " *sys.argv[2:])\n", encoding="utf-8")
    return repo


def test_try_config(tmp_path):
    assert dashboard.try_config(cli_repo(tmp_path))["kind"] == "cli"
    assert dashboard.try_config(make(tmp_path, "None", None)) is None
    assert dashboard.try_config(make(tmp_path, "Odd", '[try]\nkind = "shell"\n')) is None


def test_run_try(tmp_path):
    repo = cli_repo(tmp_path)
    r = dashboard.run_try(repo, "héllo", args="--x 'a b'")
    assert r["code"] == 0 and r["stdout"].strip() == "True HÉLLO --x a b"
    try:
        dashboard.run_try(make(tmp_path, "Static", '[try]\nkind = "static"\nindex = "index.html"\n'), "x")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_server(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "TRY_TIMEOUT_S", 60)
    cli_repo(tmp_path)
    game = make(tmp_path, "Game", '[try]\nkind = "static"\nindex = "index.html"\n')
    (game / "index.html").write_text("<h1>game</h1>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("no", encoding="utf-8")
    server = dashboard.make_server([tmp_path / "Echo", game], 0)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def call(path, body=None, header=True):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **({"X-Stratos": "1"} if header else {})})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, ""
    try:
        code, body = call("/api/try?project=Echo", {"text": "hi", "args": ""})
        assert code == 200 and json.loads(body)["stdout"].strip() == "True HI"
        assert call("/api/try?project=Echo", {"text": "hi"}, header=False)[0] == 403
        assert call("/api/try?project=Nope", {"text": "hi"})[0] == 404
        assert call("/api/try?project=Game", {"text": "hi"})[0] == 400
        assert call("/try/Game/index.html") == (200, "<h1>game</h1>")
        assert call("/try/Game/../secret.txt")[0] == 404
        assert call("/try/Echo/echoer/__main__.py")[0] == 404
        state = json.loads(call("/api/state")[1])
        assert {p["name"]: p["try"] for p in state["projects"]} == {"Echo": "cli", "Game": "static"}
    finally:
        server.shutdown()
        server.server_close()
