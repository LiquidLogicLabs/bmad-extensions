# bmad-l3io-extensions

[![Commitizen friendly](https://img.shields.io/badge/commitizen-friendly-brightgreen.svg)](http://commitizen.github.io/cz-cli/)
![GitHub issues](https://img.shields.io/github/issues/LiquidLogicLabs/bmad-extensions)
![GitHub](https://img.shields.io/github/license/LiquidLogicLabs/bmad-extensions)
![GitHub Repo stars](https://img.shields.io/github/stars/LiquidLogicLabs/bmad-extensions?style=social)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](https://www.contributor-covenant.org/)

## Overview

`bmad-l3io-extensions` adds a LiquidLogicLabs-oriented operating model on top of [BMad](https://docs.bmad-method.org/) v7 for unattended epic execution, measured estimates, and security/resilience review.

It ships as four installable BMad modules. Teams can install all four or only the ones they need.

### What it adds

BMad v7 supplies the planning and build primitives — Sofia (`bmad-agent-po`) for tickets,
`bmad-build-auto` for building and reviewing one, `bmad-retrospective` for judging an epic. This
package attaches to them through their own hooks, never replacing them, and adds:

- **An unattended run** — a whole initiative built in dependency-ordered waves, one git
  worktree per epic where the project allows it, pausing only where v7 says the user decides.
- **Estimates that learn** — every ticket and epic records an estimate *and* an actual for five
  metrics, measured by hooks on every build and retrospective, and later estimates calibrate
  from that history automatically.
- **Readiness checks** — acceptance criteria carry pointers back to the spec sections they came
  from, checked inside Sofia's validate.

Short-lived subagents hand off through files on disk. That is a cost decision: a session's
spend grows with the turns it accumulates, so many short agents beat one long one — see
[Cost Model](#cost-model).

### Where to start

| You are a… | Start here |
|---|---|
| **Developer** running the work | [Getting started](docs/getting-started.md), then the [l3io-pm reference](docs/l3io-pm-reference.md) |
| **Project manager** tracking it | [Checking progress](docs/getting-started.md#checking-progress) and the [estimation guide](docs/estimation-guide.md) |
| **Architect** reviewing the model | [Architecture and execution model](docs/architecture.md) |
| **Contributor** to this package | [CONTRIBUTING.md](CONTRIBUTING.md) — `skills/_shared/` holds the only editable copies of shared files |

### Where it runs

Skills are generated for **Claude Code** and **GitHub Copilot** (`--tools`, below). Token and
cost actuals are captured per runtime — exactly under Claude, as available under Codex and
Copilot, and `N/A` rather than a guess elsewhere; see the
[estimation guide](docs/estimation-guide.md). `/l3io-doctor update-ai-rules` additionally
maintains instruction files for Claude, Copilot, Gemini, Cursor and the generic `AGENTS.md`
convention.

On install, on upgrade, and on a module's setup, the extension also **offers to write a marked
`l3io` block** into the instruction file of the harness you are actually running — `CLAUDE.md`,
`.github/copilot-instructions.md`, or `AGENTS.md` — and never one for a harness that is not. The
block carries what an agent cannot infer from the skills themselves: that PM state is
machine-written and must never be hand-edited, that these skills take plain intent or a scope
token rather than flags, that estimates and actuals are both mandatory, that calibration learns
from the actuals you record, and that cost is derived from tokens at a rate table worth
re-checking. It is wrapped in `l3io:begin` / `l3io:end` HTML-comment markers so it can be found,
refreshed or stripped cleanly with nothing outside them touched; a file you already wrote is
proposed to, never silently appended to, and `/l3io-doctor uninstall` removes the block before
it removes any payload.

That is a **different feature** from `update-ai-rules` above, and the two only look alike
because they touch the same files: the block is a region this package owns and rewrites,
whereas `update-ai-rules` edits *your own* prose where it still describes a legacy state layout.

**Owner:** Shawn Anderson (shawn@eye-catcher.com)

**Support disclaimer:** LiquidLogicLabs does not provide default support, SLA, or managed services for this extension unless explicitly agreed in writing.

## Modules

| Module | Skills | Description |
|--------|--------|-------------|
| **l3io-pm** | `l3io-plan`, `l3io-execute` | The unattended run over a BMad v7 initiative or epic, per-ticket estimates with calibration, waves and lanes — attached to Sofia, `bmad-build-auto` and `bmad-retrospective` through their hooks |
| **l3io-sec** | `l3io-sec-redteam` | Adversarial security analysis through five threat lenses with AI poisoning cross-cut and live cloud/platform best practices research |
| **l3io-util** | `l3io-doctor` | **Required when using `l3io-pm`** (the PM skills forward migrations, health checks and the progress dashboard here). Project state diagnostics & housekeeping — health check that reports findings and proposes an ordered fix plan (default); `wire`/`unwire` attach l3io's hooks to BMad v7's skills; `stats` renders a progress dashboard over a v7 initiative; `version` reports the installed version per skill and module, and whether the two `pm_status` copies agree; migrate a legacy l3io state layout; harvest `bmad-defer:` deferred-shortcut code markers into the backlog. *(Renamed from `l3io-util-cleanup` in 2.1.0; that deprecated forwarder was removed in 3.0.0. See `docs/upgrading.md`.)* |
| **l3io-arch** | `l3io-arch-review` | Engineering-standards architecture guardrails and review — applies universal best practices (separation of concerns, reuse, design-by-contract, testability, dependency/GA policy, unified correlated logging, documentation with diagrams) plus per-stack overlays (Python, Node.js, .NET, GitHub Actions) at new-project design time, during an architectural review, or when recording an architecture/technology decision (ADR) |

## Quick Start

l3io 4.x runs on **BMad v7**. Each of this package's four modules is a folder under `skills/`
(`l3io-pm`, `l3io-util`, `l3io-sec`, `l3io-arch`), installed with the `skills` CLI and then set
up with v7's `bmad setup`. This is the sequence `npm run smoke:install` runs against a real v7
project built by `tests/fixtures/v7/make-fixture.sh`.

**1. A v7 project.** BMad v7's `core-tools` and `method` modules must already be installed and
set up in the repository — `bmad-agent-po` (Sofia), `bmad-build-auto` and `bmad-retrospective`
come from `method`, and `l3io-pm` dispatches to all three.

**2. Add the modules.** From the project root, one `npx skills add` per module folder of a
checkout of this repository, for each tool you use (`-a claude-code`, `-a codex`, …; repeat the
flag rather than comma-separating):

```bash
git clone https://github.com/LiquidLogicLabs/bmad-extensions /tmp/l3io
for m in l3io-pm l3io-util l3io-sec l3io-arch; do
  npx --yes skills add /tmp/l3io/skills/$m -s '*' -a claude-code -a codex -y --copy
done
```

`l3io-util` is **required** with `l3io-pm` (it provides `l3io-doctor`); `l3io-sec` and
`l3io-arch` are optional. Never add `skills/_shared/` — it is source, not a module.

**3. Set them up.** `npx skills add` installs the skills but none of the scripts they declare.
`bmad setup` installs those under `_bmad/<module>/scripts/` and records each module's
settings:

```
bmad setup l3io-pm
bmad setup l3io-util
```

`bmad setup l3io-pm` asks how many developers share the project (`lane_count`); every other
setting has a default. It reports `l3io-doctor` as an unmet requirement when only `l3io-pm` is
installed. `l3io-sec` and `l3io-arch` self-register from their own skill on an explicit
`configure` request.

**4. Wire the hooks.** In your agent:

```
/l3io-doctor wire
```

This writes l3io's entries into the team layer (`_bmad/custom/<skill>.toml`) of Sofia,
`bmad-build`, `bmad-build-auto` and `bmad-retrospective`: estimates on her ticket procedures,
the readiness checks in her validate, waves and lanes on her board, a measured bracket around
every build, and the epic closure on every retrospective. It never overwrites a team's own
value, and `/l3io-doctor unwire` removes exactly what it added.

**5. Check.** Run `/l3io-doctor` once — the health check reports anything still missing and
proposes the fixes in order. See [Getting started](docs/getting-started.md) for the full guide.

### Upgrading

Pull the new release into your checkout and repeat steps 2 and 3: `skills add` replaces each
skill folder, and `bmad setup` rebuilds each module's declared scripts. Re-run
`/l3io-doctor wire` only when the release notes say the wire-in set changed. A project still
carrying l3io 3.x data migrates under `bmad migrate`: method's own migration first, then
l3io-pm's `migration-1`, which moves estimates, actuals, calibration, events and the ADR
register into the v7 sidecars and keeps the 3.x source until every datum verifies.

See **[Upgrading](docs/upgrading.md)** for version-by-version notes.

## Why This Extension Exists

BMad gives strong primitives, but teams still hit common delivery issues in long-running work:

- orchestration drift across tickets and epics
- inconsistent quality gates between dev, review, QA, and security
- context bloat that reduces focus and output quality
- weak closure discipline where high-severity findings get deferred implicitly

This extension standardizes those patterns so teams can run a repeatable, auditable workflow.

## Workflows

| Slash command | What it does |
|---------------|--------------|
| `/l3io-plan` | `/l3io-plan estimate [<folder>]` estimates a v7 initiative's or epic's tickets into l3io's sidecars and rolls each epic up; Sofia's hooks run the same as she writes tickets. `/l3io-plan waves` gives the order an initiative's epics may run in and the epic closures that will pause a run. `/l3io-plan lanes` partitions the epics across developers who each have their **own clone** — it proposes which epics each lane owns, reports what the partition costs (cross-lane dependencies and lanes left idle in a wave), and shows one lane's view. One epic is one lane; lanes stay entirely off unless setup recorded `lane_count` above 1. Shaping the plan itself is Sofia's: REFINE, REPLAN and BOARD |
| `/l3io-execute` | Build a BMad v7 initiative or epic unattended: one `bmad-build-auto` run per ticket, invoked `thorough`, in the wave order `plan-graph.py` gives; each epic closed with `bmad-retrospective -H`, its tickets marked `done` on an accepted verdict, and merged. It adds no review or fix loop of its own — those are `bmad-build-auto`'s — and it stops for you at every epic a later wave waits on. Each epic runs on its own branch, in its own git worktree when your project commits `_bmad/`, and one at a time otherwise |
| `/l3io-sec-redteam` | Adversarial security review through five threat lenses — external attacker, malicious insider, chaos engineer, abusive legitimate user, and design/architecture red team — with AI poisoning cross-cut and live cloud/platform best practices research. The same six viewpoints run as lenses in `bmad-review` and every thorough code review once `/l3io-doctor wire` has run |
| `/l3io-doctor` | **Run without arguments** for a project health check — scans for all known issues (l3io 3.x data awaiting `bmad migrate`, untracked debt markers, AI instruction references, ADRs left in the old per-epic home, story spec pointers, spec-index freshness, BMad dependency resolution, `pm_status` version skew, and initiative progress) and proposes the right actions in order with a single confirmation. Or pass a keyword to skip directly to a specific mode. **The following is a selection, not the full set** — `/l3io-doctor help` prints every keyword, and [`docs/l3io-util-reference.md`](docs/l3io-util-reference.md) documents each one: `check` (read-only diagnostic only), `stats` (progress dashboard over a v7 initiative), `backlog` / `issues` (aliases for `stats` that always print the per-item backlog table), `check-deps` (verify the BMad skills this package dispatches resolve here), `wire` / `unwire` (attach or detach l3io's hooks), `migrate-state` (legacy l3io state layout → the sharded state tree), `harvest-debt` (sweep for `bmad-defer:` markers), `migrate-adrs` (move ADRs from the old per-epic home to `docs/adr/`), `triage` (audit the issues backlog and close what is already fixed), `clean-legacy` (remove migration backups) |
| `/l3io-arch-review` | Apply engineering standards in one of three modes: **design** (hands you to `bmad-architecture`, which carries the guardrails once wired), **review** (runs `bmad-review` with the five engineering lenses on a design/component/diff → severity-graded findings, with a BLOCKER/MAJOR gate), or **decision** (weigh options against the standards and record an ADR). Auto-detects the stack and loads the matching overlay (Python, Node.js, .NET, GitHub Actions). `/l3io-doctor wire` applies it automatically: guardrails and a design review in `bmad-architecture`, five engineering lenses in `bmad-review` and every thorough code review |

## Context Boundary Rule

All workflows are built around one core principle: **each unit of work runs in a fresh subagent with minimal context from previous units.** State passes through disk only — never through in-memory hand-off.

Fresh context means better focus, no context window exhaustion, and restartable runs.

## Parallelism

Epics of one wave run in parallel only where that is safe.

- `max_parallel_subagents = 4` (default, in `l3io-execute`'s `customize.toml`) — bounds how many epics of one wave build at once, each in its own git worktree; tickets within an epic are always sequential, and a project that does not commit `_bmad/` runs one epic at a time
- waves follow v7's own `after` declarations; the run pauses for the user at every epic a later wave waits on for closure

## Cost Model

Cost tracks **turns**, not tokens-per-turn and not repository size. Every turn re-reads the
accumulated prefix, so a session's spend grows with roughly the square of its turn count. The
repository-size hypothesis was tested directly and failed — deleting 4,415 lines moved the
token composition not at all, and `cache_read` stayed 75–94% of every story either way.

Execution is shaped around that:

- **One `bmad-build-auto` run per ticket**, and one agent session per parallel epic — short
  sessions beat long ones, and cost nothing in continuity because every hand-off is a file on
  disk
- **No review or fix loop around the build** — `bmad-build-auto` reviews its own work
  `thorough`, and a second pass would multiply turns
- **Actuals are read from the session transcript** by the build hooks, never typed

See [architecture.md](docs/architecture.md#cost-model) for the measurement behind it.

## Artifact Conventions

On BMad v7 the work-item tree is v7's — initiatives, epics, tickets, plans — and l3io writes
none of it. l3io's own records are TOML sidecars beside it:

- `<initiative>/tickets/l3io.toml` — each epic's lane
- `<initiative>/tickets/epic-<slug>/tickets/l3io.toml` — each entry's class and estimate; the epic's estimate, actual, closure and retrospective verdict
- `<stem>-plan.l3io.toml` beside each v7 plan — the ticket's actual, test runs and build brackets
- `{output_folder}/l3io/` in the main checkout — the event log, calibration file and ADR register, shared by every worktree

A 3.x state tree (`{implementation_artifacts}/state/`), or an older flat `sprint-status.yaml`,
is not read by 4.x; see [Upgrading](docs/upgrading.md).

## Dependencies

Required, from BMad v7's `method` module, by `l3io-execute`: `bmad-agent-po` (Sofia — the ticket
tree, tracker sync and status), `bmad-build-auto` (one run per ticket) and `bmad-retrospective`
(one run per epic). `bmad-code-review`, `bmad-qa-generate-e2e-tests` and `bmad-review` are
optional; nothing in this package dispatches them. Implementation is `bmad-build-auto`'s alone:
this package carries no dev agent.

Required intra-package: `l3io-util` (provides `l3io-doctor`, which wires the hooks).
`/l3io-doctor check-deps` shows what resolved in your project.

These come from BMad v7's `method` module, which must be installed and set up before l3io —
see [Quick Start](#quick-start). If they are missing, the l3io skills install and activate
normally and then fail at the first phase that dispatches to one. Run `/l3io-doctor check-deps` in a target project to see exactly what
resolved there.

## Repo Layout

Skills live one folder per module under `skills/` (ADR-0021): `skills/<module>/<skill>/`. A
skill is any directory holding a `SKILL.md`; a module folder is only a grouping, and an install
flattens every module's skills into one skills folder.

```
skills/
  _shared/               canonical shared sources — pm_status/ (a package), spec-align.py,
                         write-module-config.py, tests/, status-files.md, metrics-contract.md,
                         calibration-model.md, config-resolution.md, module-setup.md, steps/
  l3io-pm/               module folder
    bmod-l3io-pm/        module record: bmod.toml, help/, retired.toml, SKILL.md (a redirect to `bmad setup`)
    l3io-plan/           SKILL.md, bmod.toml, customize.toml, references/, scripts/, steps/
    l3io-execute/        SKILL.md, bmod.toml, customize.toml, references/, scripts/ (incl. pm_status/), steps/
  l3io-sec/              module folder
    l3io-sec-redteam/    SKILL.md, bmod.toml (module record), roster.toml, help/, customize.toml, references/, assets/ (module-setup.md), scripts/
  l3io-util/             module folder
    l3io-doctor/         SKILL.md, bmod.toml (module record), help/, customize.toml, references/, assets/ (module-setup.md), scripts/, steps/
  l3io-arch/             module folder
    l3io-arch-review/    SKILL.md, bmod.toml (module record), help/, customize.toml, references/, assets/ (module-setup.md), scripts/
.claude/commands/        symlinks → ../../skills/<module>/<skill>/SKILL.md
```

Files under `skills/_shared/` are the **only** editable copies of anything shared. Each PM
skill carries a generated payload copy under its own `scripts/`, `references/`, and `steps/`;
those are regenerated by `npm run sync:scripts` and must never be hand-edited. CI runs
`npm run check:scripts` to fail the build on drift.

Module setup lives at each module's **home**: `l3io-pm` — the package's only multi-skill
module — is configured by `bmad setup l3io-pm`; the three single-skill modules (`l3io-util`,
`l3io-sec`, `l3io-arch`) each embed setup (`assets/module-setup.md` + config `scripts/`) and
self-register. Setup never runs implicitly — only on an explicit `setup`, `configure`, or
`install` request. An absent `[modules.<code>]` config section is normal, not a first-run
trigger.

## Documentation

**Start here**

- [Getting started](docs/getting-started.md) — prerequisites, install, first run
- [Skills and sequence](docs/skills-and-sequence.md) — why each skill exists, what runs automatically, and the orders that make sense
- [Upgrading](docs/upgrading.md) — version-by-version notes, the migration sequence, backups and rollback
- [Troubleshooting](docs/troubleshooting.md) — what each `BLOCKED:` and `FAILED:` message means, and how to clear it
- [Glossary](docs/glossary.md) — the terms and enum values this package uses
- [Limits](docs/limits.md) — what this package deliberately does not do

**By role**

- Project manager — [Estimation and actuals guide](docs/estimation-guide.md): how estimates are built, what gets recorded at closure, and how calibration learns from your own history
- Architect — [Architecture and execution model](docs/architecture.md): the context boundary, the state contract, the pre-execution gates, and the measured cost model
- Developer — [l3io-pm reference](docs/l3io-pm-reference.md): the full lifecycle, every `pm-status.py` and `spec-align.py` subcommand, and the state schema

**Per module**

- [l3io-pm reference](docs/l3io-pm-reference.md)
- [l3io-sec reference](docs/l3io-sec-reference.md)
- [l3io-util reference](docs/l3io-util-reference.md)
- [l3io-arch reference](docs/l3io-arch-reference.md)

**Internals**

- [How modules are discovered](docs/bmad-module-yaml-discovery.md) — what `module.yaml` controls and how the installer finds skills
- [Contributing](CONTRIBUTING.md)

For BMad core guidance, see [BMad docs](https://docs.bmad-method.org/).

## Releases

This repo uses Conventional Commits with `commit-and-tag-version`.

Install the release tooling — and the check tooling's own dependencies, which every
`npm run check:*` gate needs:

```bash
npm ci
```

Release commands:

```bash
npm run release          # bump the level the commits imply (feat -> minor, fix -> patch)
npm run release:patch    # force patch, update changelog, create git tag
npm run release:minor    # force minor
npm run release:major    # force major
npm run changelog        # regenerate changelog only
```

Prefer plain `npm run release`: it derives the level from the Conventional Commit types since
the last tag, so a release carrying any `feat` becomes a minor rather than shipping features
under a patch version. The `release:*` aliases force a level and should be used deliberately.

Both hooks are configured in `.versionrc.cjs`, not in `package.json`:

- **`prerelease`** is a hard gate — it refuses to release when payload copies have drifted from
  `skills/_shared/`, when a `payload-manifest.json` hash is stale, when `check:docs` fails, or
  when `pm-status.py`'s version markers disagree.
- **`postbump`** re-syncs after the bump, because the new version string is embedded inside
  payload files: it rewrites every `bmod.toml` module record and
  `pm-status.py`'s version marker, regenerates the manifests, then stages the result.

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Contact

Raise an issue on [GitHub](https://github.com/LiquidLogicLabs/bmad-extensions/issues), or see [SECURITY.md](SECURITY.md).

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and our [code of conduct](https://www.contributor-covenant.org/). All commits must sign the [Developer Certificate of Origin](https://developercertificate.org/).

## Licensing

This extension is available under the MIT license.
