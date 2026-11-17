---
name: l3io-plan
description: Estimate a BMad v7 initiative's tickets, order its epics into waves, and partition them into lanes for several developers. Use /l3io-plan estimate [<folder>] to estimate a v7 initiative or epic into l3io's sidecars, /l3io-plan waves for the order a v7 initiative's epics may run in and the closures that gate them, /l3io-plan lanes for who owns which epic when several developers share one. Shaping and refining the plan itself is Sofia's (bmad-agent-po) through REFINE, REPLAN and BOARD.
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

**Mode routing.** Match the argument against this table. This file routes and carries no
procedure. With no argument, or one the table does not match, say what the three modes do and
that shaping the plan — slicing, refining tickets, moving them — is Sofia's (`bmad-agent-po`:
REFINE refines a ticket, REPLAN reshapes the plan, BOARD moves tickets), then stop.

| Keyword | Load | Menu | Notes |
|---|---|---|---|
| `estimate` | `steps/estimate/step-estimate-entries.md` | registered | estimate a v7 initiative's or epic's entries into l3io's `l3io.toml` sidecars; optional folder |
| `waves` | `steps/waves/step-waves.md` | registered | a v7 initiative's (or parent initiative's) epics in the order they may run, and the closures that gate them; read-only |
| `lanes` | `steps/lanes/step-lanes.md` | registered | which lane owns each epic of a v7 initiative when several developers share it; inert unless `lane_count` > 1 |

**Estimate mode** (args start with `estimate`): the argument after `estimate`, when there is
one, is a BMad v7 initiative or epic folder; none at all means the active initiative, or the
one Sofia's `l3io-estimate` menu item sent you from. Load:
```
{skill-root}/steps/estimate/step-estimate-entries.md
```
It writes only l3io's `l3io.toml` sidecars, never a v7 file.

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
