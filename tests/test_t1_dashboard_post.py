"""Tests for task t1_dashboard_post: fix do_POST in stratos/dashboard.py so the
request body is read as the very first action, and every error response
(403, 404, 400, plus the "else" 404 for non-/api/try paths) sends
Content-Length: 0.

The fix in do_POST:
  body_len = int(self.headers.get("Content-Length", 0))
  body = self.rfile.read(body_len) if body_len else b""
This runs before any path check, header check, or answer.
The /api/try branch uses the pre-read body (decoded to text).

The order of checks inside /api/try is unchanged:
  X-Stratos header check -> 403  (first, before project lookup),
  project lookup -> 404,
  try kind not cli -> 400,
  run_try -> 200.

The 200 body is json.dumps(result) with Python's default separators
(spaces after ":" and ","); tests parse it with json.loads, never
compare exact bytes or length.
"""
import json
import sys
import threading
import urllib.error
import urllib.request

from stratos import dashboard


CLI_TOML = (
    '[try]\nkind = "cli"\n'
    'command = ["{py}", "-m", "echoer", "{{file}}"]\n'
    'input_name = "in.md"\n'
)


def make_repo(root, name, toml):
    """Create a minimal project directory with .stratos/ files."""
    repo = root / name
    (repo / ".stratos").mkdir(parents=True)
    (repo / ".stratos" / "tasks.json").write_text("[]", encoding="utf-8")
    (repo / ".stratos" / "telemetry.jsonl").write_text("", encoding="utf-8")
    if toml is not None:
        (repo / "stratos.toml").write_text(toml, encoding="utf-8")
    return repo


def cli_repo(root):
    """A cli project 'Echo' that runs echoer on the pasted text."""
    repo = make_repo(root, "Echo", CLI_TOML.format(
        py=sys.executable.replace("\\", "/")))
    (repo / "echoer").mkdir()
    (repo / "echoer" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "echoer" / "__main__.py").write_text(
        "import sys\nname = sys.argv[1]\n"
        "print(name.endswith('in.md'), "
        "open(name, encoding='utf-8').read().upper())\n",
        encoding="utf-8")
    return repo


def static_repo(root):
    """A static project 'Game' with an index.html."""
    repo = make_repo(root, "Game",
        '[try]\nkind = "static"\nindex = "index.html"\n')
    (repo / "index.html").write_text("<h1>game</h1>", encoding="utf-8")
    return repo


def post(port, path, body=None, headers=None):
    """POST to the dashboard. Return (status, raw_body_bytes, resp_headers_dict)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def server(repos):
    """Start the dashboard server on a random port."""
    srv = dashboard.make_server(repos, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ─── 1. 403 response carries Content-Length: 0 ────────────────────────────────

def test_403_has_content_length_zero(tmp_path):
    """POST /api/try?project=Echo without X-Stratos → 403,
    response header must have Content-Length: 0."""
    cli_repo(tmp_path)
    srv = server([tmp_path / "Echo"])
    port = srv.server_address[1]
    try:
        code, _, hdrs = post(port, "/api/try?project=Echo",
                             {"text": "hi"}, {})
        # Step: missing X-Stratos header → 403.
        assert code == 403
        # Step: error responses must send Content-Length: 0
        #   before self.end_headers().
        assert hdrs.get("Content-Length") == "0"
    finally:
        srv.shutdown()
        srv.server_close()


# ─── 2. 404 response carries Content-Length: 0 ────────────────────────────────

def test_404_has_content_length_zero(tmp_path):
    """POST /api/try?project=Nope with X-Stratos: 1 → 404,
    response header must have Content-Length: 0."""
    cli_repo(tmp_path)
    srv = server([tmp_path / "Echo"])
    port = srv.server_address[1]
    try:
        code, _, hdrs = post(port, "/api/try?project=Nope",
                             {"text": "hi"}, {"X-Stratos": "1"})
        # Step: unknown project → 404.
        assert code == 404
        # Step: Content-Length: 0 present on 404.
        assert hdrs.get("Content-Length") == "0"
    finally:
        srv.shutdown()
        srv.server_close()


# ─── 3. 400 response carries Content-Length: 0 ────────────────────────────────

def test_400_has_content_length_zero(tmp_path):
    """POST /api/try?project=Game (kind=static) with X-Stratos: 1
    → 400, response header must have Content-Length: 0."""
    cli_repo(tmp_path)
    static_repo(tmp_path)
    srv = server([tmp_path / "Echo", tmp_path / "Game"])
    port = srv.server_address[1]
    try:
        code, _, hdrs = post(port, "/api/try?project=Game",
                             {"text": "hi"}, {"X-Stratos": "1"})
        # Step: static project, try kind != cli → 400.
        assert code == 400
        # Step: Content-Length: 0 present on 400.
        assert hdrs.get("Content-Length") == "0"
    finally:
        srv.shutdown()
        srv.server_close()


# ─── 4. "else" 404 (non-/api/try path) carries Content-Length: 0 ──────────────

def test_non_api_try_404_has_content_length_zero(tmp_path):
    """POST /api/other → 404 (the else branch), response header
    must have Content-Length: 0."""
    cli_repo(tmp_path)
    srv = server([tmp_path / "Echo"])
    port = srv.server_address[1]
    try:
        code, _, hdrs = post(port, "/api/other", {"text": "x"},
                             {"X-Stratos": "1"})
        # Step: path is not /api/try → 404.
        assert code == 404
        # Step: Content-Length: 0 present.
        assert hdrs.get("Content-Length") == "0"
    finally:
        srv.shutdown()
        srv.server_close()


# ─── 5. 403 fires before 404 (header check precedes project lookup) ────────────

def test_403_before_404(tmp_path):
    """POST to an unknown project WITHOUT X-Stratos → 403, not 404.
    The header check runs first, so 403 wins."""
    cli_repo(tmp_path)
    srv = server([tmp_path / "Echo"])
    port = srv.server_address[1]
    try:
        code, _, hdrs = post(port, "/api/try?project=Nope",
                             {"text": "hi"}, {})
        # Step: X-Stratos is missing → 403 fires first,
        #   before the project lookup that would give 404.
        assert code == 403
        # Step: Content-Length: 0 on 403.
        assert hdrs.get("Content-Length") == "0"
    finally:
        srv.shutdown()
        srv.server_close()


# ─── 6. 200 success path works; body parsed with json.loads ───────────────────

def test_200_success_parsed_with_json(tmp_path):
    """POST /api/try?project=Echo with valid X-Stratos and body
    → 200; the response body is valid JSON with keys
    code, stdout, stderr."""
    cli_repo(tmp_path)
    srv = server([tmp_path / "Echo"])
    port = srv.server_address[1]
    try:
        code, raw, hdrs = post(port, "/api/try?project=Echo",
                               {"text": "hi"}, {"X-Stratos": "1"})
        # Step: cli project, valid header → 200.
        assert code == 200
        # Step: parse with json.loads, not byte comparison.
        result = json.loads(raw)
        # Step: echoer prints "True HI\n" for input "hi"
        #   (True for endswith 'in.md', upper() of "hi").
        # Expected dict: {"code": 0, "stdout": "True HI\n", "stderr": ""}.
        assert result["code"] == 0
        assert result["stdout"].strip() == "True HI"
        assert result["stderr"] == ""
        # Step: Content-Type is application/json.
        assert "application/json" in hdrs.get("Content-Type", "")
    finally:
        srv.shutdown()
        srv.server_close()


# ─── 7. 200 body uses default separators (has spaces) ─────────────────────────

def test_200_body_is_json_default_separators(tmp_path):
    """The 200 response body has spaces after ':' and ','
    (json.dumps default separators), NOT compact form."""
    cli_repo(tmp_path)
    srv = server([tmp_path / "Echo"])
    port = srv.server_address[1]
    try:
        code, raw, _ = post(port, "/api/try?project=Echo",
                            {"text": "hi"}, {"X-Stratos": "1"})
        # Step: 200.
        assert code == 200
        # Step: default separators → ": 0" (colon-space) in bytes.
        assert b'"code": 0' in raw
        # Step: compact form → ":0" must be absent.
        assert b'"code":0' not in raw
        # Step: round-trip parse succeeds.
        result = json.loads(raw)
        # Step: echoer output.
        assert result == {"code": 0, "stdout": "True HI\n",
                          "stderr": ""}
    finally:
        srv.shutdown()
        srv.server_close()


# ─── 8. body text reaches run_try output ──────────────────────────────────────

def test_body_text_reaches_run_try(tmp_path):
    """The text field in the POST body is forwarded to run_try;
    the stdout in the response reflects the input."""
    cli_repo(tmp_path)
    srv = server([tmp_path / "Echo"])
    port = srv.server_address[1]
    try:
        code, raw, _ = post(port, "/api/try?project=Echo",
                            {"text": "hello", "args": ""},
                            {"X-Stratos": "1"})
        # Step: 200.
        assert code == 200
        result = json.loads(raw)
        # Step: echoer uppercases "hello" → "HELLO".
        # Expected stdout: "True HELLO\n".
        assert "HELLO" in result["stdout"]
    finally:
        srv.shutdown()
        srv.server_close()


# ─── 9. Content-Length: 0 (empty body) does not crash the server ──────────────

def test_content_length_zero_body_empty_no_crash(tmp_path):
    """POST with Content-Length: 0 and no body.
    body_len = 0, body = b"". json.loads(b"") raises;
    the server must survive and stay alive."""
    cli_repo(tmp_path)
    srv = server([tmp_path / "Echo"])
    port = srv.server_address[1]
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/try?project=Echo",
            data=b"",
            headers={"Content-Type": "application/json",
                     "X-Stratos": "1",
                     "Content-Length": "0"})
        # Step: body_len = int("0") = 0, body = b"".
        # json.loads(b"") raises JSONDecodeError inside do_POST.
        # The HTTP server handler catches the exception;
        # the connection closes without killing the server.
        # The client receives some response (error status)
        # or the connection closes; either way no crash.
        try:
            resp = urllib.request.urlopen(req, timeout=20)
            resp.read()
            resp.close()
        except urllib.error.HTTPError:
            pass
        # Step: server is still alive — next request succeeds.
        code, raw, _ = post(port, "/api/try?project=Echo",
                            {"text": "x"}, {"X-Stratos": "1"})
        # Step: cli project → 200.
        assert code == 200
        result = json.loads(raw)
        assert result["code"] == 0
    finally:
        srv.shutdown()
        srv.server_close()


# ─── 10. missing Content-Length header treated as zero ────────────────────────

def test_missing_content_length_header_treated_as_zero(tmp_path):
    """POST to /api/try?project=Echo with X-Stratos: 1, no body
    sent, and no Content-Length header.
    body_len = int(self.headers.get("Content-Length", 0)) → 0,
    body = b"". json.loads(b"") raises; server must not crash."""
    cli_repo(tmp_path)
    srv = server([tmp_path / "Echo"])
    port = srv.server_address[1]
    try:
        # Step: build a POST with data=None (no body, no
        # Content-Length header in our custom headers).
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/try?project=Echo",
            data=None,
            headers={"Content-Type": "application/json",
                     "X-Stratos": "1"})
        # Step: headers.get("Content-Length", 0) → 0; body = b"".
        # json.loads(b"") raises; server catches, connection
        # closes; no crash.
        try:
            r = urllib.request.urlopen(req, timeout=20)
            r.read()
            r.close()
        except urllib.error.HTTPError:
            pass
        # Step: server alive → next request works.
        code, raw, _ = post(port, "/api/try?project=Echo",
                            {"text": "y"}, {"X-Stratos": "1"})
        # Step: cli, 200.
        assert code == 200
        assert json.loads(raw)["code"] == 0
    finally:
        srv.shutdown()
        srv.server_close()


# ─── 11. sequential 403, 404, 400 requests all complete cleanly ───────────────

def test_sequential_errors_no_abort(tmp_path):
    """Three requests that get 403, 404, 400, each with a body.
    The body is read first in every case, so the connection
    closes cleanly (no ConnectionAbortedError / WinError 10053).
    After the three errors the server is still alive."""
    cli_repo(tmp_path)
    static_repo(tmp_path)
    srv = server([tmp_path / "Echo", tmp_path / "Game"])
    port = srv.server_address[1]
    try:
        # Step: 403 — missing X-Stratos.
        code, _, hdrs = post(port, "/api/try?project=Echo",
                             {"text": "a"}, {})
        # Expected: 403, Content-Length: 0.
        assert code == 403
        assert hdrs.get("Content-Length") == "0"
        # Step: 404 — unknown project.
        code, _, hdrs = post(port, "/api/try?project=Nope",
                             {"text": "b"}, {"X-Stratos": "1"})
        # Expected: 404, Content-Length: 0.
        assert code == 404
        assert hdrs.get("Content-Length") == "0"
        # Step: 400 — static project.
        code, _, hdrs = post(port, "/api/try?project=Game",
                             {"text": "c"}, {"X-Stratos": "1"})
        # Expected: 400, Content-Length: 0.
        assert code == 400
        assert hdrs.get("Content-Length") == "0"
        # Step: server alive after all three.
        code, raw, _ = post(port, "/api/try?project=Echo",
                            {"text": "d"}, {"X-Stratos": "1"})
        # Expected: 200.
        assert code == 200
        result = json.loads(raw)
        assert result["stdout"].strip() == "True D"
    finally:
        srv.shutdown()
        srv.server_close()


# ─── 12. error responses have no body content ─────────────────────────────────

def test_error_responses_have_no_body(tmp_path):
    """403, 404, 400 responses carry Content-Length: 0,
    so the response body is empty bytes."""
    cli_repo(tmp_path)
    static_repo(tmp_path)
    srv = server([tmp_path / "Echo", tmp_path / "Game"])
    port = srv.server_address[1]
    try:
        code, body, hdrs = post(port, "/api/try?project=Echo",
                                 {"text": "x"}, {})
        # Step: 403. Content-Length: 0 → empty body.
        assert code == 403
        assert hdrs.get("Content-Length") == "0"
        # Step: body read is zero bytes.
        assert body == b""

        code, body, hdrs = post(port, "/api/try?project=Nope",
                                 {"text": "x"}, {"X-Stratos": "1"})
        # Step: 404. Content-Length: 0 → empty body.
        assert code == 404
        assert hdrs.get("Content-Length") == "0"
        assert body == b""

        code, body, hdrs = post(port, "/api/try?project=Game",
                                 {"text": "x"}, {"X-Stratos": "1"})
        # Step: 400. Content-Length: 0 → empty body.
        assert code == 400
        assert hdrs.get("Content-Length") == "0"
        assert body == b""
    finally:
        srv.shutdown()
        srv.server_close()
