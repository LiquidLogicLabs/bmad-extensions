# Phase 4 exit — R3, by hand

R3 is the one Phase 4 exit criterion no gate can prove: one epic planned in Sofia, built by
`/l3io-execute`, closed through `bmad-retrospective`, with all five metrics then read back
from l3io's sidecars. It needs a live agent session. Status at the Task 4.9 commit:
**pending-manual**. Record the transcript and the read-back output beside this file as
`2026-11-17-phase-4-r3-transcript.md` once it has been run.

Upstream pin: `e435a22574fe55722841086e5566420178b98df3` (the one `scripts/fetch-bmad-tool.mjs`
exports as `PIN`).

## 1. Build the fixture

From this repository's root, on `feat/bmad-v7-layer`:

```bash
pkg=$PWD
pin=$(node --input-type=module -e 'import { PIN } from "./scripts/fetch-bmad-tool.mjs"; console.log(PIN)')
work=$(mktemp -d -t l3io-r3-XXXXXX)
bash tests/fixtures/v7/make-fixture.sh "$pin" "$work/fixture"
proj=$work/fixture/proj
```

`make-fixture.sh` installs v7's `core-tools` and `method` for Claude Code and Codex and runs
v7's `setup.py`; `$work/fixture/setup.json` must report `"problems": []`.

## 2. Install and set up all four modules

Exactly as `scripts/smoke-install.sh` does:

```bash
cd "$proj"
for m in l3io-pm l3io-util l3io-sec l3io-arch; do
  npx --yes skills add "$pkg/skills/$m" -s '*' -a claude-code -a codex -y --copy
done
uv run --quiet --no-project .agents/skills/bmad/scripts/setup.py --project-root . \
  --skill .agents/skills/bmad --root .agents/skills --root .claude/skills \
  --list-config-questions > ../questions.json
jq -r 'group_by(.module)[] | "[modules.\"\(.[0].module)\"]", (.[] | "\(.key) = \(.default | tojson)")' \
  ../questions.json > ../answers.toml
uv run --quiet --no-project .agents/skills/bmad/scripts/setup.py --project-root . \
  --skill .agents/skills/bmad --root .agents/skills --root .claude/skills \
  --module-answers ../answers.toml
test -f _bmad/l3io-pm/scripts/pm_status/__main__.py
test -f _bmad/l3io-util/scripts/pm_status/__main__.py
git add -A && git commit -qm "chore: v7 fixture with l3io"   # bmad-build-auto needs a clean tree
```

Commit `_bmad/` (the `git add -A` above does) so the run may use a worktree per epic
(ADR-0022). For the serial path, add `_bmad/` to `.gitignore` before committing instead.

## 3. Wire

Start Claude Code in `$proj` and run:

```
/l3io-doctor wire
```

Expect every entry `applied` (none `skipped`: `l3io-pm` is set up). Commit the team files it
wrote under `_bmad/custom/`. Confirm with `/l3io-doctor`; the health check must show no
Critical or High finding.

## 4. Plan one epic in Sofia

```
/bmad-agent-po
```

Ask her for one initiative with one epic of two or three small stories (for example, a
`hello` CLI with a `--name` flag and a test). Let her run TICKETS and REFINE, and approve each
ticket. Her `tickets_after` / `refine_after` hooks run `estimate-entries`; when she asks for a
class per entry, answer `simple`. Then run her validate: the Ticket check
(`spec-align.py check-pointers --story-file`) and the Set check (`estimate-entries --check`)
must both pass. Verify before building:

```bash
cat _bmad-output/<initiative>/tickets/epic-<slug>/tickets/l3io.toml   # [entry.<id>].estimate and [epic].estimate
git status --porcelain                                                  # empty
```

## 5. Run

```
/l3io-execute _bmad-output/<initiative>
```

It plans with `dispatch-plan.py`, runs one `bmad-build-auto` (invoked `thorough`) per ticket,
then `bmad-retrospective -H` for the epic, and stops at the epic gate to ask. Accept the
verdict. Each build's On Complete commits `chore(l3io): actuals <ticket>`; the retrospective's
On Complete commits `chore(l3io): epic close <slug>`.

## 6. Read the five metrics back

From `$proj`, with `E=_bmad-output/<initiative>/tickets/epic-<slug>`:

```bash
# per ticket: each plan sidecar's actual (elapsed_hours, man_hours, hitl_hours, tokens_k, cost)
for f in "$E"/tickets/*-plan.l3io.toml; do
  echo "== $f"
  python3 -c 'import sys, tomllib; a = tomllib.load(open(sys.argv[1], "rb"))["actual"]; [print(k, a.get(k)) for k in ("elapsed_hours", "man_hours", "hitl_hours", "tokens_k", "cost")]' "$f"
done

# the epic: [epic.estimate], [epic.closure], [epic.actual], retro_verdict
python3 -c 'import sys, tomllib; e = tomllib.load(open(sys.argv[1], "rb"))["epic"]; [print(b, {k: e.get(b, {}).get(k) for k in ("elapsed_hours", "man_hours", "hitl_hours", "tokens_k", "cost")}) for b in ("estimate", "closure", "actual")]; print("retro_verdict", e.get("retro_verdict"))' "$E/tickets/l3io.toml"

# read-back gates: each ticket's sidecar verifies, and the report joins it all
for p in "$E"/tickets/*-plan.md; do
  uv run _bmad/l3io-pm/scripts/pm_status/__main__.py verify --project-root . --plan-file "$p" --scope story
done
uv run _bmad/l3io-pm/scripts/pm_status/__main__.py report --project-root . \
  --initiative-dir _bmad-output/<initiative> --format md

# calibration samples and the event log
uv run _bmad/l3io-pm/scripts/pm_status/__main__.py calibration show \
  --state-root _bmad-output/l3io --format json
grep -c dispatch_close _bmad-output/l3io/events.jsonl
```

R3 passes when: every plan sidecar carries all five metrics with real `tokens_k` classes and a
derived `cost` (runtime `claude`), every `verify` exits 0, the epic's `l3io.toml` carries
`[epic.actual]` = Σ ticket actuals + `[epic.closure]` with an accepted `retro_verdict`, one
`scope` sample per estimated ticket and one `closure` sample are in the calibration file, and
`git status --porcelain` is empty.

Then keep the transcript and the output of section 6 as
`docs/superpowers/notes/2026-11-17-phase-4-r3-transcript.md`.
