<!-- resolver-invariant: canonical-contract -->
# Status File Layout Contract

This file is the single source of truth for **where** l3io's state lives on disk and **how**
to read or write it. It is a **deep reference, consulted on demand** — do not load it at
activation. `pm-status.py` outranks it, since it enforces these rules mechanically.

**On BMad v7 (4.x) the contract is §12**: v7 owns the work-item tree, and l3io writes only
sidecars beside it plus the project-wide files under `{output_folder}/l3io/`. **§1–§11 describe
the 3.x sharded state tree — read only by the migration.** Nothing in 4.x writes it, and
`pm-status.py` no longer addresses it: `l3io-pm`'s `migration-1` (run by `bmad migrate`) reads
it with the doctor's `migrate-engine.py` and writes its data into the §12 sidecars.

**4.x: v7 backlog.** l3io keeps no issues ledger. A 3.x tree's `issues.yaml` and
`issues-resolved.yaml` have no reader or writer in 4.x: deferred work is a ticket in v7's
`{output_folder}/backlog/` (`bug-<slug>.md` and the like), filed and closed by Sofia
(`bmad-agent-po`). `/l3io-doctor triage` audits that backlog read-only and `harvest-debt`
proposes candidate bugs; neither writes a leaf.

State is addressed through `pm-status.py` by a v7 address, never by hand-built path. No skill
or step file should construct a state path itself — see "Addressing" below.

## 1. File locations

In a 3.x tree, all l3io-pm state lived under `{implementation_artifacts}/state/` — committed
to git, co-located with the artifacts it describes. Nothing state-related lives under
`{project-root}/_bmad/` any more; that tree is installer-owned and gitignored.

```
{implementation_artifacts}/
│
├── state/                                   ← machine-written, pm-status.py only
│   ├── planned/
│   │   └── epic-005/
│   │       ├── epic.yaml                    ← depends_on lives here
│   │       └── sprint-01/
│   │           ├── sprint.yaml
│   │           └── E005-S01-001.yaml
│   ├── active/
│   │   ├── epic-001/
│   │   │   ├── epic.yaml
│   │   │   ├── sprint-01/
│   │   │   │   ├── sprint.yaml
│   │   │   │   ├── E001-S01-001.yaml
│   │   │   │   ├── E001-S01-002.yaml
│   │   │   │   └── E001-S01-003.yaml
│   │   │   └── sprint-02/
│   │   │       ├── sprint.yaml
│   │   │       └── E001-S02-001.yaml
│   │   └── epic-004/…
│   ├── archived/
│   │   └── epic-002/…                       ← done; keeps its full tree
│   ├── issues.yaml                          ← 3.x backlog; no 4.x reader or writer
│   ├── events.jsonl                         ← append-only transition log
│   ├── pm-calibration.yaml
│   └── adr-register.yaml                    ← ADR number allocator (`next`, `reserved`)
│
├── epic-001/                                ← human/agent-authored artifacts
│   ├── sprint-01/
│   │   ├── stories/
│   │   │   ├── E001-S01-001.md
│   │   │   ├── E001-S01-002.md
│   │   │   └── E001-S01-003.md
│   │   ├── closure/
│   │   └── tests/
│   ├── sprint-02/…
│   ├── tests/
│   └── epic-closure/
├── epic-002/…                               ← artifacts persist after close; never move
└── epic-004/…
                                             ← no epic-005/ — nothing authored until work starts
```

An epic's directory lives in exactly one of `planned/`, `active/`, or `archived/` at any
time (see "Placement rule" below). Every sprint and story of that epic lives inside the same
epic directory, one file per node.

`events.jsonl` is an append-only JSON-lines log — one object per status or actuals write,
appended automatically by the writing verb under `flock`. It is the only place
per-status *dwell* time can come from: `updated_at` records just the last write and is
overwritten by any field change, so it cannot distinguish "entered review 20 minutes ago"
from "had its estimate patched 20 minutes ago". It is committed, and it is one
project-level log rather than one per sprint — per-sprint files would fragment the timeline
and turn cross-epic velocity into a multi-file join. Absent on projects that predate it, in
which case `report` falls back to `updated_at` and marks those dwell figures approximate
with a `~` prefix. Never read it to determine current status; the node files are
authoritative for that, and the log is history.

## 2. The two trees

`state/` and the top-level `epic-{nnn}/` directories hold two different *kinds* of fact
about the same epic. They are not duplicates of each other.

| | `state/{status}/epic-001/` | `epic-001/` (top level) |
|---|---|---|
| Holds | Status, estimates, actuals, locks | Story markdown, closure reports, QA tests, ADRs |
| Written by | `pm-status.py` only, atomically | Humans and the story implementer (legacy `bmad-dev-story`) / review agents |
| Format | YAML metadata | Prose, code, test files |
| Moves? | Yes — `planned/` → `active/` → `archived/` | Never. Created once, stays forever |
| Answers | "What state is it in?" | "What is it?" |

Two asymmetries follow, both correct:

- **A planned epic has state but no artifacts.** Status and estimates exist before any
  story is authored. State comes into existence first.
- **A done epic keeps both, permanently.** Artifacts never move on close, which is why
  state must not collapse on close either — otherwise the mirror holds for active epics and
  breaks for finished ones.

**Every epic with artifacts has state; not every epic with state has artifacts yet.**

## 3. Key schema

- Epic key: `E{nnn}` (3-digit zero-padded string, e.g. `"E001"`) → directory `epic-{nnn}`
- Sprint key: `S{nn}` (2-digit zero-padded string, e.g. `"S01"`) → directory `sprint-{nn}`
- Story key: `E{nnn}-S{nn}-{nnn}` (globally unique, e.g. `"E001-S02-003"`) → file
  `E{nnn}-S{nn}-{nnn}.yaml` inside that sprint's directory
Node fields use `key:` (not `id:`) in every file.

## 4. Per-file schema

Sharding splits a nested tree into files, so each file's contents are specified below.

**Nodes are stored bare — no `epics:` list wrapper.** The wrapper existed only when one file
held many epics. With one node per file it is pure noise.

**The directory structure replaces the `sprints:` and `stories:` lists.** This is the
largest schema consequence of sharding: `epic.yaml` has no `sprints:` key and `sprint.yaml`
has no `stories:` key. Children are discovered by listing the directory — sprint
subdirectories under an epic, story `.yaml` files (excluding `sprint.yaml`) under a sprint.

**Child files carry a back-reference to their parents** (`epic:` on sprint and story files,
`sprint:` also on story files). The path already encodes this, so it is redundant —
deliberately. It makes each file self-describing when read standalone or matched by grep,
and it lets `verify --scope epic` catch a file sitting in the wrong directory by comparing
its path against its contents.

```yaml
# state/active/epic-001/epic.yaml
_lock:                                    # machine metadata, underscore-prefixed, first key
  session_id: 'l3io-pm-2026-08-16T10:00:00-abc123'
  claimed_at: '2026-08-16T10:00:00'
  ttl_minutes: 30
key: 'E001'
title: 'Epic 001 — Foundation'
goal: 'Stand up the core platform'
status: in-progress
depends_on: []                            # epic keys; read by l3io-plan
lane: 2                                   # OPTIONAL. 1..999. Which lane owns this epic
estimate:                                 # ranges at epic/sprint level
  man_hours_low: 40
  man_hours_high: 60
  hitl_hours_low: 6
  hitl_hours_high: 10
  elapsed_hours_low: 8
  elapsed_hours_high: 12
  tokens_k_min: 2000
  tokens_k_max: 3200
  cost_low: 8.25                          # derived from tokens_k_min/max x rates; never entered
  cost_high: 13.20
  model: claude-opus-5                    # the rate card that priced the range
  confidence: medium
actual:                                   # METRIC_FIELDS — all five required
  elapsed_hours: 11.5
  man_hours: 52                           # counterfactual re-assessment, not observed
  hitl_hours: 7.2
  tokens_k: {total: 2840, input: 420, output: 140, cache_write: 850, cache_read: 1430}
  cost: 6.98                              # derived; written by the tool, never by hand
  model: claude-sonnet-5                  # with by_model: the model that carried most tokens
  # by_model:                             # optional — only for a run on more than one model
  #   claude-opus-5-5: {total: 1310, input: 100, output: 10, cache_write: 1000, cache_read: 200}
  #   claude-sonnet-5-5: {total: 670, input: 50, output: 20, cache_write: 500, cache_read: 100}
  # tokens_k is then the per-class sum, and cost is each model at its own rates
  # (set-actual --tokens-by-model; verify re-prices it the same way)
orchestration:                            # sprint/epic only — the orchestrator's own overhead
  elapsed_hours: 0.6
  man_hours: 0                            # AI-only overhead; no human-developer counterfactual
  hitl_hours: 0.1
  tokens_k: {total: 90, input: 14, output: 5, cache_write: 27, cache_read: 44}
  cost: 0.23
  model: claude-sonnet-5
orchestration_sampled_at: '2026-08-16T22:34:03Z'  # replay guard; set-actual --block orchestration
# no `sprints:` — sprint-NN/ directories are the list
retired_reason: 'nothing depends on it'   # a 3.x retirement; why it went
retired_at: '2026-10-09T16:00:00Z'
```

```yaml
# state/active/epic-001/sprint-01/sprint.yaml
key: 'S01'
epic: 'E001'                              # back-reference; path must agree
next: 7                                   # story-key high-water; pm-status.py only
title: 'Sprint 01 — Foundation'
status: in-progress
estimate:
  man_hours_low: 12
  man_hours_high: 18
  hitl_hours_low: 1.5
  hitl_hours_high: 2.5
  elapsed_hours_low: 2.5
  elapsed_hours_high: 4
  tokens_k_min: 600
  tokens_k_max: 950
  cost_low: 2.48                          # derived; never entered
  cost_high: 3.93
  model: claude-opus-5                    # the rate card that priced the range
  confidence: high
actual:
  elapsed_hours: 3.2
  man_hours: 15                           # counterfactual re-assessment, not observed
  hitl_hours: 1.8
  tokens_k: {total: 812, input: 122, output: 41, cache_write: 244, cache_read: 405}
  cost: 2.02
  model: claude-sonnet-5
# no `stories:` — E001-S01-*.yaml files are the list
```

**`next` on a sprint is a high-water mark and never decreases.** Story keys are allocated as
`max(sprint.next, highest-on-disk + 1)`, so a vacated number is never reissued. Deriving from
the disk alone was safe only while stories could merely appear; the moment one can MOVE, a
freed key handed to a different story silently retargets that key's issue in any external
tracker mapping it — nothing errors, and the issue now tracks different work. The disk is
still consulted alongside `next`, which is what makes this need no migration (an absent `next`
behaves exactly as before) and no repair verb (a `next` that is somehow too low cannot cause a
reuse, because the disk floor still applies). The only visible consequence is that keys go
sparse where a story is deleted, instead of the next one backfilling the hole.


**Sprint status lifecycle:** `backlog → in-progress → review → done`. `review` means **every
child story is at `review` and none has been closed** — the sprint's work is written and
awaiting verdicts, as distinct from `in-progress`, where stories are still being produced.
It is **optional**: an orchestrator may go `in-progress → done` directly, and nothing requires
the intermediate state. The epic lifecycle has no `review` (`backlog → in-progress → done`) —
an epic spans sprints that can be in different states, so it has no single meaning there.

```yaml
# state/active/epic-001/sprint-01/E001-S01-003.yaml
key: 'E001-S01-003'
epic: 'E001'                              # back-references; path must agree
sprint: 'S01'
previous_keys:                            # append-only, oldest first; written by a 3.x re-key
- 'E007-S02-004'                          #   a single previous_key would lose the first hop
title: 'Implement token ledger'
status: review
classification: complex
estimate:                                 # single values at story level
  man_hours: 6
  hitl_hours: 0.8
  elapsed_hours: 1.5
  tokens_k: {total: 320, input: 48, output: 16, cache_write: 96, cache_read: 160}
  cost: 1.32                              # derived; never entered
  model: claude-opus-5
  confidence: high
actual:
  elapsed_hours: 1.8
  man_hours: 7                            # counterfactual re-assessment, not observed
  hitl_hours: 0.5
  tokens_k: {total: 355, input: 53, output: 18, cache_write: 107, cache_read: 177}
  cost: 1.47
  model: claude-opus-5
```

`_lock` (epic files only) is 3.x machine metadata, the first key when present — see §6.

## 5. Placement rule

**In a 3.x tree, an epic's directory lives in the folder named for its status** —
`planned/`, `active/` or `archived/` — with its sprints and stories inside it. A node lives in
exactly one place. Nothing in 4.x moves an epic between those folders; the migration reads
them as they are.

## 6. Ownership lock

A 3.x run claimed an epic by writing a `_lock` block (`session_id`, `claimed_at`,
`ttl_minutes`) as the first key of its `epic.yaml`. Nothing writes or reads one in 4.x.

## 7. Addressing

**Every write goes through `pm-status.py`, at a v7 address (§12). Skills never construct state
paths themselves.** Layout knowledge lives in exactly one place — `pm_status/nodes/`, the
resolver section check 26 judges — so a layout change only touches that package. The 3.x node
address (`--state-root` with `--story`/`--epic`/`--sprint`), and the migration-only
`import-node` and `import-actual`, retired with the 3.x tree; the migration engine reads that
tree itself and writes the sidecars directly.

Subcommand summary (see `pm-status.py --help` for full flags):

| Subcommand | Addressing |
|---|---|
| `set-estimate` | `--project-root P --ticket-dir DIR --entry ID` + the four calibrated metrics — writes `[entry.<id>].estimate`; the manual override of what `estimate-entries` computes |
| `set-actual`, `add-test-run`, `verify` | `--project-root P --plan-file PATH` — the ticket sidecar `<plan-stem>.l3io.toml` beside the plan |
| `estimate-entries` | `--project-root P --ticket-dir DIR [--entry ID ...] [--class ID=CLASS ...] [--model ID] [--token-rates JSON]` — computes each entry's estimate from `BASE_BANDS` × calibrated scope ratio × fix factor, per metric, prices `cost` from the estimated `tokens_k`, and rolls the epic's range-form estimate up with the closure and orchestration bands (no sprint level, ADR-0016). It is the v7 address of the retired 3.x story-estimate and roll-up verbs |
| `calibration show` \| `migrate-metrics` | `--state-root [--format {text,json}]` — `show` is a read-only report of every component's sample count and active ratio (a missing file reports cold-start and exits `0`); `migrate-metrics` reshapes a pre-metrics-rework calibration file in place (gated on its own marker, idempotent). The 3.x `redrive` retired with the story files it re-derived from |
| `report` | `--project-root P --initiative-dir D` (+ optional `--status-json F`, `--format`, `--out`, `--watch`, `--stall-minutes N`) — progress over a v7 initiative (§12); read-only unless `--out` is given |
| `dispatch` | `--state-root --event {open,close} --agent NAME` + optional `--epic`/`--sprint`/`--story`/`--session-id` — records a dispatch boundary into `events.jsonl`; the keys are labels, not addresses |
| `rates` | `[--model ID] [--token-rates JSON]` — prints the effective per-model token rate table (read-only); an unknown `--model` exits 2 |

`set-actual` appends a line to `events.jsonl` as a side effect of a successful write
(`--no-events` suppresses it, `--session-id` stamps it). A failed append warns on stderr and
never fails the write — the sidecar is the primary record and telemetry must not be able to
block it. It records **no** calibration sample: that is `build-close`'s and `epic-close`'s
(§12), specified in the calibration model — `l3io-execute/references/calibration-model.md`,
which ships with the PM skills (`l3io-execute`, `l3io-plan`) and not with every skill that
carries this contract.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success / verified |
| `2` | Usage error |
| `3` | Plan, entry or sidecar not found |
| `4` | Verification failure (missing/invalid field) |

### `verify`

`verify --plan-file PATH` checks **completion of one ticket's sidecar**: all five `actual.*`
metric fields present and correctly typed (numeric for `elapsed_hours`/`man_hours`/
`hitl_hours`; `tokens_k`/`cost` may only be `N/A` under a non-Claude runtime), a structured
`tokens_k.total` matching the sum of its four classes, `cost` matching what those classes
price out to under the sidecar's own `model` field — a hand-edited cost cannot pass — and
`completion_evidence` present. A bare scalar `tokens_k` fails under `--runtime claude` or
`--require-tokens`: with no class split there is nothing to price `cost` against. The status
is the plan's and v7's, so it is not judged. The 3.x `--scope epic` structural check retired
with the tree it walked.

## 8. Ordering is structural

Zero-padded names — `epic-{nnn}` (3 digits), `sprint-{nn}` (2 digits), story files
`E{nnn}-S{nn}-{nnn}.yaml` (3-digit sequence) — make lexical directory-listing order the
correct display and processing order. There is no separate ordering field to maintain and no
way for order to drift out of sync with intent, the way it could inside a YAML list.

## 9. Concurrency

Every write takes a lock over its whole read-modify-write cycle — load, derive, mutate, save —
never just the save. Locking only the save was not safe: two concurrent callers each loaded
the same state and the second save silently dropped the first's write, with both calls still
exiting 0.

- **A sidecar** is written under an exclusive `flock` on its own directory (`sidecar.locked`),
  so every writer of every sidecar in one tickets folder serialises and no lock file is left
  in the user's tree.
- **`pm-calibration.yaml`** and **`adr-register.yaml`**, the two project-wide shared-append
  targets, each take their own lock (`calibration_lock` / `adr_register_lock`), re-entrant
  within a process so a save nested inside its own lock does not deadlock. Every
  `build-close` and `epic-close` across every worktree may append a calibration sample; every
  `adr-reserve` allocates a block of ADR numbers.
- **`.notices.yaml`** is read and written under `notices_lock`, keyed on `--key` alone (there
  is no cross-invocation session identifier), for the `l3io-execute`/`l3io-plan` setup-pointer
  (`config-resolution.md` §5).
- **`events.jsonl`** is appended under a leaf flock inside `append_event`.
- **`spec-sync.lock`** is the spec-edit lease written by `spec-align.py lease` (JSON:
  `owner`, `acquired_at`, `expires_at`), held across an agent's turns.

**None of the lock files is ever committed.** `pm-status.py` keeps both `*.lock` and
`.notices.yaml` in `{state_root}/.gitignore` — one `_ensure_lock_ignore` mechanism covers both
patterns. Every lock acquisition inside a state root checks that file, at most once per process
per state root; a lock taken with no state root is skipped, so it never writes a `.gitignore`
into a repo root. Any pattern absent from the file is appended (patterns already present are
left alone, never rewritten or reordered); an absent file is created with both. The check is
best-effort: a failure warns on stderr and never fails the verb. Neither pattern matches a
directory, so a `git check-ignore` of the state-root directory itself still passes.

The first number `adr-reserve` hands out is the larger of the register's `next` and the
highest ADR number already on disk — in `--adr-dir` and in the old per-epic home
`epic-*/arch/` — plus one (ADR-0005). Outside a git work tree and with no `--adr-dir`, the
one ADR home cannot be located at all, so `adr-reserve` **refuses** (exit 2, nothing on stdout,
register untouched) and names `--adr-dir` in the message. It does not fall back to the old home
and print a number: a caller reads the number off stdout, and an allocation made without seeing
`docs/adr/` is exactly the collision the register exists to prevent.

A 3.x tree serialised every `epic.yaml` write on a per-epic lock (`{state_root}/epic-NNN.lock`)
and left a `.yaml.lock` beside a story that recorded a test run. Nothing takes either in 4.x;
the files the migration finds are left where they are and stay ignored.

## 10. Read resolution at activation

4.x activation reads no 3.x tree. It binds `{pm_state_root}` = `{output_folder}/l3io` (§12),
and leaves a 3.x tree where it is. `l3io-pm`'s migration (`bmad migrate`, once method's own
migration has built the v7 initiative) moves its data; `migrate-engine.py` detects the layout
itself:

| Found | Layout |
|---|---|
| `{implementation_artifacts}/state/` | 3.x sharded |
| `{project-root}/_bmad/state/` | legacy (per-epic file) |
| `{implementation_artifacts}/sprint-status.yaml` | legacy (flat) |

### Bindings

| Binding | Resolves to |
|---|---|
| `{pm_state_root}` | `{output_folder}/l3io` (§12); a 3.x tree's `{implementation_artifacts}/state` is read only by the migration |
| `{pm_calibration_file}` | `{pm_state_root}/pm-calibration.yaml` |

There are no other state-path bindings: every path below `{pm_state_root}` is resolved
internally by `pm-status.py`, never bound by a step file.

## 11. Dependency fields

### `lane` — which lane owns this epic

**Optional, epic-only, and a NUMBER.** Absent means lanes are not in use, which is the normal
state for a single-developer project and must stay completely inert.

`lane` partitions planned work across developers who each have their **own clone**. That is why
it exists at all: every `flock` in `pm-status.py` guards one filesystem, and two clones share
none, so concurrency stops being mediated by locks and becomes mediated by `git merge`. With
each lane writing only its own `epic-{nnn}/` directory, git merges disjoint paths cleanly and
the collision surface shrinks to four shared files.

**1 epic = 1 lane**, and sprints and stories inherit it from the directory they live in — they
never carry their own. That is the invariant the rest rests on: it makes the lane graph the
epic graph with relabelled nodes, so every cross-lane question is answered by relabelling a
computation that already exists rather than by a second traversal. On v7 the lane is
`[epic.<slug>].lane` in the initiative's `l3io.toml`, written by `set-lane` (§12).

**It is a number because a word cannot be screened.** A lane is a slot in a partition, never a
person — who works a lane is recorded in the **gitignored** user config, so a name cannot reach
the repository. `backend` and `sarah` are the same shape, so any pattern permitting the first
permits the second; numbering closes that by construction. `set-lane` refuses anything else.

`depends_on` on an epic node (`epic.yaml`): list of epic keys that must be `status: done`
before this epic can start. Present regardless of which status folder the epic currently
sits in (most commonly populated while the epic is under `planned/`). On v7 the dependency
is the epic's `after`, which v7's own migration writes from `epics.md`.

`depends_on` on a story node: list of globally-unique story keys (`E{nnn}-S{nn}-{nnn}`) that
must be `status: done` before this story starts. Lives in that story's own file.

**`depends_on` must always be a YAML list, even for a single dependency** — `['E001']`, never
`'E001'`. A scalar is refused (exit 2, naming the file) by `pm-status.py` and by
`plan-graph.py`; it is not coerced, because a bare string could equally have been meant as
one key or as several. The refusal exists because a string *iterates character by character*:
a scalar `'E001'` is read as the four keys `E`, `0`, `0`, `1`, none of which match an epic, so
the dependency is dropped entirely and the epic reads as having none. A migration reader meets
both shapes in old trees.

## 12. 4.x sidecars

On BMad v7, v7 owns the work-item tree — `tickets.toml`, leaf files and plans — and
`pm-status.py` **never writes any of them** (ADR-0015; design §3.2). What l3io records about
that tree lives in TOML sidecars beside it, written through `tomlkit` (comments and key order
survive) under a `flock` on the sidecar's own directory (no lock file is left in the tree).
None of these names is a `*.md` file or an `epic-*` directory, so `tickets.py`'s folder scan
never reads one.

| File | Holds | Written by |
|---|---|---|
| `<initiative>/tickets/l3io.toml` | `[epic.<slug>]` with `lane` (1..`lane_count`) | `set-lane` |
| `<initiative>/tickets/epic-<slug>/tickets/l3io.toml` | `[entry.<id>]` with `class`, `fingerprint`, `estimated_at` and `estimate` (the five metrics, canonical order); `[epic]` with `estimate`, `actual`, `closure`, `closure_runs`, `retro_verdict`, `calibration_sampled_at`, `orchestration` | `estimate-entries`; `set-estimate --ticket-dir DIR --entry ID`; `epic-close` |
| `<…>/tickets/<stem>-plan.l3io.toml`, beside `<stem>-plan.md` | `actual`, `fix_iterations`, `completion_evidence.test_runs` / `tests_passing`, `dispatch`, `calibration_sampled_at` | `build-close`; `set-actual`, `add-test-run` with `--plan-file PATH` |
| `{state_root}` = `<main checkout>/<core.output_folder>/l3io/` | `events.jsonl`, `pm-calibration.yaml`, `adr-register.yaml`, `.notices.yaml`, `.inflight/` | every verb with `--project-root P` |

**The state root is the main checkout's from any worktree.** The main checkout is the
directory holding `git rev-parse --path-format=absolute --git-common-dir`, which every linked
worktree shares; `core.output_folder` is resolved by BMad core's
`{project-root}/_bmad/scripts/resolve_config.py --key core.output_folder` and re-anchored on
the main checkout. A project with no resolver is a usage error (exit 2) — pass `--state-root`
for a 3.x state tree instead.

**Addressing.** `--project-root P` takes the place of `--state-root S`, and a v7 address takes
the place of the node keys: `--ticket-dir DIR --entry ID` for an entry's estimate,
`--plan-file PATH` for a ticket's actuals, test runs and `verify`. Mixing the two schemes is
a usage error. `--ticket-dir` may name the epic folder or its `tickets/` folder; an entry id
that its `tickets.toml` does not hold, or a plan that does not exist, is exit 3. A ticket's
`verify` judges the sidecar as a story node's is judged, except its status, which is the
plan's and v7's to write. `set-actual` on a ticket records **no** calibration sample: a sample
pairs an actual with the estimate made before the work, and that pairing is the build
bracket's.

**Hand-set overrides.** A person may set `estimate` or an `l3io_<name>` key on a
`tickets.toml` entry. It is read, never written: `l3io_<metric>` replaces that metric of our
`[entry.<id>].estimate`, `l3io_class` the class, and a bare `estimate` (v7's own field, in
whatever unit the user gave) is carried verbatim and marks the entry hand-estimated.

**`tickets.py move` does not carry our sidecars.** It moves the leaf and the plan and
renumbers the entry; a folder's `next_id` never decreases, so an old id is never reused.
`sidecar-reconcile --project-root P --initiative-dir D --moved-json J` (J = the move's stdout)
repoints `[entry.<old_id>]` to `[entry.<id>]` in the destination's `l3io.toml` and moves the
plan's sidecar beside the moved plan. Without `--moved-json` it sweeps `D`: a plan sidecar
whose plan is gone is moved beside the one same-named plan elsewhere, and an `[entry.<id>]`
no `tickets.toml` holds is reported, since it cannot be followed without the move.

**Estimates come from Sofia's own procedures.** `/l3io-doctor wire` gives `bmad-agent-po` a
`tickets_after`, a `refine_after` and a `replan_after` hook and an `l3io-estimate` menu item.
Each hook runs `estimate-entries --project-root P --ticket-dir D`, which estimates every entry
of the epic that is new, whose `description`, `verify` or `covers` changed (the recorded
`fingerprint`), whose class changed, or that `--entry` names (band × calibrated scope ratio ×
fix factor, per metric); then it recomputes `[epic].estimate` as the entries' sum plus the epic closure
and orchestration bands, with no sprint term. The class is the agent's judgement, passed as
`--class ID=CLASS`; an entry to write without one is refused with nothing written. An entry
with a hand-set estimate in `tickets.toml` is never written. The replan hook runs
`sidecar-reconcile` first, so a moved entry's estimate follows it before anything is
re-estimated.

**The hooks leave the tree clean.** `estimate-entries` and `sidecar-reconcile` commit exactly
the files they changed (`chore(l3io): estimates <epic>`, `chore(l3io): reconcile sidecars`),
because they run after Sofia's own commit and before the next `bmad-build-auto`, which
refuses a dirty tree. `set-estimate`, `set-actual` and `add-test-run` are not hooks and
commit nothing.

**Readiness runs inside Sofia's validate.** `/l3io-doctor wire` appends one entry to her
`workflow.checks.ticket` list and one to `workflow.checks.set`, so her own check subagents run
them and her findings sort ours. The Ticket check runs `spec-align.py check-pointers
--story-file <leaf>` from `{project-root}/_bmad/l3io-pm/scripts/`: the business and six
technical AC dimensions, each with a resolving `Spec:` line, a pointer resolving against the
markdown file it names under the project root, and the business section required per
`modules.l3io-pm.business_ac_required` for the `--work-type` given. The Set check runs
`estimate-entries --check`, which lists every entry with neither our estimate nor a hand-set
one. Both only read. A `persistent_facts` entry names the installed
`facts/ac-dimensions.md`, so REFINE writes the dimensions the Ticket check enforces.

**Every build is measured through its own hooks.** `/l3io-doctor wire` gives `bmad-build` and
`bmad-build-auto` a prepend that runs `build-open` and an On Complete that runs `build-close`.
`build-open` writes only `{state_root}/.inflight/<key>.json`; the spool holds a `.gitignore`
of `*`, so it is invisible to git and `bmad-build-auto`'s clean-tree check still passes.
`build-close` appends the `dispatch_open`/`dispatch_close` pair, adds the bracket to the
plan sidecar's `dispatch` list and writes `actual` as the sum of that list (tokens from the
Claude transcript over the bracket; under Codex and Copilot the counts the agent passes as
`--tokens-*`, refused when missing because `N/A` is forbidden there; `N/A` under `other`;
`cost` derived), records each
`--test-run`, and takes `fix_iterations` from the plan's `review_loop_iteration`. It takes one
calibration sample per ticket, and only when the plan reads `built` or `done` and the entry's
`[entry.<id>].estimate` exists: an estimate made after the build is not a prediction. It then
commits each path it wrote inside the current worktree, and nothing else, as
`chore(l3io): actuals <ticket>`, so the tree is clean for the next build. A bracket that never
closed is retired as `abandoned` by the next open under the same key or for the same plan,
and its events are written at the next close.

**Waves and lanes on Sofia's board.** `/l3io-doctor wire` gives `bmad-agent-po` a `board_after`
hook and two menu items, `l3io-waves` and `l3io-lanes`. After every board operation the hook
runs `sidecar-reconcile` when the operation was a `tickets.py move`, then pipes Sofia's own
`tickets.py status` into `{project-root}/_bmad/l3io-pm/scripts/plan-graph.py` (declared by
`l3io-plan`): `waves` orders the initiative's epics, or a parent initiative's initiatives,
over the `[[epic]] after` declarations, the entries' cross-epic `after` and each epic file's
own `after`, keeping every `needs` reason, and names in `gates` the epics whose **closure** a
later wave waits on — an `after` that names an epic, or sits in an epic file, waits for
`done`, where one naming a ticket is met once that ticket is built. `lanes` reads the
initiative's `l3io.toml` and is empty while no epic carries a lane. Both only read.

**A lane is written by `set-lane`**, `--project-root P --initiative-dir D --epic SLUG --lane N`:
`N` a number in `1..lane_count`, refused while `modules.l3io-pm.lane_count` is unset or 1, and
committed as `chore(l3io): lane <SLUG>`. One epic is one lane; a ticket never carries one.

**`report --project-root P --initiative-dir D`** is the progress view over this layout:
`tickets.py status` (or `--status-json F`) for states, plus each epic's lane, estimates and
ticket actuals from the sidecars, joined through each plan's `ticket:` frontmatter as
`tickets.py` joins it. A build bracket still open in `.inflight/` past `--stall-minutes` is
reported as a stalled build: until `build-close` runs, the spool is the only place it exists.
It writes nothing unless `--out` is given.

**Epic closure rides `bmad-retrospective`.** `/l3io-doctor wire` gives it an On Complete that
runs `epic-close --project-root P --epic-dir D --retro-file F` once the retrospective document
is saved. It appends one record per retrospective run to `[[epic.closure_runs]]` in the epic's
`l3io.toml` — its window, `man_hours`, `hitl_hours`, tokens and verdict — and writes
`[epic.closure]` as the sum of those runs and `[epic.actual]` as every ticket sidecar under
`D/tickets/` **plus** the closure: a parent's actual is its children plus its own closure-phase
spend, never the bare sum (`metrics-contract.md` §6). The window starts at `--since`, else at
the first turn of the Claude session that touched `F`, and never before the epic's previous
closure run or the last build of one of its tickets in the same session; under any other
runtime `--since` is required. `verdict` is read from `F`'s frontmatter into
`[epic].retro_verdict`. One `closure` calibration sample is taken per epic, and only when
`[epic].estimate` exists and the verdict is `accepted` or `accepted-with-open-items`. It
**writes no status** — neither does the retrospective — and commits only its own files, as
`chore(l3io): epic close <slug>`; the retrospective document is left as v7 left it.
