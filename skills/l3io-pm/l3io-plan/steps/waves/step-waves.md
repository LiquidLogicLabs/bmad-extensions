# Waves — the order a v7 initiative's epics may run in

Orders the epics of a BMad v7 initiative into waves, or the initiatives of a parent
initiative, and names the epics whose closure a later wave waits on. It only reads: v7's own
`tickets.py status`, through `plan-graph.py waves`. Sofia's board renders the same view after
every board operation once `l3io-doctor wire` has run; this mode is for the user who asks, and
for Sofia's `l3io-waves` menu item.

## 1. Which folder

- The user named an initiative or a parent initiative: use it.
- None named: the active initiative, the one Sofia is working in. If you cannot tell which
  that is, ask, naming the initiative folders under `{output_folder}`.

An epic folder has no waves of its own: say so and use the initiative that holds it.

## 2. Run it

```bash
uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} status <folder> \
  | uv run {skill-root}/scripts/plan-graph.py waves --status-json -
```

`tickets.py` is v7's, installed with Sofia (`bmad-agent-po`). If it is absent, say that Sofia
is not set up in this project and stop. If `tickets.py` itself fails, show its message: the
tree is v7's to fix, through Sofia.

## 3. Report

One line per wave, from the JSON:

```
Wave 1 (parallel): epic-platform, epic-docs
Wave 2: epic-cart — after epic-platform (sessions and the product catalogue)
Wave 3 (parallel): epic-search, epic-checkout — after epic-cart (a basket to pay for) [gate]
```

- Each `after` item names the epic waited on and its `needs` reason as v7 recorded it. An item
  with `via` and no reason came from an entry's `after`, not from the initiative's
  `tickets.toml`: name the entries, and suggest declaring the dependency there (Sofia reports
  the same thing as `undeclared_after`).
- Mark `[gate]` on each item whose `gate` is true, and list `gates` after the waves: a later
  wave waits for each one's **closure**, which the user confirms, so an unattended run stops
  there. A dependency on a ticket alone is met once that ticket is built, and is no gate.
- `done` epics are finished and out of the waves. An item marked `dropped` waits on an epic
  that will never finish: say so, and point at Sofia's BOARD to repoint the `after`.
- On a parent initiative the members are initiatives, and every dependency is a gate.
- An `error` means the dependency graph has a cycle: show it and stop.

```
DONE — {n} waves over {m} epics, {g} gates
```
