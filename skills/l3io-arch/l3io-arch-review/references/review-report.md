# Architectural Review — Report Shape

Structure a `review` output as follows: the findings `bmad-review` returned from the l3io
lenses, graded and rolled up.

## Executive summary

2–4 sentences: overall posture, the count by severity, and the single most important action.

## Findings table

| # | Severity | Principle | Location | Finding | Remediation |
|---|----------|-----------|----------|---------|-------------|
| 1 | BLOCKER  | Core §1 Separation of Concerns | `path:line` | domain imports ORM type | extract mapping layer |

Severity: **BLOCKER** (hard-rule violation) · **MAJOR** (clear deviation, fix or ADR-justify) ·
**MINOR** (improvement; auto-defers to backlog).

## Per-principle walkthrough

For each principle in `scripts/standards/standards-core.md` §1–10 and each loaded overlay, one line: PASS, or the
finding number(s). Do not skip a principle — an unwalked principle is an incomplete review.

## Gate

- BLOCKER + MAJOR: must be resolved or recorded as an accepted ADR before sign-off.
- MINOR: defer to the backlog, as a candidate for Sofia (`bmad-agent-po`).

## Recommended ADRs

Any decision surfaced by the review that lacks a record → list it for authoring via
`decision` (`assets/adr-template.md`).
