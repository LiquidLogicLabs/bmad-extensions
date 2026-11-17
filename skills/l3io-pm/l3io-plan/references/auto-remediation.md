# Auto-remediation of orchestrator halts

Skills in this package stop at a `BLOCKED:` line when they cannot proceed. Several of those
halts already know their own remedy, name it, and stop so the user can type it and start the
run over. This reference governs which halts perform the remedy instead.

> When a halt has a remedy we can determine and perform, **perform it, report what was done,
> and continue the run.** Halt only when no remedy exists, when performing one would decide
> something that is the user's to decide, or when the remedy has already been tried.

A halt is classified in exactly one of the two tables at the end of this file. A step file that
remediates a halt points here for the contract; it does not restate it.

## The attempt bound

**One attempt per distinct issue per run.** Record the remedy *before* running it. If the same
halt recurs after its own remedy has run, it becomes a hard halt naming what was tried:

> BLOCKED: I ran `<remedy>` to resolve `<condition>` and the condition persists. `<detail>`.
> This needs a decision.

There is no second attempt under any condition: a remedy that re-runs a skill carrying its
own halts would otherwise loop on them forever.

**Remedies that share one command and one underlying cause share a single attempt.** This
refines the rule above and does not replace it: a second symptom produced by the same command
over the same state cannot be independent of the first, so it goes to its site's persists halt
rather than to a second run.

**The budget is per site id, not per run.** Sites that do not share a command and a cause each
keep their own, so two different remediable halts in one invocation each run once. Sharing is
the exception above, for one command and one cause; two different remedies are never one
attempt.

The record is **in-run memory**, not a file: the bound is per run, a run is one orchestrator
invocation, and every remediable site is inline in that invocation rather than inside a
dispatched subagent. **If a site ever moves into a dispatched subagent this is void** — the
package's context boundary passes state through disk, never through in-memory hand-off — and
the record must become a file.

## Reporting — act, then confirm

Per ADR-0004 an agent acts and confirms after the edit lands. Every remediation prints one line
before and one after:

```
⚙  <condition, with counts> — running <remedy>
✓  <what the remedy did>. Continuing <what resumes>.
```

A remediation that cannot report what it changed does not qualify. Silence is never correct:
the user should finish the run knowing what their project needed, not with it hidden.

## When a remedy fails

If the remedy reports failure or errors, **halt** — reporting both the original condition and the
remedy's failure. Never continue as though it succeeded, and never retry.

A remedy that writes to disk has a failure path of its own: a write that errors (permissions, a
read-only checkout) is a failed remedy. Report the original condition **and** the write error,
and leave nothing partly applied.

A remedy that succeeds is not yet a remedy that worked: re-check the original condition once.
If it persists, that is the attempt bound's hard halt above, not a reason to continue. Every
remediable site therefore has three explicit outcomes — cleared, succeeded but persists, and
failed — and only the first continues.

## The tables are a live inventory

The two tables below hold one row per halt **site** — a site is a distinct halt condition, and
may be written as more than one `BLOCKED:` line when it has a recurrence form and a failure
form that share their opening words. The row count always equals the number of sites. A task
that converts a halt **moves its row from `Halts` to `Remediable` in the same commit** that
changes the step file, so the tables never disagree with the code.

A site is identified as `<file-stem>: <first six words of the BLOCKED text>`, or the whole line
if it is shorter; placeholders in braces match whatever they hold at runtime.

**To add, change or convert a halt, you must:**

- Add a table row **in the same commit** as any new `BLOCKED:` line.
- Give a second form of an existing site the first six tokens of the first form **verbatim**,
  so the two collapse to one id.
- **Move** a converted site's row from `Halts` to `Remediable`. Never copy it, and never leave
  a stale row behind.

**Class.** Every row carries a `Class`, and the class travels with the row when it moves:

- `auto` — remediated.
- `halt` — halts; no single remedy.
- `absolute` — halts and may never be converted.
- `auto+absolute` — has a convertible route and an absolute one.

`absolute`, and the `absolute` half of `auto+absolute`, may never be removed by a later task.

**Scope.** The inventory covers `BLOCKED:` lines at column 0 of a shared step file. An epic's
last-line template (`BLOCKED: <one-line reason>`, indented in `execute/step-04-dispatch.md`
§3) is a report format, not a halt, and is deliberately out of scope. Outside the inventory
too are the doctor's own halts — `skills/l3io-util/l3io-doctor/steps/redrive.md` and
`skills/l3io-util/l3io-doctor/SKILL.md`'s `BLOCKED: _bmad/l3io-util/scripts/pm_status is not
installed — run bmad setup l3io-util` — which are not orchestrator steps. That last one is a
**halt**, for the reason its `l3io-pm` twin in `step-00-activate` is: the remedy, `bmad setup
l3io-util`, asks the module's config questions, and the answers are the user's to give.

## Re-entry

The once-per-project setup pointer (`config-resolution.md` §5) cannot fire twice in a run:
`pm-status.py notice` records a key at most once ever per project, exit 0 the first time and
exit 1 for every call after.

## Remediable

No site is remediable today: every remaining halt's remedy is a decision or an install that is
the user's. The table stays, so a converted halt has a row to move into.

| Site | Trigger | Remedy | Changes | Class |
|---|---|---|---|---|

## Halts

These stop the run. Rows of class `absolute` (marked **ABSOLUTE**) are hard rules, not defaults: no later change may
convert them, whatever remedy appears to exist.

| Site | Why | Class |
|---|---|---|
| `step-02-resolve: {slug} is owned by another session.` | **ABSOLUTE.** The branch is checked out in another worktree, which may hold a build in flight; removing or reusing it is data loss across a boundary `flock` cannot see | `absolute` |
| `step-05-close: the retrospective of {slug} is rejected` | **ABSOLUTE.** Moving a rejected epic's tickets to `done` would accept work its retrospective refused; that acceptance is the user's alone, as setting readiness from red to amber was | `absolute` |
| `step-02-resolve: no initiative to run — name a` | User input error | `halt` |
| `step-02-resolve: the working tree is not clean —` | The remaining changes are the user's; committing or stashing them is not ours to decide | `halt` |
| `step-02-resolve: bmad-agent-po is not installed — l3io-execute` | A required v7 skill is missing; installing it is the user's | `halt` |
| `step-03-sync: tracker sync failed: <the command and` | The tracker or its credentials; a stale mirror would start tickets the tracker already moved | `halt` |
| `step-04-dispatch: {ref} of {slug} did not build:` | `bmad-build-auto` halted the ticket `blocked`, or left the tree dirty; its blocking condition is the remedy's input, not ours to guess | `halt` |
| `step-05-close: merging l3io/{slug} into {base} conflicts: <the` | Resolving a merge conflict is a code decision | `halt` |
| `step-05-close: {slug} gates the next wave and` | A container's `done` is Sofia's to set on the user's confirmation (`board.md`, Status) | `halt` |
| `step-00-activate: _bmad/l3io-pm/scripts/pm_status is not installed — run` | Setup has not run since the skills were added. The remedy is `bmad setup l3io-pm`, which asks the module's config questions, and those answers are the user's to give | `halt` |
| `step-00-activate: BMad v7 not detected. l3io 4.x` | Wrong product line, not a defect: l3io 4.x supports BMad v7 only, and the remedy is installing BMad v7 or l3io 3.x, which no step can do | `halt` |
