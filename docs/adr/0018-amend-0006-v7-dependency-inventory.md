# ADR-0018 — Amend ADR-0006's dependency inventory for v7

**Status:** Accepted (user, 2026-11-16)
**Date:** 2026-11-16
**Amends:** ADR-0006, for the 4.x line
**Spec:** §10, §13.2, §13.5

## Context

ADR-0006 keeps an inventory of the BMad skills we depend on, with a status per skill. v7
changes several of them. Measured at `e435a22`: the preview reports `6.13.0-next`;
`bmad-sprint-planning` is absent; `bmad-prd`, `bmad-prfaq` and `bmad-product-brief` moved into
`bmad-facilitate`.

## Decision

The 4.x inventory records:
- `removed`: `bmad-sprint-planning`, `bmad-check-implementation-readiness`,
  `bmad-create-epics-and-stories`, `bmad-prd`, `bmad-prfaq` and `bmad-product-brief`.
- renamed: `bmad-help` → `bmad`; module code `bmm` → `method`.
- no fallback chain to the 6.x shims. A leftover `bmad-create-story` or `bmad-dev-story` is
  never preferred on 4.x, and v7 does not offer to remove them (§13.5).
- version checks accept `6.13.0-next` as the preview, not only `7.*`.

## Consequences

`bmad-deps.py` on 4.x is a v7 checker. The 6.x inventory stays with 3.x.
