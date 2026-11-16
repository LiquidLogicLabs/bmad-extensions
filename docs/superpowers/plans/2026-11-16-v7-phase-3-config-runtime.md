# v7 Phase 3 — Config and runtime: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the skills read only config v7 provides, and run `pm_status` from the copy v7 installs for us, with self-install gone.

**Architecture:** v7's resolver returns only `core.project_name` and `core.output_folder` (Task 0.3), so every read of `user_name`, `communication_language` or `document_output_language` is deleted, and a new `check:docs` check keeps it deleted. `pm_status` is declared in each owning skill's `bmod.toml` `[skill] scripts`. v7 then installs it at `_bmad/<code>/scripts/pm_status/` and rebuilds it on every setup (spec §3.4, measured in §13.5). The declared list is generated from the payload tree, never hand-kept. Self-install, and everything that exists only for it, is deleted.

**Tech Stack:** Node (sync and check tooling); Python 3.11 PEP-723 scripts under `uv`; BMad v7 at `e435a22` (`tests/fixtures/v7/make-fixture.sh`).

**Spec:** `docs/superpowers/specs/2026-10-16-bmad-v7-layer-design.md` §3.4, §4.5, §13.3, §13.5. Notes: `docs/superpowers/notes/2026-11-v7-config-reads.md`. Parent: `docs/superpowers/plans/2026-11-15-bmad-v7-readiness.md`, Phase 3.

**Re-pin, 2026-11-16:** upstream `main` is still `e435a22574fe55722841086e5566420178b98df3`. There are 0 commits since the pin, so §13 gets no new entry and nothing reworks.

## Rulings on the parent plan

- **Parent item 4 (narrow `pm_status` to §4.5) moves to Phase 4.** The verbs it deletes (`set-status`, `move-epic`, the placement model, every issues verb) are still invoked by `l3io-execute`, `l3io-plan` and `l3io-doctor` step files. Phase 4 item 8 retires those consumers. Deleting the verbs first would fail `check:docs` check 4, which judges every invocation against the argparse surface, and leave a broken tree. Phase 4 deletes each verb with its last caller. Cost if wrong: none at runtime. Phase 4 is one task larger.
- **Declared scripts: `pm_status` only.** The parent lists `spec-align.py` and `migrate-engine.py` as well. Both run as `uv run {skill-root}/scripts/…` from the owning skill's own directory, which v7 installs and keeps. Only `pm_status` needs a path shared between skills: `l3io-plan` runs `l3io-execute`'s copy. That need is the reason self-install exists. Declaring the other two would add a second copy of each and buy nothing. `migrate-engine.py` and `spec-align.py` take the `pm_status` path as an argument (`--pm-status`), so only their callers' bindings change. Cost if wrong: one `scripts` entry each, added later.
- **One copy per module, as today.** `l3io-execute` declares `pm_status` for `l3io-pm` and `l3io-doctor` declares it for `l3io-util`. v7 places them at `_bmad/l3io-pm/scripts/pm_status/` and `_bmad/l3io-util/scripts/pm_status/`. A skill only ever calls its own module's copy. Both copies come from one release line and are byte-identical when versions match (`check:scripts`).

## Global Constraints

- Branch `feat/bmad-v7-layer` only. No push, no tag, no release.
- Upstream pin: `e435a22574fe55722841086e5566420178b98df3`.
- Call form, from §13.5: `uv run {project-root}/_bmad/<code>/scripts/pm_status/__main__.py`, with `<code>` = `l3io-pm` or `l3io-util`.
- Edit `skills/_shared/` first, then `npm run sync:scripts`, then `node scripts/write-payload-manifest.mjs`.
- `check:docs` check numbers are never reused. The new check is **39**.
- `pm_status` cap: 1,500 lines per `.py`.
- Never bundle a BMad core script.
- No reference to the downstream adopter's organization in any file or commit message.
- Conventional Commits with DCO sign-off (`git commit -s`).
- Gates come from `.github/workflows/checks.yml`. Background `npm run test:scripts` with output captured to a file.

## Review Focus

1. **A module file is added to `pm_status/` and not declared.** v7 then installs a package missing that file, and the first import fails at runtime on a user's machine. Expected: the declared list is generated, and `check:scripts` fails naming the undeclared file. → Task 3.2.
2. **`l3io-plan` runs after `npx skills add` but before `bmad setup`,** so `_bmad/l3io-pm/scripts/` does not exist yet. Expected: activation halts with one line naming `bmad setup l3io-pm`, not a Python traceback from `uv`. → Task 3.2.
3. **The two modules are updated separately,** so `_bmad/l3io-util/scripts/pm_status` and `_bmad/l3io-pm/scripts/pm_status` differ in version while writing one state tree. Expected: the doctor's default health check reports both versions as a finding. This replaces the job `check-pm-status` did. → Task 3.3.
4. **A 3.x project upgraded to v7 still has `_bmad/scripts/pm-status/`,** or a shipped file still names it. Expected: no shipped file names `_bmad/scripts/pm-status`. Check 39 enforces this. v7's own rebuild of `_bmad/scripts/` removes the old copy, which is verified on the fixture. → Tasks 3.1 and 3.3.
5. **The red-team sanctum is born on v7,** where `core.user_name` does not exist. Expected: no rendered sanctum file contains a literal `{user_name}`, and the persona addresses the user without a name. → Task 3.1.

---

### Task 3.1: Config reads v7 does not provide (R7)

**Files:**
- Modify: every canonical file Task 0.3's note lists for `communication_language`, `user_name` and `document_output_language`, in `skills/_shared/**` and each skill's non-synced files. That includes the binding tables in `skills/_shared/config-resolution.md` and `skills/_shared/steps/shared/step-00-activate.md`, and the red-team sanctum: `scripts/init-sanctum.py` and its `assets/*-template.md` files.
- Modify: `scripts/check-docs.mjs` to add check 39 and update the header and the count; also update `CLAUDE.md`'s count sentence.
- Test: `scripts/tests/check-docs.test.mjs`, and the red-team sanctum suite under `tests/l3io-sec-redteam/`.

**Interfaces:**
- Produces check 39, `v7-config-keys`. Over every shipped file (the `skillDirs()` payload, synced copies included), it fails on:
  - any occurrence of `communication_language`, `user_name` or `document_output_language`;
  - a bare `output_folder` binding that is not `core.output_folder`;
  - the path `_bmad/scripts/pm-status`.

  Each failure line names the file, the line and the token.

- [ ] **Step 1: Failing tests.**
  - In `check-docs.test.mjs`: on a fixture tree, check 39 fails on a planted `{communication_language}`, on a planted `_bmad/scripts/pm-status/__main__.py`, and on a bare `{output_folder}` binding, and it passes on `core.output_folder`.
  - In the sanctum suite: `init-sanctum.py` run with no config renders no file containing `{user_name}`.
- [ ] **Step 2:** Delete the reads, following the note's classification:
  - delete the 31 boilerplate "Communicate … in `{communication_language}`" lines;
  - delete the two subagent hand-off mentions in `step-05-epic-loop.md`;
  - remove the `user_name` and `communication_language` plumbing from the sanctum. The templates address the user as "you", and `--user-name`/`--communication-language` are removed from `init-sanctum.py`;
  - drop the binding-table rows.

  Then sync and regenerate the manifests.
- [ ] **Step 3: Add check 39 with its config-key arms only.** The `_bmad/scripts/pm-status` arm would fail on today's tree, so Task 3.2 adds it, in the same commit that rebinds the last caller. Every commit stays green.
- [ ] **Step 4:** Run every gate in `checks.yml` and both suites.
- [ ] **Step 5: Commit.** `feat(infra)!: read only the config v7 provides; check 39 keeps it so`.

### Task 3.2: Declare `pm_status`; every caller uses the declared copy

**Files:**
- Modify: `scripts/sync-shared-scripts.mjs`. It writes `[skill] scripts` into the `bmod.toml` of each skill that carries a `pm_status` payload: every `.py` under `scripts/pm_status/`, sorted, with paths relative to the skill. Its `--check` fails on any difference, naming the file.
- Modify: `skills/l3io-pm/l3io-execute/bmod.toml` and `skills/l3io-util/l3io-doctor/bmod.toml` (generated).
- Modify: every `{pm_status}` binding and literal path. The shared steps (`step-00-activate.md` and `step-05-epic-loop.md`'s `--pm-status` arguments) use `{project-root}/_bmad/l3io-pm/scripts/pm_status/__main__.py`. `l3io-doctor`'s own files use `{project-root}/_bmad/l3io-util/scripts/pm_status/__main__.py`. Shared files shipped to both modules name `{pm_status}`, never a literal path.
- Modify: `tests/fixtures/v7/` smoke (`scripts/smoke-install*`). After setup, assert that both declared copies exist and that `uv run <copy> --help` exits 0.
- Test: `scripts/tests/sync-shared-scripts*.test.mjs` (or the existing sync test file).

- [ ] **Step 1: Failing test (Review Focus 1).** On a fixture tree, add `scripts/pm_status/new_mod.py` without regenerating. `sync-shared-scripts.mjs --check` exits non-zero and names `new_mod.py` and the `bmod.toml`. After `sync:scripts`, the list contains it.
- [ ] **Step 2:** Generate the lists. Then `check:bmod` must pass, since v7's validator reads `skill.scripts`.
- [ ] **Step 3: Rebind every caller.** `git grep -n "_bmad/scripts/pm-status"` over `skills/` must reach zero. Then add check 39's third arm (the old path), with its failing fixture test written first.
- [ ] **Step 4: Review Focus 2.** Before the first `{pm_status}` call, `step-00-activate.md` tests whether the declared copy exists. If it is absent, it halts with exactly `BLOCKED: _bmad/l3io-pm/scripts/pm_status is not installed — run bmad setup l3io-pm`. `l3io-doctor` does the same with `l3io-util`. Classify the new `BLOCKED:` site in `auto-remediation.md`'s `Halts` table, because check 36 requires it.
- [ ] **Step 5: Verify on the fixture.** Run `npm run smoke:install` (network, about 20 s). Both copies are present and `--help` runs.
- [ ] **Step 6:** Run every gate in `checks.yml` and both suites.
- [ ] **Step 7: Commit.** `feat(infra)!: declare pm_status in bmod.toml; v7 installs it per module`.

### Task 3.3: Delete self-install

**Files:**
- Delete from `skills/_shared/pm_status/`: the `self-install` verb, its content guard, the downgrade refusal and the shipped-hash list (`core/__init__.py`, `__main__.py`). Then delete their tests in `skills/_shared/tests/test-pm-status.py`.
- Delete: the activation self-install step in `skills/_shared/steps/shared/step-00-activate.md` §2, and `l3io-doctor`'s own activation self-install.
- Delete: the `check-pm-status` doctor mode (its `steps/` file, its routing row and its `help/help.md` row), with `tests/l3io-doctor/test-check-pm-status.py`, `scripts/check-pm-status-version.mjs`'s self-install rationale, and `docs/l3io-util-reference.md`'s section.
- Keep: `check:version`'s invariant (marker == `PM_STATUS_VERSION` == `package.json`). `report` and `--version` still print it. Rewrite its header comment to say why it exists now.
- Modify: `l3io-doctor`'s default health check to add the version-skew finding (Review Focus 3).
- Modify: `CLAUDE.md` (the self-install paragraph and the Shared Files table), `scripts/CLAUDE.md`, and every doc `git grep -il self-install` names outside `docs/superpowers/`, `docs/adr/` and `CHANGELOG.md`. Add a short amendment to ADR-0001 stating that 4.x retires self-install in favour of declared scripts.

- [ ] **Step 1: Failing test (Review Focus 3).** In the doctor suite: with two fixture copies whose `PM_STATUS_VERSION` differ, the health-check script reports one finding naming both paths and both versions. With identical copies it reports none.
- [ ] **Step 2:** Delete. Afterwards `git grep -n -i "self-install\|self_install\|check-pm-status"` over `skills/`, `scripts/`, `tests/`, `package.json` and `.versionrc.cjs` reaches zero. Run `sync:scripts` and the manifests.
- [ ] **Step 3: Review Focus 4, on the fixture.** Plant `_bmad/scripts/pm-status/__main__.py` in a fixture project, then re-run v7 setup. Record whether it is removed. If it is not, the doctor's `clean-legacy` mode lists it, with a test.
- [ ] **Step 4:** Run every gate in `checks.yml`, both suites, and `smoke:install`.
- [ ] **Step 5: Commit.** `feat(infra)!: retire self-install; v7 installs pm_status`.

**Exit (Phase 3):** no self-install anywhere; both declared copies resolve and run on the fixture; R7 holds under check 39; every `checks.yml` gate is green.
