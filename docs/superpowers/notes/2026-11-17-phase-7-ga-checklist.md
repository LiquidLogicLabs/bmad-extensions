# Phase 7 — GA release-gate checklist (l3io 4.0.0)

Drafted 2026-11-17 on `feat/bmad-v7-layer`, before BMad v7 has a GA tag. The pre-GA documentation
part of Phase 7 is done (`docs/upgrading.md` 3.x → 4.0.0, README install via `npx skills add`).
Everything below waits on the v7 GA tag. Plan: `docs/superpowers/plans/2026-11-15-bmad-v7-readiness.md`
(Phase 7 and the R1–R15 table). Current pin: `e435a22574fe55722841086e5566420178b98df3`.

Steps marked **USER GATE** are never taken by an agent.

## 1. Re-pin to the GA tag

- [ ] Resolve the GA tag to its full 40-hex commit. The pin is a commit, never a tag.
- [ ] `scripts/fetch-bmad-tool.mjs`: set `PIN`. For every `KNOWN_TOOLS` path, fetch the file
      at the new pin by hand, read the diff against `e435a22`, and record its new SHA-256 in the
      same commit. The paths are `validate_manifests.py` and the files it loads beside it
      (`setup.py`, `knowledge.py` and the rest), `config_utils.py`, `render_skill.py`, the
      seven host `customize.toml`s (`bmad-agent-po`, `bmad-build`, `bmad-build-auto`,
      `bmad-retrospective`, `bmad-review`, `bmad-code-review`, `bmad-architecture`), and
      `skills/method/bmod-method/migration-1.toml`. Derive the list from the file; this one is
      a reminder.
- [ ] Rewrite every remaining `e435a22` citation, after re-measuring what it cites:
      `git grep -n e435a22 -- scripts tests skills docs/upgrading.md`. Today that is
      `tests/fixtures/v7/README.md`, `tests/l3io-doctor/test-engine.py`,
      `tests/l3io-doctor/test-bmad-deps.py`, `scripts/lib/bmod-records.mjs`,
      `scripts/tests/{retired,bmod-records}.test.mjs`, `skills/_shared/steps/shared/step-00-activate.md`
      (then `npm run sync:scripts` and regenerate the manifests) and
      `skills/l3io-util/l3io-doctor/scripts/bmad-deps.py`.
- [ ] Bump `required_skills` version in each `bmod.toml` if GA reports a version other than
      `6.13.0` (the preview's `6.13.0-next`).

## 2. Re-measure the file:line citations (§13-style)

Append a §14 drift log (`e435a22` → GA) to `docs/superpowers/specs/2026-10-16-bmad-v7-layer-design.md`
in the shape of §13: each claim marked verified-unchanged or moved/changed, with the phase it sends
back to rework. Only phases whose dependencies moved go back. The citations to re-check:

**Phase 5 (lenses, design review, spec sync)** — `.agent-reports/phase-5-report.md`:
- [ ] `core-tools/bmad-review/customize.toml:81-141` (`workflow.lenses`; `code`, `applies_to`, `when`, `after`); `bmad-review` `SKILL.md:28` (resolver).
- [ ] Thorough-review hosts: `bmad-code-review` `customize.toml:88`, `bmad-build :121`, `bmad-build-auto :92`.
- [ ] `render_skill.py:157-178` (a review layer keeps id/name/when/instruction only), `:122-128` (undeclared keys halt), `:301-317` (type checks), `:186-202` (keyed tables hold strings).
- [ ] `review` defaults to `quick` (`bmad-build :97`, `bmad-build-auto :68`); `thorough` by `--set` (`bmad-build-auto` `SKILL.md:16`).
- [ ] `bmad-architecture`: `doc_standards :62`, `external_sources :75`, `finalize_reviewers :96`; `references/reviewer-gate.md:7`, `headless.md:5`; update intent `SKILL.md:61`.
- [ ] `bmad-retrospective`: `persistent_facts` `customize.toml:33`; `acceptance-verdict.md:16-25`; `workflow.md:101` (only the document and approved records are written — if GA relaxes this, the spec sync may stop being advisory; update upgrading.md).

**Phase 6 (migration)** — `.agent-reports/phase-6-report.md`:
- [ ] `knowledge.py:66-68, 423-479` (a migration record's required fields), `:128` (sort by module, number — why our `detect` must wait for method's).
- [ ] `references/migrate.md:5-8` (later migrations re-checked only for the same module — upgrading.md tells users ours appears on the next pass; drop that sentence if GA changes it), `references/setup.md:57`.
- [ ] `bmod-method/migration-1.toml :17` (ordering in detect), `:129` (`v6_key`), `:151` (`sprint-status.yaml` → `archive-v6/`), `:172` (paths another module covers stay).
- [ ] `bmad-agent-po/scripts/tickets.py:280-400` (plans join through `ticket:`), `:1149` (plan path), `:1283` (`mark` creates a plan, repo store only).

**Earlier phases**: §13's own claims, the wire-in keys `check:bmod` judges against each host's pinned `customize.toml`, and the `.agents/skills` / `.claude/skills` probe roots (checks 29, 37).

## 3. Rebuild the fixture from GA and verify R1–R8

- [ ] `bash tests/fixtures/v7/make-fixture.sh <GA-sha> /tmp/v7fixture`, then `npm run smoke:install`
      (it reads the pin from `fetch-bmad-tool.mjs`). Exit 0, no `FAIL`.
- [ ] **R1** each module installs with `npx skills add <owner>/<repo>/skills/<code>` (from GitHub, not a local path); `bmad setup <code>` asks our questions; `bmad status` reports 4.0.0 (after the release bump — re-check post-release).
- [ ] **R2** `npm run check:bmod` green at the GA pin.
- [ ] **R3** the manual session — section 4.
- [ ] **R4** on a tracker store, no status written with `tickets.py mark`; readiness runs `mirror` before `next --synced`.
- [ ] **R5** run the migration engine on a project **method's GA migration actually produced**: take a real 3.x-shaped project (sharded tree with estimates, actuals, calibration, events, ADR register), run `bmad migrate` in a live agent session so method's `migration-1` moves it, then run `bmad migrate` again for ours. Verify calibration, events, ADR register, estimates and actuals byte-for-byte or datum-for-datum, the source kept until verify, and `.legacy` only after. `tests/l3io-doctor/test-engine.py` proves this only on synthetic trees; this is its first run on a real one.
- [ ] **R6** all eleven lenses resolve in merged `bmad-review` and `bmad-code-review`, and render in `bmad-build`/`bmad-build-auto` with `--set workflow.review=thorough` (smoke covers it).
- [ ] **R7** no shipped file reads `user_name`, `communication_language`, `document_output_language` or a bare `output_folder` (check 39 and the R7 test).
- [ ] **R8** every retired name in a `retired.toml`; `bmad setup` offers to delete them on a project that has them installed.
- [ ] Also re-run R13–R15 in the smoke (bracket on plain `bmad-build`, no duplicated engine, wire/unwire byte-identical).

## 4. R3 — the manual session

R3 passed at the `e435a22` pin on 2026-11-18 (`2026-11-17-phase-4-r3-transcript.md`); at GA it
is re-run, and the result is recorded as a dated successor.

- [ ] Follow `docs/superpowers/notes/2026-11-17-phase-4-r3-procedure.md` on the GA fixture (set
      its pin to the GA sha). One epic planned in Sofia, built by `/l3io-execute`, closed by
      `bmad-retrospective`; all five metrics read back as estimate and actual; no `l3io-`
      command typed except `l3io-execute`.
- [ ] Record the transcript and read-back as `2026-11-17-phase-4-r3-transcript.md` beside the
      procedure (or a dated successor).
- [ ] Watch for what no gate proves (task 4.7 report): the separate agent session per epic, CHECKPOINT resumption, the merge and the worktree cleanup.

## 5. Branches and CI

- [ ] **USER GATE** — cut `3.x` from `main` at the last 3.x release tag (R12).
- [ ] `npm ci` then every gate in `.github/workflows/checks.yml` green in CI on `3.x` and on the 4.x line (R11). Enumerate the gates from the file, not from memory.
- [ ] Confirm the 3.x release on a v7 install still refuses at activation (R9).

## 6. Release

- [ ] Breaking-change audit of `git log main..HEAD` (done pre-GA 2026-11-17; re-run for anything since). The release uses `commit-and-tag-version` (conventionalcommits preset: a `!` alone is recognised). Note `b38e0a99`'s footer says "use move-epic --to archived", which 4.0.0 also removes; the release notes should not repeat it.
- [ ] **USER GATE** — `npm run release:major` (or `npm run release` if it computes 4.0.0) for 4.0.0. `postbump` syncs every `bmod.toml` record, the `pm_status` marker and the manifests. Review the generated `CHANGELOG.md` before pushing; never hand-edit it.
- [ ] Re-check R1's `bmad status` reports 4.0.0 from the tagged release.

## 7. Adoption packet

- [ ] Send the downstream adopter the 4.0.0 adoption packet (upgrading.md's 3.x → 4.0.0 section, the mapping table, the ADRs 0014–0022). It is 6.x-scoped today and may decline; record the answer either way.
- [ ] Housekeeping: remove the fork worktree `.claude/worktrees/agent-a4f7b5ec5cce02a94` (branch `worktree-agent-a4f7b5ec5cce02a94`) if still present.
