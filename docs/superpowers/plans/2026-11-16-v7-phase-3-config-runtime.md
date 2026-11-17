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

> **Done 2026-11-16** — `ab8b43b`. 26 boilerplate language lines went, not 31: the note's
> count included lines outside the canonical set. Check 39 (`v7-config-keys`) scans 187
> shipped files and has three arms: the three keys, a `{output_folder}` binding that does not
> name `core.output_folder`, and a resolver `--key output_folder`. A *binding* is a list item
> or table row that opens with the placeholder. A use such as `{output_folder}/l3io/` is not
> judged. `init-sanctum.py` read nothing but the two keys, so its resolver call went with them.
> The module-setup files needed no exemption: their one mention was documentation and is reworded.
> `docs/l3io-pm-reference.md` and `docs/l3io-sec-reference.md` were brought in line too. The
> plan's planted `_bmad/scripts/pm-status` test is deferred to Task 3.2 with its arm.

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

- [x] **Step 1: Failing tests.**
  - In `check-docs.test.mjs`: on a fixture tree, check 39 fails on a planted `{communication_language}`, on a planted `_bmad/scripts/pm-status/__main__.py`, and on a bare `{output_folder}` binding, and it passes on `core.output_folder`.
  - In the sanctum suite: `init-sanctum.py` run with no config renders no file containing `{user_name}`.
- [x] **Step 2:** Delete the reads, following the note's classification:
  - delete the 31 boilerplate "Communicate … in `{communication_language}`" lines;
  - delete the two subagent hand-off mentions in `step-05-epic-loop.md`;
  - remove the `user_name` and `communication_language` plumbing from the sanctum. The templates address the user as "you", and `--user-name`/`--communication-language` are removed from `init-sanctum.py`;
  - drop the binding-table rows.

  Then sync and regenerate the manifests.
- [x] **Step 3: Add check 39 with its config-key arms only.** The `_bmad/scripts/pm-status` arm would fail on today's tree, so Task 3.2 adds it, in the same commit that rebinds the last caller. Every commit stays green.
- [x] **Step 4:** Run every gate in `checks.yml` and both suites.
- [x] **Step 5: Commit.** `feat(infra)!: read only the config v7 provides; check 39 keeps it so`.

### Task 3.2: Declare `pm_status`; every caller uses the declared copy

> **Done 2026-11-16** — `3014660`. The generated list has 20 entries per declarer. `--check`
> fails with `UNDECLARED: <bmod.toml> [skill] scripts lacks <script>`. It also fails on an extra
> entry and on the list being out of order. The tests are in `scripts/tests/sync-shared-scripts.test.mjs`.
> The grep does not reach zero. Seven lines still name `_bmad/scripts/pm-status`: self-install's
> `--dest` (shared activation, synced twice, plus `l3io-doctor`'s), and the `clean-payload.py` and
> `check-pm-status.py` constants. Self-install stays until Task 3.3, so each of those lines
> carries `check-39: legacy-path -- <reason>`, and check 39 exempts only a line with that marker
> and a reason. 3.3 deletes them. The legacy `clean-payload.py` constants may keep theirs for
> Review Focus 4. Activation still self-installs, but no step calls that copy. Check 36 scans
> only `skills/_shared/steps`, so the `l3io-doctor` halt in its `SKILL.md` has no table row.
> smoke:install passes, and both copies run `--help`.

**Files:**
- Modify: `scripts/sync-shared-scripts.mjs`. It writes `[skill] scripts` into the `bmod.toml` of each skill that carries a `pm_status` payload: every `.py` under `scripts/pm_status/`, sorted, with paths relative to the skill. Its `--check` fails on any difference, naming the file.
- Modify: `skills/l3io-pm/l3io-execute/bmod.toml` and `skills/l3io-util/l3io-doctor/bmod.toml` (generated).
- Modify: every `{pm_status}` binding and literal path. The shared steps (`step-00-activate.md` and `step-05-epic-loop.md`'s `--pm-status` arguments) use `{project-root}/_bmad/l3io-pm/scripts/pm_status/__main__.py`. `l3io-doctor`'s own files use `{project-root}/_bmad/l3io-util/scripts/pm_status/__main__.py`. Shared files shipped to both modules name `{pm_status}`, never a literal path.
- Modify: `tests/fixtures/v7/` smoke (`scripts/smoke-install*`). After setup, assert that both declared copies exist and that `uv run <copy> --help` exits 0.
- Test: `scripts/tests/sync-shared-scripts*.test.mjs` (or the existing sync test file).

- [x] **Step 1: Failing test (Review Focus 1).** On a fixture tree, add `scripts/pm_status/new_mod.py` without regenerating. `sync-shared-scripts.mjs --check` exits non-zero and names `new_mod.py` and the `bmod.toml`. After `sync:scripts`, the list contains it.
- [x] **Step 2:** Generate the lists. Then `check:bmod` must pass, since v7's validator reads `skill.scripts`.
- [x] **Step 3: Rebind every caller.** `git grep -n "_bmad/scripts/pm-status"` over `skills/` must reach zero. Then add check 39's third arm (the old path), with its failing fixture test written first.
- [x] **Step 4: Review Focus 2.** Before the first `{pm_status}` call, `step-00-activate.md` tests whether the declared copy exists. If it is absent, it halts with exactly `BLOCKED: _bmad/l3io-pm/scripts/pm_status is not installed — run bmad setup l3io-pm`. `l3io-doctor` does the same with `l3io-util`. Classify the new `BLOCKED:` site in `auto-remediation.md`'s `Halts` table, because check 36 requires it.
- [x] **Step 5: Verify on the fixture.** Run `npm run smoke:install` (network, about 20 s). Both copies are present and `--help` runs.
- [x] **Step 6:** Run every gate in `checks.yml` and both suites.
- [x] **Step 7: Commit.** `feat(infra)!: declare pm_status in bmod.toml; v7 installs it per module`.

### Task 3.3: Delete self-install

> **Done 2026-11-17** — `82b7983`. The verb and everything that existed only for it are gone:
> the content guard, the downgrade refusal, `_SHIPPED_SHAS`, `package_root`, `tree_digest`,
> `sweep_stale`, `_file_sha` and `_parse_version_line`. `core` now registers no verb, so the
> CLI has 42 subcommands. Both activation steps went too, along with the sibling-payload halt
> they needed. The `check-pm-status` mode is deleted (step file, routing row, help rows, script,
> suite), and the doctor now has twenty modes. `report-version.py` reads
> `_bmad/{l3io-pm,l3io-util}/scripts/pm_status/__main__.py`. Copies that disagree produce exit
> 3 and one finding naming both paths and both versions. A copy that is absent or lagging is
> explained but not flagged. Health-check Check 25 runs it. Step 2's grep reaches zero except
> for the ADR-0001 filename (ruling below). Review Focus 4: on the fixture, re-running setup
> removed both a planted `_bmad/scripts/pm-status/` and `pm-status.py`, and `smoke:install`
> now asserts it, so `clean-legacy` needed no change. Gates: every `checks.yml` step,
> test:python 21/21, test:scripts 427/427, smoke:install PASS.
>
> - Ruling: the 3.x v7 refusal is retired and inverted. §0 keeps the two v7 markers and halts
>   with `BLOCKED: BMad v7 not detected. l3io 4.x supports BMad v7 only; on BMad 6.x install
>   l3io 3.x.` That covers `unknown` (no BMad) too. Its `Halts` row replaces the old one, and the
>   only copies were the shared file and its two synced copies — why: on this branch the old
>   halt stopped every l3io-pm skill on the install 4.x is for — cost if wrong: a 6.x user of a
>   4.x build is told to change line rather than getting a 6.x run, which is what 3.x is for.
> - Ruling: `clean-payload.py` keeps `_LEGACY_COPY`/`_LEGACY_COPY_DIR`, renamed from
>   `_SELF_INSTALLED*`. Their markers now give an uninstall reason, and no marker's reason is
>   self-install — why: a project that added 4.x skills but has not re-run setup still has the
>   3.x copy, and uninstall should take it — cost if wrong: two marked constants and their
>   tests that never fire.
> - Ruling: the version-skew finding lives in `report-version.py` and Check 25 reads its JSON.
>   No second reader was added. The finding reads each copy's marker — why: one reader means
>   one answer between `version` and the health check, and `check:version` keeps the marker
>   equal to `PM_STATUS_VERSION` — cost if wrong: none at runtime; a copy with a hand-edited
>   marker would be reported by its marker.
> - Ruling: `report-version.py` also accepts `generated_from = "skills/<skill>/"`, test first.
>   Since 2026-10-10 it recognised only `skills/_shared/`, so on every current install it found
>   no skills and exited 4 — why: without this, Check 25 would be inert on every real install —
>   cost if wrong: none; `clean-payload.py` already accepts the same pair. The defect is on
>   `main` (3.x) too.
> - Ruling: `scripts/check-pm-status-version.mjs` becomes `scripts/check-version.mjs`, with its
>   test renamed to match — why: Step 2's grep covers `scripts/`, and the old name contains
>   `check-pm-status` — cost if wrong: one rename, and `check:version` and `prerelease` are
>   repointed.
> - Ruling: check:docs' forward CLI arm drops `self` from its hand-kept prefix list — why: once
>   the verb is gone, the prefix only judged release history (the ADR-0001 title, ADR-0014, the
>   upgrade notes, a dated assessment). The title's first-line match could never carry removal
>   wording — cost if wrong: a doc claiming a new `self-*` verb is judged only in the explicit
>   `pm-status.py self-…` form or on a same-line pm_status claim.
> - Ruling: Step 2's grep leaves three hits, all on the ADR-0001 filename
>   (`0001-pm-status-single-self-installed-file.md`, in check 12 and its test) — why: an ADR's
>   filename is history and is not renamed — cost if wrong: none.
> - Ruling: the docs sweep edited every live doc, but left two lines of release history alone:
>   `docs/2026-09-26-outstanding-work-assessment.md:135` and the 3.0.1 todo in
>   `docs/handoff/bmad-extensions.md`. The same applies to upgrading.md's 3.x version notes,
>   which describe what those releases did — why: rewriting a dated record falsifies it, which
>   is the reason the plan already excludes `docs/superpowers/`, `docs/adr/` and `CHANGELOG.md`
>   — cost if wrong: two stale mentions in history.
> - Open: the `BLOCKED:` line in the doctor's `SKILL.md` is still unclassified, because check 36
>   scans only `skills/_shared/steps`. Check 36 was not widened.

- Delete from `skills/_shared/pm_status/`: the `self-install` verb, its content guard, the downgrade refusal and the shipped-hash list (`core/__init__.py`, `__main__.py`). Then delete their tests in `skills/_shared/tests/test-pm-status.py`.
- Delete: the activation self-install step in `skills/_shared/steps/shared/step-00-activate.md` §2, and `l3io-doctor`'s own activation self-install.
- Delete: the `check-pm-status` doctor mode (its `steps/` file, its routing row and its `help/help.md` row), with `tests/l3io-doctor/test-check-pm-status.py`, `scripts/check-pm-status-version.mjs`'s self-install rationale, and `docs/l3io-util-reference.md`'s section.
- Keep: `check:version`'s invariant (marker == `PM_STATUS_VERSION` == `package.json`). `report` and `--version` still print it. Rewrite its header comment to say why it exists now.
- Modify: `l3io-doctor`'s default health check to add the version-skew finding (Review Focus 3).
- Modify: `CLAUDE.md` (the self-install paragraph and the Shared Files table), `scripts/CLAUDE.md`, and every doc `git grep -il self-install` names outside `docs/superpowers/`, `docs/adr/` and `CHANGELOG.md`. Add a short amendment to ADR-0001 stating that 4.x retires self-install in favour of declared scripts.

- [x] **Step 1: Failing test (Review Focus 3).** In the doctor suite: with two fixture copies whose `PM_STATUS_VERSION` differ, the health-check script reports one finding naming both paths and both versions. With identical copies it reports none.
- [x] **Step 2:** Delete. Afterwards `git grep -n -i "self-install\|self_install\|check-pm-status"` over `skills/`, `scripts/`, `tests/`, `package.json` and `.versionrc.cjs` reaches zero. Run `sync:scripts` and the manifests.
- [x] **Step 3: Review Focus 4, on the fixture.** Plant `_bmad/scripts/pm-status/__main__.py` in a fixture project, then re-run v7 setup. Record whether it is removed. If it is not, the doctor's `clean-legacy` mode lists it, with a test.
- [x] **Step 4:** Run every gate in `checks.yml`, both suites, and `smoke:install`.
- [x] **Step 5: Commit.** `feat(infra)!: retire self-install; v7 installs pm_status`.

**Exit (Phase 3):** no self-install anywhere; both declared copies resolve and run on the fixture; R7 holds under check 39; every `checks.yml` gate is green.

> **Phase 3 Exit — met 2026-11-17.**
> - *No self-install anywhere*: `git grep -i "self-install\|self_install\|check-pm-status"` over
>   `skills/`, `scripts/`, `tests/`, `package.json` and `.versionrc.cjs` finds only the ADR-0001
>   filename (Task 3.3 ruling). No shipped file names `_bmad/scripts/pm-status` except
>   `clean-payload.py`'s two marked constants, which check 39 accepts.
> - *Both declared copies resolve and run on the fixture*: `smoke:install` PASS. Each module's
>   declared files are installed under `_bmad/<code>/scripts/`, and `--help` exits 0. The
>   doctor's report finds the two copies agreeing and reports a changed one, and a planted 3.x
>   copy is removed by setup.
> - *R7 holds under check 39*: `check:docs` passes with check 39's three arms (Task 3.1, Task 3.2).
> - *Every `checks.yml` gate green*: check:lock, check:audit, check:scripts, check:docs,
>   test:scripts (427/427), check:version, check:manifest, check:module, check:bmod,
>   check:lint:py, check:types, check:lint:sh, test:python (21/21).
