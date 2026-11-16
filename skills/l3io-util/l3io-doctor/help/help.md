# l3io-util knowledge

This document covers the `l3io-util` module: what its one skill gives the user, when to recommend it, and what to offer next. The full reference is `docs/l3io-util-reference.md` in this package's source repository.

## What the module is

One skill, `l3io-doctor`, the diagnostics and housekeeping tool for l3io-pm projects. Run without arguments it scans project state for every known defect and proposes the fixes in their correct execution order, behind one confirmation. `l3io-pm` requires it.

## The skill

| Mode | For | When to recommend |
|---|---|---|
| (no argument) | A health check: every finding in a table, then an ordered fix plan. Changes nothing unless a fix is confirmed. | After installing or upgrading, before any epic run, or whenever something in l3io-pm state looks wrong. |
| `stats` | The plan-aware progress dashboard: phase, epic, sprint and story with dwell times and stuck-item flags, backlog size by severity, the last closed sprint and epic, and calibration state. | "Where are we", "what is stuck", "show progress". |
| `check-deps` | Verifies every BMad skill this package dispatches resolves in this project, reports deprecated shims still in use, and names the optional dependencies whose phases will self-skip. | A phase skipped unexpectedly, or a fresh install. |
| `check-pm-status` | Compares the installed pm-status helper against this doctor's version: current, stale, or absent. | A state write misbehaves after an upgrade. |
| `version` | Reports which l3io-extensions version the project runs, per skill and per module, and fails on a tree carrying more than one. | "Which l3io am I on", or after an interrupted upgrade. |
| `upgrade` | Runs the right command to install, upgrade or remove this extension, and confirms before acting. | The user asks to install, upgrade or uninstall l3io. |

## After a mode finishes

| Just finished | Offer next |
|---|---|
| A health check with findings | The fix plan it proposed; run it on confirmation. |
| A clean health check | `l3io-plan` or `l3io-execute`, whichever the project is ready for. |
| `stats` | `l3io-execute` to resume stuck or queued work. |
| `check-deps` with missing skills | The install command it printed. |
