# Phase 4 exit — R3 record

R3 was run on 2026-11-18 by following `2026-11-17-phase-4-r3-procedure.md`, at upstream pin
`e435a22574fe55722841086e5566420178b98df3`, with l3io at `feat/bmad-v7-layer` 1ec262e0.
**Result: R3 passes.** The progress-report fault it found is fixed in the same commit as this
record.

## How it was driven

- **§1–§2:** scripted, exactly as written. `setup.json` reported `"problems": []`, both
  declared `pm_status` copies were present, and the tree was committed with `_bmad/`, which
  enables the worktree path (ADR-0022).
- **§3:** `wire-in.py wire --project-root .` was run directly. It applied 63 entries and skipped
  none.
- **§4–§5:** Claude Code ran headless (`claude -p`) in the fixture, with ordinary permission
  prompts:
  - `/bmad-agent-po` created one initiative, `hello-cli`, with two `simple` stories: a
    `hello.py --name` CLI and a pytest test for it.
  - A resumed turn answered her two decisions and accepted her four suggestions.
  - Then `/l3io-execute _bmad-output/initiative-hello-cli` ran.

## What the run did (fixture `git log`, oldest first)

```
1648072 chore: v7 fixture with l3io
e406510 chore: wire l3io hooks
b634179 chore(l3io): estimates epic-hello-cli          <- tickets_after hook
364a976 plan(hello-cli): initiative, epic and two story entries
03d58eb chore(l3io): estimates epic-hello-cli          <- refine_after hook
673fb00 chore(l3io): estimates epic-hello-cli
76ef0a1 plan(hello-cli): refine stories 1.1 and 1.2
dfc1d10 plan(hello-cli): record validation verdict
470314c chore(l3io): estimates epic-hello-cli
2391693 chore(l3io): estimates epic-hello-cli
7fa81bd plan(hello-cli): apply user decisions, re-validate
d565a39 chore(l3io): run state                         <- close-commit.py state, run start
19f3f52 feat(hello-cli): 1.1 hello.py greets --name     <- bmad-build-auto, thorough
617bc14 chore(l3io): actuals 1                          <- build-close
10945d2 test(hello-cli): 1.2 pytest proves the greeting
de423e7 chore(l3io): actuals 2
faa45ce chore(l3io): epic close epic-hello-cli          <- epic-close on bmad-retrospective
132f544 docs(l3io): epic-hello-cli retrospective        <- close-commit.py retro
dce94c1 chore(l3io): epic-hello-cli done                <- status-done, ticket 1
a2ea20d chore(l3io): epic-hello-cli done                <- status-done, ticket 2
4dc634a chore(l3io): run state
a23822f merge l3io/epic-hello-cli
```

- The epic was built on `l3io/epic-hello-cli` in its own worktree. It was merged, and the
  worktree and branch were removed.
- Sofia's validate ran both l3io checks (Ticket and Set) on both stories, and both passed.
- The retrospective's verdict was `accepted-with-open-items`, so both tickets moved to `done`.
- No later wave waits on this epic, so the run had no gate to stop at. That is correct
  (§13.5).

## §6 read-back

Ticket actuals, from each `*-plan.l3io.toml`:

| Ticket | elapsed_hours | man_hours | hitl_hours | tokens_k total (in / out / cw / cr) | cost |
|---|---|---|---|---|---|
| 1 | 0.0799 | 0.5 | 0.0 | 2585.59 (0.098 / 48.282 / 344.857 / 2192.35) | 3.13 |
| 2 | 0.071 | 0.5 | 0.0 | 2242.45 (0.078 / 41.196 / 266.059 / 1935.118) | 2.54 |

`fix_iterations = 0` on both, and `completion_evidence.test_runs` holds 6 and 5 runs, all with
exit code 0.

Epic, from the epic's `l3io.toml` (1 `closure_runs` record):

| Block | elapsed_hours | man_hours | hitl_hours | tokens_k total | cost |
|---|---|---|---|---|---|
| closure | 0.0574 | 1.0 | 0.0 | 2463.31 | 1.57 |
| actual | 0.2083 | 2.0 | 0.0 | 7291.35 | 7.24 |

`[epic.actual]` equals the two tickets plus the closure in every metric
(0.0799 + 0.071 + 0.0574 = 0.2083 elapsed hours; 3.13 + 2.54 + 1.57 = 7.24 cost).
`retro_verdict = "accepted-with-open-items"`.

Read-back gates:
- **`verify --scope story`:** PASS on both plans, exit 0.
- **`calibration show`:** scope `simple/*` has 2 samples per metric, and closure `epic/*` has
  1 sample each for elapsed_hours, man_hours and tokens_k. hitl has no closure sample, because
  its actual is 0.
- **`events.jsonl`:** 3 `dispatch_close` records (two builds and one closure).
- **`git status --porcelain`:** empty.

## Found

1. **Fixed in this commit: `report --format md` misread both man-hours columns.**
   - It printed an estimate of `0`. `estimate-entries` writes the epic estimate as a
     `man_hours_low`/`_high` range, and the report read a point `man_hours` that is never
     written.
   - It printed an actual of `1`. That was the ticket sum, which missed the closure that
     `[epic.actual]` already includes.
   - The report now shows `8.25–9.38 | 2`.
   - `test_report_shows_the_range_estimate_and_the_closed_epic_actual` uses the real shapes:
     the range estimate and the `tokens_k` class table.
2. **Cold-start token band is far below a thorough build.**
   - Estimate: 88k tokens and $0.36 per `simple` ticket.
   - Actual: about 2,400k tokens (about 390k fresh) and $2.54–3.13.
   - The `scope` ratio activates at 3 samples, so calibration corrects this on a real project.
     The cold-start band itself may want raising for `thorough` builds.
3. **The two `done` commits share one message.** `close-commit.py` names the epic, not the
   ticket. This is cosmetic and left as a follow-up.
4. **The fixture project had no `.gitignore`.** The project's own pytest left `__pycache__/`
   behind, which the unattended build saw as an uncommitted change twice. The retrospective
   raised it as an open item. It is the project's file, not ours, and the run recovered.
