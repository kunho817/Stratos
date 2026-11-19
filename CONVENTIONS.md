# Stratos conventions (for the planner and the test writer)

Facts about this codebase that a plan or a test must get right. Keep this short; add a line when a plan or a test
draft gets one of these wrong.

## Data shapes
- A plan file (.stratos/plans/P00N.json) is {"id", "goal", "tasks": [...], "status", "hash"}. A planner answer is
  {"tasks": [{"key", "title", "goal", "files", "tests", "protected", "after", "role"}]}, never a bare list.
- A task in .stratos/tasks.json (stratos/state.py, class Store): {"id": "T001", "title", "goal", "files",
  "protected", "tests", "role", "after", "status", ...}. Store(state_dir).add_task(...), .get(id), .update(id, **f).
- Telemetry (stratos/telemetry.py): Telemetry(path).record(kind, **fields) appends one JSON line; .load() reads them.
  Every event has "ts" and "kind". The kinds and their fields (use these names, do not invent others):
  - "call": call_id, task, role, attempt, model, effort, prompt_tokens, completion_tokens, reasoning_chars, finish,
    seconds (and reasoning_budget when one was set)
  - "outcome": call_id, task, result ("passed", "failed", "no_files", "dropped_defs", "refused", "review_approve",
    "review_changes", ...), detail
  - "switch": model, from_model, seconds
  - "decision": decision ("role" or "escalate"), decider ("rules" or "jev"), task, choice, confidence, reason
    (escalate also: attempt, role)
  - "diagnosis": task, attempt, used, chars (and error)
  - "verdict": task, ... (a person's reset of a task)
  - "plan": plan (the plan id), tasks (count), edited (bool) - written by plan-add
  - "test_draft": plan (the plan id), key, file, status ("collected", "import_error", "syntax_error", "error",
    "exists", "missing", "risky", "leaks"), and risks (labels) for "risky" or leaks (failing ids, up to 10) for
    "leaks" - written by plan-tests

## Talking to models
- stratos/gateway.py, class Gateway(telemetry): gw.ensure_model(model) loads a model; gw.chat(messages, *, task,
  role, attempt, model, effort, max_tokens, reasoning_budget=None) returns (call_id, text). There is no gw.ask.
- Model settings live in stratos/config.py: config.ROLES[role], config.PLANNER, config.DIAGNOSER.
- A function that calls a model takes gw as a parameter.

## Paths
- config.REPO is the repository, config.STATE_DIR is .stratos/, config.WORKTREES the task copies.
- Raw model answers are saved under config.STATE_DIR / "answers".
- Plans: stratos/plan.py (load_plan(state_dir, pid), save_plan, parse_plan). Not in state.py.

## Commands (stratos/__main__.py)
- Every command is a subparser in main(argv); main returns an exit code. A bad argument (like an unreadable
  --goal-file) calls that subparser's .error(...) (exit code 2); other failures print to stderr and return 1.
- New commands get a line in the usage text at the top of __main__.py.

## Tests
- pytest, in tests/. A module docstring describes the behaviour; then test functions.
- Never touch the real .stratos or the network: monkeypatch config.STATE_DIR and config.REPO to tmp_path, and
  replace the gateway (monkeypatch.setattr(cli, "Gateway", FakeGateway) for commands, or pass a fake gw).
- Commands are tested through cli.main([...]) (from stratos import __main__ as cli), checking the return code and
  capsys output.
- A fake gateway's chat(messages, **kw) returns (call_id, text).

## Plans (lessons from hand edits)
- Each task's "tests" list starts with a NEW test file for that task (plan-tests never overwrites a file); existing
  test files that must keep passing may follow it. (P008 named only existing files, so no tests were drafted.)
- Put the task's own new test file in its "protected" list too, so the coder sees the tests it must pass. (P006)
- Tasks of one plan share facts: the same value (for example where "edited" comes from) must be described the same
  way in every task's goal. (P006's two test drafts disagreed.)
- TEST_SYSTEM is in stratos/plantests.py; CODER_SYSTEM is in stratos/context.py.
