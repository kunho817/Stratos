"""Git helpers. Each task runs in its own worktree on branch stratos/<task id>, never in the running copy;
merging a finished task back is a person's decision."""
import subprocess
from pathlib import Path

BOT = ["-c", "user.name=Stratos", "-c", "user.email=stratos@localhost"]


def git(cwd, *args, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def ensure_worktree(repo, root, task_id):
    path = Path(root) / task_id
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    git(repo, "worktree", "add", "-b", f"stratos/{task_id}", str(path), "HEAD")
    return path


def discard_changes(worktree):
    """Undo a failed attempt (only ever inside a Stratos worktree)."""
    git(worktree, "checkout", "--", ".")
    git(worktree, "clean", "-fd")


def commit_all(worktree, message):
    git(worktree, "add", "-A")
    git(worktree, *BOT, "commit", "-m", message)
    return git(worktree, "rev-parse", "--short", "HEAD")
