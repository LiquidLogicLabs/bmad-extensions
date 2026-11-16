# unwire — remove what `wire` added

Invoked with `unwire`. **Writes** only the files `wire` recorded in its ledger,
`{output_folder}/l3io/wire-in.json`, and removes only what it recorded there (ADR-0020).

## 1. Run it

```bash
uv run {skill-root}/scripts/wire-in.py unwire --project-root {project-root}
```

## 2. Report

Print the output as-is. Then:

- Exit 0 → `DONE — unwired.` Explain the lines:
  - `restored` / `deleted` — the file was untouched since `wire`, so it is back to its
    exact pre-wire bytes, or gone if `wire` created it.
  - `removed` — the team edited the file after `wire`, so only l3io's entries were taken
    out and every team edit kept.
  - `left (edited since wire)` — an entry l3io added has since been changed by hand. It is
    the team's now and was not removed; tell the user so they can delete it themselves.
  - `gone` — already removed by hand.
  - `nothing to do` — there is no ledger: nothing was wired, or it was already unwired.
- Exit 2 → `FAILED: <the script's stderr or the error line>`. A team file that no longer
  parses is left alone and stays in the ledger; once it is fixed, run `unwire` again.
