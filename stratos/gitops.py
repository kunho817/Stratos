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
    # the other bases, and HEAD too: commits made on main after a dependency's branch (a test fix) must reach the
    # copy (T083, 2026-11-19)
    head = git(repo, "rev-parse", "HEAD") if bases else None
    for base in bases[1:] + ([head] if head else []):
        r = subprocess.run(["git", *BOT, "merge", "--no-edit", base], cwd=path, capture_output=True, **UTF8)
        if r.returncode != 0:
            subprocess.run(["git", "merge", "--abort"], cwd=path, capture_output=True, check=False)
            remove_worktree(repo, root, task_id)
            raise BaseConflict(f"merging {base} into stratos/{task_id} conflicted")
    return path


def dependency_bases(repo, task_ids):
    """The branches a dependent task starts from: its dependencies' branches that exist and are not already in HEAD
    (a merged dependency is in main, and starting from its branch would miss what main got since, T076)."""
    out = []
    for tid in task_ids:
        branch = f"stratos/{tid}"
        if not git(repo, "branch", "--list", branch):
            continue
        merged = subprocess.run(["git", "merge-base", "--is-ancestor", branch, "HEAD"], cwd=repo,
                                capture_output=True).returncode == 0
        if not merged:
            out.append(branch)
    return out


def remove_worktree(repo, root, task_id, delete_branch=True):
    """Remove a task's worktree (root/<task_id>) and prune git's worktree list; unless delete_branch is
    False, also delete the branch stratos/<task_id>. A task with no worktree or branch does nothing."""
    path = Path(root) / task_id
    if path.exists():
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()   # an earlier remove was cut short (Windows held the folder): git already let go of it
        else:
            try:
                git(repo, "worktree", "remove", "--force", str(path))
            except RuntimeError:
                # (Claude, 2026-11-21) a shell with its cwd in the folder: git emptied it and let go of it but
                # cannot delete the folder itself - the empty folder is as good as gone (worktree add takes it)
                if path.is_dir() and not any(path.iterdir()):
                    pass
                else:
                    raise
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


def finalize_commit_message(worktree, text):
    """Clean a candidate commit's title and append the review (approving the candidate)."""
    msg = git(worktree, "log", "-1", "--format=%B")
    lines = msg.split("\n")
    title = lines[0]
    ending = " (candidate, awaiting review)"
    if title.endswith(ending):
        title = title[: -len(ending)]
    rest = "\n".join(lines[1:]).strip("\n")
    body = f"{title}\n\n{rest}" if rest else title
    git(worktree, *BOT, "commit", "-q", "--amend", "-m", f"{body}\n\n{text}")


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


def changed_since(repo, paths, since):
    """Return the paths (in given order, ::... suffixes cut off, each path once) whose last commit in
    repo is later than since (a time.time() float). Paths with no commit are left out."""
    seen = set()
    out = []
    for path in paths:
        base = path.split("::")[0]
        if base in seen:
            continue
        seen.add(base)
        r = git(repo, "log", "-1", "--format=%ct", "--", base, check=False)
        if r and int(r) > since:
            out.append(base)
    return out

