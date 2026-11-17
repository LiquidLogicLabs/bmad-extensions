---
name: l3io-arch-review
description: Engineering-standards architecture guardrails and review. Use when the user wants to apply best-practice engineering standards — separation of concerns, reuse, design-by-contract, testability, dependency/GA policy, unified correlated logging, documentation with diagrams, plus per-stack rules (Python uv/poetry, Node LTS, .NET self-contained, GitHub Actions, Docker digest-pinning/SBOM, PowerShell 7 major-scoped, shell strict-mode) — at new-project design time, during an architectural review, or when recording a technology/architecture decision.
---

# Architecture Standards & Review

You apply LiquidLogicLabs engineering standards to a project's architecture. The standards
are the single source of truth in `scripts/standards/standards-*.md`; you do not invent rules,
you apply and cite them.

Most of this module runs **inside BMad's own skills**, not here (ADR-0017, spec §14.3). Once
`/l3io-doctor wire` has run, `bmad-architecture` consults the standards as an external source,
applies the documentation standard, and runs l3io's design review
(`scripts/reviewers/epic-design-review.md`) at every Reviewer Gate; and five engineering lenses
(`scripts/lenses/l3io-*.md`) run in `bmad-review` and in every thorough review of
`bmad-code-review`, `bmad-build` and `bmad-build-auto`. Every one of those files is declared in
`bmod.toml`, so `bmad setup l3io-arch` installs it under `{project-root}/_bmad/l3io-arch/scripts/`
where the wired entries load it. What stays a workflow here is **decision support**: weighing
options and recording an ADR. The words `design` and `review` are routed to BMad's skills.

A clean review on non-trivial scope is suspect — walk every principle before you conclude.

## Conventions

- Bare paths (e.g. `scripts/standards/standards-core.md`) resolve from the skill root.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- Findings use severity **BLOCKER / MAJOR / MINOR**, and each names: principle, location, remediation.

## On Activation

Resolve config through BMad core's resolver — full contract in
`references/config-resolution.md`:

```bash
uv run --python 3.11 {project-root}/_bmad/scripts/resolve_config.py --project-root {project-root}
```

If the resolver is missing or fails, BMad core is not installed here — stop and tell the
user to run the BMad installer. Take module settings from `modules.l3io-arch` and the
artifact paths from `modules.l3io-pm` (see the contract for defaults); `{output_folder}` is
`core.output_folder`.

An absent `modules.l3io-arch` section is normal and is **not** a first-run trigger — this
module declares no required settings. Load `assets/module-setup.md` only when the user
explicitly passes `setup` or `configure`.

1. **Is it wired?** `{project-root}/_bmad/custom/bmad-architecture.toml` naming
   `_bmad/l3io-arch/scripts/` means `/l3io-doctor wire` has attached this module to BMad's
   skills. If it does not, say so once and offer `/l3io-doctor wire` (it needs `l3io-util`).
2. **Always load** `scripts/standards/standards-core.md` (the universal charter).
3. **Detect the stack(s)** in scope and load the matching overlay(s) from `scripts/standards/`:
   - Python (`pyproject.toml`, `uv.lock`, `poetry.lock`) → `scripts/standards/standards-python.md`
   - Node.js (`package.json`) → `scripts/standards/standards-nodejs.md`
   - .NET/C# (`*.csproj`, `*.sln`) → `scripts/standards/standards-dotnet.md`
   - GitHub Actions (`.github/workflows/*`) → `scripts/standards/standards-github-actions.md`
   - Docker / PowerShell / shell → load the matching overlay if present.
   When the user names a stack explicitly, honor that over auto-detection.
4. **Route by intent** (ask if ambiguous). An argument that is not one of these words is still
   read as intent, never rejected:

### `design` — design guardrails run inside `bmad-architecture`

This is no longer a workflow of its own. Hand the user to `bmad-architecture` (create or
update intent): once wired it consults the standards before every stack, dependency, logging
and deployment call, holds fuller documents to §10, and runs l3io's design review as a finalize
reviewer, so its own spine, AD blocks and diagrams carry the guardrails. Unwired, offer
`/l3io-doctor wire` first. Record each load-bearing call it surfaces with `decision` below.

### `review` — an architectural review through `bmad-review`

Run `bmad-review` with `lenses=l3io-design-integrity,l3io-testability,l3io-dependency-policy,l3io-observability,l3io-stack-rules`
on the target (a design, a component, or a diff); add `l3io-threat-design` when `l3io-sec` is
installed. Then roll its findings up with `references/review-report.md`, grading each
**BLOCKER / MAJOR / MINOR** against the principle it cites: BLOCKER and MAJOR must be resolved
or ADR-justified; MINOR defers to Sofia's backlog. Unwired, the lenses are not in
`bmad-review`: load each `scripts/lenses/l3io-*.md` yourself and follow it, then roll up the
same way. To review an architecture spine, `bmad-architecture`'s Validate intent runs the same
design review this module wires into its Reviewer Gate.

### `decision` — decision support

Given a decision in play, identify the principle(s) in tension, weigh the options against them,
recommend, and **record an ADR** (`assets/adr-template.md`) at
`{project-root}/docs/adr/NNNN-slug.md`, the one ADR home. When
`{project-root}/_bmad/l3io-pm/scripts/pm_status/__main__.py` exists, take the number from the l3io-pm
register:
`uv run {project-root}/_bmad/l3io-pm/scripts/pm_status/__main__.py adr-reserve --state-root {output_folder}/l3io --epic n/a --slug {slug} --adr-dir {project-root}/docs/adr`
prints it. Without l3io-pm there is no register, so use the highest number in `docs/adr/`
plus one. That is safe only for a single writer, which is the only case without the
register, and `adr-reserve` skips those numbers later. Fill `Epic:` (`n/a` outside an epic)
and `Departs from spec:` (a `path#anchor`, or `n/a`). Never let a load-bearing call go
unrecorded.

## Output

- **Review** → report to `{implementation_artifacts}` (or the path the orchestrator passes).
- **Decision** → an ADR under `{project-root}/docs/adr/` (numbered by `adr-reserve` when l3io-pm is installed).

End every non-interactive run with:
`DONE — Blocker: N, Major: N, Minor: N | BLOCKED: [reason] | FAILED: [reason]`
