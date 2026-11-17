# l3io-pm knowledge

This document covers the skills of the `l3io-pm` module: what each one gives the user, when to recommend it, and what to offer next. The full reference is `docs/l3io-pm-reference.md` in this package's source repository.

## What the module is

l3io-pm attaches numbers and an unattended run to BMad v7's planning and build. Sofia (`bmad-agent-po`) owns the initiative, its epics and its tickets; l3io-pm estimates them, measures every build, rolls each epic up at its retrospective and calibrates the estimates from the actuals — elapsed hours, man-hours, human attention, tokens and cost — in its own sidecar files beside Sofia's, never in hers. Recommend it when the user wants estimates they can hold work to, an order and a partition for several epics, or Sofia's planned tickets built without driving each build by hand.

## What it needs

`l3io-util` must be installed beside it: `l3io-doctor` is the module's diagnostics, migration and progress dashboard, and its `wire` mode attaches l3io's hooks to Sofia, `bmad-build`, `bmad-build-auto` and `bmad-retrospective`. `uv` must be on PATH, since every helper runs as `uv run`.

## The skills

| Skill | For | When to recommend |
|---|---|---|
| `l3io-plan` | Three modes over a v7 initiative: `estimate` estimates an initiative's or an epic's entries into l3io's sidecars (Sofia's slice, refine and replan run it for you once `l3io-doctor wire` has run); `waves` orders the initiative's epics (or a parent initiative's initiatives) into the waves they may run in, with each dependency's reason and the epic closures that gate them; `lanes` partitions the epics across developers who each work their own clone, and is inert unless `lane_count` is above 1. | The user wants to know what the work will cost, what order it runs in, or how several developers share it. Shaping the plan itself — refining a ticket, reshaping or moving tickets — is Sofia's REFINE, REPLAN and BOARD. |
| `l3io-execute` | The unattended run over a v7 initiative or epic: one `bmad-build-auto` run per ticket in wave order, one git worktree per epic where the project allows it, each epic closed with `bmad-retrospective`, and a pause at every epic gate for the user. | The user has tickets Sofia planned and wants them built, or wants to resume a run that stopped. |

## Start here

- "Estimate this initiative", "what will this epic cost" → `l3io-plan estimate` with the initiative or epic folder, or Sofia's `l3io-estimate` menu item.
- "What order do these epics run in", "what can run in parallel" → `l3io-plan waves`, or Sofia's `l3io-waves` menu item.
- "Two of us are working this plan" → `l3io-plan lanes`, or Sofia's `l3io-lanes` menu item; if `lane_count` is still 1, offer `bmad setup l3io-pm` first.
- "Refine this story", "this plan is a mess", "move this ticket" → Sofia (`bmad-agent-po`): REFINE, REPLAN or BOARD.
- "Run the plan", "build this epic", "carry on" → `l3io-execute`.
- "Where are we", "show progress", "what is stuck" → `l3io-doctor stats`.

## After a skill finishes

| Just finished | Offer next |
|---|---|
| `l3io-plan estimate` | `l3io-plan waves`, then `l3io-execute`. |
| `l3io-plan waves` | `l3io-execute` to run the waves, or `l3io-plan lanes` when several developers share the initiative. |
| `l3io-plan lanes` | `l3io-execute`, each developer in their own clone. |
| `l3io-execute` | `l3io-doctor stats` for the progress view, and `l3io-sec-redteam` for an adversarial review of what was built. |
