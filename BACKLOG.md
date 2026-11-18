# Stratos backlog

The list of improvements to Stratos itself, kept by Claude and the user. Each session: read this first, pick the top
open item (or what the user asks for), and update it at the end. Evidence comes from `stratos report`,
`stratos report --replay` and the diffs read while verifying. Finished items move to "Done" with the task ids.

Stages (2026-11-18): 0 skeleton, 1 self-development loop, 2 measurement and model choice: done. 3 decision layer:
partly (rules v1, Jev shadow, diagnosis A/B). 4 autonomy (planning, tests, merging): starting with the planner.
5 other projects (a small Python project, then Unity/Unreal): not started.

## Open (top first)

1. **Planner (T061-T062).** `stratos plan` splits a feature goal into tasks, `stratos plan-add` adds them.
   Next: measure it (plans edited vs accepted as they are: telemetry "plan" events, edited flag).
2. **Test drafts by a model.** The biggest remaining human work is writing the tests first. Let a model (Swift) draft
   each planned task's test file; a person checks it, commits it, then the task runs. Plan this one with the planner.
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

- T054-T056 reasoning budget (Gateway, loop, replay, report keys). T057-T060 diagnosis A/B.
- coder_hard: Flint -> Qwen3.8-Flash-Next Coder -> Swift 1.5 IQ2_XS with a 3000-token budget (replay on six hard tasks).
- AgentWorld as a decision model: rejected (offline A/B no better than always choosing Tiel).
