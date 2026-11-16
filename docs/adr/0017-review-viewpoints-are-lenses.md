# ADR-0017 — Review viewpoints are contributed as lenses; BMad's review is the only review

**Status:** Proposed
**Date:** 2026-11-16
**Spec:** §5, §14.1, §14.3

## Context

`bmad-review` (`[[workflow.lenses]]`, keyed by `code`) and `bmad-code-review`
(`quick_lenses`/`thorough_lenses`, keyed by `id`) accept third-party lenses through the keyed
merge. `bmad-code-review` runs inside `bmad-build`'s loop and applies fixes itself
(`fixes = "apply"`). We run a second review and fix loop after it.

## Decision

- Our engineering-standards and threat viewpoints, about eleven of them, are registered as
  lenses. Each lens's `instruction` points at our skill's own reference file, so each viewpoint
  has one source.
- BMad's review and fix loop are the only ones. `l3io-execute` runs `bmad-build-auto` with
  `review = "thorough"`, and has no review step of its own.
- Workflows stay skills: design guardrails, ADR recording, and the red-team persona and
  sanctum.

## Consequences

Our standards run inside every BMad build, including on projects where nobody invokes one of
our skills. `l3io-arch-review` Mode B becomes a caller of `bmad-review` with our lenses
selected.
