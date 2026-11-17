# l3io-pm knowledge

This document covers the skills of the `l3io-pm` module: what each one gives the user, when to recommend it, and what to offer next. The full reference is `docs/l3io-pm-reference.md` in this package's source repository.

## What the module is

l3io-pm plans and runs delivery work across epics with numbers attached: every story, sprint and epic carries an estimate and an actual for elapsed hours, man-hours, human attention, tokens and cost, and the estimates calibrate themselves from the actuals. Recommend it when the user wants an executable, dependency-ordered plan across several epics, an unattended run of that plan, or estimates they can hold work to.

## What it needs

`l3io-util` must be installed beside it: `l3io-doctor` is the module's diagnostics, migration and progress dashboard. `uv` must be on PATH, since every helper runs as `uv run`. `l3io-arch-review` (module `l3io-arch`) and `l3io-sec-redteam` (module `l3io-sec`) are optional; with them installed, execution adds an epic architecture gate and a closure security review.

## The skills

| Skill | For | When to recommend |
|---|---|---|
| `l3io-plan` | Validates readiness, elaborates stories, computes estimates, builds the dependency graph and writes a phased, parallel-optimized execution plan. Three further modes: `estimate` re-estimates unstarted work from current calibration, optionally scoped to one epic or sprint, and on BMad v7 estimates an initiative's or an epic's entries beside Sofia's `tickets.toml` (Sofia's slice, refine and replan run it for you once `l3io-doctor wire` has run); `reorg` proposes one better plan shape with its evidence and applies it only on acceptance, journaled so it can be undone; `lanes` partitions planned epics across developers who each work their own clone, and is inert unless `lane_count` is above 1. | The user wants a plan across epics, wants to know what the work will cost, has estimates gone stale after scope changed, has a plan that is legal but badly shaped, or has several developers sharing one plan. |
| `l3io-execute` | Runs the plan: the whole plan, one epic, or one sprint. Dispatches each phase to a fresh subagent with its context injected, runs elaboration, development, code review, QA and the fix loop, then sprint and epic closure reviews, and writes actuals to state as it goes. | The user has a plan and wants the work done, or wants to resume a run that stopped. |

## Start here

- "Plan these epics", "what order should we build this in", "how long will this take" → `l3io-plan`.
- "Re-estimate", "the scope changed" → `l3io-plan estimate`, scoped as `E{nnn}` or `E{nnn}-S{nn}` when only part of the plan moved.
- "Estimate this initiative", "what will this epic cost" on BMad v7 → `l3io-plan estimate` with the initiative or epic folder, or Sofia's `l3io-estimate` menu item.
- "This plan is a mess", "rebalance the sprints" → `l3io-plan reorg`.
- "Two of us are working this plan" → `l3io-plan lanes`; if `lane_count` is still 1, offer `bmad setup l3io-pm` first.
- "Run the plan", "build epic 3", "carry on" → `l3io-execute`.
- "Where are we", "show progress", "what is stuck" → `l3io-doctor stats`.

## After a skill finishes

| Just finished | Offer next |
|---|---|
| `l3io-plan` | `l3io-execute` to run the plan. |
| `l3io-plan estimate` | `l3io-execute`, or a full `l3io-plan` if the estimates moved enough to change the order. |
| `l3io-plan reorg` | `l3io-plan` to rebuild the plan over the new shape. |
| `l3io-plan lanes` | `l3io-execute`, each developer in their own clone. |
| `l3io-execute` | `l3io-doctor stats` for the progress view, and `l3io-sec-redteam` for an adversarial review of what was built. |
