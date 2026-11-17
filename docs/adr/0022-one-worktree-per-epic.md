# ADR-0022 — An unattended run builds each epic in its own git worktree, when the project allows it

**Status:** Proposed (Task 4.7, 2026-11-17)
**Date:** 2026-11-17
**Spec:** §4.4, §13.5; plan `docs/superpowers/plans/2026-11-17-v7-phase-4-hooks.md`, Task 4.7

## Context

`l3io-execute` runs `bmad-build-auto` once per ticket. That skill refuses to start on a dirty
tree, judges the branch against the epic, and finishes by committing and verifying the tree
is clean (`step-01-clarify-and-route.md:60`, `step-04-review.md:171-174`). Two builds in one
tree each see the other's edits: one halts `dirty tree`, or commits the other's work. v7's
own guidance for parallel writers is separate folders or worktrees
(`docs/toolsmith/subagent-patterns.md:52`).

A worktree is a checkout of a commit. Measured on the fixture at `e435a22` (spec §13.5):
when the project commits `_bmad/`, a worktree runs `render_skill.py` and `tickets.py` from its
own `_bmad/`, `{project-root}` stays inside it, and pm_status resolves the project-wide state
root to the main checkout through `--git-common-dir`. When the project does not commit
`_bmad/`, the worktree has no `_bmad/scripts/render_skill.py`, and no v7 skill renders there.

l3io's build bracket is keyed by the agent session, and its token counts come from that
session's transcript, so two epics built in one session would share a key and a window.

## Decision

- Each epic of a wave runs on its own branch, `l3io/<slug>`, made from the run's base branch.
- When git tracks `_bmad/scripts/render_skill.py`, `_bmad/method/scripts/tickets.py` and
  `_bmad/l3io-pm/scripts/pm_status/__main__.py`, each epic gets its own worktree beside the
  checkout, and the epics of one wave run at once, up to `max_parallel_subagents`, each in its
  own agent session rooted in its worktree. `dispatch-plan.py` decides this from `git
  ls-files`, per project, every run.
- Otherwise epics run one at a time in the main checkout, each on its branch, and the plan
  says why (`parallel.reason`).
- The epic's retrospective runs in the same session, after its last build, so its measurement
  window holds only that epic's turns; the run also passes `--since`.
- An epic is merged into the base branch only after an accepted retrospective, and its tickets
  marked `done`; the main checkout's project state (events, calibration) is committed before
  each merge and at the end of the run.
- A branch already checked out elsewhere is another session's. The run never removes, resets
  or reuses that worktree; it halts.

## Consequences

A project that commits `_bmad/` gets parallel epics; one that ignores it gets a correct but
serial run, and is told so. The shipped `max_parallel_subagents` default stays 4: the planner
caps it at 1 where worktrees cannot run.

Committing `_bmad/` means everything that runs from it must leave it clean; pm_status writes
no bytecode for that reason.

Merges can conflict when two epics of one wave touch the same files. The run aborts the merge,
keeps the branch and worktree, and halts; resolving it is a code decision.

Cost if wrong: if a runtime cannot start a separate agent session, the wave's epics run one
after another in the orchestrator's session, which is slower but measured correctly.
