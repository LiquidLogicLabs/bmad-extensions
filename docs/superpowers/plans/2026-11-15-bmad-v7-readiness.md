# BMad v7 Readiness Implementation Plan

> **For agentic workers:** execute task-by-task with subagent-driven development or an inline
> executing-plans pass. Steps use checkbox (`- [ ]`) syntax for tracking. Phases 0–1 are
> specified to the step; Phases 2–7 are specified to the task and **each gets its own detailed
> sub-plan when it starts**, against a fresh re-pin — see "Why Phases 2–7 are outlines".

**Goal:** Be able to ship l3io **4.0.0**, a v7-native package, within days of BMad v7 GA — and
keep the 3.x line correct on v7 trees until then.

**Architecture:** Two release lines, two branches. **3.x stays v6-native on `main`**: it
finishes the bridge and learns to warn safely on a v7 tree. **4.0.0 is built on
`feat/bmad-v7-layer`** to the boundary in spec §2: v7 decides what the work is; we decide what
it costs, what order it runs in, and whether it may start. `main` merges into the v7 branch
after each 3.x release, never the reverse, until 4.0.0 ships and 3.x becomes the frozen
maintenance line (spec §8).

**Tech stack:** Python under `uv run` (PEP 723); Node check tooling; BMad v7 module format
(`bmod.toml`, `roster.toml`, `retired.toml`, `migration-<n>.toml`, `help/help.md`); Toolsmith's
`validate_manifests.py`; v7's `tickets.py` store.

**Spec:** `docs/superpowers/specs/2026-10-16-bmad-v7-layer-design.md`. **§13 governs** wherever
it conflicts with §1–§12. Re-measured at `e435a22` (2026-11-12).

## Global Constraints

- **Branches.** Phase 1 → `main`. Phases 0 and 2–7 → `feat/bmad-v7-layer`. Nothing v7-native lands on `main`.
- **No push, no release, no tag** without the user's explicit go-ahead for that specific action.
- **ADR numbers come from `pm-status.py adr-reserve` only** — never chosen by hand (CLAUDE.md, ADR-0005).
- **`pm_status` cap: 1,500 lines per `.py`.** Splitting a module is the answer to tripping it; raising it is not.
- **Edit `skills/_shared/` first**, then `npm run sync:scripts`, then `node scripts/write-payload-manifest.mjs`.
- **Never bundle a BMad core script** (`resolve_config.py`, `resolve_customization.py`, `memlog.py`, `render_skill.py`, `tickets.py`).
- **The estimates-and-actuals HARD RULE is unchanged** on both lines: five metrics, canonical order, `cost` derived and frozen, `N/A` only for non-Claude token/cost.
- **Versions only move forward.** 4.0.0 > every 3.x; 3.x patches continue after 4.0.0.
- **Re-pin before every phase.** Fetch upstream `main`, diff against the last pin, and append a drift entry to spec §13 before the phase's first task. Re-measuring is cheap, and building on a stale reading has already cost us twice.
- **Gates come from `.github/workflows/checks.yml`**, never from memory. Background `npm run test:scripts` and capture it to a file: it exceeds the 600 s foreground cap, and a killed run looks like a failing one.
- **Measured figures carry their conditions** (n, box load). A count received from another session is marked RECEIVED.

## Definition of ready

4.0.0 ships only when every row holds, verified on a project installed from the **v7 GA tag**:

| # | Criterion |
|---|---|
| R1 | Each of the four modules installs with `npx skills add <owner>/<repo>/skills/<code>`; `bmad setup <code>` asks our questions; `bmad status` reports 4.0.0 |
| R2 | `validate_manifests.py` passes over this repository |
| R3 | One epic plans, executes and closes end to end on a `repo` store, with all five metrics recorded as estimates and actuals |
| R4 | On a tracker store, no status is ever written with `tickets.py mark`; readiness runs `mirror` before `next --synced` |
| R5 | A v6 l3io project migrates under `bmad migrate` with nothing lost — calibration, events, ADR register, estimates, actuals — and its source is kept until verification passes |
| R6 | All eleven lenses resolve in the merged `bmad-review` and `bmad-code-review` customization |
| R7 | No shipped file reads `user_name`, `communication_language`, `document_output_language`, or a bare `output_folder` |
| R8 | Every retired l3io name is in a `retired.toml`; no forwarder skill ships |
| R9 | The current 3.x release, run on a v7 tree, reports accurately: `check-deps` exits 6, warns before `bmad migrate`, and flags leftover v6 shims |
| R10 | `docs/upgrading.md` covers 3.x → 4.0.0; README installs with `npx skills add`; CHANGELOG is complete |
| R11 | Every gate in `checks.yml` is green in CI on both branches |
| R12 | A `3.x` maintenance branch exists, cut from `main` at the last 3.x release |

## Review Focus

The five failure modes most likely to reach a user that no task's happy path exercises:

1. **A tracker-backed project hits `StoreRefusal` mid-epic** because something called `mark`. Expected: the store is resolved once at activation, status goes through the tracker, and `mirror` brings it back. → Phase 4, test `test_tracker_store_never_calls_mark`.
2. **A migrated project still resolves a v6.12 shim** (`bmad-create-story`, `bmad-dev-story`), so 3.x silently runs the v6 path on a v7 tree. Expected: a warning on 3.x, and no fallback chain in 4.0.0. → Task 1.4; Phase 4.
3. **Our migration is offered before method's has run.** Expected: our `detect` does not match until the v7 initiative layout exists. → Phase 6, test `test_l3io_migration_waits_for_method`.
4. **Parallel epics lose a write** when our sidecars and `bmad-build-auto`'s plan-file writes interleave; `tickets.py` takes no lock. Expected: no lost writes, measured under parallel dispatch. → Phase 4, test `test_parallel_epics_sidecars_survive`.
5. **Declared scripts are called at the wrong path.** The docs say `_bmad/scripts/`; the code installs to `_bmad/<code>/scripts/`. Expected: the call form matches a real install. → Task 0.3; Phase 3.

---

## Phase 0 — Re-baseline and decide (`feat/bmad-v7-layer`)

### Task 0.1: Record the re-measure — **done in this commit**

Spec §13 holds the `61e01f8` → `e435a22` drift log. It is listed here so the ledger shows it.

### Task 0.2: Build a real v7 fixture project and settle the four "verify before building" claims

Three spec claims are explicitly marked unverified, and Phases 3, 4 and 6 build on all three.

**Files:**
- Create: `tests/fixtures/v7/README.md` — the exact commands, the upstream pin, the date, and the observed tree.
- Create: `tests/fixtures/v7/make-fixture.sh` — reproducible; takes the pin as `$1`.

- [ ] **Step 1:** In a scratch directory, install core-tools and method at the pin with `npx skills add bmad-code-org/BMAD-METHOD/skills/core-tools#<pin>` and `…/skills/method#<pin>`, then run `bmad setup`. Record `find . -path ./node_modules -prune -o -print` into the README.
- [ ] **Step 2: Scripts destination (§3.4).** Install a throwaway single-skill module that declares `scripts = ["scripts/probe.py"]`, re-run `bmad setup`, and record whether the file appears under `_bmad/<code>/scripts/` or `_bmad/scripts/`. Expected per code: `_bmad/<code>/scripts/probe.py`.
- [ ] **Step 3: `migration-2` on an l3io tree (§13.3).** Copy a 3.6 l3io state and artifact tree into the fixture's `core.output_folder` and ask `bmad migrate` what applies. Record whether method `migration-2` matches. Expected: it does not.
- [ ] **Step 4: Leftover shims.** Into the same fixture, install `bmad-create-story` from v6.12.4, re-run `bmad setup`, and record whether it offers removal. Expected: it does not.
- [ ] **Step 5:** Append the three results to spec §13 as "verified on a real install", with the pin.
- [ ] **Step 6: Commit.** `docs(infra): verify three v7 install claims on a real fixture`.

### Task 0.3: Measure the config-read rewrite

**Files:** create `docs/superpowers/notes/2026-11-v7-config-reads.md`.

- [ ] **Step 1:** List every file reading `user_name`, `communication_language`, `document_output_language` or `output_folder`, **canonical sources only** — `skills/_shared/**` plus each skill's own non-synced files. Derive the synced set from `node scripts/sync-shared-scripts.mjs --dump-deliveries`. The 85/19/14/21 in §13.3 include synced copies and are an upper bound.
- [ ] **Step 2:** Classify each read: a *removal* (v7 has no such key), a *rewrite* (`output_folder` → `core.output_folder`), or *dead* (inside a v6-only path that 4.0.0 deletes anyway).
- [ ] **Step 3:** List every module config key that repeats its module code, since v7 requires renaming those.
- [ ] **Step 4: Commit.**

### Task 0.4: Decide — nine ADRs, status *Proposed*, for the user's review

Reserve all nine numbers at once: `uv run {project-root}/_bmad/scripts/pm-status/__main__.py adr-reserve --epic V7 --slug v7-layer --count 9`. Each ADR states the decision, the evidence (cite §13 rows), and the cost if wrong.

| ADR | Decision to make | Spec source |
|---|---|---|
| a | Supersede ADR-0008: `bmod.toml`, module records, and the end of `module.yaml` | §10.1 |
| b | v7 owns the work-item tree; we write sidecars, never `tickets.toml` | §2, §3.2 |
| c | A sprint is a batch declared in `l3io.toml`, not a level | §4.1 |
| d | Review viewpoints are contributed as lenses; workflows stay skills | §5 |
| e | Amend ADR-0006: v7 removals including `bmad-prd`, `bmad-prfaq` and `bmad-product-brief`; `bmad-help` → `bmad`; `bmm` → `method` | §10.5, §13.2 |
| f | **Migration entry point:** a native `migration-1.toml` calling `migrate-engine.py`, versus the `/l3io-doctor migrate-v7` conductor | §7, §13.3 |
| g | **Lens registration's home**, now that `l3io-setup` is deleted | §6, §13.3 |
| h | **`bmad-build-auto` review selector:** `none` (our review is the only one) or `thorough` (lenses inside, ours a second pass) | §4.3, §13.3 |
| i | **Repository layout:** `skills/<code>/` per module, and where `skills/_shared/` and the sync tooling live | §9, §13.3 |

- [ ] **Step 1:** Draft all nine. f–i carry a recommendation; a–e record decisions the spec has already made.
- [ ] **Step 2:** `npm run check:docs` — check 3 resolves the `§N` citations.
- [ ] **Step 3: Commit, then stop for the user's review.** Phases 2–6 depend on f–i.

---

## Phase 1 — 3.x stays correct on v7 trees (`main`)

Everything here is v6-line work, so it lands on `main` and merges forward.

### Task 1.1: Land `1b78b73` — **user gate**

The probe-root fix is committed and verified (9/9 static gates, 26/26 Python suites, 492/492 Node tests), but not pushed. The user decides whether to push it and whether it becomes 3.6.1. Nothing else in Phase 1 waits on this decision.

### Task 1.2: `subagent_models()` — price a mixed-model run per model (deferred bridge Task 5)

**Files:**
- Modify: `skills/_shared/pm_status/metrics/actuals_usage.py` (680 lines today; stay under 1,500)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:** Produces `subagent_models(transcript_paths: list[str]) -> dict[str, str]`, mapping each `subagents/agent-*.jsonl` path to the `model` in its sibling `agent-*.meta.json`. Consumed by `usage`'s pricing loop.

- [ ] **Step 1: Write failing tests.**
  - `test_mixed_model_run_priced_per_model` — parent on model A, one subagent whose meta says model B: each agent's tokens are priced at its own model's rates. The total must differ from pricing everything at A.
  - `test_meta_without_model_falls_back_to_parent` — prices at the parent's `--model`.
  - `test_meta_is_never_identity` — a meta file whose sibling `.jsonl` carries a different `sessionId` contributes nothing. Meta files carry no `sessionId` (spec §8.1).
- [ ] **Step 2:** Run them with `uv run skills/_shared/tests/test-pm-status.py -k subagent_models` and confirm they fail.
- [ ] **Step 3:** Implement. Meta files are attribution input only; identity stays content-verified.
- [ ] **Step 4:** Run the full suite, unscoped.
- [ ] **Step 5: Mutation check.** Force every agent to the parent model; exactly the new tests must fail. Run it ≥3 times, since this touches nothing timing-sensitive but the shared box is noisy.
- [ ] **Step 6:** Sync, regenerate manifests, run the static gates.
- [ ] **Step 7: Commit.** `feat(l3io-pm): price each dispatched agent at the model it ran on`.

### Task 1.3: `dispatch_window` refuses a naive timestamp

**Files:** `skills/_shared/pm_status/metrics/actuals_usage.py:471`; `skills/_shared/tests/test-pm-status.py`.

- [ ] **Step 1: Failing test** `test_dispatch_window_naive_ts_is_refused_not_typeerror` — an `events.jsonl` dispatch record whose `ts` has no offset yields a clear refusal (or is ignored, consistently with the transcript-side guard), never a `TypeError`.
- [ ] **Step 2:** Implement the one-line guard symmetrically with the transcript side (spec §8.2).
- [ ] **Step 3:** Run the full suite, then mutate (delete the guard → the test fails).
- [ ] **Step 4: Commit.**

### Task 1.4: Warn about leftover v6 shims on a v7 tree

**Files:** `skills/l3io-doctor/scripts/bmad-deps.py`; `tests/l3io-doctor/test-bmad-deps.py`; `skills/l3io-doctor/steps/check-deps.md`.

- [ ] **Step 1: Failing test** `test_v7_tree_with_v6_shim_is_flagged`: a v7-generation tree that also has `.agents/skills/bmad-create-story/SKILL.md` reports a `v6-shim-on-v7` finding naming the skill, and says that 3.x prefers it.
- [ ] **Step 2: Failing test** `test_v6_tree_shim_not_flagged` — the same skill on a v6 tree is normal and reports nothing new.
- [ ] **Step 3:** Implement. The shim set is the inventory's `deprecated` entries.
- [ ] **Step 4:** Run the full suite and mutate both arms. Each fixture must assert that it planted what it claims to have planted.
- [ ] **Step 5: Commit.**

### Task 1.5: Bring the `bmad migrate` hazard warning up to date

**Files:** `docs/upgrading.md:838` (section "BMad v7: do not run `bmad migrate` on an l3io-pm project yet").

- [ ] **Step 1:** Add `migration-2` (`7 preview` → `7`) using the result of Task 0.2 Step 3, the newly removed `bmad-prd`/`bmad-prfaq`/`bmad-product-brief`, and the leftover-shim behaviour from Task 0.2 Step 4. Cite the pin.
- [ ] **Step 2:** `npm run check:docs`. **Commit.**

### Task 1.6: Transcript-fallback binding — design only, not GA-blocking

Spec §8.2: binding `runtime=claude` on a recovered transcript risks mis-binding a non-Claude runtime that has a dormant `~/.claude` tree. Write a design note with options and a recommendation under `docs/superpowers/notes/`, and stop for review. Implementation is a separate decision.

### Task 1.7: Release — **user gate**

After 1.2–1.5: the full gate set, then `npm run release` on approval. Then merge `main` into `feat/bmad-v7-layer`. This satisfies R9 for that release.

---

## Why Phases 2–7 are outlines

Spec §8.1 holds 4.0.0's detailed planning until GA stops the surface moving. §13.4 found that the surface §2–§5 build on did **not** move in 29 commits. What moved was packaging. So these phases can start now; each one opens with a re-pin and its own detailed sub-plan. The task lists, exit criteria and order below are firm. The step-level code is written against the pin current when the phase starts.

## Phase 2 — Packaging (`feat/bmad-v7-layer`) — needs ADRs a, e, i

1. **Run Toolsmith's migrate mode over each module first** and keep its "cannot convert" list. Hand-finishing a machine conversion is cheaper and less error-prone than hand-converting.
2. **Re-lay the repository as `skills/<code>/`** for `l3io-pm`, `l3io-util`, `l3io-sec` and `l3io-arch`, per ADR i. Repoint `sync-shared-scripts.mjs`, `write-payload-manifest.mjs`, and every path in `check-docs.mjs`.
3. **Write the module records.** `bmod-l3io-pm/bmod.toml` gets `[[bmod.config_questions]]` for every key `l3io-setup` asks today (`lane_count`, `business_ac_required`, …). The single-skill modules get theirs in their own `bmod.toml`. Every member skill gets a `bmod.toml` with `[skill]`.
4. **`roster.toml`** for `l3io-sec-redteam`; **`help/help.md`** per module, generated from `module-help.csv`.
5. **`retired.toml`:** `renamed` covers `l3io-pm-execute` → `l3io-execute`, `l3io-pm-plan` → `l3io-plan`, `l3io-pm-help` → `l3io-help` and `l3io-pm-sync` → `l3io-sync`. `removed` covers `l3io-setup`. Delete the four forwarders (R8).
6. **`required_skills`:** `l3io-pm` requires `l3io-doctor` with `source` and a minimum `version`.
7. **One version across all records**, written from `package.json` by `sync-bmad-versions.mjs`.
8. **Tooling:**
   - retire `check:module`'s installer rules (spec §9)
   - replace `check:bmb` with `validate_manifests.py`
   - rebuild `smoke:install` as `npx skills add` + `bmad setup` against the Task 0.2 fixture
   - rescope `check:docs`'s v6-path checks
   - drop `.claude-plugin/marketplace.json` from this branch

**Exit:** R1 and R2 on the fixture. **Tests:** `test_validate_manifests_clean`, `test_every_skill_has_bmod_toml`, `test_retired_names_never_shipped`.

## Phase 3 — Config and runtime (`feat/bmad-v7-layer`) — needs Task 0.3, ADR a

1. **Config-read rewrite** from Task 0.3's classification (R7). Add a `check:docs` check that fails on any shipped read of a v7-absent key — the guard that keeps R7 true.
2. **Declared scripts.** List the whole `pm_status/` package, `spec-align.py` and `migrate-engine.py` in `[skill] scripts`. Use the call form `uv run {project-root}/_bmad/<code>/scripts/…`, exactly as Task 0.2 Step 2 observed.
3. **Delete `self-install`** and everything that exists only for it: the content guard, the downgrade refusal, the shipped-hash list, `check-pm-status`, and the activation step in `step-00-activate.md`. Spec §3.4.
4. **Narrow `pm_status`** to spec §4.5. It loses the placement model and every issues verb, and keeps estimate, calibration, actuals, test runs, the event log, `adr-reserve` and `report`.

**Exit:** no self-install anywhere; scripts resolve on the fixture; R7.

## Phase 4 — The work-item tree (`feat/bmad-v7-layer`) — needs ADRs b, c, h

1. **Data placement** (§3.3): `l3io.toml` in each container's `tickets/` folder; a per-ticket sidecar beside each plan file; project-wide data under `{output_folder}/l3io/`.
2. **Levels** (§4.1), including the parent initiative as a portfolio scope.
3. **Plan** (§4.2), reading `tickets.py status`/`next`. On a tracker store it runs `mirror`, then `next --synced` (§13.3). Our readiness adds the six technical-AC dimensions, the business ACs, `Spec:` pointers and an estimate.
4. **Execute** (§4.3): gates → `tickets.py pull` → `bmad-build-auto` with the ADR h selectors → review → fix loop → QA → actuals → status. Remove the `bmad-create-story`/`bmad-dev-story` fallback chain and the in-package dev agent.
5. **Store-aware status writes** (§4.4): resolve the store once at activation with `read_store.py -k tickets`; never call `mark` on a non-`repo` store.
6. **The backlog:** `issues.yaml` dissolves into v7 `backlog/` leaves (§3.3), and the audit (findings 1a–1l) becomes a doctor mode over v7's tree.

**Exit:** R3 and R4 on the fixture. **Tests:** `test_tracker_store_never_calls_mark`, `test_parallel_epics_sidecars_survive` (Review Focus 1, 2, 4).

## Phase 5 — Lenses (`feat/bmad-v7-layer`) — needs ADRs d, g

1. Write the eleven lenses in §5.2: five engineering, five threat, plus AI-poisoning `after` external. Each one's `instruction` points at our own reference file.
2. Register them where ADR g decides, into `_bmad/custom/bmad-review.toml` and `_bmad/custom/bmad-code-review.toml`.
3. Make `l3io-arch-review` Mode B a caller of `bmad-review`. Split `l3io-sec-redteam`: workflows and persona stay, viewpoints move to lenses.

**Exit:** R6, verified by resolving both merged customizations on the fixture and listing all eleven codes.

## Phase 6 — Migration (`feat/bmad-v7-layer`) — needs ADR f, Task 0.2 Step 3

1. Build the entry point ADR f chooses. If it's native: `migration-1.toml` with `module = "l3io-pm"`, `from = "3"`, `to = "4"`, a `detect` that requires the v7 initiative layout to already exist (Review Focus 3), a `guide` that invokes `migrate-engine.py`, and a `checklist` that verifies every moved datum.
2. Add engine readers and writers for the four v6 layouts → §3.3 targets (§7's list), keeping detect → read → resolve → plan → **gate** → write → verify → dispose.
3. Build fixtures for each source layout, including one with a leftover v6 shim.

**Exit:** R5. **Tests:** `test_l3io_migration_waits_for_method`, `test_migration_preserves_calibration_events_adr_register`, `test_source_kept_until_verify`.

## Phase 7 — Release gate

1. **Re-pin to the v7 GA tag** and run the §13-style re-measure. Only phases whose dependencies moved go back to rework.
2. **Rebuild the fixture from GA** (Task 0.2's script) and verify R1–R8 end to end.
3. **Docs:** a `docs/upgrading.md` 3.x → 4.0.0 section; README install via `npx skills add`; CHANGELOG (R10).
4. **Cut `3.x` from `main`** at the last 3.x release (R12) — **user gate**.
5. **CI green on both branches** (R11). Then `npm run release` for 4.0.0 — **user gate**.
6. **Send the adoption packet** to the downstream package. It is 6.x-scoped today, so it may decline; record either way.

## Order and contingency

- **Now:** Phase 0 Tasks 0.2–0.4 and Phase 1 run in parallel; they touch different branches.
- **After the ADR review:** Phases 2 → 3 → 4 in order, since 4 needs 3's scripts and 3 needs 2's layout. Phases 5 and 6 can run beside 4.
- **If GA lands mid-phase:** finish the current task, re-pin, append to §13, and rework only what the drift touches. The spec's own history argues for this: one pin needed six sections reworked; the next needed none of §2–§5.
- **Release with what's ready.** If GA lands before 4.0.0 is ready, 3.x is the supported line on v7 trees in degraded mode — that is R9's purpose — and `docs/upgrading.md` says so.
