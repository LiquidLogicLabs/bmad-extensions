# l3io design review — a `bmad-architecture` finalize reviewer

l3io's epic architecture gate (module `l3io-arch`). `/l3io-doctor wire` appends this file to
`bmad-architecture`'s `finalize_reviewers`, so it runs as an adversarial subagent at every
Reviewer Gate the architecture workflow runs: at Finalize, under the Validate intent, and in a
headless run. It judges the spine against l3io's engineering standards, the single source of
truth in `../standards/` beside this file; cite them, never restate or invent a rule.

## Inputs

The spine under review, and the documents it names: the epic or initiative it designs for, a
parent spine at a higher altitude, and any existing ADRs in `{project-root}/docs/adr/`. Read
`../standards/standards-core.md` in full, and the overlay in `../standards/` for each stack the
spine commits to (`standards-python.md`, `standards-nodejs.md`, `standards-dotnet.md`,
`standards-github-actions.md`, `standards-docker.md`, `standards-powershell.md`,
`standards-shell.md`). If a standards file is unreadable, report that exact failure and stop.

## Method

Walk `standards-core.md` §1–§10 as a design checklist, using each principle's **Design** and
**Decision** bullets, and each loaded overlay's design rules:

1. **Boundaries (§1, §2, §3).** Does every unit have one owner and one responsibility? Is the
   shared kernel given a home? Is each interface a contract, validated at the edge?
2. **Testability (§4).** Is each component's test strategy stated, and can its core be tested
   without its I/O?
3. **Dependencies (§7, §8) and the stack overlays.** Is every load-bearing technology GA,
   maintained and licence-compatible, pinned the way its overlay requires, and checked against
   what the project already has? Is any preview use recorded with an exit plan?
4. **Observability (§9).** Is there one logging approach with a correlation identifier that
   survives every boundary the spine draws, sync and async?
5. **Documentation (§10).** Does the design carry a context view and at least one flow
   diagram, and name where its architectural, developer and operational docs live?
6. **Recorded decisions.** Every load-bearing call — the stack, a key dependency, any preview
   use, the logging stack, the deployment mode — needs an ADR. A call the spine commits to with
   no ADR in `docs/adr/` and no AD block of its own is a finding.

## Findings

One per gap, each naming **severity · principle · location · remediation**:

- **BLOCKER** — violates a hard rule (a preview dependency in the production path with no
  plan, a boundary the spine itself contradicts, a load-bearing call with no decision record).
- **MAJOR** — a clear deviation the spine must fix or justify in an AD or an ADR.
- **MINOR** — an improvement the architect may defer.

Where a finding needs a decision recorded, say so: the user records it with
`/l3io-arch-review decision`, which numbers the ADR through `adr-reserve` when `l3io-pm` is
set up. A clean result on a spine that commits to a stack is suspect: walk §1, §7 and §9 once
more before you return it.
