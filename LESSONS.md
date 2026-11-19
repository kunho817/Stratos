# Stratos lessons

General lessons for every project Stratos works on, learned from corrections people made to plans, test drafts and
tasks. One lesson per line: `- [tags] lesson (source)`. The memory indexes each line as a "guide" chunk, so the
planner, the test writer and the coders see the ones that match their task. `stratos memory learn` proposes new
lines; a person reads them before they are committed.

- [plan, data-flow] When a task changes how a value is computed (damage, range, cost), find every function that reads the old value and plan the change there too; a new helper nobody calls changes nothing. (tower defense round 2: step.js kept reading TOWER_TYPES)
- [plan, old-tests] When a goal changes existing behaviour, name the existing tests that pin the old behaviour and change them in the same task. (tower defense: waves.test.js pinned wave 5 as a normal wave; render tests pinned the corner position)
- [plan, edge-cases] A rule like "every fifth wave" must say what happens at 0 and at the first value: wave 0 % 5 === 0 too. (tower defense round 2)
- [plan, data-model] Use only the fields the data model defines; do not invent ids or fields (towers have no id - select them by index or cell). Describe a new field in CONVENTIONS.md as part of the task that introduces it (add CONVENTIONS.md to that task's files); never as a task of its own, since every task needs tests. (tower defense round 2; memory A/B: a docs-only task had no tests)
- [plan, browser, layout] Text or panels drawn on a canvas need room on it: check the canvas size in index.html against where the drawing goes. (tower defense round 2: the panel was drawn below a 640x400 canvas)
- [plan, grid] Removing an obstacle (selling a tower) changes the free cells, so anything computed from them (the enemy path) must be recomputed, as it is when one is added. (tower defense round 2)
- [plan, tasks] Do not plan a task for behaviour the code already has; read the function first. A task with nothing to change wastes a run. (tower defense round 2: step_boss, state_level)
- [plan, tests] Every task needs a new test file of its own as its first test file; existing test files may follow. (P008, P009)
- [plan, format] In list fields write nothing (or leave the field out) when there is nothing; never "none" or "(none)". (memory A/B, 4 of 9 plans)
- [tests, python, global-state] Never change module state outside monkeypatch: no importlib.reload, no sys.modules edits, no os.environ[...] =, no config.X = ... in a test. Use monkeypatch.setattr / setenv so it is undone. (P009: 4 of 6 drafts)
- [tests, expected-values] Work out every expected value step by step from the goal's rules before writing the assertion; most wrong drafts had a wrong number, not wrong code. (tower defense round 1: 8 wrong expectations)
- [tests, floats] Compare computed floats with a tolerance (Math.abs(a - b) < 1e-9 / pytest.approx), never ===: 0.5 * (1 + 0.1 * 14) is 1.2000000000000002. (tower defense round 2)
- [tests, js] In a node test, await only inside an async function, and never try to replace an ES module's export (it is read-only); pass fakes as arguments instead. (tower defense round 2 drafts)
- [tests, scope] Test only what the goal asks; do not add rules of your own (a shorter cooldown, exported constants). (tower defense round 2 drafts)
- [tests, fakes] When a function gains a parameter, every fake of it in older tests must accept it too. (T097: suite_leaks fakes without ignore)
- [tests, dependent-tasks] A later task's tests must use the earlier tasks' functions and numbers exactly as their goals define them; do not invent your own. (tower defense round 2: the panel draft invented costs)
- [code, reuse] Import an existing helper instead of copying it into another module. (tower defense round 1: path.js copied inBounds, render.js copied enemyPosition)
- [code, whole-files] When rewriting a whole file, keep every function that is already in it; only the goal's changes may differ. (T046 and later: dropped definitions)
- [code, parsing] A parser for text a model writes must accept its usual variants (**Key:**, - Key:, Key :); list them in the goal. (Stratos T075, from memory learn)
- [tests, fakes] Fakes of the gateway or telemetry must record what the code under test sends, so the test can check those calls too. (Stratos T076, from memory learn)
- [tests, timing] Compute an expected value before calling the code that writes files or changes the project, not after it. (Stratos T099, from memory learn)
- [code, regex] Check the groups of a re.Match (m.group(n)), never compare the match object with the pattern; with named groups, \N counts the named ones too. (Stratos T113, from memory learn)
- [tests, language] Test data must use the project's own paths and test names (tests/test_x.py for Python, tests/x.test.js for node). (Stratos T121, from memory learn)
- [plan, data] Static data such as a default map must satisfy what its users need (a path from start to end); test that too. (tower defense T005, from memory learn)
- [tests, edge-cases] Grid placement tests must cover the start, end and edge cells, where floor/ceil and off-by-one mistakes show. (tower defense T007, from memory learn)
- [tests, js] Inside a JS template literal or a new RegExp(...) string write \d for \d; a single backslash is dropped. (tower defense T016, from memory learn)
- [plan, cli, errors] A command-line tool needs a task for bad input: a missing file, a malformed number or date gives one clear message and exit code 1, never a traceback. (Ledger trial 3: nobody asked, nobody planned it)
- [code, tests, cli] A command-line entry point passes run()'s result to sys.exit(); test the real process exit code with a subprocess, not only run()'s return value. (Ledger trial 3: run returned 1, the process exited 0)
