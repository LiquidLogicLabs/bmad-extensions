## Project Health Check

The default mode — runs when no recognized keyword is passed, or when `check`/`status` is passed. Scans the project and reports what needs attention in a structured table. When not in read-only mode (`check`/`status`), proposes the ordered set of actions and executes them after a single confirmation.

On BMad v7 the work-item tree is v7's: Sofia (`bmad-agent-po`) owns initiatives, epics and
tickets, and l3io keeps only its sidecars beside them and its project-wide files under
`{l3io_state_root}`. Progress and stalls are read through `report` (Check 19), and the
backlog — v7's `{output_folder}/backlog/` — through `scripts/audit-tree.py` (Check 8). A
project still carrying l3io 3.x data is told so by Check 20; the migration itself is
`bmad migrate` (l3io-pm's `migration-1`), not a mode of this skill.

### Step HC1 — Load config

Load config same as described above under On Activation.

### Step HC2 — Scan (16 checks, read-only; Checks 2, 6, 7 and 13 are retired)

Run all checks. They change no project files. Checks 10–14 run `{spec_align}` in its
read-only modes, which write nothing.

**Check 1 — Status file naming**
Does `{implementation_artifacts}/sprint-status-active.yaml` exist?
- Yes → flag `rename-active` · Priority: Critical (must run before `bmad migrate`, whose
  migrations look for `sprint-status.yaml`)
- No → ✓

`rename-active` is an **inline action with no mode file** — Step HC6 performs it. It is a
single rename of a legacy flat file, so it can only fire on a project that still has
`sprint-status-active.yaml`; there is nothing for it to do on a migrated one, and it had no
caller outside this check.

**Check 2 — retired (4.x)**
It counted the pre-v7 state layouts to propose `migrate-state`. The 3.x → 4.x migration is
`bmad migrate` now, and Check 20 reports when it is pending; the number is not reused.

**Check 3 — Deferred code markers**
Run the `bmad-defer:` grep from Harvest Debt Mode (Step H2 grep command). Dedupe against the leaves of v7's backlog (Step H3 logic). Count new (unharvested) markers.
- New markers found → flag `harvest-debt` · Priority: Low · note count
- None or all already harvested → ✓

**Check 4 — AI instruction references**
Run the scan from Update AI Rules Mode Step AR1 across all well-known instruction file locations.
- Stale legacy state references found (flat `sprint-status*.yaml`, the three-file split, or `_bmad/state/`) → flag `update-ai-rules` · Priority: Low · list files
- All current or absent → ✓

**Check 5 — Migration backup files**
Scan `{implementation_artifacts}/` for `*.yaml.legacy` files (e.g., `sprint-status.yaml.legacy`); `{pm_state_root}/` for `*.yaml.v1` calibration backups — that is `{pm_calibration_file}.v1`, the path `pm-status.py`'s calibration v1 → v2 migration derives as `calibration_path(state_root) + ".v1"`, so it is beside the calibration file it came from, **not** under `{project-root}/_bmad/`; `{project-root}/_bmad/` for `pm-calibration.yaml.legacy`; `{project-root}/_bmad/` for the `state.legacy/` and `migration-backup/` backup directories; and `{implementation_artifacts}/state.legacy/`, the 3.x tree the 3.x → 4.x migration set aside (see Clean Legacy Mode's Step CL1 for exactly what each holds and which scan root each lives in).
- Any found → flag `clean-legacy` · Priority: Low · note count (files and directories separately)
- None → ✓

**Check 6 — retired (4.x)**
It padded two-digit `epic-{nn}/` artifact folders so `migrate-state` could pair them with
their state. The 3.x → 4.x migration maps a 3.x key to its v7 ticket, not by folder name; the
number is not reused.

**Check 7 — retired (4.x)**
It found 3.x story nodes whose `fix_iterations` was a string and proposed `redrive`. Both
served the 3.x tree only: v7's samples are written by `build-close` and `epic-close`, which
store the field typed, and the 3.x → 4.x migration carries the calibration file as it is. The
number is not reused.

**Check 8 — Backlog integrity and audit**
Run only if `{output_folder}` holds a `backlog/` directory or any `*/tickets/tickets.toml` —
v7's ticket tree. It is read, never written:

```bash
uv run {skill-root}/scripts/audit-tree.py --project-root {project-root} \
  --output-folder {output_folder} --format json; echo "exit=$?"
```

- exit 4 → flag `triage` · Priority: **High** · note the finding ids. Every finding's repair
  is a proposal for Sofia (`bmad-agent-po`) except `1l` with a named heir, which is
  `pm-status.py sidecar-reconcile` over our own sidecars
- any `fixed-candidate` or `obsolete-candidate` in `markers` → flag `triage` · Priority:
  **Medium** · note the count
- no tree, or exit 0 with no candidates → ✓

**Check 9 — Lock files tracked in git**
`pm-status.py`'s lock files are empty flock targets and must never be committed: in the 3.x
tree, `epic-NNN.lock`, `issues.yaml.lock`, `pm-calibration.yaml.lock` and
`adr-register.yaml.lock` in `{pm_state_root}` and a `.yaml.lock` sidecar beside some node files
below it; on v7, the `*.lock` files beside the project-wide files in `{l3io_state_root}`.
`pm-status.py` keeps `*.lock` in each root's `.gitignore`, but a project that committed them
before that rule existed still tracks them. Run the check only if `{project-root}` is a git work
tree — the first command below prints `true` (outside a repository it exits 128; inside `.git/`
it prints `false`) — and over each of the two roots that exists:

```bash
git -C {project-root} rev-parse --is-inside-work-tree
git -C {project-root} ls-files -- '{pm_state_root}/*.lock' '{l3io_state_root}/*.lock'
```

The explicit `/` keeps each pattern inside its root: the roots are bound without a trailing
slash, and `state*.lock` would also match a sibling such as `state.lock`. A git pathspec `*`
also matches `/`, so the pattern reaches sidecars at any depth.
- Any path listed → flag `untrack-locks` · Priority: **Low** · note the count, and keep the
  list: Step HC3 prints it before HC5 asks
- `ls-files` exits 128 — a root lies outside the repository → report that as Check 9's result
  and skip the check: neither flag it nor mark it ✓
- None listed, neither root exists yet, or not a git work tree → ✓

**Check 10 — ADR home and register**
Run only if `{implementation_artifacts}` exists.

```bash
{spec_align} migrate-adrs --plan
```

- `actionable` non-empty → flag `migrate-adrs` · Priority: **Medium** · note the count, and
  how many are a `collision`
- `duplicates` non-empty → report only, and **do not** propose `migrate-adrs` for them:
  `{n} legacy ADR(s) are leftover duplicates of ADRs already in docs/adr/ (same number and
  slug). migrate-adrs will not move them. Review with diff and delete by hand.`
  Keying the recommendation on `moves` instead of `actionable` pointed already-migrated
  projects — the ones a renumbering run harms — straight at it.
- `register.lagging` is true → report
  `adr-register next {next} ≤ highest ADR on disk {highest_on_disk}`. This is report only:
  the next `adr-reserve` corrects it by itself
- otherwise → ✓

**Check 11 — Spec pointers**
Run only if `{implementation_artifacts}/spec/spec-index.md` exists, meaning the project has
run spec alignment.

```bash
{spec_align} check-pointers --all
```

- exit 1 → report every broken pointer it printed on stderr. This is report only: fix the
  story's `Spec:` line through Sofia's REFINE
- exit 0 → ✓, noting its pre-provenance count

**Check 12 — ADR links**
Run only if `{project-root}/docs/adr/` exists or any
`{implementation_artifacts}/epic-*/arch/adr-*.md` exists — the two homes `check-links` reads.

```bash
{spec_align} check-links
```

- exit 1 → report each ADR it names. This is report only
- exit 0 → ✓

**Check 13 — retired (4.x)**
It reported unconfirmed `spec-change` items of the 3.x issues ledger that later commits had
built on. That ledger, and the spec sync that filed those items, are gone with Task 4.9; the
number is not reused. Phase 5 re-homes the spec sync beside `bmad-retrospective`.

**Check 14 — Spec index freshness**
Run only if the index exists.

```bash
{spec_align} build --check
```

- exit 1 → report `spec index is stale`. This is report only: `{spec_align} build` rebuilds it
- exit 0 → ✓

**Check 15 — BMad dependency resolution**
Every phase this package dispatches resolves against a real skill, or self-skips. A required
dependency that vanished under a project surfaces otherwise as a silently skipped gate
mid-epic — the failure `bmad-deps.py` exists to make visible, and nothing was calling it.

```bash
uv run {skill-root}/scripts/bmad-deps.py verify --project-root {project-root} --format json; echo "exit=$?"
```

- exit 6 → BMad v7 detected, verification degraded · report only · skill probes ran and are
  trustworthy; manifest-derived checks (shipped-skill contradictions) report
  unknown, not agreement, so read neither as drift nor as a pass. A `MISSING` line may be a
  skill BMad removed in v7 rather than a broken install: check it against v7's skill list
  before flagging, and never recommend a 6.12 installer over a v7 tree
- exit 3 → flag · Priority: **Critical** · name every unresolved **required** dependency. A
  required skill that does not resolve will not self-skip; the phase that dispatches it fails
  at the point of use, mid-run
- `baseline_drift` non-empty → report only · the declared inventory disagrees with
  `_bmad/_config/skill-manifest.csv` about what BMad ships. Informational: it means the
  inventory needs re-checking against this BMad version, not that the project is broken
- unresolved **optional** dependencies → report only · name them and the phases that will
  self-skip, so a missing phase later is expected rather than mysterious
- exit 0 and no drift → ✓

**Check 16 — State reachable and tracked**
Two halves. **The v7 half** — `{l3io_state_root}` holds the event log and the calibration
file, both committed: run it only if `{l3io_state_root}` exists, then

```bash
git -C {project-root} check-ignore -q {l3io_state_root}/events.jsonl; echo "exit=$?"
```

- exit 0 → flag · Priority: **High** · git ignores l3io's project-wide state, so no build's
  actuals or calibration samples reach another clone. Report only: the fix is a `.gitignore`
  edit, and which rule is catching it matters
- exit 1, or not a git work tree → ✓

The 3.x half, which probed the 3.x tree `migrate-state` read, is retired with that mode.

**Check 17 — Agent instruction block**
Bind `{runtime}` by the detection procedure in `l3io-execute/steps/shared/step-00-activate.md`
§2, then run:

```bash
uv run {pm_status} sync-agent-instructions --runtime {runtime} \
  --project-root {project-root} --check
```

This is read-only and takes no lock. Act on the exit code, and keep 1 and 2 apart — they are
different findings with opposite remedies:

- Exit 1 (block absent for this harness) → flag · Priority: **Low** · name the file that
  would be written, and say that an agent without it does not know state is machine-written.
  The fix is the block procedure in `assets/module-setup.md` §6, which asks before touching a
  file that exists without markers — so it is **not** in Step HC6's sequence, and is run on
  request after the report
- Exit 2 (ambiguous markers, or the file is not valid UTF-8) → flag for **manual** repair ·
  Priority: **Medium** · print the script's message. **Never offered as a fix and never
  auto-run**: the file is the user's and its markers are already in a state the script refused
  to guess about
- Exit 3 (this harness's block is current, but **another** harness's instruction file holds a
  stale copy of ours) → flag · Priority: **Medium** · print the script's message, which names
  the file and both versions. The fix is the same `sync-agent-instructions --apply` as a
  normal block update — it refreshes the other file's block in place rather than creating or
  removing anything — so this one **is** offered in Step HC6's sequence. Typically a project
  that changed harness: the block stayed where the old harness read it, and a repo carrying
  two l3io blocks at different versions is two sets of instructions, both live, because
  harnesses commonly read more than one of these files
- Exit 0 → ✓
- Any other exit → not a finding; mention the exit code and continue

**Check 18 — pm_status version skew**
BMad v7 installs `pm_status` once per module that declares it — at
`_bmad/l3io-pm/scripts/pm_status/` and `_bmad/l3io-util/scripts/pm_status/` — and both copies
write the same project-wide files. The two modules can be set up separately, so the copies can
carry different versions, and two versions of one writer over one set of files can disagree
about what they write.

```bash
uv run {skill-root}/scripts/report-version.py --project-root {project-root} --format json; echo "exit=$?"
```

- `pm_status.findings` non-empty → flag · Priority: **High** · print each finding as-is; it
  names both paths and both versions. Report only: the remedy is `bmad setup <module-code>` for
  the module whose copy is older, which asks that module's config questions, and those
  answers are the user's
- a copy whose `version` is `null` → not a finding; that module has not been set up, and the
  activation of any skill that needs it halts naming `bmad setup`
- `pm_status.findings` empty → ✓. Exit 3 with no finding is a mixed skill install, which the
  `version` mode reports; it is not this check's finding

**Check 19 — Initiative progress (v7)**
Run only if `{tickets_py}` exists — it is v7's, installed with Sofia. List the initiatives:
every folder under `{output_folder}` holding a `tickets/tickets.toml` beside its `<name>.md`.

```bash
find {output_folder} -mindepth 3 -maxdepth 3 -path '*/tickets/tickets.toml' 2>/dev/null \
  | sed 's#/tickets/tickets.toml$##' | sort
```

For each initiative folder printed:

```bash
uv run {pm_status} report --project-root {project-root} --initiative-dir <initiative> --format json; echo "exit=$?"
```

`report` runs `tickets.py status` itself and joins l3io's sidecars, the event log and the
build spool; it writes nothing without `--out`.

- `stalled_dispatches` non-empty → flag · Priority: **Medium** · for each, name the ticket (or
  plan), the agent and its age. A `build` entry is a `bmad-build`/`bmad-build-auto` run whose
  bracket opened and never closed — the build hung or died before its On Complete ran. Report
  only: whether to re-run the ticket is the user's call
- `problems` non-empty → report only · print each line as `tickets.py` wrote it. The tree is
  v7's; the fix is Sofia's (BOARD, REFINE)
- exit 2 naming a parent initiative → not a finding; its member initiatives are listed
  separately and reported on their own
- any other non-zero exit → report the message as Check 19's result for that initiative and
  continue
- no initiative found, `{tickets_py}` absent, or every initiative clean → ✓

**Check 20 — l3io 3.x data awaiting migration**
Run only if `{project-root}/_bmad/l3io-util/scripts/migrate-engine.py` exists (`bmad setup
l3io-util` installs it). It reads only:

```bash
uv run {project-root}/_bmad/l3io-util/scripts/migrate-engine.py --project-root {project-root} \
  --artifacts {implementation_artifacts} --detect
```

- `layouts` empty → ✓ (no 3.x data, or it was migrated and set aside)
- exit 0 → flag · Priority: **High** · say: `l3io 3.x data is waiting: run bmad migrate and
  choose l3io-pm's migration-1 (3 → 4). Until it runs, no estimate, actual or calibration
  sample from 3.x reaches v7.` Report only — the migration is `bmad migrate`'s, with its own
  plan, approval and verification
- exit 1 with `layouts` non-empty → flag · Priority: **High** · print `reason`. When it says
  method's migration has not run: `run bmad migrate and choose method's migration-1 first;
  l3io-pm's applies once the v7 initiative exists.` Report only

### Step HC3 — Report findings


Print the health check table. Use ✓ for passing checks, ⚠ for flagged items:

```
PROJECT HEALTH CHECK — {project-root}
================================================================
Check                           Status                         Action
----------------------------------------------------------------
Status file naming              ⚠ sprint-status-active.yaml    rename-active
Deferred code markers           ⚠ 2 new marker(s)              harvest-debt
AI instruction references       ✓ Current                      —
Migration backup files          ⚠ 1 .legacy file found         clean-legacy
Backlog integrity & audit       ⚠ 1 integrity, 4 candidate(s)  triage
Tracked lock files              ⚠ 3 *.lock tracked in git      untrack-locks
ADR home & register             ⚠ 2 ADR(s) in epic-*/arch/     migrate-adrs
Spec pointers                   ⚠ 1 broken pointer             — (report only)
ADR links                       ⚠ 1 unlinked departure         — (report only)
Spec index freshness            ✓ Fresh                        —
BMad dependencies               ✓ all resolve                  —
l3io state tracked              ✓ committed                    —
Agent instruction block         ⚠ absent in CLAUDE.md          — (on request)
pm_status version skew          ✓ both copies 4.0.0            —
Initiative progress (v7)        ⚠ 1 stalled build              — (report only)
3.x data awaiting migration     ⚠ 3.x tree present             — (bmad migrate)
================================================================
```

If flagged items exist, append the recommended execution sequence (only flagged actions shown, in priority order):
```
Recommended actions (in order): rename-active → harvest-debt → triage
```

If `untrack-locks` is flagged, print Check 9's `ls-files` list under the table — every path
the action would untrack. That is this action's dry run, shown before HC5 asks, as every other
action's dry-run output is.

If nothing is flagged:
```
✓ Project is healthy — no actions needed.
```

### Step HC4 — Exit if read-only

If invoked with `check` or `status`: print the report above and exit. No further steps.

### Step HC5 — Propose and confirm

If no items are flagged: print "✓ Nothing to do." and exit.

Otherwise ask:
```
Run {N} recommended action(s) in sequence?
  Y — run all ({action_list})
  n — exit, no changes
```

If `n`: print "Exiting — no changes made." and exit.

### Step HC6 — Execute in order

Run each approved action in this fixed priority sequence (skip any that were not flagged):

1. `rename-active` (inline — see below)
2. `harvest-debt`
3. `migrate-adrs`
4. `triage`
5. `update-ai-rules`
6. `untrack-locks`
7. `clean-legacy`

`migrate-adrs` runs before `triage` so that ADR paths a backlog ticket cites are already the new
ones when triage reads them. It keeps its own plan and confirmation (Step MA2), like `triage`
does, because it commits.

Before each action, print a separator header:
```
─── Running: {action-name} ──────────────────────────────────
```

Each action runs its full mode implementation from its own section. **Suppress the per-mode confirmation prompts** — the user already confirmed in HC5; proceed as if they answered yes at each mode's own confirm step. The per-mode dry-run output and verify steps still run and are shown.

**`triage` keeps its own confirmations here.** The rule above does not apply to it: its only write (`sidecar-reconcile`) and every proposal it hands Sofia are per finding, which the HC5 yes did not see item by item. It runs right after `harvest-debt`, so markers harvested in the same run are audited too.

**`migrate-adrs` keeps its own confirmation too** — it moves files and commits.

**`rename-active` (Check 1) has no mode file — run it here, inline.** It is one rename of a
legacy flat file. Re-check the precondition first rather than trusting Check 1's earlier
result, because an action run before this one may have changed the tree:

- If `{implementation_artifacts}/sprint-status-active.yaml` does not exist → nothing to
  rename; skip.
- If `{implementation_artifacts}/sprint-status.yaml` already exists → **conflict**. Do not
  rename and do not overwrite; print
  `Conflict: sprint-status.yaml already exists at {implementation_artifacts}. Cannot rename
  sprint-status-active.yaml — resolve manually (remove or merge the existing file first).`
  and treat this action as failed, per the stop-on-failure rule below.

Otherwise print the one-line dry run
(`Will rename: {implementation_artifacts}/sprint-status-active.yaml →
{implementation_artifacts}/sprint-status.yaml — content unchanged, filename only`), rename,
then re-parse `sprint-status.yaml` as YAML. If it does not parse, rename it back to
`sprint-status-active.yaml` and report
`FAILED — sprint-status.yaml is not valid YAML after rename. Restored. Parse error: {error}`.

**`untrack-locks` (Check 9) has no mode file — run it here, inline.** For each root Check 9
listed a path under (`{pm_state_root}`, `{l3io_state_root}`), first make sure its
`.gitignore` contains a `*.lock` line: create the file with that line if it is absent, or
append the line if it is missing, never rewriting or reordering the lines already there. Then
untrack the lock files Step HC3 listed, leaving them on disk:

```bash
git -C {project-root} rm -r --cached --quiet --ignore-unmatch -- '{pm_state_root}/*.lock' '{l3io_state_root}/*.lock'
```

This stages the removal for the user's next commit; it does not commit. It runs after every
action that invokes `pm-status.py` (and so may create lock files), and before `clean-legacy`,
the fixed final tidy-up.

If any action fails (exits with FAILED), stop and report — do not run remaining actions.

### Step HC7 — Final summary

```
HEALTH CHECK COMPLETE
================================================================
  Ran:     {comma-separated list with ✓ or ✗ per action}
  Clean:   {comma-separated list of checks that passed with ✓}
================================================================
{overall status line}
```

If all actions succeeded: "Project is now healthy."
If any action failed: "One or more actions failed — see output above for details."

---
