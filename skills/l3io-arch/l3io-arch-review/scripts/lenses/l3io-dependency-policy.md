# l3io lens: dependency policy (`l3io-dependency-policy`)

A review lens from l3io's engineering standards (module `l3io-arch`), run inside BMad's own
review: `bmad-review` and the thorough review of `bmad-code-review`, `bmad-build` and
`bmad-build-auto`. This file is the lens's whole method. The rules it applies live in the
standards files beside it, `../standards/`, which are the single source of truth: cite them,
never restate or invent a rule. It also owns the **existing-library check**: work the project or an established package already does should not be written again.

## Scope

- A diff: review the changed hunks and what they directly reach. A finding about code the diff
  did not touch is out of scope unless the change makes it newly wrong.
- Anything else (a file, a design, a plan, a ticket, a spec): the whole content is the scope.
- Read the files this lens names below before you review. If one is unreadable, report that
  exact failure as your only output and stop.

## Method

Read `../standards/standards-core.md` §7 and §8, and the overlay in `../standards/` for each
stack the content touches (`standards-python.md`, `standards-nodejs.md`, `standards-dotnet.md`,
`standards-docker.md`, `standards-github-actions.md`, `standards-powershell.md`,
`standards-shell.md`) for how that stack declares and pins a dependency.

1. **Every dependency the change adds or bumps** — check maintenance, adoption, licence
   compatibility, known unpatched vulnerabilities and transitive weight (§7). Use the
   package registry or the web when you can; say which facts you could not check.
2. **GA over preview (§8)** — flag any `-alpha`, `-beta`, `-rc`, `-preview` or `-SNAPSHOT`
   version, preview language feature or preview cloud service without a recorded decision
   (an ADR) and an exit plan.
3. **Existing-library check** — flag hand-written code that duplicates a dependency the
   project already has, the standard library, or a well-established package; and a new
   dependency added where a few lines, or one already present, would do.
4. **Recorded decision** — a load-bearing dependency choice with no ADR is a finding.

## Findings

Return the host review's canonical fields for each finding, and nothing else:

- `location` — file:line-range for code, section for a document
- `trigger_condition` — the problem, in one line
- `guard_snippet` — the concrete fix
- `potential_consequence` — what goes wrong if it ships as it is
- `principle` — `Core §7`, `Core §8`, `existing-library`, or the overlay and section, e.g. `Python: Packaging`

No severity, priority or ranking: the host review triages. An empty list is a valid result,
but say which added dependencies you checked, in one line, when you return none.
