# l3io-sec knowledge

This document covers the `l3io-sec` module: what its one agent gives the user, when to recommend it, and what to offer next. The full reference is `docs/l3io-sec-reference.md` in this package's source repository.

## What the module is

One agent, the Red Team Agent (`l3io-sec-redteam`), which reviews a sprint, an epic or a whole solution adversarially through five threat lenses: external attacker, malicious insider, chaos engineer, abusive legitimate user, and design and architecture, with AI poisoning as a cross-cut over all five. It researches current cloud and platform best practices live and keeps a research cache, so later runs are faster. It produces an HTML findings report with a severity-graded findings table and an executive summary.

## What it needs

Web search must be enabled in the user's agent for the live platform research. `research_cache_ttl_days` sets how long a cached finding is trusted before it is researched again.

## When to recommend it

- "Is this secure", "red team this", "threat model this epic" → `l3io-sec-redteam`, at sprint, epic or solution scope.
- After `l3io-execute` closes a sprint or an epic, for an adversarial pass over what was built.

## After it finishes

Offer `l3io-plan` to schedule fixes for the findings the user accepts.
