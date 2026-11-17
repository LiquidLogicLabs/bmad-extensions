# l3io lens: design integrity (`l3io-design-integrity`)

A review lens from l3io's engineering standards (module `l3io-arch`), run inside BMad's own
review: `bmad-review` and the thorough review of `bmad-code-review`, `bmad-build` and
`bmad-build-auto`. This file is the lens's whole method. The rules it applies live in the
standards files beside it, `../standards/`, which are the single source of truth: cite them,
never restate or invent a rule. Testability, dependencies, logging and per-stack rules are other l3io lenses; leave them to those.

## Scope

- A diff: review the changed hunks and what they directly reach. A finding about code the diff
  did not touch is out of scope unless the change makes it newly wrong.
- Anything else (a file, a design, a plan, a ticket, a spec): the whole content is the scope.
- Read the files this lens names below before you review. If one is unreadable, report that
  exact failure as your only output and stop.

## Method

Read `../standards/standards-core.md` §1, §2, §3, §5 and §6. For each, walk its **Review**
bullets and **Red flags** against the content:

1. **Separation of concerns (§1)** — trace what each changed unit imports and who calls it.
   Flag an inner layer depending on an outer one, a transport, ORM or framework type crossing a
   domain boundary, business branching in a controller or UI, config read deep in domain code,
   and a cycle.
2. **Reuse (§2)** — search the repository for logic the change duplicates (more than about
   five meaningful lines). Name the existing home or the extraction target. Coincidental
   similarity, the same shape for a different reason to change, is not duplication.
3. **Design by contract (§3)** — flag a public entry point with unchecked input, implicit
   nullability or an undocumented failure mode, and re-validation deep inside a trusted core.
4. **Brevity and comments (§5, §6)** — flag code a reader cannot follow on first pass, ceremony
   an idiom removes, a stale comment, and change history narrated in a comment.

## Findings

Return the host review's canonical fields for each finding, and nothing else:

- `location` — file:line-range for code, section for a document
- `trigger_condition` — the problem, in one line
- `guard_snippet` — the concrete fix
- `potential_consequence` — what goes wrong if it ships as it is
- `principle` — `Core §1`, `Core §2`, `Core §3`, `Core §5` or `Core §6`

No severity, priority or ranking: the host review triages. An empty list is a valid result,
but a clean result on a non-trivial change means walk the import graph once more before you return it.
