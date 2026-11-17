# Estimate — a v7 initiative or epic

Estimates the entries of BMad v7 epics into l3io's own `l3io.toml` beside each epic's
`tickets.toml`, and rolls each epic up. It never writes a ticket, a `tickets.toml`, a leaf
file or a plan (ADR-0015). Sofia's slice, refine and replan hooks run the same command; this
mode is for the user who asks for it, and for Sofia's `l3io-estimate` menu item.

Uses `{pm_status}` and `{model}` from `steps/shared/step-00-activate.md`.

## 1. Which folders

- The user named a folder: use it. An **epic** folder is `<initiative>/tickets/epic-<slug>`
  (it holds `epic-<slug>.md` and a `tickets/` folder). An **initiative** folder holds
  `<name>.md` and `tickets/tickets.toml`; its epics are the `epic-*` folders under its
  `tickets/`.
- No folder named: use the active initiative, the one Sofia is working in. If you cannot
  tell which that is, ask, naming the initiative folders under `{output_folder}`.

Estimate each epic folder in turn. An initiative with no epic folders has nothing to
estimate: say so and stop.

## 2. Run it

For each epic folder `D`:

```bash
uv run {pm_status} estimate-entries --project-root {project-root} --ticket-dir D --model {model}
```

Pass `--force` only when the user asked to re-estimate everything, and `--entry ID` for an
entry the user named.

- **Exit 2 naming entries that need a class.** Read each named entry in `D/tickets/tickets.toml`
  (and its leaf file, when one exists) and judge it `simple`, `standard` or `complex`: how much
  it changes, how many places, how much is unknown. Show the user your classes, one line each
  with the reason; on their word, run the command again with one `--class ID=CLASS` per entry.
  The class is the only judgement here; never type an estimate.
- **Exit 3**: an `--entry` the epic does not list. Say so; do not guess another id.
- **Exit 1**: the estimates were written but the commit failed (a commit hook, say). Show the
  message: the tree is dirty and the next `bmad-build-auto` would stop on it.

An entry with a hand-set estimate in `tickets.toml` is never written; the command says so on
stderr. That is the user's estimate, and it stands.

## 3. Report

One line per entry written (`entry`, `class`, `action`, and `man_hours`/`tokens_k` from its
`estimate`), then each epic's roll-up as its low–high range of man-hours and cost. When the
epic line lists `orchestration_unestimated`, add that its estimate is known-low on those
metrics until three epics have closed. Then:

```
DONE — estimated {n} entries across {m} epics
```
