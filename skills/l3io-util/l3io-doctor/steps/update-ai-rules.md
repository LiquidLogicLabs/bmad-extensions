## Update AI Rules Mode

Invoked with `update-ai-rules` argument. Scans for AI system instruction files in the project and updates any references to a **legacy** state layout — the flat `sprint-status*.yaml` files, the legacy per-epic `_bmad/state/` tree, or the 3.x sharded tree under `{pm_state_root}` — so they describe the **current layout on BMad v7**: v7's ticket tree under `{output_folder}`, l3io's sidecars beside it, and l3io's project-wide files under `{l3io_state_root}`. For instruction files that already exist: updates existing references. For the currently running AI system's file that does not yet exist: creates it with a state layout section. Never creates instruction files for other AI systems. Safe to run repeatedly — already-updated files are skipped.

**This mode writes into the consuming repo's own instruction files, and those files then
steer every future agent in that repo.** It must therefore only ever emit the current
layout. Emitting the decommissioned three-file layout here would teach every agent in the
consuming repo to look for files the PM skills hard-block on.

### Supported AI instruction file locations

| AI System | Instruction file |
|---|---|
| Claude Code | `{project-root}/CLAUDE.md` |
| GitHub Copilot | `{project-root}/.github/copilot-instructions.md` |
| Google Gemini | `{project-root}/GEMINI.md` |
| Generic agents | `{project-root}/AGENTS.md` |
| Cursor | `{project-root}/.cursorrules` or `{project-root}/cursor.md` |
| Cline | `{project-root}/.clinerules` or `{project-root}/CLINE.md` |

### Detection rule

A reference is flagged for update if it names any legacy state location — `sprint-status.yaml`, `sprint-status-backlog.yaml`, `sprint-status-archived.yaml`, `sprint-status-planned.yaml`, `sprint-status-issues.yaml`, `E{nnn}-status.yaml`, `_bmad/state/`, the 3.x sharded tree (`state/active/`, `state/planned/`, `state/archived/`) or its backlog (`issues.yaml`, `issues-resolved.yaml`) — and is NOT immediately followed by `.legacy`. A reference is already current, and skipped, when its paragraph or section describes the v7 layout (mentions `tickets.toml`, `l3io.toml` or `{l3io_state_root}`).

Note the direction of travel: the three-file split and the 3.x sharded tree are themselves **legacy** layouts now and are flagged for update, not treated as the target.

### Steps

**Step AR1 — Scan**

Check each well-known instruction file location. For each file that exists, grep for `sprint-status[-a-z]*\.yaml`, `E[0-9]*-status\.yaml`, `_bmad/state`, `state/(active|planned|archived)/` and `issues(-resolved)?\.yaml` (case-sensitive) and collect all matches with surrounding context (2 lines before/after). Apply the detection rule. Build a findings list: `{file}` + `{line}` + `{context}`.

Also determine the current AI runtime (Claude, Copilot, Gemini, etc.) from execution context. If the current runtime's instruction file does not exist and was not found above, add it to a `{to_create}` list.

If no existing instruction files found AND `{to_create}` is empty: print `No AI instruction files found — nothing to update.` and exit.

If existing files found but no flagged references AND `{to_create}` is empty: print `AI instruction files are already current — no legacy state-layout references detected.` listing files checked, and exit.

**Step AR2 — Dry-run**

```
AI RULES DRY RUN
================================================================
Existing files to update:
  File                                  Line   Current reference
  ─────────────────────────────────────────────────────────────
  CLAUDE.md                              42    sprint-status.yaml
  .github/copilot-instructions.md        17    _bmad-output/sprint-status.yaml

Files to create (current AI runtime):
  {file} — new section: PM state file layout

Files checked (no changes needed):
  {files_with_no_hits}
================================================================
{N} reference(s) to update across {M} existing file(s). {C} file(s) to create.
```

**Step AR3 — Confirm**

Ask: "Update {N} reference(s) in {M} file(s) and create {C} new file(s)?"

If no: print `Update cancelled — no changes made.` and exit.

**Step AR4 — Apply updates to existing files**

For each file in the findings list, read the full content. For each flagged reference, construct a contextually appropriate replacement:

- **Inline path** (e.g., `some/path/sprint-status.yaml`): replace the path with `{output_folder}` (rendered as the project's actual relative path, e.g. `_bmad-output/`) and append ` (BMad v7's ticket tree — Sofia's; l3io's sidecars sit beside it)`. A path naming the backlog (`issues.yaml`) becomes `{output_folder}/backlog/`.
- **Standalone keyword** (e.g., "reads sprint-status.yaml"): replace with a brief description: "BMad v7's ticket tree under `{output_folder}` — initiatives, epics and tickets, owned by Sofia (`bmad-agent-po`) — with l3io's `l3io.toml` sidecars beside it".
- **Section or block** describing the state files: replace the entire description block with the state layout section from Step AR5 below, preserving surrounding format.

Read 3 lines of surrounding context before choosing the replacement strategy. Write the updated content to disk.

**Step AR5 — Create the current runtime's instruction file**

For each entry in `{to_create}` — the list AR1 built, and only that list — create the file at
the path the *Supported AI instruction file locations* table gives for that AI system, and
write a minimal section covering the PM state file layout. `{to_create}` holds at most one
entry: AR1 adds the current runtime's file, and only when that file does not already exist.
So on Claude the file created is `{project-root}/CLAUDE.md`, on Copilot
`{project-root}/.github/copilot-instructions.md`, on Gemini `{project-root}/GEMINI.md`, and
`{project-root}/AGENTS.md` only when the runtime is a generic agent.

**Never create an instruction file for an AI system that is not the one running.** The other
half of this rule lives in `pm-status.py`'s `sync-agent-instructions`, which applies it to the
marker-wrapped l3io block rather than to this migration — and which additionally *refreshes* a
block already present in another harness's file, because that block is ours and a stale copy
of our own instructions is not neutrality. Same rule, two mechanisms, and it must change in
both: it was argued correctly here for a long time while the block side was silently missing
the refresh half. A rule argued in the mechanism that happened to need it first does not
propagate itself.

This step
used to say "always target `AGENTS.md` regardless of which AI system is running", which
contradicted this mode's own summary, `SKILL.md`, and the `{to_create}` list AR1 actually
builds. It also restated the gate as "no instruction file of any kind exists in the project",
which is a different predicate: on a repo holding `AGENTS.md` but no `CLAUDE.md`, running
under Claude, AR1 queues `CLAUDE.md` while that gate would have written `AGENTS.md` — a file
for another AI system, already present, and possibly already rewritten by AR4 in the same run.
The gate is AR1's: `{to_create}` non-empty. If `{to_create}` is empty there is nothing to
create here, whatever other instruction files do or do not exist.

````markdown
## l3io-pm State Layout

This project runs on BMad v7. The work-item tree is v7's, owned by Sofia (`bmad-agent-po`):
initiatives, epics and tickets under `{output_folder}`, each container's `tickets/tickets.toml`,
the leaf files and the plans beside them, and standalone tickets in `{output_folder}/backlog/`.
Change it only through Sofia's procedures.

l3io keeps its own records beside that tree, written only by `pm-status.py` and v7's hooks:

- `<initiative>/tickets/l3io.toml` — each epic's lane
- `<initiative>/tickets/epic-<slug>/tickets/l3io.toml` — estimates and the epic's closure
- `<stem>-plan.l3io.toml` beside each plan — a ticket's actuals
- `{l3io_state_root}` — `events.jsonl`, `pm-calibration.yaml`, `adr-register.yaml`

Never edit these files directly. Use `/l3io-doctor` for diagnostics and housekeeping.
````

Adapt the heading style and surrounding content to match the conventions of the file being created for that AI system.

**Step AR6 — Verify and report**

Re-read each updated and created file. Confirm no legacy state reference (per the Detection rule — `sprint-status*.yaml`, `E{nnn}-status.yaml`, `_bmad/state/`, the 3.x sharded tree or its `issues.yaml`, non-`.legacy`) remains. If any remain, list them as unresolved.

```
DONE — AI rules update complete.
  References updated: {N} across {M} file(s)
  Files created:      {C}
  Unresolved:         {U} (list if > 0)
  Files checked (no changes needed): {files}
```
