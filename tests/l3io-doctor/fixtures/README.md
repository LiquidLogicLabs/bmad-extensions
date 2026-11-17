# Migration fixtures

One directory per l3io 3.x source layout `migrate-engine.py` reads, plus two more. Each is a
minimal but REAL tree — the readers and the engine are tested against trees shaped like the
ones they will meet, not against hand-built dicts that confirm the author's assumption about
the shape. `test-engine.py` copies each into a project beside the v7 initiative method's own
migration would have written, at the place named below.

| Directory | Layout | Lands at | Reader |
|---|---|---|---|
| `sharded/` | the 3.x tree `state/{active,planned,archived}/epic-*/` plus the project-wide files | implementation folder | `read-sharded.py` |
| `l3io-flat/` | `sprint-status.yaml` with an `epics:` list | implementation folder | `read-l3io-flat.py` |
| `split/` | `sprint-status{,-backlog,-archived}.yaml` | implementation folder | `read-split.py` |
| `per-epic/` | `_bmad/state/epic-*.yaml`, one file per epic | project root | `read-per-epic.py` |
| `bmad-flat/` | `sprint-status.yaml` with BMad's `development_status:` mapping — not ours; method's migration reads it | implementation folder | none |
| `v6-shim/` | a sharded project still carrying BMad 6.12's `bmad-create-story` shim | project root | `read-sharded.py` |

**Every fixture must be referenced by a test.** `test-engine.py` asserts the set of
directories here equals the engine's `LAYOUTS` plus `bmad-flat` and `v6-shim` — so deleting a
fixture fails the suite instead of silently shrinking the corpus.
