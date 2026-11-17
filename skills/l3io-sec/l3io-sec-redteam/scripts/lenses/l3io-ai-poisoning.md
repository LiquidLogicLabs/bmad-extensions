# l3io lens: AI poisoning (`l3io-ai-poisoning`)

A threat lens from l3io's red-team model (module `l3io-sec`), run inside BMad's own review. It
is the cross-cut the Red Team Agent (`l3io-sec-redteam`) applies over its five threat
viewpoints, and this file is its single source. In `bmad-review` it runs **after**
`l3io-threat-external` and receives that lens's findings; in the thorough review of
`bmad-code-review`, `bmad-build` and `bmad-build-auto` it runs on its own.

It applies only where the content has an AI, ML or LLM component: prompts, model calls,
retrieval, embeddings, training or fine-tuning data, agent tools, or model output consumed by
code. With none, return an empty list and say so in one line.

## Scope

- A diff: review the changed hunks and what they directly reach. A finding about code the diff
  did not touch is out of scope unless the change makes it newly wrong.
- Anything else (a file, a design, a plan, a ticket, a spec): the whole content is the scope.
- Read the files this lens names below before you review. If one is unreadable, report that
  exact failure as your only output and stop.

## Method

1. **Prior findings.** When you were given another lens's findings, extend each one that
   reaches an AI component: what does the same weakness do once a model is in the path?
2. **Every input a model reads** — user input, documents, mail, web pages, tool results,
   retrieved chunks, memory. Flag any that can carry instructions the model will follow
   (direct or indirect prompt injection), and any path where untrusted text is concatenated
   into a system prompt or tool definition.
3. **Every output a model writes** — flag model output that reaches code execution, a query,
   a shell, a file path, a URL fetch, a privileged API or another user's view without
   validation, and an agent tool that can act beyond what its caller is allowed.
4. **Data and model supply chain** — training, fine-tuning and retrieval data an insider or an
   outside contributor can write; a model, adapter or embedding pulled from an unpinned or
   unverified source; prompts, data or model artifacts that can be exfiltrated.
5. **Degraded behaviour** — what the system does when the model is wrong, slow, unavailable or
   deliberately probed: is there a fallback that keeps the security invariants?

## Findings

Return the host review's canonical fields for each finding, and nothing else:

- `location` — file:line-range for code, section for a document
- `trigger_condition` — the problem, in one line
- `guard_snippet` — the concrete fix
- `potential_consequence` — what goes wrong if it ships as it is
- `principle` — `ai-poisoning`, plus the viewpoint it crosses, e.g. `ai-poisoning/external-attacker`

No severity, priority or ranking: the host review triages. An empty list is a valid result,
but never return one for content with an AI component without saying, in one line, which model inputs and outputs you examined.
Write `trigger_condition` as the attack, from the adversary's side.
