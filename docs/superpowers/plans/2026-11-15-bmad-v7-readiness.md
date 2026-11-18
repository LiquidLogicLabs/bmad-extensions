# BMad v7 Readiness Implementation Plan

> **For agentic workers:** execute task-by-task with subagent-driven development or an inline
> executing-plans pass. Steps use checkbox (`- [ ]`) syntax for tracking. Phases 0–1 are
> specified to the step; Phases 2–7 are specified to the task and **each gets its own detailed
> sub-plan when it starts**, against a fresh re-pin — see "Why Phases 2–7 are outlines".

**Goal:** Be able to ship l3io **4.0.0**, a v7-native package, within days of BMad v7 GA — and
keep 3.x correct on BMad 6.x. **l3io 3.x is for BMad 6.x and l3io 4.x is for BMad v7** (user,
2026-11-16); 3.x does not run on v7, it detects a v7 install and says so.

**Architecture:** 4.0.0 **extends v7; it does not replace it** (spec §14). A user runs v7's
skills — Sofia for planning, `bmad-build`/`bmad-build-auto` for implementation, BMad's own review
and retrospective. Every l3io capability attaches to one of those skills through an extension
point v7 ships: menu items, stage hooks, `on_complete`, lenses, `persistent_facts`. An l3io skill
exists only where v7 has nothing to attach to: unattended multi-ticket orchestration, estimation
and calibration, migration and diagnostics, ADR allocation, the red-team persona.

Two release lines, two branches. **3.x stays BMad-6.x-only on `main`**: it finishes the bridge and
learns to recognise a v7 install and refuse with a pointer to 4.x. **4.0.0 is built on `feat/bmad-v7-layer`.** `main` merges
into the v7 branch after each 3.x release, never the reverse, until 4.0.0 ships and 3.x becomes
the frozen maintenance line (spec §8).

**Tech stack:** Python under `uv run` (PEP 723); Node check tooling; BMad v7 module format
(`bmod.toml`, `roster.toml`, `retired.toml`, `migration-<n>.toml`, `help/help.md`); Toolsmith's
`validate_manifests.py`; v7's `tickets.py` store.

**Spec:** `docs/superpowers/specs/2026-10-16-bmad-v7-layer-design.md`. **§13 governs** wherever
it conflicts with §1–§12. Re-measured at `e435a22` (2026-11-12).

## Global Constraints

- **Extend, do not replace (spec §14).** Before building any capability, name the v7 skill it attaches to and the extension point it uses (§14.1). If v7 already has the capability, use v7's — do not build a second one. A new standalone l3io skill needs a sentence saying why no v7 skill can host it. The test: *if the user never types an `l3io-` command, which of our capabilities still happen?*
- **Never overwrite a user's customization.** Wire-in merges keyed and list entries into `_bmad/custom/<skill>.toml` and refuses on a non-empty single-slot string hook (§14.2).
- **Branches.** Phase 1 → `main`. Phases 0 and 2–7 → `feat/bmad-v7-layer`. Nothing v7-native lands on `main`.
- **No push, no release, no tag** without the user's explicit go-ahead for that specific action.
- **ADR numbers come from `pm-status.py adr-reserve` only** — never chosen by hand (CLAUDE.md, ADR-0005).
- **`pm_status` cap: 1,500 lines per `.py`.** Splitting a module is the answer to tripping it; raising it is not.
- **Edit `skills/_shared/` first**, then `npm run sync:scripts`, then `node scripts/write-payload-manifest.mjs`.
- **Never bundle a BMad core script** (`resolve_config.py`, `resolve_customization.py`, `memlog.py`, `render_skill.py`, `tickets.py`).
- **The estimates-and-actuals HARD RULE is unchanged** on both lines: five metrics, canonical order, `cost` derived and frozen, `N/A` only for non-Claude token/cost.
- **Version mapping: l3io 3.x ↔ BMad 6.x; l3io 4.x ↔ BMad v7** (user, 2026-11-16). Everything shipped in a 3.x release must work on BMad 6.x and is verified against v6.12.4. Anything v7-specific goes on `feat/bmad-v7-layer`; the only v7 knowledge allowed on `main` is enough to detect a v7 install and refuse.
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
| R3 | One epic plans **in Sofia**, executes and closes end to end on a `repo` store, with all five metrics recorded as estimates and actuals — and no `l3io-` command typed except `l3io-execute` for the unattended run |
| R13 | **Measurement without our entry points:** a user who runs only `bmad-build` on one ticket still gets a dispatch bracket, actuals and a calibration sample recorded |
| R14 | **No duplicated engine:** no l3io code review, fix loop, story elaborator, re-planner, help router or tracker sync ships; each was retired in favour of v7's (§14.3) |
| R15 | **Wire-in is reversible and polite:** `l3io-doctor` wire-in then unwire leaves every `_bmad/custom/*.toml` byte-identical to before, and a team's own non-empty string hook is never overwritten |
| R4 | On a tracker store, no status is ever written with `tickets.py mark`; readiness runs `mirror` before `next --synced` |
| R5 | A v6 l3io project migrates under `bmad migrate` with nothing lost — calibration, events, ADR register, estimates, actuals — and its source is kept until verification passes |
| R6 | All eleven lenses resolve in the merged `bmad-review` and `bmad-code-review` customization |
| R7 | No shipped file reads `user_name`, `communication_language`, `document_output_language`, or a bare `output_folder` |
| R8 | Every retired l3io name is in a `retired.toml`; no forwarder skill ships |
| R9 | The current 3.x release, run on a v7 install, refuses at activation and says 3.x supports BMad 6.x and 4.x is needed for v7; `docs/upgrading.md` warns against `bmad migrate` on an l3io project |
| R10 | `docs/upgrading.md` covers 3.x → 4.0.0; README installs with `npx skills add`; CHANGELOG is complete |
| R11 | Every gate in `checks.yml` is green in CI on both branches |
| R12 | A `3.x` maintenance branch exists, cut from `main` at the last 3.x release |

## Review Focus

The five failure modes most likely to reach a user that no task's happy path exercises:

1. **A tracker-backed project hits `StoreRefusal` mid-epic** because something called `mark`. Expected: the store is resolved once at activation, status goes through the tracker, and `mirror` brings it back. → Phase 4, test `test_tracker_store_never_calls_mark`.
2. **A migrated project still resolves a v6.12 shim** (`bmad-create-story`, `bmad-dev-story`), so 3.x would silently run the v6 path on a v7 tree. Expected: 3.x refuses on any v7 install (Task 1.4), and 4.0.0 has no fallback chain (Phase 4).
3. **Our migration is offered before method's has run.** Expected: our `detect` does not match until the v7 initiative layout exists. → Phase 6, test `test_l3io_migration_waits_for_method`.
4. **Parallel epics lose a write** when our sidecars and `bmad-build-auto`'s plan-file writes interleave; `tickets.py` takes no lock. Expected: no lost writes, measured under parallel dispatch. → Phase 4, test `test_parallel_epics_sidecars_survive`.
5. **Wire-in clobbers a team's own hook.** A team already sets `tickets_after` or `on_complete`; our wire-in replaces it, and their behaviour vanishes silently. Expected: refuse, name both values, change nothing. → Phase 2, test `test_wire_in_refuses_nonempty_string_hook`.

(The declared-scripts path — `_bmad/scripts/` in the docs versus `_bmad/<code>/scripts/` in the code — is settled on a real install by Task 0.2, before anything is built on it.)

---

## Phase 0 — Re-baseline and decide (`feat/bmad-v7-layer`)

### Task 0.1: Record the re-measure — **done in this commit**

Spec §13 holds the `61e01f8` → `e435a22` drift log. It is listed here so the ledger shows it.

### Task 0.2: Build a real v7 fixture project and settle the four "verify before building" claims

> **Done 2026-11-16.** `tests/fixtures/v7/make-fixture.sh` reproduces the fixture; results are in
> spec §13.5. Two expectations were wrong. Scripts land at `_bmad/<code>/scripts/` as the code
> says. `migration-2` **can** match an l3io-shaped tree, through any hand-written
> `epic-*/*-plan.md`. Leftover shims are not offered for removal, as expected. Three findings
> were new: the preview reports `6.13.0-next`; v7 treats a multi-tool install as duplicates and
> offers to delete copies; and `config_utils.py` is not a v7 marker, which made 3.7.0's v7
> refusal miss mid-upgrade trees. That is fixed on `main` (`129776e`) for 3.7.2. Ruling: Step 3
> was run by applying each migration's `detect` prose by hand to a real project, because
> `bmad migrate` is an agent reading prose, not a script.

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

> **Done 2026-11-16** — `docs/superpowers/notes/2026-11-v7-config-reads.md`. v7's resolver
> returns only `core.project_name` and `core.output_folder`. The rewrite is mostly deletion: 31
> boilerplate language lines, plus dead `user_name`/`communication_language` plumbing that
> already defaults safely. Every `output_folder` read already uses `core.output_folder`. One
> behavioural fix: `drift-report.py` must expand the literal `{project-root}` that v7's value
> carries. No module key repeats its module code.

**Files:** create `docs/superpowers/notes/2026-11-v7-config-reads.md`.

- [ ] **Step 1:** List every file reading `user_name`, `communication_language`, `document_output_language` or `output_folder`, **canonical sources only** — `skills/_shared/**` plus each skill's own non-synced files. Derive the synced set from `node scripts/sync-shared-scripts.mjs --dump-deliveries`. The 85/19/14/21 in §13.3 include synced copies and are an upper bound.
- [ ] **Step 2:** Classify each read: a *removal* (v7 has no such key), a *rewrite* (`output_folder` → `core.output_folder`), or *dead* (inside a v6-only path that 4.0.0 deletes anyway).
- [ ] **Step 3:** List every module config key that repeats its module code, since v7 requires renaming those.
- [ ] **Step 4: Commit.**

### Task 0.4: Decide — nine ADRs, status *Proposed*, for the user's review

> **Drafted 2026-11-16**, numbers from `adr-reserve --count 9`: a → ADR-0013, b → 0014,
> c → 0015, d → 0016, e → 0017, f → 0018, g → 0019, h → 0020, i → 0021. a, d and g are
> **Accepted**, each recording the user's decision. b, c, e, f, h and i were drafted as
> **Proposed**; **the user accepted all six on 2026-11-16.** Phases 2–6 are unblocked.

Reserve all nine numbers at once: `uv run {project-root}/_bmad/scripts/pm-status/__main__.py adr-reserve --epic V7 --slug v7-layer --count 9`. Each ADR states the decision, the evidence (cite §13 rows), and the cost if wrong.

| ADR | Decision to make | Spec source |
|---|---|---|
| a | **Extend v7, do not replace it** — the governing rule and its test | §14 |
| b | Supersede ADR-0008: `bmod.toml`, module records, and the end of `module.yaml` | §10.1 |
| c | v7 owns the work-item tree; we write sidecars, never `tickets.toml` | §2, §3.2 |
| d | **Sprints in 4.0.0: none** — the epic is the closure unit; calibration is already per story. **Decided by the user 2026-11-16** | §4.1, §14.3 |
| e | Review viewpoints are contributed as lenses; BMad's review and fix loop are the only ones; workflows stay skills | §5, §14.3 |
| f | Amend ADR-0006: v7 removals including `bmad-prd`, `bmad-prfaq` and `bmad-product-brief`; `bmad-help` → `bmad`; `bmm` → `method` | §10.5, §13.2 |
| g | **Migration entry point: native** `migration-1.toml` calling `migrate-engine.py`; no `/l3io-doctor migrate-v7` conductor. **Decided by the user 2026-11-16** | §7, §13.3 |
| h | **Wire-in:** `l3io-doctor` owns an idempotent merge and unwire for every §14.1 surface; refuses on single-slot string-hook collisions | §14.2 |
| i | **Repository layout:** `skills/<code>/` per module, and where `skills/_shared/` and the sync tooling live | §9, §13.3 |

- [ ] **Step 1:** Draft all nine. a, h and i carry a recommendation; d and g record the user's 2026-11-16 decisions; b, c, e and f record decisions the spec has already made.
- [ ] **Step 2:** `npm run check:docs` — check 3 resolves the `§N` citations.
- [ ] **Step 3: Commit, then stop for the user's review.** Phases 2–6 still wait on a, h and i.

### Task 0.5: Propose a module customization layer upstream — **user gate before posting**

There is no layer through which a module contributes customization (§14.2). That's why we must write to a team's own files at all. A fourth layer — module-shipped, merged below the team file — would let every third-party module extend v7 without touching user-owned files. Contributing it is extending v7 in the most literal sense.

- [ ] **Step 1:** Draft the proposal under `docs/superpowers/notes/`. Cover: the problem (cite `config_utils.load_customization` and `customize-bmad.md:66-71`); the single-slot string-hook collision; a minimal design (a module ships `customize/<skill>.toml`; setup stages it; the resolver merges it between shipped and team); and that this package would be its first user.
- [ ] **Step 2: Hold until 4.0.0 works end to end** (user, 2026-11-16: approved to post *after we have everything working*), so the proposal cites a working first user. Posting an issue or PR to `bmad-code-org/BMAD-METHOD` is outward-facing, so the user decides whether, when, and in whose name. The plan does not depend on acceptance — §14.2's wire-in stands either way, and gets simpler if the layer lands.

---

## Phase 1 — 3.x correct on BMad 6.x (`main`)

> **Done 2026-11-16 — shipped as 3.7.0** (tag `3.7.0`, then merged into this branch).
> Task 1.1 → `f25166b`; 1.2 → `91de947`, extended by `ada8563` (actuals record a per-model
> split as `by_model`, and `claude-sonnet-5` corrected to $2/$10 with `RATE_HISTORY` so older
> actuals still verify — both at the user's request); 1.3 → `91de947`; 1.4 → `c687afd` (refuse
> on v7, replacing the shim warning); 1.5 → `c687afd`, with the v7 facts marked "read from code"
> until Task 0.2 observes them; 1.6 → `809a897`, design note awaiting review. Ruling: Task 1.2
> priced from each record's `message.model` rather than subagent `meta.json`, because it is
> exact, present on every record, and read from the same file. The task text below is the
> record of what was planned.

Everything here must work on BMad 6.x and is verified against v6.12.4. It lands on `main` and merges forward. Nothing here makes 3.x run on v7.

### Task 1.1: Rework `57e09aa` against BMad 6.x's install targets — then **user gate** to push

`57e09aa` (unpushed) derived its probe roots from **v7's** `registry.py` `default_roots()`. That is the wrong source for 3.x. BMad 6.12.4's `tools/installer/ide/platform-codes.yaml` installs skills for 48 platforms into **22 distinct project directories** (`.agents/skills` for 27 of them, `.claude/skills` for one, and 20 tool-specific ones such as `.cline/skills`, `.kiro/skills`, `.junie/skills`, `.trae/skills`) and 26 distinct global ones. 3.x probes only `.claude` and `.agents`, so on any of the other 20 tools every dependency reads as absent and its phase self-skips silently. The bare `{project-root}/skills` root `57e09aa` added is a v7 location and does not belong in 3.x.

- [ ] **Step 1:** Primary signal: `_bmad/_config/skill-manifest.csv` (`canonicalId`), which 6.x writes on every install regardless of tool. Directory probes become the fallback, rooted at the target dirs of the IDEs recorded in `_bmad/_config/manifest.yaml` `ides:` (6.12.4 `manifest-generator.js:380`), mapped through a vendored copy of the 6.12.4 `target_dir`/`global_target_dir` table.
- [ ] **Step 2:** Keep `57e09aa`'s removal of the 16 dead `.agents/commands` probes; drop its bare-root probe from `main` (it moves to the v7 branch).
- [ ] **Step 3:** Tests: a `.cline/skills` install resolves; a manifest-only record resolves; a bare `skills/` install on 6.x is **not** probed. Mutate each.
- [ ] **Step 4:** Full gates and suites; **user gate** before push.

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

### Task 1.4: Detect a v7 install and refuse — 3.x is for BMad 6.x

Revised 2026-11-16: under the version mapping, 3.x does not run on v7, so warning about individual leftover shims is replaced by one refusal at activation naming 4.x. The steps below keep the shim detection as one of the v7 signals.

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

## Phase 2 — Packaging and wire-in (`feat/bmad-v7-layer`) — needs ADRs a, b, f, h, i

> **Detailed sub-plan:** `docs/superpowers/plans/2026-11-16-v7-phase-2-packaging.md` (2026-11-16). It
> adds two facts measured with Toolsmith's own `scan_legacy_module.py` at the pin. The scanner
> misses `l3io-pm`'s two setup questions, because they are declared in a `variables:` list. And
> v7 questions cannot carry our validation regexes.

1. **Run Toolsmith's migrate mode over each module first** and keep its "cannot convert" list. Hand-finishing a machine conversion is cheaper and less error-prone than hand-converting.
2. **Re-lay the repository as `skills/<code>/`** for `l3io-pm`, `l3io-util`, `l3io-sec` and `l3io-arch`, per ADR i. Repoint `sync-shared-scripts.mjs`, `write-payload-manifest.mjs`, and every path in `check-docs.mjs`.
3. **Write the module records.** `bmod-l3io-pm/bmod.toml` gets `[[bmod.config_questions]]` for every key `l3io-setup` asks today (`lane_count`, `business_ac_required`, …). The single-skill modules get theirs in their own `bmod.toml`. Every member skill gets a `bmod.toml` with `[skill]`.
4. **`roster.toml`** for `l3io-sec-redteam`; **`help/help.md`** per module, generated from `module-help.csv`.
5. **`retired.toml`** (R8, R14):
   - `renamed`: `l3io-pm-execute` → `l3io-execute`, `l3io-pm-plan` → `l3io-plan`.
   - `removed`: `l3io-pm-help`, `l3io-pm-sync`, `l3io-help` (→ `bmad` via our `help/help.md`), `l3io-sync` (→ v7 stores), `l3io-setup` (→ `bmod.toml` questions).
   - Delete the four forwarders. Ship no skill v7 replaces.
5a. **Wire-in, owned by `l3io-doctor`** (ADR h, R15). It merges our entries into `_bmad/custom/<skill>.toml` for every §14.1 surface, using a round-trip-safe TOML editor so a team's comments and key order survive. Keyed arrays merge by `code`/`id`, lists append without duplicates, and a single-slot string hook is set only when empty. It records exactly what it wrote, so `unwire` can remove only our entries. `post_install_message` tells the user to run it after `bmad setup`. **Tests:**
   - `test_wire_in_is_idempotent` — running it twice changes nothing.
   - `test_unwire_restores_bytes` — wire then unwire leaves every file byte-identical.
   - `test_wire_in_refuses_nonempty_string_hook` — Review Focus 5.
   - `test_wire_in_preserves_team_comments`.
6. **`required_skills`:** `l3io-pm` requires `l3io-doctor` with `source` and a minimum `version`.
7. **One version across all records**, written from `package.json` by `sync-bmad-versions.mjs`.
8. **Tooling:**
   - retire `check:module`'s installer rules (spec §9)
   - replace `check:bmb` with `validate_manifests.py`
   - rebuild `smoke:install` as `npx skills add` + `bmad setup` against the Task 0.2 fixture
   - rescope `check:docs`'s v6-path checks
   - drop `.claude-plugin/marketplace.json` from this branch

**Exit:** R1 and R2 on the fixture. **Tests:** `test_validate_manifests_clean`, `test_every_skill_has_bmod_toml`, `test_retired_names_never_shipped`.

## Phase 3 — Config and runtime (`feat/bmad-v7-layer`) — needs Task 0.3, ADR b

1. **Config-read rewrite** from Task 0.3's classification (R7). Add a `check:docs` check that fails on any shipped read of a v7-absent key — the guard that keeps R7 true.
2. **Declared scripts.** List the whole `pm_status/` package, `spec-align.py` and `migrate-engine.py` in `[skill] scripts`. Use the call form `uv run {project-root}/_bmad/<code>/scripts/…`, exactly as Task 0.2 Step 2 observed.
3. **Delete `self-install`** and everything that exists only for it: the content guard, the downgrade refusal, the shipped-hash list, `check-pm-status`, and the activation step in `step-00-activate.md`. Spec §3.4.
4. **Narrow `pm_status`** to spec §4.5. It loses the placement model and every issues verb, and keeps estimate, calibration, actuals, test runs, the event log, `adr-reserve` and `report`.

**Exit:** no self-install anywhere; scripts resolve on the fixture; R7.

## Phase 4 — Hooks into v7's planning and build (`feat/bmad-v7-layer`) — needs ADRs a, c, d, e, h

> **Done 2026-11-17 except R3** — tasks 4.1–4.9 of
> `docs/superpowers/plans/2026-11-17-v7-phase-4-hooks.md`. R4, R13 and R14 pass on the fixture
> (`smoke:install`) and in the suites; R3 **passed on 2026-11-18** in a live session,
> recorded in `docs/superpowers/notes/2026-11-17-phase-4-r3-transcript.md`.

Everything here attaches to a v7 skill. Each item names its host and extension point (spec §14.1).

1. **Data placement** (§3.3): estimates and wave and lane data in `l3io.toml` beside each container's `tickets.toml`; actuals in a per-ticket sidecar; project-wide data under `{output_folder}/l3io/`. We never write `tickets.toml` (ADR c).
2. **Measurement on every build — host `bmad-build` and `bmad-build-auto`.** `activation_steps_prepend` opens the dispatch bracket. `on_complete` closes it, runs `usage` → `set-actual`, records test runs and appends the calibration sample. Wired in via Phase 2's wire-in. This is R13: it works when the user never touches `l3io-execute`.
3. **Estimation — host Sofia.** `tickets_after` and `refine_after` estimate each new or changed entry from class × calibration. A `[[agent.menu]]` item `code = "ESTIMATE"` re-estimates on request. `replan_after` re-estimates what a replan touched.
4. **Readiness gates — host Sofia's `validate`.** `validate_after` adds our six-dimension technical-AC check, the business-AC check and `spec-align.py check-pointers` to her findings. On a tracker store, readiness runs `tickets.py mirror` then `next --synced` (§13.3). `ac-dimensions.md` ships as a `persistent_facts` file entry so `REFINE` writes to the same dimensions the check enforces.
5. **Waves and lanes — host Sofia's `board`.** `board_after` renders parallel waves — the topological sort over `after`, including the parent-initiative scope (§4.1) — and lanes. Menu items `WAVES` and `LANES`.
6. **Unattended run — `l3io-execute`, the one orchestrator v7 lacks.** It takes `next`'s ready set, dispatches `bmad-build-auto` per ticket with `review = "thorough"` and `interactive = false`, runs waves in parallel up to `max_parallel_subagents`, and closes each epic through Sofia's retrospective offer. **It has no code review, fix loop or story-prep phase of its own** (ADR e, R14). Status goes through the store: `mark` on `repo`; on a tracker store, the tracker's write and then `mirror` (§4.4).
7. **Closure — host `bmad-retrospective`.** `on_complete` rolls up epic actuals and closure calibration.
8. **Retire what v7 already does** (R14): the dev agent and the `bmad-create-story`/`bmad-dev-story` fallback chain; `reorg` (→ Sofia's `REPLAN`); story elaboration (→ `REFINE`); `issues.yaml` (→ v7 `backlog/`, with the 1a–1l audit kept as a doctor mode over v7's tree).

**Exit:** R3, R4, R13 and R14 on the fixture. **Tests:**
- `test_bmad_build_alone_records_actuals` (R13)
- `test_tracker_store_never_calls_mark`
- `test_parallel_epics_sidecars_survive`
- `test_execute_has_no_review_phase` — the dispatch plan contains no l3io review or fix step.

## Phase 5 — Lenses and architecture (`feat/bmad-v7-layer`) — needs ADRs e, h

> **Done 2026-11-17.** Eleven lenses ship as declared scripts (`l3io-arch`'s five, `l3io-sec`'s
> six) and `/l3io-doctor wire` adds each to `bmad-review`'s `lenses` and to the `thorough_lenses`
> of `bmad-code-review`, `bmad-build` and `bmad-build-auto`. `l3io-arch`'s design review is a
> `bmad-architecture` `finalize_reviewers` entry (the re-homed epic architecture gate), beside
> its standards (`external_sources`) and documentation standard (`doc_standards`); `design`
> routes there, `decision` stays a skill. The epic-closure spec sync is a `bmad-retrospective`
> `persistent_facts` entry; applying a reconciliation is manual by design, because the
> retrospective may write only its document and approved records. R6 passes through v7's own
> merge and render code (`tests/l3io-doctor/test-lenses.py`) and on the fixture
> (`smoke:install`).

1. **Write the eleven lenses** in §5.2 (five engineering, five threat, plus AI-poisoning `after` external). Each one's `instruction` points at our own reference file. Wire them into `bmad-review` and into `bmad-code-review`/`bmad-build`'s `thorough_lenses`.
2. **`l3io-arch-review`'s standards join `bmad-architecture`.** Design guardrails go through `doc_standards` and `external_sources`; the epic design review is appended to `finalize_reviewers`. Mode A stops being a separate workflow. Mode C (ADR recording with `adr-reserve`) stays a skill.
3. **`l3io-sec-redteam`:** threat viewpoints become lenses; the persona and sanctum stay a skill for explicit red-team sessions.

**Exit:** R6. Both merged review customizations list all eleven codes, and `bmad-architecture`'s merged `finalize_reviewers` includes ours.

## Phase 6 — Migration (`feat/bmad-v7-layer`) — needs ADR g, Task 0.2 Step 3

> **Done 2026-11-17.** ADR-0019's native entry point ships: `skills/l3io-pm/bmod-l3io-pm/migration-1.toml`
> (`from = "3"`, `to = "4"`), whose `detect` requires v7's initiative layout and a finished method
> migration — measured necessary, since v7's `knowledge.py` lists migrations by module name
> (`:128`), offering `l3io-pm`'s before `method`'s. Its guide runs l3io-util's declared
> `migrate-engine.py` (detect → read → resolve → plan → gate → write → verify → dispose), which
> reads the sharded 3.x tree and the flat, split and per-epic layouts (a flat file in method's
> `archive-v6/` too) and writes only l3io's sidecars and `{output_folder}/l3io/`; it maps a 3.x
> key by `v6_key`, `previous_keys`, title or `--map`, refuses rather than guesses, never writes a
> plan (it names `tickets.py mark`), and renames the source `.legacy` only after verification.
> R5 is proved by `tests/l3io-doctor/test-engine.py` (27 tests, one fixture per layout plus a
> leftover-shim project). The 3.x path retired with it: `import-node`, `import-actual`,
> `estimate-story`/`estimate-rollup` (`estimate-entries` is their v7 address), `calibration
> redrive`, the 3.x addressing on the four kept verbs and the `nodes/` resolver (pm_status is 18
> verbs); the doctor's `migrate-state` and `redrive` and health Checks 2, 6, 7 and the 3.x half of
> 16 (new Check 20 points at `bmad migrate`). `install.sh` and the doctor's install mode are v7's
> `npx skills add` → `bmad setup` → `/l3io-doctor wire`. Not re-pinned: built at `e435a22`.

1. Build the entry point ADR g chooses. If it's native: `migration-1.toml` with `module = "l3io-pm"`, `from = "3"`, `to = "4"`, a `detect` that requires the v7 initiative layout to already exist (Review Focus 3), a `guide` that invokes `migrate-engine.py`, and a `checklist` that verifies every moved datum.
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
- **Release with what's ready.** If GA lands before 4.0.0 is ready, 3.x still does not run on v7: it refuses, and `docs/upgrading.md` tells users to stay on BMad 6.x until l3io 4.0.0 ships.
