# l3io-arch Reference

Engineering-standards architecture guardrails and review.

## Overview

`l3io-arch` applies a LiquidLogicLabs engineering-standards charter to a project's architecture. The standards are the single source of truth in the skill's `scripts/standards/standards-*.md` files; everything else applies and cites them rather than inventing rules.

On BMad v7 the module runs mostly **inside BMad's own skills** (ADR-0017, spec §14.3). `/l3io-doctor wire` attaches it, and each entry loads a file this module declares in `bmod.toml`, which `bmad setup l3io-arch` installs under `{project-root}/_bmad/l3io-arch/scripts/` (see [Wiring into BMad](#wiring-into-bmad)). What stays a workflow of its own is **decision support**: weigh options and record an ADR. No runtime dependency on the other l3io modules; ADR numbering uses `l3io-pm`'s register when it is installed.

Skill: `/l3io-arch-review`.

## Configuration

Config is resolved via `{project-root}/_bmad/scripts/resolve_config.py` — `core.*` for shared settings and `modules.l3io-arch.*` for this module. No section is required; every value has a default.

Key settings (with defaults):

- `preferred_diagram_format` — `mermaid` (fallback `ascii`). Preferred format for architecture diagrams. This is the **only** setting `modules.l3io-arch` owns, and the only one this module's `module.yaml` declares.

Two paths this module reads are **not** its own keys:

- `output_folder` — `core.output_folder`, default `{project-root}/_bmad-output`. The installer owns it.
- `implementation_artifacts` — `modules.l3io-pm.implementation_artifacts`, default `{output_folder}/implementation-artifacts`. `l3io-pm` owns the state tree, so it owns the path, and all four modules resolve it from there — there is one artifact tree, not one per module. Setting `modules.l3io-arch.implementation_artifacts` in `_bmad/custom/config.toml` has **no effect**.

Review reports write to `implementation_artifacts`; ADRs and the docs skeleton write under `{project-root}/docs/`.

## The Standards Charter

The universal principles live in `scripts/standards/standards-core.md`. Each is written for **design**, **review**, and **decision** use, with red flags and a review severity (BLOCKER / MAJOR / MINOR).

| # | Principle | Core rule |
|---|-----------|-----------|
| 1 | Separation of concerns | Each module owns one responsibility; concern leakage across boundaries is a defect. |
| 2 | Reuse over copy-paste | Duplication of non-trivial logic is not allowed; refactor to reuse rather than copy. |
| 3 | Design by contract | Declare preconditions, postconditions, invariants; validate at boundaries, trust inside. |
| 4 | Testability | If it is hard to test, the design is wrong — inject dependencies, isolate side effects. |
| 5 | Brevity without sacrificing readability | Least code a competent reader understands on first pass; flag both golfing and ceremony. |
| 6 | Comment discipline | Comments explain current state and intent, not change history; no comment-per-fix. |
| 7 | Dependency selection | Prefer established, actively-maintained, well-licensed packages; every dep is a liability. |
| 8 | GA over alpha/beta | Depend on generally-available releases; preview/non-GA use needs an ADR-recorded justification. |
| 9 | Unified correlated logging | One structured logging approach; a correlation/trace ID propagates across every boundary. |
| 10 | Documentation with diagrams | Architectural / developer / operational docs, well-organized; Mermaid-preferred (ASCII fallback) diagrams. |

## Stack Overlays

The skill auto-detects the stack in scope and loads the matching overlay on top of `standards-core.md`.

| Overlay | Detected via | Headline rules |
|---------|--------------|----------------|
| `standards-python.md` | `pyproject.toml`, `uv.lock`, `poetry.lock` | **uv or Poetry for ALL apps and packages**; committed lockfile; supported Python; ruff/mypy; structured logging. |
| `standards-nodejs.md` | `package.json` | **Latest active LTS**, pinned (`engines` + `.nvmrc`); committed lockfile; TypeScript strict; `pino`-style structured logging. |
| `standards-dotnet.md` | `*.csproj`, `*.sln` | **Latest supported .NET**; deployable apps publish **self-contained** with explicit RID; nullable + warnings-as-errors; `ILogger` structured logging. |
| `standards-github-actions.md` | `.github/workflows/*` | **Marketplace actions over custom scripting**; **pin to major** (trusted) or SHA (third-party); least-privilege `permissions`; Dependabot. |
| `standards-docker.md` | Dockerfiles | **Pin every `FROM` by digest AND tag**; minimal/distroless final stage carrying no build toolchain; secrets via `--mount=type=secret`, never `ARG`/`ENV`; `--sbom=true --provenance=true` at build time; non-root numeric `USER`; exec-form entrypoint so signals land. |
| `standards-powershell.md` | `*.ps1` | **PowerShell 7** on a currently supported LTS minor (the minor moves — check the lifecycle page at review time); 5.1 only as a declared exception, with its 5.1→7 breaks called out (UTF-8-no-BOM default, workflows removed, `WinPSCompatSession` gives serialised values); `#Requires` + `Set-StrictMode -Version Latest` + `$ErrorActionPreference = 'Stop'`; objects not formatted strings; PSScriptAnalyzer clean, Pester 5 via `[PesterConfiguration]`; SecretManagement. |
| `standards-shell.md` | `*.sh` | `#!/usr/bin/env bash` + `set -euo pipefail`; quote every expansion, `"$@"` not `$@`; `mktemp` with `trap … EXIT` on the next line; ShellCheck clean with justified suppressions; escalate to a real language once branching outgrows shell. |

## Modes

### `design` — guardrails inside `bmad-architecture`

No longer a workflow of its own. `/l3io-arch-review design` hands the user to `bmad-architecture` (create or update intent), which, once wired, consults the standards before every stack, dependency, logging and deployment call, holds fuller documents to §10, and runs l3io's design review at its Reviewer Gate. Each load-bearing call it surfaces is recorded with `decision`.

### `review` — through `bmad-review`

Runs `bmad-review` with `lenses=l3io-design-integrity,l3io-testability,l3io-dependency-policy,l3io-observability,l3io-stack-rules` (plus `l3io-threat-design` when `l3io-sec` is installed), then grades each finding **severity · principle · location · remediation** into a report (`references/review-report.md`). **Gate:** BLOCKER and MAJOR findings must be resolved or ADR-justified; MINOR defers to the backlog. Unwired, the skill loads each lens file itself.

### `decision` — decision support

Identify the principle(s) in tension, weigh options against them, recommend, and record an ADR (`assets/adr-template.md`) at `{project-root}/docs/adr/NNNN-slug.md` — the one ADR home.

**Numbering.** When `{project-root}/_bmad/l3io-pm/scripts/pm_status/__main__.py` is present, take the number from the l3io-pm register rather than choosing one:

```bash
uv run {project-root}/_bmad/l3io-pm/scripts/pm_status/__main__.py adr-reserve \
  --state-root {output_folder}/l3io --epic n/a --slug {slug} \
  --adr-dir {project-root}/docs/adr
```

A directory listing shows who has finished, not who is in flight, so parallel writers that derive a number from one will collide. Without l3io-pm there is no register: use the highest number in `docs/adr/` plus one, which is safe only for the single-writer case that implies, and `adr-reserve` skips those numbers later.

Fill `Epic:` (`n/a` outside an epic) and `Departs from spec:` with the `path#anchor` of the spec section the decision departs from, or `n/a`.

Invocation shortcuts: `/l3io-arch-review design`, `/l3io-arch-review review`, `/l3io-arch-review decision`.

**The stack is conversational, not a flag.** This skill takes no flags — it detects the stacks in
scope and loads their overlays, and honours a stack you name in the request over its own
detection (`SKILL.md` §2). Say "review this as a Python project"; there is no `--stack`. An
earlier version of this line documented one, which would have halted on use.

### `pm-status.py` subcommands this skill runs

| Subcommand | Used by | For |
|---|---|---|
| `adr-reserve` | `decision` | Allocates the next ADR number under a lock, from `l3io-pm`'s register, before the file is written. Optional: without `l3io-pm` installed there is no register and the skill falls back to the highest number on disk plus one. Full signature in the [l3io-pm reference](l3io-pm-reference.md). |

## Severity Model

| Severity | Meaning |
|----------|---------|
| **BLOCKER** | Violates a hard rule; blocks sign-off. |
| **MAJOR** | Clear deviation; must be fixed or ADR-justified. |
| **MINOR** | Improvement opportunity; auto-defers to backlog. |

## Wiring into BMad

`/l3io-doctor wire` adds these entries to the team's `_bmad/custom/<skill>.toml`, each skipped while `l3io-arch` is not set up; `/l3io-doctor unwire` removes exactly them (ADR-0020):

| Host | Key | Entry |
|---|---|---|
| `bmad-architecture` | `finalize_reviewers` | `file:` `scripts/reviewers/epic-design-review.md` — the design review against the standards, run at every Reviewer Gate (Finalize, Validate, headless). This is the epic architecture gate 3.x ran inside `l3io-execute`. |
| `bmad-architecture` | `external_sources` | consult `scripts/standards/` before a stack, dependency, logging or deployment call |
| `bmad-architecture` | `doc_standards` | the documentation standard (§10) on fuller prose documents |
| `bmad-review` | `lenses` | the five engineering lenses, `scripts/lenses/l3io-*.md` |
| `bmad-code-review`, `bmad-build`, `bmad-build-auto` | `thorough_lenses` | the same five, in every `thorough` review |

The entries point at the files rather than duplicating them, so each viewpoint has one source. The legacy `bmad-customize` overlays (including one for 6.x's `bmad-create-story`) are gone with this.

## Artifacts Produced

- **Review** → severity-graded findings report at `implementation_artifacts`.
- **Decision** → an ADR under `{project-root}/docs/adr/` — the one ADR home — from `assets/adr-template.md`, numbered by `adr-reserve` when l3io-pm is installed.
