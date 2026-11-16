# Transcript-fallback binding: when may a recovered transcript make the runtime `claude`?

Status: **proposed, for review.** Design only. Implementation is a separate decision.
Source: spec `2026-10-16-bmad-v7-layer-design.md` §8.2, "The transcript fallback does not yet
reach the orchestrator". Plan: `2026-11-15-bmad-v7-readiness.md` Task 1.6. Targets the 3.x line.

## The problem

`step-00-activate.md` binds `runtime=claude` only when `$CLAUDE_CODE_SESSION_ID` is set.
Without it, a run records token and cost actuals as `N/A`. `pm-status.py usage` can recover the
session's transcript by elimination: `discover_session_transcript` accepts the single
transcript that spans the node's dispatch bracket and holds a record inside it. But nothing
connects that recovery back to the runtime binding, so the orchestrated path never uses it.

Wiring it in naively is worse than `N/A`. A Codex or other non-Claude run on a machine that has
a dormant `~/.claude/projects/` tree can have a Claude session whose window overlaps the
bracket, perhaps someone else's session left open. Binding `claude` on that recovery would
record exact-looking numbers from the wrong tool, and calibration would learn from them. The
in-window guard does not prevent this: two sessions that both did work inside the window
already refuse, but one stranger session that did work there is accepted.

The question is what evidence proves that **this run** is the Claude session the transcript
belongs to, rather than merely that some Claude session was active at the time.

## Options

**A. Keep `N/A` (status quo).** Never wrong, and loses real data on every env-scrubbed Claude
run.

**B. Bind `claude` whenever recovery succeeds.** Rejected for the reason above: it mis-binds on
a dormant tree.

**C. Bind `claude` only when the recovered transcript contains this run's own dispatch.**
The orchestrator runs `pm-status.py dispatch --event open` with the node keys for every spawn,
and that call is a Bash `tool_use` whose `input.command` appears verbatim in the session's
transcript. `events.jsonl` records the same call with its own `ts`. Require the recovered
transcript to hold a `tool_use` whose command is a `dispatch --event open` naming the same
node keys, timestamped within a small tolerance (for example 120 s) of the `events.jsonl`
record. A non-Claude run cannot produce that record in a Claude transcript; a stranger's
session cannot name this node's dispatch at this moment.

**D. Have the orchestrator declare its runtime at dispatch** (for example
`dispatch --runtime R`). This moves the problem rather than solving it: in the env-scrubbed
case the orchestrator does not know its runtime either.

## Recommendation: C

It turns the binding from "a Claude session was active" into "this run is that Claude
session", using evidence the run already writes and the transcript already records. No new
state is needed. The failure direction is safe: a missing or mismatched `tool_use` keeps today's
`N/A`.

## What implementing C would involve

- `discover_session_transcript` (or a sibling) gains a proof step: scan the one surviving
  candidate for the matching `dispatch --event open` `tool_use` within tolerance, and refuse
  otherwise. That is a new reason for refusal, not a weaker acceptance.
- `step-00-activate.md` §7, or the actuals step, binds `runtime=claude` from a successful
  *proved* recovery, and records `recovered_by: dispatch-proof` beside the actual so the
  provenance is readable later.
- Tests:
  - a stranger transcript spanning the window with work inside it but no matching dispatch is
    refused;
  - the matching transcript is accepted;
  - a matching command outside the tolerance is refused;
  - every refusal leaves the runtime non-`claude` and the actuals `N/A`.

## Open questions for the reviewer

1. **Tolerance.** The `tool_use` record and the `events.jsonl` `ts` are written by different
   processes: the first at tool invocation, the second inside `pm-status.py`. Measure the gap
   on real runs before fixing a number.
2. **Subagent dispatches.** A dispatched subagent's own spawns appear in its
   `subagents/agent-*.jsonl` file, which carries the parent's `sessionId`. The proof should
   accept a match in either the parent file or a subagent file of the same session.
3. **Does this ship in 3.x, or wait for 4.x?** The env-scrubbed case is unusual, and 4.x's
   capture runs through `bmad-build`'s `on_complete` hook, where the same proof applies
   unchanged. Doing it once, in 4.x, is the cheaper option.
