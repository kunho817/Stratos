# Stratos backlog

The list of improvements to Stratos itself, kept by Claude and the user. Each session: read this first, pick the top
open item (or what the user asks for), and update it at the end. Evidence comes from `stratos report`,
`stratos report --replay` and the diffs read while verifying. Finished items move to "Done" with the task ids.

Stages (2026-11-18): 0 skeleton, 1 self-development loop, 2 measurement and model choice: done. 3 decision layer:
partly (rules v1, Jev shadow, diagnosis A/B). 4 autonomy (planning, tests, merging): planner and test drafts built, quality not yet good enough to skip review.
5 other projects (a small Python project, then Unity/Unreal): not started.

## Open (top first)

Process (user, 2026-11-18): after each feature chunk (one "push"), build a larger throwaway project with Stratos
(e.g. a web game) in D:\Strata\Trials\<name> and log what breaks here. Next trial: after the planner chunk (P006).

**Trial 1: tower defense (D:\Strata\Trials\TowerDefense, 2026-11-19).** JS + node --test, 10 tasks, 107 tests, the
game plays headless (13 waves in 3 minutes) and is served on 127.0.0.1:8123. Found, by weight:
   a. **Wrong test drafts were the main cost.** 8 drafted tests had wrong expectations (grid paths that were not the
      only way, a "maze" with no path, a spawn timer that had not run out, an enemy that had already left, a tower on
      the start cell). Each time Swift's code was right and the task went to needs_human. Ideas: before needs_human,
      ask a model whether the failing assertion contradicts the goal (show the goal, the test and the output); tell
      TEST_SYSTEM to work out each expected value step by step in a comment; draft fewer, simpler cases.
   b. **node --test output is useless as feedback.** The last 4000 characters are stack traces; the failing test
      names and assertion values are cut off, and failure_signature finds no ids. Use the TAP reporter
      (--test-reporter=tap) and keep the "not ok" lines with their expected/actual, per project (a summarize
      setting or a parser per test runner).
   c. **The planner did not define the data shared between modules** (state, enemy, tower shapes, numbers); Claude
      wrote a data model into CONVENTIONS.md and most of each goal. Plan a "shared contract" first (a CONVENTIONS
      section or a task-0 doc) before splitting into tasks. It also left out index.html.
   d. **Bugs the tests missed, found by playing headless:** canPlace and placeTower ignored existing towers (a test
      with towers already built was never drafted). A headless "play" script per project (a smoke run) would catch
      this kind of bug; render bugs (enemies drawn at a cell corner, a copied helper, an unrequested indicator) were
      found only by reading the diff.
   e. **Copying instead of importing:** path.js copied grid.inBounds, render.js copied step.enemyPosition; the
      reviewer missed both. Add "uses existing functions instead of copies" to the review checklist.
   f. Test drafts: answers with no FILE header and no fence (raw file) were dropped (2/7); a Python docstring in a JS
      test; for JS the draft check is only `node --check` (syntax), not "the runner loads it".
   g. Harness: a task whose dependency finished in the last round stays todo (T007 needed another run-all);
      `stratos add` and plan-add still need --protected to include the task's own tests by hand.
   h. Old tests that pin the behaviour being fixed: when a fix task says "keep the old tests passing", check that
      they do not encode the bug (render.test.js pinned the corner position and the indicator).

**After trial 1 (P009, T085-T092, 481 tests, 2026-11-19):** verify.summarize_output keeps TAP "not ok" lines with
their error/expected/actual/location (4,000 chars of stack traces -> ~1,000 chars of names and values), decide reads
TAP names, triage.py asks Swift "test or code?" before needs_human (store field + telemetry + `status`), test drafts
get a language-style top comment and "work out every expected value step by step", header-less single-file drafts
are kept. Still open from trial 1: multi-line expected/actual values in TAP are cut (keep the indented lines after
"actual:"); triage has not met a real wrong test yet (it was not merged when T086's draft was wrong).
**P010 (T093-T097, 508 tests, 2026-11-19):** a .py draft that collects but uses importlib.reload, sys.modules
writes, os.environ writes, `config.X = ` or its own MonkeyPatch() gets status "risky"; one that collects cleanly is run
with the whole suite and gets "leaks" when tests outside the drafts of this run fail; `stratos plan` sends back a plan
whose task starts with an existing (or shared) test file; plan-add puts each task's tests into its protected list.
First real triage (T097): "test_wrong", correct - my old fakes lacked the new ignore parameter; it named both files.
T098: run-all runs a next pass for todo tasks whose dependencies became done (fixes trial 1's g). Still open:
a risky draft gets no second try with the reason (a person fixes it); the suite check costs one full test run per
draft (~40 s here).

**Trial 2: tower defense round 2 (P002 in the trial, 2026-11-19).** Upgrades/sell, boss waves, wave preview, panel,
keys. The new check made every task start with a new test file (first try). Found:
   a. **The planner did not follow the data to where it is used.** Upgrades changed damage/range in towers.js, but
      step.js reads TOWER_TYPES directly, so upgraded towers would have done nothing in play; a "step_boss" task
      was planned for behaviour step already had; a "state_level" task had nothing to do; the preview was called
      with wave + 1 although it already returns the next wave. Claude rewrote 5 of 6 goals (towerStats, towerAt,
      exact numbers, the boss rule "wave > 0"). Same root as trial 1 c: the planner needs the data flow (who reads
      which field) - item 0's memory should hold "who calls/reads what" per function.
   b. **A later task's test draft cannot see an earlier task's rules.** render_panel's draft invented its own
      upgrade and refund numbers (70% refund, double cost) because only render's goal was shown, and towers.js did
      not have the functions yet. Show each draft the goals (and drafts) of the tasks it comes after.
   c. **Drafts for tasks with several test files.** Two drafts were dropped: the answer was one header-less block per
      listed file (rewriting the existing ones too). Fixed: the header-less fallback counts only files still to write
      (fa90ca1). Better: list only the new file under "WRITE THESE TEST FILES" and show the others read-only.
   d. JS drafts: `await` inside a non-async test (2 drafts), replacing an ES module export
      (impossible), a float compared with === (1.2000000000000002), a test for exported constants nobody asked for,
      a "cooldown gets shorter" rule nobody asked for. 2 of 5 drafts were rewritten, 3 needed additions.

0. **Memory -> retrieval -> planner (user's idea, 2026-11-18).** Keep a memory of the project (code split by
   function, tests, past tasks with goal/diff/failures/review issues, and lessons: what a person changed in a plan or a
   test draft and why) and let a fast model (Tiel or AgentWorld, one load, many short calls) pick what the planner
   needs before it plans. Reading is cheap here (~4 s per 10K prompt tokens), writing is not (~80 tok/s), and only one
   model fits at a time, so "many small models" means many calls of one fast model that answer with ids, not text.
   Start without a vector DB (the corpus is small; keyword search + the model's choice); add embeddings only if
   retrieval visibly misses. Measure with the three feature goals of the planner comparison (scratchpad plan_eval.py).
   Lessons recorded from every human edit are the way to grow CONVENTIONS.md automatically.
1. **Planner quality.** Record: P001-P004 all needed hand edits (rules, invented APIs, data shapes). Then
   (T071-T076): CONVENTIONS.md in the prompt, the planner writes Key:/Title:/Goal:... text that code reads
   (plan.parse_text_plan; AgentWorld only as fallback - as the converter it broke JSON on quotes in goals),
   parse_plan refuses test-only tasks. P006/P007 (2026-11-18): field names and APIs right, same-file chains right,
   one return shape wrong (check_draft). Next: run P006 (report --plans) through plan-tests and plan-add to measure a
   whole feature; text after the last task is appended to its last field (risk); add a lesson to CONVENTIONS.md each
   time a plan or draft is fixed by hand (until item 0 records them automatically).
2. **Test drafts.** Record: P004 3/3 fixed by hand; P006 2 drafts disagreed (where "edited" comes from); P008 6
   drafts: 2 kept as written, 2 fixed (tmp_path=None, language case, module reload left in place), 2 rewritten (an
   in-process config reload that left a fake module in sys.modules; an answer without FILE header plus
   contradicting requirements). Ideas: show each task's draft the drafts already written for earlier tasks of the
   same plan; tell TEST_SYSTEM never to reload modules or touch sys.modules/os.environ outside monkeypatch, and to
   test import-time settings in a subprocess; accept a lone code block as the first test file (like the coders'
   T022 rule); make plan-add put each task's tests into its protected list automatically.
3. **Diagnosis A/B (live since T060).** Read the "diagnosis A/B" line in `stratos report` after ~30 retries; adopt
   (always give the diagnosis) or drop it. Offline: 7/19 with vs 5/19 without.
4. **Tiel's third try.** Real history: Tiel passed 30/47 on the first try, 38/47 within two, 39/47 within three.
   Consider ATTEMPT_PLANS coder = 2 tries, then Swift. Check against the diagnosis A/B first (it changes retries).
5. **Model switch cost.** 104 switches took 2,324 s (about 30% of model time). Swift's switch is 60-100 s. Ideas:
   order rounds to share models more; let the reviewer review Swift's and Tiel's candidates in one load.
6. **Review strength.** 49 approvals, 1-2 change requests. It caught unreachable code in T058, but missed T060's
   attempt-vs-tries bug and unrequested reformatting in T058. Replay old diffs with known problems to measure it.
7. **A second project.** Run Stratos on a small Python project that is not Stratos, to find what is Stratos-specific.
8. **Worktrees and main.** A task's copy is made once; later commits on main (test fixes) do not reach it unless it is
   reset after its dependencies are merged. Consider merging HEAD into the copy at the start of each round.
9. **Non-Python files.** Answers for non-Python files without a FILE header cannot be rescued (T022/T025 rules).
10. **Memory headroom.** With Swift loaded, Windows has ~13 GB of commit left. Claude Code killed a background run
   twice for low memory, both times during a switch to Swift (2026-11-18). Run Claude Code with
   CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP=1 (user's choice); still consider a lighter coder_hard or unloading
   the old model fully before Swift loads.

## Done

- Harness (2026-11-18): a FILE header alone in its own fence no longer leaves a fence line in the file (Tiel, T075/T076);
  a dependency already merged into HEAD is not a base for the dependent task's copy (T076 missed main's fixes).
- T071-T076: conventions, text planning read by code, AgentWorld fallback, plan_parse telemetry, stricter parse_plan.

- T061-T070 planner: plan, plan-add, plan-tests; prompt rules, signatures, files/protected overlap refused, goal-file
  errors, raw planner answers saved (.stratos/answers/plan-<call_id>.md), check_draft timeout and UTF-8.

- T054-T056 reasoning budget (Gateway, loop, replay, report keys). T057-T060 diagnosis A/B.
- coder_hard: Flint -> Qwen3.8-Flash-Next Coder -> Swift 1.5 IQ2_XS with a 3000-token budget (replay on six hard tasks).
- AgentWorld as a decision model: rejected (offline A/B no better than always choosing Tiel).
