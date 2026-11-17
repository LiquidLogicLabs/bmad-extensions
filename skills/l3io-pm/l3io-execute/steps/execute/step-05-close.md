# Step 05: Close each epic, merge it, and stop at gates

`{epic}` is the epic's object from `{run_plan}`, and §1 and §2 run where its builds ran (its
own session in its worktree, or here). Its closing steps are `{epic.close}`, in order.

## 1. Retrospective (`close-epic`)

Record when it starts, then run the retrospective headless on this epic alone:

```bash
since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```

Invoke `bmad-retrospective` with the step's `invocation`, `-H <slug>`, and tell it: "This
retrospective began at `<since>`; pass `--since <since>` to l3io's epic-close command." Its On
Complete hook runs l3io's `epic-close`, which records the epic's actuals and the closure's
spend over that window and commits l3io's own files. The window is unambiguous because this
session ran only this epic, its builds one at a time, and then this retrospective.

The retrospective commits nothing of its own (`retro-document.md:39`), so its document is still
uncommitted, and the next `bmad-build-auto` would refuse the tree. Commit it now with the
step's `commit` command:

```bash
uv run {skill-root}/scripts/close-commit.py retro --project-root {epic.root} --retro-file <retro_file>
```

It prints `{"epic", "verdict", "committed"}`; bind `{verdict}`. Exit 2 means the document has
no recognisable verdict; report it, and treat the epic as rejected.

## 2. Status (`status-done`)

Only an accepted verdict (`accepted` or `accepted-with-open-items`) moves tickets to `done`.
On `rejected`, the tickets stay `built`, and this epic stops:

```
BLOCKED: the retrospective of {slug} is rejected — <its document's path>. Its tickets stay built.
```

On an accepted verdict, run each `status-done` step:

- **Repo store** (the step has a `command`): run the `command`, then its `commit`. The command is
  v7's own status write, which writes only the ticket's plan; the commit records it, so the tree
  stays clean.
- **Tracker store** (the step has `store_write`): follow **Status** in
  `{po_root}/references/board.md` — the store's `write` to `[tickets.status].done`, then
  mirror — then run the step's `next`. Never write a plan's status on a tracker.

The epic then ends with `DONE — {slug}: <n> built, verdict {verdict}`.

## 3. Merge (`merge`), in the main checkout

For each epic that ended `DONE`, in the orchestrator:

1. Run the step's `state_commit`. Builds in a worktree commit their ticket sidecars there, but
   the project-wide events log and calibration file live in the main checkout; this commits
   them, and only them.
2. Merge the epic's branch into `{base}`:

   ```bash
   git -C {project-root} switch {base}
   git -C {project-root} merge --no-ff {branch} -m "merge {branch}"
   ```

3. With a worktree, remove it and the merged branch: `git -C {project-root} worktree remove
   {worktree}`, then `git -C {project-root} branch -d {branch}`.

On a merge conflict, abort the merge (`git merge --abort`), leave the branch and its worktree,
and stop the run:

```
BLOCKED: merging l3io/{slug} into {base} conflicts: <the paths>
```

## 4. Gates

`{run_plan}.gates` lists the epics a later wave waits on for **closure**: a ticket's or an epic
file's own `after` names them, and `tickets.py` holds the dependent until the epic container
itself reads `done` (`tickets.py:584-590`). A container's status is Sofia's to set, on the
user's confirmation (`board.md`, Status). An epic that a later wave only follows, through an
`[[epic]] after` declaration, gates nothing: its tickets being built is all the next wave
needs, and the run goes straight on.

After a wave is merged, for each slug in that wave's `pause_after`, stop and ask:

```
⏸  {slug} is closed: verdict {verdict}, retrospective <path>.
   <dependent epics> wait for it to be done. Close the epic in Sofia (bmad-agent-po, BOARD)
   if you accept it, then tell me to continue.
```

On "continue", run `{run_plan}.next` again and check that the epic's row in
`tickets.py status` reads `done`. If it does not, stop:

```
BLOCKED: {slug} gates the next wave and is not done — close it in Sofia, then run /l3io-execute again.
```

## 5. End of the run

After the last wave, or when the run stops, commit l3io's project state once more, then show
the main checkout is clean:

```bash
uv run {skill-root}/scripts/close-commit.py state --project-root {project-root}
git -C {project-root} status --porcelain
```

Then report: per epic, its tickets built, its verdict and whether it merged; the epics blocked
and why; and `uv run {pm_status} report --project-root {project-root} --initiative-dir
{run_plan.initiative}` for the actuals.

The epic architecture gate and the write-back of accepted spec departures are not part of this
run: an epic design review belongs with `bmad-architecture`, and decision records with
`bmad-retrospective`'s own.

## 6. Output

```
Step 05 complete — closed: <slugs>; merged: <slugs>; blocked: <slugs, or none>
```
