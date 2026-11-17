# Getting Started

Installation and first-run guide for `bmad-l3io-extensions`.

## What this adds to BMad

BMad v7 supplies the planning and build primitives — Sofia (`bmad-agent-po`) for tickets,
`bmad-build-auto` for building and reviewing one, `bmad-retrospective` for judging an epic. This
package attaches to them through their own hooks and adds:

- **An unattended run** — `/l3io-execute` builds an initiative's tickets in dependency-ordered
  waves, one worktree per epic where the project allows it, and stops only where v7 says you
  decide.
- **Estimates that learn** — every ticket and epic records an estimate *and* an actual, measured
  by hooks on every build and retrospective, and future estimates calibrate from that history
  with no setup.
- **Readiness checks** — acceptance criteria carry pointers back to the spec sections they came
  from, checked inside Sofia's validate.

Everything runs in short-lived subagents that hand off through files on disk. That is a cost
decision, not an aesthetic one: a session's spend grows with the turns it accumulates, so many
short agents beat one long one.

## Where to start

| You are a… | Start here |
|---|---|
| **Developer** running the work | This guide, then [First Run](#first-run) and the [l3io-pm reference](l3io-pm-reference.md) |
| **Project manager** tracking it | [Checking Progress](#checking-progress), then the [estimation guide](estimation-guide.md) for how estimates, actuals and calibration work |
| **Architect** reviewing the model | [Architecture and execution model](architecture.md) — the context boundary, the hooks, and the sidecar state contract |
| **Contributor** to this package | [CONTRIBUTING.md](../CONTRIBUTING.md) — note that `skills/_shared/` holds the only editable copies of shared files |

New to the five skills? [Skills and sequence](skills-and-sequence.md) explains why each one
exists and which of them run automatically rather than being invoked. When something stops with
a `BLOCKED:` message, see [Troubleshooting](troubleshooting.md); unfamiliar terms are in the
[Glossary](glossary.md).

## Prerequisites

- **An agent** — Claude Code, Codex, or another the `skills` CLI supports; pick one or more
  with `-a` at [Install](#install).
- **BMad v7** installed and set up in the target repo: its `core-tools` and `method` modules.
  l3io 4.x runs on BMad v7 only; a BMad 6.x project stays on l3io 3.x.
- **[uv](https://docs.astral.sh/uv/)** on your `PATH`. The Python helpers (`pm-status.py`,
  `spec-align.py`) are invoked as `uv run`, which provisions their dependencies from an inline
  PEP 723 header — there is nothing else to install, but without `uv` the first status write
  fails.
- Required BMad v7 skills present, from its `method` module: `bmad-agent-po` (Sofia — the
  ticket tree), `bmad-build-auto` (one run per ticket) and `bmad-retrospective` (one per epic).
  `/l3io-doctor check-deps` shows what resolved in your project.
- **WebSearch permission** granted in your IDE if you plan to use `l3io-sec` (required for live cloud/platform best practices research)

Node.js is **not** needed to use the skills — only to develop this package itself, where
`package.json` requires Node 22 or newer.

## Module Selection

You can install all four modules or only the ones you need — but `l3io-util` is required
whenever `l3io-pm` is installed (it provides the doctor that PM skills forward to for
the progress dashboard, the hooks and the version report, and `bmad setup l3io-pm` reports it
as an unmet requirement when it is missing).

| Module | Install if you want |
|--------|---------------------|
| **l3io-pm** | Unattended runs over BMad v7 initiatives, per-ticket estimates, waves and lanes |
| **l3io-util** | **Required with `l3io-pm`.** Diagnostics, `wire`/`unwire` for l3io's hooks, the progress dashboard, the 3.x → 4.x migration engine `bmad migrate` runs, and the version report. |
| **l3io-sec** | Adversarial security review |
| **l3io-arch** | Engineering-standards architecture guardrails and review (new-project design, review audits, and ADR-recorded decisions) |

All four modules are installed the same way: each is its own folder under `skills/`, added
with its own `npx skills add`, and `bmad setup <code>` then installs the scripts it declares
and asks its questions.

## Install

Run in the project repo where you want to use the extension — the same sequence
`npm run smoke:install` runs against a real v7 project:

```bash
for m in l3io-pm l3io-util l3io-sec l3io-arch; do
  npx --yes skills add LiquidLogicLabs/bmad-extensions/skills/$m -s '*' -a claude-code -y --copy
done
```

Together, this installs all five skills and registers the four modules with v7 once
`bmad setup` has run. Repeat `-a` for each agent (`-a claude-code -a codex`), never comma-separated. Never add
`skills/_shared/` — it is source, not a module. `install.sh --action install` at the repository
root runs the same loop.

Then, in your agent:

```
bmad setup l3io-pm
bmad setup l3io-util
/l3io-doctor wire
```

`npx skills add` installs skills but none of the scripts they declare; `bmad setup` installs
those under `_bmad/<code>/scripts/`. `bmad setup l3io-pm` asks `lane_count`; every other setting
has a default. `wire` attaches l3io's hooks, lenses and facts to Sofia, the builds and the
retrospective through the team's `_bmad/custom/<skill>.toml` files, and `/l3io-doctor unwire`
removes exactly what it added.

### Verify the install

```
/l3io-doctor
```

Run it once, before anything else, after `bmad setup` has installed the status helper. With no
argument it scans the project and prints a findings table — so a clean report confirms both that the skills
resolved and that your project state is readable. If the command is not found, the installer
did not generate a surface for your IDE: re-run the install with the right `--tools` value.

### The agent instruction block

On install, on upgrade, and whenever you run a module's setup, the extension offers to write a
marked `l3io` block into the instruction file of the harness you are actually running —
`CLAUDE.md` under Claude Code, `.github/copilot-instructions.md` under Copilot, `AGENTS.md`
otherwise. It never creates a file for a harness that is not running.

The block is short, and it holds what an agent cannot infer from the skills themselves: that PM
state is machine-written and must never be hand-edited, that these skills take plain intent or a
scope token like `E007` rather than `--flags`, which command does what, that estimates and
actuals are both mandatory, that calibration derives its ratios from the actuals you record — so
an inaccurate one degrades every later estimate — and that cost is tokens × the model's rates,
with the rate card worth re-checking whenever a model appears that it does not name.

That file is yours, so the block is wrapped in `l3io:begin` / `l3io:end` HTML-comment markers and
everything outside them is left alone. A file that already exists with no markers is **proposed
to, never silently appended to** — you are shown the body and asked first. A later upgrade
replaces the block in place, and only when its text actually changed. `/l3io-doctor uninstall`
strips the block before it removes any payload, and never deletes the file. Edits you make
*inside* the markers are overwritten on the next refresh; keep your own notes outside them.

If you run the extension from a second harness later, that harness's instruction file has no
block yet — the PM skills say so once, at activation, and otherwise stay out of the way.

This is not the same thing as `/l3io-doctor update-ai-rules`, which is older and narrower: that
mode rewrites *your own* prose where it still describes a legacy state layout. One maintains a
region this package owns; the other corrects text you wrote.

## First-Run Configuration

Core settings live in installer-owned `{project-root}/_bmad/config.toml` and `config.user.toml`. Your own module settings go in `{project-root}/_bmad/custom/config.toml` (team, committed) and `custom/config.user.toml` (personal, gitignored), under `[modules.<module-code>]`.

No module needs configuring to work — every setting has a default. Run a module's `configure` action only when you want to change one.

### l3io-pm

`l3io-pm` is the only multi-skill module, and it is configured with `bmad setup l3io-pm`. Run
it only when you want to record a project-level setting; every PM skill resolves config at
activation via `_bmad/scripts/resolve_config.py` and uses sensible defaults when
`modules.l3io-pm` is absent — which is the normal state for a fresh install, not a trigger for
setup to run automatically.

Key settings (with defaults) — what `bmad setup l3io-pm` collects and writes:

- `implementation_artifacts` — default: `{output_folder}/implementation-artifacts`
- `planning_artifacts` — default: `{output_folder}/planning-artifacts`
- `lane_count` — default: `1`. How many developers will work this plan in parallel, each in
  their own clone. `1` keeps lanes entirely off; see
  [setting up for several developers](#optional-set-up-for-several-developers-at-once)
- `lane` — which lane *you* are, asked only when more than one is configured. It is written to
  the personal, gitignored layer and never to the committed one

`output_folder` (default `{project-root}/_bmad-output`) is **not** one of them. It is a core
setting (`core.output_folder`) that the BMad installer owns, and this module's setup deliberately
does not collect or write it — asking again invites an answer that silently loses on the next
install. Change it through BMad's own config, not through this module's setup.

Both paths resolve from `modules.l3io-pm` for **all four** l3io modules: there is one artifact
tree, and `l3io-pm` owns the path to it.

See [l3io-pm reference](l3io-pm-reference.md) for the full config schema.

### l3io-sec

`/l3io-sec-redteam` is a standalone (single-skill) module and self-registers when you
explicitly ask it to `setup` or `configure` — an absent `l3io-sec` config section
is normal, not a trigger. The first time you invoke it, it also initializes its sanctum.

For WebSearch to work, ensure the `WebSearch` tool is allowed in your Claude Code permissions.

### l3io-util

`/l3io-doctor` is a standalone (single-skill) module and self-registers only when you
explicitly pass `setup` or `configure` — an absent `l3io-util` config section is
normal, not a trigger. With no argument it runs its health check directly.

### l3io-arch

`/l3io-arch-review` is a standalone (single-skill) module and self-registers only when you
explicitly pass `setup` or `configure` — an absent `l3io-arch` config section is
normal, not a trigger. The standards themselves live in the skill's `scripts/standards/standards-*.md` files — a universal `standards-core.md` plus per-stack overlays that load automatically based on the detected stack. Run `/l3io-doctor wire` to apply them automatically inside BMad: `bmad-architecture` gets the guardrails and l3io's design review, and five engineering lenses join `bmad-review` and every thorough code review.

See [l3io-arch reference](l3io-arch-reference.md) for the standards catalog, the three modes, and the wiring.

## Upgrading

An upgrade is the install sequence again: `npx skills add` of each installed module folder
replaces its skills, `bmad setup` rebuilds every declared script and offers any migration that
now applies, and `/l3io-doctor wire` adds whatever entries the release added
(`install.sh --action upgrade`, or `/l3io-doctor upgrade`, runs the first and third for you).

**From l3io 3.x.** After installing 4.x and running `bmad setup`, run `bmad migrate`: method's
own migration first, which turns the v6 folders into a v7 initiative, then l3io-pm's
`migration-1`, which carries your estimates, actuals, calibration, event log and ADR register
into l3io's v7 sidecars, verifies every datum, and only then renames the 3.x source `.legacy`.
`/l3io-doctor`'s Check 20 says when it is pending.
CHANGE the module or IDE set, deliberately.

`install.sh` at the repository root picks the right command and refuses the wrong one; inside
an installed project, `/l3io-doctor upgrade` does the same from payload already on disk.

After upgrading, your `_bmad/custom/config.toml` and `config.user.toml` overrides are preserved — the installer never touches those layers.

### Upgrading from 1.x

The installer refreshes skills; it does not migrate your data. Run `/l3io-doctor` once
before any run — it inspects the project and applies every migration you
need, in dependency order, behind one confirmation.

The 1.x → 2.x jump renamed and merged several skills and changed the state layout twice.
See **[Upgrading](upgrading.md)** for the version-by-version notes, the full ordered
sequence, backups and rollback, and current deprecations.

## Before Running l3io-pm

Before your first run, verify:

1. BMad v7 is installed with Sofia (`bmad-agent-po`), `bmad-build-auto` and
   `bmad-retrospective`, and `bmad setup` has run for `l3io-pm` and `l3io-util`.
2. `/l3io-doctor wire` has run. It adds l3io's hooks to the team's `_bmad/custom/<skill>.toml`
   files — estimates on Sofia's ticket procedures, readiness checks in her validate, waves and
   lanes on her board, measurement on every build and retrospective — and never overwrites a
   team value. `/l3io-doctor unwire` removes exactly what it added.
3. Sofia has planned an initiative: its epics and tickets exist, refined, under
   `{output_folder}`.
4. If you are unsure what shape your project is in, run `/l3io-doctor` — with no argument it
   reports findings and proposes the right actions in order. A project coming from l3io 3.x
   should read [Upgrading](upgrading.md) first.

### Optional: estimate and order the work first

Sofia's hooks estimate new and changed tickets as she writes them. To estimate an initiative or
epic yourself:

```
/l3io-plan estimate _bmad-output/initiative-shop
```

To see the order the epics may run in, and which epic closures will pause the run:

```
/l3io-plan waves
```

Dependencies are v7's: the initiative's `[[epic]] after`, each ticket's `after`, and each epic
file's own `after`. Change them through Sofia's REFINE, REPLAN and BOARD.

### Optional: set up for several developers at once

Skip this if one person runs the work. Lanes are off by default and stay completely inert —
no prompt, no proposal, no extra field — until you ask for them.

Everything else in this package relies on `flock` to keep concurrent agents from colliding, and
a `flock` guards one filesystem. Two developers with their **own clones** share none, so between
developers concurrency is mediated by `git merge` instead. Lanes partition the epics so that
merge has nothing to decide.

Turn them on by running `bmad setup l3io-pm` and answering its question about how many developers will
work this project. The answer is recorded as `lane_count` in the committed team config layer —
`1` means single-developer, deliberately, and is behaviourally identical to never having been
asked. Each developer then records *which* lane they are in their own gitignored
`_bmad/custom/config.user.toml`, and nowhere else: a lane is a slot in a partition, never a
person, which is why it is a number rather than a name and why no name reaches the repository.

With `lane_count` above 1, `/l3io-plan lanes` proposes the partition:

```
/l3io-plan lanes
```

It groups the initiative's epics into that many lanes, then reports two numbers that are
different objectives — the **cross-lane dependencies** it had to accept, which turn two parallel
developers into a queue, and the **waves each lane is idle in**, because a partition can be
perfect by connectivity and still leave one developer waiting for another to finish. If more
lanes than the work supports costs crossings, the proposal says what fewer would have cost.

On your agreement it writes each epic's lane with `pm-status.py set-lane`, into the initiative's
`l3io.toml`, and commits it. The rule is **one epic, one lane**: a ticket never carries one, so
moving work between lanes means moving a ticket between epics, through Sofia's BOARD. Re-run
`/l3io-plan lanes` any time to see one lane's view — a filter over the waves, never a second
document that could go stale.

Three things make a shared run safe, and the mode restates all of them:

- **Commit and push everything before execution begins.** That does not remove the merge; it
  bounds it to a known surface by making everyone fork from one commit.
- **Add one line to `.gitattributes`** for l3io's `events.jsonl` with `merge=union`. The event
  log is append-only, so union is literally the right semantics; measured on two clones, it
  turned the one conflict they produced into none, with every event preserved.
- **Reserve ADR numbers before the fork.** `adr-register.yaml` has a single global allocator
  and is the one genuine collision; a block reserved with `adr-reserve --count`, and committed
  in the push everyone starts from, needs no lock at all.

What lanes do **not** solve is source-file collisions. The dependency graph proves two epics do
not wait on each other. It says nothing about whether both of them rewrite `auth/session.py`.
Partition the work with lanes; agree the file boundaries between yourselves.

## First Run

`/l3io-execute` builds the tickets Sofia (`bmad-agent-po`) planned, unattended:

```
/l3io-execute                                   # the active initiative
/l3io-execute _bmad-output/initiative-shop      # one initiative, wave by wave
/l3io-execute _bmad-output/initiative-shop/tickets/epic-cart   # one epic
```

It reads the store, `tickets.py status` and the waves `plan-graph.py` derives, then runs one
`bmad-build-auto` per ticket, invoked `thorough` — that skill plans, implements, reviews and
fixes on its own, so there is no separate review or fix loop here. When an epic's tickets are
built it runs `bmad-retrospective -H` on it; on an accepted verdict it marks the tickets `done`
and merges the epic's branch. It stops and asks you only where v7 says you decide: a ticket's
`plan_checkpoint` or `done_checkpoint`, a rejected retrospective, and an epic that a later wave
waits on, which Sofia closes on your word.

Each epic runs on its own branch, `l3io/<slug>`. If your project commits `_bmad/`, each epic of
a wave also gets its own git worktree and runs at the same time as the others, up to
`max_parallel_subagents`; if it does not, a worktree has no runnable `_bmad/`, and epics run one
at a time. Your working tree must be clean when the run starts.

Every build records **actuals** beside the ticket's estimate for all five metrics — compute
(wall-clock) hours, man-hours (a counterfactual assessed from the delivered work, not an
observed figure), human-attention (hitl) hours, tokens, and token cost — through l3io's hooks on
`bmad-build-auto`, and every retrospective records the epic's. Cost is never entered directly;
it is derived from the captured tokens and the model's rate table. See the
[PM reference](l3io-pm-reference.md#metrics-contract) for the full metrics
contract and calibration details.

## Checking Progress

A full run is long. Two ways to see where it is, both read-only.

**Ask, at any time:**

```
/l3io-doctor stats
```

This renders the initiative's epics and tickets with their v7 status, each epic's lane, and
estimates against actuals from l3io's sidecars, plus any build whose bracket has been open past
the stall threshold.

**Watch it live**, in a second terminal, while a run is in progress:

```bash
uv run _bmad/l3io-pm/scripts/pm_status/__main__.py report \
  --project-root . --initiative-dir _bmad-output/initiative-shop \
  --watch 15
```

This is the only way to get per-ticket detail during a *parallel* wave: each epic runs in its
own session, and several reporting at once would interleave into unreadable output.

## Using l3io-sec

### Standalone

Invoke directly for ad hoc reviews:

```
/l3io-sec-redteam
```

On first run it initializes its sanctum (persistent memory) at `{project-root}/_bmad/memory/l3io-sec-redteam/`. On subsequent runs it loads its identity from the sanctum and asks for scope and target.

To run a scoped analysis against a specific epic or the whole solution, provide the scope when prompted. The skill loads relevant platform research cache topics, runs all five threat lenses, and writes a report.

## Using l3io-util

Run with no argument any time you want a health check:

```
/l3io-doctor
```

It scans the project, reports what it finds, and proposes every fix in order behind one
confirmation. The diagnostic itself is safe to run any time.

Modes worth knowing:

```
/l3io-doctor wire             # add l3io's hooks to BMad's skills (unwire removes them)
/l3io-doctor stats            # progress dashboard over a v7 initiative, read-only
bmad migrate                  # l3io 3.x data → its v7 sidecars (l3io-pm migration-1, after method's)
```

> `/l3io-util-cleanup` was renamed to `/l3io-doctor` in 2.1.0. The old name's deprecated
> forwarder was removed in 3.0.0 — see [Upgrading](upgrading.md).

To sweep the source tree for `bmad-defer:` deferred-shortcut markers and harvest them into the backlog (report-only until you confirm the merge):

```
/l3io-doctor harvest-debt
```

A `bmad-defer:` marker is a one-line comment a developer (or a dev subagent) leaves on a deliberate simplification — `// bmad-defer: <what was simplified>. ceiling: <limit>. upgrade: <trigger>.` — recognized across every common language's comment syntax. Harvesting turns those crumbs into tracked backlog items so they don't rot silently; markers that name no upgrade trigger are flagged at a higher severity.
