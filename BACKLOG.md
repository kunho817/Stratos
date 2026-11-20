# Stratos backlog

The list of improvements to Stratos itself, kept by Claude and the user. Each session: read this first, pick the top
open item (or what the user asks for), and update it at the end. Evidence comes from `stratos report`,
`stratos report --replay` and the diffs read while verifying. Finished items move to "Done" with the task ids.

Stages (2026-11-18): 0 skeleton, 1 self-development loop, 2 measurement and model choice: done. 3 decision layer:
partly (rules v1, Jev shadow, diagnosis A/B). 4 autonomy (planning, tests, merging): planner and test drafts built, quality not yet good enough to skip review.
5 other projects (a small Python project, then Unity/Unreal): not started.

## Open (top first)

**Work order 3 (user, 2026-11-20, after trial 11; reordered the same day): everything still to do, in order.
Each P ends with push + a trial. Replaces the rest of work order 2.**
- P10 context: only what is needed (user: "only the needed parts, so the models' memory of a long context fades
  less"). First the huge prompts (user asked why reading is sometimes enormous): coder prompts reach 56-66k
  tokens (median 7-13k) on tasks that touch stratos/__main__.py - since T029 every module a task file imports is
  shown whole as READ-ONLY, and __main__.py imports 25 modules: T179 (a reset flag) got 8.5k tokens of its own file,
  2k of tests and ~45k of read-only modules it never needed (report.py 5k, loop.py 4.7k, plan.py 4.5k ...). Swift
  spent 90-250 s per call on them. Fix: for imported modules show only the names the task's files use from them
  (code-map signatures, or the symbol's text when it is short), whole text only for small modules; measure prompt
  tokens and first-try before/after on replays.
  The same rule for the other roles: triage (up to 34k tokens) and the test writer (up to 29k) get whole test
  files and outputs - give them the failing tests and the names they use.
- P11 tests (problems keep coming from tests). Causes so far: wrong drafts (data rules, arithmetic, an unread
  goal), old tests and fakes pinning old behaviour, Claude's own slips (escapes, a measure on the wrong thing,
  imports removed as unused), junk in drafts (a half-written duplicate function). Build: ruff F401/F811/F821 on
  every draft (b); refcheck tells "the reference crashed" from "interface" (a); old test files not shown as
  "missing" (c); the Claude Code hook also runs ruff F on test files Claude writes; Claude's fixes to drafts (the
  "(Claude: ...)" notes in commits) become lessons (d); measure: wrong drafts per task, per trial.
  **Test cases instead of test code (user, 2026-11-20):** Claude gives the cases (call, input, expected - the part
  that needs judgement) and Stratos writes the test files. Cases that are plain calls (module, function, args ->
  result or error) are turned into pytest parametrize mechanically (no model; this is the table-driven item);
  cases that need setup (files, fakes, monkeypatch, CLI) go to the test writer with the case list, and the
  existing checks (ruff, collect, refcheck, Claude's reference) run on the result. Removes Claude's slips in test
  code and the drafts' wrong expected values. Try it on Stratos's own tasks too (rule 1 would change).
- P12 dashboard (user: "only progress bars is dull - stream what it is doing, show the terminal log"): a live
  view - the model's answer streamed token by token as it writes (the gateway asks PolyStrata with stream=true and
  appends the text to a live file; the page reads it over server-sent events), the run log of run-all/plan-tests,
  the current step (attempt, model switch, tests running, review), test output as it comes. It also keeps itself current - picks up new projects and plans, reloads its own code after a merge (now a
  restart is needed), shows what later P's add (plans and their critiques, refcheck results, draft flags, memory
  counts, Jev vs rules, efficiency over time); a "try it" page per trial (web games served as static files, CLI
  tools run with a fixed command from stratos.toml on text pasted in the page; 127.0.0.1 only, no free shell).
- P13 code cleanup: unused code (ruff F is clean; by name, gitops.append_to_commit_message and
  plan.check_new_tests are used only by tests), features that stay off (draftcheck since P7) - keep or remove,
  shared answer reading (loop._judge and refcheck.check read answers the same way), long modules that the models
  edit badly (__main__.py 685 lines, report.py 582, plan.py 492: split by command), speed of the suite (~90 s).
- P14 memory (the central goal): `memory learn` after each run-all/push, wiki pages for trial projects, packs for
  the test writer/reviewer/triage, a second model checks wiki pages, the M6 A/B (with vs without memory).
- P15 Jev: a fair test first - replay both branches (keep/switch model, rules' role vs Jev's role) on past tasks
  with the replay tool, so "Jev was right" is not decided by the rules' own choices; adopt it per decision where
  it wins; new uses to try: which drafts a person should read first, whether a failure is test_wrong (triage).
- P16 time: model switches (36% of model time; order rounds by model), the design-by-numbers "search" task
  kind (item 16). (Table-driven tests moved into P11.)
- Then a direction question for the user: stage 5 (another language/engine, e.g. Unity C#).

**Work order 2 (user, 2026-11-20, after P8): what was left out, in order. Each P ends with push + a trial.**
- P9 Claude's and the models' small slips, mechanically: addcheck names only the old tests that use what the goal
  changes, capped at 8 (T195); lenient edit-block markers (T197); "partial_file" and an edit-format hint for
  unreadable blocks (T198); the cut-off note for edit_mismatch, one import line in refcheck (T196). Still: addcheck
  should skip the tests of tasks in After (T198 got a wrong "new test of T196" warning).
  **P9 built (T195-T200, 854 tests, 2026-11-20).** Seen at once: addcheck went from ~40 warnings to the 3 right ones
  on the next add; partial_file caught Tiel (T200 a3: 101 of 385 lines) and Swift (T200 a7) and the next try passed.
  Found while verifying: T197's line reader let a block without a divider swallow the next block (Claude read the
  diff; T199); T198's answer held the marker text inside a string and the old regex split it mid-line (T197's
  line reader fixes that). check_answer had 9 nested levels (deepest line 56 spaces): T196/T198 failed 7 times on
  its indentation and the reviewer misread a branch (T198 a5 accepted by hand) -> T200 split it into _judge with
  early returns and _lint_fix (nesting 12 -> 3 by an ast count). Claude's slips: T200's first test counted
  indentation, so aligned string lines failed both models (consensus named it), and the goal's "change nothing
  else" left no room for the helper the limit needed. Lesson: a structural limit is measured on the structure
  (ast), and the goal must allow what the limit forces.
  **Trial 11: Quill, a Markdown-to-HTML CLI (D:\Strata\Trials\Quill, Python, 2026-11-20) - the trial after P9; two
  rounds, 10 tasks, 138 tests, pushed.** Best trial so far: first try 8/10, 1.5 attempts per passed task, waste
  4.9% (all tasks so far: 105/200, 2.62, 40.8%); every output equals Claude's reference implementation on three
  sample files with edge cases. What made the difference: Claude rewrote the plan before plan-tests (the planner
  put all tasks in quill/__init__.py, split the block splitting between two tasks and left --toc no path; one module
  per task, exact inline rules - no nesting, an unclosed marker stays) -> round 1's 86 drafts passed unchanged on
  Claude's reference and all 6 tasks passed on the first try. Round 2 (changes to existing modules): Flint's
  critique and Claude found 3 goal problems (a quote line "ends a fence", "continue from the !" = an endless
  loop, headings() must skip "#" lines in fences - the TOC had that bug); drafts: 2 wrong of 51 (two lines = one
  paragraph, slug "a--b") and a half-written duplicate test function that no check caught.
  Refcheck (Swift): round 1 agreed on 5 tasks; toc's reference crashed (parameter toc hid `from quill import toc`
  - Claude's goal invited it) and was reported as "interface". Round 2: flagged 4 tests - 1 right, 2 reference
  bugs, 1 crash shown as "interface" (that was a wrong test).
  Edit blocks: Swift answered blocks.py (174 lines) and inline.py (84) as whole files; only small edits came as
  blocks. Fine while partial_file/dropped_defs guard it; edit blocks pay off on bigger files.
  Claude's slips: removed two imports as unused after reading a grep cut by head (T010 failed 4 times; consensus
  and triage named it) - run ruff on a test file before calling an import unused; a heredoc escape again (the
  reference's cli.py).
  New items: (a) refcheck: tell "the reference crashed" (every failure is the same exception raised in the
  reference's own file) from "the goal leaves the interface open"; (b) plan-tests: run ruff F811 (a function
  defined twice) and F401/F821 on the drafts; (c) plan-tests prints old test files of a task as "missing";
  (d) memory (user, 2026-11-20): `memory learn` runs only by hand (last at Pantry round 2), Claude's draft fixes in
  commits never become lessons, trial projects get no wiki -> automate in P11.
- P10 time: model switches are 12,558 s of 72,421 s active (switches = 36% of model time). Order the rounds so one
  load serves more calls (item 5); measure before and after with report --efficiency.
- P11 memory (the central goal, items 0/M5/M6 and P3 leftovers): context packs for the test writer, reviewer and
  triage; a second model checks wiki pages; the M6 A/B (with vs without memory on fixed goals).
- P12 design-by-numbers "search" task kind (item 16); table-driven tests (P7 leftover).
- Then a direction question for the user: stage 5 (another language/engine, e.g. Unity C#).
- Closed without building: item 8 (worktrees get main) - `reset` rebuilds the copy and `status` warns about test
  files changed after a task was added; item 9 (non-Python rescue) - edit blocks made it rare; P1's quick re-ask on a
  syntax error - partial_file/edit hints cover the common cases.

**Work order (user, 2026-11-20): P1 -> P2 -> P3 -> P4, each P ends with push + a trial.**
- P1 first-try pass rate without more model calls: preflight (run the task's tests on its base before any model
  call; refuse import errors of other modules, broken test files, failing old tests), the preflight failures in the
  first prompt, a syntax check of each answer with a quick re-ask, triage on the last *failed* attempt,
  `stratos drop`, `status` warns about stale test lists (items 11, 12). Measure with `report --efficiency`.
  Evidence (4 projects, 192 tasks): 107 first-try passes; of 85 first failures 36 tasks were later reset by a
  person, 38 of 50 reset reasons "test wrong or outdated"; 263 failed attempts before a pass, 2.9 h model time.
  **P1 built (T154-T160, 721 tests, 2026-11-20):** verify.syntax_errors (py compile, node --check; trap: node 24
  passes an ESM syntax error in a .js file when no package.json says "type": "module", so such files are checked
  again as --input-type=module - plantests' JS draft check has the same hole), preflight.py (refuses missing or broken
  test files, imports of files the task does not write, uninstalled modules; otherwise its failing output goes into
  the first prompt), check_answer stops at "syntax_error" before the tests, triage on the last *failed* attempt,
  `stratos drop` (T142 dropped), `status` warns about test files changed after a task was added (it flagged T142's).
  Run: 7 tasks, 10 attempts (4 first-try of 7). Claude found one bug by reading T155: `from stratos import x` with x
  missing names stratos/__init__.py in the ImportError, so preflight would have refused every new-module task (T160).
  Seen: the diagnosis switches to another model and back between two Tiel attempts (6 s each way) - P4.
  Not built: the "quick re-ask" on a syntax error (it is a normal failed attempt). The first-try effect is measured
  on the next trial.
- P2 test drafts with a second model (missed request of 2026-11-19: multi-model cross-checks): Gemma 4 31B
  uncensored (Jiunsong SuperGemma4-31b-abliterated Q4_K_M, G:\PolyStrata-models, user 2026-11-20) as a non-Qwen
  checker; offline experiment (a): how many known wrong drafts (trial 1 x8, Orbit x5) each of Qwen3.6, Flint,
  Gemma 4 catches; then a draft check before running; the test writer proposes edits to old tests that call changed
  names; data files whole in its pack; drafts see the goals of the tasks they come after.
  **Gemma 4 31B (2026-11-20): does not run.** strata-poly's gemma4 code needs gemma4.expert_count (26B-A4B MoE
  only); the 31B is dense. User: no llama.cpp side server (PolyStrata's GPU + RAM split is the point), so it stays
  unused (file kept in G:\PolyStrata-models\supergemma4-31b).
  **Experiment (a) done (scratchpad draft_eval.py, 2026-11-20).** 6 fixed draft files from trials 1 and 4: 20 wrong
  tests (changed or removed by a person later), 108 kept; a "check each test by hand" prompt, 2 runs per model:
  Qwen3.6 Q3 caught 3/2 (false alarms 0/1), Tiel 7/7 (2/4), **Swift 13/13 (3/1), ~4 min per run**, Flint 16/12
  (3/3) but 12 min. Swift found the shared-state DOM tests Claude removed by hand; nobody found "pixel (0,0) places
  a tower at (0,0)" (the start cell) or "trail last entry equals probe position". The reviewer model (Qwen3.6) is the
  weakest checker by far. -> the draft check uses Swift (it is loaded right after it writes the drafts: no switch).
  **P2 built (T161-T165, 744 tests, 2026-11-20):** TAP multi-line expected/actual/error values kept (item 13; known
  nit: value lines are scanned again by the outer loop, so a nested "error:" inside a value can appear twice),
  draftcheck.py (Swift, the whole plan's goals + the task's files, flags only names that exist in the draft), plan-tests
  runs it on every written draft and prints the flags (advisory: a person still reads every draft), the test writer is
  told not to assume the contents of data another task writes, the reviewer rates repeated work medium only when it
  grows with the input (item 14), `stratos accept` (item 15, first half). Not built from the P2 list: edits to old
  tests proposed by the test writer (moved to P3).
  Run: first try 2 of 5 (T162, T164). T163 failed on Claude's own wrong test (a plain-text answer becomes a draft, so
  it is never "missing") - Swift tried to change the fallback to pass it and the reviewer rejected that as unrequested
  twice, correctly; Claude's fix then had a broken escape and **preflight refused it before any model call** (the first
  real refusal). T165: Tiel answered no_files twice on the 640-line __main__.py (M3a's note again: big files need
  edit-style answers or smaller modules).
- P3 plan critique (experiment (b) on Ledger's goal), a second model checks wiki pages, a wiki overview page, packs
  for test writer / reviewer / triage, M6 A/B.
  **Experiment (b) done (scratchpad critique_eval.py, 2026-11-20):** the planner's original plans of Lumen and Pantry
  against the 12 problems Claude fixed, 2 runs: Flint 17/24, Tiel 12, Swift 9, Qwen3.6 8 (~2 min per plan for
  Flint). Flint's extra lines were mostly real (argparse exits 2, not 1, on "abc"; pixel-to-cell mapping undefined);
  one was wrong (parse_amount "not written by any task" - it already existed).
  **P3 built (T166-T170, 766 tests, 2026-11-20):** the reviewer sees the project's files (Pantry T006), a wiki
  overview page (no model: each module's purpose line and imports; also a memory chunk), the test writer sees the
  existing tests that import the task's files and can mark them "OUTDATED: path::test - reason" (logged, recorded,
  in the results; known limit: a task on a widely imported file such as config.py pulls in most tests - cap it),
  plancritic.py (Flint) runs after `stratos plan` and on `stratos plan-critique PID`, advisory, saved in the plan file.
  LESSONS.md: plan-tagged lessons for __main__.py and "name files, not task keys" (the __main__ lesson was tagged
  [code, tests, cli], so the planner never got it). Run: first try 4 of 5 (T166, T168, T169, T170 on attempt 1;
  T170 then had one review rejection). T167 failed 3 times on an old test Claude did not list as changing
  (test_wiki::test_chunks pinned "module chunks only"); triage named it exactly - the very case T168 is for.
  Not built from the P3 list: a second model checking wiki pages, packs for the reviewer/triage beyond the file list,
  the M6 A/B.
  **P4 started (T171-T172, 773 tests, 2026-11-20):** the diagnosis A/B is over and every eligible retry gets a
  diagnosis (with 9/36 retries passed, without 2/32); coder tasks get 2 Tiel tries, then 2 Swift tries (Tiel passed
  10 of 56 third attempts; 83 of 174 tasks pass on its first, 17 on its second); OUTDATED also for a task's own
  existing tests and the critic knows the test-file rule (trial 7). Both tasks first failed on old tests Claude had
  not updated (loop tests that assumed 3 Tiel tries, plantests_earlier pinning "no OUTDATED sentence"), and triage
  named both correctly. The loop tests now pin their attempt plan in conftest.
  **Jev decided (user + Claude, 2026-11-20): not adopted, stays in shadow.** Raw: escalation Jev 118/201 vs rules
  98/202, roles Jev 60/97 vs rules 24/29. Paired on the same decisions: escalation 115 agree, and where they
  disagree (181) Jev was right 97 times, the rules 84 (54%, a coin flip); roles: 32 pairs, the 5 disagreements all
  went to the rules. The escalation "truth" (did a different role pass later) is shaped by the rules' own
  choices, so it cannot show Jev is better; a real test needs replays of both branches - not worth it now that
  coder tasks escalate after 2 tries anyway.
  **Experiment (c) done (scratchpad review_eval.py, 2026-11-20):** 10 review cases from trials 5-7 with a known
  verdict (3 should block, 7 should pass), the current prompt with the file list, 2 runs: **Qwen3.6 9/9 (the
  reviewer stays)**, Tiel 8/8, Swift 6/5, Flint 4/4 (Flint flags unrequested things everywhere - the opposite of
  experiments a and b: each role has its own best model). The P2/P3 fixes held: the task-key case and the nit now
  pass. All four models called T013-a11 wrong for "no import json" - the import was in the file, not in the diff:
  T173 shows the reviewer the import lines of the changed files. Claude found by reading T173 that build_messages
  joined parts into a str.format template, so a JS import `{ b }` raised KeyError (latent since T166's file list):
  T174. A reviewer change would not cut switches, so the switch cost stays open.
  Still open in P4 (older note): the reviewer (Qwen3.6) - the weakest checker in experiment (a) and 4 wrong blocking reviews in
  trials 5-7 (a nit as medium, a task key read as a module, a short-circuit read as NameError, a present import
  called missing) while it caught one real bug (the servings padding) - and its load costs 2 switches per round:
  replay the reviewer cases of trials 5-7 with Swift/Tiel/Flint as reviewer (experiment c); worktrees get main
  (item 8).
- P4 time: fewer model switches, Tiel 2 tries (item 4), worktrees get main (item 8), decide diagnosis A/B and Jev.

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

   e. **Result:** T011-T016 done in 9 attempts in all (Tiel 2 tasks, Swift 4), 183 tests, the game plays headless
      to wave 13. Triage met three real wrong tests: T097 (Stratos) and T012 "test_wrong" with the exact reason
      (old waves.test.js pinned wave 5 as a normal wave - trial 1 h again); T016 "unclear" with an empty reason
      although the cause was in the test (a `\d` lost in a JS template literal, by Claude) - an empty reason should
      be retried or shown as "no reason".
   f. **Layout is untested.** T014 drew the panel below the map, outside the 640 x 400 canvas; the tests checked only
      the text. Found by Claude reading the diff. A headless smoke check that every fillText lands inside the
      canvas would catch this class.

**Trial 3: Ledger (D:\Strata\Trials\Ledger, Python CLI, 2026-11-19) - the first run with memory on.** Only a layout in
CONVENTIONS.md this time, no data model. So far:
   a. **The planner defined the shared data contract itself** (Decimal in memory, strings in ledger.json, the three
      storage keys, one function per module): trial 1 needed Claude to write it. 3 goal fixes: who converts
      Decimal <-> str (storage), load's empty shape ({} -> the three empty keys), the missing ledger/__main__.py.
   b. **Test drafts: 6 of 6 usable**, 2 changed: categorize was called with the description string although the plan
      says categorize(transaction, rules) (a draft disagreeing with its own plan - check drafts' calls against the
      plan's signatures in code), and duplicates inside one import were dropped (a judgement call; the goal only
      forbids duplicates of what the ledger holds). Expected values were right everywhere (trial 1: 8 wrong).
   d. **Run: 6 tasks, 6 attempts, all passed on the first try** (trial 1 round 1: 10 tasks with many retries and
      Claude's help; trial 2: 9 attempts for 6). 111 tests. The CLI works end to end on a real-looking export:
      in-file duplicates kept, re-import adds 0, food 94.35, balance 1705.65, "Over budget: food by 14.35".
   e. **What a frontier model would have added and nobody asked for:** error handling. A missing file, an amount
      "abc" or a budget "lots" end in a traceback; "report 2026-13" is accepted. Lesson candidate: a command-line
      tool's plan needs a task for bad input (clear message, exit code 1). Small: an unused DEFAULT in storage.py.
   f. **Round 2 (list, rules list/remove, budget list, "1,500.00").** First planning failed 3 times: Swift kept the
      existing test file first whenever it extended a module, and once wrote "After: T004" (a past task id from the
      memory pack); the search did not bring the [plan, cli, errors] lesson for a goal about lists. Fixed in code
      (T131-T134): fix_new_tests adds tests/test_<key>.py in front instead of refusing, past task ids are dropped
      from After, and each role gets all lessons of its tag (plan / tests / code) instead of a search. Re-plan: valid
      at once, and it planned "bad arguments print a clear message and exit code 1" by itself. Drafts 4/4 usable,
      run 4/4 on the first attempt, 178 tests. Running the commands found one bug the tests missed: run returned 1
      but `python -m ledger` exited 0 (__main__ ignored the result) - fixed by T011 with a subprocess test; lesson
      added.
   c. The risky/leaks checks skip drafts whose status is import_error - which is every draft of a new module. Run
      risky_patterns on every written .py draft.

**Trial 4: Orbit, a gravity slingshot puzzle (D:\Strata\Trials\Orbit, 2026-11-19).** JS + node --test, no data model
given (the planner had to define it), memory, lessons, wiki on. Round 1: 6 tasks, 129 tests, all 4 levels' logic
verified headless (a brute-force launch search wins every level). Found:
   a. **Parallel tasks disagreed on shared data again.** physics used planet.pos and a constant G, levels used
      {x, y, r} with no mass; both were planned with no After between them, so neither saw the other's shape. index.html
      loaded "main.js" from the root (src/main.js). Game state rules (when shotsUsed rises, what happens with no
      shots left) were vague. Claude rewrote 5 of 6 goals. The tasks and their order were right. Idea: when two tasks
      both use a shape (planet, level), the planner must write it in a first "contract" task or in both goals - a
      check could look for the same noun in two goals with different field lists.
   b. **Drafts far too long:** game 1,285 lines / 37 tests (cut at the length limit), main 550 lines; the main answer
      came header-less in two ```python blocks. Fixed by T144 (at most 15 tests / 300 lines; the longest block).
   c. **Wrong drafts, by kind:** self-contradiction (reads probe.x, then asserts probe null), arithmetic
      (250 + 7*2 = 364), a test that depends on level data (the 240-step cap test ended early because the probe left
      level 1), and DOM tests of main.js that share the module's state between tests (an open drag, piled-up shots)
      and expect movement from frames whose timestamps do not advance. Triage named the first two exactly. T006 went
      to needs_human 3 times with no triage at all: its last attempt was no_files (Tiel cut off), and triage only
      runs after a test failure - run triage on the last *failed* attempt's output instead.
      Swift's attempt 7 of T006 was right; 3 rounds (10 attempts) were spent on wrong tests.
   d. **A missing After from Claude's own plan edit** (levels' test uses vec.length) failed T003 3 times; triage said
      test_wrong (the test depends on src/vec.js) - right about the cause, wrong about the remedy. Check mechanically:
      a task whose tests import a module another task of the plan creates or changes needs that task in After.
   e. **Bugs the tests missed (found by reading main.js):** after the last level levelIndex = LEVELS.length, so
      main.js reads LEVELS[3].launch and render reads level.field -> the game freezes at the end. Level 3 was the
      easiest (103 winning launches of 6840 vs 69 for level 1). The levels task wrote a "game state" section into
      CONVENTIONS.md before game.js existed (said main.js owns the state; fixed by Claude).
   f. Code quality: game.js copies the whole state by hand 6 times (no spread/helper); render.js sets no colours.
   g. Harness: `stratos reset` failed (Permission denied) while Claude's shell stood in the worktree (known; hit again).

**Trial 4 round 2 (Orbit P002 + a trail fix, T007-T012, 193 tests, 2026-11-19).** End screen and R restart, colours,
launch-direction preview, harder levels and a fourth. The planner saw that the game breaks after the last level and
split the work well; Claude changed 4 of 5 goals (levels must really get harder; restartLevel needs no level; a
preview signature change would have broken old tests, so it became main-only). With T144 all 5 drafts were kept
(13-15 tests, 164-486 lines). Found:
   a. **Old tests pinning old behaviour, 5 times** (trial 1 h again): "exactly 3 levels", LEVELS[2] as the last
      level, one polyline per trail, two fake documents without addEventListener, a launch point pinned at (40,300).
      Triage named 3 of 5 right. The drafts never change existing tests (by design), and coders cannot touch
      tests, so every one needed Claude. Idea: let the test writer propose edits to existing tests that call the
      changed names (code map users), shown for review like a draft.
   b. **The test writer invented data instead of reading it:** "all levels share launch (40,300) and target
      (760,300)" - levels.js said otherwise. Data files (levels) should be in the test writer's pack whole.
   c. **Tuning by numbers is out of reach for a one-shot coder:** T007 (make winning launches strictly decrease)
      failed 4 times; Claude tuned the levels by simulation in ~3 tries (75/52/42/23). A "tune" task kind could let
      the harness run the measuring test after each small change the model proposes (an experiment loop).
   d. **A bug no test or review caught:** drawTrail stroked one growing path after every lineTo (n^2 per frame, old
      segments never faded); found by reading the diff, fixed by T012 with a new test.
   e. The first round's DOM-test lesson held: main_restart was rewritten as pure onKey/currentLevel tests and
      passed on the first try after that (T009 attempt 7 overall, 1 after the rewrite).

**Trial 5: Lumen, a light-and-mirror grid puzzle (D:\Strata\Trials\Lumen, JS, 2026-11-20) - the trial after P1.**
Only a layout in CONVENTIONS.md (no data model). Plan: 5 tasks in the right order (simulate, levels, game, render,
main). Claude changed 4 of 5 goals: the shapes (simulate(level, mirrors), "x,y" keys, lit as an array), each level
carries a `solution` the tests can check, game.js as pure functions over a state (the planner wrote a mutable game
object - Orbit's shared-state lesson), render's drawing contract (CELL, texts below the board), main.js must load
without a document. Drafts: simulate right except 2 invented rules (target on a wall / on the emitter) and a loop
test that needs a mirror on the emitter; **levels designed its own levels in the test comments and pinned them, and
game and render tested against that invented data** (the same root as Orbit's "invented level data": the data file
does not exist when the drafts are written, so the drafts make it up); levels used await in non-async tests; render
pinned a cell size from ctx.width and colour names. 3 of 5 rewritten by Claude, main kept.
The draft checker (experiment-a prompt, Swift) blind on these drafts: right that levels invents data, but with made-up
reasons; flagged all 15 render tests with one meaningless reason; missed simulate's invented rules; one false alarm
in main because it saw only main's goal. -> for P2: the checker needs the whole plan (every goal) and a "data the
tests may assume" section; a test of a module that reads a data file must take its cases from the data (find cells),
or the data task must run (and its file be shown) before the dependent drafts are written.
Run: T001 simulate passed on attempt 3 (its first failure showed "expected: / actual:" with no values: TAP's
multi-line values are still cut - open since trial 1, now with a cost); **T002 levels failed 4 times** (off-board
emitter, a mirror on a target, levels not harder; triage "code_wrong" with the exact reasons) - the second time after
Orbit T007 that a one-shot coder cannot design data that must satisfy numbers; Claude designed the levels with a
solution search (scratchpad lumen_levels.mjs, 0.2 s) and marked T002 done by hand (no `stratos accept` command; and
`drop` would have left T003-T005 waiting forever on a dropped After). T003, T005 first try (Swift); T004 passed on
the first try but the reviewer rejected it as "medium" for calling simulate twice (a nit on a 40-cell board), after
which Tiel broke the tests 3 times and Swift fixed it: 4 attempts and 2 switches for a nit - review severity needs
calibration. Bugs no test caught, found by reading: no grid lines, "Solved!" below the canvas (trial 1 f again: a
won-state layout test was missing), lit listed a target twice, game.js copies inBounds. T006/T007 fixed the first
three on the first try. 54 tests, private repo stratos-trial-lumen.
**P1 measured (report --efficiency):** Lumen first try 5/7, 2.0 attempts per passed task, waste 10.6% (Orbit 4/12,
3.82, 27.8%; tower defense 8/16, 2.94, 21.6%). Preflight refused nothing here (no broken test file or missing After)
and put the base failures in every first prompt. Not a clean A/B: Claude also rewrote 3 of 5 drafts before the run.

**Trial 6: Pantry, a recipe-scaling CLI (D:\Strata\Trials\Pantry, Python, 2026-11-20) - the trial after P2.**
Plan: 6 tasks, right split and order; Claude changed 4 goals and 3 Afters: `convert(amount, from, to, gw)` (a Stratos
name leaked from the memory pack into a trial's API), no pantry/__main__.py (Ledger's lesson missed again, although
LESSONS.md has it), shopping "prints" in a pure module and no return shape, no pantry.json shape; recipe and
scale lacked After units, shopping lacked After scale. Drafts: 2 of 6 kept, 4 changed by Claude: servings 0 accepted
(recipe, scale: would divide by zero), cli called main(["pantry", ...]) with the program name and took scale's
servings as --servings although the goal says `scale <file> <servings>`; no `python -m` exit-code test (added). No
invented data this time (the new "do not assume its contents" rule, or simply a small table - not separable).
**The draft checker (P2) flagged 1 test** (a message-format detail) and none of the 5 real problems: on fresh drafts
it finds arithmetic slips, not interface mismatches with the goal. Keep it advisory; P3 should give it the goal's
command syntax and the signatures the plan names (a check of calls against the plan, Ledger trial b).
Run: first try 3/8, 2.88 attempts per passed task, waste 17.4% (Lumen 5/7, 2.0, 10.6%; Ledger 11/11). Failures were
the code's this time (fraction amounts, the shopping rules, argparse), plus: **the reviewer asked T006 to import from
"pantry_mgmt" - a task key the planner had written into the goal - and the change broke the import** (goals should
name files, not task keys; the reviewer cannot tell them apart); Claude's test list for T007 held T008's new test
(rule 3 broken by Claude again; triage named it exactly: "a separate task"). Running the CLI found 2 bugs the tests
missed: `list` crashed sorting None against a unit, `--servings 4 2` was refused (T007/T008 fixed both). Not merged:
"2 eggs" + "3 eggs" stay two lines - Claude's own goal said lines without a unit are not added up. 88 tests, private
repo stratos-trial-pantry.

**Trial 7: Pantry round 2 (P002: counting, unit aliases, show, --json; 2026-11-20) - the trial after P3.**
The plan critic (Flint) ran live: 11 lines, 3-4 real (JSON needs the tuples turned into dicts, show printed
"ingredient unit amount" unlike list, None vs piece display); 5 were "test files should be tests/test_<module>.py"
(it does not know Stratos's own new-test-file rule - tell it), 2 wrong. Claude applied the 2 clear ones.
**OUTDATED did not fire:** the planner listed the old test files (tests/test_shopping.py ...) as the tasks' own
tests, so old_tests() left them out and no draft got the OUTDATED instruction; 3 old shopping tests pinned "no unit
-> other" and Claude fixed them by hand. Fix: also give the instruction for existing files in task["tests"].
The draft checker flagged 0 of 5 drafts again; the json draft split an unknown unit "oz" off the name (against round
1's rule) - missed by the checker, found by triage's explanation.
Run: T009-T012 passed their tests on the first try (4/4); the reviewer then rejected T012 twice, the second time
wrongly ("best_size used before set" - it is behind a short-circuit `or`), and T013 three times: once wrongly
("missing import json" - it was there) and twice rightly (an attempt padded servings with len(recipes) -
len(recipes) = 0, which no test caught). Both done with `stratos accept` (first real use) after a one-line hand fix
and a new test. T013 also ran without T011's counting: **cli_json lacked After shopping_count** (a behaviour
dependency, not an import, so preflight cannot see it); Claude then fixed the json test wrongly once more (forgot
round 2's counting). Worktree removal failed 3 times with "Permission denied" while Claude's shell had been in it.
Left: `have 6 eggs` needs a unit (round 1's CLI). 159 tests.
Pantry overall: first try 7/13, 3.08 attempts per passed task, waste 18.3%.

**Trial 8: Lumen round 2 (splitters, undo, moves; 2026-11-20) - the trial after P4's first part.**
The critic (Flint) gave 12 lines, 5-6 real (no way to get solvable splitter levels; cellAt rejecting splitters in
main.js; mirrorsLeft redefined; rejected clicks counted as moves; undo of an empty history); Claude also dropped the
planner's levels task (design by numbers, item 16). **OUTDATED fired for the first time:** the undo and moves
drafts named 7 old tests that compare whole states (newGame, nextLevel, restartLevel, onKey) - all right; they now
compare their own fields. It missed one: the round-1 test that pinned a path with a repeated cell, which round 2's
"no repeats" contradicts - so T008 could not pass (3 attempts; triage said code_wrong). The draft checker flagged the
render draft's syntax error 14 times (once per test) and missed game_splitters' syntax error and the loop test's
miscalculation (a "\" mirror the hand trace forgot). **Claude found both bad tests by running the drafts against a
30-line reference simulate** - a differential check, the strongest draft check seen so far (see item 17).
Run: T009-T012 passed their tests on the first try (T008 after the test fixes, on attempt 4). The reviewer rejected
T012 three times, wrongly: "moves rises even on rejected clicks" - every rejection returns early, above the diff
hunk; like T013-a11's import, the reviewer lacks the code around the hunk (item 18). Accepted by hand. Reading the
code found that U was never wired (the plan gave undo to game.js only; the critic missed it): T013 (Swift on
attempt 3, the new 2+2 plan). 116 tests, pushed. Lumen overall: first try 9/13, 2.17 attempts per passed task, waste
8.7%.

**Trial 9: Drift, an ice-sliding puzzle (D:\Strata\Trials\Drift, JS, 2026-11-20) - the trial after P5.** Levels made by
Claude with a search (2 of Claude's 3 hand-made levels were unsolvable - checked before use). Readiness metrics
(user, 2026-11-20: "when can it run alone?"): **goals changed 4 of 5** (the critic named 2 of the 4), drafts: 1 of 5
unusable (grid), the slide draft 14/14 right against Claude's reference, but **3 drafts held a wrong test each** that
cost about 3 attempts apiece: two render tests contradicted each other (background vs board cells), a game test passed
one level without the list of levels, the main draft passed direction names where the others agreed on DIRS values.
Consensus fired on all three and triage then said test_wrong twice, correctly. Also: an inBounds(grid) trap that
both models fell into the same way (a false consensus - 40% of the signal), a totalMoves bug in game.js that only the
main task's test exposed (main could not fix it: T006), and Claude's own goal edit that called `gems` the level's
gems while the game draft used it as the taken Set. Playing headless found **0 bugs** after the fixes (all 4 levels
solved in their fewest moves through the real game). Claude also reset the finished T003 by mistake (the cancelled
command had gone on) and restored it from its commit -> P6 reset guard. Result: first try 2/6, 4.67 attempts per
passed task, waste 31% - the cost was tests and contracts between tasks, not code. 63 tests, private repo.

**Watching and measuring (user, 2026-11-19): dashboard, efficiency, push per P (T145-T153).**
`stratos dashboard` (127.0.0.1:8765): the gateway now writes call_start/switch_start, so the page shows who is
writing which task right now, PolyStrata's live /metrics (phase, generated/max tokens, tok/s), GPU/VRAM/temperature
gauges and history, a task board per project, an event feed and an efficiency panel. The page (stratos/dashboard.html)
was written by Claude; the data side by Stratos. `stratos report --efficiency`: waste by cause (completion tokens only;
the old "wasted tokens" also counted reviewer approvals and prompt tokens: 4.0M vs 0.80M), time split, first try.
First reading (Stratos, all history): 2.15M tokens generated, 37.5% waste (tests_failed 650k, cut_off 66k); of 14.8 h
active, model 48%, **model switches 19% (2.9 h)**, other (tests, git) 33%; first try 83/152 (coder 56/108, coder_hard
27/44), 2.65 attempts per passed task. Orbit: 24.5% waste, first try 4/10. -> item 5 (switch cost) is now the
cheapest measurable win. `stratos push`: refuses with uncommitted changes, off main, failing tests or a secret-looking
added line (`# pragma: allowlist secret` marks deliberate fakes); first real push not done yet (277 commits, public
repo: the user decides).
   Found on the way: the triage reason with an em dash broke log() on a cp949 stdout (fixed in main(): streams replace
   what they cannot encode). Claude's own test lists for tasks again included tests that need another task of the same
   batch (T151 x2, T153 nearly): when tests are added to main while tasks wait, `stratos status` could warn "T151 lists
   tests/test_x.py, changed after the task was added".

0. **Memory system - the central goal (user, 2026-11-19).** Local models are weaker than frontier models; close the
   gap with memory and retrieval, comprehensively (vector DB, RAG, an LLM-written wiki, lessons). Both trials failed
   for missing context, not missing skill: the planner did not know who reads a field (trial 2 a), a test draft did
   not know an earlier task's numbers (trial 2 b), old tests pinned old behaviour (trial 1 h, trial 2 e).
   Layers (each one usable alone, built in this order):
   M1. **Code map** (exact, no model): per function/class/constant its signature and the names it uses (Python ast,
       JS by top-level declarations); `users(name)`, "who uses what" for the planner, and which tests touch a name.
       **M1 done (T101-T106, 2026-11-19).** stratos/codemap.py: scan_python/scan_js (declarations end at their
       brace, top-level code such as node's test(...) calls is a "(top level)" symbol), build, users, uses_summary;
       `stratos plan` shows "WHO USES WHAT". A/B on trial 2's goal at the pre-round-2 commit: the planner now routes
       step.js through towerStats (missed before), plans no empty tasks (2 before), records totalSpent for the refund;
       still changed the hp formula unasked without seeing waves.test.js pins it, and selling does not recompute the
       path - about 2 goal fixes instead of 5 (one sample). Embeddings check (scratchpad embed_eval.py, tower
       defense, 8 expected hits in top 5): jina-v2-base-code 7/8, bge-small 5/8, nomic-Q 3/8; no model found
       step.js:step for "upgraded towers deal more damage" - the code map's users() does, so search must expand
       hits through it.
   M2. **Store + hybrid search**: one SQLite file per project (.stratos/memory.db, stdlib sqlite3) of chunks (code per
       function, tests per test, wiki pages, episodes, lessons, CONVENTIONS sections) with BM25 (own code) and
       embedding vectors (CPU ONNX model via fastembed, cosine in numpy, re-embedded only when a chunk's hash
       changes), fused by reciprocal rank. `stratos memory index|search`.
       **M2 done (T107-T115, 2026-11-19).** memstore.py (SQLite chunks + float32 vectors, tokenize with camelCase
       split and a light stemmer, BM25), embed.py (fastembed, jina-v2-base-code on CPU, models in
       C:\PolyStrata-data\embeddings), memindex.py (a chunk per code map symbol incl. one per JS test(...) call,
       CONVENTIONS sections; re-embeds only changed chunks), memsearch.py (BM25 + cosine fused by RRF, then up to 3
       code + 2 test users per hit from the code map), `stratos memory index|search`. Tower defense: 253 chunks,
       first index 80 s; the three trial-2 queries now find step+towerStats, sellTower, the click handlers.
       Weak spots: on Stratos tests outrank code, and __main__.main is one 400-line chunk (split long symbols into
       windows); the seen-check runs after the cap (fewer than 3 when earlier hits took them). Not yet used by any
       role - that is M5; the next trial comes after M5.
   M3. **Episodes and lessons**: every finished task (goal, files, attempts, failure signatures, review issues,
       triage, resets with their reason) becomes an episode; every human correction (an edited plan vs. the planner's
       text, a rewritten draft vs. the model's answer, a reset reason) is distilled by a local model into a one-line
       lesson with tags. Lessons replace hand-written CONVENTIONS "lessons".
       **M3a done (T116-T117, 2026-11-19).** episodes.py: an "episode" chunk per finished task (goal, files, results,
       failing tests, review, triage, resets) and a "lesson" chunk per person's reset reason; `memory index` adds
       them (Stratos: 143 history chunks, 1090 in all). Search finds T117 for "answer cut off at the length limit",
       but code and tests outrank history in a mixed search: M5 must search per kind. remove_except("lesson")
       would delete M3b's distilled lessons - give those their own kind. Found on the way: index_project embedded
       only its own stale chunks (KeyError on history chunks; fixed by Claude with a test).
       Also seen in M3a: Swift's whole-file answers for __main__.py (499 lines) hit the length limit (T117 no_files
       twice) - big files need edit-style answers or smaller modules.
       **M3b done (T122-T127, 2026-11-19).** LESSONS.md in the Stratos folder (shared by every project, git-tracked)
       holds `- [tags] lesson (source)` lines; memindex indexes them as "guide" chunks; recall puts general lessons and
       people's corrections first and cuts code entries at 1000 characters (A/B 2: code filled the budget and only 2
       lessons fit). `stratos memory learn` asks the reviewer model for one lesson per reset reason not yet learned
       (state learned.json) and appends it. First live run: 32 proposed (26 Stratos, 6 tower defense), Claude kept 8:
       about 6 restated "old tests pin old behaviour", one was the opposite of the real cause (use named regex
       groups), many were vague. Next for the learner: at most 25 words and one concrete action in the prompt,
       duplicates by embedding similarity, and learn from edited plans and rewritten drafts too (keep the planner's
       original tasks in the plan file).
       **Learner step 2 (T140, T143, 2026-11-19):** at most 25 words and one action in the prompt, answers over 30
       words dropped; duplicates also by embedding (cosine >= 0.72: unrelated lessons reach 0.68, paraphrases
       0.65-0.76, so about 2 of 3 restatements are caught); save_plan keeps "original" and learn reads every task a
       person changed, removed or added in an added plan (plan:<pid>:<key>). Not yet: rewritten test drafts.
       A/B 2 (5 runs per variant, with the lessons): mean of parsed plans base 2.4, uses 2.0, memory 3.67, but
       memory had 2 parse failures - both a docs-only CONVENTIONS task without tests, caused by the wording of one
       lesson (reworded). Variance between runs is large (base 1-4): compare means over 5+ runs.
   M4. **LLM wiki**: a page per module written by Tiel from the code map and the code (purpose, data shapes, who uses
       it, invariants, traps), rebuilt when the module's hash changes; a project overview page; hand edits kept.
       **M4 done (T135-T139, 2026-11-19).** wiki.py: Tiel writes .stratos/wiki/<path>.md per code file (Purpose, Data
       shapes, Used by, Invariants, Traps; <= 400 words) from the source and the code map's users; index.json keeps
       the hash of the prompt (source + users) and of the page written, so a page is rewritten when its file or its
       users change and kept when a person edited it. memindex indexes pages as "wiki" chunks; recall puts "MODULE
       NOTES" after the lessons (planner 3, coder 2). `stratos memory wiki [--only ...]`. Stratos: 32 pages in 6 min,
       ~10,500 words. Read by Claude: Purpose and Data shapes mostly right; Traps partly invented ("fix_new_tests does
       not check existence" - it does) -> the prompt now says "only what a line of the code shows, else none found".
       **Found on the way (T138):** codemap.users matched by name only, so plan.py's page said diagnose/triage/wiki use
       plan.build_messages (they have their own). Now build records each file's imports and users(cmap, name, path)
       counts only files that import the defining module; uses_summary, memsearch and wiki pass the path. Known loss:
       methods called on an object passed in (store.get in recall) without importing its module are no longer users.
       **Wiki A/B (scratchpad mem_eval_wiki.py, trial 2's goal at 89feb4f, 5 plans each, same 12,000 budget):** first
       read: memory 4.0, wiki 1.8 - 3 of 5 wiki plans failed to parse, all on form: notes in list items ("tests/x
       (existing, add level checks)", the comma split it), the new test file in Files too, a file both changed and
       "protected" for part of it. T141/T143 read these (notes go into the goal, test files leave Files, Files wins
       over Protected). Rescored with the new parser: memory [3,4,4,5,4] 4.0, wiki [4,6,5,4,4] 4.6, no parse failures
       left. The wiki plans named old tests to update more often (wiki-2: "tests/towers.test.js (existing, updated
       for level/totalSpent)"). Still nobody: boss_rule_safe 0/10. Next: an overview page; wiki pages for the test
       writer (it sees only the pack's code); notes on old tests that need changes should reach the test drafts.
   M5. **Retrieval agent + context packs**: hybrid search + code-map expansion (users of the symbols a goal names),
       then a fast local model picks the ids that matter in short calls (reading is cheap, writing is not); a
       budgeted pack per role (planner, test writer, coder, reviewer, triage).
       **M5 first step done (T118-T120, 2026-11-19).** memsearch kinds filter; recall.pack builds a budgeted pack
       per kind (code 6, tests 4, conventions 3, past tasks 3, lessons 5); `stratos plan` adds it when memory.db
       exists (config.MEMORY). One A/B run on trial 2's goal: as good as the code map alone on step/levels, no
       unasked hp change, preview consistent, but it invented a towerId and still missed "wave 0" and the path
       recompute. Next: the test writer, the coder and the reviewer get packs too; a fast model picks from a larger
       candidate set (M5b); memsearch rebuilds an id set per vector in the kinds filter (quadratic, fine at ~1000).
       **First measured A/B (scratchpad mem_eval.py, 2026-11-19):** trial 2's goal at 89feb4f, 3 plans per variant,
       6 checks from Claude's hand fixes. Mean (a parse failure = 0): base 0.67, +code map 2.0, +code map+memory
       2.67; parsed plans scored base 2, uses 3/3, memory 4/4. Only memory planned "selling recomputes the path"
       (2/2); nobody caught "wave 0 / the old wave test" or "room on the canvas" - those are lessons from earlier
       trials, which the eval checkout's memory does not hold: cross-project lessons are the next step (M3b).
       4 of 9 plans failed on "After: none" -> T121 drops none-words in list fields.
   M6. **Measure**: plan_eval A/B with and without memory on fixed goals (trial 2's goal has a known answer: the
       5 goal fixes Claude made), then trial 3 on a new project.
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

11. **No way to drop a task.** T142 (a cleanup Tiel failed 3 times on the 470-line plan.py: the reviewer rightly
   said the comments were not put back) stays needs_human; its work went into T143. Add `stratos drop TID --reason`.
12. **Old fakes break when a signature grows** (T136 test_memory_refresh, T140 test_cli_memory): Claude's test lists
   for a task miss other tests that fake the changed function. Before `add`, grep tests/ for fakes of the changed
   names (monkeypatch.setattr(<module>, "<name>", ...)) and put those files into --tests.
13. **TAP multi-line expected/actual are cut** (Lumen T001 and the simulate_unique test: "expected: / actual:" with
   nothing after): keep the indented lines after those keys in verify.summarize_output. Cheap; first in P2.
14. **Review severity:** "medium" for a repeated pure call on a tiny board sent Lumen T004 back (4 attempts, 2
   switches). Tell the reviewer that performance notes are "low" unless the goal is about speed.
15. **Done by a person:** no `stratos accept TID` (Claude edited tasks.json for Lumen T002); `drop` does not release
   tasks whose After names the dropped task.
  **P5 built (T175-T176, 783 tests, 2026-11-20):** consensus - when two models wrote their own code and both
  failed the same tests, the task records it and triage is told (history: 15 of 25 such tasks were later reset as
  test-wrong, vs 3 of 12 without a shared test; 15 of all 20 test-wrong resets had the signal) - a free,
  after-the-fact version of item 17; the reviewer sees short changed files whole (< 300 lines), imports of the
  longer ones. Experiment (c) again with that context: **Qwen3.6 10/10 and 10/10** (was 9/9; T012-a1's real missing
  import is now caught, the false blocks stay gone). Both tasks passed on the first try.
  **P6 built (T177-T181, 798 tests, 2026-11-20) - guards against Claude's own slips** (user: "too many small
  mistakes"): lint.py runs ruff (installed in Stratos's venv) on the Python files a model writes - undefined names
  (F821-F823) stop an attempt before the tests, unused imports (F401) are removed after they pass and the tests run
  again (history: 12 NameError attempts, 5 of 43 review rejections about unused code; ruff found 5 such spots in
  Stratos itself); `reset` refuses a done task without --force; `stratos add` warns about a test list that holds
  another waiting task's new test, old tests that import the changed files, missing or broken test files. Plus a
  Claude Code PostToolUse hook (D:\Strata\.claude) that syntax-checks every .py/.js file Claude writes, and
  CLAUDE.md rule 14. Notes: a lint fix that breaks the tests now fails the attempt - it should restore the files
  and keep the pass; the suite slowed from ~55 s to ~70 s (add tests build the real code map); JS has no linter
  (no npm in trials).
  **P7 built (T182-T188, 812 tests, 2026-11-20):** refcheck.py - after plan-tests writes the drafts, Tiel writes
  each task's files from the goal alone (never the tests), the references build on each other in plan order, and
  the drafts run against them: some failing -> those tests are flagged; most failing -> "the goal may leave the
  interface open". Experiment (scratchpad ref_eval.py, 4 cases, 5 known wrong tests, Tiel and Swift x2): every
  wrong test failed on every reference (20/20); Drift slide failed 14/14 every time = the interface gap Claude
  had fixed by hand. The model draft checker is now off by default. Also: a lint fix that breaks the tests is
  undone, Stratos itself is pyflakes-clean (a test keeps it so). Run notes: T185 (3 files with __main__.py) failed
  6 times on cut-off/partial answers - dropped and split (T186/T187); preflight refused T186 at once for a
  missing After (its second real catch); T184 and T188 failed on Claude's goal text (tmp/"p" on mkdtemp's str)
  and on old tests Claude had not updated (an exact-dict assert, a fake without the new argument) - consensus
  and triage named each one. add's old-test warning lists dozens of files for config.py/loop.py tasks, so the one
  that mattered was missed: show only the tests that call the changed names (code map), cap the list, skip tasks
  in After. Not done: table-driven test cases (refcheck gives their main gain on normal test files).
  **P8 built (T189-T190, 824 tests, 2026-11-20): edit blocks** (user: whole-file rewrites overflow and break working
  code). Experiment (scratchpad edit_eval.py, 10 past tasks on 580-680 line files, one run each): whole files 7/10
  (Tiel 0/3: two cut at its 6000-token limit), SEARCH/REPLACE blocks 8/10 with 0 SEARCH mismatches, ~6.6x fewer
  tokens (97k -> 14.7k), ~3.3x faster (1180 s -> 356 s). Now the coder answers existing files with SEARCH/REPLACE
  blocks and new ones whole; patch.render_edits applies them in memory and the result goes through the same
  checks (dropped definitions, protected files, syntax, lint, tests); a SEARCH found 0 or 2+ times gives
  "edit_mismatch" with the closest line. Nit: an edit_mismatch skips the cut-off note. Next: measure on a
  trial round that changes existing code; the reviewer's diffs should shrink too.
  **Trial 10: Pantry round 3 (2026-11-20, P7+P8 on a project that changes existing code; 3 tasks: `;` comments,
  have/used without a unit, list --markdown; 200 tests, pushed).** Edit blocks: Swift changed the 200-line cli.py in
  553-2550 tokens per answer (whole files took 6-9k before), 0 SEARCH mismatches by Swift; Tiel ignored the format
  twice (half a file -> dropped_defs, then a syntax error) - partly the old "write each file completely" hints.
  Planner goals fixed 2 of 3; drafts: 2 wrong tests in list_markdown - the "2 oz spice" unit trap a third time, now
  a data rule in Pantry's CONVENTIONS.md. New problems, each fixed through Stratos:
  - refcheck flagged all 3 tasks wrongly: the reference writer never saw the files it changed and rewrote cli.py
    whole (T191: it sees them and answers with edit blocks; answers saved as answers/<plan>-<key>-reference.md).
    Even then Tiel broke its own edit blocks (several "=======") -> Swift writes references, thinking budget 3000,
    a reference that does not compile is an error, not a flag (T194). Re-run on the round-3 drafts
    (scratchpad recheck_pantry3.py): recipe_comments agree 0/13, cli_count agree 0/14, list_markdown flagged exactly
    the 2 tests Claude had found wrong by hand. **First clean refcheck result on a change round.**
  - lint vs reviewer: lint blamed an old undefined name in a function the task did not touch; the coder defined it
    to pass, the reviewer rejected that as out of scope 3 times (T015 accepted by hand). T192: lint only blames
    errors the answer adds (compared without row:col); the hints mention edit blocks.
  - a failed edit attempt is thrown away, but the next answer sent only the fix (an import) as if the edits had
    stayed (T192 attempt 2). T193: the retry message says the attempt was not kept and to send every change again.
  - Claude's mistakes: an old lint fake (same errors for any call) failed T192 once; heredoc escapes broke a test
    file twice (the hook and py_compile caught both at once).
  Efficiency (Stratos, all tasks): first try 105/194, 2.62 attempts per passed task, waste 40.2%.
  Nits: refcheck.py has two `from stratos import` lines (T194); addcheck still lists ~40 old tests for a config.py
  task (cap it / only tests that use the changed names).
17. **Differential draft check** (trial 8): for a task whose rules can be computed (simulate, scoring, parsing), have
   a second model write a small independent reference implementation from the goal alone, run the drafted tests
   against it, and flag the tests that fail on it (the test or the reference is wrong - a person decides). Claude's
   own 30-line reference found the 2 bad tests that the model checker missed. Measure on trials 1, 4, 5, 8.
18. **Reviewer context** (trial 8 T012, trial 7 T013-a11): the reviewer judges hunks without the code around them;
   2 of the 3 remaining false blocks came from that. Show the whole new file when it is short (< 300 lines), else the
   changed functions whole (code map spans).
16. **Design-by-numbers tasks** (Orbit T007, Lumen T002): a one-shot coder cannot design data that must satisfy a
   measurable rule. A "search" task kind: the model writes a small generator/solver, the harness runs it and keeps
   its output as the data file.

## Done

- Harness (2026-11-18): a FILE header alone in its own fence no longer leaves a fence line in the file (Tiel, T075/T076);
  a dependency already merged into HEAD is not a base for the dependent task's copy (T076 missed main's fixes).
- T071-T076: conventions, text planning read by code, AgentWorld fallback, plan_parse telemetry, stricter parse_plan.

- T061-T070 planner: plan, plan-add, plan-tests; prompt rules, signatures, files/protected overlap refused, goal-file
  errors, raw planner answers saved (.stratos/answers/plan-<call_id>.md), check_draft timeout and UTF-8.

- T054-T056 reasoning budget (Gateway, loop, replay, report keys). T057-T060 diagnosis A/B.
- coder_hard: Flint -> Qwen3.8-Flash-Next Coder -> Swift 1.5 IQ2_XS with a 3000-token budget (replay on six hard tasks).
- AgentWorld as a decision model: rejected (offline A/B no better than always choosing Tiel).
