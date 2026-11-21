import re
from pathlib import Path

from stratos import decide
from stratos.gitops import git

SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9_-]{20,}",
    r"ghp_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]",
]

_compiled = [re.compile(p) for p in SECRET_PATTERNS]

SECRET_FILES = {".env", "credentials.json", "settings.local.json", "id_rsa"}


def _is_secret_file(name):
    if name in SECRET_FILES:
        return True
    if name.endswith(".pem") or name.endswith(".key"):
        return True
    return False


def secret_hits(diff):
    hits = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
            name = path.rsplit("/", 1)[-1]
            if _is_secret_file(name):
                hits.append(f"file: {path}")
        elif line.startswith("+") and not line.startswith("+++"):
            content = line[1:]
            if "pragma: allowlist secret" in content:
                continue
            for pat in _compiled:
                if pat.search(content):
                    hits.append(f"line: {content.strip()[:80]}")
                    break
    return hits


def all_tests(root, settings):
    test_dir = Path(root) / settings["test_dir"]
    suffixes = settings["test_suffixes"]
    results = []
    for p in test_dir.rglob("*"):
        if p.is_file():
            name = p.name
            for suf in suffixes:
                if name.endswith(suf):
                    if suf == ".py" and not name.startswith("test_"):
                        continue
                    results.append(p.relative_to(root).as_posix())
                    break
    results.sort()
    return results


def check(repo, run_tests):
    messages = []

    remote_url = git(repo, "remote", "get-url", "origin", check=False)
    if not remote_url:
        return (False, ["no remote 'origin'"], {"skip": True})

    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if branch not in ("main", "master"):
        messages.append(f"on branch {branch}, not main")

    status = git(repo, "status", "--porcelain", "--untracked-files=no")
    if status:
        messages.append("uncommitted changes")

    base = f"origin/{branch}"
    verify_out = git(repo, "rev-parse", "--verify", "--quiet", base, check=False)
    if not verify_out:
        base = None

    if base:
        ahead = int(git(repo, "rev-list", "--count", f"{base}..HEAD"))
    else:
        ahead = int(git(repo, "rev-list", "--count", "HEAD"))

    info = {"branch": branch, "ahead": ahead, "skip": False}

    if ahead == 0:
        return (True, ["nothing to push"], info)

    if base:
        diff_output = git(repo, "diff", f"{base}..HEAD")
    else:
        diff_output = git(repo, "log", "-p", "--format=", "HEAD")

    for hit in secret_hits(diff_output):
        messages.append(f"secret? {hit}")

    passed, output = run_tests()
    if not passed:
        # (Claude, 2026-11-21) name what failed: a refusal that said only "tests failed" never came back
        failed = decide._extract_ids(output or "")[:5]
        messages.append("tests failed: " + ", ".join(failed) if failed else "tests failed")

    ok = len(messages) == 0
    return (ok, messages, info)


def push(repo, telemetry, run_tests, dry_run=False, log=print):
    ok, msgs, info = check(repo, run_tests)

    if info.get("skip"):
        log("push: no remote, skipped")
        return 0

    if not ok:
        for m in msgs:
            log(f"push: {m}")
        log("push: refused")
        return 1

    ahead = info["ahead"]
    branch = info["branch"]

    if ahead == 0:
        log("push: nothing to push")
        return 0

    if dry_run:
        log(f"push: would push {ahead} commits to origin/{branch}")
        return 0

    try:
        git(repo, "push", "origin", branch)
    except RuntimeError as e:
        log(f"push: {e}")
        return 1

    telemetry.record("push", branch=branch, commits=ahead)
    log(f"push: pushed {ahead} commits to origin/{branch}")
    return 0
