l3io-doctor — Project State Diagnostics & Utilities
========================================================
Usage: /l3io-doctor [command]

Diagnostic (read-only)
  (no argument)      Project health check — scan and propose all needed actions
  check / status     Read-only health check — report findings, no changes
  stats              Progress over BMad v7 initiatives — epics, tickets, stalls + backlog
  backlog / issues   Aliases for stats; always print the per-item backlog table
  check-deps         Verify BMad skill dependencies resolve in this project
  version            Which l3io-extensions version this project is running
  upgrade            Update this extension (BMad quick-update; never deletes modules)
  uninstall          Remove this extension's payload only — dry run until confirmed

One-time migrations
  migrate-state      Migrate a legacy flat or per-epic layout to the 3.x sharded tree
  migrate-adrs       Move ADRs from epic-*/arch/ to docs/adr/, the one ADR home

Ongoing maintenance (safe to repeat)
  redrive            Rebuild calibration scope/fix samples from the story nodes on disk
  triage             Audit v7's backlog; propose to Sofia what to close or move

Source & external sync
  harvest-debt       Sweep source for bmad-defer: markers; candidate bugs for Sofia
  update-ai-rules    Update AI instruction files that name a legacy state layout

Setup & housekeeping
  setup              Register l3io-util module config for this project
  wire               Attach l3io's entries to the team's _bmad/custom/<skill>.toml files
  unwire             Remove exactly what wire added, never a team entry
  clean-legacy       Remove .legacy/.v1 migration backup files and the state.legacy/ and
                     migration-backup/ backup directories after confirmation

Run without arguments to let the health check decide what's needed.
