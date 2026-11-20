"""tee: copy stdout/stderr into a log file for long commands."""
import contextlib
import sys
import time
from pathlib import Path

LOGGED = {"run", "run-all", "plan", "plan-tests", "plan-add", "plan-critique", "review", "memory", "push"}


class _Writer:
    def __init__(self, old, log_file):
        self._old = old
        self._log = log_file

    def write(self, text):
        self._old.write(text)
        self._log.write(text)
        self._log.flush()

    def flush(self):
        self._old.flush()

    def __getattr__(self, name):
        return getattr(self._old, name)


@contextlib.contextmanager
def tee(path, argv):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > 4000:
            lines = lines[-2000:]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    f = path.open("a", encoding="utf-8")
    header = f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} stratos {' '.join(argv)}\n"
    f.write(header)
    f.flush()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = _Writer(old_stdout, f)
    sys.stderr = _Writer(old_stderr, f)
    try:
        yield
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        f.close()
