# ADR-0013 — 4.x extends BMad v7; it does not replace it

**Status:** Accepted (user, 2026-11-15)
**Date:** 2026-11-16
**Spec:** `docs/superpowers/specs/2026-10-16-bmad-v7-layer-design.md` §14

## Context

The first v7 design let v7 own the work-item data but kept the workflow ours. `l3io-plan` and
`l3io-execute` stayed the entry points; sprints, which v7 rejects, came back; and a second code
review and fix loop ran after BMad's own. That design even weighed turning BMad's review off.
That is a parallel product built on v7's data model.

## Decision

A user runs v7's own skills: Sofia (`bmad-agent-po`) to plan, `bmad-build`/`bmad-build-auto`
to build, BMad's review and retrospective. Every capability of ours attaches to one of those
through an extension point v7 ships: menu items, stage hooks, `on_complete`, review lenses,
`persistent_facts`. A skill of ours exists only where v7 has nothing to attach to: unattended
multi-ticket orchestration, estimation and calibration, migration and diagnostics, ADR
allocation, and the red-team persona.

**The test, applied to every 4.x design:** if the user never types one of our commands, which
of our capabilities still happen? Where v7 already does something, ours is retired (§14.3).

## Consequences

- Most of today's workflow code retires (§14.3). What stays is the part v7 refuses to compute.
- v7 has no customization layer a module contributes (§14.2), so attaching means writing into
  the team's `_bmad/custom/<skill>.toml`. ADR-0020 governs that.
- Measurement covers every build, not only orchestrated ones, because it runs on
  `bmad-build`'s own hooks.
