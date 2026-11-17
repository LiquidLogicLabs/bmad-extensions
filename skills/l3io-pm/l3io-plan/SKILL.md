---
name: l3io-plan
description: Validate readiness, elaborate stories, estimate, build dependency graph, and produce an executable plan. Use when the user wants to plan across epics before execution, to re-estimate existing ones, or to reorganize a plan that is legal but badly shaped. Use /l3io-plan for a full plan, /l3io-plan estimate [E{nnn}|E{nnn}-S{nn}] to re-estimate only (or /l3io-plan estimate <folder> for a BMad v7 initiative or epic), /l3io-plan reorg to propose a better plan shape, /l3io-plan waves for the order a BMad v7 initiative's epics may run in, /l3io-plan lanes for who owns which epic when several developers share one.
---

# l3io-plan

## Conventions

- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- Bare paths (e.g. `steps/shared/step-00-activate.md`) resolve from `{skill-root}`.

## On Activation

Run: `uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`

If the script fails, resolve the `workflow` block by reading `{skill-root}/customize.toml`, then `{project-root}/_bmad/custom/l3io-plan.toml` (team), then `{project-root}/_bmad/custom/l3io-plan.user.toml` (personal) in order. Scalars override, arrays append.

`setup`, `configure`, and `install` are not recognized arguments here — `bmad setup l3io-pm` is the module's setup entry point. Config itself is resolved in step-00-activate per `{skill-root}/references/config-resolution.md`; an absent `modules.l3io-pm` section means the module has no overrides, not that it needs setup.

## Execution

**All modes — load first:**
```
{skill-root}/steps/shared/step-00-activate.md
```

Before reading any further state, apply the once-per-project setup pointer
(`{skill-root}/references/config-resolution.md` §5) — this skill is one of the two skills the
pointer is wired into. It fires only when `{l3io_pm_section_absent}` (bound in step-00-activate
§1, from config already resolved there) is `true` — a configured project gets no pointer at
all:

```bash
if [ "{l3io_pm_section_absent}" = "true" ]; then
  uv run {pm_status} notice --state-root {pm_state_root} --key setup-pointer && \
    echo "l3io-pm currently has no project-level configuration. bmad setup l3io-pm configures it if you want to."
fi
```

`notice` is keyed on `--key` alone, not a session — there is no cross-invocation session
identifier available (`{session_id}` is bound fresh per invocation), so this fires **at most
once ever** for this project, not once per invocation. Exit 1 means this key was already
recorded — print nothing further, permanently, for this key. Exit 2 means recording it
actually failed (never conflated with exit 1). Never halt on any branch, and never treat this
as a setup trigger.

```
{skill-root}/steps/shared/step-01-classify-work.md
```

**Mode routing.** Match the argument against this table; everything it does not match is the
full plan mode. Each mode's body lives below or in its own `steps/` file — this file routes
and carries no procedure.

| Keyword | Load | Menu | Notes |
|---|---|---|---|
| `plan` (or no argument) | the full-plan step list below | default | the default: readiness → elaboration → graph → estimate → snapshot |
| `estimate` | `steps/shared/step-estimate.md`; for a v7 folder, `steps/estimate/step-estimate-entries.md` | registered | re-estimate only; optional `E{nnn}` or `E{nnn}-S{nn}` scope, or a v7 initiative or epic folder |
| `reorg` | `steps/reorg/step-reorg.md` | registered | propose, confirm and apply a better plan shape — writes planned work only |
| `waves` | `steps/waves/step-waves.md` | registered | a v7 initiative's (or parent initiative's) epics in the order they may run, and the closures that gate them; read-only |
| `lanes` | `steps/lanes/step-lanes.md` | registered | which lane owns each epic of a v7 initiative when several developers share it; inert unless `lane_count` > 1 |

**Undo has no keyword, by design.** A user asks for it in prose — "undo that reorg" — and the
agent resolves which journal entry they mean. Load `steps/reorg/step-reorg-undo.md` on such a
request. There is no flag for it and none of this skill's modes parse one.

**Full plan mode** (default — no args, or args that do not start with `estimate`, `reorg`, `waves` or `lanes`):

Bind `{scope}` = `all` before loading step-estimate.

```
{skill-root}/steps/plan/step-backlog-intake.md         ← offers backlog → story promotion; never automatic
{skill-root}/steps/plan/step-02-readiness-check.md
{skill-root}/steps/plan/step-03-story-elaboration.md   ← no-op when readiness is green
{skill-root}/steps/plan/step-04-load-state.md
{skill-root}/steps/plan/step-05-dependency-graph.md
{skill-root}/steps/shared/step-estimate.md
{skill-root}/steps/plan/step-06-plan-output.md
```

**Estimate mode** (args start with `estimate`):

When the argument after `estimate` is a folder — a BMad v7 initiative or epic, or none at all
when Sofia's `l3io-estimate` menu item sent you — load only this and stop when it is done:
```
{skill-root}/steps/estimate/step-estimate-entries.md
```
It writes only l3io's `l3io.toml` sidecars, and none of what follows applies to it.

Otherwise (the 3.x state tree):

Parse scope from arg: `estimate` → `{scope}=all`; `estimate E{nnn}` → `{scope}=E{nnn}`; `estimate E{nnn}-S{nn}` → `{scope}=E{nnn}-S{nn}`. Then load:
```
{skill-root}/steps/shared/step-estimate.md
```
Output estimate summary only. No graph, no elaboration, no plan document.

Estimate mode writes state and **must not touch any plan snapshot** — snapshots are immutable
once written, and `l3io-execute` may be reading one concurrently. Their estimate blocks are a
point-in-time report stamped `estimates_as_of` (see `step-06-plan-output.md` §2); re-estimating
makes that stamp stale, which is the stamp doing its job.

Say so rather than silently leaving a stale report behind. After the summary:

```bash
test -f {planning_artifacts}/plan-output-meta.yaml && \
  grep '^current_plan:' {planning_artifacts}/plan-output-meta.yaml
```

If a pointer exists, print:
```
ℹ️  Estimates updated in state. {current_plan} still shows the estimates from when it was
   generated — run /l3io-plan (full) to produce a snapshot with the new numbers.
   Execution is unaffected: l3io-execute reads estimates from state, not the snapshot.
```

If no pointer exists, print nothing — there is no snapshot to go stale.

**Reorg mode** (arg starts with `reorg`):

```
{skill-root}/steps/reorg/step-reorg.md
```

Proposes one improvement to the shape of the plan, shows it as a plan summary the user can
accept or reject in about a minute, and applies it only on confirmation. It writes **planned
work only**; active and archived work is read-only input. Nothing is deleted — a retired epic
is archived with its reason recorded, and the whole reorg is journaled so it can be undone.

**Undo** (a conversational request, never a flag):

```
{skill-root}/steps/reorg/step-reorg-undo.md
```

Like estimate mode, reorg writes state and **must not touch any plan snapshot** — snapshots
are immutable once written. Tell the user to run `/l3io-plan` for a snapshot that reflects the
new shape.

**Waves mode** (arg starts with `waves`):

```
{skill-root}/steps/waves/step-waves.md
```

Orders a BMad v7 initiative's epics, or a parent initiative's initiatives, into waves from
v7's own `tickets.py status`, keeping each dependency's `needs` reason, and names the epics
whose closure gates a later wave. It writes nothing. Sofia's `l3io-waves` menu item sends you
here, and her board shows the same view after every board operation.

**Lanes mode** (arg starts with `lanes`):

```
{skill-root}/steps/lanes/step-lanes.md
```

Shows who owns which epics of a BMad v7 initiative when several developers work it, proposes
a partition when `{lane_count}` is set above 1 and none has been made, and carries the
protocol that keeps two clones from colliding. Sofia's `l3io-lanes` menu item sends you here. **Completely inert when `{lane_count}` is absent or 1** — a
single-developer project must not be able to tell this mode exists.
