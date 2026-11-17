## Stats Mode

Invoked with the `stats` argument, or with its aliases `backlog` / `issues`. Read-only
progress dashboard over BMad v7's work-item tree — renders each initiative's epics and tickets
via `pm-status.py report`, then appends the backlog and calibration sections that `report`
does not cover. No files are changed.

**One `list-issues` call serves both views.** Step ST3 already reads the whole backlog
(`--all`) to produce the counts, so the per-item table in Step ST4 costs nothing extra. Under
the `backlog`/`issues` alias the per-item table is always printed; under `stats` it is printed
whenever there is at least one open item.

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

- **Backlog items** — only if `{pm_state_root}` exists; otherwise every count is zero. If more
  than one pre-v7 layout is present (the multi-layout condition of Check 2 in
  `steps/health-check.md` — keep the two in sync), print `Backlog: not read — more than one
  state layout is present. Run /l3io-doctor migrate-state first.` and skip this bullet.
  Otherwise:
  `uv run {pm_status} list-issues --state-root {pm_state_root} --all --format json`: count
  `open` by severity (Critical, High, Medium, Low, unknown) and by status (untriaged =
  `backlog`, `scheduled`) plus `origin_archived`; count `resolved` by `resolution`. An absent
  file = zero items, not an error. **Keep the `open` records themselves, not only the
  counts** — Step ST4 prints them per item from this same call; do not make a second
  `list-issues` call for it.
- **Calibration** — if `{l3io_state_root}/pm-calibration.yaml` exists:
  `uv run {pm_status} calibration show --state-root {l3io_state_root} --format json`; note its
  version and the number of samples per component.
- **3.x state tree** — whether `{pm_state_root}` exists. It is read only by `migrate-state`.

Append:

```
----------------------------------------------------------------
Backlog items
  Critical: {n}  High: {n}  Medium: {n}  Low: {n}  total: {n}
  untriaged: {n}  scheduled: {n}  origin archived: {n}
  resolved: {n}  (fixed {n} · wontfix {n} · duplicate {n} · obsolete {n})
Calibration file:    {version}, {n} samples  (or "not found")
3.x state tree:      present at {pm_state_root}, read only by migrate-state  (or "none")
================================================================
```

**Step ST4 — Per-item backlog table**

From the `open` records Step ST3 already read — no second `list-issues` call. Print this when
the argument was `backlog`/`issues`, or when `stats` found at least one open item. Group by
severity (Critical → High → Medium → Low → unknown); within a group sort by `epic` then `key`.
`scheduled` items show the story they are scheduled into; `origin_archived` items are marked.
Each item carries a `kind` — `defect` (the default, and what an absent field means) plus
`spec-change` and `spec-proposal`, which `triage`'s spec pass resolves:

```
----------------------------------------------------------------
BACKLOG — {pm_issues_file}
Sev    Key           Epic  Sprint  Kind        Status              Title
----------------------------------------------------------------
High
  HIGH   BL-E001-002   001   —       defect      scheduled E003-S02-004  {title}
Low
  LOW    BL-E002-001   002   03      spec-change backlog (archived)      {title}
----------------------------------------------------------------
Run /l3io-doctor triage to audit these and close what is already fixed.
```

Truncate titles at 50 characters with `…`. Show the sprint as `—` when blank. With no open
items, print `Backlog is empty — no open items.` in place of the table.

---
