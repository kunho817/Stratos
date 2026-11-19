"""Command line:

  python -m stratos add --title T --goal G --files a.py,b.py --protected tests/test_x.py --tests tests/test_x.py
  python -m stratos add --title T --goal-file PATH --files a.py,b.py --protected tests/test_x.py --tests tests/test_x.py
  python -m stratos plan --goal-file PATH [--tries N]
  python -m stratos plan-add PLAN_ID
  python -m stratos plan-tests PLAN_ID
  python -m stratos run T001
  python -m stratos run-all
  python -m stratos status
  python -m stratos report --plans
  python -m stratos clean
  python -m stratos reset T001 --reason R
  python -m stratos replay T001 T002 --role coder --model M --effort E --max-tokens N --tries K
  python -m stratos memory index [--no-vectors]
  python -m stratos memory search QUERY [-k N] [--no-vectors]
  python -m stratos memory learn
"""
import argparse
import json
import subprocess
import sys

from . import codemap
from . import config
from . import decide
from . import embed
from . import gitops
from . import jev
from . import learn
from . import memindex
from . import memsearch
from . import memstore
from . import plan as plan_mod
from . import plantests
from . import recall
from . import replay
from .gateway import Gateway
from .loop import run_all, run_task
from .report import decision_accuracy, diagnosis_ab, escalation_accuracy, plans_summary, replay_summary, summarize
from .scheduler import plan as scheduler_plan
from .state import Store
from .telemetry import Telemetry


def split(s):
    return [x for x in (s or "").split(",") if x]


def refresh_memory():
    if not config.MEMORY:
        return
    try:
        c = memindex.refresh(config.REPO, config.STATE_DIR, embed.Embedder())
        print(f"memory: {c['changed']} changed, {c['embedded']} embedded")
    except Exception as e:
        print(f"memory: {e}", file=sys.stderr)


def add_one(store, title, goal, files, protected, tests, role, after):
    if role is None:
        d = decide.choose_role({'files': files, 'goal': goal})
        role = d['choice']
    else:
        d = None
    t = store.add_task(title, goal, files, protected, tests, role=role, after=after)
    if d is not None:
        store.update(t['id'], role_decision=d)
        Telemetry(config.STATE_DIR / 'telemetry.jsonl').record('decision', decision='role', decider='rules',
                                                               task=t['id'], choice=d['choice'],
                                                               confidence=d['confidence'], reason=d['reason'])
        print(f"role: {d['choice']} ({d['reason']})")
    if config.JEV_SHADOW:
        j = jev.choose_role({'files': files, 'goal': goal})
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
    return t


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
    plan_p = sub.add_parser("plan", help="split a feature goal into tasks")
    plan_p.add_argument("--goal-file", required=True, help="path to a file containing the feature goal")
    plan_p.add_argument("--tries", type=int, default=2, help="attempts to get a valid plan")
    plan_add_p = sub.add_parser("plan-add", help="add a saved plan as tasks")
    plan_add_p.add_argument("plan_id")
    plan_tests_p = sub.add_parser("plan-tests", help="draft the test files of every task in a plan")
    plan_tests_p.add_argument("plan_id")
    r = sub.add_parser("run", help="run a task")
    r.add_argument("task_id")
    sub.add_parser("run-all", help="run every todo task, in scheduler order")
    sub.add_parser("status", help="list tasks")
    report_p = sub.add_parser("report", help="summarize telemetry")
    report_p.add_argument("--replay", action="store_true", help="summarize the replay runs instead")
    report_p.add_argument("--plans", action="store_true", help="summarize plan files and their test drafts")
    sub.add_parser("clean", help="remove worktree and branch of merged, done tasks")
    reset = sub.add_parser("reset", help="throw away a task's result so it runs again")
    reset.add_argument("task_id")
    reset.add_argument("--reason", required=True, help="why the task is being reset")
    replay_p = sub.add_parser("replay", help="try a model on past tasks; nothing is committed")
    replay_p.add_argument("task_ids", nargs="+")
    replay_p.add_argument("--role", choices=sorted(config.ROLES), default="coder",
                          help="which model plays these tasks")
    replay_p.add_argument("--model", default=None, help="override the role's model")
    replay_p.add_argument("--effort", default=None, help="override the role's effort")
    replay_p.add_argument("--max-tokens", type=int, default=None, help="override the role's max_tokens")
    replay_p.add_argument("--tries", type=int, default=2, help="attempts per task")
    replay_p.add_argument("--reasoning-budget", type=int, default=None, help="override the role's reasoning budget")

    memory_p = sub.add_parser("memory", help="index and search the code memory")
    memory_sub = memory_p.add_subparsers(dest="memory_cmd", required=True)
    memory_index_p = memory_sub.add_parser("index", help="index the project into the memory store")
    memory_index_p.add_argument("--no-vectors", action="store_true", help="skip embedding")
    memory_search_p = memory_sub.add_parser("search", help="search the memory store")
    memory_search_p.add_argument("query")
    memory_search_p.add_argument("-k", "--k", type=int, default=10, help="number of results")
    memory_search_p.add_argument("--no-vectors", action="store_true", help="skip vector search")
    memory_sub.add_parser("learn", help="learn lessons from people's corrections")

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
        role = args.role
        add_one(store, args.title, goal, split(args.files), split(args.protected), split(args.tests),
                role, split(args.after))
    elif args.cmd == "plan":
        try:
            goal = open(args.goal_file, encoding="utf-8").read()
        except OSError as e:
            plan_p.error(f"cannot read goal file {args.goal_file}: {e}")
        refresh_memory()
        tel = Telemetry(config.STATE_DIR / "telemetry.jsonl")
        gw = Gateway(tel)
        planner = config.PLANNER
        conv_path = config.REPO / "CONVENTIONS.md"
        conventions = conv_path.read_text(encoding="utf-8") if conv_path.exists() else None
        converter = config.PLAN_CONVERTER
        as_text = config.PLAN_AS_TEXT
        answers_dir = config.STATE_DIR / "answers"
        answers_dir.mkdir(parents=True, exist_ok=True)

        cmap = codemap.build(config.REPO)
        uses = codemap.uses_summary(cmap)

        memory = None
        if config.MEMORY and (config.STATE_DIR / "memory.db").exists():
            try:
                store2 = memstore.Store(config.STATE_DIR / "memory.db")
                try:
                    memory = recall.pack(store2, goal, embed.Embedder(), cmap)
                finally:
                    store2.close()
            except Exception as e:
                print(f"memory: {e}", file=sys.stderr)
                memory = None

        system = plan_mod.TEXT_SYSTEM if as_text else None
        messages = plan_mod.build_messages(goal, plan_mod.repo_summary(config.REPO),
                                           conventions=conventions, system=system, uses=uses, memory=memory)
        last_reason = None
        for attempt in range(1, args.tries + 1):
            gw.ensure_model(planner["model"])
            kw = dict(task="plan", role="planner", attempt=attempt,
                      model=planner["model"], effort=planner["effort"],
                      max_tokens=planner["max_tokens"])
            budget = planner.get("reasoning_budget")
            if budget is not None:
                kw["reasoning_budget"] = budget
            call_id, text = gw.chat(messages, **kw)
            (answers_dir / f"plan-{call_id}.md").write_text(text, encoding="utf-8")

            parse_ok = False
            parse_via = None
            parse_error = None
            tasks = None

            if as_text:
                try:
                    tasks = plan_mod.parse_text_plan(text)
                    parse_ok = True
                    parse_via = "text"
                except plan_mod.PlanFormatError as e:
                    if converter is not None:
                        gw.ensure_model(converter["model"])
                        conv_kw = dict(task="plan", role="plan_converter", attempt=attempt,
                                       model=converter["model"], effort=converter["effort"],
                                       max_tokens=converter["max_tokens"])
                        conv_call_id, conv_text = gw.chat(plan_mod.convert_messages(text), **conv_kw)
                        (answers_dir / f"plan-{conv_call_id}.md").write_text(conv_text, encoding="utf-8")
                        try:
                            tasks = plan_mod.parse_plan(conv_text)
                            parse_ok = True
                            parse_via = "converter"
                        except plan_mod.PlanError as e2:
                            parse_ok = False
                            parse_via = "converter"
                            parse_error = e2
                    else:
                        parse_ok = False
                        parse_via = "text"
                        parse_error = e
                except plan_mod.PlanError as e:
                    parse_ok = False
                    parse_via = "text"
                    parse_error = e
            else:
                try:
                    tasks = plan_mod.parse_plan(text)
                    parse_ok = True
                    parse_via = "json"
                except plan_mod.PlanError as e:
                    parse_ok = False
                    parse_via = "json"
                    parse_error = e

            if parse_ok:
                try:
                    plan_mod.check_new_tests(tasks, config.REPO)
                except plan_mod.PlanError as e:
                    parse_ok = False
                    parse_error = e

            kw2 = dict(attempt=attempt, via=parse_via, ok=parse_ok)
            if parse_error is not None:
                kw2["error"] = str(parse_error)
            gw.telemetry.record("plan_parse", **kw2)

            if parse_ok:
                pid = plan_mod.save_plan(config.STATE_DIR, goal, tasks)
                print(f"plan {pid}: {len(tasks)} tasks")
                for t in tasks:
                    print(f"  {t['key']}. {t['title']}")
                    print(f"    files: {', '.join(t['files'])}  tests: {', '.join(t['tests'])}")
                return 0

            last_reason = str(parse_error)
            messages.append({"role": "assistant", "content": text})
            if as_text:
                messages.append({"role": "user",
                                 "content": f"Your plan was invalid: {parse_error}. Answer with the corrected plan text only."})
            else:
                messages.append({"role": "user",
                                 "content": f"Your plan was invalid: {parse_error}. Answer with the corrected JSON plan only."})
            continue
        print(f"plan invalid: {last_reason}", file=sys.stderr)
        return 1
    elif args.cmd == "plan-add":
        try:
            p = plan_mod.load_plan(config.STATE_DIR, args.plan_id)
        except KeyError:
            print(f"no such plan: {args.plan_id}", file=sys.stderr)
            return 1
        if p["status"] != "draft":
            print(f"plan {args.plan_id} was already added", file=sys.stderr)
            return 1
        tasks = p["tasks"]
        key_to_id = {}
        for t in tasks:
            after_ids = [key_to_id[a] for a in t.get("after", [])]
            prot = list(t.get("protected", []))
            for test in t["tests"]:
                if test not in prot:
                    prot.append(test)
            task = add_one(store, t["title"], t["goal"], t["files"], prot,
                           t["tests"], t.get("role"), after_ids)
            key_to_id[t["key"]] = task["id"]
        plan_mod.mark_added(config.STATE_DIR, args.plan_id, key_to_id)
        Telemetry(config.STATE_DIR / "telemetry.jsonl").record("plan", plan=args.plan_id,
                                                                tasks=len(tasks), edited=plan_mod.edited(p))
        return 0
    elif args.cmd == "plan-tests":
        refresh_memory()
        tel = Telemetry(config.STATE_DIR / "telemetry.jsonl")
        gw = Gateway(tel)
        try:
            results = plantests.draft_tests(gw, args.plan_id, config.REPO, config.STATE_DIR)
        except KeyError:
            print(f"no such plan: {args.plan_id}", file=sys.stderr)
            return 1
        for r in results:
            print(f"{r['key']} {r['file']}: {r['status']}")
        return 0
    elif args.cmd == "run":
        tel = Telemetry(config.STATE_DIR / "telemetry.jsonl")
        print(f"running {args.task_id}")
        result = run_task(store, Gateway(tel), args.task_id)
        print(f"{args.task_id}: {result}")
        return 0 if result == "done" else 1
    elif args.cmd == "run-all":
        refresh_memory()
        tel = Telemetry(config.STATE_DIR / "telemetry.jsonl")
        gw = Gateway(tel)
        try:
            current = gw.health().get("model")
        except Exception:
            current = None
        order, blocked = scheduler_plan(store.tasks(), config.ROLES, current)
        waiting = [t["id"] for t in store.tasks() if t["status"] == "awaiting_review"]
        order = waiting + [tid for tid in order if tid not in waiting]
        if not order and not blocked:
            print("nothing to run")
            return 0
        print("plan: " + " ".join(order))
        if blocked:
            print("blocked: " + " ".join(blocked))
        statuses = run_all(store, gw, order)
        last = order
        while True:
            again = [tid for tid in order if store.get(tid)["status"] == "todo"
                     and all(store.get(x)["status"] == "done" for x in store.get(tid).get("after", []))]
            if not again or again == last:
                break
            print("next pass: " + " ".join(again))
            statuses.update(run_all(store, gw, again))
            last = again
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
        if args.plans:
            plans_dir = config.STATE_DIR / "plans"
            if not plans_dir.exists():
                print("no plans yet")
                return 0
            plans = []
            for f in sorted(plans_dir.glob("*.json")):
                plans.append(json.loads(f.read_text(encoding="utf-8")))
            if not plans:
                print("no plans yet")
                return 0
            events = Telemetry(config.STATE_DIR / "telemetry.jsonl").load()
            summaries = plans_summary(plans, events)
            for s in summaries:
                d = s["drafts"]
                print(f"PLAN {s['id']} | tasks {s['tasks_count']} | {s['status']} | {s['edited']} | "
                      f"drafts: collected {d['collected']}, import_error {d['import_error']}, "
                      f"syntax_error {d['syntax_error']}, error {d['error']}, "
                      f"exists {d['exists']}, missing {d['missing']}")
            return 0
        if args.replay:
            summary = replay_summary(Telemetry(config.STATE_DIR / "replay.jsonl").load())
            if not summary:
                print("no replay runs yet")
            else:
                for key in sorted(summary):
                    s = summary[key]
                    print(f"{key}: {s['passed']}/{s['runs']} passed, {s['attempts']} attempts, {s['seconds']:.0f} s")
                    for task in sorted(s['tasks']):
                        t = s['tasks'][task]
                        print(f"  {task}: {t['passed']}/{t['runs']} passed, "
                              f"{t['attempts'] / t['runs']:.1f} attempts and {t['seconds'] / t['runs']:.0f} s per run")
            return 0
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
            ab = diagnosis_ab(events)
            if ab["hinted"]["retries"] > 0 or ab["plain"]["retries"] > 0:
                print(f"diagnosis A/B: with diagnosis {ab['hinted']['passed']}/{ab['hinted']['retries']} retries passed, without {ab['plain']['passed']}/{ab['plain']['retries']}")
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
    elif args.cmd == "replay":
        tasks = []
        for tid in args.task_ids:
            try:
                tasks.append(store.get(tid))
            except KeyError:
                print(f"no such task: {tid}", file=sys.stderr)
                return 1
        role = config.ROLES[args.role]
        model = args.model if args.model is not None else role["model"]
        effort = args.effort if args.effort is not None else role["effort"]
        max_tokens = args.max_tokens if args.max_tokens is not None else role["max_tokens"]
        gw = Gateway(Telemetry(config.STATE_DIR / "replay.jsonl"))
        budget = args.reasoning_budget if args.reasoning_budget is not None else role.get("reasoning_budget")
        if budget is not None:
            results = replay.replay(tasks, gw, model=model, effort=effort, max_tokens=max_tokens,
                                    tries=args.tries, repo=config.REPO, root=config.WORKTREES,
                                    reasoning_budget=budget)
        else:
            results = replay.replay(tasks, gw, model=model, effort=effort, max_tokens=max_tokens,
                                    tries=args.tries, repo=config.REPO, root=config.WORKTREES)
        total_seconds = 0.0
        passed = 0
        for res in results:
            total_seconds += res["seconds"]
            if res["result"] == "passed":
                passed += 1
            print(f"{res['task']}: {res['result']} ({res['attempts']} attempts, {res['seconds']:.0f} s)")
        print(f"replay {model}: {passed}/{len(results)} passed, {total_seconds:.0f} s")
        return 0
    elif args.cmd == "memory":
        if args.memory_cmd == "learn":
            r = learn.learn(Gateway(Telemetry(config.STATE_DIR / "telemetry.jsonl")),
                            Store(config.STATE_DIR).tasks(),
                            Telemetry(config.STATE_DIR / "telemetry.jsonl").load(),
                            config.LESSONS, config.STATE_DIR, config.REPO.name)
            print(f"learn: {r['corrections']} corrections, {r['added']} added, {r['duplicates']} duplicates, {r['skipped']} skipped")
            return 0
        store = memstore.Store(config.STATE_DIR / "memory.db")
        try:
            embedder = None if args.no_vectors else embed.Embedder()
            if args.memory_cmd == "index":
                h = memindex.index_history(store, Store(config.STATE_DIR).tasks(),
                                           Telemetry(config.STATE_DIR / "telemetry.jsonl").load())
                print(f"history: {h['chunks']} chunks, {h['changed']} changed, {h['removed']} removed")
                counts = memindex.index_project(config.REPO, store, embedder)
                print(f"memory: {counts['chunks']} chunks, {counts['changed']} changed, {counts['removed']} removed, {counts['embedded']} embedded")
                return 0
            elif args.memory_cmd == "search":
                hits = memsearch.search(store, args.query, embedder, codemap.build(config.REPO), args.k)
                if not hits:
                    print("no results")
                else:
                    for h in hits:
                        print(f"{h['score']:.4f}  {h['title']}  ({h['why']})")
                return 0
        finally:
            store.close()
    else:
        for t in store.tasks():
            extra = f" commit {t['commit']}" if t.get("commit") else ""
            wt = t.get("worktree")
            mark = "  [wt]" if wt and (config.WORKTREES / wt).exists() else ""
            triage = ""
            if t.get("status") == "needs_human" and isinstance(t.get("triage"), dict):
                triage = f" [triage: {t['triage'].get('verdict')}]"
            print(f"{t['id']}  {t['status']:<12} {t['title']}{extra}{mark}{triage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

