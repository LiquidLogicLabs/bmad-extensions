# Troubleshooting

Every skill in this package refuses loudly rather than guessing. A run that stops prints
`BLOCKED:`, `FAILED:` or `HALT`, and this page maps those to causes and fixes.

Two general rules first:

- **`BLOCKED:` means nothing was written.** The run stopped before changing state. It is safe to
  fix the cause and re-run.
- **Re-running without changing anything will block identically.** There is no override flag for
  most gates, by design. If a message tells you what to fix, that is the only path forward.

When you do not know where you are, `/l3io-doctor stats` shows where the initiative stands. It is
read-only and safe at any time.

## Exit codes

Both Python helpers use stable exit codes, useful when scripting around them.

| Code | `pm-status.py` | `spec-align.py` |
|---|---|---|
| 0 | success / verified | ok |
| 1 | `notice`: already emitted for this key; `estimate-entries --check`: an entry has no estimate; a committing verb: written, but the commit failed | a report-mode check found problems |
| 2 | usage error; for `notice`, an unexpected recording failure | a gate refused, or bad input |
| 3 | node, entry or plan not found | — |
| 4 | verification failure (missing or invalid field); `build-close` with no open bracket | — |
| 5 | epic locked (issue verbs on a 3.x tree) | the spec-sync lease is held by another owner |

## Setup and environment

### `ruamel.yaml is required`

```
pm-status.py: ruamel.yaml is required. Run via `uv run` (auto-provisions it) or `pip install ruamel.yaml`.
```

The helper's dependencies come from an inline PEP 723 header, which only `uv run` reads. Run it
through `uv`, or `pip install ruamel.yaml` for the interpreter you are using.

Note that missing `uv` alone is not fatal — the skills fall back to `python3`. It only becomes
fatal when that interpreter also lacks the dependency, which is why `uv` is listed as a
prerequisite.

### `BMad v7 not detected`

```
BLOCKED: BMad v7 not detected. l3io 4.x supports BMad v7 only; on BMad 6.x install l3io 3.x.
```

l3io 4.x attaches to v7's skills and reads v7's ticket tree; it has no 6.x mode.

### `_bmad/l3io-pm/scripts/pm_status is not installed`

`npx skills add` installs skills but no declared script. Run `bmad setup l3io-pm` (and
`bmad setup l3io-util` for the doctor), which installs each module's `pm_status` copy.

### BMad core is not installed

Config resolution runs BMad core's `resolve_config.py`. If it is missing, the skill blocks and
tells you to run the BMad installer. It will not write a config itself or continue on guesses.

## A 3.x project

l3io 4.x does not read a 3.x state tree (`{implementation_artifacts}/state/`, a flat
`sprint-status.yaml` or a legacy `_bmad/state/`). `bmad migrate` moves it onto v7's tree:
method's migration first, then l3io-pm's `migration-1`; see
[Upgrading](upgrading.md).

## Estimation problems

### `estimate-entries` exits 2 naming entries that need a class

A new entry has no class, and the class is the one judgement an estimate needs. `/l3io-plan
estimate` and Sofia's hooks ask the agent to classify each named entry `simple`, `standard` or
`complex` and pass it as `--class ID=CLASS`. Nothing was written.

### `entry <id> (<title>): no estimate`

Sofia's validate Set check (`estimate-entries --check`) found entries with neither l3io's
estimate nor a hand-set one. Run `/l3io-plan estimate` on the epic, or set an estimate on the
entry in `tickets.toml` yourself.

### A committing verb exits 1

`estimate-entries`, `sidecar-reconcile`, `set-lane`, `build-close` and `epic-close` wrote their
files and then failed to commit them — usually a commit hook. The tree is dirty, and the next
`bmad-build-auto` will refuse to start on it. Commit or fix the hook, then continue.

## Execution problems

### `the working tree is not clean`

`l3io-execute` starts only from a clean main checkout, because every `bmad-build-auto` run
demands one. Commit or stash the listed paths.

### `{slug} is owned by another session`

Its branch `l3io/{slug}` is checked out in another worktree, so another run may be building it.
The run never removes or reuses that worktree. Once nothing runs in it, remove it yourself.

### `{ref} of {slug} did not build`

`bmad-build-auto` halted on the ticket; the reason is its plan's `blocked_reason`, or the paths it
left dirty. Resolve it in that epic's worktree, then run `/l3io-execute` again — a ticket already
`built` is not rebuilt.

### `the retrospective of {slug} is rejected`

`bmad-retrospective` did not accept the epic, so its tickets stay `built` and that epic halts.
Moving them to `done` anyway would be a risk acceptance, which is yours alone — the run never
does it for you.

### `{slug} gates the next wave and is not done`

A later wave waits for this epic's closure, and only you can tell Sofia an epic is `done`. Close
it in Sofia, then run `/l3io-execute` again.

### `merging l3io/{slug} into {base} conflicts`

Two epics of one wave changed the same files. Resolve the conflict, finish the merge, and run
`/l3io-execute` again.

### `tracker sync failed`

Sofia's Tracker sync procedure failed before any build. The message names the command; fix the
tracker connection and re-run.

## Spec alignment problems

### `Departs from spec: … does not resolve`

An ADR points at a spec section that the spec index cannot find. Fix the pointer so it matches a
real `path#anchor`, or correct the heading it refers to.

### `migrate-adrs --apply refuses: uncommitted changes already sit under …`

A previous run stopped midway, leaving moved files uncommitted. Inspect and commit or revert
**those specific paths** by hand.

Never use a repo-wide discard: other agents may share this checkout, and a blanket reset would
destroy their uncommitted work. The message lists exactly which paths to look at.

## Things that are refused on purpose

These are not errors to work around. Each one exists because the alternative shipped a bug once.

| You tried | Why it is refused | Do this instead |
|---|---|---|
| `set-actual --cost …` | Cost is derived from tokens × rates, never entered | Fix the token counts, or the `token_rates` override |
| Asserting `completion_evidence.tests_passing` | An agent asserting its own tests passed is not falsifiable — one once shipped `true` over a suite it never ran | `add-test-run --command CMD --exit-code N`, or `build-close --test-run 'CMD=EXIT'`; the flag is derived from them |
| A lane named rather than numbered | A name cannot be screened from a person's | `set-lane --lane N`, `N` in `1..lane_count` |
| `--runtime` with any other value | Only `claude`, `codex`, `copilot`, `other` are valid | Use one of the four; `other` when unsure |
| An `N/A` token count under `--runtime claude` | A Claude session can read its own usage | Capture the real figures from the transcript |

## Still stuck?

- `/l3io-doctor stats` — where the initiative stands, read-only
- `/l3io-doctor check` — the full diagnostic, read-only, changes nothing
- [Limits](limits.md) — it may be something this package deliberately does not do
- [Upgrading](upgrading.md) — if the project came from an older version
