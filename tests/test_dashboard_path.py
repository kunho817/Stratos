"""Tests for task dashboard_path: the static try handler in make_server checks
Path(resolved_file).is_relative_to(Path(resolved_repo_folder)) instead of
str(file).startswith(str(repo_resolved)), so a sibling folder whose name
starts with the repo's name (e.g. "Current2" beside "Current") is refused
with 404.  The repo folder is the resolved form of the repo found in the
server's repo list (config.REPO when running standalone).

OUTDATED: tests/test_dashboard_try.py::test_server - the server test creates
tmp_path/secret.txt and tmp_path/Game; its "/try/Game/../secret.txt" check
(404) still passes. No sibling-prefix case is covered, so no assertion
breaks; this task adds coverage for that case.

All assertions use Path.is_relative_to semantics; the string-prefix check is
not tested (the old behaviour must be replaced).

monkeypatch: no network, no GPU, no real models.  Servers run on ephemeral
127.0.0.1 ports and are shut down.
"""

import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from stratos import dashboard


STATIC_TOML = '[try]\nkind = "static"\nindex = "index.html"\n'


def make_repo(root, name, toml=STATIC_TOML):
    """A minimal static-try repo with .stratos dirs on disk."""
    repo = root / name
    (repo / ".stratos").mkdir(parents=True, exist_ok=True)
    (repo / ".stratos" / "tasks.json").write_text("[]", encoding="utf-8")
    (repo / ".stratos" / "telemetry.jsonl").write_text("", encoding="utf-8")
    if toml is not None:
        (repo / "stratos.toml").write_text(toml, encoding="utf-8")
    return repo


def start_server(repos):
    """Start a server on port 0 and return (server, get) where get(path)
    returns (status, body_bytes)."""
    server = dashboard.make_server(repos, 0)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    def get(path):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}{path}", timeout=10
            ) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""

    return server, get


# ─── 1. sibling whose name starts with the repo name ──────────────────────────

def test_sibling_starting_with_repo_name_is_refused(tmp_path):
    """Repo "Current" beside sibling "Current2": string-prefix accepts
    tmp_path/Current2 (starts with tmp_path/Current); is_relative_to
    rejects it, so the file in Current2 must be 404.
    subpath "../Current2/index.html": (Current / "../Current2/index.html")
    .resolve() = tmp_path/Current2/index.html
    str prefix: str(tmp_path/Current2/index.html).startswith(str(tmp_path/Current))
      → True
    is_relative_to: Path(tmp_path/Current2/index.html).is_relative_to(
      Path(tmp_path/Current)) → False
    Expected: 404"""
    repo = make_repo(tmp_path, "Current")
    sibling = make_repo(tmp_path, "Current2")
    (sibling / "index.html").write_text("<h1>sibling</h1>", encoding="utf-8")
    server, get = start_server([repo, sibling])
    try:
        # Expected: 404 — Current2 is NOT inside Current
        status, body = get("/try/Current/../Current2/index.html")
        assert status == 404
        # Expected: body is empty
        assert body == b""
    finally:
        server.shutdown()
        server.server_close()


# ─── 2. file inside the repo is served ────────────────────────────────────────

def test_file_inside_repo_is_served(tmp_path):
    """A file inside the repo passes is_relative_to and is served.
    subpath "index.html": (Current / "index.html").resolve()
      = tmp_path/Current/index.html
    is_relative_to(Path(tmp_path/Current)) → True
    Expected: 200"""
    repo = make_repo(tmp_path, "Current")
    (repo / "index.html").write_text("<h1>hello</h1>", encoding="utf-8")
    server, get = start_server([repo])
    try:
        # Expected: 200
        status, body = get("/try/Current/index.html")
        assert status == 200
        # Expected: body is the file content
        assert body == b"<h1>hello</h1>"
    finally:
        server.shutdown()
        server.server_close()


# ─── 3. escape to parent refused ──────────────────────────────────────────────

def test_parent_escape_is_refused(tmp_path):
    """Escape to parent: tmp_path/secret.txt is outside the repo.
    subpath "../secret.txt": (Current / "../secret.txt").resolve()
      = tmp_path/secret.txt
    str prefix: str(tmp_path/secret.txt).startswith(str(tmp_path/Current))
      → False
    is_relative_to(Path(tmp_path/secret.txt)).is_relative_to(
      Path(tmp_path/Current)) → False
    Expected: 404 (both old and new refuse this)"""
    repo = make_repo(tmp_path, "Current")
    (tmp_path / "secret.txt").write_text("no", encoding="utf-8")
    server, get = start_server([repo])
    try:
        # Expected: 404
        status, body = get("/try/Current/../secret.txt")
        assert status == 404
        # Expected: body is empty
        assert body == b""
    finally:
        server.shutdown()
        server.server_close()


# ─── 4. nested file inside repo ───────────────────────────────────────────────

def test_nested_inside_repo_is_served(tmp_path):
    """A file in a nested subfolder inside the repo passes is_relative_to.
    subpath "a/b/file.html": resolves to tmp_path/Current/a/b/file.html
    is_relative_to(Path(tmp_path/Current)) → True
    Expected: 200"""
    repo = make_repo(tmp_path, "Current")
    (repo / "a" / "b").mkdir(parents=True)
    (repo / "a" / "b" / "file.html").write_text("<h1>nested</h1>",
                                                encoding="utf-8")
    server, get = start_server([repo])
    try:
        # Expected: 200
        status, body = get("/try/Current/a/b/file.html")
        assert status == 200
        # Expected: body is the nested file content
        assert body == b"<h1>nested</h1>"
    finally:
        server.shutdown()
        server.server_close()


# ─── 5. file at the repo root ─────────────────────────────────────────────────

def test_repo_root_file_is_served(tmp_path):
    """A file at the repo root itself is inside the repo.
    subpath "page.html": resolves to tmp_path/Current/page.html
    is_relative_to(Path(tmp_path/Current)) → True
    Expected: 200"""
    repo = make_repo(tmp_path, "Current")
    (repo / "page.html").write_text("hi", encoding="utf-8")
    server, get = start_server([repo])
    try:
        # Expected: 200
        status, body = get("/try/Current/page.html")
        assert status == 200
        # Expected: body is "hi"
        assert body == b"hi"
    finally:
        server.shutdown()
        server.server_close()


# ─── 6. sibling with longer prefix (Ab vs Abc) ────────────────────────────────

def test_sibling_longer_prefix_refused(tmp_path):
    """Repo "Ab", sibling "Abc". str prefix: "Abc" starts with "Ab" → True.
    is_relative_to: Path(tmp_path/Abc/file.html).is_relative_to(
      Path(tmp_path/Ab)) → False
    subpath "../Abc/file.html" resolves to tmp_path/Abc/file.html
    Expected: 404"""
    repo = make_repo(tmp_path, "Ab")
    sibling = make_repo(tmp_path, "Abc")
    (sibling / "file.html").write_text("nope", encoding="utf-8")
    server, get = start_server([repo, sibling])
    try:
        # Expected: 404 — Abc is NOT inside Ab
        status, body = get("/try/Ab/../Abc/file.html")
        assert status == 404
        # Expected: body is empty
        assert body == b""
    finally:
        server.shutdown()
        server.server_close()


# ─── 7. two siblings both refused ─────────────────────────────────────────────

def test_two_siblings_both_refused(tmp_path):
    """Repo "Current", siblings "Current2" and "Current3". Both start with
    "Current" as string prefix, neither is inside Current.
    Expected: both 404"""
    repo = make_repo(tmp_path, "Current")
    s2 = make_repo(tmp_path, "Current2")
    s3 = make_repo(tmp_path, "Current3")
    (s2 / "f.html").write_text("a", encoding="utf-8")
    (s3 / "f.html").write_text("b", encoding="utf-8")
    server, get = start_server([repo, s2, s3])
    try:
        # Expected: Current2 → 404
        status2, body2 = get("/try/Current/../Current2/f.html")
        assert status2 == 404
        # Expected: Current3 → 404
        status3, body3 = get("/try/Current/../Current3/f.html")
        assert status3 == 404
        # Expected: both bodies empty
        assert body2 == b""
        assert body3 == b""
    finally:
        server.shutdown()
        server.server_close()


# ─── 8. sibling that does NOT start with repo name ────────────────────────────

def test_sibling_not_starting_with_repo_name_refused(tmp_path):
    """Repo "Current", sibling "Other". "Other" does not start with "Current",
    so neither check accepts it.
    Expected: 404"""
    repo = make_repo(tmp_path, "Current")
    sibling = make_repo(tmp_path, "Other")
    (sibling / "file.html").write_text("nope", encoding="utf-8")
    server, get = start_server([repo, sibling])
    try:
        # Expected: 404
        status, body = get("/try/Current/../Other/file.html")
        assert status == 404
        # Expected: body is empty
        assert body == b""
    finally:
        server.shutdown()
        server.server_close()


# ─── 9. is_relative_to is the method used ─────────────────────────────────────

def test_is_relative_to_is_used(tmp_path, monkeypatch):
    """The handler must call Path.is_relative_to, not str.startswith.
    Spy records every is_relative_to call (self, argument).
    subpath "../Current2/index.html":
      file = (Current / "../Current2/index.html").resolve()
           = Path(tmp_path/Current2/index.html)
      repo_resolved = Path(tmp_path/Current)
      spy records (file, repo_resolved)
    is_relative_to → False → 404
    Expected: is_relative_to called, self=Current2/index.html,
              other=Current"""
    repo = make_repo(tmp_path, "Current")
    sibling = make_repo(tmp_path, "Current2")
    (sibling / "index.html").write_text("x", encoding="utf-8")

    calls = []
    original = Path.is_relative_to

    def spy(self, other):
        calls.append((self, Path(other)))
        return original(self, other)

    monkeypatch.setattr(Path, "is_relative_to", spy)

    server, get = start_server([repo, sibling])
    try:
        get("/try/Current/../Current2/index.html")
        # Expected: at least one is_relative_to call
        assert len(calls) >= 1
        # Expected: first call checks tmp_path/Current2/index.html against
        #           tmp_path/Current
        # Expected: calls[0][0] == Path(tmp_path / "Current2" / "index.html")
        assert calls[0][0] == Path(tmp_path / "Current2" / "index.html")
        # Expected: calls[0][1] == Path(tmp_path / "Current")
        assert calls[0][1] == Path(tmp_path / "Current")
    finally:
        server.shutdown()
        server.server_close()


# ─── 10. symlinked repo resolves to the real folder ───────────────────────────

def test_symlink_repo_resolved(tmp_path):
    """A repo listed as a symlink: the handler uses the resolved folder for
    is_relative_to, so a file inside the real folder is served.
    repo = Path(Link); repo.resolve() = Path(Current)
    file = (Link / "index.html").resolve() = Path(Current/index.html)
    is_relative_to(Path(Current)) → True
    Expected: 200"""
    real = make_repo(tmp_path, "Current")
    (real / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
    # Create a symlink Link → Current
    link = tmp_path / "Link"
    link.symlink_to(real)
    # The handler matches Path(link).name == "Link"
    server, get = start_server([link])
    try:
        # Expected: 200 — Link/index.html resolves inside Current
        status, body = get("/try/Link/index.html")
        assert status == 200
        # Expected: body is the content
        assert body == b"<h1>ok</h1>"
    finally:
        server.shutdown()
        server.server_close()


# ─── 11. non-static repo refused before path check ────────────────────────────

def test_non_static_repo_refused(tmp_path):
    """A cli repo: the kind check refuses before any path check.
    cfg.get("kind") != "static" → 404
    Expected: 404"""
    cli_toml = ('[try]\nkind = "cli"\n'
                'command = ["python", "-m", "echoer", "{file}"]\n')
    repo = make_repo(tmp_path, "Current", toml=cli_toml)
    (repo / "index.html").write_text("x", encoding="utf-8")
    server, get = start_server([repo])
    try:
        # Expected: 404 — not static
        status, body = get("/try/Current/index.html")
        assert status == 404
        # Expected: body is empty
        assert body == b""
    finally:
        server.shutdown()
        server.server_close()


# ─── 12. file inside repo that does not exist ─────────────────────────────────

def test_missing_file_inside_repo_is_refused(tmp_path):
    """A path inside the repo, but no such file on disk.
    is_relative_to → True; file.is_file() → False → 404
    Expected: 404"""
    repo = make_repo(tmp_path, "Current")
    server, get = start_server([repo])
    try:
        # Expected: 404
        status, body = get("/try/Current/missing.html")
        assert status == 404
        # Expected: body is empty
        assert body == b""
    finally:
        server.shutdown()
        server.server_close()
