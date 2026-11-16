# ADR-0016 — No sprints in 4.0.0

**Status:** Accepted (user, 2026-11-16)
**Date:** 2026-11-16
**Spec:** §4.1, §14.3

## Context

v7 rejects sprints by design. Its levels are initiative, epic and ticket. Ours added a sprint
level between epic and story, used for closure reviews and to feed calibration forward between
batches.

## Decision

4.0.0 has no sprint level. The epic is the closure unit: `bmad-review` with our lenses, then
`bmad-retrospective`. Calibration needs no batch, because every `set-actual` already appends a
sample at story granularity.

## Consequences

- Sprint-level estimates, closure bands and orchestration bands go; epic-level ones remain.
- Migration (ADR-0019) folds each 3.x sprint's stories into its epic. Sprint closure reports are
  kept as files and not translated.
- Parallel waves inside an epic are dispatch planning in `l3io-execute`, not a stored level.
