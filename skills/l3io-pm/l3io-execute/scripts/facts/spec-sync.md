# l3io: architecture specs follow accepted departures (`l3io-pm`)

A standing fact for `bmad-retrospective`, added by `/l3io-doctor wire`. It replaces l3io's
3.x epic-closure spec sync, which wrote accepted architecture departures back into the specs.

- **This repository's decisions folder is `docs/adr/`.** It is the one home for decision
  records (ADRs). Write every decision record the user approves there; never a second
  `docs/decisions/` folder beside it.
- **A decision that departs from an architecture spec is also a spec reconciliation.** When a
  decision you propose, or a finding you route, contradicts what an architecture document
  states — the architecture spine, `docs/architecture*`, or a section a ticket cites in a
  `Spec: <path>#<anchor>` line — add an action item naming the spec file and section, the
  sentence the as-built contradicts, the replacement text, and the decision record or commit
  that justifies it. Mark it a spec reconciliation awaiting the user.
- **You do not edit the spec.** The retrospective's only writes are its document and the
  decision records the user approved. The user applies a spec reconciliation through
  `bmad-architecture` (its Validate or update intent), where l3io's design review runs as a
  finalize reviewer, and every edit there is confirmed after it lands.
