# l3io-arch knowledge

This document covers the `l3io-arch` module: what its one skill gives the user, when to recommend it, and what to offer next. The full reference is `docs/l3io-arch-reference.md` in this package's source repository.

## What the module is

One skill, `l3io-arch-review`, which applies engineering standards: separation of concerns, reuse, design by contract, testability, dependency and GA policy, unified correlated logging and documentation with diagrams, plus per-stack rules for Python, Node.js, .NET, GitHub Actions, Docker, PowerShell and shell.

Most of it runs inside BMad's own skills once `/l3io-doctor wire` has run: `bmad-architecture` consults the standards, applies the documentation standard and runs l3io's design review at every Reviewer Gate, and five engineering lenses (`l3io-design-integrity`, `l3io-testability`, `l3io-dependency-policy`, `l3io-observability`, `l3io-stack-rules`) run in `bmad-review` and in every thorough review inside `bmad-code-review`, `bmad-build` and `bmad-build-auto`.

## The skill

| Mode | For | When to recommend |
|---|---|---|
| `design` | Routes to `bmad-architecture`, which carries the guardrails once wired. | The user is starting a project or a major component. |
| `review` | Runs `bmad-review` with the five l3io lenses on a design, component or diff, and grades the findings into a severity-graded report. BLOCKER and MAJOR must be resolved or justified by an ADR; MINOR defers to the backlog. | The user wants an architecture review, or a second opinion on a design before building it. |
| `decision` | Weighs a decision in play against the principles it puts in tension, recommends an option, and records the choice as a numbered ADR. | The user is choosing a technology or an architectural approach. |

## After a mode finishes

| Just finished | Offer next |
|---|---|
| `design` | `bmad-agent-po` (Sofia) to plan the work the design implies. |
| `review` | `decision` for each finding that needs a recorded ADR. |
| `decision` | Nothing further: the ADR is the output. |
