"""Tests for task t1_dashboard_post: fix do_POST in stratos/dashboard.py to read
the request body as the very first action, and send Content-Length: 0 on every
error response (403, 404, 400).

Changes in do_POST:
- body_len = int(self.headers.get("Content-Length", 0));
  body = self.rfile.read(body_len) if body_len else b""  — before any path check,
  header check, or answer.
- The /api/try branch decodes the pre-read body and uses it (no rfile.read inside
  the branch).
- Each error response (403, 404, 400) adds self.send_header("Content-Length", "0")
  before self.end_headers().

OUTDATED: tests/test_dashboard_try.py::test_server - this test POSTs bodies to
paths that return 403/404/400; the old do_POST did not read the body before
answering, causing ConnectionAbortedError on Windows under parallel runs. After
this fix the server consumes the body first, making the test reliable.
"""
import http.client
import json
import threading

from stratos import dashboard


CLI_TOML = '[try]\nkind = "cli"\ncommand = ["python", "-m", "echoer", "{file}"]\ninput_name = "in.md"\n'
STATIC_TOML = '[try]\nkind = "static"\nindex = "index.html"\n'


def make_repo(root, name, toml):
    """Build a repo with .stratos dirs and stratos.toml."""
    repo = root / name
    (repo / ".stratos").mkdir(parents=True)
    (repo / ".stratos" / "tasks.json").write_text("[]", encoding="utf-8")
    (repo / ".stratos" / "telemetry.jsonl").write_text("", encoding="utf-8")
    (repo / "stratos.toml").write_text(toml, encoding="utf-8")
    return repo


def start_server(repos):
    server = dashboard.make_server(repos, 0)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, port


def _send_post(port, path, body, headers):
    """Send one POST, return the response and its body bytes."""
    conn = http.client.HTTPConnection("127.0.0.1", port)
    hdrs = dict(headers)
    hdrs["Content-Length"] = str(len(body))
    conn.request("POST", path, body=body, headers=hdrs)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp, data


def test_403_reads_body_first_and_sends_content_length_zero(tmp_path):
    """POST /api/try?project=Echo with a body, no X-Stratos header.
    The server must read the body before sending 403, and the response
    must carry Content-Length: 0."""
    make_repo(tmp_path, "Echo", CLI_TOML)
    server, port = start_server([tmp_path / "Echo"])
    try:
        body = json.dumps({"text": "hello"}).encode("utf-8")
        resp, _ = _send_post(port, "/api/try?project=Echo", body,
                             {"Content-Type": "application/json"})
        # Step: X-Stratos header is missing → forbidden → 403
        assert resp.status == 403
        # Step: error response must include Content-Length: 0
        assert resp.getheader("Content-Length") == "0"
    finally:
        server.shutdown()
        server.server_close()


def test_404_api_try_reads_body_first_and_sends_content_length_zero(tmp_path):
    """POST /api/try?project=Nope (unknown project) with a body.
    Body is read, 404 returned, Content-Length: 0 present."""
    make_repo(tmp_path, "Echo", CLI_TOML)
    server, port = start_server([tmp_path / "Echo"])
    try:
        body = json.dumps({"text": "hello"}).encode("utf-8")
        resp, _ = _send_post(port, "/api/try?project=Nope", body,
                             {"Content-Type": "application/json",
                              "X-Stratos": "1"})
        # Step: project "Nope" is not in the repos → 404
        assert resp.status == 404
        # Step: Content-Length: 0 on error
        assert resp.getheader("Content-Length") == "0"
    finally:
        server.shutdown()
        server.server_close()


def test_400_reads_body_first_and_sends_content_length_zero(tmp_path):
    """POST /api/try?project=Game (static project, not cli) with X-Stratos: 1.
    Body is read, 400 returned, Content-Length: 0 present."""
    make_repo(tmp_path, "Echo", CLI_TOML)
    make_repo(tmp_path, "Game", STATIC_TOML)
    server, port = start_server([tmp_path / "Echo", tmp_path / "Game"])
    try:
        body = json.dumps({"text": "hello"}).encode("utf-8")
        resp, _ = _send_post(port, "/api/try?project=Game", body,
                             {"Content-Type": "application/json",
                              "X-Stratos": "1"})
        # Step: Game is "static", not "cli" → 400
        assert resp.status == 400
        # Step: Content-Length: 0 on error
        assert resp.getheader("Content-Length") == "0"
    finally:
        server.shutdown()
        server.server_close()


def test_404_other_path_reads_body_first_and_sends_content_length_zero(tmp_path):
    """POST to /other (not /api/try) with a body.
    Body is read, 404 returned, Content-Length: 0 present."""
    make_repo(tmp_path, "Echo", CLI_TOML)
    server, port = start_server([tmp_path / "Echo"])
    try:
        body = b"raw bytes"
        resp, _ = _send_post(port, "/other", body,
                             {"Content-Type": "application/json"})
        # Step: path is not /api/try → 404
        assert resp.status == 404
        # Step: Content-Length: 0
        assert resp.getheader("Content-Length") == "0"
    finally:
        server.shutdown()
        server.server_close()


def test_api_try_uses_pre_read_body(tmp_path, monkeypatch):
    """The /api/try branch uses the body that do_POST read at the start,
    not a second rfile.read. Verify run_try receives text/args from
    the pre-read body."""
    make_repo(tmp_path, "Echo", CLI_TOML)
    server, port = start_server([tmp_path / "Echo"])
    calls = []
    monkeypatch.setattr(dashboard, "run_try",
                        lambda repo, text, args="": (calls.append((text, args))
                                                     or {"code": 0, "stdout": "ok",
                                                        "stderr": ""}))
    try:
        body = json.dumps({"text": "abc", "args": "1 2"}).encode("utf-8")
        resp, data = _send_post(port, "/api/try?project=Echo", body,
                                {"Content-Type": "application/json",
                                 "X-Stratos": "1"})
        # Step: 200 for valid cli project
        assert resp.status == 200
        # Step: run_try was called with text="abc" and args="1 2"
        # Expected: ("abc", "1 2")
        assert calls == [("abc", "1 2")]
        # Step: response JSON matches the monkeypatched result
        # Expected: {"code": 0, "stdout": "ok", "stderr": ""}
        assert json.loads(data.decode("utf-8")) == {"code": 0, "stdout": "ok", "stderr": ""}
    finally:
        server.shutdown()
        server.server_close()


def test_connection_reusable_after_body_read(tmp_path):
    """After a 403 that consumed the body, the same connection can handle
    a second POST → 200. This proves the first body was fully read, leaving
    no pending bytes that would abort the connection on Windows."""
    make_repo(tmp_path, "Echo", CLI_TOML)
    server, port = start_server([tmp_path / "Echo"])
    try:
        body1 = json.dumps({"text": "first"}).encode("utf-8")
        body2 = json.dumps({"text": "second"}).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", port)
        # Step: first POST – no X-Stratos → 403, body consumed
        conn.request("POST", "/api/try?project=Echo", body=body1,
                     headers={"Content-Length": str(len(body1))})
        resp1 = conn.getresponse()
        resp1.read()
        # Step: 403
        assert resp1.status == 403
        # Step: send second POST on the SAME connection – body2 consumed
        conn.request("POST", "/api/try?project=Echo", body=body2,
                     headers={"Content-Length": str(len(body2)),
                              "X-Stratos": "1"})
        resp2 = conn.getresponse()
        resp2.read()
        # Step: 200 – connection was alive, proving first body was consumed
        assert resp2.status == 200
        conn.close()
    finally:
        server.shutdown()
        server.server_close()


def test_missing_content_length_header_treated_as_zero(tmp_path):
    """POST with no Content-Length header: body_len = 0, body = b"",
    server does not crash, returns 404 for unknown project with
    Content-Length: 0 in the response."""
    make_repo(tmp_path, "Echo", CLI_TOML)
    server, port = start_server([tmp_path / "Echo"])
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port)
        # Step: no Content-Length header → int("0") = 0, body = b""
        conn.request("POST", "/api/try?project=Nope")
        resp = conn.getresponse()
        resp.read()
        # Step: 404 (unknown project)
        assert resp.status == 404
        # Step: Content-Length: 0 in response
        # Expected: "0"
        assert resp.getheader("Content-Length") == "0"
        conn.close()
    finally:
        server.shutdown()
        server.server_close()


def test_content_length_zero_body_empty_no_crash(tmp_path):
    """POST with Content-Length: 0 header: body_len = 0, body = b"".
    Server reads empty body, returns 404, Content-Length: 0, no crash
    from trying to JSON-parse empty bytes."""
    make_repo(tmp_path, "Echo", CLI_TOML)
    server, port = start_server([tmp_path / "Echo"])
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("POST", "/api/try?project=Nope",
                     body=b"",
                     headers={"Content-Length": "0"})
        resp = conn.getresponse()
        resp.read()
        # Step: 404 (unknown project)
        # Expected: 404
        assert resp.status == 404
        # Step: Content-Length: 0 in response
        # Expected: "0"
        assert resp.getheader("Content-Length") == "0"
        conn.close()
    finally:
        server.shutdown()
        server.server_close()


def test_200_success_path_still_works(tmp_path, monkeypatch):
    """The normal 200 path (valid project, valid header, valid body)
    keeps working with Content-Type and Content-Length of the JSON
    response (not Content-Length: 0)."""
    make_repo(tmp_path, "Echo", CLI_TOML)
    server, port = start_server([tmp_path / "Echo"])
    monkeypatch.setattr(dashboard, "run_try",
                        lambda repo, text, args="": {"code": 0, "stdout": "x", "stderr": ""})
    try:
        body = json.dumps({"text": "y", "args": ""}).encode("utf-8")
        resp, data = _send_post(port, "/api/try?project=Echo", body,
                                {"Content-Type": "application/json",
                                 "X-Stratos": "1"})
        # Step: 200
        assert resp.status == 200
        # Step: Content-Type is application/json
        assert resp.getheader("Content-Type") == "application/json; charset=utf-8"
        # Step: Content-Length is the byte length of the JSON response
        # Expected: {"code":0,"stdout":"x","stderr":""} → 31 chars → 31 bytes
        # Step: 31
        resp_bytes = data
        assert len(resp_bytes) == 31
        assert resp.getheader("Content-Length") == "31"
    finally:
        server.shutdown()
        server.server_close()


def test_all_three_error_codes_have_content_length_zero(tmp_path):
    """A single server answers 403, 404, and 400; every one of the
    three responses must include Content-Length: 0."""
    make_repo(tmp_path, "Echo", CLI_TOML)
    make_repo(tmp_path, "Game", STATIC_TOML)
    server, port = start_server([tmp_path / "Echo", tmp_path / "Game"])
    try:
        body = json.dumps({"text": "x"}).encode("utf-8")
        hdrs = {"Content-Type": "application/json",
                "Content-Length": str(len(body))}

        # 403: no X-Stratos
        resp403, _ = _send_post(port, "/api/try?project=Echo", body, hdrs)
        # Step: 403 + Content-Length: 0
        # Expected: status=403, CL="0"
        assert resp403.status == 403
        assert resp403.getheader("Content-Length") == "0"

        # 404: unknown project
        resp404, _ = _send_post(port, "/api/try?project=Nope",
                                body, {**hdrs, "X-Stratos": "1"})
        # Step: 404 + Content-Length: 0
        # Expected: status=404, CL="0"
        assert resp404.status == 404
        assert resp404.getheader("Content-Length") == "0"

        # 400: static project
        resp400, _ = _send_post(port, "/api/try?project=Game",
                                body, {**hdrs, "X-Stratos": "1"})
        # Step: 400 + Content-Length: 0
        # Expected: status=400, CL="0"
        assert resp400.status == 400
        assert resp400.getheader("Content-Length") == "0"
    finally:
        server.shutdown()
        server.server_close()


def test_body_read_before_checks_not_after(tmp_path, monkeypatch):
    """The body read must happen before any path, header, or project
    check. Verify: POST /api/try?project=Nope with a body, and
    monkeypatch make_server's repos_for to prove run_try is never
    called (body consumed before project lookup)."""
    make_repo(tmp_path, "Echo", CLI_TOML)
    server, port = start_server([tmp_path / "Echo"])
    try:
        body = json.dumps({"text": "x"}).encode("utf-8")
        # Step: send POST to unknown project with body
        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("POST", "/api/try?project=Nope", body=body,
                     headers={"Content-Length": str(len(body)),
                              "X-Stratos": "1"})
        resp = conn.getresponse()
        resp.read()
        # Step: 404
        # Expected: 404
        assert resp.status == 404
        # Step: body consumed → connection usable
        # Expected: second request succeeds
        conn.request("POST", "/api/try?project=Echo",
                     body=json.dumps({"text": "z"}).encode("utf-8"),
                     headers={"Content-Length": str(len(json.dumps({"text": "z"}))),
                              "X-Stratos": "1"})
        resp2 = conn.getresponse()
        resp2.read()
        # Step: 200
        # Expected: 200
        assert resp2.status == 200
        conn.close()
    finally:
        server.shutdown()
        server.server_close()
