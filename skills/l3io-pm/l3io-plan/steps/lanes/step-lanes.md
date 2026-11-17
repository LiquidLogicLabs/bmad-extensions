# Lanes — who owns what, and how several developers share one plan

**A lane is a slot in a partition, never a person.** Who works a lane lives in each
developer's own gitignored config, so a name never reaches the repository. That is also why a
lane is a **number**: `backend` and `sarah` are the same shape, so no pattern could permit one
and refuse the other.

## 1. Is this project running lanes at all?

Read `{lane_count}` (`modules.l3io-pm.lane_count`, set by `bmad setup l3io-pm`).

- **Absent, or `1`** — lanes are off. Say so in one line and stop:
  `Lanes are off for this project (one developer). bmad setup l3io-pm can change that.`
  **Do not prompt, do not propose, do not assign.** An absent module config section is a
  valid permanent state, never a first-run trigger, and a project that never asked for lanes
  must not be able to tell this mode exists.
- **`N > 1`** — continue.

The mode is a **configured answer**, never inferred from the tree. A project set up for three
lanes that has not assigned any yet looks exactly like a single-developer project if you only
scan epics, and the two must not get the same answer.

## 2. Which initiative, and has the partition been made?

Lanes are on a BMad v7 initiative's epics, one lane per epic, recorded as `[epic.<slug>] lane`
in l3io's own `l3io.toml` beside the initiative's `tickets.toml`; v7's files are never written.
Use the initiative the user named, else the active one Sofia is working in; a parent
initiative has no lanes of its own, so ask which of its initiatives.

```bash
uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} status <initiative> \
  | uv run {skill-root}/scripts/plan-graph.py lanes --status-json - \
      --lanes-toml <initiative>/tickets/l3io.toml --lanes {lane_count}
```

If it reports **no lanes**, there is a partition to propose: its `proposal` is it — go to §3.
If it reports lanes, go to §4; an existing partition is a decision already taken, and this
mode does not re-open it.

## 3. Propose a partition

Report **both** numbers the proposal carries, because they are different objectives and a
good score on one can hide a bad score on the other:

- **`cross_lane_edges`** — how much the lanes still wait on each other. Zero means genuinely
  independent work.
- **`idle_waves` per lane** — a partition can be perfect by connectivity and still hand one
  lane only late-wave epics, leaving that developer idle until another finishes.

```
📋 Proposed partition — {lane_count} lanes over {n} epics

Lane 1: epic-platform, epic-cart, epic-checkout   waves 1–3
Lane 2: epic-search, epic-docs                    waves 1, 3   idle in wave 2

Cross-lane dependencies: 2   (epic-search → epic-platform, epic-search → epic-cart)
```

**If the proposal carries crossings or idle waves, say what fewer lanes would cost.** Asking
for more lanes than the work supports forces splits through real dependencies — the price is
real and belongs in front of the person deciding whether to add a developer, not behind them.

**Confirm before assigning.** On agreement, write each epic's lane:

```bash
uv run {pm_status} set-lane --project-root {project-root} --initiative-dir <initiative> --epic <slug> --lane <n>
```

`set-lane` refuses anything that is not a lane number in `1..{lane_count}`, and refuses
outright while lanes are off. It writes only the initiative's `l3io.toml` and commits it.

## 4. Show a lane's view

A **filter** over the waves, not a second document — a per-lane file would be another source
of truth and would go stale the next time the plan changes. Sofia's board shows the same view
after every board operation once `l3io-doctor wire` has run.

With `{lane}` bound (from the developer's own gitignored config), show that lane. Without it,
show every lane, from the `lanes` JSON of §2:

```
📋 Lane 2 — 2 epics across waves 1 and 3

Waves:        1 (epic-docs), 3 (epic-search)
Waits for:    lane 1 — epic-search on epic-platform (the catalogue index), on epic-cart
Waited on by: nothing
Idle in:      wave 2 — no epic owned
Unassigned:   none
```

`Waits for` and `Waited on by` are the lane's `waits_for` and `waited_on_by`. An epic in
`unassigned` has no lane yet: offer §3's `set-lane` for it.

Rendering this to a file is fine, but the rendering **names when it was taken**, so a printed
copy cannot be mistaken for current once the plan changes.

## 5. The protocol — what makes this safe

**Every `flock` in `pm_status` guards one filesystem, and two clones share none.** Between
developers, concurrency is mediated by `git merge` and nothing else. The protocol exists
because of that, and all of it follows from it.

**Assign lanes, commit and push before execution begins.** Everyone forks from one commit, so
the initiative's `l3io.toml` is the same in every clone. This does not eliminate the merge; it
bounds it to a known surface.

**Each lane writes only its own epics' folders.** A ticket's actuals sit beside its plan, and
its estimates in its epic's `l3io.toml`, so disjoint ownership means git has nothing to
reconcile there.

**Three files are shared, under `{output_folder}/l3io/`, and they are not equally hard:**

| File | Behaviour |
|---|---|
| `events.jsonl` | Both lanes append. `merge=union` is literally the right semantics — 2 lines + 2 lines = 4, all identities preserved. **This project needs the rule added; see below** |
| `pm-calibration.yaml` | Order-independent samples. A lost one degrades estimates without corrupting anything |
| `adr-register.yaml` | A **global** allocator — the one real collision |

### The one line this project must add

**The extension does not ship a `.gitattributes` into your repository, and cannot** — that file
belongs to your project, not to an installed skill. Without the rule, **every** multi-developer
merge conflicts on `events.jsonl` alone, and the conflict looks alarming while being entirely
mechanical.

Check whether it is already there, and offer to add it if not:

```bash
grep -q 'events.jsonl' .gitattributes 2>/dev/null && echo present || echo missing
```

The line to add — `union` is built into git and needs nothing installed:

```
**/l3io/events.jsonl merge=union
```

Ask before writing it: it is the user's file. Then write it yourself rather than handing them
the editing — once they have agreed, locating the file and appending a line is mechanical work
there is no reason to give back. Append; never rewrite a `.gitattributes` that already exists.

**Reserve ADR blocks before the fork**, which is why the allocator's inability to cross clones
stops mattering — a reservation made before anyone diverges needs no lock:

```bash
uv run {pm_status} adr-reserve --state-root {output_folder}/l3io --epic <slug> --slug <topic> --count 6
```

## 6. What lanes do NOT solve

**Source-file collisions.** The dependency graph proves two epics have no `after` between
them. It says **nothing** about whether both rewrite the same module. Two lanes can be
perfectly independent in the plan and still spend a week diverging on one file — the failure
that makes teams abandon parallel work, and the one invisible to every signal here.

Say this out loud when proposing a partition. Lanes partition *work*, not *code*.

## 7. Output status line

```
Step lanes complete — lane_count: {lane_count}, assigned: {n} epic(s), cross-lane edges: {n}
```
