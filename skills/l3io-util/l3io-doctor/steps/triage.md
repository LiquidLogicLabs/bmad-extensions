## Triage Mode

Invoked with the `triage` argument. Audits the backlog on BMad v7's tree and proposes what to
close or repair — with evidence, and only on confirmation. On 4.x the backlog is v7's: the
leaves in `{output_folder}/backlog/` (`bug-<slug>.md`, and any story or spike filed there),
each with its state in the plan beside it, and the epics' `tickets.toml` entries. **Sofia
(`bmad-agent-po`) owns every one of those files**, so closing a ticket, moving it into an
epic or fixing its frontmatter is hers: triage hands her the proposals. The only files triage
itself changes are l3io's own sidecars, through `pm-status.py sidecar-reconcile`. All
[Safety Rules](`SKILL.md` § Safety Rules) apply: nothing is written without a yes, and
nothing uncertain is closed.

It runs two passes: the structural audit and the marker evidence (`scripts/audit-tree.py`,
read-only), then an optional agent review of whatever the evidence could not decide.

### Step T1 — Load config

Load config (as under On Activation in `SKILL.md`). Bind
`{triage_session}` — `triage-{UTC timestamp, e.g. 20260910T153000Z}`.

**Precondition.** If `{output_folder}` holds no `backlog/` directory and no
`*/tickets/tickets.toml`, print `No ticket tree under {output_folder} — nothing to triage.`
and exit.

### Step T2 — Audit

```bash
uv run {skill-root}/scripts/audit-tree.py --project-root {project-root} \
  --output-folder {output_folder} --format json; echo "exit=$?"
```

It writes nothing. Exit `0` → print `✓ Backlog integrity: no findings` and go to T3. Exit `4`
→ print every finding (`id`, `path`, `detail`) with its `repair`. The findings are the 3.x
audit's, re-expressed over v7's tree; four 3.x findings (1a, 1e, 1g, 1j) have no v7 meaning
and are never reported:

| Finding | What it means on v7 | Repair (`repair` field) |
|---|---|---|
| `1b` | an `[entry.<id>]` estimate in an epic's `l3io.toml` that its `tickets.toml` no longer holds — a `tickets.py move` nobody reconciled | report only: `sidecar-reconcile --moved-json` with the move's output if it was kept, else Sofia's REPLAN re-estimates |
| `1c` | a backlog ticket whose plan reads `built` but not `done` | Sofia's BOARD `mark <ticket> done`, on its owner's word |
| `1d` | a backlog leaf whose `parent` names an epic, still sitting in `backlog/` | Sofia's BOARD `move` into that epic, or clear its parent |
| `1f` | a plan status v7 does not know | report only: Sofia sets it through BOARD |
| `1h` | two plans joining one ticket | report only: remove the stale plan by hand |
| `1i` | two leaves in one folder carrying one `id`, or two `tickets.toml` entries with one id | report only: Sofia's REFINE renumbers one |
| `1k` | a leaf whose `type` is not `story`/`spike`/`bug`, a bug whose `severity` is not `P0`–`P3`, or unparseable frontmatter | report only: Sofia's REFINE |
| `1l` | a plan sidecar `<stem>-plan.l3io.toml` whose plan is gone | with exactly one same-named plan elsewhere: `uv run {pm_status} sidecar-reconcile --project-root {project-root} --initiative-dir <initiative>`, which moves it beside that plan; otherwise report only |

Only `1l` with a named heir is ours to run. Ask
`Run sidecar-reconcile for {n} initiative(s)? (y/n)`, run the confirmed ones (each commits
what it moved as `chore(l3io): reconcile sidecars`), then rerun the audit and report what
remains. Gather every other repair into the **Proposals for Sofia** list printed in T5.

### Step T3 — Marker evidence

From the same JSON, the `markers` list: one verdict per backlog leaf that cites a
`code-marker (<file>:<line>)` — the reference `harvest-debt` writes into its candidates.

- `open` — the `bmad-defer:` marker is still in the source; list it as information.
- `fixed-candidate` — the file has no `bmad-defer:` line carrying the ticket's title. Find
  the commit that removed it: `git -C {project-root} log -n1 --format=%h -S "{title}" -- {file}`.
- `obsolete-candidate` — the file no longer exists.

Table the candidates with their `evidence` and add them to the **Proposals for Sofia** list:
a fixed one is closed with BOARD `mark <ticket> done` citing the commit; an obsolete one is
dropped with BOARD `mark <ticket> dropped` citing the evidence.

### Step T4 — Agent review (optional; costs tokens)

Count the open backlog leaves that neither T2 nor T3 decided. Ask:

```
{n} ticket(s) need a reviewer to check them against the current code
→ {ceil(n / 8)} spawn(s). Run? (y/n)
```

Spawn nothing without a yes. Batch at most 8 tickets per spawn, and bracket each spawn:

```bash
uv run {pm_status} dispatch --state-root {l3io_state_root} --event open \
  --agent l3io-util-triage --session-id {triage_session}
# ... spawn ...
uv run {pm_status} dispatch --state-root {l3io_state_root} --event close \
  --agent l3io-util-triage --session-id {triage_session}
```

Send this prompt verbatim, filling in the ticket lines:

```
You are checking whether recorded defects are already fixed in the current code.
Read-only: do not edit, create, or delete any file, and run no git write command.
For each ticket, read its file, then inspect the current code it concerns. Answer with
exactly one JSON object per ticket, one per line:
{"ticket": "<file stem>", "verdict": "fixed" | "still-present" | "can't-tell", "evidence": "<file:line> — <one sentence>"}
A "fixed" verdict MUST cite file:line evidence showing the fix. If you cannot find the code
the ticket describes, answer "can't-tell".
Tickets (file | severity | title):
{one line per ticket}
```

Treat a `fixed` verdict whose `evidence` has no `file:line` as `can't-tell`. Add each `fixed`
verdict to the **Proposals for Sofia** list with its evidence; the rest stay open.

### Step T5 — Proposals for Sofia and summary

Print the proposals, one per line, as the request to make of Sofia — for example
`BOARD: mark bug-linear-scan-in-cache done — fixed by 3f9c2a1 (marker removed from src/cache.py)`.
**Do not run `tickets.py mark`, `move` or any edit of a leaf, plan or `tickets.toml`
yourself**: on a tracker store `mark` is refused outright, and on any store the state
belongs to Sofia's procedures. Then:

```
BACKLOG TRIAGE — {output_folder}
================================================================
  Findings:            {n}  ({finding ids})
  Sidecars reconciled: {n}
  Marker verdicts:     open {o} · fixed {f} · obsolete {b}
  Agent verdicts:      fixed {a} · still present {s} · can't tell {c}
  Proposals for Sofia: {n}
================================================================
```

---
