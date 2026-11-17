# l3io-util knowledge

This document covers the `l3io-util` module: what its one skill gives the user, when to recommend it, and what to offer next. The full reference is `docs/l3io-util-reference.md` in this package's source repository.

## What the module is

One skill, `l3io-doctor`, the diagnostics and housekeeping tool for l3io projects on BMad v7. Run without arguments it scans project state for every known defect and proposes the fixes in their correct execution order, behind one confirmation. `l3io-pm` requires it.

## The skill

| Mode | For | When to recommend |
|---|---|---|
| (no argument) | A health check: every finding in a table, then an ordered fix plan. Changes nothing unless a fix is confirmed. | After installing or upgrading, before any epic run, or whenever something in l3io-pm state looks wrong. |
| `stats` | Progress over BMad v7 initiatives: each epic's status, lane and built count, open tickets, estimates and actuals, stalled builds, plus backlog size by severity and calibration state. | "Where are we", "what is stuck", "show progress". |
| `check-deps` | Verifies every BMad skill this package dispatches resolves in this project, reports deprecated shims still in use, and names the optional dependencies whose phases will self-skip. | A phase skipped unexpectedly, or a fresh install. |
| `version` | Reports which l3io-extensions version the project runs, per skill and per module, and fails on a tree carrying more than one. | "Which l3io am I on", or after an interrupted upgrade. |
| `upgrade` | Runs the right command to install, upgrade or remove this extension, and confirms before acting. | The user asks to install, upgrade or uninstall l3io. |
| `wire` | Attaches l3io's lenses, facts and hooks to the team's `_bmad/custom/<skill>.toml` files, never overwriting a team value, and records what it added. | After installing, to make l3io's capabilities run inside BMad's own skills. |
| `unwire` | Removes exactly what `wire` added, and nothing the team wrote. | Before uninstalling l3io, or to detach it from BMad's skills. |

## After a mode finishes

| Just finished | Offer next |
|---|---|
| A health check with findings | The fix plan it proposed; run it on confirmation. |
| A clean health check | `l3io-execute` to run an initiative Sofia has planned, or `l3io-plan` to estimate one first. |
| `stats` | `l3io-execute` to run queued tickets; for a stalled build, the user decides whether to re-run it. |
| `check-deps` with missing skills | The install command it printed. |
