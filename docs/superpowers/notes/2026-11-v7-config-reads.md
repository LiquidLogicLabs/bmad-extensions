# v7 config reads: what the rewrite actually is (plan Task 0.3)

Measured 2026-11-16 on `feat/bmad-v7-layer` (merged with `main` at 3.7.1).

**Scope.** Canonical sources only: `skills/_shared/**` plus each skill's own non-synced
files. Copies were excluded using `node scripts/sync-shared-scripts.mjs --dump-deliveries`.
The 85/19/14/21 in spec §13.3 counted the copies and was an upper bound.

**What v7's resolver returns.** Run on the v7 fixture (`tests/fixtures/v7/make-fixture.sh`,
`e435a22`): `{"core": {"project_name": …, "output_folder": "{project-root}/_bmad-output"}}`
and nothing else. 6.12.4, on a real `--tools cline` install, returns `user_name`,
`communication_language`, `document_output_language`, `project_name` and `output_folder`
(as the relative `_bmad-output`).

## Classification

| Key | Canonical lines / files | Class | Notes |
|---|---|---|---|
| `communication_language` | 45 / 38 | **removal** | 31 are the boilerplate opening line "Communicate … in `{communication_language}`", one per step file and `SKILL.md`; delete them. The rest: two subagent hand-offs in `execute/step-05-epic-loop.md` (lines 246, 323); the red-team persona (`init-sanctum.py`, `BOND-template.md`, `first-breath.md`); `l3io-arch-review/SKILL.md:33`; and the binding tables in `config-resolution.md` and `step-00-activate.md`. Every read already has a default (`English`), so nothing breaks on v7 — the reads are dead, not failing. |
| `user_name` | 11 / 7 | **removal** | Red-team sanctum (`init-sanctum.py` defaults to `friend`; three templates), `l3io-doctor/steps/clean-layout.md:227` (prose), and the binding docs. Defaults exist; dead on v7. |
| `document_output_language` | 2 / 2 | **removal** | `config-resolution.md` and `module-setup.md` only — documentation, no runtime read. |
| `output_folder` | 17 / 6 | **no rename; one value fix** | Every read is already `core.output_folder`, the key v7 keeps. But v7's **value** is `{project-root}/_bmad-output`, with the placeholder unexpanded. Prose bindings in `step-00-activate.md`, `l3io-doctor/SKILL.md` and `l3io-help/steps/step-01-config.md` are resolved by the agent, which handles it. **`l3io-sync/scripts/drift-report.py:92` uses the value as a path directly**, so on v7 it would look in a folder literally named `{project-root}`. It must expand `{project-root}` in 4.0.0. |
| Module keys repeating the module code | 0 | **none** | No `modules.l3io-*.*` key starts with its module's code (`l3io-pm`'s 14 keys, `l3io-arch`, `l3io-sec`, `l3io-util`). Nothing to rename. |

## What this means for Phase 3

The config rewrite is mostly **deletion**, not translation. About 33 boilerplate lines go,
along with the dead `user_name` and `communication_language` plumbing. The one behavioural
fix is `{project-root}` expansion in `drift-report.py`. That is far smaller than §13.3's upper
bound implied.

Phase 3's guard stands: a `check:docs` check that fails on any shipped read of a key v7 does
not return. It should also cover a script reading `core.output_folder` without expanding
`{project-root}`.

Phase 3 work only. 3.x stops on v7 at activation, so none of this affects a 6.x user.
