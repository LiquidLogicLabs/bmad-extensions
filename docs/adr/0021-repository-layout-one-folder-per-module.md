# ADR-0021 — Repository layout on 4.x: one folder per module

**Status:** Proposed
**Date:** 2026-11-16
**Spec:** §9, §13.3, §13.5

## Context

v7 prescribes `skills/<code>/<skill>/` for a multi-module source repo, with
`update_source = "github:<owner>/<repo>/skills/<code>"`, and users install with
`npx skills add <owner>/<repo>/skills/<code>`. `validate_manifests.py` requires one version
across a repository's records, and treats a folder with neither `SKILL.md` nor `bmod.toml` as
a group. Measured (§13.5): `npx skills add` of a module folder installs its skills flat into
each chosen tool's skills folder.

## Decision

- `skills/l3io-pm/`, `skills/l3io-util/`, `skills/l3io-arch/` and `skills/l3io-sec/`, each
  holding its skills and its `bmod-<code>` record.
- `skills/_shared/` stays the canonical source, outside every module folder, so an install
  never ships it. `sync-shared-scripts.mjs` keeps copying into skill folders, retargeted to the
  new paths.
- One version for the whole repository, as today.

## Consequences

Install docs become `npx skills add LiquidLogicLabs/bmad-extensions/skills/<code>`.
`.claude-plugin/marketplace.json` stays only while 3.x ships. Every path-deriving check
(manifests, sync groups, checks 24, 29, 37 and 38) is retargeted in the same change.
