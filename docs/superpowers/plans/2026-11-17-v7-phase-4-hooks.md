# v7 Phase 4 — Hooks into v7's planning and build: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach every l3io capability to the v7 skill a user already runs: estimation, readiness, waves and lanes on Sofia; measurement on `bmad-build` and `bmad-build-auto`; closure roll-up on `bmad-retrospective`. Then cut `l3io-execute` down to the one thing v7 lacks, the unattended multi-ticket run, and retire everything v7 already does. `pm_status` narrows to spec §4.5 as its last callers go.

**Architecture:** v7 owns the work-item tree (ADR-0015). We write only sidecars: `l3io.toml` beside each container's `tickets.toml`, `<plan-stem>.l3io.toml` beside each ticket's plan, and project-wide files under `{output_folder}/l3io/`. Every hook value is prose rendered into a v7 workflow. It reaches our code **only** through a script v7 installs for us under `{project-root}/_bmad/l3io-pm/scripts/`, because `{skill-root}` in a hook binds to the *host's* root (`render_skill.py:359-368`). `l3io-doctor wire` writes every hook (ADR-0020). Nothing in this phase edits a v7 file. `l3io-execute` becomes a dispatch planner over `tickets.py next` and `status`. It runs `bmad-build-auto` per ticket with `thorough` review, one git worktree per epic, and closes each epic with `bmad-retrospective -H`. It has no review, fix-loop or story-prep phase of its own (ADR-0017).

**Tech Stack:** Python 3.11 PEP-723 scripts under `uv` (`ruamel.yaml`, plus `tomlkit` for sidecars, already used by `wire-in.py`); Node check tooling; BMad v7 at `e435a22` (`tests/fixtures/v7/make-fixture.sh`, `npm run smoke:install`).

**Spec:** `docs/superpowers/specs/2026-10-16-bmad-v7-layer-design.md` §2, §3.1–§3.3, §4.1, §4.4, §4.5, §13.3, §14. ADRs 0013, 0015, 0016, 0017, 0020. Parent: `docs/superpowers/plans/2026-11-15-bmad-v7-readiness.md`, Phase 4, and the Phase 3 ruling that moved the §4.5 narrowing here (`docs/superpowers/plans/2026-11-16-v7-phase-3-config-runtime.md`).

**Re-pin, 2026-11-17:** upstream `main` is still `e435a22574fe55722841086e5566420178b98df3`, with 0 commits since the pin. §13 gets no new entry. Every file:line below was read at that commit in `.upstream-bmad`.

## Extension points, measured at `e435a22`

Paths are relative to `skills/method/` unless they start with `core-tools/`.

| Host | Key (team file `_bmad/custom/<skill>.toml`) | Kind | Declared at | Rendered / run at |
|---|---|---|---|---|
| `bmad-agent-po` (Sofia) | `agent.menu` (`code`, `description`, `prompt` \| `skill`) | keyed by `code` | `bmad-agent-po/customize.toml:35-70` | `workflow.md:39-41`: runs its `prompt` or `skill`. A missing skill is offered from **Sofia's** `bmod.toml` `source` |
| Sofia | `agent.persistent_facts` (**`[agent]`, not `[workflow]`**) | list | `customize.toml:20-21` | `workflow.md:25` |
| Sofia | `workflow.tickets_after` | string, one slot | `customize.toml:83` | `references/slice.md:112`, after an approved slice, story plan or re-slice |
| Sofia | `workflow.refine_after` | string, one slot | `customize.toml:87` | `references/ticket.md:49`, after the approved ticket is saved |
| Sofia | `workflow.board_after` | string, one slot | `customize.toml:91` | `references/board.md:76`, after any board operation, including `tickets.py move` (`:61`) |
| Sofia | `workflow.validate_after` | string, one slot | `customize.toml:95` | `references/validate.md:18` |
| Sofia | `workflow.checks.{ticket,set,tree,dependencies,closure}` | **list** | `customize.toml:118-122` | `references/validate-checks.md:30-85`, inside the section each check subagent runs |
| Sofia | `workflow.replan_after` | string, one slot | `customize.toml:99` | `references/replan.md:15` |
| `bmad-build` | `workflow.activation_steps_prepend` | list | `bmad-build/customize.toml:17` | `workflow.md:43`, before config and greeting |
| `bmad-build` | `workflow.on_complete` | string, one slot | `customize.toml:49` | `step-05-present.md:41`, `step-oneshot.md:132`: **success path only**, after the local commit (`step-05:19`) |
| `bmad-build` | `workflow.review` / `thorough_lenses` | string / keyed by `id` | `customize.toml:97`, `:121` | `step-04-review.md` |
| `bmad-build-auto` | `workflow.activation_steps_prepend` | list | `bmad-build-auto/customize.toml:17` | `workflow.md:84` |
| `bmad-build-auto` | `workflow.on_complete` | string, one slot | `customize.toml:49` | `workflow.md:46-52`: HALT step 3, so **every** terminal status, `blocked` included |
| `bmad-build-auto` | `workflow.review` | string | `customize.toml:68` (default `quick`) | `SKILL.md:16`: an invocation naming `thorough` appends `--set workflow.review=thorough` |
| `bmad-build-auto` | (no `interactive` key) | — | absent from `customize.toml` | non-interactive by construction (`SKILL.md:3`, `step-04-review.md` RULES) |
| `bmad-code-review` | `workflow.fixes`, `workflow.interactive` | string | `bmad-code-review/customize.toml:49-53` | `bmad-code-review` only; `bmad-build-auto`'s own step 4 triages and patches |
| `bmad-retrospective` | `workflow.on_complete` | string, one slot | `bmad-retrospective/customize.toml:39` | `references/retro-document.md:41-45`, after the document is saved |
| `bmad-retrospective` | `-H <epic>` headless | invocation | `workflow.md:15-17` | its verdict is in the document's frontmatter only (`retro-document.md:9-21`) |

Rules the hooks live under:

- **A team file may set only declared keys.** `_check_persistent_layers` halts the render of the *whole skill* on any undeclared leaf (`core-tools/bmad/scripts/render_skill.py:122-128`). Values are type-checked against the shipped default (`:301-317`). A keyed table's fields must all be strings (`:186-202`).
- **Merge:** strings replace, lists append, and arrays of tables merge by `code` and then `id` (`core-tools/bmad/scripts/config_utils.py:15`, `:55-86`).
- **`{skill-root}`** in a value is bound to the **host's** generation directory (`render_skill.py:359-368`). `{project-root}` is left for the agent, as v7's own prose does.

`tickets.py` (`bmad-agent-po/scripts/tickets.py`, 1,891 lines), as Phase 4 relies on it:

| Fact | Where |
|---|---|
| Statuses `draft … built, done, blocked, dropped`; `built` maps to state `review` | `:56`, `:59-69` |
| A ticket in `review` meets an entry's `after`, but an **epic** gate (`gated_by`) waits for the epic container to be `done` | `classify`, `:581-606` (comment `:584`) |
| Store = `_bmad/custom/ticketing-store-config.toml` `[tickets] store`, absent → `repo` | `store_config`/`store_name`, `:780-793` |
| `next` refuses a non-`repo` store without `--synced` | `:998-1009` (refusal `:1002`) |
| `find` returns `plan`, `folder`, `epic_file`, `story_file` | `:1157-1179`; plan path `:1149-1154` |
| `mark` writes only the plan and refuses a non-`repo` store | `:1283-1324` (refusal `:1288`) |
| `mirror` writes tracker fields into leaf files, never `status`, and refuses `repo` | `:1379-1385` |
| `move` renumbers the entry and moves **only** its leaf file and plan | `:1509`, `:1633-1652` |
| Folder scan reads only `*.md` and `epic-*` directories | `:322`, `:406` |
| Exit codes: 0 ok, 1 `TicketError`, **2 `StoreRefusal`** | `:1878-1884` |
| No `flock`, `fcntl` or `os.replace` anywhere | `grep -c` = 0 |
| Layout: `<initiative>/tickets/tickets.toml`, `<initiative>/tickets/epic-<slug>/tickets/{tickets.toml, <leaf>.md, <stem>-plan.md}` | `tickets_dir`, `:180-192` |

`bmad-build-auto`'s working-tree contract: step 1 requires a **clean** tree and a branch that fits the epic, and HALTs `blocked` otherwise (`step-01-clarify-and-route.md:60`). Finalization commits and then verifies the tree is clean (`step-04-review.md:171-174`). The terminal status is `built` (`:167`). An orchestrator may set `done` through `mark` (`bmad-agent-po/references/board.md:50`), and **only an unattended run's orchestrator honors `plan_checkpoint` and `done_checkpoint`** (`board.md:44`). v7's own guidance for parallel writers is separate folders or worktrees (`docs/toolsmith/subagent-patterns.md:52`).

## Rulings on the parent plan

- **Readiness attaches to `workflow.checks.ticket` and `workflow.checks.set`, not `validate_after`.** Why: both are lists that append (`customize.toml:118-119`), and they render inside the very check sections Sofia's subagents run (`validate-checks.md:30-47`). `validate_after` is a single slot that a team's own hook would make us refuse. ADR-0020 prefers a list wherever one reaches the same point. Cost if wrong: our findings arrive as check findings, which Sofia sorts as fix, suggest or ask (`validate.md:15`). A `validate_after` value would have needed the same sorting.
- **Menu codes are `l3io-estimate`, `l3io-waves`, `l3io-lanes`, not `ESTIMATE`/`WAVES`/`LANES`.** Why: wire-in refuses a keyed identity without the `l3io-` prefix (`wire-in.py:69`, `:196`). From the team layer, an identity equal to a BMad item's would **replace** that item (`config_utils.py:66-71`). Cost if wrong: cosmetic.
- **Menu items use `prompt`, never `skill`.** Why: for a missing `skill`, Sofia offers an install from **her own** `bmod.toml` `source` (`workflow.md:41`), which names BMAD-METHOD. The prompt names the `l3io-plan` skill and its mode. Cost if wrong: none.
- **Every hook calls a declared script. This overturns Phase 3's "declare `pm_status` only".** `spec-align.py`, `plan-graph.py` and a facts file `facts/ac-dimensions.md` join the declared set. Why: a hook's `{skill-root}` is Sofia's or `bmad-build`'s (`render_skill.py:359-368`). Our skill root varies by tool (`.agents/skills` or `.claude/skills`). The only stable path a static hook string can name is `{project-root}/_bmad/l3io-pm/scripts/…`. `read_declared_script` accepts any file under the skill (`setup.py:1695-1708`), so a `.md` fact declares the same way. Cost if wrong: three more installed files per module.
- **No `interactive = false`; `fixes = "apply"` is not ours to set.** `bmad-build-auto` declares no `interactive` key, so a wire-in write would halt every render (`render_skill.py:122-128`). It is non-interactive by construction. `fixes` belongs to `bmad-code-review`, and the build loop triages and patches in its own step 4. `l3io-execute` names `thorough` in the invocation, which `SKILL.md:16` turns into `--set workflow.review=thorough`. Neither the route nor anything else is pinned. Cost if wrong: none; the parent's intent is met.
- **The dispatch bracket opens into a gitignored spool, and the close commits what it wrote.** `build-open` writes `{state_root}/.inflight/<id>.json`, ignored through the `_ensure_lock_ignore` mechanism. `build-close` writes the events pair, the sidecar actuals and the calibration sample. It then commits each path it wrote that lies inside the current worktree (`git rev-parse --show-toplevel`). Why: a tracked write in the prepend fails `bmad-build-auto`'s clean-tree check (`step-01:60`). A write after finalization that is left uncommitted fails the *next* build's check. Cost if wrong: one `chore(l3io): actuals <ticket>` commit per build.
- **Parallel epics run in one git worktree per epic, on branch `l3io/<epic-slug>`.** Project-wide state resolves to the main checkout through `git rev-parse --git-common-dir`. Why: two `bmad-build-auto` runs in one tree each see the other's edits and HALT `dirty tree` (`step-01:60`), or commit them (`step-04:173`). v7's own guidance is worktrees (`subagent-patterns.md:52`). `step-01:60` judges the branch against the **epic**, and a branch per epic satisfies it. `flock` is valid again because every worktree shares the main checkout's filesystem path. Cost if wrong: Task 4.7 Step 1 has not yet measured whether a worktree carries a runnable `_bmad/`. If it does not, parallel epics fall back to `max_parallel_subagents = 1` and the finding is recorded (see Infeasible points).
- **An unattended run pauses at every epic gate.** A dependent epic waits for its predecessor's container status `done` (`tickets.py:584-590`). That status is Sofia's to set **on the user's confirmation** (`board.md:55`). `l3io-execute` runs independent epics unattended. At a boundary that gates a later epic, it presents the retrospective verdict and asks the user. Cost if wrong: an unattended run is unattended per wave of independent epics, not across the whole initiative.
- **`done` is written at epic closure, after an accepted retrospective verdict.** `built` already satisfies an entry's `after` (`:584`), so waves inside an epic never wait for `done`. Sofia's principle (`customize.toml:31`) makes `done` a check the owner runs. On `repo` it is written with `mark <ref> done`. On a tracker it goes through the store's `write`, then `mirror`. A `rejected` verdict leaves tickets at `built` and halts. Cost if wrong: tickets read `built` until closure.
- **The store name is read from the TOML file, and tracker traffic goes through Sofia's own procedure.** `dispatch-plan.py` reads `_bmad/custom/ticketing-store-config.toml` exactly as `store_name()` does (`:780-793`), and a test pins that rule. The tracker `query`/`write` verbs need the starter-merged config. That comes from Sofia's `read_store.py`, which is not a declared script (`bmad-agent-po/bmod.toml` declares only `tickets.py`). So `l3io-execute` locates her skill root by probing `.agents/skills` then `.claude/skills` (checks 29/37) and follows `board.md`'s "Tracker sync" section verbatim. Cost if wrong: if v7 moves the store file, one constant and its test change.
- **The sidecar path assembly lives in `pm_status/nodes/`.** Check 26 requires exactly one file to carry the resolver markers. Cost if wrong: none. `nodes/` shrinks when the placement model goes in Task 4.8.
- **A calibration sample needs an estimate recorded before the build.** R13 as written ("a calibration sample recorded") is narrowed. An unestimated ticket gets its bracket and actuals and **no** sample, and `build-close` says so on stderr. Why: an estimate made by the builder after the fact is not a prediction, and sampling it would poison the ratios. Cost if wrong: unestimated tickets do not calibrate. That is the case today.
- **`bmad-build`'s `on_complete` runs only on success** (`step-05:41`, `step-oneshot:132`). An abandoned interactive build leaves an open bracket. `report --stall-minutes` flags it, and the next `build-open` for the same plan closes it as `abandoned`. `bmad-build-auto` runs `on_complete` on every HALT, so it never dangles. Cost if wrong: an abandoned interactive build records no actuals.
- **`tickets.py move` does not carry our sidecars.** It moves only the leaf and the plan, and renumbers the entry (`:1633-1652`). `replan_after` and `board_after` therefore run `sidecar-reconcile`, and the doctor's tree audit reports orphans. Estimates are keyed by entry id in `l3io.toml`; `next_id` never decreases, so an old key is never reused. Actuals are keyed by the plan's stem, which `move` keeps. Cost if wrong: an estimate is orphaned until the audit runs.
- **`import-node` and `import-actual` survive Phase 4.** §4.5 deletes `import-node`. Its last caller is `migrate-engine.py`'s writer, which Phase 6 replaces. The same principle as the Phase 3 ruling applies: a verb goes with its last caller. The doctor's `migrate-state` mode stays with them. Cost if wrong: two verbs live one phase longer.
- **The epic architecture gate and the epic-closure spec sync leave `l3io-execute` in Task 4.7.** Phase 5 re-homes the gate on `bmad-architecture`'s `finalize_reviewers` (parent Phase 5 item 2). The spec sync is recorded as open for Phase 5, beside `bmad-retrospective`'s decision records (`retro-document.md:30`). Why: `test_execute_has_no_review_phase` forbids a review step of ours, and the gate is one. Cost if wrong: on this unreleased branch, between 4.7 and Phase 5, no epic design gate runs and accepted departures are not written back.
- **`plan_checkpoint` and `done_checkpoint` are honored by `l3io-execute`.** This is an addition to the parent: `board.md:44` makes it the orchestrator's job, and nothing else honors them. `plan_checkpoint` runs `bmad-build-auto` with `Halt after planning.` (`step-02-plan.md:37`) and asks the user. `done_checkpoint` asks after `built`. Cost if wrong: an author's checkpoints are silently skipped.
- **The sprint level leaves the estimate and calibration code together with its last callers** (ADR-0016): sprint closure in Task 4.7, sprint planning in Task 4.8. Epic closure and orchestration bands remain.

## Global Constraints

- Branch `feat/bmad-v7-layer` only. No push, no tag, no release.
- Upstream pin: `e435a22574fe55722841086e5566420178b98df3`. Cite upstream by file:line at that pin.
- **Never edit a v7 file.** Every hook is a `[[entry]]` in `skills/l3io-util/l3io-doctor/assets/wire-in.toml`, applied by `/l3io-doctor wire`. Each entry carries `requires = "l3io-pm"`, and wire skips it (status `skipped`) when `_bmad/l3io-pm/scripts/pm_status/__main__.py` is absent.
- **Never write `tickets.toml`, a leaf file, a container file, or a plan file**, except a plan through `tickets.py mark` on `repo` (ADR-0015). No hook or script of ours ever calls `mark` on a tracker store.
- Hook values call only `uv run {project-root}/_bmad/l3io-pm/scripts/…`, never `{skill-root}`.
- Edit `skills/_shared/` first, then `npm run sync:scripts`, then `node scripts/write-payload-manifest.mjs`.
- `pm_status` cap: 1,500 lines per `.py`. `verbs/__init__.py` is at 1,400, so new verbs go in a new module (`sidecar/`, `build/`). Split a module rather than raise the cap.
- `check:docs` check numbers are never reused. The next free number is **40**.
- New Python suites go in `tests/<skill>/test-*.py`, or `skills/_shared/tests/test-*.py` for shared code. `test:python` discovers both.
- **The gate run**, in each task's verification: `npm ci`, then `check:lock`, `check:audit`, `check:scripts`, `check:docs`, `check:version`, `check:manifest`, `check:module`, `check:bmod` (network), `check:lint:py`, `check:types`, `check:lint:sh`, `test:python`, and `test:scripts` backgrounded with its output in `/tmp/l3io-p4-<task>.log`. Enumerated from `.github/workflows/checks.yml`, never from memory.
- ADR numbers come from `pm-status.py adr-reserve` only.
- No reference to the downstream adopter's organization in any file or commit message.
- Conventional Commits with DCO sign-off (`git commit -s`), ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A wire-in entry sets a key the v7 skill does not declare, or sets it with the wrong type,** so `render_skill.py` halts every invocation of Sofia or `bmad-build` (`render_skill.py:122-128`, `:301-317`). Our wire-in would have broken the user's planner. Expected: `check:bmod` checks every entry against the pinned `customize.toml`, and `smoke:install` renders each host after `wire`. → Task 4.2.
2. **Our hook leaves the tree dirty,** so the next `bmad-build-auto` HALTs `blocked` with "dirty tree" (`step-01:60`) or "finalization left repository dirty" (`step-04:174`). Expected: after open then close, `git status --porcelain` is empty. → Task 4.2, `test_bmad_build_alone_records_actuals`.
3. **`tickets.py move` renumbers an entry under REPLAN or BOARD,** so its estimate stays keyed to the old id, or a different ticket takes it. Calibration is then poisoned silently. Expected: `replan_after`/`board_after` run `sidecar-reconcile`, and the old key is never reused, because `next_id` only grows. → Task 4.3.
4. **A tracker-backed project hits `StoreRefusal` mid-epic** because something called `mark`, or because `next` ran unsynced (`:1288`, `:1002`). Expected: the store is resolved once, `mirror` runs before `next --synced`, and on a tracker no plan we emit and no hook value contains `mark`. → Task 4.7, `test_tracker_store_never_calls_mark`.
5. **Parallel epics lose a write.** Our sidecars, the events log and the calibration file interleave with `bmad-build-auto`'s plan-file writes, and `tickets.py` takes no lock. Expected: with N concurrent closes across worktrees, there are N sidecars, N bracket pairs, N samples, and every plan file intact. → Task 4.7, `test_parallel_epics_sidecars_survive`.

---

### Task 4.1: Sidecars and the project-wide state root (item 1)

**Done 2026-11-17** (`282471b3`). New module `pm_status/sidecar/` (`__init__.py` load/save/lock, `verbs.py` the v7 handlers and `route`, `reconcile.py` `sidecar-reconcile`); resolvers in `nodes/`; `skills/_shared/tests/test-pm-status-sidecar.py` (17 tests); `smoke:install` asserts byte-identical `tickets.py status` around our writes. CLI is 43 subcommands.

- Ruling: sidecar writes lock the sidecar's **directory** (`flock` on a directory fd), not a lock file — why: a lock file beside a sidecar is an untracked file in the user's tree, which is exactly what fails `bmad-build-auto`'s clean-tree check (`step-01:60`) — cost if wrong: every writer in one tickets folder serialises (they are short), and a non-flock filesystem loses the guard as everywhere else in the package.
- Ruling: `set-actual --plan-file` records **no** calibration sample and says so on stdout — why: the plan → entry → estimate pairing is `build-close`'s (Task 4.2, step 5); sampling here would duplicate it or sample unestimated tickets — cost if wrong: a caller that uses `set-actual` alone on v7 gets no sample until 4.2 lands.
- Ruling: v7 handlers are chosen after parsing by `sidecar.verbs.route` (called from `main`), and `--state-root` (plus `add-test-run --story`) is no longer argparse-required; `route` enforces it with exit 2 — why: argparse cannot make one flag required only when another is absent, and the 3.x handlers stay untouched — cost if wrong: a caller invoking a handler without `main` skips the check.
- Ruling: `verify --plan-file` judges the ticket sidecar as a story node is judged **except status**, which is the plan's and v7's to write — cost if wrong: none; status is read from `tickets.py` where needed.
- Ruling: a hand-set override is `l3io_<metric>` per metric and `l3io_class`; a bare `estimate` is carried verbatim as `hand_estimate` (its unit is the user's) — exposed through `sidecar.effective_estimate`; `set-estimate` still writes our sidecar and notes the override on stderr — cost if wrong: Task 4.3 may want `set-estimate` to refuse instead.
- Ruling: `project_state_root` runs core's `resolve_config.py` through `uv run` when `uv` is on PATH, else the current interpreter, and retries in the main checkout when the worktree's own `_bmad/` cannot resolve — cost if wrong: one subprocess per CLI call (~0.1 s).
- `--moved-json` takes the JSON itself, a file, or `-`; `from`/`to` are folder names, located under the initiative's `tickets/`, then beside it.

**Files:**
- Create: `skills/_shared/pm_status/sidecar/__init__.py` (load/save of `l3io.toml` and ticket sidecars through `tomlkit`, under `flock`; no path assembly).
- Modify: `skills/_shared/pm_status/nodes/__init__.py`. Inside the check-26 marker section, add the only functions that turn a v7 address into a path: `entry_sidecar(ticket_dir)`, `ticket_sidecar(plan_file)`, `container_sidecar(initiative_dir)`, `project_state_root(project_root)`.
- Modify: `skills/_shared/pm_status/__main__.py` (PEP-723 adds `tomlkit>=0.13`); `metrics/__init__.py` and `verbs/__init__.py`. `set-estimate`, `set-actual`, `add-test-run` and `verify` gain v7 addressing **beside** the node keys, so every existing caller still passes.
- Modify: `skills/_shared/status-files.md` (a new §, "4.x sidecars", stating the layout below). `CLAUDE.md`'s state-file bullets gain a sidecar paragraph.
- Test: `skills/_shared/tests/test-pm-status-sidecar.py` (new).

**Interfaces:**
- Layout:
  - `<initiative>/tickets/l3io.toml`: `[epic.<slug>]` with `lane` (1–999).
  - `<initiative>/tickets/epic-<slug>/tickets/l3io.toml`: `[entry.<id>]` with `class` and `estimate` (the five metrics, canonical order), plus `[epic]` (`estimate`, `actual`, `orchestration`).
  - `<…>/tickets/<stem>-plan.l3io.toml` beside `<stem>-plan.md`: `actual`, `fix_iterations`, `completion_evidence.test_runs`, `dispatch`.
  - Project-wide `{state_root}` = `<main worktree>/<core.output_folder>/l3io/`: `events.jsonl`, `pm-calibration.yaml`, `adr-register.yaml`, `.notices.yaml`, `.inflight/`. The main worktree is `dirname(git rev-parse --path-format=absolute --git-common-dir)`, and `core.output_folder` is read with `uv run {project-root}/_bmad/scripts/resolve_config.py --project-root P --key core.output_folder`.
- New addressing flags, mutually exclusive with `--epic/--sprint/--story`:
  - `--ticket-dir DIR --entry ID` (estimates);
  - `--plan-file PATH` (actuals, test runs);
  - `--project-root P` in place of `--state-root`.
- `sidecar-reconcile --project-root P --initiative-dir D [--moved-json J]`. `J` is `tickets.py move`'s stdout. It repoints `[entry.<old_id>]` to `[entry.<id>]` in the destination's `l3io.toml`, moves `<plan-stem>.l3io.toml` beside the moved plan, and prints one line per action. With no `--moved-json`, it sweeps for orphans (a sidecar whose plan is absent but has a same-named plan elsewhere in the initiative). Exit 0, or 2 on usage.
- A hand-set `estimate` or `l3io_*` key on a `tickets.toml` entry is read as an override and never written (§3.2).

- [x] **Step 1: Failing tests.**
  - `test_tickets_toml_never_written`: snapshot the bytes of every `tickets.toml`, `*.md` leaf and `*-plan.md` in a fixture initiative. Run every verb with v7 addressing. Every byte is unchanged.
  - `test_sidecar_names_are_invisible_to_tickets_py`: no name we create matches `*.md` or `epic-*` (pins `tickets.py:322`, `:406`).
  - `test_state_root_resolves_to_main_worktree`: from a `git worktree add` checkout, the state root equals the main checkout's.
  - `test_sidecar_round_trip_keeps_comments`.
  - `test_concurrent_set_actual_distinct_plans`: 8 processes; every sidecar and every event survives.
  - `test_reconcile_follows_move`: built from a recorded `tickets.py move` JSON.
  - `test_hand_set_estimate_is_override`.
- [x] **Step 2:** Implement `nodes` resolvers, `sidecar/`, and the new flags. `--state-root` keeps working for the 3.x tree until Task 4.8.
- [x] **Step 3: On the fixture.** Hand-write a small initiative in the fixture project (one epic, three entries). Run `set-estimate`/`set-actual` with v7 addressing. Assert `uv run _bmad/method/scripts/tickets.py status <initiative>` prints byte-identical JSON before and after, with no `problems`. Add this to `scripts/smoke-install.sh`.
- [x] **Step 4:** Sync, regenerate manifests and the declared lists (`check:scripts` sees the new module), then run the gate run.
- [x] **Step 5: Commit.** `feat(l3io-pm): sidecars beside v7's tree; project state under {output_folder}/l3io`.

### Task 4.2: Measurement on every build (item 2, R13)

**Done 2026-11-17** (`fcce5c5a`). New module `pm_status/build/` (`build-open`, `build-close`); `requires` and the `skipped` status in `wire-in.py`; four entries in `assets/wire-in.toml`; `check:bmod`'s wire-in arm over six pinned host `customize.toml` files; `tests/l3io-pm/test-build-hooks.py` (6 tests); `smoke:install` renders both build skills after `wire` and checks `unwire` and the refusal. CLI is 45 subcommands.

- Ruling: the spool ignores itself (`.inflight/.gitignore` holding `*`, written by `_ensure_lock_ignore`), rather than a line in `{state_root}/.gitignore` — why: on a first build that `.gitignore` is itself an untracked file, so writing it at open dirties the tree `bmad-build-auto` checks at step 1 — cost if wrong: none; the state root's `.gitignore` still gets `*.lock` and is committed by the close.
- Ruling: `build-open` appends no event; the bracket's `dispatch_open` is written by the close with the open's timestamp, and an abandoned bracket's pair likewise at the next close — why: an event is a tracked write, and the open runs before the clean-tree check — cost if wrong: `report --stall-minutes` cannot see an in-flight build until Task 4.5's v7 report source reads `.inflight/`.
- Ruling: the bracket key is `--session-id`, else `CLAUDE_CODE_SESSION_ID`, else the agent plus a hash of the worktree — why: the prepend runs before any plan exists, so neither verb can be told the other's name — cost if wrong: two concurrent non-Claude builds by one agent in one worktree share a key, which the clean-tree rule already forbids.
- Ruling: `[actual]` is the sum of the plan sidecar's `dispatch` list, one record per closed bracket — why: `bmad-build-auto` runs On Complete on `blocked` too, so a blocked-then-resumed ticket has two brackets and its spend is both — cost if wrong: re-building a built ticket adds to its actual.
- Ruling: the calibration sample is taken once per ticket (`calibration_sampled_at`), only when the plan reads `built` or `done` and `[entry.<id>].estimate` exists — why: a blocked run's partial spend is not a size measurement, and an after-the-fact estimate is not a prediction — cost if wrong: a ticket that ends blocked never calibrates.
- Ruling: `fix_iterations` is the plan's `review_loop_iteration` — why: it is v7's own count of review loopbacks — cost if wrong: the fix cohort follows v7's meaning of the counter.
- Ruling: under `codex`/`copilot`/`other` the close records tokens `N/A`, though `set-actual` refuses `--tokens-na` for codex and copilot — why: the close cannot read those runtimes' usage, and guessing is forbidden — cost if wrong: those runtimes' tickets carry no tokens until a reader exists.
- Ruling: the hook commands carry slots `<runtime>`, `<man_hours>`, `<hitl_hours>`, `<verification command>`, `<exit code>` (bmad-build-auto's has `--hitl-hours 0` fixed); the R13 test fills them beside `{project-root}`/`{plan_file}` and fails on any unfilled slot — cost if wrong: none.
- Ruling: `.gitignore` gains `!skills/**/pm_status/build/`, keeping the plan's module name — why: the repository's Python template ignores every `build/` — cost if wrong: a consumer whose own `.gitignore` ignores `build/` and who commits `_bmad/` loses `pm_status/build/` from git, and a clone or worktree of theirs cannot import `pm_status`. Task 4.7 Step 1 should measure this alongside whether a worktree carries `_bmad/`.
- Ruling: a failed commit (a user's commit hook, say) exits 1 and says the tree is dirty; hooks are never skipped — cost if wrong: the next `bmad-build-auto` HALTs `dirty tree` with our message already on screen.
- Ruling: `requires` names a module from a fixed map (`l3io-pm` → `_bmad/l3io-pm/scripts/pm_status/__main__.py`); any other value is exit 2 — cost if wrong: one map entry per module that grows hooks.
- In a linked worktree the state root is the main checkout's, outside the worktree, so the close commits only the plan sidecar there; the main checkout's events and calibration stay uncommitted until Task 4.7 commits them at epic closure or merge.

**Files:**
- Create: `skills/_shared/pm_status/build/__init__.py`, holding the `build-open` and `build-close` verbs.
- Modify: `skills/l3io-util/l3io-doctor/scripts/wire-in.py` (the `requires` field and the `skipped` status) and `assets/wire-in.toml` (four entries).
- Modify: `scripts/check-bmod.mjs` and `scripts/fetch-bmad-tool.mjs`. Fetch the pinned `customize.toml` of `bmad-agent-po`, `bmad-build`, `bmad-build-auto`, `bmad-retrospective`, `bmad-review` and `bmad-code-review` with recorded SHA-256s. Assert that every non-`test_only` wire-in entry's `path` is declared there, and that its kind matches the default: `scalar`↔string, `list`↔string list, `keyed`↔array of tables.
- Modify: `scripts/smoke-install.sh`.
- Test: `tests/l3io-pm/test-build-hooks.py` (new), `tests/l3io-doctor/test-wire-in.py`, `scripts/tests/check-bmod*.test.mjs`.

**Interfaces — wire-in writes:**

| Team file | Key | Kind | Entry id |
|---|---|---|---|
| `_bmad/custom/bmad-build.toml` | `workflow.activation_steps_prepend` | list | `l3io-build-open` |
| `_bmad/custom/bmad-build.toml` | `workflow.on_complete` | scalar | `l3io-build-close` |
| `_bmad/custom/bmad-build-auto.toml` | `workflow.activation_steps_prepend` | list | `l3io-build-auto-open` |
| `_bmad/custom/bmad-build-auto.toml` | `workflow.on_complete` | scalar | `l3io-build-auto-close` |

- `build-open --project-root P --agent bmad-build|bmad-build-auto [--plan-file F]` writes `{state_root}/.inflight/<session>.json`. It writes no tracked file. A stale open for the same plan is closed as `abandoned`.
- `build-close --project-root P --agent A [--plan-file F] --runtime claude|codex|copilot|other [--model M] --man-hours H --hitl-hours H [--test-run 'CMD=EXIT' …]`:
  1. reads the open;
  2. runs `usage` over its window (Claude), or records `N/A` tokens;
  3. writes `set-actual` to the ticket sidecar, plus one `add-test-run` per `--test-run`;
  4. appends `dispatch_open`/`dispatch_close` to `events.jsonl`;
  5. appends a calibration sample **only if** `[entry.<id>].estimate` exists (otherwise warns);
  6. commits each written path inside `git rev-parse --show-toplevel`, as `chore(l3io): actuals <ticket>`.

  With no plan file it closes the bracket and records events only. Exit 0; 2 on usage; 4 if the open is missing (the bracket is recorded as unmatched).
- The hook values are short prose, each with one fenced command. The on_complete text tells the agent:
  - `hitl_hours` is 0 under `bmad-build-auto`;
  - `man_hours` is the counterfactual assessed from the diff (the HARD RULE);
  - pass every `## Verification` command it ran, with its exit code;
  - **never** call `mark`.

- [x] **Step 1: Failing tests.**
  - **`test_bmad_build_alone_records_actuals` (R13).** It reads the two `bmad-build` entries from `wire-in.toml`, extracts their commands, substitutes `{project-root}` and `{plan_file}`, and runs them against a git-initialised fixture project. The fixture holds a v7 epic, a plan file, an estimate in `l3io.toml`, and a synthetic Claude transcript. It asserts:
    - one `dispatch_open`/`dispatch_close` pair;
    - all five actual metrics in canonical order, with `cost` derived;
    - one calibration sample;
    - `git status --porcelain` empty afterwards (Review Focus 2).

    A second case, with no estimate, asserts actuals and no sample.
  - In `test-wire-in.py`: `test_requires_absent_module_skips`.
  - In the check-bmod test: a planted entry with path `workflow.interactive` on `bmad-build-auto` fails, naming the key (Review Focus 1).
- [x] **Step 2:** Implement `build/`, `requires`, the four entries and the check-bmod arm.
- [x] **Step 3: On the fixture** (`smoke:install`).
  - Run `/l3io-doctor wire`'s script, then `uv run _bmad/scripts/render_skill.py --project-root . --skill .claude/skills/bmad-build`, and the same for `bmad-build-auto`. Each exits 0 and its output contains the `l3io-build` command lines.
  - Unwire, then assert both team files are byte-identical to before (R15).
  - Plant a team `on_complete` and assert wire exits 3 and changes nothing.
- [x] **Step 4:** Doctor `steps/wire.md` lists the new entries. Sync, regenerate manifests, then run the gate run.
- [x] **Step 5: Commit.** `feat(l3io-pm): measure every bmad-build run through its own hooks (R13)`.

### Task 4.3: Estimation on Sofia (item 3)

**Done 2026-11-17** (`e8a08fb9`, `08fcdb11`, `91f48cec`). Carry-overs from 4.2 first: `pm_status/build/` is now `pm_status/bracket/` and the `.gitignore` negation is gone (`e8a08fb9`); `build-close` takes the counts Codex and Copilot expose instead of laundering `N/A` through `runtime=other` (`08fcdb11`). Then `estimate-entries` in `pm_status/sidecar/estimate.py`, a shared `sidecar/commit.py`, `metrics.estimates.rollup_values` extracted from `estimate-rollup`, four entries in `assets/wire-in.toml`, `l3io-plan estimate <folder>` (`steps/estimate/step-estimate-entries.md`), `bmad-agent-po` declared optional. Tests: seven in `test-pm-status-sidecar.py` (the four named), `tests/l3io-pm/test-sofia-hooks.py` (4, run from the shipped hook values, `git status --porcelain` empty after each), seven more in `test-build-hooks.py`. `smoke:install` renders Sofia after `wire`. CLI is 46 subcommands.

- Ruling: under `codex` and `copilot`, `build-close` takes `--tokens-input`/`--tokens-output` (and `--tokens-cache-read` with `--model` under Codex) and refuses `N/A` there with exit 2 before any write, leaving the bracket open; `other` records `N/A`; Claude refuses typed counts — why: metrics-contract.md §3, `set-actual` and `verify` all forbid `N/A` under codex and copilot (tests `test_tokens_na_forbidden_under_codex`/`_copilot`), and 4.2's close recorded `N/A` as `runtime=other`, so `verify --runtime codex|copilot` failed every ticket it closed. The 4.2 report's statement that `set-actual` refuses `N/A` for those runtimes was correct; the "refused only under claude" reading of the HARD RULE is not what the contract says — cost if wrong: a Codex or Copilot agent that cannot read its own usage cannot close a bracket until the contract is loosened in all three places.
- Ruling: a close with no plan file records the bracket's `dispatch_open`/`dispatch_close` and commits them, with no actual and no sample, exit 0 — why: `bmad-build-auto` runs On Complete at every HALT, including a step-1 `blocked` before `plan_file` is set (`step-01-clarify-and-route.md:2`), and refusing would leave the spool open and fail the hook — cost if wrong: a plan-less build's time is visible only in `events.jsonl`.
- Ruling: `set-estimate` does not refuse when a hand-set override exists; it writes ours and notes the override on stderr, as 4.1 left it — why: it is an explicit, per-entry call, the override still wins on read (`effective_estimate`), and refusing would make it impossible to record a model estimate beside a person's bare `estimate`; the sweep is the one that must not overwrite a person, so `estimate-entries` skips such an entry — cost if wrong: a deliberate `set-estimate` on a hand-estimated entry is silently secondary.
- Ruling: `estimate-entries` reads `tickets.toml` directly and read-only, not `tickets.py status` — why: the status rows (`public`, `tickets.py:722-745`) carry neither `description` nor `verify`, which the change test needs; `set-estimate` already reads it this way — cost if wrong: an entry `tickets.py` would reject is estimated anyway; `smoke:install` asserts `tickets.py status` is byte-identical and problem-free after a run.
- Ruling: the change test is a `fingerprint` (SHA-256 of the entry's `description`, `verify`, `covers`); a refine changes the leaf rather than the entry, so the refine hook names its entry with `--entry` — cost if wrong: a leaf-only edit outside REFINE is not re-estimated until replan or `--force`.
- Ruling: an entry to write with no class (given, recorded or hand-set `l3io_class`) is exit 2 naming every such entry, nothing written; the hook prose has the agent classify and re-run — why: the class is the one judgement, and a default class would be a guess recorded as a prediction — cost if wrong: one extra command per slice.
- Ruling: `estimate-entries` and `sidecar-reconcile` commit exactly what they changed (`chore(l3io): estimates <epic>`, `chore(l3io): reconcile sidecars`; a moved sidecar's old path as a deletion); `set-estimate`, `set-actual` and `add-test-run` are not hooks and commit nothing — cost if wrong: one commit per hook run that changed a file.
- Ruling: the epic roll-up is recomputed on every run, and dropped when no estimated entry is left — why: a move or drop otherwise leaves a stale `[epic].estimate` — cost if wrong: a calibration change rewrites the epic roll-up on the next hook run.
- Ruling: `--class` differing from the recorded class re-estimates (`reclassified`); `--force` re-estimates every entry without a hand-set estimate and never overrides one.

**Files:**
- Create: `skills/_shared/pm_status/sidecar/estimate.py`, holding `estimate-entries`.
- Modify: `skills/l3io-pm/l3io-plan/SKILL.md`. Add an `estimate` mode that runs `estimate-entries` over an initiative or epic folder. The 3.x modes stay until Task 4.8. Add a row to `help/help.md` (check:module).
- Modify: `assets/wire-in.toml` (four entries).
- Test: `skills/_shared/tests/test-pm-status-sidecar.py` (extend).

**Interfaces — wire-in writes:**

| Team file | Key | Kind | Entry id |
|---|---|---|---|
| `_bmad/custom/bmad-agent-po.toml` | `workflow.tickets_after` | scalar | `l3io-estimate-on-slice` |
| `_bmad/custom/bmad-agent-po.toml` | `workflow.refine_after` | scalar | `l3io-estimate-on-refine` |
| `_bmad/custom/bmad-agent-po.toml` | `workflow.replan_after` | scalar | `l3io-reestimate-on-replan` |
| `_bmad/custom/bmad-agent-po.toml` | `agent.menu` | keyed, `code = "l3io-estimate"` | `l3io-menu-estimate` |

- `estimate-entries --project-root P --ticket-dir D [--entry ID …] --class ID=CLASS … [--force]` reads `uv run {project-root}/_bmad/method/scripts/tickets.py status D` and writes `[entry.<id>]` for each new entry, each changed entry (description, `verify` or `covers` hash differs from the one recorded), or each `--entry` given. It uses `class × calibration`, as `estimate-story` does today. It then rolls up `[epic].estimate` as Σ entries + the epic closure band + the orchestration band. There is no sprint term (ADR-0016). It skips an entry carrying a hand-set `estimate`. It prints one JSON line per entry written.
- The menu value is `prompt = "Run the l3io-plan skill in estimate mode on the folder the user names, or the active initiative."`.
- `replan_after` runs `sidecar-reconcile` **first** (with the move JSON in context when there was a move), then re-estimates what the replan touched (Review Focus 3).

- [x] **Step 1: Failing tests:**
  - `test_estimate_entries_writes_only_l3io_toml` (byte check as in 4.1);
  - `test_changed_entry_is_reestimated_unchanged_is_not`;
  - `test_epic_rollup_has_no_sprint_term`;
  - `test_reconcile_then_estimate_after_move`. A recorded move from entry 3 → 7 leaves no `[entry.3]` estimate in the source, and leaves the estimate at `[entry.7]` in the destination.
- [x] **Step 2:** Implement, wire the four entries, and add `l3io-plan estimate`.
- [x] **Step 3: On the fixture:** wire, then render `bmad-agent-po`. The output contains our text at the end of `slice.md`, `ticket.md` and `replan.md`, and the menu lists `l3io-estimate`. Run `estimate-entries` on the hand-written initiative and assert `tickets.py status` is unchanged.
- [x] **Step 4:** Sync, regenerate manifests, then run the gate run.
- [x] **Step 5: Commit.** `feat(l3io-pm): estimate on Sofia's slice, refine and replan`.

### Task 4.4: Readiness gates on Sofia's validate (item 4)

**Done 2026-11-17** (`b20c1393`). `spec-align.py check-pointers --story-file`; `estimate-entries --check` in `pm_status/sidecar/estimate.py`; `DECLARED_EXTRAS` in `sync-shared-scripts.mjs` (l3io-execute declares `scripts/spec-align.py` and `scripts/facts/ac-dimensions.md`, synced from `skills/_shared/ac-dimensions.md`); three entries in `assets/wire-in.toml`. Tests: `TestV7Leaf` in `test-spec-align.py` (11), two `--check` cases in `test-pm-status-sidecar.py`, `tests/l3io-pm/test-readiness-checks.py` (8, run from the shipped hook values, `git status --porcelain` empty after each), and the extras case in `sync-shared-scripts.test.mjs`. `smoke:install` asserts both files installed, Sofia's rendered `validate-checks.md` and facts carry our entries, and both checks run from the installed paths. CLI is still 46 subcommands.

- Ruling: under `--story-file`, with no `--planning-root`/`--spec-paths`, a pointer resolves against the markdown file it names anywhere under the project root (`does not exist under the project root` otherwise) — why: a v7 project's specs are its tickets and their `sources:`/`companions:`, which sit beside the ticket tree, not under a planning folder, and a leaf naturally points at its epic's `## Requirements` — cost if wrong: any markdown file under the project counts as a spec; passing `--planning-root` restores the 3.x catalog.
- Ruling: the leaf's work type is `--work-type` (default `CODE`), given by the check agent; `business_ac_required` is read through core's `resolve_config.py` (default `"CODE,MIXED"` when the resolver or key is absent; an unknown entry exits 2 naming it); an explicit `--business` wins — why: a v7 leaf carries no work type, and the policy key names work types — cost if wrong: an agent that omits `--work-type` on a DOCS ticket is held to the CODE policy, the stricter side.
- Ruling: `--work-type` outside `--story-file` exits 2, and `--business` defaults to `advisory` there as before — why: the 3.x modes stay byte-for-byte in behaviour — cost if wrong: none.
- Ruling: a leaf whose frontmatter `type` is `initiative` or `epic` is refused (exit 2) — why: a container's acceptance criteria are its children's — cost if wrong: a container passed by mistake is a finding rather than a silent pass.
- Ruling: the Set check is a new read-only `estimate-entries --check`, not prose about `l3io.toml` — why: a hand-set `estimate`/`l3io_<metric>` in `tickets.toml` also counts, which an agent reading one file would miss; it refuses `--entry`/`--class`/`--force` and never resolves the state root — cost if wrong: one flag on a 4.3 verb.
- Ruling: the Ticket check text says an entry with no leaf file is a finding (not ready until pulled and refined) — why: the six-dimension gate is always enforced (CLAUDE.md), and an entry has nowhere to carry the sections — cost if wrong: Sofia surfaces every unpulled entry at validate; she sorts it as fix, suggest or ask.
- Ruling: extras are a fixed per-skill list keyed by skill name, and each must be delivered to that skill by a sync group; `--check` fails `declares X, which the payload does not contain` — why: the plan's "fixed extras list"; deriving it from wire-in.toml would couple the sync to an asset — cost if wrong: a hook naming a new installed file needs one line here, and `test_checks_text_names_only_declared_paths` fails until it is added.
- `test_checks_text_names_only_declared_paths` covers every `requires = "l3io-pm"` entry, not only the three new ones.

**Files:**
- Modify: `skills/_shared/spec-align.py`. `check-pointers` gains `--story-file F`, which reads a v7 leaf rather than a 3.x story. Business-AC policy reads `modules.l3io-pm.business_ac_required`. Never rename `TAC_HEADING`.
- Modify: `scripts/sync-shared-scripts.mjs`.
  - `l3io-execute` declares `scripts/spec-align.py` and `scripts/facts/ac-dimensions.md`. Sync `skills/_shared/ac-dimensions.md` to that path.
  - The generated `[skill] scripts` list takes a fixed extras list per skill beside the `pm_status` tree, and `--check` judges both.
- Modify: `assets/wire-in.toml` (three entries).
- Test: `skills/_shared/tests/test-spec-align.py`, `scripts/tests/sync-shared-scripts.test.mjs`, `tests/l3io-pm/test-readiness-checks.py` (new).

**Interfaces — wire-in writes:**

| Team file | Key | Kind | Entry id |
|---|---|---|---|
| `_bmad/custom/bmad-agent-po.toml` | `workflow.checks.ticket` | list | `l3io-check-technical-ac`: six dimensions, each satisfied or N/A with a reason; business ACs per policy; `spec-align.py check-pointers --story-file` |
| `_bmad/custom/bmad-agent-po.toml` | `workflow.checks.set` | list | `l3io-check-estimate-present`: every entry has `[entry.<id>].estimate` |
| `_bmad/custom/bmad-agent-po.toml` | `agent.persistent_facts` | list | `l3io-fact-ac-dimensions`: `file:{project-root}/_bmad/l3io-pm/scripts/facts/ac-dimensions.md` |

`validate_after` is not written (Ruling).

- [x] **Step 1: Failing tests:**
  - `test_check_pointers_on_v7_leaf` (resolving, unresolving, and `Spec: none — reason`);
  - `test_declared_extras_generated`. Removing `facts/ac-dimensions.md` from the payload fails `--check`, naming it;
  - `test_checks_text_names_only_declared_paths`. Every path in our `checks.*` and facts values is under `_bmad/l3io-pm/scripts/`.
- [x] **Step 2:** Implement, sync, generate the declared lists, and wire the entries.
- [x] **Step 3: On the fixture:**
  - `bmad setup` installs `_bmad/l3io-pm/scripts/spec-align.py` and `facts/ac-dimensions.md`;
  - after wire, the rendered `bmad-agent-po` `validate-checks.md` holds our Ticket and Set lines;
  - `spec-align.py check-pointers --story-file` runs from the installed path.
- [x] **Step 4:** Sync, regenerate manifests, then run the gate run, including `check:bmod` (the validator reads `skill.scripts`).
- [x] **Step 5: Commit.** `feat(l3io-pm): readiness checks run inside Sofia's validate`.

### Task 4.5: Waves and lanes on Sofia's board, and `report` over v7's tree (item 5)

**Done 2026-11-17** (`9633afaf`, `b4c20c8c`). The 4.4 carry-over first: the Ticket check holds an entry with no leaf file to a suggestion, never a fix (`9633afaf`, `test_entry_with_no_leaf_file_is_advisory`). Then `plan-graph.py waves`/`lanes` over recorded `tickets.py status` fixtures (`tests/l3io-plan/fixtures/`, re-recordable by `record-v7-status.sh`); `pm_status` verb `set-lane` in `sidecar/lanes.py`; `report --project-root --initiative-dir [--status-json]` in `metrics/report.py`, reading the `.inflight/` spool (the 4.2 carry-over, test first: `test_report_stall_reads_the_open_build_bracket`); `nodes.resolve_config_key` generalised from the output-folder read, and `nodes.v7_tickets_py`; l3io-plan declares `scripts/plan-graph.py` through `DECLARED_EXTRAS`; three entries in `assets/wire-in.toml`; `l3io-plan waves` (`steps/waves/step-waves.md`) and `lanes` retargeted. Tests: 14 in `test-plan-graph.py` (the four named), 6 in `test-pm-status-sidecar.py`, `tests/l3io-pm/test-board-hooks.py` (6, from the shipped hook values, `git status --porcelain` empty after each), the extras-only case in `sync-shared-scripts.test.mjs`. `smoke:install` asserts `plan-graph.py` installed, Sofia's `board.md` ending with our hook, both menu items, `waves`/`lanes`/`report` on the live initiative, and `tickets.py status` byte-identical. CLI is 47 subcommands.

- Ruling: an entry with no leaf file is advisory at validate (suggest, never fix) — why: Sofia builds such an entry as it is, and her own Ticket check already demands full criteria where her rule needs them (bugs, `refine = true`) — cost if wrong: an unpulled entry can reach `bmad-build-auto` without our six dimensions, as v7 intends.
- Ruling: `gates` holds only epics waited on for **closure**: a ticket's `after` naming an epic, and anything in an epic file's own `after` (`gated_by`, checked against done keys only); an `[[epic]] after` declaration or an entry-to-entry `after` orders the waves but gates nothing — why: tickets.py meets a ticket-level `after` once the ticket is in review (`classify`, `:581-606`), and a declaration releases nothing on its own (`unpinned_after` reports it unpinned) — cost if wrong: Task 4.7 pauses at fewer epics than an author who relies on declarations alone expects; a declared-only dependency still orders the waves.
- Ruling: on a parent initiative every prerequisite of a later wave is a gate, and the members are listed under the same `epics` key — why: `parent_view`'s `waiting_on` is every `after` not yet done — cost if wrong: a consumer reading `epics` as epic slugs at parent scope must check `scope`.
- Ruling: a `done` epic leaves the waves and its edges are met; a `dropped` one leaves them too, but an edge into it stays in the dependent's `after`, marked `dropped` — why: tickets.py never meets a dropped prerequisite, and Sofia's BOARD repoints it — cost if wrong: none; it is a display mark.
- Ruling: an entry-level `after` into another epic with no declaration still orders the waves, with `needs` empty and `via` naming the entries — why: otherwise search runs beside the cart it needs; tickets.py reports the same edge as `undeclared_after` — cost if wrong: none.
- Ruling: `set-lane` refuses while `lane_count` is unset or 1, not only outside `1..lane_count` — why: a lane written then would make a single-developer project stop being inert — cost if wrong: a team must run `bmad setup l3io-pm` before assigning a first lane.
- Ruling: `set-lane` commits what it wrote (`chore(l3io): lane <slug>`), though it is not a hook — why: it runs in the lanes mode between Sofia's commits and the next `bmad-build-auto`, exactly as `estimate-entries` does from the estimate mode — cost if wrong: one commit per lane assignment.
- Ruling: the board hook pipes Sofia's own `tickets.py status` command into `plan-graph.py` (a `<status command>` slot) instead of naming `_bmad/method/scripts/tickets.py` — why: every `_bmad/` path in a hook value must be one of ours (`test_checks_text_names_only_declared_paths`), and Sofia already knows the command; the l3io-plan step files name the installed path, which they may — cost if wrong: an agent that cannot find `tickets.py` renders no waves; the board itself is unaffected.
- Ruling: `report`'s v7 source takes `--status-json` beside running v7's installed `tickets.py`, refuses `--all`/`--status`/`--plan` (3.x only), and joins a ticket to its sidecar through the plan's `ticket:` frontmatter as `join_plans` does — why: tests and CI have no `tickets.py`, and the status rows carry no plan path — cost if wrong: a plan whose `ticket:` names neither the id nor the leaf stem shows no actuals, which tickets.py reports as a problem anyway.
- Ruling: `waves` is not folded into `report` — why: `pm_status` takes no graph library (plan-graph.py's docstring), and the board already renders waves — cost if wrong: the v7 report lists epics in build order rather than by wave.
- Ruling: `DECLARED_EXTRAS` may name a skill with no `pm_status` copy, which then declares its extras alone — why: plan-graph.py is l3io-plan's, and the plan has l3io-plan declare it — cost if wrong: none; `check:scripts` and the new extras-only test pin it.

**Files:**
- Modify: `skills/l3io-pm/l3io-plan/scripts/plan-graph.py`. Add `waves --status-json F` and `lanes --status-json F --lanes-toml T`. The input is `tickets.py status` JSON on an initiative **or a parent initiative** (§4.1, `board.md:13`). The sort runs over `[[epic]] after`, entry `after`, and `[[initiative]] after`. It preserves each `needs` reason string. `l3io-plan` declares it, so it installs at `_bmad/l3io-pm/scripts/plan-graph.py`.
- Create: `pm_status` verb `set-lane --project-root P --initiative-dir D --epic SLUG --lane N`. It refuses a non-number and anything outside `1..lane_count`, and writes only `[epic.<slug>].lane`.
- Modify: `skills/_shared/pm_status/metrics/report.py`. Add a v7 source: `tickets.py status` plus sidecars plus `events.jsonl`. The 3.x source stays until Task 4.8.
- Modify: `l3io-plan`: modes `waves` and `lanes` (the existing `steps/lanes/step-lanes.md` retargeted), with `help/help.md` rows. `assets/wire-in.toml` gets three entries.
- Test: `tests/l3io-plan/test-plan-graph.py` (extend), `skills/_shared/tests/test-pm-status-sidecar.py`.

**Interfaces — wire-in writes:**

| Team file | Key | Kind | Entry id |
|---|---|---|---|
| `_bmad/custom/bmad-agent-po.toml` | `workflow.board_after` | scalar | `l3io-board-waves`: runs `sidecar-reconcile` when the operation was a `move`, then renders waves and lanes |
| `_bmad/custom/bmad-agent-po.toml` | `agent.menu` | keyed, `code = "l3io-waves"` | `l3io-menu-waves` |
| `_bmad/custom/bmad-agent-po.toml` | `agent.menu` | keyed, `code = "l3io-lanes"` | `l3io-menu-lanes` |

- `waves` output: `{"scope": "initiative|parent", "waves": [{"n": 1, "epics": [...], "parallel": bool, "after": [{"epic": …, "needs": "…"}]}], "gates": [<epic slugs whose closure gates a later wave>]}`. `gates` is what Task 4.7 pauses on.

- [x] **Step 1: Failing tests:**
  - `test_waves_from_status_json`, on a recorded fixture from the pin's `tickets.py`;
  - `test_waves_parent_initiative_scope`;
  - `test_needs_reason_preserved`;
  - `test_gates_lists_epics_a_later_wave_waits_on`;
  - `test_set_lane_refuses_name_and_range`;
  - `test_report_reads_v7_tree`.
- [x] **Step 2:** Implement, declare `plan-graph.py`, and wire.
- [x] **Step 3: On the fixture:** run `waves` over the hand-written initiative's live `tickets.py status` output. Render Sofia after wire; `board.md` ends with our text.
- [x] **Step 4:** Sync, regenerate manifests, then run the gate run.
- [x] **Step 5: Commit.** `feat(l3io-pm): waves and lanes on Sofia's board`.

### Task 4.6: Closure on `bmad-retrospective` (item 7)

**Done 2026-11-17** (`3899271d`). New verb `epic-close` in `pm_status/sidecar/closure.py`, registered by `build_parser` (it reuses `bracket`'s token and summing helpers, now public, so `sidecar.verbs` cannot register it without a cycle); `calibration.closure_ratio` and `append_closure_ratios` extracted from the 3.x closure sample, unchanged for that path; `actuals_usage.first_tool_use_naming`; one entry in `assets/wire-in.toml`. Tests: seven in `test-pm-status-sidecar.py` (the four named, plus rejected verdict, the `--since` refusal and the second-run window), `tests/l3io-pm/test-retro-hooks.py` (3, run from the shipped hook value, `git status --porcelain` empty after it), the registration test at 48. `smoke:install` renders `bmad-retrospective` after wire with our command in `retro-document.md`'s On Complete, unwire removes the team file, a planted team `on_complete` makes wire exit 3 naming both values, and `epic-close` from the installed copy leaves `tickets.py status` byte-identical. CLI is 48 subcommands.

- Ruling: the retrospective's window is `--since`, else the first turn of this Claude session whose tool call names the document's file, clamped to start no earlier than the end of this epic's previous closure run or the last build of one of its tickets closed in the same session — why: the plan wires one entry, so there is no prepend to open a bracket, and the whole session would count every build before the retrospective; the document is created as a skeleton when the run starts (`retro-document.md:7`) — cost if wrong: a run that never touched the file by a tool call, or runs under another runtime, must pass `--since` (exit 2 names it); parallel epics in one session (Task 4.7) can still mix spend into one window.
- Ruling: `--man-hours`/`--hitl-hours` are the retrospective's own, and `[epic].actual` is Σ ticket sidecars + Σ closure runs per metric, `man_hours` included — why: metrics-contract §6 makes a parent's actual children plus its closure-phase spend, and the closure residual is measured from exactly that — cost if wrong: an epic's `man_hours` is a sum, not an independent counterfactual re-assessment of the whole epic.
- Ruling: closure is a list, `[[epic.closure_runs]]`, summed into `[epic.closure]` — why: a rejected retrospective is re-run after fixes, and both runs are closure spend, as `build-close` sums a ticket's brackets — cost if wrong: none.
- Ruling: the closure sample needs an accepted verdict (`accepted` or `accepted-with-open-items`) as well as an `[epic].estimate`, and is taken once (`[epic].calibration_sampled_at`) — why: after `rejected` the epic goes back to its tickets and its closure is not over, the same reason `build-close` samples only a built ticket — cost if wrong: an epic only ever rejected never calibrates the closure band.
- Ruling: the sample's numerator is the measured closure actual and its denominator is `closure_ratio` over the entries the epic estimate rolled up — why: on v7 the residual the 3.x sample derives is measured directly, and the denominator must be the quantity the ratio is applied to — cost if wrong: none beyond the 3.x model's own.
- Ruling: one part with no token count (an `N/A` ticket or closure, an unmatched bracket) makes the summed tokens `N/A` — why: a partial sum reads as the whole and would understate the epic — cost if wrong: a single unmeasured part hides the rest of the epic's tokens.
- Ruling: the verb commits only what it wrote and leaves the retrospective document as v7 left it — why: the retrospective commits nothing of its own (`retro-document.md:39`; committing is the user's, `acceptance-verdict.md:23`) — cost if wrong: an uncommitted retrospective still dirties the tree, so Task 4.7's `step-05-close` must commit it before the next `bmad-build-auto`.
- Ruling: a missing or unknown `verdict`, or a frontmatter `epic` naming another epic, is exit 2 with nothing written — cost if wrong: the agent re-runs after the retrospective fixes its frontmatter.
- `done` is not written here, as the plan states; Task 4.7's `step-05-close` writes it on an accepted verdict through the store.

**Files:**
- Create: `pm_status` verb `epic-close --project-root P --epic-dir D --retro-file F --runtime R [--model M] --man-hours H --hitl-hours H`, in `sidecar/closure.py`.
- Modify: `assets/wire-in.toml` (one entry).
- Test: `skills/_shared/tests/test-pm-status-sidecar.py`.

**Interfaces — wire-in writes:**

| Team file | Key | Kind | Entry id |
|---|---|---|---|
| `_bmad/custom/bmad-retrospective.toml` | `workflow.on_complete` | scalar | `l3io-epic-close` |

`epic-close` works as follows:

1. It rolls up `[epic].actual` in the epic's `l3io.toml` as Σ of every ticket sidecar under `D/tickets/`.
2. It records the retrospective session's own usage as the closure actual.
3. It appends one `closure` calibration sample when `[epic].estimate` exists.
4. It reads `verdict` from `F`'s frontmatter (`retro-document.md:9-21`) and writes it into the epic's `l3io.toml` as `[epic].retro_verdict`.
5. It commits what it wrote inside the worktree.

It writes **no** status. The retrospective writes none either (`retro-document.md:39`).

- [x] **Step 1: Failing tests:**
  - `test_epic_close_rolls_up_sidecars`;
  - `test_closure_sample_only_with_estimate`;
  - `test_epic_close_writes_no_status_and_no_tree_file` (byte check);
  - `test_verdict_read_from_frontmatter`.
- [x] **Step 2:** Implement and wire.
- [x] **Step 3: On the fixture:** render `bmad-retrospective` after wire; `retro-document.md`'s On Complete holds our command. Unwire leaves it byte-identical.
- [x] **Step 4:** Sync, regenerate manifests, then run the gate run.
- [x] **Step 5: Commit.** `feat(l3io-pm): epic actuals and closure calibration on bmad-retrospective`.

### Task 4.7: `l3io-execute` becomes the unattended run (item 6, the dev-agent half of item 8)

**Done 2026-11-17** (`ef25b36f`, `b38e0a99`). Step 1 measured first: a worktree carries a runnable `_bmad/` **only when the project commits `_bmad/`** (spec §13.5, ADR-0022), and a committed `_bmad/` exposed pm_status writing `__pycache__/` there, fixed in its own commit (`ef25b36f`, `TestNoBytecode`). Then `scripts/dispatch-plan.py` and `scripts/close-commit.py` in l3io-execute; new `steps/execute/step-02-resolve`, `step-03-sync`, `step-04-dispatch`, `step-05-close`; `steps/sprint/*`, `steps/closure/*` and the old `steps/execute/*` (arch gate included) deleted, with the in-package dev agent and the shim chain they carried; `sync-story-doc` and `archive-epic` deleted with their tests; `customize.toml` keeps `max_parallel_subagents` only; `auto-remediation.md` re-inventoried (19 sites); `bmad-dependencies.json` requires `bmad-build-auto`, `bmad-retrospective`, `bmad-agent-po`; ADR-0022. Tests: `tests/l3io-execute/test-dispatch-plan.py` (18, the six named plus worktree/serial, batching, scope, parent refusal, and the three carry-overs), `tests/l3io-execute/test-parallel-sidecars.py` (2 and 4 epics × 20 rounds). Mutations caught: dropping `--synced`, `thorough`, the gate pause, the retro commit, the state commit, and the calibration lock (10 of 40 and 26 of 80 samples lost). `smoke:install` runs the installed `dispatch-plan.py` over the live initiative on the repo store and with `store = "github"` planted. CLI is 46 subcommands.

- Ruling: worktrees are decided per project, every run, by `dispatch-plan.py` from `git ls-files` of `_bmad/scripts/render_skill.py`, `_bmad/method/scripts/tickets.py` and `_bmad/l3io-pm/scripts/pm_status/__main__.py`; the shipped `max_parallel_subagents` stays 4 and the planner caps it at 1 (`"worktree": null`) where they are not committed — why: the measured answer is "it depends on the project", so neither shipped default is right for both kinds — cost if wrong: a project committing only part of `_bmad/` is judged by those three files.
- Ruling: each epic of a parallel wave runs as **its own agent session** in its worktree; serial epics run one at a time in the orchestrator's session — why: the build bracket is keyed by session id and measured from that session's transcript, so two epics in one session collide — cost if wrong: a runtime that cannot start a second session runs the wave serially (step-04 says so).
- Ruling (4.6 carry-over): an epic's retrospective runs in the epic's own session, after its last build, **and** the step passes `--since` explicitly — why: the window is then unambiguous by construction, and `--since` does not rely on the first-touch heuristic — cost if wrong: none beyond 4.6's.
- Ruling (4.6 carry-over): `close-commit.py retro` commits the retrospective document right after the retrospective, before any further build, and prints the frontmatter verdict — why: v7 commits nothing and `epic-close` leaves the document — cost if wrong: one `docs(l3io): <epic> retrospective` commit per epic. Test: `test_retrospective_committed_before_the_next_build`.
- Ruling (4.2 carry-over): `close-commit.py state` commits the main checkout's project state root before every merge and at the start and end of the run, and refuses (exit 2) from a linked worktree — why: a build in a worktree can commit only its ticket sidecar — cost if wrong: one `chore(l3io): run state` commit per merge. Test: `test_main_checkout_left_clean`.
- Ruling (4.5 carry-over): the run pauses at exactly `plan-graph.py waves`' `gates` — confirmed, unchanged — why: `tickets.py` holds a dependent only on an epic its ticket's or epic file's own `after` names (`classify`, :581-606); an `[[epic]] after` declaration releases nothing, and wave order already serialises it — cost if wrong: an author relying on a declaration alone gets ordering, not a pause. Test: `test_gates_pause_before_dependent_wave`.
- Ruling: at a gate the run asks the user to close the epic in Sofia and re-reads `tickets.py status`; it never writes the container — why: a container's `done` is Sofia's on the user's word (`board.md`, Status), and we write no container file — cost if wrong: one manual step per gate.
- Ruling: the closing commits live in an l3io-execute script, not new pm_status verbs — why: Task 4.9 pins pm_status's final surface, and these commits are the run's, not a hook's — cost if wrong: one more skill-local script.
- Ruling: `update-issue` is **not** deleted — why: the caller map still finds the doctor's `triage` T6 using it; it goes with the issues verbs in 4.9 — cost if wrong: one verb lives one task longer.
- Ruling: the sprint-closure calibration code stays until 4.8 — why: it is reached through `set-actual --node sprint`, a kept verb's 3.x addressing that 4.8 deletes with the sprint terms; removing the sample alone would leave a sprint actual that writes no sample — cost if wrong: dead code for one task.
- Ruling: the `absolute` rows follow their meaning, not their sites: another session's epic is now its `l3io/<slug>` branch checked out in another worktree (`step-02-resolve`), and the risk-acceptance refusal is now a rejected retrospective (`step-05-close`); the readiness red-to-amber site left with `step-03-load-plan` — cost if wrong: none; no step writes readiness.
- Ruling: `dispatch-plan.py` refuses a parent initiative (exit 2), skips a blocked ticket or one waiting for REFINE with the reason, and never rebuilds a `built` ticket — cost if wrong: a parent initiative is run one child at a time by hand.
- Ruling: `l3io-execute` runs step-00-activate §0–§2.6 and §7 only, with `{pm_state_root}` = `{output_folder}/l3io` — why: §3–§6 detect and create the 3.x state tree, a tracked write the clean-tree check would refuse — cost if wrong: none for `l3io-plan`, which still runs them.
- Ruling: `bmad-code-review`, `bmad-qa-generate-e2e-tests` and `bmad-review` become optional, and `max_fix_iterations` leaves both PM skills; the phase matrix keeps only `l3io-plan`'s phases — why: nothing dispatches or reads them any more — cost if wrong: none.
- **Left for Phase 5 (Ruling above):** the epic architecture gate (re-home on `bmad-architecture`'s `finalize_reviewers`) and the epic-closure spec sync (beside `bmad-retrospective`'s decision records). Their step files are deleted; `CLAUDE.md` ("Readiness gates") and `docs/l3io-pm-reference.md` ("Not in this run") say so.

**Files:**
- Create: `skills/l3io-pm/l3io-execute/scripts/dispatch-plan.py`, a deterministic planner. It never runs a build.
- Replace: `skills/_shared/steps/execute/*`. New steps:
  - `step-02-resolve` resolves the store and the scope;
  - `step-03-sync` runs `mirror` and then `next --synced` on a tracker, and `next` on `repo`;
  - `step-04-dispatch` executes the emitted plan, one worktree per epic, up to `max_parallel_subagents`;
  - `step-05-close` runs `bmad-retrospective -H <epic>`, then on an accepted verdict writes `done` through the store, then merges the epic branch, then pauses at any `gates` epic for the user's confirmation.
- Delete:
  - `skills/_shared/steps/sprint/*`, `skills/_shared/steps/closure/*` and `step-04-arch-gate.md` (Ruling);
  - the in-package dev agent and the `bmad-create-story`/`bmad-dev-story` fallback chain;
  - every `{pm_status}` verb whose last caller was one of these files — `archive-epic`, `sync-story-doc`, `update-issue` — with their tests. Re-run the caller map before deleting each.
- Modify: `skills/l3io-pm/l3io-execute/SKILL.md`, `customize.toml` (`max_fix_iterations` goes), `references/auto-remediation.md` (the `BLOCKED:` table, check 36), `skills/l3io-util/l3io-doctor/assets/bmad-dependencies.json` (`bmad-build-auto`, `bmad-retrospective` and `bmad-agent-po` required; no shim chain, per ADR-0018), and `CLAUDE.md`'s execution contracts.
- Create: an ADR for one-worktree-per-epic, its number from `adr-reserve`.
- Test: `tests/l3io-execute/test-dispatch-plan.py` (new), `tests/l3io-execute/test-parallel-sidecars.py` (new).

**Interfaces:**
- `dispatch-plan.py --project-root P [--initiative D | --epic D] --max-parallel N` reads the store and `waves` (Task 4.5), and emits JSON: `{"store", "sync": [...], "waves": [{"n", "epics": [{"slug", "worktree", "branch", "tickets": [{"ref", "steps": [...]}]}]}], "gates": [...]}`. Each step is one of:

| Step | When / what |
|---|---|
| `sync` | tracker only: run Sofia's Tracker-sync procedure, then `next --synced` |
| `checkpoint-plan` | when `plan_checkpoint` |
| `build` | `bmad-build-auto` with the ticket ref, its folder, and the word `thorough` |
| `checkpoint-done` | when `done_checkpoint` |
| `close-epic` | `bmad-retrospective -H <slug>` |
| `status-done` | `repo`: `tickets.py mark <ref> done`; tracker: `store-write done` followed by `mirror` |
| `merge` | merge the epic branch |

  No other step kind exists.
- Store detection: `_bmad/custom/ticketing-store-config.toml` → `[tickets] store`, defaulting to `repo` (pins `tickets.py:780-793`).

- [x] **Step 1: Measure first.** On the fixture, `git worktree add ../wt-epic l3io/epic-x`, then run `uv run {wt}/_bmad/scripts/render_skill.py --project-root {wt} --skill .claude/skills/bmad-build-auto` and `tickets.py --project-root {wt} status <initiative>`. Record whether a worktree carries a runnable `_bmad/`, and whether its `{project-root}` stays inside the worktree. That depends on whether the project commits `_bmad/`.
  - **If yes,** parallel epics proceed.
  - **If no,** set the shipped `max_parallel_subagents` default to 1, have `dispatch-plan.py` emit `"worktree": null`, and record the finding in spec §13 and the ADR. The tests below still run, with worktrees created by the test.
- [x] **Step 2: Failing tests:**
  - **`test_tracker_store_never_calls_mark`.** With `store = "github"`, no emitted step, and no wire-in value or step file under `skills/_shared/steps/execute/` outside a tracker-guarded branch, contains `tickets.py … mark`. The first step is `sync`, and every `next` carries `--synced`. With `repo`, `status-done` is `mark … done`. (Review Focus 4.)
  - **`test_execute_has_no_review_phase`.** The step-kind set equals the table above. No step names `bmad-code-review`, `bmad-review`, a fix loop, story prep, elaboration or an architecture gate. Every `build` step carries `thorough`. No l3io step file under `steps/execute/` invokes a review skill.
  - **`test_parallel_epics_sidecars_survive`.** Two (and four) epics, each in its own `git worktree` sharing one state root through the common dir. Per ticket, one process rewrites its plan's frontmatter `status` the way `tickets.py`'s `edit_frontmatter` does (unlocked), while another runs `build-close`. A barrier forces overlap, over 20 rounds. Afterwards: every sidecar, N `dispatch` pairs, N calibration samples, every plan file parses, and no `.inflight` residue. (Review Focus 5.)
  - `test_checkpoints_emitted`, `test_gates_pause_before_dependent_wave`, `test_store_rule_matches_tickets_py`.
- [x] **Step 3:** Implement the script and the four steps. Delete the old phases and verbs. Sync, then run the caller grep: `git grep -nE "\b(archive-epic|sync-story-doc|update-issue)\b" skills/` returns nothing outside `CHANGELOG`/`docs/`.
- [x] **Step 4: On the fixture:** run `dispatch-plan.py` over the hand-written initiative twice, once with no store config and once with a planted `store = "github"`. Assert the step sets from Step 2. Add both to `smoke:install`.
- [x] **Step 5:** Sync, regenerate manifests, then run the gate run.
- [x] **Step 6: Commit.** `feat(l3io-pm)!: l3io-execute dispatches bmad-build-auto; no review or fix loop of its own`.

### Task 4.8: Retire what Sofia does; narrow `pm_status`'s placement half (item 8, first part)

**Done 2026-11-17** (`95d575a8`). `test_cli_surface_after_placement_retired` written first and seen failing (46 registered, 30 expected); the CLI is now 30 verbs. Deleted with their callers: the sixteen listed verbs, `plan/`, `l3io-plan`'s full plan and reorg (steps, `reorg-derive.py`, `reorg-validate.py`, their suites, plan-graph's `analyze`/`phases`/`partition`), the six doctor modes, `step-00-digest`, `step-01-classify-work`, `step-estimate`, `steps/plan/*` and step-00-activate §3–§6/§8. `report` is v7-only; the sprint roll-up, `set-actual --node sprint` and sprint closure/orchestration calibration are gone, and a file carrying sprint samples loads and ignores them (`test_a_file_with_sprint_samples_loads_and_ignores_them`). `git grep` of every deleted verb over `skills/` finds only the surface test's `RETIRED` tuple. check:types: 47 ungated (was 70), both gated classes 0.

- Ruling: `import-node` gains `--goal`, `--superseded-by` and `--depends-on`, so `migrate-engine.py` stops calling `set-field`/`set-depends-on` — why: they were the engine's last callers, and the 4.9 surface keeps neither — cost if wrong: extras land only on a node the import creates (a SKIP writes none), which is the idempotence the verb already promised.
- Ruling: the 3.x node addressing of `set-estimate`, `set-actual` (story|epic), `add-test-run`, `verify`, `estimate-story` and `estimate-rollup` stays until Phase 6 — why: `migrate-engine.py` writes estimates through `set-estimate`, `import-actual` runs through `set-actual`'s writer, `estimate-story`/`estimate-rollup` have no other address and Task 4.9's surface keeps them, and the calibration tests that reach v7's shared internals go through that arm — cost if wrong: a 3.x arm nothing in `skills/` invokes outside the migration lives one phase longer.
- Ruling: `estimate-rollup --epic` sums every story under the epic, sprint folders notwithstanding, and the 3.x epic closure sample's children are those stories (ADR-0016) — cost if wrong: none for v7, which uses `estimate-entries`/`epic-close`.
- Ruling: `nodes/` keeps the 3.x resolver beside the sidecar resolvers (Ruling on `import-node`); check 26 passes unchanged.
- Ruling: `l3io-plan` with no mode (or an unknown one) explains its three modes and points at Sofia's REFINE, REPLAN and BOARD; it is not a plan any more.
- Ruling: checks 2 (gating-tables) and 8 (digest-size) retire, numbers not reused; check 13 compares `spec-align.py`'s tuples with `ac-dimensions.md`; the check-4 `--reason` rule re-keys from `set-status` to `import-node`, which enforces it — cost if wrong: none.
- Ruling: the Remediable table of `auto-remediation.md` is empty (its four sites lived in the deleted activation and plan steps); ADR-0012 gains an amendment. The doctor's `SKILL.md` `pm_status`-not-installed halt is classified in the contract's Scope paragraph as a halt, since check 36 scans shared steps only and a row would be stale.
- Ruling: `bmad-sprint-planning` becomes optional; its only caller was the retired readiness phase.
- Ruling: `promote-issue` still honours an existing 3.x `_lock` (Task 4.9 removes it); its refusal now says to delete the `_lock` block, not `clear-lock`.

**Files:**
- Delete from `l3io-plan`:
  - the full-plan mode and its steps (`steps/plan/*`: readiness, story elaboration, load state, dependency graph, plan output, backlog intake);
  - `reorg` and `reorg-undo` (`steps/reorg/*`, `reorg-derive.py`, `reorg-validate.py`, their suites).

  `l3io-plan` keeps `estimate`, `waves` and `lanes`. Its `SKILL.md`, description and `help/help.md` say so. REFINE replaces elaboration and REPLAN replaces reorg, each named in `docs/upgrading.md`.
- Delete from the doctor the modes that write the 3.x tree: `bootstrap-state`, `split-status`, `sort-status`, `reconcile-status`, `schema-migration` and `clean-layout`. Delete their step files, routing rows and help rows. `migrate-state` stays (Ruling). `health-check` and `stats` are retargeted to the v7 tree through `report`'s v7 source.
- Delete these `pm_status` verbs with their last callers:
  - status and placement: `set-status`, `move-epic`, `reparent-story`, `retire-epic`, `reorg-log`, `reorg-undo`, `dump-plan`;
  - listing and display: `list-epics`, `list-stories`, `show`;
  - node writes: `set-depends-on`, `story-doc-init`, `set-field`;
  - locks: `set-lock`, `clear-lock`, `check-lock`.

  Also delete the sprint terms in `estimate-rollup` and calibration (ADR-0016), the 3.x node addressing of the kept verbs, and `report`'s 3.x source. `nodes/` keeps only the sidecar resolvers. Split any module that the deletions leave incoherent; never raise the cap.
- Modify: `skills/_shared/status-files.md` (now the sidecar contract only), `metrics-contract.md`, `calibration-model.md` (no sprint), `step-00-digest.md`, `CLAUDE.md` (state files, placement rule, sprints, the reorg journal), `docs/l3io-pm-reference.md` and `docs/l3io-util-reference.md`.

- [x] **Step 1: Failing test** `test_cli_surface_after_placement_retired`. The argparse subcommand set equals the §4.5 keep set + Task 4.1–4.6 additions + the issues verbs (Task 4.9) + `import-node`/`import-actual` (Ruling) + `notice`, `rates`, `usage`, `dispatch`, `verify`, `sync-agent-instructions`.
- [x] **Step 2:** Delete callers before verbs, file by file. After each deletion, check 4 (invocations against argparse) must still pass. Then run `git grep` for each deleted verb over `skills/` and confirm zero.
- [x] **Step 3:** `npm run check:types -v`. Record the new finding count, which moves with deletions, and confirm the two gated classes stay at zero.
- [x] **Step 4:** Sync, regenerate manifests, then run the gate run.
- [x] **Step 5: Commit.** `feat(l3io-pm)!: retire the full plan, reorg and the 3.x placement model`.

### Task 4.9: Dissolve `issues.yaml` into v7's `backlog/`; finish §4.5 (item 8, last part)

**Files:**
- Delete the `pm_status` verbs `append-issue`, `update-issue` (if not already gone), `promote-issue`, `schedule-issue`, `resolve-issue`, `repair-issue`, `list-issues` and `audit-issues`, the `issues/store.py`/`promote.py`/`audit.py` modules, and their tests. `issues/adr.py` (`adr-reserve`) moves to `adr/`.
- Create: `skills/l3io-util/l3io-doctor/scripts/audit-tree.py`. It runs findings 1a–1l, re-expressed over v7's tree: `backlog/` leaves, `type = "bug"`, `tickets.toml` entries and our sidecars, plus orphaned sidecars from Task 4.1. It writes nothing. Its fixes are proposals for Sofia (REFINE, BOARD `move`).
- Modify: the doctor's `triage` (audit over the v7 tree; closing is Sofia's) and `harvest-debt`. `harvest-debt` emits candidate `bug-<slug>` entries for Sofia's TICKETS/REFINE in `backlog/`; we write no leaf. The `stats` backlog section changes to match. `CLAUDE.md`'s issues paragraphs (`issues.yaml`, `issues-resolved.yaml`, ADR-0002) become a short "4.x: v7 backlog" note.
- Test: `tests/l3io-doctor/test-audit-tree.py` (new); `skills/_shared/tests/test-pm-status.py` loses the issues classes.

- [ ] **Step 1: Failing tests:**
  - `test_audit_tree_findings_1a_to_1l`, one fixture per finding that still has a meaning on v7, plus a table in the test naming each finding that has none and why;
  - `test_audit_tree_writes_nothing`;
  - **`test_pm_status_surface_is_4_5`**: the final subcommand set equals exactly the §4.5 keep set (`estimate-story`, `estimate-rollup`, `calibration`, `set-estimate`, `set-actual`, `add-test-run`, `dispatch`, `report`, `adr-reserve`), plus `usage`, `rates`, `verify`, `notice` and `sync-agent-instructions`, plus `sidecar-reconcile`, `build-open`, `build-close`, `estimate-entries`, `set-lane` and `epic-close`, plus `import-node`/`import-actual` until Phase 6.
- [ ] **Step 2:** Delete callers, then verbs. Run `check:docs` (check 4 and check 36) after each.
- [ ] **Step 3: Phase exit on the fixture** (Exit below).
- [ ] **Step 4:** Sync, regenerate manifests, then run the gate run and `smoke:install`.
- [ ] **Step 5: Commit.** `feat(l3io-pm)!: issues live in v7's backlog; pm_status narrowed to spec §4.5`.

**Exit (Phase 4):** R3, R4, R13 and R14 on the fixture.
- **R13:** `test_bmad_build_alone_records_actuals` passes, and `smoke:install` renders both build skills with our hooks.
- **R4:** `test_tracker_store_never_calls_mark` passes, and the planted-tracker plan on the fixture starts with `sync`.
- **R14:** `test_execute_has_no_review_phase` passes; `git grep` finds no dev agent, shim chain, reorg, elaboration or issues ledger.
- **R3:** this needs an agent session, so no gate can prove it. On a fixture built by `make-fixture.sh` with all four modules wired, one epic is planned in Sofia, run with `/l3io-execute`, and closed through `bmad-retrospective`. The transcript is kept under `docs/superpowers/notes/`, and all five metrics are read back from the sidecars and the epic's `l3io.toml`.

Every `checks.yml` gate must be green.

## Infeasible points, as measured

- **Parallel waves cannot share one working tree.** `bmad-build-auto` requires a clean tree to start and leaves a clean, committed one (`step-01:60`, `step-04:171-174`). The parent's "runs waves in parallel up to `max_parallel_subagents`" needs a worktree per epic. Whether a worktree carries a runnable `_bmad/` is not yet measured (Task 4.7 Step 1). If it does not, 4.0.0 runs epics serially.
- **"Unattended" stops at every epic gate.** An epic-level `after` needs the predecessor container `done`, which is user-confirmed (`tickets.py:584-590`, `board.md:55`). Only waves of independent epics run without a human.
- **R13 is narrower than written.** An interactive `bmad-build` runs `on_complete` only on success, and an unestimated ticket yields no calibration sample (Rulings).
- **R3 and R4 cannot be fully proven by a gate.** R3 needs an agent session (recorded manually at exit). R4's tracker half is verified on the command plan, not against a live tracker. §11's need for a real Jira or Linear project still stands.
- **`interactive = false` cannot be set** on `bmad-build-auto`; the key does not exist, and setting it would halt the render (Ruling).
