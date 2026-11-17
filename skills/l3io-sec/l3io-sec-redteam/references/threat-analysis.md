# Threat Analysis

## What Success Looks Like

Findings across all applicable lenses, each with:
- **Title** — specific, descriptive, not generic ("Unauthenticated admin endpoint at /api/admin/users", not "Missing authentication")
- **Attack path** — concrete reproduction steps from an adversary's perspective
- **Impact** — what an adversary gains; who is affected; what data or systems are at risk
- **Recommendation** — specific code or design change, not generic advice
- **Lens** — which perspective surfaced it (may span multiple)

A clean report on non-trivial scope is a failure of analysis. If no Critical or High findings surface, re-examine with a fresh angle before declaring the scope clean.

## The Five Lenses and the AI Poisoning Cross-cut

Each viewpoint has one source, a lens file under `scripts/lenses/`. The same files run inside
BMad's own review once `/l3io-doctor wire` has added them to `bmad-review` and the thorough
review of `bmad-code-review`, `bmad-build` and `bmad-build-auto`; this session walks them all,
in depth, across the whole scope.

| Lens | File |
|---|---|
| 1 — External attacker | `scripts/lenses/l3io-threat-external.md` |
| 2 — Malicious insider | `scripts/lenses/l3io-threat-insider.md` |
| 3 — Chaos engineer | `scripts/lenses/l3io-threat-chaos.md` |
| 4 — Abusive legitimate user | `scripts/lenses/l3io-threat-abuse.md` |
| 5 — Design and architecture red team | `scripts/lenses/l3io-threat-design.md` |
| AI poisoning cross-cut, over the findings of all five | `scripts/lenses/l3io-ai-poisoning.md` |

Load each file and apply its **Viewpoint** and **Check**, then run the AI poisoning cross-cut
over what the five found. Report in this session's own shape (`references/findings-report.md`,
with severity), not the lens files' canonical-field contract, which is the host review's.

## HALT Conditions

**Empty scope** — no artifacts, no entry points identified: halt and ask for clarification before running any lens.

**Zero Critical/High on non-trivial scope** — if the scope contains auth code, data access patterns, or external interfaces and zero Critical/High findings surface: mandatory re-analysis. Choose a different angle, assume a different attacker model, examine from the chaos engineer lens if not done thoroughly. Document why the score is genuinely low before declaring the scope clean.

**Auth code with no auth findings** — if the scope includes authentication, authorization, or identity management code and zero auth findings surface: re-examine ownership checks, token validation, and privilege escalation paths explicitly. Document your reasoning.
