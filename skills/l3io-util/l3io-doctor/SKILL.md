---
name: l3io-doctor
description: Diagnostics and housekeeping for l3io projects on BMad v7. Use when the user wants a health check of the project (it scans for every known problem and proposes the fixes in order), a progress dashboard over BMad v7 initiatives with stalled-build flags, the issues backlog, to triage the backlog (audit and close what is already fixed), to harvest deferred-shortcut code markers into the backlog, to verify BMad dependencies or the installed l3io version, to install, upgrade or uninstall the extension, to wire l3io's hooks into BMad's skills or unwire them, to migrate a legacy l3io state layout, to move ADRs to docs/adr/, to rebuild poisoned calibration samples, to update AI instruction files, or to remove migration backups. Run without arguments for an auto-diagnostic.
---

# l3io-doctor — Project State Diagnostics & Utilities

## Overview

Migration and housekeeping utilities for BMad artifacts.

**Default behavior (no argument, or text matching no keyword below):** Runs a project health check — scans for all known issues, reports findings in a priority table, and proposes the right actions in the correct execution order. One confirmation runs them all.

**A REMOVED keyword is refused by name, never treated as unrecognized text.** Check the
argument against this table *before* falling through to the health check. Print the
replacement and stop; propose nothing.

- Removed **normalize** → `migrate-state` on a legacy split layout, which it reads directly;
  nothing otherwise.
- Removed **migrate-schema**, **split-status** and **reconcile-status** → `migrate-state`,
  which reads the flat and split layouts directly.
- Removed **bootstrap-state** → on BMad v7 the work-item tree is Sofia's (`bmad-agent-po`);
  nothing here creates state nodes from story files.
- Removed **sort-status** → nothing; the 3.x tree whose naming it validated is read only by
  `migrate-state`.
- Removed **clean-layout** and **layout-cleanup** → nothing; v7 lays out its own tree.
- Removed **rename-active** → just `/l3io-doctor`; Health Check 1 detects the old
  filename and renames it inline.
- Removed **rename-epic-dirs** → just `/l3io-doctor`; Health Check 6 detects two-digit
  `epic-{nn}/` directories and renames them inline.
- Removed **overlay** → nothing yet; held back until `assets/overlays/` ships overlay TOML.
- Removed **cleanup** → the skill was renamed; use `/l3io-doctor`.

> Deliberately a list and **not a table**, and the removed names are bold rather than
> code-formatted. `DOCTOR_ROUTING_ROW_RE` matches any SKILL.md table row whose first cell is
> backticked tokens, so writing this as a table added every one of them to the keyword set
> check 25 derives — neutering the guard that catches a stale keyword. Its scope-attack test caught it.
> Keep this shape.

> Falling through meant someone typing a keyword that used to work got a health check and a
> proposal to write files they never asked about — the argument silently ignored. `backlog`
> and `issues` are deliberately NOT here: they are live aliases for `stats`.
>
> This table duplicates `docs/upgrading.md`'s removed-keyword mapping, which is the
> user-facing copy. **No check enforces that the two agree** — `check:module`'s help-registration rule reads
> the Menu column of the routing table below, not this one. Stated rather than implied,
> per `CLAUDE.md` §3: if you remove a keyword, edit both.

Modes (pass as argument to skip directly to that mode):

**Diagnostic (read-only)**
- **`check` / `status`:** Read-only health check — same diagnostic scan as the default but prints the findings table and exits without prompting to make changes. The full set of findings, their severities, and their remedies is defined in `steps/health-check.md`, not repeated here.
- **`stats`** (aliases **`backlog`**, **`issues`**): Progress dashboard over BMad v7's work-item tree — each initiative's epics and tickets, estimates, actuals and stalled builds (via `pm-status.py report`), plus backlog size by severity, the per-item backlog table from `{pm_issues_file}` grouped by severity, and calibration state. Scope it by naming an initiative; with none it reports every initiative under `{output_folder}`. No files changed.
- **`check-deps`:** Verifies every BMad skill this package dispatches resolves in this project, reports deprecated shims still in use, and names optional dependencies whose phases will self-skip. No files changed.
- **`version`** (aliases **`--version`**, **`which-version`**): Reports which l3io-extensions version this project is running, read from the manifests the installer writes — per skill and, for the four module homes, per module. Exits 3 on a tree carrying more than one version, which is a partial install. This is the mode that answers "which l3io am I on?". With `--project-root` it also lists the two declared `pm_status` copies (`_bmad/l3io-pm/…`, `_bmad/l3io-util/…`) and reports them disagreeing as a finding, which the health check's Check 18 surfaces. No files changed.
- **`install`** (aliases **`upgrade`**, **`uninstall`**): Runs the right BMad command for the intent and refuses the wrong one. `upgrade` uses `--action quick-update`, which derives the module set and IDE list off the existing install and deletes nothing; `install` is first-install only and refuses an existing install, because its `--modules`/`--tools` are authoritative and BMad deletes every module and IDE tree they do not name without confirming; `clean` removes only this extension's payload, decided by SHA-256 against each skill's `payload-manifest.json`, keeping any file a user has edited and never touching project state. Confirms before every action; `clean` is a dry run until `--apply`.

**One-time migrations**
- **`migrate-state`:** Migrates either legacy layout (flat `sprint-status*.yaml`, the three-file split included, or legacy per-epic `_bmad/state/`) to the 3.x sharded state tree under `{implementation_artifacts}/state/`. Preserves originals as `.legacy` files. The 3.x tree is read only by this mode; no 4.x skill reads or writes it.
- **`migrate-adrs`:** Moves ADRs from the old per-epic home (`{implementation_artifacts}/epic-*/arch/`) to `{project-root}/docs/adr/`, renumbering a colliding one only inside its own epic's artifacts; plans first, confirms, commits once.

**Ongoing maintenance (safe to repeat)**
- **`redrive`:** Rebuilds the `scope` and `fix` calibration components from the story nodes on disk — repairs samples poisoned by a fixed defect where `fix_iterations` was once stored as a string and misclassified as `backout` instead of `exact`. Backs up the calibration file first (only if no backup already exists); `closure`, `orchestration`, and `token_mix` are untouched. Safe to run repeatedly — it derives fresh from the same nodes each time.
- **`triage`:** Audits the issues backlog — integrity (`audit-issues`), mechanical evidence (`scripts/audit-backlog.py`), and an optional agent review — and resolves what is already fixed, with evidence, only on confirmation.

**Source & external sync**
- **`harvest-debt`:** Greps the whole source tree for `bmad-defer:` deferred-shortcut markers (the comment crumbs developers and dev subagents leave when they take an intentional simplification) and harvests them into the consolidated `backlog:` list so deferrals do not rot into "later means never." Language-generic — recognizes the comment syntax of every common language. Re-runnable: dedupes against already-harvested markers. Report-only by default; backlog merge is confirmed. Respects `harvest_exclude_dirs` in the `l3io-util` config section for additional exclusions beyond the built-in list.
- **`update-ai-rules`:** Scans for AI system instruction files in the project (`CLAUDE.md`, `.github/copilot-instructions.md`, `GEMINI.md`, `AGENTS.md`, `.cursorrules`, and others) and rewrites any reference to a legacy state layout (flat `sprint-status*.yaml`, the three-file split, or `_bmad/state/`) to describe the current sharded state tree. For files that already exist: updates existing references. For the currently running AI system's file if it does not exist: creates it with a state layout section. Never creates files for other AI systems. Safe to run repeatedly.

**Setup & housekeeping**
- **`wire`:** Attaches l3io's lenses, facts and hooks to the team's `_bmad/custom/<skill>.toml` files — v7 has no customization layer a module contributes. Round-trip safe and idempotent; never overwrites a team value, and refuses (exit 3) on a single-value hook the team already set. Records what it added (ADR-0020).
- **`unwire`:** Removes exactly what `wire` recorded — byte-exact when the file is untouched since, entry by entry when the team has edited it — and never an entry the team wrote.
- **`clean-legacy`:** Removes migration backup files and directories left behind by one-time migration commands — `.yaml.legacy` files, the `{pm_calibration_file}.v1` calibration schema backup in the state root, the pre-migration `_bmad/state.legacy/` directory and `_bmad/pm-calibration.yaml.legacy` file, and the `_bmad/migration-backup/` directory `migrate-state` Stage F's default "move" option relocates everything into. Dry-run first; confirms before deleting. Safe to run once migrations have been verified.

## Conventions

- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## On Activation

**Load exactly one mode file.** Every mode below lives in its own file under `steps/`, and
only the one the argument selects is ever loaded. That is the point of the layout: this skill
carries fourteen procedures and a run needs one, so inlining them all charged every
invocation for thirteen it would not execute. Read this file, match the keyword, load that
one file, and follow it.

**Recognized keywords** — if the user's argument exactly matches any of these, load that
file and follow it:

The **Menu** column records whether that keyword is listed in this module's `help/help.md`,
which is what BMad's `bmad` skill recommends from, and is the source of truth for that
decision — it is not kept anywhere else; `check:module`'s help-registration rule reads this
column and fails on a keyword that is neither listed nor excluded here, so an unrecognized
value fails rather than quietly excluding a mode. `registered` means `help/help.md` names the
keyword. `default` means it is the bare invocation, which `help/help.md` covers by naming the
skill. `health-check` means it deliberately does not: Step HC6 of `steps/health-check.md`
already proposes it and fixes its place in the execution order, so a menu entry would invite
running a migration or a repair *without* the diagnosis that decides whether it is needed.
`not-a-capability` is help output or module setup.

| Keyword | Load | Menu | Notes |
|---|---|---|---|
| `help` or `?` | — | not-a-capability | Print the command list below and exit — no project scan. |
| `check` or `status` | `steps/health-check.md` | default | read-only — scan only, no changes |
| `stats`, `backlog` or `issues` | `steps/stats.md` | registered | read-only — progress over v7 initiatives plus the per-item backlog table |
| `check-deps` | `steps/check-deps.md` | registered | read-only — verify BMad skill dependencies resolve |
| `version`, `--version` or `which-version` | `steps/version.md` | registered | read-only — report the installed l3io-extensions version per skill and per module |
| `install`, `upgrade` or `uninstall` | `steps/install.md` | registered | runs BMad's installer (`upgrade`/`install`) or deletes this extension's payload (`clean`) — every path confirms first; `clean` reports before it changes anything |
| `harvest-debt` | `steps/harvest-debt.md` | health-check |  |
| `redrive` | `steps/redrive.md` | health-check | rebuild calibration `scope`/`fix` from story nodes |
| `triage` | `steps/triage.md` | health-check | audit the backlog and resolve findings already fixed — confirms every write |
| `migrate-adrs` | `steps/migrate-adrs.md` | health-check | move ADRs from the old per-epic home to `docs/adr/` — confirms before writing |
| `update-ai-rules` | `steps/update-ai-rules.md` | health-check |  |
| `clean-legacy` | `steps/clean-legacy.md` | health-check | remove migration backup files |
| `migrate-state` | `steps/migrate-state.md` | health-check | prose around `migrate-engine.py` — confirms before and interprets after the eight-step migration run |
| `wire` | `steps/wire.md` | registered | writes the team's `_bmad/custom/<skill>.toml` — adds l3io's entries, never overwrites a team value (ADR-0020) |
| `unwire` | `steps/unwire.md` | registered | removes exactly what `wire` recorded, nothing a team wrote |
| `setup` or `configure` | `assets/module-setup.md` | not-a-capability | then continue to `steps/health-check.md`. **`install` is deliberately not here** — it routes to `steps/install.md`, because a user typing it means the extension, not this module's config. It was in both rows until 3.2.5, with no precedence rule to separate them. |

**Everything else** (no argument, unrecognized text, or a natural-language description) →
load `steps/health-check.md`.

A mode file may direct you to another mode's file — the health check proposes fixes by
naming the modes that apply. Load each as you reach it; do not pre-load the set. Three
proposed actions are **not** modes and have no file — `rename-active`, `rename-epic-dirs` and
`untrack-locks`: each is a single rename or `git rm --cached` with no caller outside the check
that detects it, and `steps/health-check.md` runs all three inline.


**Help output** — when `help` or `?` is passed, print the contents of
`assets/help-text.md` verbatim inside a code fence and exit. Load that file only when this
keyword selects it; SKILL.md carries just this pointer, not the command list.

Resolve config through BMad core's resolver — full contract in
`references/config-resolution.md`:

```bash
uv run --python 3.11 {project-root}/_bmad/scripts/resolve_config.py --project-root {project-root}
```

If the resolver is missing or fails, BMad core is not installed here — stop and tell the
user to run the BMad installer.

Bind, applying the default when the key is absent:

- `{output_folder}` — `core.output_folder` (default `{project-root}/_bmad-output`)
- `{implementation_artifacts}` — `modules.l3io-pm.implementation_artifacts`
  (default `{output_folder}/implementation-artifacts`)
- `{planning_artifacts}` — `modules.l3io-pm.planning_artifacts`
  (default `{output_folder}/planning-artifacts`)
- `harvest_exclude_dirs` — `modules.l3io-util.harvest_exclude_dirs` (default: none)

The artifact paths come from the **`l3io-pm`** section, not `l3io-util` — all modules share
one artifact tree, and this skill reads the very directories the PM skills write.

An absent `modules.l3io-util` section is normal and is **not** a first-run trigger: this
module declares no required settings. Load `assets/module-setup.md` only when the user
explicitly passes `setup` or `configure`.

Then bind the state paths every mode below uses:

- `{l3io_state_root}` = `{output_folder}/l3io` — l3io's project-wide files on BMad v7: the
  event log, calibration, the ADR register, the build spool
- `{tickets_py}` = `{project-root}/_bmad/method/scripts/tickets.py` — v7's own reader of the
  work-item tree, installed with Sofia (`bmad-agent-po`)
- `{pm_state_root}` = `{implementation_artifacts}/state` — the 3.x tree, and the home of the
  issues backlog
- `{pm_issues_file}` = `{pm_state_root}/issues.yaml`
- `{pm_calibration_file}` = `{pm_state_root}/pm-calibration.yaml` — the 3.x calibration file
  `redrive` rebuilds

**Locate `pm-status.py` before dispatching to a mode** (skip this for `help`/`?` — that
keyword exits above without a project scan or any config resolve). This skill declares the
`pm_status` package for the `l3io-util` module in its `bmod.toml` (`[skill] scripts`), and BMad
v7's `bmad setup l3io-util` installs it at `{project-root}/_bmad/l3io-util/scripts/pm_status/`,
rebuilding that tree on every setup. Seven of the mode files below invoke `{pm_status}`; run
before setup, a missing copy would fail inside `uv run` with a traceback that names nothing the
user can act on. Check first:

```bash
test -f {project-root}/_bmad/l3io-util/scripts/pm_status/__main__.py
```

If absent, halt:
```
BLOCKED: _bmad/l3io-util/scripts/pm_status is not installed — run bmad setup l3io-util
```

Bind `{pm_status}` = `{project-root}/_bmad/l3io-util/scripts/pm_status/__main__.py` for use in
all mode files below.

Bind `{spec_align}` = `uv run {skill-root}/scripts/spec-align.py --project-root {project-root} --planning-root {planning_artifacts} --impl-root {implementation_artifacts} --state-root {pm_state_root} --pm-status {pm_status}`
for health Checks 10–14, triage's spec pass and `migrate-adrs`. It passes no `--spec-paths`,
so it checks the spec set the project's spec index recorded (pm-execute's `spec_paths`).

**Which tree a mode reads.** On BMad v7 the work-item tree — initiatives, epics, tickets — is
v7's and Sofia's; l3io writes only TOML sidecars beside it and its project-wide files under
`{l3io_state_root}`, all through `pm-status.py`. `stats` and the health check read that tree
through `report`. The 3.x tree under `{pm_state_root}` is read only by `migrate-state`; the
backlog verbs (`triage`, `harvest-debt`) and `redrive` still use `{pm_state_root}`.

## Safety Rules

- Dry-run first — show the full plan before changing any files
- Never overwrite an existing destination file
- If destination exists: keep source in place, record conflict
- Reference updates: auto-update only exact old-path matches that map to one known moved file; if ambiguous, record for manual review — never auto-update ambiguous references

## State File Layout

On BMad v7, l3io keeps three kinds of file, none of them hand-edited:

- **Sidecars beside v7's tree**, through `tomlkit`: `<initiative>/tickets/l3io.toml` (a lane
  per epic), `<initiative>/tickets/epic-<slug>/tickets/l3io.toml` (estimates and the epic
  roll-up), and `<stem>-plan.l3io.toml` beside each plan (actuals). v7 owns `tickets.toml`,
  the leaf files and the plans; `pm-status.py` never writes them.
- **Project-wide files under `{l3io_state_root}`**: `events.jsonl`, `pm-calibration.yaml`,
  `adr-register.yaml`, and the gitignored `.inflight/` build spool.
- **The issues backlog** under `{pm_state_root}`: `issues.yaml` and `issues-resolved.yaml`,
  changed only through the `pm-status.py` issue verbs.

The layout is `references/status-files.md`'s. Older layouts — the 3.x sharded tree under
`{pm_state_root}`, a flat `sprint-status*.yaml`, or a per-epic `_bmad/state/` tree — are read
only by `/l3io-doctor migrate-state`.
