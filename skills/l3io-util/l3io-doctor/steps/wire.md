# wire — attach l3io's entries to the team's customization files

Invoked with `wire`. **Writes** the team's `_bmad/custom/<skill>.toml` files, and only
those (ADR-0020). BMad v7 has no customization layer a module contributes, so l3io's lenses,
facts and hooks are attached by adding them to the team's own file. What is added is listed
in `assets/wire-in.toml`; what was added is recorded in a ledger,
`{output_folder}/l3io/wire-in.json`, so `unwire` can remove exactly that.

## 1. Run it

```bash
uv run {skill-root}/scripts/wire-in.py wire --project-root {project-root}
```

It is idempotent: a second run changes nothing. Comments, key order and every entry the
team wrote survive.

## 2. Report

Print the output as-is. Each line is one entry: `applied`, `already` (ours, from an
earlier run), `present` (the team already holds the same value), `yielded` (the team holds
an entry with the same `code`/`id` — the team's wins and ours is not added), or `refused`.
Then:

- Exit 0 → `DONE — wired; run /l3io-doctor unwire to remove it.`
- Exit 3 → `REFUSED — a team value is in the way; everything else was applied.` Each
  `refused` line names the file, the key, the team's value and ours. A single-value hook
  (`on_complete`, `tickets_after`, …) holds one value, so l3io **never** overwrites it.
  Offer the user two ways out, and do neither without their word:
  1. compose the two into one instruction by hand in that file, or
  2. clear the team's value, then run `/l3io-doctor wire` again.
  A `refused` line saying a key "is not an array" or "is not a table" means the team file
  holds that key in a different shape; show it to the user rather than editing it.
- Exit 2 → `FAILED: <the script's stderr>`. A team file that is not valid TOML is named
  there, and nothing at all was written.
