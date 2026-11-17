# Architecture

Execution model and design principles for `bmad-l3io-extensions` on BMad v7.

## Extend v7, never replace it

On BMad v7 the work-item tree is v7's. Sofia (`bmad-agent-po`) owns initiatives, epics,
tickets and their status; `bmad-build-auto` builds and reviews a ticket; `bmad-retrospective`
judges an epic ([ADR-0015](adr/0015-v7-owns-the-work-item-tree.md),
[ADR-0016](adr/0016-no-sprints-in-4x.md), [ADR-0017](adr/0017-review-viewpoints-are-lenses.md)). This package attaches
to those skills through their own extension points — hooks, menu items and check lists in the
team's `_bmad/custom/<skill>.toml` — and records what it measures in sidecar files beside v7's
tree. It never writes `tickets.toml`, a leaf file, a container file or a plan file, except a
plan through `tickets.py mark` on the `repo` store.

There is no sprint level: v7 has epics and tickets, and so does l3io (ADR-0016).

## Context Boundary Principle

The core design rule: **one unit of work = one fresh agent session; all state passes through
disk.**

No session receives conversation history from the orchestrator or from a sibling. Each starts
clean, reads what it needs from disk, does its work, writes its outputs to disk, and ends with a
single status line. In `l3io-execute`, each epic of a parallel wave runs as its own session in
its own worktree: the build bracket is keyed by the session and measured from its transcript,
so two epics in one session would share a key and a measurement window.

The same principle applies to `l3io-sec`: the agent's memory is disk-based (its sanctum)
precisely so that each session starts with a deliberate reload, not an inherited in-context
state.

## Module Relationships

```
Sofia (bmad-agent-po)            owns the tickets: TICKETS, REFINE, REPLAN, VALIDATE, BOARD
    |-- hooks (wired by /l3io-doctor wire) --> pm_status estimate-entries, sidecar-reconcile
    |-- validate checks --------------------> spec-align.py check-pointers, estimate-entries --check
    |-- board hook and menu ----------------> plan-graph.py waves / lanes
    |
l3io-plan          estimate | waves | lanes    (read-mostly; writes only l3io's sidecars)
    |
l3io-execute       the unattended run over an initiative or epic
    |-- per ticket --> bmad-build-auto thorough      (build-open / build-close hooks measure it)
    \-- per epic ----> bmad-retrospective -H <slug>  (epic-close hook records closure)

l3io-sec-redteam   standalone persona; its six threat lenses are wired into BMad's review
l3io-doctor        standalone — health check, stats, wire/unwire, migrations, housekeeping
l3io-arch-review   ADR recording; its standards, lenses and design review are wired into BMad
```

`l3io-sec` and `l3io-arch` run standalone and only read the `l3io-pm` config section if
`l3io-pm` is configured. Their viewpoints are lenses (ADR-0017): `l3io-arch`'s five engineering
lenses and `l3io-sec`'s five threat lenses plus AI poisoning run inside `bmad-review` and every
thorough review of `bmad-code-review`, `bmad-build` and `bmad-build-auto`, and `l3io-arch`'s
standards and design review join `bmad-architecture`. Each loads a file its module declares, so
they run on a project where nobody types an `l3io-` command.

## Hooks: how l3io attaches to v7

`/l3io-doctor wire` writes l3io's entries into the team's `_bmad/custom/<skill>.toml` and
records what it wrote; `/l3io-doctor unwire` removes exactly that ([ADR-0020](adr/0020-wire-in-owns-team-customization-edits.md)). It never
overwrites a team value. Every entry calls a script, or loads a file, BMad v7 installs from
this package's declared scripts, at `{project-root}/_bmad/<module>/scripts/…`, and is skipped
while that module is not set up.

| Host skill | Extension point | Runs |
|---|---|---|
| `bmad-agent-po` | `tickets_after`, `refine_after`, `replan_after`; `l3io-estimate` menu item | `estimate-entries` (the replan hook runs `sidecar-reconcile` first) |
| `bmad-agent-po` | `workflow.checks.ticket`, `workflow.checks.set`; a `persistent_facts` entry | `spec-align.py check-pointers --story-file`; `estimate-entries --check`; `facts/ac-dimensions.md` |
| `bmad-agent-po` | `board_after`; `l3io-waves`, `l3io-lanes` menu items | `sidecar-reconcile` after a `move`, then `plan-graph.py waves` and `lanes` |
| `bmad-build`, `bmad-build-auto` | activation prepend; On Complete | `build-open`; `build-close` |
| `bmad-retrospective` | On Complete; a `persistent_facts` entry | `epic-close`; `facts/spec-sync.md`, the epic-closure spec sync |
| `bmad-review` | `lenses` | the eleven l3io lenses (`l3io-arch`, `l3io-sec`) |
| `bmad-code-review`, `bmad-build`, `bmad-build-auto` | `thorough_lenses` | the same eleven |
| `bmad-architecture` | `finalize_reviewers`, `external_sources`, `doc_standards` | l3io's design review (the epic architecture gate); the standards; the documentation standard |

**No hook may leave the tree dirty**, because `bmad-build-auto` halts on a dirty tree at its
first step. `build-open` writes only a self-ignoring spool, `{state_root}/.inflight/`. Every
hook that writes a tracked file commits exactly what it wrote, and nothing else.

## State Contract

v7 owns status. l3io writes TOML sidecars beside v7's tree, through `pm-status.py`, under a
`flock` on the sidecar's directory:

```
<initiative>/tickets/
├── tickets.toml                         ← v7's
├── l3io.toml                            ← [epic.<slug>] lane
└── epic-<slug>/tickets/
    ├── tickets.toml                     ← v7's
    ├── l3io.toml                        ← [entry.<id>] class + estimate; [epic] estimate, actual, closure, verdict
    ├── <stem>-plan.md                   ← v7's
    └── <stem>-plan.l3io.toml            ← a ticket's actual, test runs, dispatch brackets

<main checkout>/<output_folder>/l3io/    ← the project state root, shared by every worktree
├── events.jsonl                         ← append-only event log
├── pm-calibration.yaml                  ← learned estimation ratios
├── adr-register.yaml                    ← ADR number allocator
├── .notices.yaml                        ← one-time notices (gitignored)
└── .inflight/                           ← open build brackets (self-ignoring)
```

The full layout is the sidecar contract in `status-files.md`, carried by `l3io-execute`.

**The state root is the main checkout's from any worktree**, found through `git rev-parse
--git-common-dir`, so every worktree of one clone shares one event log and one calibration
file, and `flock` guards them.

**Who writes it:** `pm-status.py` exclusively, atomically (temp file plus rename) and
round-trip-safe (comments and key order survive). Path assembly lives in one place,
`pm_status/nodes/` (check 26), so a layout change touches only that module.

**`tickets.py move` does not carry the sidecars.** It moves the leaf and the plan and renumbers
the entry. `sidecar-reconcile`, run by Sofia's replan and board hooks, repoints them; a
folder's `next_id` never decreases, so an old entry id is never reused.

**Reads are lock-free.** Every write is an atomic rename, so a reader — `report --watch`
during a parallel wave — never sees a torn file.

**3.x state trees** (`{implementation_artifacts}/state/`, and the older flat, split and
per-epic layouts) are read only by the 3.x → 4.x migration: `bmad migrate` runs l3io-pm's
`migration-1.toml` after method's own, and its guide runs l3io-util's
`scripts/migrate-engine.py` (ADR-0019), which writes only l3io's sidecars and
`{output_folder}/l3io/`.

## The unattended run

`l3io-execute` runs a v7 initiative or epic with no review, fix loop or planning phase of its
own (ADR-0017). `dispatch-plan.py` reads the store, `tickets.py status` and `plan-graph.py
waves`, and emits the run as JSON; the steps then follow it:

1. **Sync.** On a tracker store, Sofia's Tracker sync procedure, then `tickets.py next
   --synced`; on `repo`, `next`. Nothing on a tracker ever calls `mark`.
2. **Waves.** Epics run in `waves` order. Each epic runs on branch `l3io/<slug>`; when the
   project commits `_bmad/`, each epic of a wave gets its own worktree and agent session, up to
   `max_parallel_subagents`, else epics run one at a time in the main checkout ([ADR-0022](adr/0022-one-worktree-per-epic.md)).
3. **Tickets.** Inside an epic, tickets run one at a time — they share a tree, and
   `bmad-build-auto` demands a clean one. Each is one `bmad-build-auto` run invoked `thorough`.
   `plan_checkpoint` and `done_checkpoint` are honoured by asking the user.
4. **Close.** After its last build, the epic's session runs `bmad-retrospective -H <slug>`. An
   accepted verdict marks the epic's tickets `done`; a `rejected` verdict leaves them `built`
   and halts that epic — accepting the work anyway is the user's call alone. The epic branch is
   then merged.
5. **Gates.** The run pauses at each epic in `waves`' `gates` — one that a later ticket or epic
   file waits on for closure — and asks the user to close it in Sofia. It never writes a
   container status.

The project state root is committed in the main checkout (`close-commit.py state`) before each
merge and at the end of the run, since a build in a worktree can commit only its own ticket
sidecar.

## Bounded Parallelism

Concurrency is bounded by a fixed default, not adaptively sized — `parallel_mode`,
`parallel_ceiling` and `safe_batch_size` describe an adaptive model that is specced
(`docs/superpowers/specs/2026-08-17-adaptive-parallelism-design.md`) but not implemented.

| Level | Concurrency |
|---|---|
| Epics within a wave | Parallel, up to `max_parallel_subagents` (default 4), one worktree each — only when the project commits `_bmad/` |
| Tickets within an epic | Always sequential |

A wave starts only when the previous one is merged. Another session's epic — its
`l3io/<slug>` branch checked out in another worktree — is never removed or reused; the run
halts on it.

## Cost Model

**Cost tracks turns.** Not tokens-per-turn, and not repository size. Every turn re-reads the
whole accumulated prefix, so a session's spend grows with roughly the square of its turn
count — a 263-turn agent pays for its own history 263 times.

The repository-size hypothesis was tested directly and failed: deleting 4,415 lines from a
project moved the token composition not at all, and `cache_read` stayed 75–94% of every
story's tokens either way. That finding shapes the run:

| Rule | What it prevents |
|---|---|
| One `bmad-build-auto` run per ticket | A single session accumulating many tickets' turns |
| One agent session per parallel epic | Two epics sharing one measurement window and one growing prefix |
| No review or fix loop around the build | A second review pass over work `bmad-build-auto` already reviewed `thorough` |

## Metrics Contract

Every planning point and closeout — ticket and epic — records an `estimate` and an `actual`
for all five metrics: `elapsed_hours` (AI wall-clock), `man_hours` (counterfactual developer
effort, assessed at closure — not observed), `hitl_hours` (human attention actually spent
supervising), `tokens_k` (a mapping of `total` plus the four token classes), and `cost`
(derived from `tokens_k × rates`, never entered directly). Under `--runtime claude` an `N/A`
token count is refused, and `--cost*` is refused on every runtime.

Estimates are a bottom-up roll-up: an entry's estimate is its class band × the calibrated scope
ratio × the fix factor, and `epic.estimate = Σ entry estimates + calibrated epic-closure band +
calibrated orchestration band`, so an epic reconciles with its tickets by construction.

Actuals come from the hooks: `build-close` writes a ticket's, from the session transcript over
the build bracket; `epic-close` writes the epic's closure and its total. Full model and capture
procedure: `metrics-contract.md`, carried by the PM skills.

## Subagent Invocation

**Preferred method:** Agent tool with a self-contained prompt. No conversation history is
forwarded — only paths, keys, and the skill to invoke.

Every session ends with exactly one status line:

```
DONE — [brief metrics]
BLOCKED: [one-line reason]
FAILED: [one-line reason]
```

An epic session of `l3io-execute` may also end `CHECKPOINT: …`, when a ticket's checkpoint
needs the user.

## Customization Model

Each skill ships with a `customize.toml` at its skill root. Overrides layer in this order:

```
{skill-root}/customize.toml                          (base — shipped, don't edit)
    ↓ override
{project-root}/_bmad/custom/{skill-name}.toml        (team — commit to repo)
    ↓ override
{project-root}/_bmad/custom/{skill-name}.user.toml   (personal — gitignore)
```

Scalar values override; array values append. `resolve_customization.py` performs the merge at
activation; if it fails, the skill falls back to reading the three files in order and applying
the same precedence.

**The root key must match the skill type**, or overrides are ignored silently:

| Skill type | Root key |
|---|---|
| Workflow / utility (l3io-execute, l3io-plan, l3io-doctor, l3io-arch-review) | `[workflow]` |
| Memory agent (l3io-sec-redteam) | `[agent]` |

See [l3io-pm-reference.md](l3io-pm-reference.md#workflow-customization) for the shipped keys and
their defaults.
