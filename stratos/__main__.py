"""Command line:

  python -m stratos add --title T --goal G --files a.py,b.py --protected tests/test_x.py --tests tests/test_x.py
  python -m stratos run T001
  python -m stratos status
"""
import argparse
import sys

from . import config
from .gateway import Gateway
from .loop import run_task
from .state import Store
from .telemetry import Telemetry


def split(s):
    return [x for x in (s or "").split(",") if x]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="stratos")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="add a task")
    a.add_argument("--title", required=True)
    a.add_argument("--goal", required=True)
    a.add_argument("--files", default="")
    a.add_argument("--protected", default="")
    a.add_argument("--tests", required=True)
    r = sub.add_parser("run", help="run a task")
    r.add_argument("task_id")
    sub.add_parser("status", help="list tasks")
    args = ap.parse_args(argv)

    store = Store(config.STATE_DIR)
    if args.cmd == "add":
        t = store.add_task(args.title, args.goal, split(args.files), split(args.protected), split(args.tests))
        print(f"added {t['id']}: {t['title']}")
    elif args.cmd == "run":
        tel = Telemetry(config.STATE_DIR / "telemetry.jsonl")
        print(f"running {args.task_id}")
        result = run_task(store, Gateway(tel), args.task_id)
        print(f"{args.task_id}: {result}")
        return 0 if result == "done" else 1
    else:
        for t in store.tasks():
            extra = f" commit {t['commit']}" if t.get("commit") else ""
            print(f"{t['id']}  {t['status']:<12} {t['title']}{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
