"""Command line:

  python -m stratos add --title T --goal G --files a.py,b.py --protected tests/test_x.py --tests tests/test_x.py
  python -m stratos add --title T --goal-file PATH --files a.py,b.py --protected tests/test_x.py --tests tests/test_x.py
  python -m stratos run T001
  python -m stratos run-all
  python -m stratos status
  python -m stratos clean
  python -m stratos reset T001 --reason R
"""
import argparse
import subprocess
import sys

from . import config
from . import decide
from . import gitops
from . import jev
from .gateway import Gateway
from .loop import run_all, run_task
from .report import decision_accuracy, escalation_accuracy, summarize
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
    g = a.add_mutually_exclusive_group(required=True)
    g.add_argument("--goal", help="the task goal")
    g.add_argument("--goal-file", help="path to a file containing the task goal")
    a.add_argument("--files", default="")
    a.add_argument("--protected", default="")
    a.add_argument("--tests", required=True)
    a.add_argument("--role", choices=sorted(config.ROLES), default=None, help="which model plays this task")
    a.add_argument("--after", default="", help="comma-separated task ids that must be done first")
    r = sub.add_parser("run", help="run a task")
    r.add_argument("task_id")
    sub.add_parser("run-all", help="run every todo task, in scheduler order")
    sub.add_parser("status", help="list tasks")
    sub.add_parser("report", help="summarize telemetry")
    sub.add_parser("clean", help="remove worktree and branch of merged, done tasks")
    reset = sub.add_parser("reset", help="throw away a task's result so it runs again")
    reset.add_argument("task_id")
    reset.add_argument("--reason", required=True, help="why the task is being reset")
    args = ap.parse_args(argv)

    store = Store(config.STATE_DIR)
    if args.cmd == "add":
        if args.goal_file is not None:
            try:
                goal = open(args.goal_file, encoding="utf-8").read()
            except OSError as e:
                a.error(f"cannot read goal file {args.goal_file!r}: {e}")
        else:
            goal = args.goal
        if args.role is None:
            d = decide.choose_role({'files': split(args.files), 'goal': goal})
            role = d['choice']
        else:
            d = None
            role = args.role
        t = store.add_task(args.title, goal, split(args.files), split(args.protected), split(args.tests),
                           role=role, after=split(args.after))
        if d is not None:
            store.update(t['id'], role_decision=d)
            Telemetry(config.STATE_DIR / 'telemetry.jsonl').record('decision', decision='role', decider='rules',
                                                                   task=t['id'], choice=d['choice'],
                                                                   confidence=d['confidence'], reason=d['reason'])
            print(f"role: {d['choice']} ({d['reason']})")
        if config.JEV_SHADOW:
            j = jev.choose_role({'files': split(args.files), 'goal': goal})
            if j is None:
                choice = confidence = None
                reason = "jev unavailable"
                input_tokens = 0
            else:
                choice = j['choice']
                confidence = j['confidence']
                reason = j['reason']
                input_tokens = j['input_tokens']
            Telemetry(config.STATE_DIR / 'telemetry.jsonl').record('decision', decision='role', decider='jev',
                                                                   task=t['id'], choice=choice, confidence=confidence,
                                                                   reason=reason, input_tokens=input_tokens)
            if j is None:
                print("jev: unavailable")
            else:
                print(f"jev: {j['choice']} {j['confidence']} (shadow)")
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
        statuses = run_all(store, gw, order)
        done = True
        for tid in order:
            task = store.get(tid)
            status = statuses.get(tid, task["status"])
            if status == "todo":
                dep = next((x for x in task.get("after", []) if store.get(x)["status"] != "done"), None)
                if dep is not None:
                    print(f"skipped {tid} (waits on {dep})")
                    done = False
                    continue
            print(f"{tid}: {status}")
            if status != "done":
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
            acc = decision_accuracy(events)
            if acc:
                print("role decisions:")
                for name in sorted(acc):
                    d = acc[name]
                    print(f"  {name}: {d['correct']}/{d['judged']} right ({d['decisions']} decided; confidence >= 0.3: {d['confident_correct']}/{d['confident_judged']})")
            esc = escalation_accuracy(events)
            if esc:
                print("escalation decisions:")
                for name in sorted(esc):
                    d = esc[name]
                    print(f"  {name}: {d['correct']}/{d['judged']} right ({d['decisions']} decided; confidence >= 0.7: {d['confident_correct']}/{d['confident_judged']})")
        return 0
    elif args.cmd == "clean":
        merged = gitops.git(config.REPO, "branch", "--merged", "HEAD", "--list", "stratos/*")
        merged = {line.lstrip(" *+").strip() for line in merged.splitlines()}
        all_branches = gitops.git(config.REPO, "branch", "--list", "stratos/*")
        all_branches = {line.lstrip(" *+").strip() for line in all_branches.splitlines()}
        cleaned = 0
        for t in store.tasks():
            if t["status"] != "done":
                continue
            branch = f"stratos/{t['id']}"
            if branch not in all_branches:
                continue
            if branch in merged:
                gitops.remove_worktree(config.REPO, config.WORKTREES, t["id"])
                store.update(t["id"], cleaned=True, worktree=None)
                print(f"cleaned {t['id']}")
                cleaned += 1
            else:
                print(f"kept {t['id']} (not merged)")
        print(f"cleaned {cleaned} task(s)")
        return 0
    elif args.cmd == "reset":
        try:
            task = store.get(args.task_id)
        except KeyError:
            print(f"no task {args.task_id}", file=sys.stderr)
            return 1
        commit = task.get("commit")
        if commit and subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"],
                                     cwd=config.REPO, capture_output=True).returncode == 0:
            print(f"{args.task_id} is merged; reset would not take it out of HEAD", file=sys.stderr)
            return 1
        gitops.remove_worktree(config.REPO, config.WORKTREES, args.task_id)
        store.update(args.task_id, status="todo", worktree=None, commit=None)
        store.decide(task=args.task_id, result="reset_by_human", reason=args.reason)
        Telemetry(config.STATE_DIR / "telemetry.jsonl").record("verdict", task=args.task_id,
                                                               result="reset_by_human", reason=args.reason)
        print(f"reset {args.task_id}")
        return 0
    else:
        for t in store.tasks():
            extra = f" commit {t['commit']}" if t.get("commit") else ""
            wt = t.get("worktree")
            mark = "  [wt]" if wt and (config.WORKTREES / wt).exists() else ""
            print(f"{t['id']}  {t['status']:<12} {t['title']}{extra}{mark}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
