# l3io lens: observability (`l3io-observability`)

A review lens from l3io's engineering standards (module `l3io-arch`), run inside BMad's own
review: `bmad-review` and the thorough review of `bmad-code-review`, `bmad-build` and
`bmad-build-auto`. This file is the lens's whole method. The rules it applies live in the
standards files beside it, `../standards/`, which are the single source of truth: cite them,
never restate or invent a rule. It applies to code; a design document's logging plan is a decision the architecture review records.

## Scope

- A diff: review the changed hunks and what they directly reach. A finding about code the diff
  did not touch is out of scope unless the change makes it newly wrong.
- Anything else (a file, a design, a plan, a ticket, a spec): the whole content is the scope.
- Read the files this lens names below before you review. If one is unreadable, report that
  exact failure as your only output and stop.

## Method

Read `../standards/standards-core.md` §9, and the **Logging** lines of the overlay in
`../standards/` for each stack the change touches.

1. Flag ad-hoc output (`print`, `console.log`, `Write-Host`, bare `echo` to stdout for
   diagnostics) where the project has a logger, and an unstructured message where it logs
   structured fields.
2. Trace each request, job or message the change handles across every boundary it crosses:
   service to service, sync to async, request to job to callback. Flag a hop where the
   correlation or trace identifier is not propagated, and a new entry point that does not
   start or accept one.
3. Flag an error path that swallows the error or logs it without context, a level that does
   not match the event, and a secret, token or personal data written to a log.

## Findings

Return the host review's canonical fields for each finding, and nothing else:

- `location` — file:line-range for code, section for a document
- `trigger_condition` — the problem, in one line
- `guard_snippet` — the concrete fix
- `potential_consequence` — what goes wrong if it ships as it is
- `principle` — `Core §9`, or the overlay and section

No severity, priority or ranking: the host review triages. An empty list is a valid result,
but a change with no logging, error handling or boundary crossing has nothing for this lens: return an empty list and say so in one line.
