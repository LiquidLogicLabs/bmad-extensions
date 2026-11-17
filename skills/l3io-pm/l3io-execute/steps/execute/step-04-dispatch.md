# Step 04: Dispatch the builds

Execute `{run_plan}` wave by wave. Each ticket is one run of `bmad-build-auto`, invoked with the
word `thorough` so its own review runs every lens (`SKILL.md:16`). Review, fixing and
verification are that skill's: this run adds no phase of its own around a build (ADR-0017).

## 1. Waves and epics

Take `{run_plan}.waves` in order. A wave's epics have no dependency on one another, and its
length is already capped at `{run_plan}.parallel.max`. Finish every epic of a wave — built,
closed and merged (step 05) — before starting the next one.

**When `parallel.worktrees` is true**, each epic gets its own worktree, on its own branch, made
from `{run_plan}.base`:

```bash
git -C {project-root} worktree add -b {branch} {worktree} {base}
```

Then run each epic of the wave as **its own agent session**, rooted in its worktree, all at
once. A separate session is what keeps two epics' measurements apart: l3io's build bracket is
keyed by the session, and each session's transcript holds only its own turns, so every build
and every retrospective is measured over its own window. Start the session with this prompt:

```
/l3io-execute epic-session
l3io_epic_run: <the epic's object from {run_plan}, as JSON>
store: {store}
po_root: {po_root}
```

Under Claude Code that is `claude -p '<prompt>'` launched with the worktree as its working
directory; under another runtime, its own headless equivalent. When the runtime cannot start a
second session, run the wave's epics here, one after another, which is always correct and only
slower. Wait for every session's last line (§3).

**When `parallel.worktrees` is false**, run each epic here, one at a time, on its branch in the
main checkout:

```bash
git -C {project-root} switch -c {branch} {base}
```

## 2. One epic

This is what an epic session runs, and what this session runs for an epic when it runs it
itself. `{epic}` is the epic's object from `{run_plan}`; work in `{epic.root}`.

For each ticket in `{epic.tickets}`, in order, run its steps in order:

| Step | Do |
|---|---|
| `sync` | Sofia's **Start** for a tracker store (`{po_root}/references/board.md`): `write` the ticket to `[tickets.status].in-progress`, then mirror, then run the step's `next` and confirm the ticket is in `ready_to_start` or `in_progress`. |
| `checkpoint-plan` | Run `bmad-build-auto` with the step's `invocation`, which ends `Halt after planning.` (`step-02-plan.md:37`). Then stop this epic with `CHECKPOINT: {ref} plan — <the step's ask>`. |
| `build` | Run `bmad-build-auto` with the step's `invocation`. |
| `checkpoint-done` | Stop this epic with `CHECKPOINT: {ref} built — <the step's ask>`. |

`bmad-build-auto` commits its own work and leaves the tree clean, and l3io's hooks on it record
the ticket's actuals and commit them. After each build, read the plan's status with
`{project-root}/_bmad/method/scripts/tickets.py --project-root {epic.root} find <ref>`:

- `built` (or `done`): go on to the next ticket.
- `blocked`, or the tree is left dirty: stop this epic. Its tickets after this one wait for it,
  and so does everything a later wave needs from it.

```
BLOCKED: {ref} of {slug} did not build: <the plan's blocked_reason, or the dirty paths>
```

When every ticket is built, run the epic's closing steps: step 05 §1 and §2.

## 3. The epic's last line

An epic ends with exactly one of these lines, which is all the orchestrator reads from it:

```
  DONE — {slug}: <n> built, verdict {verdict}
  CHECKPOINT: {ref} <plan|built> — <question>
  BLOCKED: <one-line reason>
```

On `CHECKPOINT`, ask the user the question. On approval, run the epic again — a new epic
session with the same object, or here — and it resumes: a built ticket is not rebuilt, and a
plan left at `draft` by `Halt after planning.` is picked up where it stopped
(`step-01-clarify-and-route.md`, step 5). On refusal, treat the epic as blocked.

On `BLOCKED`, leave the epic's worktree and branch exactly as they are for the user, report
it, and carry on with the rest of the wave. A later wave that needs this epic does not start.

When every epic of the wave has ended, continue with step 05 §3 for each `DONE` epic.

## 4. Output

```
Step 04 complete — wave {n}: <done slugs>; blocked: <slugs, or none>
```
