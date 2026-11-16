# v7 Phase 2 — Packaging and wire-in: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the four modules installable on BMad v7 with `npx skills add` + `bmad setup`, retire the v6 packaging, and build the one reversible wire-in mechanism every later phase uses.

**Architecture:** The repository is re-laid as one folder per module (ADR-0021). Each module has a v7 `bmod.toml` record (ADR-0014). Skills v7 replaces are retired through `retired.toml`. `l3io-doctor` gains `wire`/`unwire`, which edit a team's `_bmad/custom/<skill>.toml` round-trip-safely and never overwrite a team's value (ADR-0020). Phase 2 changes **packaging only**: what each skill does at runtime is Phases 3–5. Between phases this branch is not releasable; it becomes releasable at Phase 7.

**Tech Stack:** Node (sync and check tooling), Python 3.11 PEP-723 scripts run through `uv`, `tomlkit` for round-trip TOML, BMad v7 at `e435a22` (`tests/fixtures/v7/make-fixture.sh`).

**Spec:** `docs/superpowers/specs/2026-10-16-bmad-v7-layer-design.md` (§9, §13.3, §13.5, §14.1–§14.3), plus ADRs 0013–0021. Parent plan: `docs/superpowers/plans/2026-11-15-bmad-v7-readiness.md`, Phase 2.

## Global Constraints

- Branch `feat/bmad-v7-layer` only. Nothing here lands on `main`; 3.x stays BMad-6.x-only.
- Upstream pin: `e435a22574fe55722841086e5566420178b98df3`. Re-pin, and append to spec §13, before starting if upstream has moved.
- `update_source` for module `<code>`: `github:LiquidLogicLabs/bmad-extensions/skills/<code>`.
- One version for every record in the repo, written from `package.json` by `sync-bmad-versions.mjs`. Never hand-edited.
- `required_skills` always includes `{ skill = "bmad", version = "6.13.0", source = "github:bmad-code-org/BMAD-METHOD/skills/core-tools" }`. That is the preview's version, measured in §13.5.
- A config question has only `key`, `prompt`, `default` and optional `scope`. Defaults keep `{project-root}` literal.
- Never bundle a BMad core script, `validate_manifests.py` included. Fetch it at the pin.
- No reference to the downstream adopter's organization in any file or commit message.
- Conventional Commits with DCO sign-off (`git commit -s`).

## Review Focus

1. **A team already set a single-value hook** (`tickets_after`, `on_complete`) in `_bmad/custom/<skill>.toml`. Expected: `wire` refuses that entry, names the file, key and both values, writes nothing for it, and exits non-zero. → Task 2.4.
2. **The team's file has comments, odd key order or a hand-added entry next to ours.** Expected: `wire` then `unwire` leaves it byte-identical; `unwire` never removes an entry it did not write. → Task 2.4.
3. **A user installs only `l3io-pm`.** Expected: `bmad setup` reports `l3io-util` (which provides `l3io-doctor`) as an unmet requirement with an install command. → Task 2.3.
4. **A 3.x project's `_bmad/custom/config.toml` already holds `modules.l3io-pm.lane_count`.** Expected: v7's three-layer merge still resolves it, and `bmad setup l3io-pm` does not ask again. → Task 2.3, verified on the fixture.
5. **A stale per-skill copy survives the move** (a file under an old `skills/<skill>/` path). Expected: `check:scripts` and `check:manifest` fail on it rather than pass over an empty scope. → Task 2.1.

---

## Target layout (ADR-0021)

```
skills/
  _shared/                         canonical sources (not a module; never installed)
  l3io-pm/
    bmod-l3io-pm/                  module record: bmod.toml, help/help.md, retired.toml
    l3io-execute/                  member skill, bmod.toml [skill]
    l3io-plan/                     member skill, bmod.toml [skill]
  l3io-util/l3io-doctor/           single-skill module: [bmod] + [skill], help/help.md
  l3io-arch/l3io-arch-review/      single-skill module
  l3io-sec/l3io-sec-redteam/       single-skill module + roster.toml
```

Retired, and listed in `bmod-l3io-pm/retired.toml`:
- `renamed`: `l3io-pm-execute` → `l3io-execute`, `l3io-pm-plan` → `l3io-plan`;
- `removed`: `l3io-pm-help`, `l3io-pm-sync`, `l3io-help`, `l3io-sync`, `l3io-setup`.

---

### Task 2.1: Re-lay the repository

**Files:**
- Move: every `skills/<skill>/` into its module folder above, with `git mv` so history follows.
- Modify: `scripts/sync-shared-scripts.mjs` (sync-group destinations), `scripts/write-payload-manifest.mjs` (skill discovery), `scripts/check-docs.mjs` (every path-derived scope: checks 24, 29, 37, 38 and the rest that walk `skills/*/`), `scripts/check-scripts`-family callers, `package.json` scripts.
- Test: `scripts/tests/check-docs.test.mjs`, `scripts/tests/*` touched by the path change.

**Interfaces:**
- Produces `skillDirs(): string[]` in one shared module (e.g. `scripts/lib/skill-dirs.mjs`). It returns every directory under `skills/` that holds a `SKILL.md`, at any depth, excluding `skills/_shared/`. Every tool derives skill locations from it, never from `skills/*/`.

- [ ] **Step 1: Failing test** `skill-dirs.test.mjs`. On a fixture tree with `skills/a/x/SKILL.md`, `skills/b/SKILL.md`, `skills/_shared/s/SKILL.md` and `skills/a/group/` (no `SKILL.md`), `skillDirs()` returns exactly `["skills/a/x", "skills/b"]`.
- [ ] **Step 2:** Implement `skillDirs()` and switch every tool that globbed `skills/*/` to it. Measured scope on 2026-11-16: 51 `readdirSync`/`skills/*` sites across `scripts/*.mjs`. Tool by tool, `git grep -n "skills/\*"` and `readdirSync(.*skills` must reach zero outside it.
- [ ] **Step 3:** `git mv` the directories. Run `npm run sync:scripts` and regenerate the manifests.
- [ ] **Step 4: Review Focus 5.** Plant a stray `skills/l3io-execute/steps/x.md` at the old path. `check:scripts` or `check:manifest` must fail naming it. Remove the plant.
- [ ] **Step 5:** All static gates and both suites green, with only path changes in the diff.
- [ ] **Step 6: Commit.** `refactor(infra): lay skills out one folder per module (ADR-0021)`.

### Task 2.2: Retire what v7 replaces

**Files:**
- Delete: `l3io-help`, `l3io-sync`, `l3io-setup`, and the four `l3io-pm-*` forwarders.
- Move: the `pm_status` payload copy and the module-home files `l3io-setup` carried (`write-module-config.py`, `merge-config.py`, `merge-help-csv.py`, `module-setup.md`, `agent-instructions.md`). `pm_status` goes to `l3io-execute`; the 6.x module-setup machinery is deleted, not moved.
- Create: `skills/l3io-pm/bmod-l3io-pm/retired.toml` per the list above.
- Modify: sync groups, the dependency inventory, and every step or doc that names a removed skill (check 1 lists them).

- [ ] **Step 1: Failing test** `test_retired_names_never_shipped` in `scripts/tests/`. No `skillDirs()` entry's basename appears under `removed`, or as an old name under `renamed`, in any `retired.toml`.
- [ ] **Step 2:** Delete and move as above. Self-install now reads `l3io-execute`'s sibling copy; Phase 3 replaces self-install with declared scripts.
- [ ] **Step 3:** Fix every reference check 1 reports. A removed skill named in prose is allowed only where it maps old to new.
- [ ] **Step 4:** Gates and suites green. **Commit.** `feat(l3io-pm)!: retire skills v7 replaces (R8, R14)`.

### Task 2.3: Module records

**Files:**
- Create:
  - `skills/l3io-pm/bmod-l3io-pm/bmod.toml` (`[bmod]`) and `help/help.md`;
  - `bmod.toml` with `[skill]` in `l3io-execute` and `l3io-plan`;
  - `bmod.toml` with `[bmod]` + `[skill]`, plus `help/help.md`, in each single-skill module;
  - `skills/l3io-sec/l3io-sec-redteam/roster.toml`.
- Modify: `scripts/sync-bmad-versions.mjs` writes `version` into every `[bmod]` table.
- Delete: every `module.yaml`, `assets/module.yaml` and `module-help.csv`.

**Config questions** (from `scan_legacy_module.py` at the pin, plus the two it missed):

| Module | `key` | `default` | `scope` | Note |
|---|---|---|---|---|
| `l3io-pm` | `lane_count` | `"1"` | team | **Missed by the scanner** (`variables:` list). The regex `^[1-9][0-9]{0,2}$` has no v7 equivalent; the skill validates on read. |
| `l3io-pm` | `lane` | `""` | user | **Missed by the scanner.** Regex `^([1-9][0-9]{0,2})?$`, validated on read. |
| `l3io-arch` | `preferred_diagram_format` | as today | team | |
| `l3io-sec` | `research_cache_ttl_days` | as today | team | |

`required_skills`: every record carries `bmad` (Global Constraints). `l3io-pm` also carries `{ skill = "l3io-doctor", version = "<repo version>", source = "github:LiquidLogicLabs/bmad-extensions/skills/l3io-util" }`.

`roster.toml`: `code = "redteam"`, `skill = "l3io-sec-redteam"`, and `name`, `icon`, `title` and `description` (as `persona`) as in today's agent roster.

`help/help.md`: written from each module's `module-help.csv` rows, one entry per skill. Each entry says what the skill gives and when to recommend it; preceded-by/followed-by become what to offer next.

- [ ] **Step 1: Failing tests** in `scripts/tests/`:
  - `test_every_skill_has_bmod_toml` — every `skillDirs()` entry has one, with `[skill] bmod` naming its module's record;
  - `test_one_version_across_records` — every `[bmod] version` equals `package.json`'s.
- [ ] **Step 2:** Write the records. Run `node scripts/sync-bmad-versions.mjs`, which `postbump` also chains, to stamp versions.
- [ ] **Step 3: R2.** Fetch `validate_manifests.py` at the pin (Task 2.5's helper) and run it over the repo: clean.
- [ ] **Step 4: R1 on the fixture.**
  - Build a fixture.
  - `npx skills add <this repo path>/skills/<code>` for each module, then run setup.
  - Expected:
    - no `problems`;
    - `bmad setup l3io-pm` lists `lane_count`;
    - with only `l3io-pm` installed, `unmet_requirements` names `l3io-doctor` (**Review Focus 3**).
  - Write `modules.l3io-pm.lane_count = "3"` into the fixture's `_bmad/custom/config.toml` first. `resolve_config.py --key modules.l3io-pm.lane_count` must print `3`, and setup must not ask for it (**Review Focus 4**).
- [ ] **Step 5: Commit.** `feat(infra)!: package all four modules as v7 bmods (ADR-0014)`.

**Done 2026-11-16 (`970d1a3`).** Findings that change later work:
- **RF4 holds only for resolution.** `resolve_config` returns the `_bmad/custom/config.toml` value, but
  `setup.py`'s `find_pending_questions` (pin, `setup.py:2107-2126`) treats a team question as
  answered only when it is in `_bmad/config.toml`. Setup therefore asks again, writes the answer
  there, and the custom value then silently overrides it. **Ruling:** the 3.x→4.x migration
  (`migration-<n>.toml`, ADR-0019) copies each `modules.l3io-*` answer from `custom/config.toml`
  into `_bmad/config.toml` and leaves the custom value in place, so the two cannot disagree.
  Raised in the upstream proposal as well.
- **`validate_manifests.py` treats `skills/_shared/` as a skill** and reports a missing
  `bmod.toml`. Over a view without `_shared` it passes (5 skills, 4 records). Task 2.5's
  `check:bmod` validates that view. Moving the shared sources out of `skills/` is the
  alternative and would amend ADR-0021.
- `research_cache_ttl_days` is **user**-scoped, not team: the scanner reports `user_setting: true`.
  `roster.toml` omits `name`, because today's value is empty.
- Unverified offline, so check in Task 2.5's smoke: setup's update check reads `bmod.toml` from
  `main`, which has none while 3.x ships; and its install hint
  (`npx skills add LiquidLogicLabs/bmad-extensions --skill l3io-doctor`) has no `skills/<code>`
  path.
- Dead now, removed in 2.5 or Phase 3: the single-skill modules' 6.x setup files
  (`module-setup.md`, the merge scripts, `write-module-config.py`).

### Task 2.4: Wire-in and unwire, owned by `l3io-doctor`

**Files:**
- Create:
  - `skills/l3io-util/l3io-doctor/scripts/wire-in.py` (PEP-723, `tomlkit`);
  - `skills/l3io-util/l3io-doctor/steps/wire.md` and `steps/unwire.md`, each with a routing-table row;
  - `skills/l3io-util/l3io-doctor/assets/wire-in.toml`, the declarative list of entries. It starts with one **test-only** entry; Phases 4–5 add the real ones.
- Test: `tests/l3io-doctor/test-wire-in.py`.

**Interfaces:**
- `wire-in.py wire --project-root R [--entries PATH] [--format text|json]`
  - exit 0: applied or already applied;
  - exit 3: one or more refusals, with nothing written for the refused entries;
  - exit 2: usage or a parse error.
- `wire-in.py unwire --project-root R` — removes exactly what the ledger records. Exit 0.
- Ledger: `{output_folder}/l3io/wire-in.json`. It records, per file, the keys and keyed-array entries (`code`/`id`) we added, with the bytes each replaced: none, since we never replace.
- Entry kinds, from `assets/wire-in.toml`:
  - `keyed` — append to `[[workflow.lenses]]`-style arrays by `code`/`id`; skip if an entry with that key exists (team's wins);
  - `list` — append to `activation_steps_*` / `persistent_facts` without duplicates;
  - `scalar` — set a single-value hook only when absent or empty, otherwise refuse.

- [ ] **Step 1: Failing tests:**
  - `test_wire_in_is_idempotent` — running twice gives a byte-identical second result and the ledger is unchanged.
  - `test_unwire_restores_bytes` — over a fixture holding comments, odd key order and a team entry, wire then unwire leaves every file byte-identical (**Review Focus 2**).
  - `test_wire_in_refuses_nonempty_string_hook` — exit 3, the message names file, key and both values, and the file is unchanged (**Review Focus 1**).
  - `test_wire_in_preserves_team_comments`.
  - `test_unwire_never_removes_a_team_entry` — a team-added lens with a different `code` survives unwire.
  - `test_keyed_entry_yields_to_team_entry_with_same_code`.
- [ ] **Step 2:** Implement. Mutation-check each test: each must be the one that fails under its own mutation, and each fixture must assert that what it planted really landed.
- [ ] **Step 3:** Run against the real fixture's `_bmad/custom/`: wire, unwire, then `git diff --exit-code` over a commit of the fixture taken before.
- [ ] **Step 4: Commit.** `feat(l3io-util): reversible wire-in for team customization files (ADR-0020)`.

**Done 2026-11-16 (`76249b7`).** Wire then unwire on the real fixture left every file byte-identical. **Ruling:** v7's resolver (`config_utils.py:55-74` at the pin) lets a team-file entry *replace* a shipped default when the two share a `code`/`id`, so `wire-in.py` refuses (exit 2) any keyed entry whose `code`/`id` does not start with `l3io-`. Open, for Phases 4–5:
- **A user can override our hook unseen.** A `<skill>.user.toml` that sets the same single-value hook overrides ours silently. `wire` should report it.
- **No lock.** Two concurrent `wire`/`unwire` runs can both write the ledger.
- **Deleted entries come back.** A team that deletes an entry we added gets it back on the next `wire`. Decide whether the ledger records the deletion as a refusal.
- **No check reaches the doctor's Menu column on v7.** `check:module` rule 9 skips v7 modules, so its menu rows are hand-mirrored in `help/help.md`. Task 2.5's check:docs rescope should cover that.

### Task 2.5: Tooling

**Files:** `scripts/check-module.mjs`, `scripts/check-bmb.mjs`, `scripts/smoke-install.sh`, `scripts/check-docs.mjs`, `package.json`, `.github/workflows/checks.yml`, `.claude-plugin/marketplace.json`.

- [x] **Step 1:** Add `scripts/fetch-bmad-tool.mjs <pin> <path>`, which fetches one file from BMAD-METHOD at the pin into a cache directory. Then add `check:bmod`, which runs `validate_manifests.py` over the repo through it, and add that step to `checks.yml` after `npm ci`.
- [x] **Step 2:** Retire `check:module`'s installer rules (PluginResolver strategies, agent roster parity, menu codes, two-location `module.yaml`). Delete `check:bmb` and the `bmad-builder` devDependency. Each removed rule's test goes with it; `check:bmod` replaces them.
- [x] **Step 3:** Rebuild `smoke:install`: `make-fixture.sh` at the pin, then `npx skills add` of each local module folder, then setup. It asserts R1's observable parts. Keep the trap rules: a failing run keeps its tree, and a caller's directory is never removed.
- [x] **Step 4:** Rescope `check:docs`:
  - CLI-surface checks stay;
  - checks asserting 6.x paths or skill names are retargeted or retired, each with a stated reason in the header;
  - the count of checks is updated wherever docs state it.
- [x] **Step 5:** Delete `.claude-plugin/marketplace.json` on this branch. v7 does not use it; it stays on `main` while 3.x ships.
- [x] **Step 6:** All gates green locally. Push nothing without the user's go-ahead. **Commit.** `build(infra): v7 tooling — validate_manifests gate, smoke on a real v7 install`.

**Done 2026-11-16 (`6f45881`).** Rulings and findings:
- **`fetch-bmad-tool.mjs`** records a SHA-256 per (pin, path) and refuses anything unrecorded
  before any network call. The validator needs **four** files, not one: it loads `setup.py` and
  `knowledge.py` from its own directory, and `knowledge.py` imports `list_templates.py`. The cache
  is outside the repository (`$BMAD_TOOL_CACHE` → `$XDG_CACHE_HOME/l3io-bmad-tools` →
  `~/.cache/l3io-bmad-tools`), so nothing fetched can be committed or linted.
- **`check:bmod`** validates a view without `_shared` (`l3io-check-bmod-*`, kept on failure):
  5 skills, 4 records, 4 knowledge documents. It is in CI after `npm ci` and needs network.
- **`check:module`** keeps two rules: `pm-status-singleton`, now by module folder, and
  `help-registration`, retargeted from `module-help.csv` to `help/help.md` — this is what now
  reaches the doctor's Menu column. Its first run found `l3io-plan`'s `plan` keyword marked
  `registered` with no help entry by that name; it is the bare invocation, so its Menu value is
  now `default`. The `roster.toml` ↔ `customize.toml [agent]` parity rule retired with the rest,
  as this task's list says; nothing compares the two copies of the agent's title and icon now.
- **`check:docs` is 35 checks.** Retired, numbers not reused, each with its reason in the header:
  23 (marketplace.json), 35 (forwarders; v7 uses `retired.toml`), 38 (`skill-manifest.csv`,
  which v7 does not write). Kept: 29 (guards the `.claude/commands` probes the step files still
  carry; vacuous after Phase 3) and 37 (`.agents/skills` is v7's first root). Retargeted: 19 and
  check 4's module arm derive modules from the module folder; 16 no longer reads `module.yaml`,
  and `bmad-extensions` (the repository slug in install commands) is declared `not-a-skill`.
- **Deleted:** `check-bmb.mjs`, `check-module-view.mjs`, `module-config-keys.mjs`,
  `forwarder-shape.mjs`, their tests, the `bmad-builder` devDependency, `marketplace.json` and its
  postbump/version-sync handling, and `merge-config.py`/`merge-help-csv.py` with their two suites
  (nothing at runtime called either). **Left for Phase 3**, because runtime still loads them:
  `module-setup.md` (doctor `SKILL.md` routing row `setup`/`configure` and line 167,
  `l3io-arch-review/SKILL.md:38`, doctor `steps/install.md:51`, `steps/health-check.md:438`),
  `write-module-config.py` (called by `module-setup.md`) and `agent-instructions.md` (same).
- **`smoke:install`** passes in ~30 s: fixture at the pin, four module folders, setup headless.
  Not in CI (GitHub and npm). Measured: the install hint resolves `--skill l3io-doctor` from the
  repository root, so following it against this checkout satisfies the requirement — but against
  GitHub it installs `main`'s **3.x** `l3io-doctor`, which has no `bmod.toml`, so a 4.x user
  following it today gets a skill v7 cannot register. Setup's update check (`--source-record`)
  reports `could-not-check` (404) for all four records while `main` ships 3.x; it does not fail
  setup. Both resolve when 4.x reaches `main` (Phase 7).
- Still stale for Phase 7's docs pass: `docs/getting-started.md` and `README.md` install
  instructions name `.claude-plugin/marketplace.json` and the 6.x installer.

---

## Exit

R1 and R2 on the fixture at the pin, every gate green, Review Focus 1–5 each covered by a test that fails without its fix. Then Phase 3: config reads, declared scripts and the end of self-install.

## Cannot be converted (from Toolsmith's migrate mode, recorded)

- **Input validation** (`lane_count` and `lane` regexes): v7 questions have no `regex`. The skill validates on read and halts with the allowed range.
- **Headless setup**: `bmad setup` has none. CI and smoke use `setup.py` directly, as the fixture does.
- **Existing answers in `_bmad/config.yaml`** are not carried by v7. Ours live in `_bmad/custom/config.toml`, which v7's three-layer merge still reads (Review Focus 4 verifies it).
- **Post-install notes and directory creation**: none in v7. Folded into `post_install_message` ("run `/l3io-doctor wire`") and into the skills' own first-run handling.
