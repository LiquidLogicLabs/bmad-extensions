# l3io lens: testability (`l3io-testability`)

A review lens from l3io's engineering standards (module `l3io-arch`), run inside BMad's own
review: `bmad-review` and the thorough review of `bmad-code-review`, `bmad-build` and
`bmad-build-auto`. This file is the lens's whole method. The rules it applies live in the
standards files beside it, `../standards/`, which are the single source of truth: cite them,
never restate or invent a rule. This lens judges whether the design can be tested, not how many tests there are.

## Scope

- A diff: review the changed hunks and what they directly reach. A finding about code the diff
  did not touch is out of scope unless the change makes it newly wrong.
- Anything else (a file, a design, a plan, a ticket, a spec): the whole content is the scope.
- Read the files this lens names below before you review. If one is unreadable, report that
  exact failure as your only output and stop.

## Method

Read `../standards/standards-core.md` §4, then for each changed unit ask: what is the unit
test for this, and what does it need?

1. Flag a collaborator created inside business logic instead of injected, a hard-wired clock,
   network, filesystem, random source or environment read, a static singleton, and hidden
   global state.
2. Flag pure logic reachable only through I/O or a heavy integration path: the functional core
   should be separable from the imperative shell.
3. Flag a behaviour whose only test would need the full environment, and a test the change
   adds that exercises a mock rather than the behaviour.
4. For a design or plan: flag a component with no stated test strategy (unit, contract,
   integration, end-to-end).

## Findings

Return the host review's canonical fields for each finding, and nothing else:

- `location` — file:line-range for code, section for a document
- `trigger_condition` — the problem, in one line
- `guard_snippet` — the concrete fix
- `potential_consequence` — what goes wrong if it ships as it is
- `principle` — `Core §4`

No severity, priority or ranking: the host review triages. An empty list is a valid result,
but a change that adds logic with no seam to test it through is never clean.
