# Step 00: Activate l3io-pm Module

This step runs first in every l3io-pm skill. Complete all actions in order before loading
any subsequent step file.

---

## 0. Confirm this is a BMad v7 install

l3io 4.x supports **BMad v7 only**; l3io 3.x is the line for BMad 6.x. Check before anything
else, because every later step reads v7's layout: config from v7's resolver, and `pm_status`
from the copy `bmad setup` installs under `_bmad/l3io-pm/scripts/`.

```bash
evidence_path=""
if [ -f "{project-root}/_bmad/scripts/setup.py" ]; then
  bmad_generation=v7; evidence_path="{project-root}/_bmad/scripts/setup.py"
elif evidence_path=$(grep -ls '^\[bmod\]' {project-root}/.*/skills/*/bmod.toml | head -1) \
     && [ -n "$evidence_path" ]; then
  bmad_generation=v7
else
  bmad_generation=not-v7
fi
echo "bmad_generation=$bmad_generation evidence_path=$evidence_path"
```

Only things no 6.x release ships count as v7: `_bmad/scripts/setup.py`, which v7's `bmad setup`
writes, and a module record (`bmod.toml` carrying `[bmod]`) in any tool's skills folder, which
arrives as soon as v7's skills are installed. `_bmad/scripts/config_utils.py` is **not** a
signal: 6.12.0 and later ship it too. A 6.x project with v7's skills added, whose
`_bmad/_config/manifest.yaml` is still present, is a v7 project by the second signal. Verified
against a real 6.12.4 install (no v7 signal), a v7 install at `e435a22` (`setup.py`), and that
6.12.4 install with v7's skills added (`[bmod]` record, manifest still present).

When `bmad_generation` is `not-v7`, stop. Do not resolve config or load another step:

```
BLOCKED: BMad v7 not detected. l3io 4.x supports BMad v7 only; on BMad 6.x install l3io 3.x.
```

## 1. Load module configuration

Resolve config through BMad core's resolver — the full contract, including every
binding and its default, is `{skill-root}/references/config-resolution.md`:

```bash
uv run --python 3.11 {project-root}/_bmad/scripts/resolve_config.py --project-root {project-root}
```

If the resolver is missing or the command fails, BMad core is not installed in this
project: **BLOCKED** — tell the user to run the BMad installer. Do not write config
yourself and do not continue.

`modules.l3io-pm` being absent is **not** a first-run and **not** an error — it means the
module has no project-level overrides, which is the normal state. Bind the defaults below
and continue. This skill never loads module setup, regardless of argument —
`bmad setup l3io-pm` is the module's setup entry point.

Bind `{l3io_pm_section_absent}` = `true` when `modules.l3io-pm` is absent from the resolved
JSON, else `false`. This reuses the same resolved JSON already read above — it is not a second
resolve. It exists solely for the once-per-project setup-pointer check in `l3io-execute` and
`l3io-plan` (`config-resolution.md` §5) — not once per session: there is no cross-invocation
session identifier available, so a session-keyed check would fire on every invocation instead.
The pointer's only useful message is "you have not configured this," so it must say nothing
once a section exists. This flag is never a trigger for setup itself — no argument to this
skill triggers module setup; `bmad setup l3io-pm` is the module's setup entry point.

Extract and bind from the resolved JSON:
- `{output_folder}` — `core.output_folder` (default `{project-root}/_bmad-output`)
- `{model}` — `modules.l3io-pm.default_model` (default `claude-opus-5`). The model id every
  `cost` in this project is priced against. Pass it as `--model {model}` on `estimate-entries`
  and every pm-status call that prices tokens. **Not optional** —
  leaving it unbound prices every estimate at `claude-opus-5` regardless of what the project
  actually runs on, and the same token volume prices ~2× apart between a $3/M and a $10/M
  input tier. An unknown id is a hard error, exit 2, never a silent fallback.
- `{token_rates_json}` — `modules.l3io-pm.token_rates`, serialized to compact JSON; empty
  when the key is absent, which is the normal case (the shipped rate table applies). When it
  is **non-empty**, add `--token-rates '{token_rates_json}'` to `estimate-story`,
  `estimate-rollup`, `estimate-entries`, `set-actual`, **and `verify`**; when it is empty, omit the flag
  entirely. Passing it to the writers but not to `verify` makes `verify` recompute `cost`
  against the shipped rates and fail every node the override priced. See
  `references/config-resolution.md` §3.
- `{lane_count}` — `modules.l3io-pm.lane_count` (absent: lanes off), and `{lane}` —
  `modules.l3io-pm.lane`, from the user layer only (absent: no lane of one's own)
- Set `{pm_state_root}` = `{output_folder}/l3io`, the project-wide state root every l3io hook
  shares beside v7's ticket tree (`references/status-files.md` §12)

## 2. Locate pm-status.py

`pm-status.py` is the package `pm_status/`, shipped once per module and **declared** in that
module's `bmod.toml` (`[skill] scripts`). For `l3io-pm` the declaring skill is `l3io-execute`,
and BMad v7's `bmad setup l3io-pm` installs the declared files at
`{project-root}/_bmad/l3io-pm/scripts/pm_status/`, rebuilding that tree on every setup. Every
`l3io-pm` skill calls that one copy.

`npx skills add` puts the skills on disk but installs no declared script; only setup does. So a
skill run between the two finds no copy, and a `uv run` of the missing file would fail with a
Python traceback that names nothing the user can act on. Check first:

```bash
test -f {project-root}/_bmad/l3io-pm/scripts/pm_status/__main__.py
```

If absent, halt:
```
BLOCKED: _bmad/l3io-pm/scripts/pm_status is not installed — run bmad setup l3io-pm
```

Bind `{pm_status}` = `{project-root}/_bmad/l3io-pm/scripts/pm_status/__main__.py` for use in all
subsequent steps.

### 2a. Bind the runtime

Bind `{runtime}` — passed as `--runtime` to every `set-actual` and `verify` call
(`references/metrics-contract.md` §3). The value must be **exactly** one of `claude`,
`codex`, `copilot`, or `other` — `pm-status.py` rejects anything else with exit 2.
The criterion is a **capability**, not a brand check: choose the value whose token capture
procedure you can actually execute.

**Detection procedure:**

1. **`claude`** — bind when `$CLAUDE_CODE_SESSION_ID` is set in the environment. This is the
   Claude Code session identifier; its presence means the `pm-status.py usage` subcommand can
   read the session transcript to extract exact per-class token counts.

2. **`codex`** — bind when running inside Codex CLI and session JSONL files are available at
   `~/.codex/sessions/`. Confirmation: `ls ~/.codex/sessions/ 2>/dev/null | head -1` returns a
   session directory. Token capture reads `token_count` events from `rollout-*.jsonl`; sum
   `input_tokens`, `output_tokens` + `reasoning_output_tokens` (folded into output),
   and `cached_input_tokens` (→ `cache_read`); `cache_write` is `0` (Codex CLI drops this
   field — see metrics-contract.md §3).

3. **`copilot`** — bind when running inside a GitHub Copilot agent session (VS Code Copilot
   extension or Copilot Cloud Agent) where `$CLAUDE_CODE_SESSION_ID` is absent and Codex CLI
   session files are not present. Token capture sums `usage.prompt_tokens` (→ input) and
   `usage.completion_tokens` (→ output) across every API response in the node's dispatch
   window. No cache split is accessible; cost is recorded as N/A.

4. **`other`** — bind in all other cases, including when token data is genuinely not observable.
   Tokens and cost are recorded as N/A; `man_hours`, `hitl_hours`, and `elapsed_hours` are
   still required as real numbers.

**Default to `other` when uncertain** — it is the permissive value, allowing N/A for
tokens/cost. Guessing `claude` without transcript access, or `codex` without readable session
files, would either block every write (exit 2 on `--tokens-na`) or invite a fabricated number,
and both are worse than an honest N/A.

## 2.5. Verify the l3io-doctor sibling module is installed

`l3io-doctor` is a required intra-package module (CLAUDE.md "Dependencies") — the PM
skills forward migrations, health checks, and the plan-aware progress dashboard to it. `l3io-pm`'s
module record requires it, so `bmad setup` reports it as an unmet requirement until it is
installed.

The check probes `.claude/skills`, `.claude/commands/` (pre-6.12) and `.agents/skills`, in the
project and then in the home directory, and finally BMad 6.x's own install record,
`_bmad/_config/skill-manifest.csv`. It is inlined because `bmad-deps.py` cannot be used here:
that script *is* the doctor. `.agents/skills` is the **cross-tool standard on 6.x**, shared by
27 of the 48 platforms 6.12.4's installer supports. The manifest line covers the other twenty
tool-specific directories (`.cline/skills`, `.kiro/skills`, …): 6.x writes one row per skill it
installs, whichever tool was chosen, and a row's first field is the quoted skill name. There is
deliberately **no `.agents/commands/`** probe: upstream has zero references to one, so probing
it would read as supported layout while matching nothing.

```bash
if   [ -f "{project-root}/.claude/skills/l3io-doctor/SKILL.md" ] \
  || [ -f "{project-root}/.claude/commands/l3io-doctor.md" ] \
  || [ -f "{project-root}/.agents/skills/l3io-doctor/SKILL.md" ] \
  || [ -f "$HOME/.claude/skills/l3io-doctor/SKILL.md" ] \
  || [ -f "$HOME/.claude/commands/l3io-doctor.md" ] \
  || [ -f "$HOME/.agents/skills/l3io-doctor/SKILL.md" ] \
  || grep -qs '^"l3io-doctor",' "{project-root}/_bmad/_config/skill-manifest.csv"; then
  doctor=present
else
  doctor=absent
fi
```

**Warn but do not block.** This skill can complete without the doctor for its own core path;
the failure is deferred to whichever specific step tries to forward to it (`migrate-state`,
`stats`). Surfacing the warning up front turns "skill not found"
into a diagnosable install anomaly instead of a downstream mystery.

When `doctor=absent`, print exactly once at activation (do not repeat later):

```
⚠️  l3io-doctor is not installed — this is a required module of the LiquidLogicLabs
    extension, and `bmad setup` lists it as an unmet requirement of l3io-pm. Some steps
    below (state-layout migrations and the progress dashboard) will fail
    if reached. Install it with
    `npx skills add LiquidLogicLabs/bmad-extensions/skills/l3io-util`, then run
    `bmad setup`.
```

Continue to section 2.6 either way.

## 2.6. Offer the agent instruction block, once per harness

A project installed under one harness has no block in another harness's instruction file.
Check, and if the block is absent offer it **once ever, per harness**. This is **advisory and
never blocking**: it fires at activation, the user started this run for something else, and
interrupting it to ask about a documentation file is disproportionate. Print the offer and
continue. (The health check, `/l3io-doctor`, is the second surface, where interruption is
expected.) `{runtime}` is the value bound in section 2.

```bash
uv run {pm_status} sync-agent-instructions --runtime {runtime} \
  --project-root {project-root} --check
rc=$?
if [ "$rc" -eq 1 ]; then
  uv run {pm_status} notice --state-root {pm_state_root} --key ai-rules-missing:{runtime}
fi
```

`--check` is read-only and takes no lock. Act on its exit code:

- **0** — the block is present. Say nothing.
- **1** — absent. Run `notice`. When it exits 0, print one line and continue:
  `This project's {runtime} instruction file has no l3io block — an agent without it does not
  know project state is machine-written. Add it with /l3io-doctor (health check).`
  When `notice` exits 1 it has already been offered for this harness; say nothing. Keying per
  harness is the point — a single global key would mean the second harness is never asked.
- **2** — the file is not valid UTF-8, or its `l3io:begin`/`l3io:end` markers are ambiguous.
  **Do not offer to add a block, and never repair this on your own judgement.** The script
  refused precisely because it could not tell which marker was real, and picking one is the
  damage it exists to prevent.

  **Refusing to guess is not the same as refusing to help.** Deciding which block is right is
  the user's; finding the markers and splicing the lines is not, and handing that back gives
  them the easy half. So:

  1. **Show the ambiguity.** Name each `l3io:begin` and `l3io:end` with its line number and a
     few surrounding lines — "two `l3io:begin`, lines 42 and 118; the one at 42 has no
     matching end" — so they can see what they are choosing between. For invalid UTF-8, name
     the byte offset instead; there is nothing to choose, only to report.
  2. **Ask which reading is right.** The one question only a human can answer.
  3. **Make the edit yourself**, touching nothing outside the markers they resolved, and say
     what you changed.

  If they decline to choose, say so and continue — never edit on a guess, and never block the
  run. Print one line while unresolved —
  `⚠️  {runtime} instruction file could not be read for the l3io block (invalid UTF-8 or
  ambiguous markers). Tell me which block is current and I will fix it.` — and continue. This
  line is not recorded in the notice ledger, so it repeats until the file is fixed.
- Any other exit — say nothing and continue; a documentation probe never fails the run.

## 3. Bind session ID

Generate and bind `{session_id}` — a stable unique identifier for this execution session
(e.g., `l3io-pm-{iso_timestamp}-{random_suffix}`). This value must remain constant for the
lifetime of this skill invocation and stamps every event this run appends. Generate it once
here; never regenerate it in later steps.

**Only an orchestrator generates one.** If your context block supplies `session_id`, that
value is the run's — bind it and do not mint another. Two ids for one run cannot be
reconciled afterwards: `events.jsonl` is append-only and the stamp is all there is.

## 4. Output status line

```
Step 00 complete — state: {pm_state_root}, pm-status: installed, runtime: {runtime}
```
