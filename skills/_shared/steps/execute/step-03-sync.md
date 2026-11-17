# Step 03: Sync with the store

`next` is the build order v7 vouches for. On the repo store it reads the tree as it is. On a
tracker the tree only mirrors the tracker, so `next` refuses until the mirror is fresh, and
v7's status verb refuses outright (`:1002` and `:1288` of Sofia's script). This run therefore
never writes a status through that script on a tracker: every status change there goes
through the store's own `write`, then `mirror`, as Sofia does it.

## 1. Repo store

When `{store}` is `repo`, `{run_plan}.sync` is empty. Run `{run_plan}.next` once and print the
`ready_to_start` refs, so the user sees what the first wave starts with. Continue to step 04.

## 2. Tracker store

When `{store}` is anything else, run `{run_plan}.sync[0]`:

1. Read and follow **Tracker sync** in `{po_root}/references/board.md`, verbatim: Sofia's own
   `read_store.py` merges the store's starter config, `query` reads the tracker's state for the
   initiative, and `tickets.py mirror` writes it into the leaf files. Nothing else writes them.
2. Then run the step's `next` command. It carries `--synced`, which is what tells `tickets.py`
   the mirror is fresh.

If either fails, stop; a stale mirror would start tickets the tracker already moved:

```
BLOCKED: tracker sync failed: <the command and its message>
```

Commit what `mirror` wrote, as Sofia's procedure does, so the first build starts on a clean
tree.

## 3. Output

```
Step 03 complete — store: {store}, ready to start: <refs>
```
