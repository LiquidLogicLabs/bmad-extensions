# l3io lens: design and architecture (`l3io-threat-design`)

A threat lens from l3io's red-team model (module `l3io-sec`), run inside BMad's own review:
`bmad-review` and the thorough review of `bmad-code-review`, `bmad-build` and
`bmad-build-auto`. The same viewpoint is one of the five the Red Team Agent
(`l3io-sec-redteam`) walks in a full session; this file is its single source.

Stance: an adversary, not an auditor. A clean result on content with a security surface
(authentication, authorization, input from outside the process, data access, secrets, a trust
boundary) is a failure of analysis: re-examine from a different angle before you return it.

## Scope

- A diff: review the changed hunks and what they directly reach. A finding about code the diff
  did not touch is out of scope unless the change makes it newly wrong.
- Anything else (a file, a design, a plan, a ticket, a spec): the whole content is the scope.
- Read the files this lens names below before you review. If one is unreadable, report that
  exact failure as your only output and stop.

## Viewpoint

A red team over the system's shape: weaknesses no single line of code shows.

## Check

- Missing controls: a control the architecture specifies that the implementation lacks.
- Trust boundaries: components talking across a boundary with no authentication or validation.
- Defense in depth: a single point of failure in a security control; no fallback layer.
- Observability: security-relevant events not logged; no alerting on an anomalous pattern.
- Recovery: after a breach, is there a kill switch, revocation, and an audit trail fit for forensics?
- Secrets: hard-coded credentials, keys in config, secrets in version control or logs.

**AI poisoning, from this viewpoint:** A model or agent placed inside a trust boundary it should sit outside; model output trusted as if it were validated input; no control between a model's decision and a privileged action. When the content has an AI or LLM component, the
`l3io-ai-poisoning` lens goes deeper; note what you saw here for it.

## Findings

Return the host review's canonical fields for each finding, and nothing else:

- `location` — file:line-range for code, section for a document
- `trigger_condition` — the problem, in one line
- `guard_snippet` — the concrete fix
- `potential_consequence` — what goes wrong if it ships as it is
- `principle` — `design-architecture`

No severity, priority or ranking: the host review triages. An empty list is a valid result,
but never return one for content with a security surface without saying, in one line, which entry points you examined.
Write `trigger_condition` as the attack: a concrete path an adversary would take, from their
side, and `potential_consequence` as what they gain and who is harmed.
