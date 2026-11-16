"""Command line:

  python -m stratos add --title T --goal G --files a.py,b.py --protected tests/test_x.py --tests tests/test_x.py
  python -m stratos run T001
  python -m stratos run-all
  python -m stratos status
"""
import argparse
import sys

from . import config
from .gateway import Gateway
from .loop import run_task
from .report import summarize
from .scheduler import plan as scheduler_plan
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
    a.add_argument("--role", choices=sorted(config.ROLES), default="coder", help="which model plays this task")
    a.add_argument("--after", default="", help="comma-separated task ids that must be done first")
    r = sub.add_parser("run", help="run a task")
    r.add_argument("task_id")
    sub.add_parser("run-all", help="run every todo task, in scheduler order")
    sub.add_parser("status", help="list tasks")
    sub.add_parser("report", help="summarize telemetry")
    args = ap.parse_args(argv)

    store = Store(config.STATE_DIR)
    if args.cmd == "add":
        t = store.add_task(args.title, args.goal, split(args.files), split(args.protected), split(args.tests),
                           role=args.role, after=split(args.after))
        print(f"added {t['id']}: {t['title']}")
    elif args.cmd == "run":
        tel = Telemetry(config.STATE_DIR / "telemetry.jsonl")
        print(f"running {args.task_id}")
        result = run_task(store, Gateway(tel), args.task_id)
        print(f"{args.task_id}: {result}")
        return 0 if result == "done" else 1
    elif args.cmd == "run-all":
        tel = Telemetry(config.STATE_DIR / "telemetry.jsonl")
        gw = Gateway(tel)
        try:
            current = gw.health().get("model")
        except Exception:
            current = None
        order, blocked = scheduler_plan(store.tasks(), config.ROLES, current)
        if not order and not blocked:
            print("nothing to run")
            return 0
        print("plan: " + " ".join(order))
        if blocked:
            print("blocked: " + " ".join(blocked))
        done = True
        for tid in order:
            task = store.get(tid)
            dep = next((a for a in task.get("after", [])
                        if store.get(a)["status"] != "done" if store.get(a)["status"] != "todo"
                        or store.get(a)["status"] != "done"), None)
            if dep is not None:
                print(f"skipped {tid} (waits on {dep})")
                done = False
                continue
            result = run_task(store, gw, tid)
            print(f"{tid}: {result}")
            if result != "done":
                done = False
        return 0 if done and not blocked else 1
    elif args.cmd == "report":
        events = Telemetry(config.STATE_DIR / "telemetry.jsonl").load()
        if not events:
            print("no telemetry yet")
        else:
            s = summarize(events)
            print(f"calls: {s['calls']}  prompt tokens: {s['prompt_tokens']}  completion tokens: {s['completion_tokens']}")
            print(f"switches: {s['switches']}  switch time: {s['switch_seconds']:.1f} s")
            outcomes = " ".join(f"{k}={s['outcomes'][k]}" for k in sorted(s['outcomes']))
            print(f"outcomes: {outcomes}")
            print(f"wasted tokens: {s['wasted_tokens']}")
            print("by model:")
            for name in sorted(s['by_model']):
                m = s['by_model'][name]
                print(f"  {name}: calls={m['calls']} prompt={m['prompt_tokens']} completion={m['completion_tokens']} time={m['seconds']:.1f} s")
        return 0
    else:
        for t in store.tasks():
            extra = f" commit {t['commit']}" if t.get("commit") else ""
            print(f"{t['id']}  {t['status']:<12} {t['title']}{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
