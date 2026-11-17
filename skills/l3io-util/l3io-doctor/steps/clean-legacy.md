## Clean Legacy Mode

Invoked with `clean-legacy` argument. Removes migration backup files *and directories* left
behind by one-time migrations: the `.legacy` sources the 3.x → 4.x migration (`bmad migrate`,
l3io-pm's `migration-1`) sets aside after verifying them — `{implementation_artifacts}/state.legacy/`,
`.yaml.legacy` flat files, `_bmad/state.legacy/` — the `.v1` calibration schema backup, and the
`pm-calibration.yaml.legacy` file and `migration-backup/` directory an older `migrate-state`
left. Dry-run first; confirms before deleting. Safe to run once migrations have been verified.

### Steps

**Step CL1 — Load config and scan**

Load config (as under On Activation in `SKILL.md`). Scan for:
1. `*.legacy` files anywhere under `{implementation_artifacts}/` (e.g.,
   `sprint-status.yaml.legacy`, `sprint-status-backlog.yaml.legacy`,
   `sprint-status-archived.yaml.legacy`) — flat sources set aside by a migration, outside the
   `state.legacy/` directory of item 6.
2. `{pm_calibration_file}.v1` (i.e. `{pm_state_root}/pm-calibration.yaml.v1`) — the
   calibration schema v1 → v2 backup. **Derive this path from `{pm_calibration_file}`, never
   type a second literal**: `pm-status.py`'s `migrate_calibration` writes it as
   `calibration_path(state_root) + ".v1"`, so it always lands beside the live calibration
   file in the state root and follows it if that location ever moves. Scan `{pm_state_root}/`
   for `*.yaml.v1` **and `*.yaml.pre-redrive`** so a backup from any calibration schema
   bump, and the one the retired `redrive` mode wrote, are swept by the same pass.
3. `{project-root}/_bmad/pm-calibration.yaml.legacy` (file) — a pre-migration calibration
   backup, at its original location.
4. `{project-root}/_bmad/state.legacy/` (directory) — a legacy per-epic `_bmad/state/`
   source set aside by a migration, at its original location.
5. `{project-root}/_bmad/migration-backup/` (directory) — an older `migrate-state`'s default
   "move" destination. When present it already holds copies of some/all of items 1, 3, and 4
   (the flat `.legacy` files, `pm-calibration.yaml.legacy`, and `state.legacy/`), relocated
   there in one pass by F2. Treat it as a single item in the scan and report — do not also
   descend into it and list its contents as separate items. Items 1/3/4 above only match
   files/directories at their *original* `_bmad/`-or-`{implementation_artifacts}/` locations,
   so there is no double-counting: a repo that ran F2 with "M" has items 1/3/4 empty and item
   5 present; a repo that chose "K" has items 1/3/4 present and item 5 absent.
6. `{implementation_artifacts}/state.legacy/` (directory) — the 3.x sharded tree the 3.x → 4.x
   migration renamed aside once every datum verified in its v7 sidecars. Treat it as one item;
   its `.v1` or `.lock` files are inside it, not separate items.

If nothing found: print `No legacy backup files or directories found — nothing to clean.` and exit.

**Step CL2 — Dry-run**

For each plain file, get its size (`stat`/`du -h`). For each directory (items 4, 5 and 6), get
its total recursive size (`du -sh`) and a one-line content summary — top-level entry names
plus a recursive file count — so the user sees what is inside *before* agreeing to remove it:

```
CLEAN LEGACY DRY RUN
================================================================
File / Directory                                         Size     Contents
----------------------------------------------------------------
{implementation_artifacts}/sprint-status.yaml.legacy      {size}   —
{pm_state_root}/pm-calibration.yaml.v1                    {size}   —
{project-root}/_bmad/pm-calibration.yaml.legacy             {size}   —
{project-root}/_bmad/state.legacy/                          {size}   DIR — {n} files (epic-001/, epic-002/, ...)
{project-root}/_bmad/migration-backup/                       {size}   DIR — {n} files (sprint-status.yaml.legacy, state.legacy/, pm-calibration.yaml.legacy)
{implementation_artifacts}/state.legacy/                    {size}   DIR — {n} files (active/, planned/, archived/, ...)
...
================================================================
{N} file(s) and {M} director(y/ies) to remove. These are migration backups — the live files
are unaffected.
```

**Step CL3 — Confirm**

Ask: "Remove {N} backup file(s) and {M} backup director(y/ies)? This cannot be undone."

If no: print `Clean cancelled — nothing removed.` and exit.

**Step CL4 — Delete**

Delete each file with `rm -f`. Remove each directory with `rm -rf` **only after** its
contents were shown in the Step CL2 dry-run and the user confirmed in Step CL3 — never
remove a directory whose contents the user has not seen. Log each removal individually. If
any removal fails (permissions, locked file), record and continue — do not abort the entire
run.

**Step CL5 — Report**

```
DONE — Clean legacy complete.
  Removed: {n} file(s), {m} director(y/ies)
  Failed:  {n} file(s)/director(y/ies) (list if > 0)
```

---
