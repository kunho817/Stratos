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

## Done

- Harness (2026-11-18): a FILE header alone in its own fence no longer leaves a fence line in the file (Tiel, T075/T076);
  a dependency already merged into HEAD is not a base for the dependent task's copy (T076 missed main's fixes).
- T071-T076: conventions, text planning read by code, AgentWorld fallback, plan_parse telemetry, stricter parse_plan.

- T061-T070 planner: plan, plan-add, plan-tests; prompt rules, signatures, files/protected overlap refused, goal-file
  errors, raw planner answers saved (.stratos/answers/plan-<call_id>.md), check_draft timeout and UTF-8.

- T054-T056 reasoning budget (Gateway, loop, replay, report keys). T057-T060 diagnosis A/B.
- coder_hard: Flint -> Qwen3.8-Flash-Next Coder -> Swift 1.5 IQ2_XS with a 3000-token budget (replay on six hard tasks).
- AgentWorld as a decision model: rejected (offline A/B no better than always choosing Tiel).
