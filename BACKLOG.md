# Stratos backlog

The list of improvements to Stratos itself, kept by Claude and the user. Each session: read this first, pick the top
open item (or what the user asks for), and update it at the end. Evidence comes from `stratos report`,
`stratos report --replay` and the diffs read while verifying. Finished items move to "Done" with the task ids.

Stages (2026-11-18): 0 skeleton, 1 self-development loop, 2 measurement and model choice: done. 3 decision layer:
partly (rules v1, Jev shadow, diagnosis A/B). 4 autonomy (planning, tests, merging): planner and test drafts built, quality not yet good enough to skip review.
5 other projects (a small Python project, then Unity/Unreal): not started.

## Open (top first)

**P029 and the trial 21 follow-up (2026-11-24; T335-T344 in Stratos, T020-T022 in Current).** Current: the duplicate levels (rr) fixed - retries use makeRng(seed * 100 + attempt), the private makeRng copy is gone, every level needs at least 2 clicks; Claude's check: 0 equal start grids, 0 equal solved grids, minimum 2 clicks, 178 tests x3; pushed. Stratos P029 done: (ss, new) second_opinion kept a second check's 'error' and lost the first flag (P003 t2 showed 'reference: error') - now keeps the first result; (qq) the repair round logs why it changed nothing (writer failed / no test file in the answer / <path> gave <status>); (pp) loop._judge refuses JS test files that call names they never import or define (_unbound_test_lines); (nn) facts keeps both programs and their errors (<plan>-a.py, -b.py, -a-error.txt, -b-error.txt; run_program_full) and STRATOS_FACTS_B picks the role for program B (default coder) - next facts run: read B's error, then try STRATOS_FACTS_B=coder_hard. 1772 tests x3, ruff F clean on the package. Evidence from the drafts: 4 of 5 P029 test files and 2 of 2 P003 files had wrong tests; Claude's reference implementation found every one, the second opinion flagged most of them, and the repair round fixed none. Kinds: (a) a test of a LATER task's behaviour inside an earlier task's file (P003 t1 checked the click minimum of t2; P029 facts_run_full checked cmd_facts of facts_cmd_save) - twice in one day; (b) a test that runs its own copy of the rule instead of the code; (c) a fake set before a helper that resets it (check_draft in _run); (d) an env variable set with monkeypatch after the module read it at import; (e) a project setting the test needs (WRITABLE_SUFFIXES without .js); (f) the code block text without its final newline. (tt) new idea for (a): give the test writer the later tasks' titles with 'do not test these here', and when both references fail a test that names a later task's file or function, delete it instead of repairing it. Claude's slips: missed the old test tests/test_loop.py::test_flat (nesting depth of _judge) before adding the JS check (rule 14 again; fixed by T344), and merged the P029 branches into main before running the full suite - next time merge into a scratch branch first.

**Trial 21: Current grows to 50 generated levels (JavaScript; delegation; private repo stratos-trial-current, 159 tests, 2026-11-23).** A seeded generator (path tree from the spring, tiles from the tree's sides, scramble only pipe tiles); Claude played all 50: sizes 3x3..7x7, 1..5 flowers, one spring, none won at the start, every solution wins, same seed same level (level 8 needs one click). First real use of the thinking aids: the second opinion flagged the right tests every time (8 wrong tests over P025-P028 and the trial), and its repair round fixed one by itself (a hand-computed mulberry32 value 0.259 -> the real 0.601). The facts command: program A tabulated the tile rules correctly (67 facts, checked by Claude) once the rules were in the plan goal; program B (Tiel) failed both times - (nn) save B's program and error, and try Swift for B. Wrong tests still met: hand traces of a fake rng (call order not fixed by the goal), a helper that left the pipe cells out of a tree (twice), a diagonal 'neighbour', (0 - 3) mod 4 written as 3, a fake DOM that made a new element per lookup (the coder then added a cache that broke the real page - caught by the review). Harness gaps fixed on the way (P027, P028): the facts disagreement listed equal keys; the partial-file guard refused an intended rewrite (new task field replace / --replace); JS unbound false alarms on of, import() and regular expressions. Still open: (pp) run js_unbound_calls on test files a task writes (a test fix used makeRng without importing it and only the review saw it); (qq) when both references fail a test and the repair keeps failing check_draft (the false alarm blocked it once), say so in the log. User play review: some levels look the same. Claude's check: 22 of the 50 are exact copies of a neighbour (24-28 and 46-50 are one level each; 19-20, 22-23, 31-32, 33-35, 36-37, 38-39, 41-42, 43-44). Cause is in Claude's goal, not the coder: 'try again with the next seed value' makes level i retry with seed 1000+i+1, the base seed of level i+1, so neighbours that fail buildTree land on the same seed; the walk fails often on the bigger boards. Neither the goal's checklist nor Claude's 50-level check asked for different levels - (rr) a level set needs a 'no two levels equal' check, and retries must use a seed space no other level uses (for example seed*1000+attempt); also lower the failure rate (walk that backtracks).

**Thinking aids by execution, P024-P026 (delegation; T311-T326, 1639 tests, 2026-11-23).** Done: `stratos facts <plan>` - a program from the reference writer turns the plan's rules into JSON facts, the coder model writes a second program for the same keys, and only when both print the same values are they added to every goal as WORKED FACTS (facts.py); a second reference (the coder model) when the first flags tests: tests both fail are 'suspect', logged and repaired once by the test writer (plantests.second_opinion); refcheck results carry the test output; JS drafts that call names they never import or define are 'unbound' (comments, strings, method shorthand, getters/setters are skipped: 0 false alarms on Current's 6 test files, the real slip caught); a test-fix task whose test file is not in its copy stops (loop.missing_test_files); the dashboard try path uses is_relative_to. Evidence the second reference works: on its first real use it flagged 3 tests of P025 that were wrong (an answers folder never made, a fake gateway without the repair answer), and 1 of P026 that asked more than the goal. Still open: (jj) suite_leaks calls a draft 'leaking' into old tests that already failed before it (5 false alarms in P024-P026) - compare with a run without the draft; (kk) the repair round has not repaired anything yet (its rewrites were not needed or not attempted) - watch it in the next trial; (ll) test writers still do head math (the last 4000 of 5000 characters 'keep 1000 s'): facts help only for rules in the plan goal. Claude's slips: an old command-list test and a two-calls-only structure test missed before adding tasks (rule 14), and a reset that broke a copy because Claude's shell sat in it.

**Trial 20: Current (JavaScript, canvas pipe puzzle, graphical; delegation round 2; private repo stratos-trial-current, 76 tests, 2026-11-23).** 5 tasks, all written by Stratos; the user reviews the page. Claude's hand: the plan (a circular order game <-> levels, the level check, SHARED SHAPES), goal notes and test-fix goals. Findings: (ee) a JS test draft that never imported the names it tests passed plan-tests (node --check only) - add a no-undef style check; (ff) spatial slips of the test writer, again and again: a corner's rotation, a spring at rotation 0 sending water south, row 1 -> row 0 called south, a flower 'above' the spring written in one row - what cured them was putting the worked OPENINGS TABLE and fixed GRID DIRECTIONS into every goal (the water redraft then passed 15/15 on Claude's reference); a derived table in the goal beats a rule the model must apply in its head - consider generating such tables in the planner; (gg) level design: the coders' solutions clicked flowers until the goal gave a METHOD (write the solved grid, scramble pipe tiles by k, click each k times) - Swift then passed; the levels are tiny and easy (level 1 is won after one click: Claude's own example scrambled a symmetric straight by 3); (hh) Claude's slips: a check test whose code was not in the task's base, and a redraft left uncommitted (the test-fix task then wrote a jest file from nothing) - a test-fix task whose file is missing in its copy should stop, not write a new file; (ii) the dashboard's static try checks the path with a string prefix (a sibling folder named like the repo plus more letters would pass) - use Path.is_relative_to.

**Weakness fixes after trial 19 (delegation; T301-T310, 1472 tests, 2026-11-23).** Done: (z) a test file is cut before a "FILE: " line the test writer added; (y) check_draft uses verify.syntax_errors (a SyntaxWarning is a syntax error); (cc) TEST_SYSTEM tells how to monkeypatch and to write real files; (aa) the preflight counts "No module named" only on Python's own error lines; (bb) checker.check drops pyright's inferred-type rules (CHECK_IGNORE_RULES); (dd) the planner prompts ask for a METHOD line in the goal of an algorithm task. Left: (f) the files-less message (two broken drafts in a row; dropped). Notes: the preflight fix was itself refused by the bug it fixes (run with STRATOS_PREFLIGHT=0, as for P022); the METHOD task's coder was right three rounds running - _RULES is a slice of SYSTEM, so one edit covers TEXT_SYSTEM too - and the reviewer, seeing only the diff, kept asking for a second edit (a review needs the code a diff relies on, not only the diff); Claude missed an old equality test (TEST_SYSTEM == system_prompt(...)) and once wrote a note that contradicted the task's own tests; two goal-note scripts did not run (quotes, then no PYTHONPATH).

**Trial 19: Transit, an earliest-arrival train journey finder (D:\Strata\Trials\Transit, Python, 2026-11-23) - delegation round 2, NO exception: Claude wrote only setup, goals, plan edits and commands.** 4 tasks done, 60 tests; the final review by hand on two tricky timetables: the transfer rule (a 4-minute change refused, exactly 5 allowed), no transfer time before the first boarding, staying on one train, the tie by train id, no journey, same station, JSON, the error lines (blank lines counted) - all right; flaw: the output has no final newline. First try 2/4, 9.0 attempts per task (the finder took 25), waste 37.9%. Time - the first full breakdown: model 2244 s, switches 872 s, upkeep 207 s, memory 81 s, check 53 s, tests 43 s, preflight 11 s, idle 278 s, OTHER 0 s of 3692 s: the "other" is fully explained now. Log:
1. setup (Claude): stratos.toml, tests/test_example.py, .gitignore, git init.
2. plan P001: 4 tasks; the critic said the shapes between tasks were open. Claude (plan edit, allowed): one SHARED SHAPES block (functions, data shapes, int minutes) in every task goal.
3. Drafts: finder and output tests right (references wrong); parse pinned reason texts the goal never gave -> Claude put the reasons into the goal; cli monkeypatched "builtins","open" the wrong way (all 15 fail) -> draft discarded, goal says to use real files in tmp_path, redraft.
4. Transit T001 refused by preflight before any attempt: "module transit not installed" - git keeps no empty folder, so the package the task writes did not exist. Stratos weakness -> a Stratos task on itself (P022), no hand edit (round 2).
5. T300 (the preflight fix) was itself refused by preflight: its new test prints a fake "No module named transit.parse", and preflight reads test output for missing modules. Weakness (aa): preflight takes any such text in the test output for a real import error. Claude (a command, allowed): STRATOS_PREFLIGHT=0 for this run.
6. After the preflight fix: T001 rejected by review 3 rounds - the reviewer was RIGHT each time (a raw ValueError from a stop time, the increasing-times check reset on every token after the first train, a bare train line) - bugs the drafted tests did not cover; the coder fixed one and made another each round. Claude: the three rules into the goal.
7. T001 done (the three review rules). T002 (finder) failed with both models: triage code_wrong (transfer time applied to the first boarding). Claude: a search method in the goal (states ordered by arrival, rides, train ids; no transfer before the first boarding).
8. T002 with the method: the static checker blocked 3 attempts - Claude's method pushed states holding None on the heap (None vs str when earlier fields tie: a real runtime risk). Claude corrected the method (heap of comparable items + a seq counter, states in a dict).
9. T002 again blocked by the checker 4 times: the models still put None in heap items, and pyright inferred narrow types from first values (false positives on untyped containers). Weakness (bb): the checker is too strict for unannotated code. Claude: exact annotations in the goal.
11. Claude's slip: the stratos.toml edit to turn the checker off did not apply (CRLF line endings, the replace found nothing) and Claude reported it as done; the finder passed with the checker on, at attempt 25.
**What round 2 shows:** without hand edits Stratos still finished, and it fixed its own preflight (P022) on the way. Where it stalled, the cure was always a goal: the shapes shared between tasks, the exact error texts, the review's three findings, a search method (Claude's first method itself had a bug the checker found). The reviewer now finds real bugs the tests miss (three in the parser). Queue: (aa) preflight reads fake error text in test output as real; (bb) pyright is too strict for unannotated code (narrow inferred container types); (cc) the test writer misused monkeypatch ("builtins", "open"); (dd) a hard algorithm needs a method in the goal - consider a planner step that writes one.

**The flaky test is fixed (delegation; T298, 1391 tests, 2026-11-23).** tests/test_dashboard_try.py::test_server failed now and then with ConnectionAbortedError (WinError 10053): dashboard do_POST answered 403/404/400 without reading the request body, and Windows aborts a connection the server closes while the client still sends. do_POST now reads the body first, every error answer has Content-Length: 0, and a body that is not JSON answers 400. Before: 1 of 6 push-like runs (-n auto) failed; after: 9 of 9 passed. The 60 s TRY_TIMEOUT_S was not the cause (Claude's first guess). The first draft was wrong twice (it expected 404 before the header's 403); stating the existing order of checks in the goal fixed the redraft.

**Work order 6 (user, 2026-11-22: "add the retry policy, then the rest in order").** From the Tiel analysis (622 coder attempts over Stratos and 18 trials): Tiel passes 34% of attempts (Swift 50%), 48% of first attempts (Swift 61%), but at 19 s and ~1.5k tokens per call (Swift 61 s, ~4.8k) a pass costs ~56 s against ~123 s. Of Tiel's 295 test failures 75% are wrong values (logic), 9% names, 5% types; ~40% of them (117) were on tasks a person later found had a wrong test (85), goal (23) or harness bug (9). no_files 8%: half cut off at the length limit, half no FILE block. Swift passed 92 of the 104 tasks Tiel could not; 16% of Tiel's passes were rejected by review. Tiel tries in a row: 1st 40%, 2nd 24%, 3rd 14% - the policy already gives Tiel 2 tries, the 3rd-in-a-row tries come from a new round (after a review rejection or a reset) that starts with Tiel again. Order:
1. Retry policy: **no change needed** - all 43 third-Tiel-tries-in-a-row are from 11-16..11-20, before P4 set Tiel to 2 tries, all straight on (no review between); none since. Claude's guess (new rounds) was wrong.
2. Weakness group 3 (checks): (i) mutate only the lines the reference changed; (s) a budget for refcheck's prompt; (x) addcheck warns about old tests that hold a literal of the text being changed or fake the changed function; (w) a test-fix task can run its own test; (f) a plan with a files-less task is asked again automatically; (g) let the coder check its own data (play the solution) before answering.
3. Go and the flaky test: (p) Go tests in any folder by suffix; (t) "is not in std" as missing_import; (n) a tool prefix (vet.exe: ) in checker lines; (u) chained references in a typed language; (h) the CASES path guard; (l) test_dashboard_try::test_server.
4. Time "other" (38% of active time; tests and checks are only 2%): time upkeep (memory, wiki), planning, critique, git.
5. The design doc: P20-P23 and the weakness groups.
6. A verification trial after these (consider no exception at all - the user's next delegation step).
7. Later: C# reinforcement (reference quality, xUnit cases), test cleanup step 2 (one scripted fake gateway). On hold (user): memory packs, Jev; perception in a new session.

**Work order 5 (user, 2026-11-21, "진행"): first a cleanup of Stratos's own tests (user: "tidy what can be tidied"):
189 files, 16,150 lines, 944 tests; 29 different FakeGateway classes, 9 FakeTelemetry, 15 inline `git init`s, 36
files with 1-2 tests (one file per task). Then P20 language adapters (one place per language for test command,
output reading, syntax/build check, scoping; split __main__ and report), P21 test strength (mutation score for
drafts, stale-test finder), P22 judging (reviewer's false blocks, the flaky push test, "other" time measured), P23
Go + C# follow-ups. Memory packs and Jev stay on hold.
  **Done 2026-11-21:** tests merged one file per module (187 -> 134 files, the same 944 tests, collected names
  identical; scratchpad merge_tests.py, strict: no name clash incl. helpers imported from other test files).
  P20: stratos/langs.py (T236-T238: Runner/Pytest/NodeTest/Dotnet - test_cmd, with_paths, scope,
  missing_import, child_env; verify/checker/plantests/refcheck name no runner now; checked on Settle and
  Lantern for real) and __main__ as one function per command + COMMANDS (T239). 965 tests.
  Found: (a) **checker vs reviewer**: an untyped `parser` made pyright say "possibly unbound" after
  parser.error(); Swift added `raise SystemExit(2)`, the reviewer rejected it as dead code - 3 rounds (fixed in
  the goal: annotate the parameter). P22: when a check_error fix is what the review blocks, the review must see
  why the line is there. (b) the last T239 review was `review_unparsed` and counted as approval - P22 too.
  (c) reset failed 3 times: Claude's shell cwd sat in the task folder; gitops now treats the emptied folder as
  removed. (d) Claude's slips: a too-strict test (T237), 3 old tests reading getsource(cli._main) not updated
  before add (addcheck warned "uses main" generically; it cannot see getsource), `&& tail` hid a test failure
  again. Left for later: report.py split (636 lines of functions, not a chain - low value), test cleanup step
  2 (40 FakeGateway variants in 38 files -> one scripted fake).
  **P21 done (T240-T242, 985 tests):** stratos/mutate.py (small bugs by rule: spaced comparisons, ==/!=, +/-,
  and/or, &&/||, true/false, integer+1; strings, comments, docstrings left alone; 12 spread evenly), refcheck
  scores an "agree" draft on them (non-building mutants not counted, a timeout counts as caught) and plan-tests
  logs "caught k of n" plus "weak tests" below 60%; addcheck names old tests that read a changed file's source
  text. Measured on finished trial code: Lantern board 12/12, solver 11/12 (the survivor only loops longer - an
  equivalent mutant), the placeholder example.test.js 0/12 (the control); Settle Split 6/6, Transfers 7/12 -
  **the tie-break (equal balances by name) is untested**, a real gap the 75 passing tests hid. Cost: 3-4 s per
  py/js file, ~110 s per C# file (a build per mutant).
  **The reviewer is now the worst judge.** T240: 6 answers that passed the tests were rejected - first because
  the reviewer saw only the goal sentence, not the test docstring the goal points to (fixed: review.spec_text
  puts it in), then with false claims (" < " inside " <= ", digits in a1.b2) and one right edge case; Claude
  accepted attempt 23 with that fix. P22 first: a review issue must quote the line it is about, and a
  candidate that passes the tests is blocked only by a high issue whose quote is in the diff.
  **P22 done (T243-T248 + Claude's harness fixes, 1014 tests):** a review issue blocks only when its "quote" is a
  line of the diff or the whole changed files (others go into the commit message "not counted"); an unparsed
  review is asked once more, then the task is done but `status` shows [unreviewed]; the second review call is
  guarded like the first. steps.py times tests/check/lint/refcheck/mutation/draft_check and `report
  --efficiency` splits "other" by them (no step events yet: the timing was merged after the runs - look after
  the next trial). Claude's fixes on the way: the reviewer sees the test docstring the goal names
  (review.spec_text); a writer call the server refuses (T245's 8 files made a 125k-token prompt, over Swift's
  131k) ends only that task instead of run-all; `add --after` must name an existing task (T245 waited on
  itself); a refused push names its failing tests (the one-time push failure did not come back in 18 runs,
  idle or two suites at once). Lessons for Claude: keep a task's files small enough for the prompt (8 files was
  too many; split by module), and a task whose tests share a file with later tasks lists test ids, not the file.
  addcheck's "uses <name>" is noisy for common names (check, main: 30+ lines) - rank or drop names defined in
  many modules.

**Timing the "other" time (delegation; T290-T297, 1379 tests, 2026-11-23).** More steps are timed (memory, upkeep, codemap, worktree, git, preflight); commands record start/end events and report --efficiency counts "idle" (active time outside every command: mostly the time Claude reads results between runs - the active sessions only cut at gaps over 10 minutes); config.TIMING (off in conftest; the timing tests turn it on). Numbers come with the next runs. Eight tasks for five rules: three were test fixes, two follow-ups for old tests that read their telemetry exactly. Claude's slips: overwrote a task's after (T291 lost T290), committed a draft plan-tests had called syntax_error, missed test_steps.py and test_timed_steps.py when adding the switch. New weakness (z): the test writer also wrote a FILE block for a non-test file and plan-tests glued it onto the test file.

**Go finishing and the flaky test (delegation; T284-T288, 1352 tests, 2026-11-22).** (p) for "go test" the plan check takes tests in any folder and allows a task's files under test_dir; (t) "is not in std" counts as a missing import; (h) the CASES path of the test writer is guarded; (l) the try runner's limit is dashboard.TRY_TIMEOUT_S (test_server sets 60): the push's three parallel runs can start a Python child slower than 10 s - the likely cause of the one-time failures. (n) DROPPED for now: two drafted tests in a row were wrong (an invalid escape, a missing fixture, then a self-contradiction) - go build works as the checker. Seen at work: a code_wrong diagnosis reached the next attempt by itself (group 2), and the [unreviewed] mark (P22). Claude's goal missed the second plan check for Go (files under test_dir) - the tests were right. New: plan-tests called a draft with an invalid escape "collected" - only the preflight caught it (queue y).

**Weakness fixes, group 3 (delegation; T279-T283, 1300 tests, 2026-11-22).** (i) mutants only on lines the reference wrote (base = the file before it); (s) refcheck's existing files within REF_EXISTING_CHARS = 60000 (as today when all fit; else goal-stem files first, the rest as one line); (x) addcheck names old tests that hold a >= 30-character string literal of a changed .py file, or setattr-fake a goal-named function of it. (w) DROPPED: a deliberate rule in tests/test_loop_edits.py keeps a protected test protected even when listed in files (the model must not rewrite its judge) - Claude missed it before adding; test-fix tasks keep a different check test plus the full run at merge. (f) left: plan already re-asks on an invalid plan, the model repeats the same files-less task. (g) left for the perception work. Two retries: the reviewer was right once (reordered even when all fit), a drafted test was wrong once (its budget equalled the total).

**Weakness fixes, group 2 (delegation; T276-T278, 1264 tests, 2026-11-22).** (v) the review's findings get their own part ("THE TESTS PASSED, BUT A CODE REVIEW FOUND THESE PROBLEMS") on every attempt of the round - before, they were shown as "Test output" on the first attempt only and the next failure replaced them (why Rota's coder ignored the same review three times); (j) a code_wrong triage reason reaches every next attempt ("A DIAGNOSIS OF THE EARLIER ATTEMPTS") - Claude no longer copies it into goals; (m) the reviewer is told the tests exist and are not in the diff. All three drafts agreed with the reference at once (12/12, 12/12, 13/13) and the merge broke no old test: Claude checked before adding which old tests pin the changed text (test_context endswith, test_loop_memory memory-then-failure, test_replay fakes of build_messages) and wrote the placement rules into the goal. One retry: two spaces between two sentences.

**Weakness fixes, group 1 + (k) (delegation; T266-T275, 1227 tests, 2026-11-22).** Done: (e) the test writer (build_messages feature=) and the coder (plan-add appends it) see the whole feature goal; (q) the planner is told "TEST FILES: every test file path starts with <test_dir>/ and ends with <suffix>"; (k) the lint fix leaves files that already had an unused import before the attempt. Six of the ten tasks were test fixes Stratos made for old tests that pin exact prompt text or fake signatures. Log:
1. P015: T267, T268 done first round. T266: the drafted test compared two strings alphabetically to check their order (triage right) - the fix goes to Stratos (T269), T266 after it.
2. T269 (the test fix) failed: Claude gave it T268's new test as its check while T268 was done but not merged - its copy lacked T268's code. Fixed: T267/T268 merged, T269 checks tests/test_plan.py. (A new session began here; the PolyStrata server had stopped and was restarted.)
3. Merging T267/T268 broke 7 old tests that pin the exact planner message and the added goal: those two tasks ran only their new tests (the planner listed nothing else) - rule 14 missed by Claude when reading the plan. Handed to Stratos as one test-fix task. Stratos weakness (w): a task that fixes a test cannot run that test as its check (a listed test is protected, so the write is refused) - the check happens only at Claude's merge run.
4. T270 done and merged. T269 rejected 3 times for imports the harness lint fix removed (weakness k, second time) - note in the goal; (k) goes first in group 2.
5. After merging T266 (and T269, T270): 5 tests failed - T270 put the TEST FILES line at the end because CLAUDE's goal said "at the end" without reading plan.py (it is after PROJECT FILES); T270 never ran its own tests (weakness w) and Claude merged T270 without the full run. New Stratos task with "read the order in plan.py".
6. Two more old tests pinned the exact draft_tests message (stale since T266) - another Stratos test-fix task.
7. T272 blocked by the lint-fix collision (k) a 4th time - goal note; (k) itself planned now.
8. T273 failed on one drafted test whose setup contradicted its own fake checker (FILE_E imports json, the fake flags only os) - triage "unclear"; Claude read it. Test fix to Stratos (T274), T273 after it.
9. T273 merged; 6 old tests broke: their lint.check fakes (lambdas) do not accept codes - the draft's docstring claimed "no existing test becomes outdated". Test fix to Stratos.
**Lessons:** (1) before a task that changes a model prompt, find every old test that pins that prompt's text or fakes the changed function (addcheck sees names, not exact strings or call signatures) - queue (x): addcheck should warn about tests holding a literal of the text being changed and fakes of the changed function; (2) Claude must read the code before writing an expected position into a goal ("at the end" was wrong); (3) a test-fix task cannot run its own test (w), so merge only after the full run.

**Trial 18: Rota, a shift-rota CLI (D:\Strata\Trials\Rota, Go, 2026-11-22) - the second delegation trial and the first Go project.** 5 tasks done (T005 was Stratos fixing a wrong test), 60 tests, the output checked by hand on a sample (fewest-shifts-first, ties by name, off days, max, short counts, physical line numbers, exit codes 0/1/2) - all right; the JSON line has no final newline (minor). First try 1/5, 4.0 attempts, waste 8.0%. Time: model 2213 s, switches 617 s, tests 46 s, check 12 s, draft_check 10 s, refcheck 7 s, other 280 s of 3184 s. Log:
1. setup (Claude): go.mod, stratos.toml, rota/example_test.go.
2. plan invalid: a test outside rota/ - Go keeps tests next to their package, Stratos has one test_dir. Stratos weakness (p): allow tests in any folder (by suffix) for Go. Claude: goal rule 12 (all logic in package rota as Run(...); cmd/rota/main.go only calls it).
3. The planner wrote every test as tests/<name>_test.go despite the goal (its habit from Python/JS). Claude (setup): test_dir = "tests" - Go allows an external test package in tests/ importing rota/rota. Stratos weakness (q): the planner prompt should state the test folder and suffix.
4. All 4 Rota drafts failed to build: they imported "rota" (the path is rota/rota - Claude's confusing setup: module rota with a folder rota), and Go compiles a folder's test files together, so one draft that names something not written yet breaks every task (like .NET). Claude's own rule 1 in P23-B (packages) caused that. Stratos task: GoTest.test_cmd passes the test files. Rota goal: import path stated.
5. P014: the reference writer got HTTP 400 - refcheck shows every source file of the project (all of Stratos), weakness (s): refcheck needs the same kind of budget. T264 was refused 3 times: tests/test_langs_go.py was both a file to change and a test to run (protected) - Claude's plan edit; removed from the tests list (the merge runs it).
6. Rota redraft: still broken - the parse goal had lost the line formats ("worker <name> max <n>"), so the drafts wrote "worker Alice 3" (weakness e again: the plan split drops spec details); and "package rota/rota is not in std" (no code yet) is not taken as import_error - weakness (t): GoTest.missing_import should know it. Claude: pasted the spec's own words for each task into its goal; drafts discarded.
7. Redraft with the spec's words: parse reference agrees 15/15. fill/output/cli references cannot build: each chained reference redeclares types an earlier one made (FilledShift twice) - weakness (u): in a typed language the reference chain collides; the references should only add what is missing. Drafts committed.
8. T001 (parse) rejected 3 times, the reviewer RIGHT each time: the line number counted only content lines (blank/# lines skipped before counting) - the drafted tests did not cover it. The coder got the same review feedback 3 times and did not fix it - weakness (v): review feedback is not acted on. Claude: the rule in the goal.
9. T002 failed with both models; triage said test_wrong and was right (the draft counted carol as 1 when she had 0). The test fix goes to Stratos (T005), T002 after it.
**Queue (p-v):** (p) Go keeps tests next to the code - allow test files in any folder by suffix; (q) the planner prompt must state the test folder and suffix (it wrote tests/... every time); (r) done: GoTest runs the test files, not folders (P014); (s) refcheck shows every source file - it needs a budget like the test writer (HTTP 400 on Stratos itself); (t) GoTest.missing_import: "is not in std" (no code yet); (u) chained references in a typed language redeclare each other's types; (v) the coder did not act on the same review feedback 3 times. And (e) again - the plan split dropped the input formats; pasting the spec's own words per task fixed it at once (parse 15/15): **make plan-add carry the feature goal's text for each task**.

**P23-B Go (delegation; T257-T263, 1172 tests, 2026-11-22).** langs.GoTest (test packages "./<dir>"), Go "--- FAIL: " ids and counts, gofmt syntax check, the checker's Go form, missing_import for undefined/could not import, with_paths keeps go build's ./... (a follow-up plan, P013). Six one-behaviour rules: 4 of 6 drafts agreed with the reference at once (the compound-rule plan P010 had 1 of 5). Checked on a real module: runner, failing ids, counts, gofmt errors, checker (with check_command go build ./...) and missing_import right. Log:
1. Review blocked T260 and T262 for "the goal asks to add tests and the diff has none" - the planner's goals end with "write tests ...", but the tests are drafted separately. Stratos weakness (m): strip the test-writing sentences from a task goal for the coder and reviewer (or tell the reviewer the tests exist). T258: triage right (stripped the line, counted subtests). Claude: goal notes.
2. P23-B merged (T257-T262, 1165 tests). Real Go check (a tiny module): runner, failing ids, counts, gofmt syntax errors, missing_import all right. checker with `go vet` found nothing: vet prefixes "vet.exe: " - Stratos weakness (n); `go build ./...` as check_command works.
3. A plan call once produced nothing usable (the planner's answer was invalid; the second call worked) and Claude's script took the newest old plan - which showed a good thing: P012's kept drafts were now reference-checked (P23-A item 3 at work).
**Queue (m-o):** (m) the planner's task goals end with "write tests ..." - the reviewer blocked two right answers for "no tests in the diff" (the tests are drafted separately): strip those sentences for the coder and the reviewer; (n) `go vet` prefixes "vet.exe: " so the checker reads nothing - accept a tool prefix; (o) done (GoTest.with_paths). Next for Go: a trial project.

**P23-A (Stratos on itself, delegation; T249-T256, 1082 tests, 2026-11-22).** Done: PlanNotFound (a KeyError inside a command is no longer "no such plan"; load_plan fills protected/after/role), a passing answer that changes nothing is done ("no change"), a kept draft gets its reference check, mutation skips a reference file whose stem no test names, a refused test-writer call ends only that task's draft. The old-test budget (OLD_TESTS_CHARS) was Claude's one EXCEPTION edit: plan-tests could not run for tasks on __main__.py or config.py (42/~100 old tests in the prompt, over Swift's context) - not even for the task meant to fix it. Log:
1. plan P010: the planner listed tests/test_cli_plan_add.py and tests/test_cli_plan_tests.py, merged away on 2026-11-21 - it saw stale names (memory/wiki index not refreshed after the test merge?). Claude removed them from the plan (plan edit).
2. plan-tests P010 crashed: the test writer prompt for main_plan_notfound was 109k tokens (__main__.py + three big old test files listed as its tests) -> HTTP 400 ended the whole command (Stratos weakness h: plantests has no guard, like loop had). Claude: plan edit (only the new test file for that task) and deleted the pre-crash draft tests/test_plan_notfound.py so it is redrafted with a reference.
3. The real cause of the 109k prompt: the test writer gets the full text of every old test that imports a changed file - 42 files (~69k tokens) for __main__.py, 26 loop.py, 21 plantests.py, 17 plan.py. Hidden until now because Claude wrote the tests by hand. P010 waits; plan P011 (prompt budget for old tests + HTTP error guard in draft_tests) goes first. Claude: removed P011 task 4 (it changes __main__.py, whose draft would hit the same limit; plan-tests already prints any status) and added "same order when everything fits" to the budget goal (the critic found the contradiction).
4. EXCEPTION (Stratos could not run): P011 plan-tests hit the limit too (config.py has ~100 importers) - the fix could not be drafted by the thing it fixes. Claude wrote the old-test budget by hand (plantests._old_test_parts, goal_names, config.OLD_TESTS_CHARS=48000) with its test; the __main__ prompt went from ~109k to ~28k tokens. The HTTP-error guard stays a Stratos task (P011, one task left).
5. P011 draft: reference agrees 11/11, mutation 0/12 - every mutant was in lines of the big plantests.py the task does not touch. Stratos weakness (i): mutate only the lines the reference changed (the diff against the base), not the whole file.
6. T249 merged (guard on the main test-writer call). Gap: the CASES path call of _ask_test_writer is not guarded (follow-up).
7. P010 drafts: plan_notfound agrees (mutation 4/12 - survivors in untouched lines, weakness i again); main_plan_notfound and loop_no_change tests pin harmless details (import form, a log line) -> Claude added them to the goals; plantests_ref_exists: the test is right (missing tasks skip the reference), the reference was wrong; refcheck_mutation_skip: 5 of 15 disagree, left to the run and triage.
8. P010 run: T250-T252 done first round; T253 and T254 failed with both models, triage said code_wrong and named the exact slip each time. Claude copied the triage reason into the goals and reset. Stratos weakness (j): a triage diagnosis of code_wrong should go into the next attempt by itself (today a person carries it over).
9. Second round of T253/T254 failed again. Claude read them: T253 - the TEST was wrong (a lone FILE block counts as the test file, so "missing" never happens); triage said code_wrong (wrong). T254 - Claude's goal was ambiguous (which language decides the import rules); fixed in the goal. The wrong test goes to Stratos as T255 (a task whose file is the test), T253 after it. Claude's slip: a goal-update script crashed on cp949 printing an em dash, so T254 missed the triage note in round 2.
10. Round 3: T254 failed (both models wrote a stem regex that kept the suffix) -> goal says pathlib.Path(path).stem. T255 could never pass: its test list was the whole file, which holds T253's not-yet-passing tests (Claude's task design) -> T255 dropped, the deletion folded into T253 (its files now include that test file).
11. The real cause of T254's 15 failures: old tests (Claude's, P21) compare the mutation dict exactly, so "always has skipped" could not pass both - rule 14 missed by Claude (addcheck did not warn: the dict shape is not a name). The models went back and forth between the two. Fix: T254 also updates those exact comparisons (its files include the old test file).
12. After merging P010 one old test failed (test_unknown_plan fakes a plain KeyError) - it had been cut from T251's tests by Claude to shrink the prompt. Fixed by a Stratos task.
13. T256 rejected 3 times: the reviewer flagged removed imports (import sys, Path) - removed by the harness lint fix (already unused in the old file), not by the model. Stratos weakness (k): lint.fix should remove only imports the attempt made unused, or tell the reviewer what it removed. Claude: a note in the goal.
**Queue (h-k):** (h) the CASES path of _ask_test_writer is not guarded; (i) mutate only the lines the reference changed, not the whole file (0/12 and 4/12 "weak" on big files were noise); (j) a triage code_wrong reason should reach the next attempt by itself; (k) lint.fix removes imports that were already unused and the reviewer blocks it as unrequested - fix only what the attempt made unused, or tell the reviewer. (l) **the flaky test is found:** a push was refused once more and its new message named tests/test_dashboard_try.py::test_server (a server started in the test - timing or port); fix it as a Stratos task. Lessons for Claude: short rules (one rule per behaviour) work, compound rules fail; check old tests that pin a result's exact shape (addcheck cannot see a dict shape); don't cut old tests out of a task's list without running them at merge (one went stale).

**Trial 17: Sprout, a garden puzzle (D:\Strata\Trials\Sprout, JS, 2026-11-21) - the first DELEGATION trial: Claude edited no code or test file (only setup, goals, commands, reading).** 8 tasks done (T009 dropped), 134 tests, every level's solution wins with the spec's exact scores; first try 7/9, 2.11 attempts, waste 20.3%. Time: model 2094 s, switches 476 s, tests 6 s, mutation 8 s, refcheck 1 s, draft_check 1 s, other 560 s of 3147 s - the timed steps are small for JS; "other" is elsewhere (memory/wiki upkeep, git, planning) - time those next. Interventions:
1. setup (Claude): stratos.toml, package.json, .gitignore, tests/example.test.js, git init.
2. plan goals (Claude, allowed): 4 fixes after plan + critique - plant refused on moisture (not in the spec),
   levels "seeds match plantable cells" (meaningless) -> a winning solution per level played by the test,
   plants' dry-day test belongs to game, main tested without DOM -> src/view.js pure helpers; a stray sentence.
3. Claude's slip: the added "view" task had no "protected" key -> plantests KeyError.
   Stratos weakness (queue as a Stratos task): every KeyError inside plan-tests/plan-add/... is printed as
   "no such plan: P001" (__main__ catches KeyError around the whole call) - it hid the real cause. Also: a plan
   task missing a key should be filled with defaults or refused with its name when the plan is loaded.
4. plan-tests results: moisture/plants drafts had been written by the crashed first run, so the rerun kept them
   ("already exists") and made no reference for them -> the game and levels references could not import
   src/plants.js / newGame ("interface"). Stratos weakness: a kept draft gets no reference, which breaks the
   reference chain for every later task (queue: make the reference even when the draft is kept).
   view: 1 of 15 flagged - the test wanted "#..." colors, the goal said "a CSS color" -> Claude made the goal
   say "#rrggbb" (goal edit, allowed). Claude read game and levels drafts: correct.
   mutation: html 0/3 (only placeholder text changed - harmless), main 0/12 (main's test reads the source as
   text by design) -> mutation on a text-reading test says nothing; queue: skip or mark it when the test does
   not import the module.
5. run-all: T001-T004, T006 done (T001, T003 needed a second round after review). T005 (levels) failed 4 times
   with 2 models: the solutions put plants on springs - a spatial slip (grid row/col reading), the perception
   weakness the user named. Claude's intervention (goal only): how to check each solution cell (grid[row][col]
   is '.', distance rule per kind, harvest day = ripeStage + 1, points add up, a comment per cell).
   Idea: a "check" tool the model can call on its own data (play the solution) before answering - or Stratos
   runs the tests on a draft level data file and feeds the cell-by-cell failure back.
6. T005 passed on attempt 8 after the goal fix; T007 (main) passed first try. 106 tests pass 3 times.
   Claude's check (playing every level's solution with node): all won, but score 30/9 - **src/plants.js has
   sunflower 10 and fern 8 points, the spec says 3 and 2.** The planner's plants goal dropped the numbers
   ("points" without values); the plants test compares with PLANTS[kind].points (cannot see a wrong number);
   that draft came from the crashed run, so no reference and no mutation score ever looked at it.
   Stratos weaknesses: (a) plan split lost spec numbers - the plan critic did not notice; (b) the kept draft
   had no checks (item 4). Levels: no rocks and almost no cacti - valid but dull (spec did not ask more).
   Fix handed to Stratos as plan P002 (goal only). First plan attempt: "plan invalid: files must be a
   non-empty list" - the planner made a tests-only task; the second attempt was valid.
7. T009 (re-check level 3): the passing answer changed nothing and `git commit` failed on the empty change - run-all crashed (Stratos weakness: an answer that changes nothing must be handled). Claude dropped T009 (not needed).
**Queue for Stratos (from this trial):** (a) KeyError shown as "no such plan"; (b) a kept draft gets no reference/mutation; (c) mutation on text-reading tests is noise; (d) a passing answer with no change crashes the commit; (e) the plan split can drop spec numbers - the critic should compare numbers in the feature goal with the task goals; (f) the planner made a tests-only task (no files); (g) spatial slips on grids (levels): let the model check its own data (play the solution) before answering.

**Next theme (user, 2026-11-21): perception - research and design in a NEW session.** The local models (even the
vision ones) perceive the world far worse than frontier models. Start: a spatial occupancy map ("HeightMap") of a
screen - count per cell how many things occupy it, so text overlap (TowerDefense) and overflow are found by
arithmetic, not by eye; later: 3D map perception, and page changes over an animation (web design). The user runs the
research/discussion in a new session (context); Claude's first notes: geometry from a headless browser (DOM boxes,
text rects; Playwright with the installed Edge) or a canvas shim (fillText/measureText), layers (background/text),
violations as test failures and retry feedback, a downsampled ASCII map for the model, an annotated screenshot for
the vision model; pitfalls: intended overlaps, hidden elements, states, viewports. Also from the research: mutation
testing for drafted tests (P21 candidate), several candidates + test selection, property tests in cases; constrained
decoding is out (PolyStrata's engine has no grammar decoder).

**Work order 4 (user, 2026-11-21, after P16): GCM - the user updates Git; other languages approved, engines not
yet; do the open items from trial 15; consider LSP.**
- P17 from trial 15: (a) cases for node:test projects (cases.py writes pytest only; JS drafts flipped board columns
  in 7 of 15 tests); (b) a search task runs the tests of the code its generator calls before the generator (10 of
  14 right generators failed on a wrong solver); (c) review quality in `report`: blocks later overruled by a person
  (accept, or the next try approved with no change asked), per reviewer model - to watch Tiel reviewing its own code.
  **P17 built (T227-T230, 923 tests, 2026-11-21).** cases -> node:test files for JS projects (`stratos cases` by
  the --out suffix, plan-tests by the project language); search failures count for consensus as "(the generator)"
  and triage is told to suspect the code the generator calls (the planned "run the callee's tests first" would not
  have caught Lantern: the solver's own tests passed - they were weak); `report --reviews`: per reviewer model,
  reviews / blocks / blocks a person overruled (Stratos: Qwen3.6 250/40/4; Pantry 22/9/8 - T015's three repeats;
  Tiel so far: Lantern 7/2/1).
- P18 LSP: one diagnostics layer for every language - a small JSON-RPC client (stratos/lsp.py) that starts the
  project's language server (stratos.toml "lsp_command"), opens the files a task wrote, collects
  textDocument/publishDiagnostics and blocks on errors before the tests (like lint today, but types, imports and
  undefined names in any language). Python: pyright (pip), JS: typescript-language-server with checkJs (npm),
  Go: gopls (installed), C#: csharp-ls (dotnet tool), Rust: rust-analyzer (rustup). Measure on past failed
  attempts what it would have caught.
  **P18 built (T231-T232, 931 tests, 2026-11-21) - LSP engines as command-line checkers.** The LSP conversation
  itself (JSON-RPC, open/close, configuration requests) gave no diagnostics in 8 s and hung; the same engines as
  CLIs answer in ~1-4 s (pyright: 42 Stratos files in 3.7 s, 17 errors). checker.py runs stratos.toml's
  check_command ({files} placeholder) and reads both error forms (file:line:col - error: msg / file(line,col): error
  X: msg - pyright, gcc, tsc, dotnet); loop._judge blocks on errors the answer adds (compared without line numbers,
  like lint) as "check_error", before lint and the search generator; Python projects get pyright by default when it
  sits in the venv. Of 440 failed attempts ~80 were static-visible kinds (types, attributes, imports, names); the
  checker matters most for compiled languages (C#: the build is the check). Also: the syntax check now treats a
  SyntaxWarning (invalid escape) as an error - Tiel's checker.py had "\s" in a plain docstring (49 warnings in the
  suite). Claude's slip: a heredoc ate backslashes in a test again (rule 14 says not to).
  **P19 built + trial 16: Settle, a C# expense splitter (D:\Strata\Trials\Settle, .NET 8, 2026-11-21).** Built:
  dotnet test ids ("Failed <name> [..]") and totals ("Total: N" / "Total tests: N"), the coder prompt's example
  path uses the language's extension, tests run as a class filter (FullyQualifiedName~<file stem>) with
  DOTNET_CLI_UI_LANGUAGE=en, drafts checked by `dotnet build`. Settle: 5 tasks done, 75 tests, the CLI's text and
  JSON output right by hand (cent rounding, greedy transfers); first try 2/5, 2.6 attempts, waste 12.9%. Found and
  fixed while running it (all harness, all C#-specific):
  - a .NET test project builds as one unit: later tasks' drafts (types not written yet) broke every build, so no
    test could run -> during a run, <test_dir>/Directory.Build.targets compiles only the task's test files;
  - refcheck read bin/obj .dll files as text; it ran `dotnet test <file>.cs`; it called 0 of 0 tests "agree"
    (now an error, and such a reference is not passed on); a draft naming missing types is import_error, not error;
  - the checker appended .cs paths to `dotnet build` (MSB4025: every attempt failed) and spoke Korean;
  - test_runner read with get (old test fakes without it; Claude had grepped away addcheck's warning about them).
  The checker earned its place on C#: it stopped a build with a stray ``` before the tests. The test writer
  forgot `using Settle.Cli;` (triage named it). Next for C#: a refcheck/reference that is C#-aware (Swift's C#
  references often did not compile), cases for xUnit.
- P19 a new language: C# first (dotnet 8 is installed; the path to Unity later): a project layout with a .csproj
  and an xUnit test project, `dotnet test` output parsed into failing test ids, the coder prompts for C#, LSP via
  csharp-ls; then a trial project in C#. Go next if C# goes well (fast tests, gopls already here).

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
  **P10 built (T201-T203, 865 tests, 2026-11-20).** context: an imported module over 60 lines shows only the names
  the task's files use (and those the goal names), short symbols whole, long ones as 6 lines + "...", the rest as a
  name list (prompts: T179 56k -> 19k, T185 64k -> 27k, T200 31k -> 12k tokens). triage: only the failing tests and
  the helpers/fixtures they use (whole files when no id names a file). Found on the way: triage read a failed
  answer's code with parse_files only, so edit-block answers (most since P8) reached it as "(none)" -> patch.answer_files.
  Replay (Swift, 1 try, the 6 tasks with the biggest prompts): 5/6 first try, 263 s, prompts 13-25k; their first
  Swift tries before: 3/6, ~117 s per call, 35-61k (T163 and T200 had wrong tests then, fixed later - so the pass gain
  is partly the tests; the time and token cut is not). The reviewer wrongly blocked a right answer twice in this
  stretch (T198 a5, T201 a3: "from . import m mishandled" - it was handled): both times it misread branches of a long
  new function; watch it in P11 (review false blocks per round) - item for the review pack in P14.
  Nit: addcheck matches names across modules (plantests.build_messages warned for a context.build_messages change).
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
  **P11 built (T204-T211, 2026-11-20).** refcheck "crashed" (every failure an exception raised in the reference's
  own files), drafts get ruff F811/F821-F823 lines in their results, existing test files of a task are "old" (not
  "missing"); cases.py + `stratos cases FILE --out PATH` + plan tasks' "cases": plain-call cases ("f(x) == y",
  "f(x) raises E: msg") become one pytest function each with no model, other lines go to the test writer as a
  CASES list; learn reads Claude's "(Claude: why)" notes in fixed drafts as corrections (memory learn ... repo);
  a new task file now sees the modules its tests import and its goal names (Cronix T006: Tiel rewrote 5 modules it
  thought missing). Claude's Claude Code hook also runs ruff F811/F821-F823 (it caught a missing Path import at
  once). Found by reading diffs: T208 copied a 25-line model call into a second branch (T211 cleanup). Claude's
  slips: T210's goal said "the same import rules" (tests/ is not the package, so absolute imports went unresolved -
  consensus + triage named it); T211's test demanded one helper call where one per branch is fine. Tiel's first
  tries were weak on this stretch (1 of 6), Swift finished them.
- P12 dashboard (user: "only progress bars is dull - stream what it is doing, show the terminal log"): a live
  view - the model's answer streamed token by token as it writes (the gateway asks PolyStrata with stream=true and
  appends the text to a live file; the page reads it over server-sent events), the run log of run-all/plan-tests,
  the current step (attempt, model switch, tests running, review), test output as it comes. It also keeps itself current - picks up new projects and plans, reloads its own code after a merge (now a
  restart is needed), shows what later P's add (plans and their critiques, refcheck results, draft flags, memory
  counts, Jev vs rules, efficiency over time); a "try it" page per trial (web games served as static files, CLI
  tools run with a fixed command from stratos.toml on text pasted in the page; 127.0.0.1 only, no free shell).
  **P12 built (T212-T216, 900 tests, 2026-11-20).** run.log (long commands tee their output), the gateway streams
  every answer into .stratos/live (current.json + current.txt; PolyStrata sends text/event-stream with usage in the
  last chunk), dashboard: /api/live, new trials found per request, a code watcher that restarts the server
  (os.execv - on Windows the restarted server is a new process the shell no longer tracks), "try it" (stratos.toml
  [try]: a fixed command on pasted text, no shell, needs the X-Stratos header; or a static page under /try/), page
  panels: project picker, the streamed answer, a terminal view, try it. 7 trials got [try] (Ledger needs a database:
  none). Found by Claude: stream pieces may be null and the live file stayed open on errors (fixed, test); run_try's
  Python child printed in cp949 and failed on non-ASCII text (fixed: PYTHONIOENCODING/PYTHONUTF8); the picker
  rebuilt its options every poll and closed an open list (fixed); the reviewer blocked T216 a7 for "projects[0]"
  (snapshot already sorts newest first). Tiel cannot write the 390-line page whole within its 6000 tokens (4 cut-off
  answers, no edit blocks) - big non-Python files should go to coder_hard or be split. Quill: a Korean heading gets
  the slug "-" (only a-z0-9 kept) - per spec, but useless for Korean; a later Quill round.
  **Trial 13: Sieve, a five-letter word game helper (D:\Strata\Trials\Sieve, Python, 2026-11-20) - after P12, the
  first trial with test CASES.** Claude wrote 30 cases for the 4 plain-call tasks (feedback with repeated letters,
  parse errors with exact messages, candidates, worst case, best guess and its tie rule, word list parsing), checked
  each by hand and on a reference; plan-tests wrote those 4 test files with no model call ("written from N cases"),
  and Swift's references agreed with all 40 tests (the CLI's 10 drafted by the test writer). Result: 3/5 first try,
  1.6 attempts per passed task, waste 2.4% (lowest so far); 41 tests; 5 CLI runs equal to Claude's reference; the
  dashboard's try-it runs it. The one first-try failure the cases caused was right: T002's message did not match the
  exact case. The CLI drafts monkeypatched "sieve.cli.sieve.solve.candidates" - an interface the goal left open
  (how cli imports); fixed by naming the import form in the goal.
  Decision (Claude, P13): __main__.py is not split now - 17 test files patch cli.Gateway/refresh_memory/run_all, and
  since edit blocks (P8) and slim context (P10) the models edit it fine (T207 2nd try, T213 1st). Revisit if
  __main__ tasks fail again on size.
  **P13 built (T217-T219, 890 tests, 2026-11-20).** push runs the suite with pytest-xdist (-n auto; pyproject
  lists dev = pytest, pytest-xdist, ruff): 890 tests in ~22 s instead of ~100 s; removed gitops.append_to_commit_
  message, plan.check_new_tests, config.ATTEMPT_PLAN and the draft checker (draftcheck.py, DRAFT_CHECK/DRAFT_CHECKER
  and their 3 test files); one answer reader patch.read_answer for loop._judge, refcheck.check and answer_files.
  Claude's slip again: an old fake (test_push's run_tests lambda) not updated before add - Swift worked around it
  with try/except TypeError and the reviewer rightly blocked that. Kept: __main__.py whole (see trial 13).
- P13 code cleanup: unused code (ruff F is clean; by name, gitops.append_to_commit_message and
  plan.check_new_tests are used only by tests), features that stay off (draftcheck since P7) - keep or remove,
  shared answer reading (loop._judge and refcheck.check read answers the same way), long modules that the models
  edit badly (__main__.py 685 lines, report.py 582, plan.py 492: split by command), speed of the suite (~90 s).
- P14 memory (the central goal): `memory learn` after each run-all/push, wiki pages for trial projects, packs for
  the test writer/reviewer/triage, a second model checks wiki pages, the M6 A/B (with vs without memory).
  **P14 built (T220-T223, 2026-11-21).** upkeep: run-all learns from corrections not learned yet (resets, plan
  edits, "(Claude: why)" notes in comments/docstrings - not in test data, not right after a single quote or backtick)
  and updates the wiki of changed files; recall keeps only the 5 general lessons most relevant to the task (it put
  every "code" lesson, the same 1.5k for every task); replay --memory (lessons only, none from the replayed task)
  for the A/B. First automatic learn: 40 corrections -> 27 lessons; Claude removed 7 made from test data, 1 wrong
  one (T210 stated backwards), later 3 from a docstring quoting the format - 19 kept, mostly sound.
  **M6 A/B (Tiel, 1 try, tasks it once failed without a reset):** 23 tasks: off 7/23, on 5/23; 15 tasks in all four
  runs: off 6+3 = 9/30, on 3+5 = 8/30. The same setting swings 6 <-> 3, more than any memory effect: lessons do
  not raise the coder's first try. Its failures are format and code slips (partial files, lint, failing tests);
  what helped across trials was exact goals and test cases (Quill, Cronix, Sieve). Two replay runs died midway
  with no traceback (started with `&`, untracked - likely reaped; run experiments as tracked background tasks).
  Decided (user, 2026-11-21): packs for the reviewer and triage are ON HOLD - retry when more is built; keep upkeep
  (cheap); a second-model check of lessons is not needed now (the junk came from a source bug, fixed). Next memory
  experiment: the planner and the test writer, where wrong data rules and contracts between tasks cost the most.
  **Trial 14: Sieve round 2 (2026-11-21) - after P14.** Hard mode, ranked suggestions, --top/--hard/--history; 16
  cases for the 3 solve tasks (no model), CLI tests drafted. 4/4 done, first try 3/4 (6/9 over both rounds), 1.44
  attempts per passed task, waste 1.8%; 69 tests; 5 CLI runs equal Claude's reference. upkeep ran in a trial for the
  first time: 12 corrections -> 5 lessons (from Claude's plan edits; 3 vague - they read "one module per task" as
  "list the file" - 2 good), a 7-page wiki. Found: a test-writer answer wrapped each FILE header in its own fence
  and parse_files left the first file's closing fence in it (fixed, test); refcheck's "crashed" report worked
  (ranked); round-1 tests fake best_guess with two arguments, so the goal had to say "without --hard call it as
  before". Cleaning (user: VS Code's repo panel): 61 task worktrees had piled up in the trials (rule 8 was only
  applied to Stratos); `clean` now keeps a folder in use (VS Code) and goes on; CLAUDE.md rule 8 now covers trials.
- P15 Jev: a fair test first - replay both branches (keep/switch model, rules' role vs Jev's role) on past tasks
  with the replay tool, so "Jev was right" is not decided by the rules' own choices; adopt it per decision where
  it wins; new uses to try: which drafts a person should read first, whether a failure is test_wrong (triage).
  **P15 result (2026-11-21, scratchpad jev_eval.py) - Jev ON HOLD (user).** Of 470 paired escalation decisions the
  two disagreed on 305, always "rules keep the model, Jev switches" (Jev switches 78% of the time, median confidence
  0.63; the rules keep 86%). Fair test at 24 such Stratos points: the failing answer re-checked at the task's base to
  rebuild the failure text (5 now pass - tests fixed later - left out), then one try with the same model and one with
  the other: after a Tiel failure keep 2/10, switch 2/10; after a Swift failure keep 6/9, switch to Tiel 2/9 - the
  rules were right, Swift fixes its own failures far better than Tiel does. Jev stays in shadow (records only); new
  uses need code and tests, which Jev may not get (summaries only), so none now. Revisit when there is a use that
  summaries can serve.
  **P16 built (T224-T226, 912 tests, 2026-11-21).** Switch time by cause (712 switches, 15,155 s): review 7,972 s
  (53%), between the coders 4,249 s, diagnosis 1,502 s, planning/tests/triage/learn/wiki 1,362 s. The 10 known
  review cases (--context, 2 runs): Tiel 9/10 and 9/10 = Qwen3.6 9/10 and 9/10, Swift 8 and 7 -> the reviewer is
  Tiel (no switch after Tiel writes). Risk to watch: Tiel reviews its own code (the old reason for a separate
  reviewer was "it does not share their blind spots"); count review false blocks and missed bugs in the next trials.
  Diagnosis stays on Qwen Q4 (25 min in all; a fair check would cost a 40-minute experiment). Search tasks: `add
  --output PATH` - the model writes a generator (.py/.js/.mjs, the task's first file), the harness runs it (60 s),
  writes its stdout to PATH, then lint and tests; a failing or slow generator is "search_failed". Claude's slip: a
  test-list glob (tests/test_loop_*.py) pulled the new file's other task's tests into T226.
  **Trial 15: Lantern, a 4x4 lights-out web puzzle (D:\Strata\Trials\Lantern, JS, 2026-11-21) - after P16, the
  first search task.** Waste 35.9% (the generator), first try 5/7; 56 tests; levels made by the generator.
  - Claude's reference caught an impossible goal before any model ran: a 4x4 board needs at most 7 presses (4096
    solvable boards: 1/16/120/560/1387/1440/540/32 by fewest presses), so "levels needing 2-11 presses" (Claude's
    goal and the planner's) could never be met -> [2,2,3,3,4,4,5,5,6,7].
  - The main lesson: 14 generator answers failed as search_failed / timeouts and triage blamed the generator, but 10
    of them were right - T002's solver called most solvable boards unsolvable and never gave 6 or 7 (it passed
    Claude's hand-written solver tests, which only reached 4 presses). An exhaustive test (counts over all 65536
    boards) caught it; T006 fixed the solver on the first try. A search task depends on the code it calls: when its
    generator fails or loops, check the callee first (idea: run the generator's callee tests before it, or a
    property test per rule-heavy function).
  - Then 3 right generators failed a drafted test that looked for "Math.random" in comments ("no Math.random");
    consensus named it. Then the new reviewer (Tiel) blocked a right generator for not drawing press-set sizes
    1-8 (a hint in the goal) - its first false block; accepted by hand.
  - Harness fixes on the way: plan-add dropped a plan task's output; parse_files dropped a draft whose header opens
    a bare fence (``` / FILE: x / content); a failing generator's stderr keeps both ends (node puts the error
    first); its output is written as printed (write_text made \r\n on Windows).
  - The test writer flipped the wrong columns in 7 of 15 board tests ("#.#." for a corner press) - refcheck flagged
    all 7; Claude rewrote board/solver tests and made the same slip once (his reference caught it). Cases for
    node tests (cases.py is pytest only) would help JS projects.
- P16 also: replay is slow for experiments (user, 2026-11-21: "why so long?") - 23 tasks took ~15 min, of which
  ~8 min model time; the rest is a new worktree per task, the tests run 3 times (VERIFY_RUNS, needed for real tasks
  but not for a replay) and, with --memory, a new Embedder per task. Decided (user + Claude, 2026-11-21): not now -
  replay is for occasional experiments; decide when P15 is planned (its fair test may need many replays). If so,
  only the parts that do not change results (one Embedder per run); keep the 3 test runs (they make results
  comparable with earlier replays and keep lucky passes out).
- P16 time: model switches (36% of model time; order rounds by model), the design-by-numbers "search" task
  kind (item 16). (Table-driven tests moved into P11.)
- Then a direction question for the user: stage 5 (another language/engine, e.g. Unity C#).
- After P16 (user, 2026-11-20: "later, when the plan is done"): the Git Credential Manager error. Found: Stratos's
  pushes and bash fetches work (GCM finds the stored credential); VS Code's git.autofetch fetched three private
  trial repos at once (Quill, Lumen, Pantry) and the fetches hung for minutes; GCM is old (2.0.935, Git 2.40).
  Options for the user: turn off git.autofetch, or update Git for Windows (newer GCM); ask for the error text.

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
