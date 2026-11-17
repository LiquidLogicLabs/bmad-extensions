# CLAUDE.md

## Repository Purpose

`bmad-l3io-extensions` is a BMad community module package with four modules: `l3io-pm` (estimation, measurement and the unattended run over BMad v7's tickets), `l3io-sec` (red team security agent), `l3io-util` (artifact utilities), and `l3io-arch` (engineering-standards architecture guardrails & review). It ships as installable Claude Code slash commands.

Architecture decisions are recorded in `docs/adr/` — ADR-0001: one `pm-status.py` runtime, and single-consumer code lives in its skill's own `scripts/`. **It is no longer one file, and it is no longer self-installed** — its title is history, not an instruction; the ADR's 2026-10-23 amendment records the package, and its 2026-11-16 amendment records that 4.x retires self-install in favour of the copies BMad v7 installs from each module's declared scripts. Option B was taken: the source is the package `skills/_shared/pm_status/`, an entry file plus seven modules (`core` the dependency root, then `nodes`, `instructions`, `metrics`, `issues`, `verbs`, `plan`), and `check:docs` check 12 is now **one** limit — **1,500 lines for every `.py` in the package, `__main__.py` included**. `PM_STATUS_LINE_LIMIT` and the 10,000 are gone. New code goes in the module that owns it; **splitting a module is the answer to tripping the cap, never raising it**; ADR-0004: agents edit architecture specs, PRD/UX/epic docs are proposal-only, and every edit is confirmed after it lands; ADR-0005: `docs/adr/` is the one ADR home and `adr-reserve` allocates from max(register, files on disk) — **allocate every new number through `adr-reserve`, never by hand**: it cannot see a number a design document has promised in prose, and hand-picking one has already collided with such a promise; ADR-0007: CI installs npm dependencies, so the check tooling parses with libraries; ADR-0008: the module packaging shape — one setup skill for `l3io-pm`, three standalone modules, and a TOML writer under the name BMad's validator requires; ADR-0009: `work_type` does not gate phases — a phase is skipped only when the work type leaves it **no subject matter**, which is true of `DOCS` alone, so `CONFIG`'s matrix column is now identical to `CODE`'s; ADR-0010: business acceptance criteria are **authored for every story, blocked only by policy** (`business_ac_required`, a scalar because the core resolver appends arrays and so could only ever widen the requirement); ADR-0022: an unattended run builds each epic on its own branch, in its own git worktree **only when the project commits `_bmad/`** (a worktree of a project that does not has no runnable `_bmad/`), else serially in the main checkout.

## Module Layout

The repository is laid out **one folder per module** (ADR-0021): `skills/l3io-pm/` holds the
`l3io-pm` skills, and `skills/l3io-util/l3io-doctor/`, `skills/l3io-arch/l3io-arch-review/` and
`skills/l3io-sec/l3io-sec-redteam/` are the three single-skill modules. `skills/_shared/` sits
beside them as the canonical source tree and belongs to no module. A skill is any directory
under `skills/` holding a `SKILL.md`; every tool locates skills through
`scripts/lib/skill-dirs.mjs`, never a `skills/*/` glob (`scripts/CLAUDE.md` has the mechanics).
A skill is still named by its own directory, so sibling-relative paths between skills of one
module hold, and an install flattens every module into one skills folder.

`l3io-doctor` routes: `SKILL.md` carries the overview, the keyword table, safety rules
and the state layout, and each of its fourteen modes lives in its own `steps/` file loaded
only when its keyword selects it. Add a mode as a file plus a table row — never inline. The
modes were inlined once and `SKILL.md` reached 96,980 B, so every invocation paid for fifteen
procedures it would not run.

Its migrations are not prose: `scripts/migrate-engine.py` runs detect → read → resolve →
plan → gate → write → verify → dispose, with five readers beside it (one per source
layout) and `pm-status.py import-node` as the only writer. The gate sits before the write
because the previous prose ran its completeness checks after it, so an empty parse passed
vacuously and then deleted the source. Check 26 keeps state-path assembly inside
`pm-status.py`'s resolver section — which now lives in `pm_status/nodes/`, the only place
a node key becomes a path. The markers travel with that code, and the check derives which
file carries them: exactly one must.

Module setup lives at each module's **home**: `bmad setup l3io-pm` for `l3io-pm` (the package's only multi-skill module, whose 6.x `l3io-setup` skill is retired — `skills/l3io-pm/bmod-l3io-pm/retired.toml` lists every name the module no longer ships), and the skill itself for the three single-skill modules (`l3io-util`, `l3io-sec`, `l3io-arch`), each of which self-registers. Setup never runs implicitly — only on an explicit `setup` or `configure` request. **`install` is not a setup trigger** — it routes to `l3io-doctor`'s `steps/install.md`, because a user typing it means the extension, not a module's config. It was both until 3.2.5, in two `l3io-doctor` routing rows with no precedence rule between them. An absent `[modules.<code>]` config section is normal, not a first-run trigger; see `references/config-resolution.md` §5.

## Skill Directory

| Skill | Purpose |
|-------|---------|
| `l3io-execute` | The unattended run over a v7 initiative or epic: `dispatch-plan.py` plans it from the store, `tickets.py status` and `plan-graph.py waves`; each ticket is one `bmad-build-auto` run invoked `thorough`; each epic closes with `bmad-retrospective -H`, has its tickets marked `done` on an accepted verdict, and merges; the run stops at every epic gate for the user. It has no review, fix-loop, story-prep or architecture-gate phase of its own (ADR-0017) |
| `l3io-plan` | Three modes over a BMad v7 initiative: `estimate` writes entry estimates and the epic roll-up into l3io's `l3io.toml` sidecars (`estimate-entries`; Sofia's slice, refine and replan hooks run it too); `waves` orders the epics into the waves they may run in and names the closures that gate them; `lanes` partitions the epics across developers who each have their own clone (inert unless `lane_count` > 1). Shaping the plan is Sofia's: REFINE replaced the full plan's elaboration and REPLAN replaced `reorg` (Task 4.8) |
| `l3io-sec-redteam` | Red team security agent — persona, sanctum and live platform research for explicit sessions. Its five threat viewpoints and the AI poisoning cross-cut are lens files (`scripts/lenses/`) that wire adds to `bmad-review` and every thorough code review (ADR-0017) |
| `l3io-doctor` | Project state diagnostics and housekeeping — default is a health check that reports findings and proposes an ordered fix plan; `stats` is the progress dashboard over v7 initiatives (`report`); plus `triage` (audits v7's backlog, proposes to Sofia), `migrate-adrs`, `migrate-state` (a 3.x layout, until Phase 6), `harvest-debt` (candidate `bug-<slug>` tickets for Sofia), `update-ai-rules`, `clean-legacy`, `redrive`, and `wire`/`unwire` (ADR-0020: the reversible edit of a team's `_bmad/custom/<skill>.toml`). The modes that wrote the 3.x tree (`bootstrap-state`, `split-status`, `sort-status`, `reconcile-status`, `migrate-schema`, `clean-layout`) retired in Task 4.8 |
| `l3io-arch-review` | Engineering standards. Decision support + ADR recording (`adr-reserve`) is its own workflow; `design` routes to `bmad-architecture`, and `review` runs `bmad-review` with the five engineering lenses. Wire attaches the standards (`scripts/standards/`), the five lenses (`scripts/lenses/`) and the design review to BMad's skills |

## Shared Files

Files in `skills/_shared/` are the canonical sources for content shared across PM skills. Do not edit the per-skill copies directly — they are auto-generated.

| Canonical source | Per-skill destination | Skills |
|---|---|---|
| `skills/_shared/pm_status/` (package) | `scripts/pm_status/` | **l3io-execute**, **l3io-doctor** (one payload copy per module, no test suite — see below; BMad v7 installs each module's declared copy at `_bmad/<module-code>/scripts/pm_status/`, and l3io-plan runs l3io-pm's instead of carrying its own) |
| `skills/_shared/spec-align.py` | `scripts/spec-align.py` | pm-execute, **l3io-doctor** — each 3.x step runs its own skill's copy. **l3io-execute also declares it**, so v7 installs it at `_bmad/l3io-pm/scripts/spec-align.py` for the readiness check wired into Sofia's validate (`check-pointers --story-file`); its suite `tests/test-spec-align.py` stays in `_shared/tests/` |
| `skills/_shared/status-files.md` | `references/status-files.md` | pm-execute, pm-plan, **l3io-doctor** (state layout only — it ships this contract but not `metrics-contract.md`/`calibration-model.md`; six of its directives named it, including `SKILL.md`, and it did not carry it) |
| `skills/_shared/ac-dimensions.md` | `references/ac-dimensions.md`; also `scripts/facts/ac-dimensions.md` in l3io-execute, declared | pm-plan, pm-execute — the canonical story-AC dimension reference (which dimensions apply to CODE, to CONFIG, and to every work type), loaded by both enrichment prompts so the two cannot drift apart. The declared copy is Sofia's `persistent_facts` entry on v7, so REFINE writes the dimensions the readiness check enforces |
| `skills/_shared/agent-instructions.md` | `assets/agent-instructions.md` | each standalone module's HOME only: `l3io-doctor`, `l3io-sec-redteam`, `l3io-arch-review` — the block body written into a consuming project's AI instruction file |
| `skills/_shared/auto-remediation.md` | `references/auto-remediation.md` | pm-execute, pm-plan — the contract and the live two-table inventory of every `BLOCKED:` site (`Remediable` / `Halts`); a converted halt moves its row in the same commit |
| `skills/_shared/metrics-contract.md` | `references/metrics-contract.md` | pm-execute, pm-plan |
| `skills/_shared/calibration-model.md` | `references/calibration-model.md` | pm-execute, pm-plan |
| `skills/_shared/steps/**` | `steps/**` | pm-execute, pm-plan |
| `skills/_shared/config-resolution.md` | `references/config-resolution.md` | **every skill** — every skill resolves config |
| `skills/_shared/module-setup.md` | `assets/module-setup.md` | each standalone module's HOME only: `l3io-doctor`, `l3io-sec-redteam`, `l3io-arch-review` (l3io-pm's 6.x setup machinery retired with `l3io-setup`; Phase 3 retires these) |
| `skills/_shared/write-module-config.py` | `scripts/write-module-config.py` | each standalone module's HOME only: `l3io-doctor`, `l3io-sec-redteam`, `l3io-arch-review` (l3io-pm's 6.x setup machinery retired with `l3io-setup`; Phase 3 retires these) |

**A skill-local pointer is only valid if that skill carries the file.** `l3io-doctor` named
`references/status-files.md` in six runtime directives — `SKILL.md` calls it "the canonical
contract" — while shipping no such file; it now ships it (row above). The wider class this
belongs to is **now fixed and, for the shared files, mechanically guarded.** A sweep of every
backticked `references/…`, `assets/…`, `steps/…` or `scripts/…` path in `skills/*/**.md`,
re-measured 2026-09-22 **after** the fix, finds **347 pointers and 0 unresolved** (it was 337
examined with 56 unresolved before). The three pre-existing classes were resolved by rewording
rather than by moving files: shared references and digests naming `steps/…` files that only
`l3io-execute` carries now name them as `l3io-execute/steps/…`; `config-resolution.md`
names the module homes' copies instead of a bare `assets/…`; and the onward pointers inside the `status-files.md` copy shipped to
`l3io-doctor` say which skills carry their targets. Cross-skill citations into
`l3io-sec-redteam` and `l3io-arch-review` are qualified the same way.

**The gate this made possible is check 24 (`shared-pointers`)**, in `scripts/check-docs.mjs`.
It is scoped to *pointers inside a file `sync-shared-scripts.mjs` ships, required to resolve in
every skill that file's sync group delivers it to* — scope and destinations both derived from
`syncGroups` (read by spawning the checked tree's own `sync-shared-scripts.mjs
--dump-deliveries`), so there is no allowlist and nothing hand-kept to go stale. It judges 95
pointers across the 28 shared `.md` files. The one exemption is derived too: a pointer whose
line names a real skill directory that actually contains the file. It does **not** look at a
skill's own non-shared files, at non-`.md` payloads, or at whether the cited `§N` exists (check
3 does that).

**Test suites are never shipped as payload.** `skills/_shared/tests/test-pm-status.py`,
`skills/_shared/tests/test-write-module-config.py` and `skills/_shared/tests/test-spec-align.py` stay in `skills/_shared/tests/` only — no
consumer skill invokes any of them, `sync-shared-scripts.mjs` deliberately excludes them from
every sync group, and no `payload-manifest.json` lists anything under a `tests/` directory. Ten
copies (`test-pm-status.py` into pm-execute/pm-plan/pm-sync, `test-write-module-config.py`
into all 8) shipped as dead payload — ~842 KB across the package — until removed; do not add
either back to a manifest.

**CI discovers the Python suites; it does not list them.** `npm run test:python`
(`scripts/run-python-suites.mjs`) globs `skills/_shared/tests/test-*.py` and
`tests/**/test-*.py` (its `PATTERNS` const) — shared suites in the first, per-skill suites in the
second, which is where they live precisely so they do not ship as payload when a
`--custom-source` install copies a skill directory — and runs each under `uv
run`, and the workflow has one step instead of ten. The list used to be written out in
`.github/workflows/checks.yml` and it was wrong: seven suites — `test-engine.py`, the five
reader suites it depends on, and `test-state-record.py` — were written during the
`l3io-doctor` redesign and never added, so CI had never run the tests for the migration
engine that deletes a project's source layout. Every suite therefore carries its own PEP-723
header (four had their dependencies passed as `--with` flags in the workflow instead, which
made them fail spuriously when run directly). The runner refuses with exit 2 on an empty
discovery rather than reporting success over nothing.

**`check:lint:py` runs ruff over every Python file in `skills/`.** `ruff.toml` carries no
`select` list on purpose: the rule set is whatever the pinned ruff enables, so it cannot drift
from a hand-kept list, and the pin lives in the npm script so a bump is a visible diff. Before
this existed nothing linted ~12,000 lines of Python — and the since-retired `check:bmb` was
reporting clean over them, because bmb's `scan-scripts.py` shells to `uv run ruff`, which fails
to spawn when ruff is absent and is swallowed. Deliberate violations are marked inline with `# noqa: RULE -- reason`, never
ignored wholesale; `ruff.toml` states the only two exemptions and why each cannot be inline.

**`check:types` is a SCOPED type check over the package `skills/_shared/pm_status/` — two error
classes, never a clean tree.** mypy reports **44** findings across the package today (mostly `str | None` into
`os.path` calls), so gating on zero would mean a large unrelated cleanup first and no gate at
all until it landed. That number moves with every extraction — it was 47 before Task 4.9 retired the issues verbs, 70 before Task 4.8 retired the placement verbs, and 69 before `nodes/` left
`__main__.py` — so derive it with `npm run check:types -v`, which prints the tally and the
per-code breakdown, rather than trusting this sentence.
The two gated classes are the message `not callable` (a `@property` read as a method — the
pattern that shipped the 3.4.2 `reparent-story` crash, which **ruff cannot see**, verified on a
repro) and **any** `[name-defined]`. The second guards the first: every ruamel import in
the package is lazy, so `CommentedSeq` is out of scope at module level and an annotation
naming it silently degrades to `Any` — `reveal_type` prints `Any`, calling `Any` is allowed,
and the gate goes blind while still reporting success. An `if TYPE_CHECKING: from
ruamel.yaml.comments import CommentedSeq` is therefore load-bearing wherever such an annotation
lives. The annotated `IssueStore` accessors the gate was written for went with the issues verbs
in Task 4.9, so `check-types.test.mjs` plants a two-module probe of the same shape (lazy import,
`TYPE_CHECKING` import, the properties read from a second module) into a copy of the package,
mutates **every** `.py` and fails if a mutation matched nothing. Deleting the import *is* a
`[name-defined]` error, so the gate fails instead of quietly checking
nothing. Measured: lazy import + annotation + bug → **0** findings; `TYPE_CHECKING` import +
annotation + bug → **2**, at both call sites; correct code → **0**. Do not widen this to
clean-file enforcement without deciding that deliberately — `scripts/tests/check-types.test.mjs`
asserts the rest stay ungated (as a property; it does not pin the count, which is why that
test is the one place here that cannot go stale). Found by the downstream package doing the annotation
follow-up and hitting the inert state.

**`check:bmod` runs BMad v7's own manifest validator, `validate_manifests.py`, over this
package's skills** — every `bmod.toml`, each module record, `retired.toml`, `roster.toml`,
`help/help.md`, one version across every record, and a dry run of setup's module discovery
(ADR-0014). It is never bundled: `scripts/fetch-bmad-tool.mjs <pin> <path>` fetches it, and the
three files it loads beside it, from BMAD-METHOD at the pin over raw.githubusercontent.com,
verifies each against a SHA-256 recorded in that script, and caches it outside the repository —
so the CI step needs network, and a tampered fetch fails it. It validates a temp-dir view of
`skills/` without `_shared/`, which the validator would otherwise report as a skill missing
`bmod.toml`; a failing run keeps that view and prints its path. It replaced `check:bmb` (BMad
Builder's 6.x scanners, and the `bmad-builder` devDependency) and the twelve 6.x installer rules
`check:module` used to model by hand. `check:module` keeps two package rules the validator does
not assert: one `pm_status` payload copy per module, and every routing keyword marked
`registered` named in its module's `help/help.md` — the doctor's menu rows are mirrored there by
hand, and that rule is what keeps them honest.

**`smoke:install` installs the four modules into a real v7 project** —
`tests/fixtures/v7/make-fixture.sh` at the pin, `npx skills add` of each module folder, then
v7's `setup.py` headlessly — and asserts what setup reports: no problems, `lane_count` asked,
and `l3io-doctor` an unmet requirement when only `l3io-pm` is installed. It needs network
(GitHub and npm) and is not a CI gate. Trap rules: a failing run keeps its tree, a workdir
passed as `$1` is never removed.

**Never bundle a BMad core script.** `resolve_config.py`, `resolve_customization.py`, and
`memlog.py` are installed by BMad core at `{project-root}/_bmad/scripts/` and must be invoked
from there. This package used to vendor byte-identical copies of all three into skill
`scripts/` directories where nothing invoked them — dead payload that duplicated core and
would rot on the next BMad release.

Each skill carries a **generated** `skills/<module>/<skill>/payload-manifest.json` — a SHA-256 for
**every file that skill ships**, keyed relative to that skill's own root so a consumer who
installed one skill can verify that skill alone. **Every skill** has one: anything with a
`SKILL.md` is payload, and `clean-payload.py` cannot see a directory with no manifest. The writer walks the skill directory rather than
reading the sync groups — until 2026-10-10 it did the latter, which left 123 of 198 shipped
files unhashed and made `/l3io-doctor uninstall` walk past every skill-local file, including
`clean-payload.py` itself. **Never hand-edit a manifest, and regenerate it whenever a payload
file changes** — `npm run sync:scripts` does not do it for you, and `check:manifest` now fails
after any skill edit until you do. The manifest contract, the sync/verify
commands and the release gates live in `scripts/CLAUDE.md`.

**The check tooling has npm dependencies, and CI installs them.** `.github/workflows/checks.yml`
runs `npm ci` before any gate — add a gate step and it goes *after* that install, or it fails on
`ERR_MODULE_NOT_FOUND`. The checkers parse with libraries rather than hand-rolled readers
(`yaml`, `csv-parse`, `mvdan-sh`); they are **devDependencies only** and nothing under
`node_modules/` is payload, so `check:manifest` never sees them. The dependency-free convention
that used to hold here was never a decision — it accreted, and its cost was four hand-written
parsers. See `docs/adr/0007-ci-installs-npm-dependencies.md`. There is **no mechanical check**
that a gate script's imports are declared in `package.json`" — that follow-up, named in the ADR,
is now **check 28**. An undeclared import works locally, where the package is usually present
transitively, and dies in CI at `ERR_MODULE_NOT_FOUND` after `npm ci` installs only what is
declared.

**Four packages in the installed tree carry an npm deprecation notice, not one.** `mvdan-sh`
(a direct devDependency) is deliberate and argued in ADR-0007. The other three are
pre-existing release tooling and **out of scope — do not "fix" them as part of unrelated
work**: `conventional-changelog-cli` (a direct devDependency), plus `git-raw-commits` and
`git-semver-tags`, which arrive transitively through it and through `commit-and-tag-version`.
Recorded here so the next `npm ci` warning is a known fact rather than a rediscovery. Derive
the current list rather than trusting this sentence: the `deprecated` field in
`package-lock.json`'s `packages` map is the source of truth.

`check:docs` runs thirty-four checks asserting facts that have each drifted in this repo's history. **They compare documented CLI *surface* to the code — flag names, `choices`, subcommand names, counts, paths, versions — and never documented *behaviour*.** A reference row can name every flag correctly, describe the wrong semantics, and pass forever; both reference docs did exactly that for `sync-agent-instructions` until 2026-10-12. The scope statement at the top of `scripts/check-docs.mjs` has the measured case.
They are numbered and described in `scripts/check-docs.mjs`'s own header — read them there rather
than restating them here, **including the `KNOWN GAPS` block** at the end of that header, which
states in full what check 4 does *not* reach over `skills/`. A numbered entry describes a check's
rule; only that block describes its reach, and the two are different questions (`CLAUDE.md` §4).
Three things that header does not tell you:

- Check 16 guards dependency **names** only: **no `check:docs` check verifies probe *paths***. A
  step file that reverted to probing `.claude/commands/<name>.md` alone would pass every CI gate and
  then silently self-skip its phase on a 6.12 install — the failure mode §1.2 of
  `docs/superpowers/specs/2026-09-12-bmad-v612-migration-design.md` calls worse than a missing
  skill. Probe-path correctness is now also checked at build time by **check 29**, which
  requires any name probed through `.claude/commands/` to be probed through
  `.claude/skills/<name>/SKILL.md` in the same file. `/l3io-doctor check-deps` remains the
  runtime verification against a real install; check 29 catches the reversion, not the install.
  Check 37 is the same guard on a second axis: a `.claude/skills` probe must also probe
  `.agents/skills`, the root v7's setup reads first. Check 38 (every tool-directory probe also
  tests `_bmad/_config/skill-manifest.csv`) is **retired on this branch**: v7 writes no such
  file, and the rule would force a 6.x-only probe into every new one. Checks 23 and 35 retired
  with `marketplace.json` and the forwarders; the header of `scripts/check-docs.mjs` states each
  ruling, and the numbers are not reused.
- Check 1 deliberately allows a doc to name a removed skill when mapping it to its replacement or
  explaining the change — `docs/upgrading.md` must be able to say `/l3io-pm-epic-execute` →
  `/l3io-execute`. Docs are allowed to quote values inline; they are not allowed to quote them
  wrongly.
- Check 4's `skills/` arm judges an invocation against the **invoked subcommand's own**
  argparse surface, not the union of everything the CLI registers: long flags, short options,
  each flag's value where argparse declares `choices`, whether a value-taking flag was given
  one, and whether a required positional is present and legal. The same extractor now judges
  `spec-align.py`'s flags too, which that arm never looked at. A bare `{pm_status} …` invocation counts as
  one when the binding is **code-formatted** — that qualifier, not "carries a long flag", is
  what keeps the arm off ordinary prose, and `pmStatusAnchors()` records the two shipped
  sentences that proved the flag version unsafe. What it still does not judge is listed in that
  `KNOWN GAPS` block, not here, so there is one place to keep true; it covers false negatives
  only, and says so.

The `postbump` hook chains sync automatically, so every release keeps the payloads in sync.

## Commands

The `postbump` hook auto-syncs the new version into every `bmod.toml` module record — do not manually bump those files. The release gates and the rest of the
build tooling are documented in `scripts/CLAUDE.md`.

## Skill Authoring Conventions

### customize.toml root key

Every skill has a `customize.toml`. Use the correct root key:

| Skill type | Root key | When to use |
|---|---|---|
| Workflow / utility skill | `[workflow]` | Any skill that is not a persistent memory agent (l3io-execute, l3io-plan, l3io-doctor, l3io-arch-review) |
| Memory agent | `[agent]` | Skills with a named persona, sanctum, and First Breath (l3io-sec-redteam) |

The BMad resolver (`resolve_customization.py`) is called with `--key workflow` or `--key agent` to match. Using the wrong key means team/user overrides are ignored silently.

## Commit Conventions

Conventional Commits are required (enforced via Commitizen). All commits must include a DCO sign-off (`git commit -s`).

Valid types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `revert`, `WIP`.
Suggested scopes: `l3io-pm`, `l3io-sec`, `l3io-util`, `l3io-arch` (module changes), plus `infra` and `ci-cd` (tooling/pipeline). Custom scopes are also permitted (`allowCustomScopes: true` in `.cz-config.js`); there is no commit-msg hook enforcing the list, so these are conventions, not hard gates.

## Key Execution Contracts

**Context boundary**: Each phase runs in a fresh subagent. All state passes through disk — never through in-memory hand-off. In `l3io-execute`, each epic of a parallel wave runs as its own agent session in its own worktree: l3io's build bracket is keyed by the session and measured from its transcript, so two epics in one session would share a key and a window.

**Config resolution**: every skill resolves config by running BMad core's
`{project-root}/_bmad/scripts/resolve_config.py`, which merges four TOML layers
(`_bmad/config.toml`, `config.user.toml`, `custom/config.toml`, `custom/config.user.toml`)
and prints JSON as `core.*` + `modules.<code>.*`. **There is no `_bmad/config.yaml`** — do
not reintroduce a read of one. Module settings the skills write go to the `custom/` layers
only (the installer regenerates the other two). `implementation_artifacts` and
`planning_artifacts` resolve from `modules.l3io-pm` for *all four* modules — one artifact
tree, one home for its path. An absent module section is normal and never triggers setup;
setup runs only on an explicit `setup`/`configure`. Whether an optional module is
installed is answered by `_bmad/_config/manifest.yaml`, never by a config section — a module
can be installed and unconfigured. Full contract: `skills/_shared/config-resolution.md`.

**State files.** On BMad v7 the project-wide files live in `{state_root}` = `{output_folder}/l3io/` (4.x sidecars, below). The **3.x sharded tree** (`{implementation_artifacts}/state/{planned,active,archived}/epic-{nnn}/[sprint-{nn}/]`, one bare YAML node per epic, sprint and story) is written by nothing in 4.x: `/l3io-doctor migrate-state` and `import-node`/`import-actual` read and write it until Phase 6 moves a 3.x project onto v7's tree. The 3.x resolver in `pm_status/nodes/` stays exactly as long as they do. The files, by name:

- **4.x: v7 backlog.** l3io keeps no issues ledger. Deferred work is a ticket in v7's `{output_folder}/backlog/` (`bug-<slug>.md` and the like), with its state in the plan beside it, filed, moved and closed by Sofia (`bmad-agent-po`); v7's `next_id` never decreases, so an id is never reused. The 3.x `issues.yaml`/`issues-resolved.yaml` and the eight issue verbs retired in Task 4.9 (ADR-0002's amendment). `/l3io-doctor triage` runs `scripts/audit-tree.py` — findings 1a–1l re-expressed over v7's tree, read-only, with 1a, 1e, 1g and 1j listed in `tests/l3io-doctor/test-audit-tree.py` as having no v7 meaning — and hands Sofia the repairs; the one it runs itself is `sidecar-reconcile` for an orphaned plan sidecar (1l). `harvest-debt` proposes `bmad-defer:` markers as candidate `bug-<slug>` tickets with a `code-marker (<file>:<line>)` reference, which triage reads back as marker evidence; neither writes a leaf.
- `events.jsonl` — append-only log, `flock`-guarded, one JSON object per actuals or import write plus a `dispatch_open`/`dispatch_close` pair per measured run (`build-close`, `epic-close`, `pm-status.py dispatch`). The input to `usage --agent` scoping; `report`'s stall flags read the `.inflight/` build spool.
- `pm-calibration.yaml` — learned estimation-calibration ratios (see Estimation calibration below).
- `adr-register.yaml` — the ADR number allocator (`next:` plus a `reserved:` list). `pm-status.py adr-reserve --epic E --slug S [--count N]` hands out sequential numbers under a flock **before** dispatch, so parallel arch-gate agents cannot both claim ADR-0007. Absent, empty, or an unparseable `next` all resolve to "start at 1" — a project that has never recorded an ADR still works. A malformed `reserved` (not a list) is the one exception: that field is the record of who is in flight, so `adr-reserve` refuses outright (exit 2) rather than discarding it, since silently resetting it to `[]` could let a new reservation collide with one already in flight. The first number handed out is the larger of the register's `next` and the highest ADR number already on disk — in `--adr-dir` (default `<git top-level>/docs/adr`) and in the old per-epic home — plus one. If that scan is impossible — not in a git work tree and no `--adr-dir` — it **refuses** (exit 2, nothing on stdout, register untouched) and names `--adr-dir` in the message, rather than printing a number derived from a home it never read.
- **Lanes** — `[epic.<slug>].lane` in the initiative's `l3io.toml`, **optional**, a number 1–999, written by `set-lane` and the only lane fact that is committed. It partitions planned work across developers who each have their **own clone**: every `flock` here guards one filesystem and two clones share none, so between developers concurrency is mediated by `git merge`, and with each lane writing only its own epics' folders git has nothing to reconcile. **1 epic = 1 lane**. It is a **number** because a word cannot be screened: `backend` and `sarah` are the same shape, and who works a lane lives in the **gitignored** user layer so a name cannot reach the repository. Absent means lanes are off, which is the majority of projects and must stay completely inert. How many lanes a project runs is `modules.l3io-pm.lane_count`, **asked at setup** rather than inferred.
- `.gitattributes` carries exactly one rule, and `events.jsonl merge=union` is it. The log is append-only and line-oriented, so union is literally its semantics; measured, it reduced the one conflict two lanes produced to none with all events preserved. The other two shared files are deliberately left to conflict — `pm-calibration.yaml` loses at worst a sample, and `adr-register.yaml`'s answer is `adr-reserve --count` **before** the fork, not a merge strategy after it.
- `spec-sync.lock` — the spec-edit lease (`spec-align.py lease`): owner and expiry as JSON, taken by an epic closure's spec sync so parallel closures sharing one tree never edit or commit a spec at once; ignored by the `*.lock` rule.
- `.notices.yaml` — the one-time-ever advisory ledger `pm-status.py notice --state-root S --key KEY` reads and writes under `notices_lock`, keyed on `--key` alone, no pruning (a project's set of distinct notice keys stays small by construction). Not session-scoped: there is no cross-invocation session identifier available, so keying on one would fire on every invocation instead of once. Backs the `l3io-execute`/`l3io-plan` setup-pointer (`config-resolution.md` §5): exit 0 means "not yet emitted for this key — show it and record it," exit 1 means "already shown, permanently, for this key." Never a trigger for setup itself. Kept out of git the same way lock files are — `_ensure_lock_ignore` writes both `*.lock` and `.notices.yaml` into `{state_root}/.gitignore`, one mechanism covering both.

**4.x sidecars (v7's tree).** On BMad v7, v7 owns `tickets.toml`, leaf files and plans, and `pm-status.py` never writes them (ADR-0015). It writes TOML sidecars beside them through `tomlkit`, under a `flock` on the sidecar's directory: `<initiative>/tickets/l3io.toml` (`[epic.<slug>]` with `lane`), `<initiative>/tickets/epic-<slug>/tickets/l3io.toml` (`[entry.<id>]` with `class` and `estimate`; `[epic]` with `estimate`, `actual`, `orchestration`), and `<stem>-plan.l3io.toml` beside each `<stem>-plan.md` (`actual`, `fix_iterations`, `completion_evidence.test_runs`, `dispatch`). Project-wide files move to `{state_root}` = `<main checkout>/<core.output_folder>/l3io/` — the main checkout found through `git rev-parse --git-common-dir`, so every worktree of one clone shares one event log and one calibration file. `set-estimate`, `set-actual`, `add-test-run` and `verify` take `--project-root P` plus `--ticket-dir DIR --entry ID` or `--plan-file PATH` **beside** the 3.x node keys, which only the migration still writes through and which retire with it in Phase 6; `sidecar-reconcile` repoints our sidecars after `tickets.py move`, which carries only its own files. **Estimates come from Sofia's own procedures:** `/l3io-doctor wire` gives `bmad-agent-po` `tickets_after`, `refine_after` and `replan_after` hooks and an `l3io-estimate` menu item, each running `estimate-entries` (new, changed or named entries; class × calibration as `estimate-story` computes it; `[epic].estimate` = Σ entries + epic closure + orchestration, no sprint term), and the replan hook runs `sidecar-reconcile` first. Like `build-close`, both verbs **commit exactly what they wrote**, since they run before the next `bmad-build-auto`'s clean-tree check; `set-estimate`, `set-actual` and `add-test-run` are not hooks and commit nothing. **Readiness runs inside Sofia's validate:** wire appends an entry to her `workflow.checks.ticket` list (`spec-align.py check-pointers --story-file`, the business and six technical dimensions on a v7 leaf, business policy from `business_ac_required`) and to `workflow.checks.set` (`estimate-entries --check`), plus the declared `facts/ac-dimensions.md` as a `persistent_facts` entry; `validate_after` is not used. Both checks only read. **Waves and lanes ride Sofia's board:** wire adds a `board_after` hook (`sidecar-reconcile` after a `move`, then `tickets.py status` piped into `plan-graph.py waves` and `lanes`, which `l3io-plan` declares through `DECLARED_EXTRAS` and so installs at `_bmad/l3io-pm/scripts/plan-graph.py`) and `l3io-waves`/`l3io-lanes` menu items. `waves` sorts over `[[epic]] after`, entry `after` and each epic file's `after`, keeps every `needs` reason, and lists in `gates` the epics a later wave waits on for **closure** (an `after` naming an epic, or in an epic file, waits for `done`; one naming a ticket is met once it is built). `set-lane` writes `[epic.<slug>].lane` (1..`lane_count`, refused while lanes are off) and commits it. `report --project-root P --initiative-dir D` is the v7 progress view; it reads the `.inflight/` spool, so a build whose bracket is still open past `--stall-minutes` shows as stalled. The path assembly lives in `pm_status/nodes/` (check 26); the layout is `status-files.md` §12.

**Every v7 build is measured through its own hooks (R13).** `/l3io-doctor wire` gives `bmad-build` and `bmad-build-auto` a prepend running `pm-status.py build-open` and an On Complete running `build-close`, each from `{project-root}/_bmad/l3io-pm/scripts/` (a hook's `{skill-root}` is the host's) and each skipped while `l3io-pm` is not set up (`requires`). **Neither may leave the tree dirty**, because `bmad-build-auto` HALTs on a dirty tree at its first step: the open writes only a self-ignoring spool, `{state_root}/.inflight/`, and no event; the close writes the events, the plan sidecar's `dispatch` record and `actual`, and the calibration sample, then commits exactly those paths inside the worktree as `chore(l3io): actuals <ticket>`. A sample needs an estimate recorded **before** the build and a plan reading `built`; an unestimated ticket gets actuals and no sample. `check:bmod` judges every wire-in entry's key and kind against the host's pinned `customize.toml`, since an undeclared key halts that skill's every render. The verbs live in `pm_status/bracket/`, never a `build/` directory: a consumer's `.gitignore` commonly ignores every `build/`, and one who commits `_bmad/` would silently lose the module.

**Epic closure rides `bmad-retrospective`.** Wire gives it an On Complete running `pm-status.py epic-close`, which writes, in the epic's `l3io.toml`, one `[[epic.closure_runs]]` record per retrospective (its window: `--since`, else the first turn of the Claude session that touched the document, never before the epic's previous closure run or its last build in the session), `[epic.closure]` as their sum, `[epic.actual]` as every ticket sidecar plus the closure, and `retro_verdict` from the document's frontmatter. It takes one `closure` calibration sample per epic, only with an `[epic].estimate` and an accepted verdict, and commits only its own files (`chore(l3io): epic close <slug>`). It **writes no status**, and leaves the retrospective's own document uncommitted, as v7 does; `done` is the owner's call on the verdict. The verb lives in `pm_status/sidecar/closure.py`.

**No placement model in 4.x.** v7 owns where a ticket lives and its status (ADR-0015); Sofia's REFINE, REPLAN and BOARD shape and move work, and `tickets.py move` carries only v7's files, which is why `sidecar-reconcile` exists. The 3.x placement rule (an epic's directory in the folder named for its status, its sprints and stories inside it, a separate artifact tree mirroring it) is described in `status-files.md` §1–§5 for `migrate-state`'s sake only. Legacy `sprint-status.yaml` (flat) and `_bmad/state/` (per-epic file) layouts are read by the same migration.

Ticket statuses are v7's (`draft … built, done, blocked, dropped`). The 3.x story statuses (`backlog → ready-for-dev → in-progress → review → done`) survive only as `import-node`'s validation of a migration record.

**Every l3io write goes through the shared `pm-status.py`** (run via `uv run`; deps auto-provisioned from its PEP-723 header): sidecar estimates and actuals, the event log, calibration, `verify`. Each is one atomic, round-trip-safe operation, and no skill builds a state path itself — `pm_status/nodes/` is the only place an address becomes a path (check 26). Its CLI is twenty-two verbs (`TestSubcommandRegistration` pins them, and `test_pm_status_surface_is_4_5` pins spec §4.5): the §4.5 keep set, the v7 hooks (`build-open`, `build-close`, `epic-close`, `estimate-entries`, `set-lane`, `sidecar-reconcile`), and `import-node`/`import-actual` until Phase 6. `estimate-story`/`estimate-rollup` keep only their 3.x address; Phase 6 decides their fate when it retires. Under `--runtime claude`, `set-actual`/`verify` **reject** an `N/A` tokens/cost. **`add-test-run --command CMD --exit-code N`** appends one executed test command to `completion_evidence.test_runs` and **derives** `completion_evidence.tests_passing` from it — `all(exit_code == 0)` over the **last run of each distinct command**; nothing lets an agent assert the boolean itself. **`adr-reserve`** allocates ADR numbers (above). **`import-node`** creates a 3.x node that does not exist yet, from a migration record, with its `--goal`, `--superseded-by` and `--depends-on` in the same write, under the epic write lock and the event log; it is idempotent by skip, never by overwrite.

`pm-status.py` is a **shared runtime utility** authored once in `skills/_shared/` (with its `tests/`); `npm run sync:scripts` (also chained into `postbump`) generates the per-skill `scripts/` payload copies — **never hand-edit those**. It ships as a payload copy in exactly **one skill per module**, not in every skill that invokes `{pm_status}`: `l3io-execute` for `l3io-pm`, `l3io-doctor` for the standalone `l3io-util` module (`check:module` guards against a second copy reappearing inside one module). Each of those two skills **declares** every `.py` of the package under `[skill] scripts` in its `bmod.toml` (generated by `sync-shared-scripts.mjs`, compared by `check:scripts`; `l3io-execute` also declares `scripts/spec-align.py` and `scripts/facts/ac-dimensions.md` from that script's fixed `DECLARED_EXTRAS` list, because a hook value can name only a path under `_bmad/<module>/scripts/`), and v7's `bmad setup` installs them at `{project-root}/_bmad/l3io-pm/scripts/pm_status/__main__.py` and `{project-root}/_bmad/l3io-util/scripts/pm_status/__main__.py`, rebuilding each tree on every setup. A skill's `{pm_status}` is always **its own module's** declared copy; activation halts naming `bmad setup <code>` when it is absent (`npx skills add` installs skills but no declared script). The two copies come from one release line but can be set up at different times, so the doctor's health check reports them disagreeing as a finding (Check 25, via `report-version.py`). **There is no self-install**: the 3.x mechanism that copied the package into `_bmad/scripts/pm-status/` at every activation is gone. `_bmad/scripts/` is BMad's directory, rebuilt to exactly its own set by every v7 setup — which is also what removes a copy a 3.x project left there (verified by `smoke:install`). `check:docs` check 39 forbids the old `_bmad/scripts/pm-status` path in any shipped file outside a line marked `check-39: legacy-path -- <reason>`; the only marked lines are `clean-payload.py`'s, which let `/l3io-doctor uninstall` remove a 3.x copy that setup has not yet cleared. **`pm-status.py` shares the package's release line** — its top-of-file marker and `PM_STATUS_VERSION` are written from `package.json` by `sync-bmad-versions.mjs` at `postbump`, alongside every `bmod.toml` module record. Never hand-edit either, and **never move the version backwards**: the doctor's version report and skew finding would read a newer copy as older. The two lines were merged at 2.4.2, jumping the package up past the script's 2.4.1 so that no version went backwards. CI runs `npm run check:scripts` to fail on payload drift from the `skills/_shared/` source, and `npm run check:version` (also chained into `prerelease`) to assert `marker == PM_STATUS_VERSION == package.json version` — an invariant that holds at every commit, not only at release.

`status-files.md` is also shared from `skills/_shared/` — the canonical state-layout contract: §12 is the 4.x sidecar layout, §1–§11 the 3.x tree the migration reads. `npm run sync:scripts` keeps all PM skill `references/status-files.md` copies in sync. Never edit per-skill copies directly.

**HARD RULE — estimates & actuals.** Every planning point and every closeout — at **ticket (story), epic and retrospective** level — must record both an `estimate` and an `actual` for all five metrics, in canonical order: **`elapsed_hours`** (AI wall-clock), **`man_hours`** (counterfactual — what a developer would have taken to do this work by hand; assessed at closure from the delivered diff/tests/scope, never observed), **`hitl_hours`** (human attention actually spent supervising the run — observable), **`tokens_k`** (a mapping of `total` plus the `input`/`output`/`cache_write`/`cache_read` classes), and **`cost`**. This is enforced, not optional. **`cost` is never entered — it is derived once, at capture time, from `tokens_k × the model's per-class rate table` and frozen; `set-actual`/`set-estimate` reject a `--cost*` flag outright (exit 2), and `verify` recomputes and fails on any mismatch.** Token/cost actuals are captured **exactly** under Claude (read from the session transcript `usage` fields, split by class, priced via `--model`) and as `N/A` (never guessed) under other runtimes (e.g. Copilot — capture what's exposed, else `N/A`). `man_hours` and `hitl_hours` are always observable/assessable and must always be real numbers, on every runtime. The rule, runtime detection, and the exact capture procedure live in each PM skill's `references/metrics-contract.md`.

**Estimates are a bottom-up roll-up.** Per metric, `story.estimate = base_band(class) × scope_ratio × fix_mult`. For `tokens_k` the band is **fresh tokens only** (`input + output + cache_write`) and the scope ratio is measured fresh-against-fresh; `cache_read` is projected from the observed mix on top, never banded, because it tracks corpus × agent count rather than story size — folding it in made the ratio compare a cache-inclusive actual to a fresh band, ~1000× apart, and silently poisoned the affected buckets.  `epic.estimate = Σ story (entry) estimate + calibrated epic-closure band + calibrated orchestration band` — no sprint level (ADR-0016). An epic estimate is *defined as* the sum of its children + closure + orchestration, so it reconciles by construction. `cost` has no band of its own — it is priced from the rolled-up `tokens_k` total (split across classes by the observed or cold-start mix) rather than banded and calibrated independently, so it can no longer drift apart from the token estimate it prices. The fix reserve `F` (default 1.25) is a **cold-start prior only** — it fills the gap before a component has ≥3 calibration samples, then the learned ratios (which already encode fix overhead) supersede it; stacking the two would double-count fixes. **Orchestration is a fourth calibration component** (alongside scope, closure, and fix), at epic level, learning a *fraction* of children's actuals rather than a ratio — its band ships unseeded, with nothing to measure a ratio against until `set-actual --block orchestration` records real observations. Full model in `references/metrics-contract.md`.

For the fields the skills write, see `references/status-files.md` §12 (4.x sidecars) and §4 (3.x nodes), carried by the PM skills (`l3io-execute`, `l3io-plan`). No `SKILL.md` contains schema — they are routers.

**Artifact paths** are v7's: an initiative's tickets, leaf files and plans under `{output_folder}` (`status-files.md` §12). A 3.x project's `{implementation_artifacts}/epic-XX/sprint-YY/stories/` tree is the migration's input.

**Phase status line**: Every subagent must end with:
```
DONE — [brief metrics]
BLOCKED: [one-line reason]
FAILED: [one-line reason]
```

**Quality gates**: on v7 the review of a build is `bmad-build-auto`'s own, invoked `thorough` (every lens), and an epic's acceptance is `bmad-retrospective`'s verdict, read from its document's frontmatter. `l3io-execute` adds no review or fix loop around either (ADR-0017), so `max_fix_iterations` is gone from both PM skills' `customize.toml`. A `rejected` verdict leaves the epic's tickets at `built` and halts that epic; moving them to `done` anyway would be a risk acceptance, which is the user's alone (an **absolute** halt).

**`work_type` is gone with the 3.x plan phases it gated (ADR-0009).** The phase matrix lived in `step-01-classify-work.md`, deleted in Task 4.8 with the full plan; v7's tickets carry no work type and l3io gates no phase of its own. `business_ac_required` still names work types, read against a v7 leaf by the readiness check.

**Stories carry business ACs as well as technical ones (ADR-0010).** `## Business acceptance criteria` (`Outcome` with a resolving `Spec:` pointer, `Non-goals` with none) sits above `## Technical acceptance criteria`. REFINE writes it for **every** ticket; `modules.l3io-pm.business_ac_required` (scalar, default `"CODE,MIXED"`) decides only whether a missing or weak section *blocks*. A story with no business section is pre-business: INFO under `--all`, a failure only under `--story --business required`. **Never rename `TAC_HEADING`** in `spec-align.py` — `check_story()` treats a story lacking that exact h2 as pre-provenance and skips the rest of it, which is loud under `--story` but **silent** under the `--all` closure sweep, taking the business ACs unchecked with it. Changing that heading is a migration, not a rename. REFINE writes the sections from the canonical dimension reference, `skills/_shared/ac-dimensions.md`, which `l3io-execute` declares as Sofia's `persistent_facts` entry; check 13 compares both `spec-align.py` tuples against it.

**Readiness gates (shift-left)**: the **story technical-AC gate** — six dimensions (interfaces/data model, error and edge handling, observability, security, testability, and an **existing-library check**), each satisfied or marked N/A with a reason, always enforced — runs inside Sofia's validate as `l3io-check-technical-ac` (Task 4.4), with `spec-align.py check-pointers --story-file` checking each dimension's `Spec:` line. The **epic architecture gate** left `l3io-execute` with its 3.x phases and is now `l3io-arch`'s design review (`scripts/reviewers/epic-design-review.md`), which wire appends to `bmad-architecture`'s `finalize_reviewers` as `l3io-arch-design-review`: it runs at every Reviewer Gate that workflow runs (Finalize, Validate, headless), so it gates an epic's design when its architecture is drawn rather than after the epic is planned. The **epic-closure spec sync** is `l3io-fact-spec-sync`, a `persistent_facts` entry on `bmad-retrospective` (`l3io-execute`'s declared `scripts/facts/spec-sync.md`): decision records go to `docs/adr/`, and a decision that departs from an architecture spec becomes a spec-reconciliation action item naming the section and the replacement text. **Applying it is a manual step at this pin, by design:** the retrospective's only writes are its document and the decision records the user approved (`bmad-retrospective/workflow.md:101`, `references/acceptance-verdict.md:16-25`), so no hook of ours may edit a spec from inside it; the user applies the item through `bmad-architecture`'s update intent, where the design review runs. The 3.x `spec-align.py` ledger subcommands (`sync-plan`/`propose`/`commit`/`reject`/`check-stale`) are not coming back. The `bmad-customize` overlays in `l3io-arch-review/assets/customize-architect.md`, including the legacy `bmad-create-story` one, are deleted; wire replaced them. Design of the spec index: `docs/superpowers/specs/2026-09-11-spec-alignment-design.md`.

**Halts with a determinable remedy self-heal (ADR-0012).** No classified `BLOCKED:` site in the shared step files is remediable today: the four that were (artifact-only stories, legacy layout, a moved `implementation_artifacts`, multiple layouts) lived in the 3.x activation and plan steps Task 4.8 deleted. The contract stands for the next one: **one attempt per site per run**, recorded before the remedy runs; a recurrence halts naming what was tried; the attempt record is **in-run memory**, void if a site moves into a dispatched subagent. **Two refusals are absolute and may never be converted**: another session's epic (its `l3io/<slug>` branch checked out in another worktree, which the run never removes or reuses), and accepting work a gate refused (moving a `rejected` epic's tickets to `done`). `references/auto-remediation.md` (canonical `skills/_shared/auto-remediation.md`) is the contract and holds the two tables; **`check:docs` check 36** gates *classification*, not implementation: it fails if a `BLOCKED:` site is unclassified, a row is stale, or a Remediable row's remedy is absent from its step file or appears only inside `BLOCKED:` blocks. The doctor's own halts are outside its scope and named in that file's Scope paragraph. A converted halt moves its table row from `Halts` to `Remediable` in the same commit.

**Parallelism**: `l3io-execute` runs a wave's epics at once, up to `max_parallel_subagents` (default 4), each on its own branch `l3io/<slug>` in its own git worktree beside the checkout — but only when git tracks the `_bmad/` files a build runs (`render_skill.py`, `tickets.py`, `pm_status`); otherwise `dispatch-plan.py` caps the run at one epic at a time in the main checkout and says why (ADR-0022). Tickets inside an epic are always sequential: they share a tree, and `bmad-build-auto` demands a clean one. Every worktree shares the main checkout's project state root through `--git-common-dir`, so `flock` guards it; the run commits that state (`close-commit.py state`) before each merge and at the end, since a build in a worktree can commit only its own ticket sidecar. A wave starts only when the previous one is merged, and the run pauses for the user at each epic in `plan-graph.py waves`' `gates` — an epic a later ticket or epic file waits on for closure, since `tickets.py` holds the dependent until the container reads `done`, which Sofia sets on the user's word. A dependency declared only in `[[epic]] after` orders the waves and gates nothing. **`parallel_mode`, `parallel_ceiling`, and `safe_batch_size` are not implemented** (`docs/superpowers/specs/2026-08-17-adaptive-parallelism-design.md`).

**Estimation calibration (decomposed, v2, mechanized)**: `pm-status.py` runs the calibration loop itself — this is not orchestrator prose. `build-close` (a ticket) and `epic-close` (an epic's closure) — and on a 3.x tree `set-actual` — derive and append a plan-vs-actual sample to `{state_root}/pm-calibration.yaml` (`version: 2`) after every successful actuals write; `--no-calibrate` opts a call out, and a failed derivation only warns on stderr — it never fails the actuals write. `estimate-story` and `estimate-rollup` read the file back and apply whichever ratios are active. It learns **three separable components**, each per metric: `scope` (story sizing, per classification), `closure` (epic-level closure overhead; a 3.x file's sprint samples load and are never read), and `fix` (cost of the fix loop, per classification, as `clean`/`reworked` man-hour cohorts). `scope` and `closure` each activate once a metric has **≥3 samples** (exponential-decay weighted, decay 0.8); `fix` needs **both** cohorts at ≥3 — one cohort alone cannot form a ratio, so a project where every story needs rework never activates `fix` and correctly stays on the cold-start prior (ratio 1.0 for `scope`/`closure`, fix `F`=1.25). At estimate time the components combine as the roll-up above. `token`/`cost` ratios only accumulate from runs with **real** actuals (Claude runs); `N/A` entries are skipped — never guessed. `granularity` is a field stored in the calibration file itself, not a step-file or `customize.toml` binding — nothing currently varies it, so every project runs `"story"` granularity in practice. The scope-vs-fix split uses `completion_evidence.fix_iterations`, checked only when the estimate carries a `fix_factor` — an estimate recorded before `estimate-story` existed (no `fix_factor`) is `provenance: legacy` regardless of iterations, and contributes no fix-cohort sample: zero iterations gives an exact scope sample and feeds the `clean` fix cohort; a nonzero count, or the field being absent entirely, falls back to backing fix out of the actual (`actual × fix_factor / estimate`), and only a nonzero count also feeds the `reworked` cohort — an absent field backs out the scope ratio but updates no cohort. A legacy `version: 1` file is auto-migrated the first time a sample is appended (original kept as `pm-calibration.yaml.v1`); read-only commands (`calibration show`, `estimate-story`, `estimate-rollup`) never migrate it. The file lives at `{implementation_artifacts}/state/pm-calibration.yaml`, is committed, and is a shared append target across every epic and parallel subagent — every write takes flock. Full spec in `references/calibration-model.md` (split out of `metrics-contract.md`, which keeps a short §8 summary — `pm-status.py` performs the whole loop, so a normal run never loads the model).

## Dependencies (consumer repos)

Each dependency site resolves between two names in a deliberately chosen order — for some the
6.12 name is tried first, for others the legacy name is tried first because its presence is
positive evidence about the install. No site requires a fixed minimum BMad version.

Required, from v7's `method` module, by `l3io-execute`: `bmad-build-auto` (one run per ticket),
`bmad-retrospective` (one headless run per epic) and `bmad-agent-po` (Sofia: the ticket tree,
and the Tracker sync and Status procedures the run follows). `bmad-code-review`,
`bmad-qa-generate-e2e-tests` and `bmad-review` are optional now that nothing here dispatches
them. `bmad-sprint-planning` is optional too: its only caller was `l3io-plan`'s 3.x readiness phase, retired in Task 4.8.

Implementation is `bmad-build-auto`'s alone: `l3io-execute` carries no dev agent and no
`bmad-create-story`/`bmad-dev-story` fallback chain (ADR-0018), and `l3io-plan` no longer
elaborates stories: REFINE is Sofia's.

**`deprecated` is a distinct inventory status from `removed`, and the difference is load-bearing.**
`bmad-create-story`, `bmad-dev-story` and `bmad-review-adversarial-general` are **still shipped**
by BMad 6.12.0 as shims — the first two retaining their full bodies — with `bmad-build` named as
the official implementation method; `bmad-build` and `bmad-build-auto` are declared in the
inventory as optional. Encoding those three as `removed` made three of six `removed` entries
false, and the two guards over the inventory could not tell: one compared it to files on disk,
the other to prose. `bmad-deps.py` now derives shipped-ness from `_bmad/_config/skill-manifest.csv`
and reports any inventory claim the manifest contradicts, so the annotation is checked against
the install rather than asserted. A `deprecated` entry that does not resolve is reported as such,
never as "absent (optional — its phase self-skips)". See ADR-0006's amendment.

Optional — UX review: the legacy `bmad-ux-review` is preferred when installed, because it is purpose-built for review; `bmad-ux`'s opt-in Reviewer Gate is used only when the legacy `bmad-ux-review` is absent. UX review phases skip gracefully when neither is present. (`bmad-testarch-atdd` was previously listed here, but no step file ever invoked it; its gating machinery has been removed.)

Required intra-package: `l3io-util` (this package's utilities module — provides
`l3io-doctor`). The PM skills forward migrations, health checks and the progress dashboard
(`/l3io-doctor stats`) to it, so they would fail without the doctor installed. The 6.x
`dependencies:` declaration lived in the retired `l3io-setup`'s `module.yaml`; on v7 it becomes
a `required_skills` entry in `bmod-l3io-pm/bmod.toml` (Task 2.3 of the Phase 2 plan), so `bmad
setup` names `l3io-doctor` as an unmet requirement, with an install command, when only `l3io-pm`
is installed. `.claude-plugin/marketplace.json` is gone on this branch; v7 does not read it.

Optional intra-package: `l3io-arch` and `l3io-sec`. Each ships its lens files, and `l3io-arch`
its standards and design review, as declared scripts; wire's entries for a module are
`skipped` until `bmad setup <module>` has installed them, so an absent module costs nothing.

Run `/l3io-doctor check-deps` in a target project to see exactly what resolved there — the
declared inventory lives at `skills/l3io-util/l3io-doctor/assets/bmad-dependencies.json`.
Run `/l3io-doctor version` to see which l3io version is installed, per skill and per module,
and whether the two declared `pm_status` copies agree.
