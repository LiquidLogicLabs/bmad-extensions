# l3io lens: malicious insider (`l3io-threat-insider`)

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

An adversary with legitimate but limited access, attacking from inside.

## Check

- Privilege abuse: data beyond the role, elevated permissions used for unauthorized purposes.
- Out-of-scope access: other tenants' or users' data; bulk export or reporting abused.
- Audit gaps: an operation that succeeds without an audit trail; log tampering; bypassed monitoring.
- Corruption and deletion: overwriting others' data; malicious content in shared state.
- Supply chain: malicious code or data through a legitimate contribution path (a dependency,
  a CI definition, a build script, a generated file).

**AI poisoning, from this viewpoint:** Training or fine-tuning data poisoned through insider write access to a data pipeline; a backdoor planted in a model workflow; proprietary prompts, data or model artifacts exfiltrated. When the content has an AI or LLM component, the
`l3io-ai-poisoning` lens goes deeper; note what you saw here for it.

## Findings

Return the host review's canonical fields for each finding, and nothing else:

- `location` — file:line-range for code, section for a document
- `trigger_condition` — the problem, in one line
- `guard_snippet` — the concrete fix
- `potential_consequence` — what goes wrong if it ships as it is
- `principle` — `malicious-insider`

No severity, priority or ranking: the host review triages. An empty list is a valid result,
but never return one for content with a security surface without saying, in one line, which entry points you examined.
Write `trigger_condition` as the attack: a concrete path an adversary would take, from their
side, and `potential_consequence` as what they gain and who is harmed.
