## Stats Mode

Invoked with the `stats` argument, or with its aliases `backlog` / `issues`. Read-only
progress dashboard over BMad v7's work-item tree — renders each initiative's epics and tickets
via `pm-status.py report`, then appends the backlog and calibration sections that `report`
does not cover. No files are changed.

**The backlog is v7's** (4.x): the leaves in `{output_folder}/backlog/` — `bug-<slug>.md` and
any story or spike filed there — with their state in the plan beside each. Sofia
(`bmad-agent-po`) files and closes them; l3io only reads them. **One `tickets.py status` call
serves both views**: Step ST3 counts from it and Step ST4 prints its rows. Under the
`backlog`/`issues` alias the per-item table is always printed; under `stats` it is printed
whenever there is at least one ticket not `done` or `dropped`.

### Steps

**Step ST1 — Load config and find the initiatives**

Load config same as described under On Activation in `SKILL.md`.

The work-item tree is v7's: Sofia (`bmad-agent-po`) owns it, and `{tickets_py}` is the script
v7 installs with her. If `{tickets_py}` does not exist, there is no tree to report on — print
`Sofia (bmad-agent-po) is not set up in this project — no initiatives to report on.` in place
of Step ST2's output and continue with Step ST3.

Which initiatives:

- The user named an initiative folder: that one, resolved against `{project-root}`, then
  against `{output_folder}`.
- None named: every initiative under `{output_folder}` — each folder holding a
  `tickets/tickets.toml` beside its `<name>.md`:
  ```bash
  find {output_folder} -mindepth 3 -maxdepth 3 -path '*/tickets/tickets.toml' 2>/dev/null \
    | sed 's#/tickets/tickets.toml$##' | sort
  ```
- None found → print `No initiatives under {output_folder} — nothing to report.` in place of
  Step ST2's output and continue with Step ST3.

An epic folder (`<initiative>/tickets/epic-<slug>`) has no report of its own: say so and use
the initiative that holds it.

**Step ST2 — Progress per initiative**

Do not walk the tree by hand. `tickets.py` is the only reader of v7's tree and `pm-status.py`
the only reader of l3io's sidecars; a second walk here would drift from both. For each
initiative:

```bash
uv run {pm_status} report --project-root {project-root} --initiative-dir <initiative> --format tree
```

This is read-only: `report` writes only when `--out` is passed, and it is not passed here. It
runs `tickets.py status` itself, then joins each ticket's estimate and actual from l3io's
sidecars and the open build brackets from the spool under `{l3io_state_root}`. Print each
output verbatim — re-rendering it by hand would drift from the tool's own view. It lists every
epic with its status, lane and built count, the tickets not yet `done`, totals, actual spend,
and any `Problems (tickets.py)` or `STALLED BUILD` block.

- **Exit 2 naming a parent initiative** → its member initiatives are reported on their own;
  skip it without a message when the member list was discovered above, and when the user named
  it, report each initiative its `tickets/tickets.toml` lists.
- **Any other non-zero exit** → print the message under that initiative's heading and continue
  with the next one.

**Three follow-ups on the tree output, only when it warrants them:**

- Always append a live-view pointer, because that is what answers "what is happening right
  now" during a run:
  ```
  For a live view during a run: uv run {pm_status} report --project-root {project-root} \
    --initiative-dir <initiative> --watch 15
  ```
- If the tree contains `STALLED BUILD`, add for each entry: `{ticket} has had a build open for
  {N}m with no close — the run hung or died before its On Complete ran. Check that session;
  re-running the ticket is your call.` Do not re-derive stall state yourself — the report
  already computed it against `--stall-minutes` (default 15).
- If the tree contains `Problems (tickets.py)`, add: `These are v7's findings over its own tree;
  Sofia's BOARD and REFINE fix them.`

**Step ST3 — Backlog, calibration and layout**

`report` does not cover these. Read them directly.

- **Backlog** — only if `{tickets_py}` exists and `{output_folder}/backlog/` is a directory;
  otherwise every count is zero:
  `uv run {tickets_py} status {output_folder}/backlog`. Count its `tickets` rows by `type`
  (`bug`, `story`, `spike`) and by `state` (`backlog`, `in-progress`, `review`, `done`,
  `dropped`). **Keep the rows themselves, not only the counts** — Step ST4 prints them from
  this same call. A non-zero exit is v7's finding over its own tree: print its message in
  place of the counts and say `Sofia's BOARD and REFINE fix it; /l3io-doctor triage lists
  what l3io can see.`
- **Calibration** — if `{l3io_state_root}/pm-calibration.yaml` exists:
  `uv run {pm_status} calibration show --state-root {l3io_state_root} --format json`; note its
  version and the number of samples per component.
- **3.x state tree** — whether `{pm_state_root}` exists. It is read only by `migrate-state`.

Append:

```
----------------------------------------------------------------
Backlog ({output_folder}/backlog)
  bug: {n}  story: {n}  spike: {n}  total: {n}
  backlog: {n}  in-progress: {n}  review: {n}  done: {n}  dropped: {n}
Calibration file:    {version}, {n} samples  (or "not found")
3.x state tree:      present at {pm_state_root}, read only by migrate-state  (or "none")
================================================================
```

**Step ST4 — Per-item backlog table**

From the rows Step ST3 already read — no second `tickets.py` call. Print this when the
argument was `backlog`/`issues`, or when `stats` found at least one ticket not `done` or
`dropped`. Leave out `done` and `dropped` rows. Sort by `state` (`in-progress`, `review`,
`backlog`), then by `file`:

```
----------------------------------------------------------------
BACKLOG — {output_folder}/backlog
Type   Ticket                               State        Title
----------------------------------------------------------------
bug    bug-checkout-total-ignores-codes     in-progress  {title}
bug    bug-linear-scan-in-cache             backlog      {title}
----------------------------------------------------------------
Run /l3io-doctor triage to audit these; Sofia (bmad-agent-po) closes them.
```

Truncate titles at 50 characters with `…`. With no open ticket, print
`Backlog is empty — no open tickets.` in place of the table.

---
