# ADR-0020 — One reversible wire-in owns every edit to a team's customization files

**Status:** Proposed
**Date:** 2026-11-16
**Spec:** §14.1, §14.2

## Context

v7 merges customization from the skill's defaults, the team's `_bmad/custom/<skill>.toml`,
and the user's `.user.toml`. A module has no layer of its own, so attaching our hooks and
lenses means writing into the team's file. Some hooks hold one value (Sofia's stage hooks,
`on_complete`), and a team may already use them.

## Decision

`l3io-doctor` owns one wire-in mechanism for every surface in §14.1, with a matching unwire.
- **Idempotent and round-trip safe:** comments and order in the team's file survive, and
  running it twice changes nothing.
- **Never overwrites a team's value.** On a non-empty single-value hook it refuses and names
  the conflict. Composing with the team's value happens only with explicit consent.
- **Prefers list and keyed surfaces** (lenses, `activation_steps_*`, `persistent_facts`) wherever
  one reaches the same point.
- **Records what it added**, so unwire removes exactly that and nothing a team wrote.

The proposal to BMad for a module customization layer is drafted, and posted only once 4.x
works end to end (user, 2026-11-16).

## Consequences

If BMad adds a module layer, wire-in shrinks to shipping files into it, and unwire becomes
uninstall.
