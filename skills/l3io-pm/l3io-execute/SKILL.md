---
name: l3io-execute
description: Run a BMad v7 initiative or epic unattended — dispatches bmad-build-auto per ticket in wave order, one git worktree per epic where the project allows it, closes each epic with bmad-retrospective, and stops at epic gates for the user. Use when the user wants Sofia's planned tickets built without driving each build by hand.
---

# l3io-execute

The unattended multi-ticket run v7 does not have. It plans nothing and reviews nothing of its
own: Sofia (`bmad-agent-po`) owns the tickets, `bmad-build-auto` builds and reviews each one
(invoked `thorough`), and `bmad-retrospective` judges each epic. This skill decides the order,
runs the builds, commits what the closing steps leave behind, and asks the user wherever v7
says the user decides.

## Conventions

- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- Bare paths (e.g. `steps/shared/step-00-activate.md`) resolve from `{skill-root}`.

## On Activation

Run: `uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`

If the script fails, resolve the `workflow` block by reading `{skill-root}/customize.toml`, then
`{project-root}/_bmad/custom/l3io-execute.toml` (team), then
`{project-root}/_bmad/custom/l3io-execute.user.toml` (personal) in order. Scalars override, arrays append.

`setup`, `configure`, and `install` are not recognized arguments here — `bmad setup l3io-pm` is
the module's setup entry point. Config itself is resolved in step-00-activate per
`{skill-root}/references/config-resolution.md`; an absent `modules.l3io-pm` section means the
module has no overrides, not that it needs setup.

## Execution

**Epic session** — when the invocation is `epic-session` and the context carries
`l3io_epic_run`, this is one epic of a run, started by the orchestrator in the epic's own
worktree. Run step-00-activate §0–§2a only, then bind `{epic}` = `l3io_epic_run`, `{store}` and
`{po_root}` from the context, and run:

```
{skill-root}/steps/execute/step-04-dispatch.md   §2 and §3 for {epic}
{skill-root}/steps/execute/step-05-close.md      §1 and §2 for {epic}
```

End with the epic's last line (step-04 §3) and nothing after it.

**Normal mode** — load the shared activation, then the run's steps in order:

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
{skill-root}/steps/execute/step-02-resolve.md
{skill-root}/steps/execute/step-03-sync.md
{skill-root}/steps/execute/step-04-dispatch.md
{skill-root}/steps/execute/step-05-close.md
```
