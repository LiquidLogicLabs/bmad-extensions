# ADR-0014 — v7 module packaging: `bmod.toml` and module records (supersedes ADR-0008 on the 4.x line)

**Status:** Proposed
**Date:** 2026-11-16
**Supersedes:** ADR-0008 for 4.x. ADR-0008 stays in force on the 3.x line.
**Spec:** §9, §13.3, §13.5

## Context

ADR-0008 shaped our modules for BMad 6.x's installer: one setup skill for `l3io-pm`, three
standalone modules, `module.yaml` in two places, and `module-help.csv`. v7 has no installer of
that kind. Modules are discovered from `bmod.toml` files, a `bmod-<code>` module-record skill
holds config questions, help is `help/help.md`, and `npx skills add` plus `bmad setup` installs
them. Measured on a real install (§13.5): declared scripts land at `_bmad/<code>/scripts/`.

## Decision

- Every skill folder carries a `bmod.toml` (`[skill]`, declaring its scripts).
- Each module gets a `bmod-<code>` record (`l3io-pm`, `l3io-util`, `l3io-arch`, `l3io-sec`).
  Each record carries one `[[bmod.config_questions]]` per current module key, `required_skills`
  for cross-module needs, and `help/help.md`.
- `module.yaml`, `module-help.csv`, `l3io-setup` and its merge scripts are retired and listed
  in each module's `retired.toml`.
- Scripts are declared, never self-installed. The call form is
  `uv run {project-root}/_bmad/<code>/scripts/…`.
- `validate_manifests.py` gates the repo; `check:module`'s twelve 6.x rules retire with the
  installer they model.

## Consequences

`self-install` and its machinery (digest, symlink swap, downgrade refusal) do not exist on
4.x. `smoke:install` is rebuilt on `tests/fixtures/v7/make-fixture.sh`.
