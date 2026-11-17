# Step 02: Resolve the store, the scope and the run plan

This step decides what the run builds, in which order, and where. It writes nothing but the
commit of l3io's own project state (§2). Everything it decides comes from v7: the store from
`_bmad/custom/ticketing-store-config.toml`, the tickets from `tickets.py status`, and the order
from `plan-graph.py waves`. `dispatch-plan.py` turns those into the plan the rest of the run
follows; it never runs a build.

## 1. Parse the scope

Inspect the text that follows `/l3io-execute`:

| Argument | Scope | Bind |
|---|---|---|
| none | the active initiative (`core.active_initiative` from the config resolved in step-00) | `{scope_flag}` = `--initiative {initiative_dir}` |
| an initiative folder | that initiative | `{scope_flag}` = `--initiative <folder>` |
| an epic folder (`<initiative>/tickets/epic-<slug>`) | that epic alone | `{scope_flag}` = `--epic <folder>` |

A folder is resolved against `{project-root}`, then against `{output_folder}`. With no argument
and no active initiative, or with a folder that does not exist, output:

```
Usage:
  /l3io-execute                      — run the active initiative
  /l3io-execute <initiative folder>  — run one initiative, wave by wave
  /l3io-execute <epic folder>        — run one epic
```

BLOCKED: no initiative to run — name a folder, or set active_initiative.

A parent initiative (one whose `tickets/tickets.toml` lists `[[initiative]]`) is run one child
initiative at a time, in the order `plan-graph.py waves` gives over it; `dispatch-plan.py`
refuses it whole, with exit 2, and says so.

## 2. Start from a clean main checkout

`bmad-build-auto` refuses a dirty tree (`step-01-clarify-and-route.md:60`). First commit
l3io's own project state — hooks that ran since the last commit (Sofia's estimates, an earlier
run's events) may have left it modified — then check:

```bash
uv run {skill-root}/scripts/close-commit.py state --project-root {project-root}
git -C {project-root} status --porcelain
```

If `status` prints anything, the remaining changes are the user's, and they are not ours to
commit or stash:

```
BLOCKED: the working tree is not clean — commit or stash these first: <the paths>
```

## 3. Locate Sofia

The tracker procedures are `bmad-agent-po`'s own (its `board.md`); this run follows them, it
does not reimplement them. Find her skill root:

```bash
for d in "{project-root}/.agents/skills/bmad-agent-po" "{project-root}/.claude/skills/bmad-agent-po" \
         "$HOME/.agents/skills/bmad-agent-po" "$HOME/.claude/skills/bmad-agent-po"; do
  [ -f "$d/SKILL.md" ] && { echo "$d"; break; }
done
```

Bind `{po_root}` to the first directory printed. If none is printed:

```
BLOCKED: bmad-agent-po is not installed — l3io-execute runs Sofia's ticket tree.
```

## 4. Build the run plan

```bash
uv run {skill-root}/scripts/dispatch-plan.py --project-root {project-root} {scope_flag} \
  --max-parallel {max_parallel_subagents}
```

Keep the JSON it prints as `{run_plan}` for the rest of the run. Exit 2 is a usage error and is
reported as printed. Then print a summary, one line each:

```
Store: {store}    Waves: <count>    Gates: <gates, or none>
Worktrees: {parallel.worktrees} — {parallel.reason}
Skipped: <each skipped ref or epic, with its reason>
```

`parallel.reason` matters: a project that does not commit `_bmad/` gets a worktree with no
runnable `_bmad/`, so its epics run one at a time in the main checkout, and the user should
know why the run is serial.

## 5. Ownership

Each epic runs on the branch `l3io/<slug>`. A branch already checked out in another worktree is
another session's run of that epic, or one an earlier run left behind:

```bash
git -C {project-root} worktree list --porcelain
```

For each epic of `{run_plan}`: if its `branch` is listed as checked out anywhere, stop. Never
remove, reset or reuse another worktree — it may hold a build in flight.

```
BLOCKED: {slug} is owned by another session. Its branch l3io/{slug} is checked out at <path>; remove that worktree yourself once nothing runs in it.
```

## 6. Output

```
Step 02 complete — store: {store}, scope: {scope}, waves: <count>, worktrees: {parallel.worktrees}
```
