# l3io-util Reference

Project state diagnostics, progress reporting, and housekeeping utilities for BMad projects.

## Overview

`l3io-util` provides project state diagnostics, the progress dashboard over BMad v7
initiatives, one-time migrations, and repeatable maintenance for l3io's files. It is
standalone — no orchestrator relationship. Run the single skill `/l3io-doctor` with no
argument for a **project health check** that scans for all known issues and proposes the
right actions in priority order behind one confirmation, or pass a keyword to jump straight
to a mode.

Skill: `/l3io-doctor [command]`.

> **Renamed in 2.1.0.** This skill was `l3io-util-cleanup` through 2.0.x. "Cleanup"
> described about three of its modes, while the default behavior is a
> diagnose-report-repair health check. The deprecated `/l3io-util-cleanup` forwarder has
> been **removed in 3.0.0**. See [Upgrading](upgrading.md). Update any scripts or docs that
> still invoke the old name.

## Configuration

Config is resolved via `{project-root}/_bmad/scripts/resolve_config.py` — `core.*` for shared settings, `modules.l3io-util.*` for this module, and `modules.l3io-pm.*` for the artifact paths it reads. No section is required; every value has a default.

**Runs `l3io-util`'s own `pm_status` copy.** This skill declares the `pm_status` package in its `bmod.toml` (`[skill] scripts`), and BMad v7's `bmad setup l3io-util` installs it at `{project-root}/_bmad/l3io-util/scripts/pm_status/__main__.py`, rebuilding it on every setup. Before dispatching to any mode (skipping only for `help`/`?`), activation checks that copy exists and halts naming `bmad setup l3io-util` when it does not — several modes invoke it directly, and a missing copy would otherwise fail inside `uv run` with a traceback that names nothing the user can act on.

Key settings (with defaults):

- `output_folder` — default: `{project-root}/_bmad-output`
- `implementation_artifacts` — default: `{output_folder}/implementation-artifacts`
- `planning_artifacts` — default: `{output_folder}/planning-artifacts`
- `harvest_exclude_dirs` — default: `[]`. Extra directories excluded from the `harvest-debt` source sweep, on top of the built-in exclusions (`node_modules`, `.git`, `dist`, `build`, `vendor`, `.venv`, `target`, `out`, and the artifact directories).

## Commands

### Diagnostic (read-only — never changes files)

| Command | What it does |
|---------|--------------|
| *(no argument)* | Project health check — runs all checks and, after one confirmation, executes the flagged actions in priority order. |
| `check` / `status` | Same scan as the health check, but reports the findings table and exits without changing anything. |
| `stats` (aliases `backlog`, `issues`) | Progress dashboard over BMad v7's work-item tree. For each initiative under `{output_folder}` (or the one named) it runs `pm-status.py report --project-root … --initiative-dir …`, which reads v7's own `tickets.py status` and joins l3io's sidecars, the event log and the build spool: each epic's status, lane and built count, the tickets not yet `done`, estimates and actuals, `tickets.py`'s problems, and any build whose bracket has been open past `--stall-minutes` (default 15). It then appends v7's backlog (`{output_folder}/backlog/`) counted by type and state, its open tickets listed, and calibration state from `{output_folder}/l3io/pm-calibration.yaml`. The `backlog` and `issues` aliases always print that table; both views come from one `tickets.py status` call over `backlog/`. See [l3io-pm reference § Progress Reporting](l3io-pm-reference.md#progress-reporting). |
| `check-deps` | Verifies every BMad skill this package dispatches resolves in this project, reports deprecated shims still in use, and names optional dependencies whose phases will self-skip. Read-only. |
| `version` (aliases `--version`, `which-version`) | Reports which l3io-extensions version this project is running, read from the manifests the installer writes — per skill, and per module for the four module homes. Exits non-zero on a tree carrying more than one version, which is a partial or interrupted install. This is the mode that answers "which l3io am I on?": `_bmad/_config/manifest.yaml` records a custom-source module's `version` as the git ref that was cloned, so a project tracking the default branch reads `version: main`, which is accurate and useless. With `--project-root` it also lists the two `pm_status` copies BMad v7 installs (`_bmad/l3io-pm/scripts/pm_status/`, `_bmad/l3io-util/scripts/pm_status/`) and reports them disagreeing as a `pm_status SKEW` finding, exiting non-zero; the health check's Check 18 runs the same report. Read-only. |
| `install` (aliases `upgrade`, `uninstall`) | Runs the right BMad command for the intent, and refuses the wrong one. **`upgrade`** uses `--action quick-update`, which derives the module set and the IDE list off the existing install, preserves settings, and performs no selection-driven deletion. **`install`** is first-install only and refuses an existing install, because the form it must use passes `--modules` and `--tools`, which are authoritative: BMad `fs.remove`s every installed module and runs `cleanupByList` over every IDE tree those flags do not name, without confirming — two repos here were told to use that form for an upgrade and one lost the per-module `config.yaml` for core, bmm, cis and tea. **`clean`** removes only this extension's payload, decided file by file by SHA-256 against each skill's `payload-manifest.json`: a matching hash is ours and removable, a differing hash is reported and **kept** because somebody edited it, and anything absent from the manifests is never touched. Project state under the artifacts tree appears in no manifest, so it is out of scope by construction. Dry run until `--apply`; confirms before every action. The BMad release is pinned, overridable with `--bmad-version`. |

### One-time migrations

| Command | What it does |
|---------|--------------|
| `migrate-state` | Migrates a legacy state layout (flat `sprint-status.yaml`, the three-file split, or legacy per-epic `_bmad/state/`) to the 3.x sharded state tree. The source is renamed to `.legacy`, never deleted. A migration that would move nothing is refused rather than run. Each node is written through `pm-status.py import-node`, which also carries the source's `goal`, `superseded_by` and `depends_on`; estimates and actuals follow through `set-estimate` and `import-actual`, and any other field the reader saw is reported on stderr as a `WARN` naming the record and the value. The 3.x tree is read only by this mode — no 4.x skill reads or writes it. |
| `migrate-adrs` | Moves ADRs from the old per-epic home (`{implementation_artifacts}/epic-*/arch/`) to `{project-root}/docs/adr/`, the one ADR home (ADR-0005). Plans first, confirms, then commits once. Three outcomes per ADR: a **plain move** when `docs/adr/` has no such number; a **collision** (same number, *different* slug — two real decisions competing) which keeps the `docs/adr/` number and renumbers the epic copy, rewriting mentions only inside that epic's artifacts; and a **duplicate** (same number **and** slug — the epic copy is a leftover of an ADR already migrated), which is **never moved and never renumbered**, only reported for you to diff and delete. A run where every ADR is a duplicate does nothing and says so. |

### Ongoing maintenance (safe to repeat)

| Command | What it does |
|---------|--------------|
| `triage` | Audits v7's backlog (`{output_folder}/backlog/`, plus every epic's `tickets.toml` and l3io's sidecars) with `scripts/audit-tree.py`, read-only: findings 1a–1l re-expressed over v7's tree (1a, 1e, 1g and 1j have no v7 meaning and are never reported), marker evidence for each ticket citing a `code-marker (<file>:<line>)`, and an optional agent review. Every repair is a proposal for Sofia (`bmad-agent-po`) — BOARD `mark`/`move`, REFINE — except an orphaned plan sidecar with one heir, which `sidecar-reconcile` moves on confirmation. The 3.x spec pass went with the issues ledger in 4.0.0. |
| `redrive` | Rebuilds the `scope` and `fix` calibration components from the story nodes on disk — repairs samples poisoned by a fixed defect that once stored `fix_iterations` as a string and misclassified them as `backout` instead of `exact`. Backs up the calibration file first (only if no backup already exists); `closure`, `orchestration`, and `token_mix` are untouched. Safe to run repeatedly. |

### Source & external sync

| Command | What it does |
|---------|--------------|
| `harvest-debt` | Sweeps the source tree for `bmad-defer:` deferred-shortcut markers and proposes each new one as a candidate `bug-<slug>` ticket (with a `code-marker (<file>:<line>)` reference) for Sofia to file in v7's `backlog/`. It writes no leaf. Language-generic, re-runnable (dedupes against the backlog's `code-marker` references). |
| `update-ai-rules` | Rewrites any reference to a legacy state layout (flat `sprint-status*.yaml`, the three-file split, or `_bmad/state/`) in the project's AI instruction files (`CLAUDE.md`, `.github/copilot-instructions.md`, `GEMINI.md`, `AGENTS.md`, `.cursorrules`, …) so they describe the current layout on BMad v7 — v7's ticket tree, l3io's sidecars beside it and `{l3io_state_root}`. The 3.x sharded tree and its `issues.yaml` are legacy references too. Creates the **currently running** AI system's instruction file if it does not exist; never creates one for another AI system. |

### BMad customization layer — specified, not shipped

There is **no `overlay` keyword** on `/l3io-doctor`. The mode was specified and then held
back, because `skills/l3io-util/l3io-doctor/assets/overlays/` ships no overlay TOML: all three of its
actions (`list`, `diff`, `verify`) would report "nothing ships yet" by construction. Its full
contract is kept as `skills/l3io-util/l3io-doctor/assets/overlays/overlay-mode.md`, beside the
directory it describes, and Phase 3 of the customization-layer design restores the keyword along
with the content.

**On BMad v7, `wire` and `unwire` are the one place this package writes
`{project-root}/_bmad/custom/`** (ADR-0020). v7 has no customization layer a module
contributes, so attaching l3io's lenses, facts and hooks means writing into the team's
`_bmad/custom/<skill>.toml`. Both are explicit modes, never run implicitly, and they only
ever touch the committed team layer, never a gitignored `<skill>.user.toml`. Everything else
here stays out: the specified `diff` action above stages a file under
`{implementation_artifacts}/` and **prints one `cp` command** for you to run yourself.

### Setup & housekeeping

| Command | What it does |
|---------|--------------|
| `setup` / `configure` | Registers the `l3io-util` module config for the project. |
| `clean-legacy` | Removes migration backup files and directories after confirmation: `*.yaml.legacy` files, the `state/pm-calibration.yaml.v1` calibration schema backup (beside the live calibration file, not under `_bmad/`), `_bmad/pm-calibration.yaml.legacy`, the `_bmad/state.legacy/` directory, and the `_bmad/migration-backup/` directory. |
| `wire` | Adds the entries in `assets/wire-in.toml` to the team's `_bmad/custom/<skill>.toml` files (ADR-0020). Round-trip safe (comments, key order and hand-added entries survive) and idempotent. Three kinds: a **keyed** table appended to an array of tables by `code`/`id` — a team entry with the same identity wins, and ours must start with `l3io-` so it can never replace a BMad default; a **list** string appended once; a **scalar** single-value hook set only when absent or empty. A non-empty team hook is **refused** (exit 3), naming the file, key and both values, and nothing is written for that entry. Records what it added in `{output_folder}/l3io/wire-in.json`. |
| `unwire` | Removes exactly what the ledger records. A file untouched since `wire` gets its pre-wire bytes back (or is deleted, if `wire` created it); a file the team has edited since loses only l3io's entries, each only while it still equals what `wire` wrote. Never removes a team entry. |
| `help` / `?` | Prints the command list and exits — no project scan. |

## `pm-status.py` subcommands this skill runs

The doctor runs `l3io-util`'s declared `pm_status` copy (above) because its modes call it
directly. These are the subcommands they invoke; the authoritative signature for each one is
in the [l3io-pm reference](l3io-pm-reference.md), which documents the whole CLI.

| Subcommand | Used by | For |
|---|---|---|
| `report` | `stats`, the health check (Check 19) | Progress over one v7 initiative: `tickets.py status` joined with l3io's sidecars, the event log and the build spool. The tree, the stalled builds and `tickets.py`'s problems are rendered from its output rather than duplicated here. |
| `import-node` | `migrate-state` | Creates a missing 3.x state node from a migration record, with its `goal`, `superseded_by` and `depends_on` (`--depends-on` repeats) in the same write; idempotent by skip (an existing node is left exactly as-is, no event appended). |
| `set-estimate` | `migrate-state` | Writes a migrated node's estimate after `import-node` lands it. |
| `import-actual` | `migrate-state` | Writes a migrated node's actual as `runtime: other` with tokens `N/A` and no calibration sample — fixed, not optional, so a bulk import cannot poison the learned ratios. |
| `calibration` | `redrive`, `stats` | `redrive` rebuilds the `scope` and `fix` components through it; `stats` reads the file's state with `show`. |
| `dispatch` | `triage` | Opens and closes the dispatch record for a subagent the mode fans out to, in `{l3io_state_root}`. |
| `sidecar-reconcile` | `triage` | Moves an orphaned plan sidecar (finding 1l) beside the one same-named plan it belongs to, and commits what it moved. |
| `notice` | `references/config-resolution.md` (shipped, not invoked by the doctor) | Records a one-time-ever advisory in `{state-root}/.notices.yaml`. The contract ships with every skill; only `l3io-execute` and `l3io-plan` call it. |
| `sync-agent-instructions` | `upgrade`, `uninstall`, module setup, the health check (Check 17) | Writes, refreshes (`--apply`), checks (`--check`) or strips (`--remove`) the marker-wrapped l3io block in the running harness's AI instruction file. **Never CREATES** a block in another harness's file, but **always REFRESHES** one already there — a project that changes harness keeps our block where the old one read it, and a stale copy of our own instructions is not neutrality. Refreshes rather than removes, since the other harness may still be in use. Idempotent; never deletes the file; exit 1 from `--check` means the block is absent for this harness, exit 2 leaves the file byte-unchanged, exit 3 means another harness's file holds a stale copy that `--apply` repairs. |

## Project Health Check

The default mode runs eighteen numbered read-only checks (Check 13 is retired), prints a findings table (✓ pass / ⚠ flagged), and — unless invoked as `check`/`status` — proposes the flagged actions in a fixed priority sequence behind a single confirmation. The checks, with the action each proposes:

1. Status file naming (`rename-active`)
2. 3.x state layout (`migrate-state`) — a legacy flat or per-epic layout, more than one layout at once, or the 3.x sharded tree on its own, which no 4.x skill reads
3. Deferred code markers (`harvest-debt`)
4. AI instruction references (`update-ai-rules`)
5. Migration backup files (`clean-legacy`)
6. Epic directory padding (`rename-epic-dirs`)
7. Poisoned calibration provenance (`redrive`)
8. Backlog integrity and audit (`triage`)
9. Lock files tracked in git (`untrack-locks`)
10. ADR home and register (`migrate-adrs`)
11. Spec pointers (report only)
12. ADR links (report only)
13. Retired in 4.0.0 (unconfirmed spec changes; the issues ledger it read is gone, and the number is not reused)
14. Spec index freshness (report only)
15. BMad dependency resolution
16. State reachable and tracked (report only) — `{l3io_state_root}` ignored by git, and on the migration path a 3.x tree orphaned or ignored
17. Agent instruction block
18. `pm_status` version skew (report only)
19. Initiative progress (v7) — runs `report` over every initiative and reports stalled builds and `tickets.py`'s problems (report only)

The action sequence:

`rename-active → rename-epic-dirs → migrate-state → harvest-debt → migrate-adrs → triage → update-ai-rules → redrive → untrack-locks → clean-legacy`

Three of those actions are **not modes** and have no keyword — the health check runs each one
inline, from the check that detects it:

- `rename-active` (Check 1) renames `sprint-status-active.yaml` → `sprint-status.yaml`, content
  unchanged. It refuses on a conflict and renames back if the result does not parse.
- `rename-epic-dirs` (Check 6) renames legacy two-digit `epic-{nn}/` artifact directories to
  the three-digit `epic-{nnn}/` form, skipping any whose destination already exists.
- `untrack-locks` (Check 9) makes sure `.gitignore` has a `*.lock` line in each state root
  holding a tracked lock file (`{implementation_artifacts}/state/`, `{output_folder}/l3io/`),
  then runs `git rm --cached` over those `*.lock` files. The files stay on disk, and the
  removal is staged for your next commit.

Each executed action runs its full mode (dry-run + verify still shown); per-mode confirmations are suppressed since the user already confirmed — except `triage`, which keeps its own confirmations, because every triage action resolves or rewrites backlog items the single confirmation did not show item by item. If any action fails, the sequence stops and reports.

## Safety Rules

- Dry-run first — the full plan is shown before any file changes.
- Never overwrite an existing destination; on conflict, keep the source and record it.
- `rename-active` re-parses the renamed file and restores the original on a parse failure.
- Reference updates only auto-apply for unambiguous single-target matches; ambiguous references are recorded for manual review.
