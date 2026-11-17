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

What it adds (`assets/wire-in.toml`):

| Entry | Team file | Key | What it does |
|---|---|---|---|
| `l3io-build-open` | `bmad-build.toml` | `workflow.activation_steps_prepend` | opens l3io's measurement bracket (`build-open`) |
| `l3io-build-close` | `bmad-build.toml` | `workflow.on_complete` | closes it: the ticket's actuals, events, calibration sample, and a commit of them (`build-close`) |
| `l3io-build-auto-open` | `bmad-build-auto.toml` | `workflow.activation_steps_prepend` | as `l3io-build-open` |
| `l3io-build-auto-close` | `bmad-build-auto.toml` | `workflow.on_complete` | as `l3io-build-close`, with `hitl_hours` 0 |
| `l3io-estimate-on-slice` | `bmad-agent-po.toml` | `workflow.tickets_after` | estimates the entries a slice planned, and rolls up their epic (`estimate-entries`) |
| `l3io-estimate-on-refine` | `bmad-agent-po.toml` | `workflow.refine_after` | re-estimates the entry just refined |
| `l3io-reestimate-on-replan` | `bmad-agent-po.toml` | `workflow.replan_after` | repoints l3io's files after a move (`sidecar-reconcile`), then re-estimates each epic the replan touched |
| `l3io-menu-estimate` | `bmad-agent-po.toml` | `agent.menu` (code `l3io-estimate`) | a Sofia menu item running `l3io-plan` in estimate mode |
| `l3io-check-technical-ac` | `bmad-agent-po.toml` | `workflow.checks.ticket` | a Ticket check in Sofia's validate: business and six-dimension technical ACs with resolving `Spec:` lines (`spec-align.py check-pointers --story-file`) |
| `l3io-check-estimate-present` | `bmad-agent-po.toml` | `workflow.checks.set` | a Set check: every entry has an l3io estimate (`estimate-entries --check`) |
| `l3io-fact-ac-dimensions` | `bmad-agent-po.toml` | `agent.persistent_facts` | the AC dimension reference as a session fact, so REFINE writes what the Ticket check enforces |
| `l3io-board-waves` | `bmad-agent-po.toml` | `workflow.board_after` | after every board operation: repoints l3io's files after a move (`sidecar-reconcile`), then shows the initiative's waves and, when lanes are on, its lanes (`plan-graph.py waves`/`lanes`) |
| `l3io-menu-waves` | `bmad-agent-po.toml` | `agent.menu` (code `l3io-waves`) | a Sofia menu item running `l3io-plan` in waves mode |
| `l3io-menu-lanes` | `bmad-agent-po.toml` | `agent.menu` (code `l3io-lanes`) | a Sofia menu item running `l3io-plan` in lanes mode |
| `l3io-epic-close` | `bmad-retrospective.toml` | `workflow.on_complete` | after the retrospective is saved: the epic's actuals, the retrospective's own spend as the closure actual, its verdict, one closure calibration sample, and a commit of them (`epic-close`); writes no status |
| `l3io-fact-spec-sync` | `bmad-retrospective.toml` | `workflow.persistent_facts` | the epic-closure spec sync: decision records go to `docs/adr/`, and a decision that departs from an architecture spec becomes a spec-reconciliation action item, applied by the user through `bmad-architecture` (`facts/spec-sync.md`) |
| `l3io-lens-<viewpoint>-review` (11) | `bmad-review.toml` | `workflow.lenses` (codes `l3io-…`) | the eleven review lenses: `l3io-design-integrity`, `l3io-testability`, `l3io-dependency-policy`, `l3io-observability`, `l3io-stack-rules` (`l3io-arch`) and `l3io-threat-external`, `l3io-threat-insider`, `l3io-threat-chaos`, `l3io-threat-abuse`, `l3io-threat-design`, `l3io-ai-poisoning` (`l3io-sec`), the last chained `after` the external attacker |
| `l3io-lens-<viewpoint>-code-review`, `-build`, `-build-auto` (11 each) | `bmad-code-review.toml`, `bmad-build.toml`, `bmad-build-auto.toml` | `workflow.thorough_lenses` (ids `l3io-…`) | the same eleven, in every `thorough` review; the quick review stays BMad's |
| `l3io-arch-design-review` | `bmad-architecture.toml` | `workflow.finalize_reviewers` | l3io's design review against the engineering standards, at every Reviewer Gate (the epic architecture gate) |
| `l3io-arch-standards-source` | `bmad-architecture.toml` | `workflow.external_sources` | consult the standards before a stack, dependency, logging or deployment call |
| `l3io-arch-doc-standard` | `bmad-architecture.toml` | `workflow.doc_standards` | the documentation standard (§10) on fuller prose documents |

Each entry names a file under `{project-root}/_bmad/<module>/scripts/`, which `bmad setup
<module>` installs from the files that module declares, and carries `requires = "<module>"`:
while that module's file is absent the entry is `skipped` and nothing is written for it.
The `l3io-pm` hooks call `pm_status/__main__.py`, `spec-align.py` or `plan-graph.py`, or name a fact
file under `facts/`; the menu items need `l3io-pm` the same way. The engineering lenses, the
standards and the design review need `l3io-arch` (`lenses/`, `standards/`, `reviewers/`); the
threat lenses need `l3io-sec` (`lenses/`).
Every hook that writes commits the l3io files it wrote and nothing else, so the next
`bmad-build-auto` still starts on a clean tree; the two checks, the waves and lanes views, the
lenses and the architecture entries only read.

## 2. Report

Print the output as-is. Each line is one entry: `applied`, `already` (ours, from an
earlier run), `present` (the team already holds the same value), `yielded` (the team holds
an entry with the same `code`/`id` — the team's wins and ours is not added), `skipped` (the
module it calls is not set up: suggest `bmad setup <module>`, then `wire` again), or
`refused`.
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
