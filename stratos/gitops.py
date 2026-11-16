"""Git helpers. Each task runs in its own worktree on branch stratos/<task id>, never in the running copy;
merging a finished task back is a person's decision."""
import subprocess
from pathlib import Path

BOT = ["-c", "user.name=Stratos", "-c", "user.email=stratos@localhost"]


class BaseConflict(Exception):
    """A merge of dependency branches conflicted."""


UTF8 = {"text": True, "encoding": "utf-8", "errors": "replace"}   # git prints UTF-8; Windows' default codepage is not


def git(cwd, *args, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, **UTF8)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def ensure_worktree(repo, root, task_id, bases=None):
    path = Path(root) / task_id
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    bases = bases or []
    start = bases[0] if bases else "HEAD"
    git(repo, "worktree", "add", "-b", f"stratos/{task_id}", str(path), start)
    for base in bases[1:]:
        r = subprocess.run(["git", *BOT, "merge", "--no-edit", base], cwd=path, capture_output=True, **UTF8)
        if r.returncode != 0:
            subprocess.run(["git", "merge", "--abort"], cwd=path, capture_output=True, check=False)
            remove_worktree(repo, root, task_id)
            raise BaseConflict(f"merging {base} into stratos/{task_id} conflicted")
    return path


def dependency_bases(repo, task_ids):
    return [f"stratos/{tid}" for tid in task_ids if git(repo, "branch", "--list", f"stratos/{tid}")]


def remove_worktree(repo, root, task_id, delete_branch=True):
    """Remove a task's worktree (root/<task_id>) and prune git's worktree list; unless delete_branch is
    False, also delete the branch stratos/<task_id>. A task with no worktree or branch does nothing."""
    path = Path(root) / task_id
    if path.exists():
        git(repo, "worktree", "remove", "--force", str(path))
    git(repo, "worktree", "prune", "-v")
    if delete_branch:
        branch = f"stratos/{task_id}"
        if git(repo, "branch", "--list", branch):
            git(repo, "branch", "-D", branch)


def diff(worktree):
    """Everything the attempt changed, new files included (stages it; discard_changes undoes that too)."""
    git(worktree, "add", "-A")
    return git(worktree, "diff", "--cached", "--no-color", "HEAD")


def commit_diff(worktree):
    """The changes of the last commit (a candidate waiting for review)."""
    return git(worktree, "diff", "--no-color", "HEAD~1", "HEAD")


def append_to_commit_message(worktree, text):
    """Add text to the last commit's message (the review, which comes after the candidate commit)."""
    msg = git(worktree, "log", "-1", "--format=%B")
    git(worktree, *BOT, "commit", "-q", "--amend", "-m", f"{msg}\n\n{text}")


def undo_last_commit(worktree):
    """Drop the last commit and its changes (a candidate the review rejected)."""
    git(worktree, "reset", "-q", "--hard", "HEAD~1")
    git(worktree, "clean", "-fd")


def discard_changes(worktree):
    """Undo a failed attempt (only ever inside a Stratos worktree)."""
    git(worktree, "reset", "-q", "--hard", "HEAD")
    git(worktree, "clean", "-fd")


def commit_all(worktree, message):
    git(worktree, "add", "-A")
    git(worktree, *BOT, "commit", "-m", message)
    return git(worktree, "rev-parse", "--short", "HEAD")
