# l3io-sec knowledge

This document covers the `l3io-sec` module: what its one agent gives the user, when to recommend it, and what to offer next. The full reference is `docs/l3io-sec-reference.md` in this package's source repository.

## What the module is

One agent, the Red Team Agent (`l3io-sec-redteam`), which reviews a sprint, an epic or a whole solution adversarially through five threat lenses: external attacker, malicious insider, chaos engineer, abusive legitimate user, and design and architecture, with AI poisoning as a cross-cut over all five. It researches current cloud and platform best practices live and keeps a research cache, so later runs are faster. It produces an HTML findings report with a severity-graded findings table and an executive summary.

The same viewpoints run inside BMad's own review once `/l3io-doctor wire` has run: `l3io-threat-external`, `l3io-threat-insider`, `l3io-threat-chaos`, `l3io-threat-abuse`, `l3io-threat-design` and `l3io-ai-poisoning` are lenses in `bmad-review` (AI poisoning chained after the external attacker) and in every thorough review inside `bmad-code-review`, `bmad-build` and `bmad-build-auto`. The agent is for a deliberate, whole-scope red-team session with its persona and memory.

## What it needs

Web search must be enabled in the user's agent for the live platform research. `research_cache_ttl_days` sets how long a cached finding is trusted before it is researched again.

## When to recommend it

- "Is this secure", "red team this", "threat model this epic" → `l3io-sec-redteam`, at epic or solution scope.
- After `l3io-execute` closes an epic, for an adversarial pass over what was built.
- A quick security pass over one change → `bmad-review` with the threat lenses, e.g. `lenses=l3io-threat-external,l3io-ai-poisoning`.

## After it finishes

Offer Sofia (`bmad-agent-po`) to turn the findings the user accepts into tickets.
