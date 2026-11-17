# l3io lens: abusive legitimate user (`l3io-threat-abuse`)

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

An adversary who uses the system exactly as designed, in ways its designers did not intend.

## Check

- Feature misuse: scraping, automated bulk operations, chained features that escalate access.
- Logic flaws: steps out of the expected order; transitions the state machine allows but should not.
- Edge inputs: zero, null or empty, maximums, negatives, unicode and encoding tricks.
- Shared-state harm: input that corrupts other users' experience; one tenant consuming another's resources.
- Boundaries: behaviour at exact limits (maximum size, maximum items, expiry instants).

**AI poisoning, from this viewpoint:** Adversarial prompts from legitimate users; jailbreaks through legitimate-looking input; systematic probing of model behaviour for an exploitable pattern. When the content has an AI or LLM component, the
`l3io-ai-poisoning` lens goes deeper; note what you saw here for it.

## Findings

Return the host review's canonical fields for each finding, and nothing else:

- `location` — file:line-range for code, section for a document
- `trigger_condition` — the problem, in one line
- `guard_snippet` — the concrete fix
- `potential_consequence` — what goes wrong if it ships as it is
- `principle` — `abusive-user`

No severity, priority or ranking: the host review triages. An empty list is a valid result,
but never return one for content with a security surface without saying, in one line, which entry points you examined.
Write `trigger_condition` as the attack: a concrete path an adversary would take, from their
side, and `potential_consequence` as what they gain and who is harmed.
