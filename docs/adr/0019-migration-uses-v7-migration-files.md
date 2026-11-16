# ADR-0019 — Migration to 4.x uses v7's native `migration-<n>.toml`

**Status:** Accepted (user, 2026-11-16)
**Date:** 2026-11-16
**Spec:** §7, §13.3, §13.5

## Context

v7 runs module migrations through `bmad migrate`: an agent lists every module's
`migration-<n>.toml`, applies each one's `detect` prose, and follows its `guide` and
`checklist`. The alternative was our own `/l3io-doctor migrate-v7` conductor. Measured (§13.5):
method's own `migration-1` and `migration-2` can both match an l3io-shaped project.

## Decision

`l3io-pm` ships `migration-1.toml` (`from = "3"`, `to = "4"`). Its `detect` requires that v7's
initiative layout already exists, so ours runs after method's `migration-1`. Its `guide`
invokes `migrate-engine.py`, which is the only writer. Its `checklist` verifies every moved
datum.

## Consequences

One migration entry point for the user (`bmad migrate`). Ordering against method's migrations
comes from `detect`, as v7 intends. `docs/upgrading.md` keeps telling 3.x users not to run
`bmad migrate` until 4.x is installed.
