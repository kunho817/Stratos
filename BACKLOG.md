# Stratos backlog

The list of improvements to Stratos itself, kept by Claude and the user. Each session: read this first, pick the top
open item (or what the user asks for), and update it at the end. Evidence comes from `stratos report`,
`stratos report --replay` and the diffs read while verifying. Finished items move to "Done" with the task ids.

Stages (2026-11-18): 0 skeleton, 1 self-development loop, 2 measurement and model choice: done. 3 decision layer:
partly (rules v1, Jev shadow, diagnosis A/B). 4 autonomy (planning, tests, merging): planner and test drafts built, quality not yet good enough to skip review.
5 other projects (a small Python project, then Unity/Unreal): not started.

## Open (top first)

0. **Memory -> retrieval -> planner (user's idea, 2026-11-18).** Keep a memory of the project (code split by
   function, tests, past tasks with goal/diff/failures/review issues, and lessons: what a person changed in a plan or a
   test draft and why) and let a fast model (Tiel or AgentWorld, one load, many short calls) pick what the planner
   needs before it plans. Reading is cheap here (~4 s per 10K prompt tokens), writing is not (~80 tok/s), and only one
   model fits at a time, so "many small models" means many calls of one fast model that answer with ids, not text.
   Start without a vector DB (the corpus is small; keyword search + the model's choice); add embeddings only if
   retrieval visibly misses. Measure with the three feature goals of the planner comparison (scratchpad plan_eval.py).
   Lessons recorded from every human edit are the way to grow CONVENTIONS.md automatically.
1. **Planner quality.** `stratos plan` (T061-T065) and `stratos plan-tests` (T066-T070) work end to end.
   Record so far: P001 9 tasks, broke the same-file rule -> T063 put Stratos's task rules in the prompt; P002 3 tasks,
   invented APIs (gw.ask, load_plan in state.py) -> T064 shows public signatures; P003 2 tasks, goals rewritten by
   hand; P004 3 tasks, goals tightened by hand, all 3 test drafts collected but all needed fixes (plan JSON shape
   wrong in 2 files, an error copied from the plan, an unrequested requirement, STATE_DIR not isolated). Every plan
   so far was edited (telemetry "plan" edited=true). Next ideas: show the planner real call examples (e.g. how tests
   fake Gateway and call cli.main), the shapes of the data it writes about (a plan is {"tasks": [...]}), and let it
   see the files a task will change, not only the summary. Measure with the same feature goals again.
2. **Test drafts.** Track drafts kept as written vs fixed (telemetry "test_draft"); compare after each prompt change.
   TEST_SYSTEM could tell the model to copy the fixture style of the example and to keep every path in tmp_path.
3. **Diagnosis A/B (live since T060).** Read the "diagnosis A/B" line in `stratos report` after ~30 retries; adopt
   (always give the diagnosis) or drop it. Offline: 7/19 with vs 5/19 without.
4. **Tiel's third try.** Real history: Tiel passed 30/47 on the first try, 38/47 within two, 39/47 within three.
   Consider ATTEMPT_PLANS coder = 2 tries, then Swift. Check against the diagnosis A/B first (it changes retries).
5. **Model switch cost.** 104 switches took 2,324 s (about 30% of model time). Swift's switch is 60-100 s. Ideas:
   order rounds to share models more; let the reviewer review Swift's and Tiel's candidates in one load.
6. **Review strength.** 49 approvals, 1-2 change requests. It caught unreachable code in T058, but missed T060's
   attempt-vs-tries bug and unrequested reformatting in T058. Replay old diffs with known problems to measure it.
7. **A second project.** Run Stratos on a small Python project that is not Stratos, to find what is Stratos-specific.
8. **Non-Python files.** Answers for non-Python files without a FILE header cannot be rescued (T022/T025 rules).
9. **Memory headroom.** With Swift loaded, Windows has ~13 GB of commit left; a background run was once killed by
   Claude Code for low memory during a model switch.

## Done

- T061-T070 planner: plan, plan-add, plan-tests; prompt rules, signatures, files/protected overlap refused, goal-file
  errors, raw planner answers saved (.stratos/answers/plan-<call_id>.md), check_draft timeout and UTF-8.

- T054-T056 reasoning budget (Gateway, loop, replay, report keys). T057-T060 diagnosis A/B.
- coder_hard: Flint -> Qwen3.8-Flash-Next Coder -> Swift 1.5 IQ2_XS with a 3000-token budget (replay on six hard tasks).
- AgentWorld as a decision model: rejected (offline A/B no better than always choosing Tiel).
