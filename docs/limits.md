# Limits

What this package does not do. Some of these are deliberate design boundaries, some are
features that are specified but not built, and a few are knobs that exist but do nothing. All of
them are stated here so you do not have to discover them mid-run.

## Concurrency

**Parallelism is bounded by a fixed number, not adaptively sized.** Epics within a wave run
concurrently up to `max_parallel_subagents` (default 4). The settings `parallel_mode`,
`parallel_ceiling` and `safe_batch_size` appear in design material but are **not implemented** —
they describe an intended adaptive model, not current behaviour.

**Parallel epics need a committed `_bmad/`.** Each epic of a wave runs in its own git worktree,
and a worktree of a project that does not commit `_bmad/` has no runnable v7 skills. In that
case `dispatch-plan.py` runs epics one at a time in the main checkout and says why (ADR-0022).

**Parallel epics get no source-file independence check.** Each epic has its own worktree and
branch, so builds never see each other's edits, but nothing verifies that two epics will not
change the same files. That surfaces as a merge conflict when the second epic merges.

**Tickets within an epic never run in parallel.** They share one tree, and `bmad-build-auto`
refuses to start on a dirty one.

**An unattended run is unattended per wave, not per initiative.** It pauses at every epic a
later ticket or epic file waits on for closure, because only the user may tell Sofia an epic is
`done`.

## Platform and runtime

**Token and cost actuals are exact only under Claude.** Other runtimes record what they expose,
and `N/A` where they expose nothing — never a guess. Under `--runtime claude` an `N/A` token
count is refused outright, since a Claude session can read its own usage.

**`--runtime` accepts exactly four values**: `claude`, `codex`, `copilot`, `other`. Anything else
is a hard error, not a silent fallback to the permissive default.

## What the gates check, and what they don't

**The technical-AC check checks coverage, not correctness.** It runs inside Sofia's validate and
verifies that each of the six dimensions is filled or explicitly marked `N/A` with a reason, and
that each carries a `Spec:` pointer that resolves. It does not judge whether the criteria are
*technically right*. That is what `bmad-build-auto`'s review is for.

**No epic architecture gate runs on a v7 run yet.** The 3.x gate left `l3io-execute` with its
3.x phases, and accepted architecture departures are not written back to the specs. Both are
re-homed in a later phase: the gate on `bmad-architecture`, the spec sync beside
`bmad-retrospective`'s decision records.

**l3io adds no review of its own.** A ticket's review is `bmad-build-auto`'s, invoked
`thorough`; an epic's acceptance is `bmad-retrospective`'s verdict (ADR-0017).

**Nothing enforces that a ticket actually ran tests.** `completion_evidence.tests_passing` is
derived from recorded test runs and cannot be asserted, which prevents an agent claiming a pass
it never earned. But no gate can know which suites *should* have run: a ticket that changed code
and recorded nothing shows an absent value rather than a failure.

**Reviewer severity vocabularies are not validated.** Only the backlog's four levels are
enforced in code. The architecture and security vocabularies live in prose, so a reviewer
emitting an out-of-vocabulary severity word would not be caught by any gate.

## Things refused on purpose

Each of these exists because the permissive version shipped a bug.

- **`cost` cannot be entered.** It is derived from tokens and rates and frozen at capture.
- **`tests_passing` cannot be set directly.** It is derived from the test runs `add-test-run`
  and `build-close` record.
- **No l3io verb writes a v7 status.** Status is Sofia's; the run asks the user wherever v7 says
  the user decides.
- **`migrate-adrs --apply` refuses a dirty tree** rather than attempting a partial repair over
  the remains of an interrupted run.

## Knobs that exist but do nothing

Worth knowing so you do not spend time tuning them.

Each is kept deliberately rather than removed.

- **`granularity`** in the calibration file is never varied — every project runs story (ticket)
  granularity in practice. Kept because it is a field in a versioned file: removing it is a
  schema change.

A separate `max_fix_iterations_non_code` used to head this list. It was removed in 3.1.x rather
than documented, because unlike the entry above it was **user-settable** in four
`customize.toml` files and so invited tuning that could not do anything.

## Not in scope at all

- **The installer refreshes skills; it does not migrate your data.** Those are separate steps,
  and the second one is `/l3io-doctor`.
- **No BMad core script is bundled.** The config and customization resolvers are invoked from
  BMad's own installed location, never vendored here.
- **Test suites are never shipped to consumers.** They stay in the source repository and run in
  its CI.
- **Issue-tracker sync is not part of this package.** `l3io-sync` was retired; use BMad v7's
  own ticket stores.
- **This package does not replace any core BMad skill.** It attaches to them through their own
  hooks. Ticket planning and refinement (Sofia), build and review (`bmad-build-auto`) and the
  retrospective remain BMad's.
- **There is no sprint level.** v7 has initiatives, epics and tickets (ADR-0016).

## See also

- [Skills and sequence](skills-and-sequence.md) — what each module does and does not require
- [Troubleshooting](troubleshooting.md) — when one of these boundaries stops a run
- [Architecture and execution model](architecture.md) — the reasoning behind the cost and
  concurrency decisions
