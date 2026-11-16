# l3io-arch knowledge

This document covers the `l3io-arch` module: what its one skill gives the user, when to recommend it, and what to offer next. The full reference is `docs/l3io-arch-reference.md` in this package's source repository.

## What the module is

One skill, `l3io-arch-review`, which applies engineering standards: separation of concerns, reuse, design by contract, testability, dependency and GA policy, unified correlated logging and documentation with diagrams, plus per-stack rules for Python, Node.js, .NET, GitHub Actions, Docker, PowerShell and shell. With it installed, `l3io-execute` also runs an epic architecture gate before any sprint.

## The skill

| Mode | For | When to recommend |
|---|---|---|
| `design` | A new-project design checklist: separation-of-concerns boundaries, a C4 context plus one flow diagram, the initial ADR set, a docs skeleton, and a dependency policy note. | The user is starting a project or a major component. |
| `review` | Audits a design, component or diff against every loaded principle and rolls the findings into a severity-graded report. BLOCKER and MAJOR must be resolved or justified by an ADR; MINOR defers to the backlog. | The user wants an architecture review, or a second opinion on a design before building it. |
| `decision` | Weighs a decision in play against the principles it puts in tension, recommends an option, and records the choice as a numbered ADR. | The user is choosing a technology or an architectural approach. |

## After a mode finishes

| Just finished | Offer next |
|---|---|
| `design` | `l3io-plan` to plan the work the design implies. |
| `review` | `l3io-execute` once the BLOCKER and MAJOR findings are resolved. |
| `decision` | Nothing further: the ADR is the output. |
