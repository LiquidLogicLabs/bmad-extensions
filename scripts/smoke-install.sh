#!/usr/bin/env bash
# Install this package's four modules into a real BMad v7 project and assert what `bmad setup`
# reports about them (plan Task 2.3's R1). The project is built by tests/fixtures/v7/make-fixture.sh
# at the pin in scripts/fetch-bmad-tool.mjs, so this needs network: GitHub for the fixture's
# BMAD-METHOD fetch and for setup's update check, npm for `npx skills`. That is why it is not
# a CI gate; run it at phase boundaries by hand. ADR-0006: the 6.12 defects were found only by
# installing for real and looking.
#
# What it does, in the order a user would:
#   1. builds a v7 project (core-tools + method, for Claude Code and Codex);
#   2. copies it, untouched, for the "only l3io-pm" case;
#   3. `npx skills add` of each module folder under skills/ (never skills/_shared/), for the
#      same two tools, repeated -a flags (the comma form is not what make-fixture.sh measured);
#   4. runs v7's setup.py headlessly: --list-config-questions, then --module-answers with each
#      question's default, then --status.
#
# Usage: scripts/smoke-install.sh [workdir]
set -euo pipefail

# The workdir is ours to clean up only when WE created it. A caller-supplied "$1" belongs to the
# caller -- removing it would be the over-broad delete this estate has already paid for once.
# And a run that FAILS keeps its tree: a smoke test that deletes the evidence at the moment you
# need it is hostile to the debugging it exists to serve. standards-shell.md, which this package
# ships, puts the `trap` on the line after `mktemp`.
smoke_cleanup() {
  local rc=$?
  if [ "$rc" -eq 0 ]; then
    rm -rf "$work"
  else
    echo "smoke: workdir kept for inspection: $work" >&2
  fi
  return "$rc"
}

work="${1:-}"
if [ -z "$work" ]; then
  work="$(mktemp -d -t l3io-smoke-install-XXXXXX)"
  trap smoke_cleanup EXIT   # the very next line after mktemp, per the rule above
fi
pkg="$(cd "$(dirname "$0")/.." && pwd)"

# Validated explicitly rather than left to `set -e`: a missing directory, an unwritable one, and
# a relative path (used again after a `cd`) each end with a report on an install never made.
if [ ! -d "$work" ]; then
  echo "smoke: FAIL -- workdir '$work' does not exist (create it first, or pass no argument to get a mktemp -d)" >&2
  exit 2
fi
work="$(cd "$work" 2>/dev/null && pwd)" || {
  echo "smoke: FAIL -- workdir '$1' exists but could not be entered (permissions?)" >&2
  exit 2
}
if [ ! -w "$work" ]; then
  echo "smoke: FAIL -- workdir '$work' is not writable" >&2
  exit 2
fi
echo "smoke: workdir $work"

for tool in jq uv npx git; do
  command -v "$tool" >/dev/null || { echo "smoke: FAIL -- '$tool' is not on PATH" >&2; exit 2; }
done

# One pin for the whole repository: the one fetch-bmad-tool.mjs verifies validate_manifests.py at.
pin="$(cd "$pkg" && node --input-type=module -e \
  'import { PIN } from "./scripts/fetch-bmad-tool.mjs"; console.log(PIN)')"
version="$(jq -r .version "$pkg/package.json")"
export DO_NOT_TRACK=1 DISABLE_TELEMETRY=1

fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
info() { echo "  info $1"; }

add_module() { # <project> <source> [extra skills-CLI args]
  local proj="$1" src="$2"; shift 2
  (cd "$proj" && npx --yes skills add "$src" "$@" -a claude-code -a codex -y --copy >/dev/null)
}
setup() { # <project> [setup.py args]
  local proj="$1"; shift
  (cd "$proj" && uv run --quiet --no-project .agents/skills/bmad/scripts/setup.py --project-root . \
    --skill .agents/skills/bmad --root .agents/skills --root .claude/skills "$@")
}

echo "== fixture (BMAD-METHOD at ${pin:0:7}) =="
bash "$pkg/tests/fixtures/v7/make-fixture.sh" "$pin" "$work/fixture" >/dev/null
proj="$work/fixture/proj"
pm_only="$work/pm-only"
cp -a "$proj" "$pm_only"
check "the fixture's own setup reported no problems" \
  "jq -e '.problems == []' '$work/fixture/setup.json' >/dev/null"

# The module folders and their skills, derived from the tree the way check:bmod's view is.
modules=$(find "$pkg/skills" -mindepth 1 -maxdepth 1 -type d ! -name _shared -printf '%f\n' | sort)
check "skills/ holds at least one module folder (the derived set is not empty)" "[ -n '$modules' ]"

echo "== all four modules =="
for m in $modules; do
  add_module "$proj" "$pkg/skills/$m" -s '*'
  for skill in $(find "$pkg/skills/$m" -mindepth 2 -maxdepth 2 -name SKILL.md -printf '%h\n' | xargs -n1 basename); do
    check "$m: '$skill' landed in .agents/skills and .claude/skills" \
      "test -f '$proj/.agents/skills/$skill/SKILL.md' && test -f '$proj/.claude/skills/$skill/SKILL.md'"
  done
done

questions="$work/questions.json"
setup "$proj" --list-config-questions > "$questions"
check "setup lists l3io-pm's lane_count among the questions it would ask" \
  "jq -e 'any(.[]; .module == \"l3io-pm\" and .key == \"lane_count\")' '$questions' >/dev/null"

# Every question answered with its own default, as a user accepting each would.
answers="$work/answers.toml"
jq -r 'group_by(.module)[] | "[modules.\"\(.[0].module)\"]", (.[] | "\(.key) = \(.default | tojson)")' \
  "$questions" > "$answers"
report="$work/setup.json"
check "setup runs headlessly with every default accepted" \
  "setup '$proj' --module-answers '$answers' > '$report'"
check "setup reports no problems" "jq -e '.problems == []' '$report' >/dev/null"
check "setup reports no unmet requirement" "jq -e '.unmet_requirements == []' '$report' >/dev/null"
check "setup finds every skill's module record" "jq -e '.missing_module_records == []' '$report' >/dev/null"
for m in $modules; do
  check "setup registers module '$m' at $version" \
    "jq -e --arg m '$m' --arg v '$version' 'any(.modules[]; .module == \$m and .version == \$v)' '$report' >/dev/null"
done

# Phase 3 Task 3.2: each module's declared pm_status, installed by setup where its skills call it.
# The expected file set is the bmod.toml's own list, so a module missing from the declaration
# shows up as a missing file here and as an import failure in --help.
for decl in "l3io-pm:l3io-pm/l3io-execute" "l3io-util:l3io-util/l3io-doctor"; do
  code="${decl%%:*}"; skill_rel="${decl#*:}"
  copy="$proj/_bmad/$code/scripts/pm_status"
  declared="$(uv run --quiet --no-project python -c \
    'import sys, tomllib; print("\n".join(tomllib.load(open(sys.argv[1], "rb"))["skill"]["scripts"]))' \
    "$pkg/skills/$skill_rel/bmod.toml")"
  check "$code: the bmod.toml declares pm_status/__main__.py" \
    "printf '%s\n' '$declared' | grep -qx 'scripts/pm_status/__main__.py'"
  missing=""
  while IFS= read -r rel; do
    [ -f "$proj/_bmad/$code/${rel}" ] || missing="$missing ${rel}"
  done <<< "$declared"
  check "$code: setup installed every declared script under _bmad/$code/scripts/${missing:+ (missing:$missing)}" \
    "[ -z '$missing' ]"
  check "$code: uv run _bmad/$code/scripts/pm_status/__main__.py --help exits 0" \
    "(cd '$proj' && uv run --quiet '$copy/__main__.py' --help >/dev/null)"
done

# Phase 3 Task 3.3, Review Focus 3: the doctor's version report (the health check's Check 25)
# reads both installed copies. Agreeing copies are no finding; one copy's version moved is one
# finding naming both paths. The edited copy is restored before anything else reads it.
reporter="$proj/.agents/skills/l3io-doctor/scripts/report-version.py"
util_main="$proj/_bmad/l3io-util/scripts/pm_status/__main__.py"
check "the doctor's version report finds both pm_status copies agreeing (exit 0, no finding)" \
  "(cd '$proj' && uv run --quiet '$reporter' --project-root . --format json) \
     | jq -e '(.pm_status.findings == []) and ([.pm_status.copies[].version] | all(. != null))' >/dev/null"
cp "$util_main" "$work/util-main.bak"
sed -i 's/^# pm-status-version: .*/# pm-status-version: 0.0.1/' "$util_main"
skew="$(cd "$proj" && uv run --quiet "$reporter" --project-root . --format json; echo "exit=$?")"
cp "$work/util-main.bak" "$util_main"
check "one copy at another version is exit 3 and one finding naming both paths" \
  "printf '%s' '$skew' | grep -q '^exit=3$' && printf '%s' '$skew' | sed '\$d' \
     | jq -e '(.pm_status.findings | length) == 1 and (.pm_status.findings[0] | contains(\"_bmad/l3io-pm/scripts/pm_status\") and contains(\"_bmad/l3io-util/scripts/pm_status\") and contains(\"0.0.1\"))' >/dev/null"

# Phase 3 Task 3.3, Review Focus 4: a 3.x project kept its runtime copy in BMad's own
# _bmad/scripts/, as the pm-status/ package or the older single file. Plant both and re-run
# setup (no answers: every question is already answered): v7 rebuilds _bmad/scripts/ to exactly
# its own set, so neither survives.
mkdir -p "$proj/_bmad/scripts/pm-status"
printf '# pm-status-version: 3.7.1\n' > "$proj/_bmad/scripts/pm-status/__main__.py"
printf '# pm-status-version: 3.5.0\n' > "$proj/_bmad/scripts/pm-status.py"
setup "$proj" > "$work/setup-rerun.json"
check "re-running setup removes a 3.x copy left in _bmad/scripts/ (package and single file)" \
  "[ ! -e '$proj/_bmad/scripts/pm-status' ] && [ ! -e '$proj/_bmad/scripts/pm-status.py' ]"
check "re-running setup keeps BMad's own _bmad/scripts/ (setup.py)" \
  "[ -f '$proj/_bmad/scripts/setup.py' ]"

# Review Focus 4, the half that holds: a 3.x answer in _bmad/custom/config.toml still resolves.
# (Setup asks again regardless -- plan Task 2.3's note; the migration copies the answer across.)
printf '\n[modules.l3io-pm]\nlane_count = "3"\n' >> "$proj/_bmad/custom/config.toml"
check "a lane_count in _bmad/custom/config.toml resolves through v7's merge" \
  "(cd '$proj' && uv run --quiet --no-project _bmad/scripts/resolve_config.py --project-root . \
     --key modules.l3io-pm.lane_count) | jq -e '.\"modules.l3io-pm.lane_count\" == \"3\"' >/dev/null"

echo "== sidecars beside v7's tree (Phase 4 Task 4.1) =="
# A hand-written initiative (one epic, three entries, one plan each) under the project's own
# core.output_folder. set-estimate and set-actual with v7 addressing write only our sidecars:
# tickets.py's own `status` reads the tree byte-identically before and after, with no problems.
pm_main="$proj/_bmad/l3io-pm/scripts/pm_status/__main__.py"
tickets_py="$proj/_bmad/method/scripts/tickets.py"
check "v7 installed tickets.py at _bmad/method/scripts/" "[ -f '$tickets_py' ]"
out_folder="$(cd "$proj" && uv run --quiet --no-project _bmad/scripts/resolve_config.py --project-root . \
  --key core.output_folder | jq -r '."core.output_folder" // empty')"
out_folder="${out_folder//\{project-root\}/$proj}"
case "$out_folder" in /*) ;; *) out_folder="$proj/$out_folder" ;; esac
info "core.output_folder: $out_folder"
init="$out_folder/initiative-smoke"
epic_t="$init/tickets/epic-smoke/tickets"
mkdir -p "$epic_t"
printf -- '---\ntype: initiative\n---\n# Smoke\n' > "$init/initiative-smoke.md"
printf '[[epic]]\nid = 1\nslug = "epic-smoke"\ntitle = "Smoke"\n' > "$init/tickets/tickets.toml"
printf -- '---\ntype: epic\nafter: []\n---\n# epic-smoke\n' > "$init/tickets/epic-smoke/epic-smoke.md"
: > "$epic_t/tickets.toml"
for n in 1 2 3; do
  printf '[[entry]]\nid = %s\ntype = "story"\ntitle = "Story %s"\n\n' "$n" "$n" >> "$epic_t/tickets.toml"
  printf -- "---\ntitle: 'Story %s'\ntype: 'feature'\nticket: '%s'\nstatus: 'in-progress'\n---\n\n# Story %s\n" \
    "$n" "$n" "$n" > "$epic_t/story-$n-plan.md"
done
tstatus() { (cd "$proj" && uv run --quiet "$tickets_py" --project-root . status "$init"); }
tstatus > "$work/tickets-before.json"
check "tickets.py status reads the hand-written initiative with no problems" \
  "jq -e 'has(\"problems\") | not' '$work/tickets-before.json' >/dev/null"
sidecar_ok=1
for n in 1 2 3; do
  (cd "$proj" && uv run --quiet "$pm_main" set-estimate --project-root . --ticket-dir "$epic_t" \
     --entry "$n" --elapsed-hours 1 --man-hours 3 --hitl-hours 0.5 --tokens-k 120 >/dev/null) || sidecar_ok=0
  (cd "$proj" && uv run --quiet "$pm_main" set-actual --project-root . --plan-file "$epic_t/story-$n-plan.md" \
     --node story --elapsed-hours 1.5 --man-hours 4 --hitl-hours 0.25 --tokens-na >/dev/null) || sidecar_ok=0
done
check "set-estimate and set-actual with v7 addressing exit 0 from the installed copy" "[ '$sidecar_ok' = 1 ]"
tstatus > "$work/tickets-after.json"
check "tickets.py status prints byte-identical JSON after our writes" \
  "cmp -s '$work/tickets-before.json' '$work/tickets-after.json'"
check "the sidecars landed beside the tree (l3io.toml and three plan sidecars)" \
  "[ -f '$epic_t/l3io.toml' ] && [ \"\$(ls '$epic_t'/*-plan.l3io.toml | wc -l)\" -eq 3 ]"
check "the actual events landed in {output_folder}/l3io/events.jsonl" \
  "[ \"\$(grep -c '\"event\": \"actual\"' '$out_folder/l3io/events.jsonl')\" -eq 3 ]"

echo "== measurement hooks on bmad-build and bmad-build-auto (Phase 4 Task 4.2) =="
# /l3io-doctor wire writes the four build hooks into the team files; v7's own renderer must then
# render both skills (an undeclared or mistyped key halts it) with our commands in place, and
# unwire must put the team files back byte for byte (R15).
wire_py="$proj/.agents/skills/l3io-doctor/scripts/wire-in.py"
custom="$proj/_bmad/custom"
snap() { # <dest>: each build team file's bytes, or an "absent" marker
  mkdir -p "$1"
  for f in bmad-build bmad-build-auto; do
    if [ -f "$custom/$f.toml" ]; then cp "$custom/$f.toml" "$1/$f.toml"; else : > "$1/$f.absent"; fi
  done
}
same_as() { # <snapshot dir>
  for f in bmad-build bmad-build-auto; do
    if [ -e "$1/$f.absent" ]; then [ ! -e "$custom/$f.toml" ] || return 1
    else cmp -s "$1/$f.toml" "$custom/$f.toml" || return 1; fi
  done
}
render() { # <skill>
  (cd "$proj" && uv run --quiet --no-project _bmad/scripts/render_skill.py --project-root . \
    --skill ".claude/skills/$1")
}
snap "$work/team-before"
check "wire applies the build hooks (exit 0)" \
  "(cd '$proj' && uv run --quiet '$wire_py' wire --project-root . > '$work/wire.txt')"
check "wire wrote the l3io-build-* entries into both team files" \
  "grep -q 'build-open' '$custom/bmad-build.toml' && grep -q 'build-close' '$custom/bmad-build-auto.toml'"
check "bmad-build renders after wire (exit 0), its prepend naming build-open" \
  "render bmad-build > '$work/render-build.md' && grep -q 'pm_status/__main__.py build-open' '$work/render-build.md'"
check "bmad-build's rendered On Complete (step-05-present.md) names build-close" \
  "grep -rlq 'pm_status/__main__.py build-close' '$proj/_bmad/render/bmad-build'"
check "bmad-build-auto renders after wire (exit 0), with build-open and build-close" \
  "render bmad-build-auto > '$work/render-auto.md' && grep -q 'build-open' '$work/render-auto.md' \
     && grep -q 'pm_status/__main__.py build-close' '$work/render-auto.md'"
check "unwire puts both team files back byte for byte (R15)" \
  "(cd '$proj' && uv run --quiet '$wire_py' unwire --project-root . >/dev/null) && same_as '$work/team-before'"
# A team's own single-slot hook is never overwritten: wire refuses (exit 3) and leaves it.
cp -a "$custom" "$work/custom-before-plant"
printf '[workflow]\non_complete = "Team hook: post to chat."\n' >> "$custom/bmad-build.toml"
cp "$custom/bmad-build.toml" "$work/planted.toml"
code=0; (cd "$proj" && uv run --quiet "$wire_py" wire --project-root . > "$work/wire-planted.txt") || code=$?
check "with a team on_complete planted, wire exits 3" "[ '$code' = 3 ]"
check "the refused entry is named and the team's on_complete is unchanged" \
  "grep -q 'refused.*l3io-build-close' '$work/wire-planted.txt' \
     && grep -q 'Team hook: post to chat.' '$custom/bmad-build.toml' \
     && ! grep -q 'build-close' '$custom/bmad-build.toml'"
(cd "$proj" && uv run --quiet "$wire_py" unwire --project-root . >/dev/null) || true
check "unwire after the refusal leaves the planted team file as the team wrote it" \
  "cmp -s '$work/planted.toml' '$custom/bmad-build.toml'"
rm -rf "$custom" && cp -a "$work/custom-before-plant" "$custom"

echo "== estimation on Sofia (Phase 4 Task 4.3) =="
# wire attaches three single-slot hooks and a menu item to bmad-agent-po's team file. Sofia must
# still render, with our commands at the end of slice.md, ticket.md and replan.md and the menu
# item listed; estimate-entries on the hand-written epic must leave tickets.py's view of the
# tree byte-identical; unwire must restore the team file byte for byte (R15).
po_team="$custom/bmad-agent-po.toml"
if [ -f "$po_team" ]; then cp "$po_team" "$work/po-before.toml"; else : > "$work/po-before.absent"; fi
check "wire applies the Sofia entries (exit 0)" \
  "(cd '$proj' && uv run --quiet '$wire_py' wire --project-root . > '$work/wire-po.txt')"
check "wire wrote the estimation hooks and the l3io-estimate menu item into bmad-agent-po.toml" \
  "grep -q 'estimate-entries' '$po_team' && grep -q 'sidecar-reconcile' '$po_team' \
     && grep -q 'code = \"l3io-estimate\"' '$po_team'"
check "bmad-agent-po renders after wire (exit 0)" "render bmad-agent-po > '$work/render-po.md'"
po_render="$proj/_bmad/render/bmad-agent-po"
ends_with() { # <rendered file name> <text>: the text is in the file's last 40 lines
  f="$(find "$po_render" -name "$1" -type f | head -n 1)"
  [ -n "$f" ] && tail -n 40 "$f" | grep -q "$2"
}
check "slice.md ends with the estimate-entries hook" "ends_with slice.md 'pm_status/__main__.py estimate-entries'"
check "ticket.md ends with the estimate-entries hook" "ends_with ticket.md 'pm_status/__main__.py estimate-entries'"
check "replan.md ends with sidecar-reconcile, then estimate-entries" \
  "ends_with replan.md 'pm_status/__main__.py sidecar-reconcile' && ends_with replan.md 'estimate-entries'"
check "Sofia's rendered menu lists l3io-estimate" \
  "grep -q 'l3io-estimate' '$work/render-po.md' || grep -rq 'l3io-estimate' '$po_render'"
code=0
(cd "$proj" && uv run --quiet "$pm_main" estimate-entries --project-root . --ticket-dir "$epic_t" \
   --class 1=simple --class 2=standard --class 3=complex > "$work/estimate-entries.jsonl") || code=$?
check "estimate-entries on the hand-written epic exits 0 from the installed copy" "[ '$code' = 0 ]"
check "it estimated all three entries and rolled the epic up" \
  "[ \"\$(grep -c '\"entry\"' '$work/estimate-entries.jsonl')\" -eq 3 ] && grep -q '^\\[epic.estimate\\]' '$epic_t/l3io.toml'"
tstatus > "$work/tickets-after-estimate.json"
check "tickets.py status prints byte-identical JSON after estimate-entries" \
  "cmp -s '$work/tickets-before.json' '$work/tickets-after-estimate.json'"

echo "== readiness checks on Sofia's validate (Phase 4 Task 4.4) =="
# The same wire attached two check-list entries and a persistent_facts file to Sofia. Setup must
# have installed the two files they name; her rendered validate-checks.md must carry our Ticket
# and Set lines and her workflow our fact; spec-align.py must run from where setup put it.
spec_align="$proj/_bmad/l3io-pm/scripts/spec-align.py"
fact="$proj/_bmad/l3io-pm/scripts/facts/ac-dimensions.md"
check "setup installed _bmad/l3io-pm/scripts/spec-align.py and facts/ac-dimensions.md" \
  "[ -f '$spec_align' ] && [ -f '$fact' ]"
check "the installed fact file is the canonical AC dimension reference" \
  "cmp -s '$fact' '$pkg/skills/_shared/ac-dimensions.md'"
vchecks="$(find "$po_render" -name validate-checks.md -type f | head -n 1)"
check "the rendered validate-checks.md holds our Ticket check (spec-align.py check-pointers --story-file)" \
  "[ -n '$vchecks' ] && sed -n '/^## Ticket/,/^## Set/p' '$vchecks' | grep -q 'spec-align.py --project-root {project-root} check-pointers --story-file'"
check "the rendered validate-checks.md holds our Set check (estimate-entries --check)" \
  "sed -n '/^## Set/,/^## Tree/p' '$vchecks' | grep -q 'estimate-entries .*--check'"
check "Sofia's rendered session facts name the installed ac-dimensions.md" \
  "grep -q 'file:{project-root}/_bmad/l3io-pm/scripts/facts/ac-dimensions.md' '$work/render-po.md' \
     || grep -rq 'file:{project-root}/_bmad/l3io-pm/scripts/facts/ac-dimensions.md' '$po_render'"
leaf="$epic_t/story-1.md"
{ printf -- '---\nid: 1\ntype: story\ntitle: "Story 1"\nparent: epic-smoke\nrefined: true\n---\n\n# Story 1\n\n'
  printf '## Business acceptance criteria\n\n### Outcome\n\nSmoke passes.\nSpec: none — smoke fixture\n\n'
  printf '### Non-goals\n\nNothing else.\n\n## Technical acceptance criteria\n\n'
  for d in "Interface contracts" "Error and edge case handling" "Observability requirements" \
           "Security considerations" "Testability approach" "Existing-library check"; do
    printf '### %s\n\nN/A — smoke fixture\n\n' "$d"
  done; } > "$leaf"
code=0
(cd "$proj" && uv run --quiet "$spec_align" --project-root . check-pointers --story-file "$leaf" \
   --work-type CODE > "$work/check-pointers.txt" 2>&1) || code=$?
check "spec-align.py check-pointers --story-file passes a ready leaf from the installed path" "[ '$code' = 0 ]"
printf -- '---\nid: 1\ntype: story\ntitle: "Story 1"\n---\n\n# Story 1\n' > "$leaf"
code=0
(cd "$proj" && uv run --quiet "$spec_align" --project-root . check-pointers --story-file "$leaf" \
   > "$work/check-pointers-thin.txt" 2>&1) || code=$?
check "... and finds a thin one (exit 2)" "[ '$code' = 2 ]"
rm -f "$leaf"
code=0
(cd "$proj" && uv run --quiet "$pm_main" estimate-entries --project-root . --ticket-dir "$epic_t" \
   --check > "$work/estimate-check.txt") || code=$?
check "estimate-entries --check passes the estimated epic from the installed copy" "[ '$code' = 0 ]"
tstatus > "$work/tickets-after-checks.json"
check "tickets.py status prints byte-identical JSON after the checks" \
  "cmp -s '$work/tickets-before.json' '$work/tickets-after-checks.json'"

echo "== waves and lanes on Sofia's board, report over v7's tree (Phase 4 Task 4.5) =="
# The same wire attached a board_after hook and two menu items. l3io-plan declares plan-graph.py,
# so setup installed it beside pm_status; her rendered board.md must end with our commands, and
# waves must read the hand-written initiative's live tickets.py status. The views write nothing.
plan_graph="$proj/_bmad/l3io-pm/scripts/plan-graph.py"
check "setup installed _bmad/l3io-pm/scripts/plan-graph.py (declared by l3io-plan)" "[ -f '$plan_graph' ]"
check "board.md ends with the board hook: sidecar-reconcile, then plan-graph.py waves and lanes" \
  "ends_with board.md 'plan-graph.py waves' && ends_with board.md 'plan-graph.py lanes' \
     && ends_with board.md 'pm_status/__main__.py sidecar-reconcile'"
check "Sofia's rendered menu lists l3io-waves and l3io-lanes" \
  "{ grep -q 'l3io-waves' '$work/render-po.md' || grep -rq 'l3io-waves' '$po_render'; } \
     && { grep -q 'l3io-lanes' '$work/render-po.md' || grep -rq 'l3io-lanes' '$po_render'; }"
code=0
(tstatus | (cd "$proj" && uv run --quiet "$plan_graph" waves --status-json -) > "$work/waves.json") || code=$?
check "plan-graph.py waves reads the live tickets.py status from the installed path" "[ '$code' = 0 ]"
check "... one wave holding epic-smoke, with no gate" \
  "jq -e '.scope == \"initiative\" and (.waves | length) == 1 and .waves[0].epics == [\"epic-smoke\"] and .gates == []' '$work/waves.json' >/dev/null"
code=0
(tstatus | (cd "$proj" && uv run --quiet "$plan_graph" lanes --status-json - \
   --lanes-toml "$init/tickets/l3io.toml") > "$work/lanes.json") || code=$?
check "plan-graph.py lanes is inert with no lane assigned" \
  "[ '$code' = 0 ] && jq -e '.lanes == []' '$work/lanes.json' >/dev/null"
code=0
(cd "$proj" && uv run --quiet "$pm_main" report --project-root . --initiative-dir "$init" \
   --format json > "$work/report-v7.json") || code=$?
check "report over the v7 initiative runs v7's tickets.py and exits 0" "[ '$code' = 0 ]"
check "... and reads the epic's three tickets with their actuals" \
  "jq -e '.source == \"v7\" and .epics[0].slug == \"epic-smoke\" and (.epics[0].tickets | length) == 3 and .epics[0].actual.man_hours == 12' '$work/report-v7.json' >/dev/null"
tstatus > "$work/tickets-after-views.json"
check "tickets.py status prints byte-identical JSON after the views" \
  "cmp -s '$work/tickets-before.json' '$work/tickets-after-views.json'"

(cd "$proj" && uv run --quiet "$wire_py" unwire --project-root . >/dev/null) || true
if [ -e "$work/po-before.absent" ]; then
  check "unwire removes the bmad-agent-po team file wire created (R15)" "[ ! -e '$po_team' ]"
else
  check "unwire puts bmad-agent-po.toml back byte for byte (R15)" "cmp -s '$work/po-before.toml' '$po_team'"
fi

echo "== epic closure on bmad-retrospective (Phase 4 Task 4.6) =="
# wire sets bmad-retrospective's single-slot On Complete. v7 must still render it, with our
# epic-close command in the rendered retro-document.md's On Complete; unwire must restore the
# team file byte for byte (R15); and a team's own on_complete must make wire refuse, naming
# both values, and stay untouched (ADR-0020).
retro_team="$custom/bmad-retrospective.toml"
if [ -f "$retro_team" ]; then cp "$retro_team" "$work/retro-before.toml"; else : > "$work/retro-before.absent"; fi
check "wire applies the retrospective entry (exit 0)" \
  "(cd '$proj' && uv run --quiet '$wire_py' wire --project-root . > '$work/wire-retro.txt')"
check "wire wrote l3io-epic-close into bmad-retrospective.toml" "grep -q 'epic-close' '$retro_team'"
check "bmad-retrospective renders after wire (exit 0)" "render bmad-retrospective > '$work/render-retro.md'"
retro_doc="$(find "$proj/_bmad/render/bmad-retrospective" -name retro-document.md -type f | head -n 1)"
check "the rendered retro-document.md's On Complete holds the epic-close command" \
  "[ -n '$retro_doc' ] && sed -n '/^## On Complete/,\$p' '$retro_doc' | grep -q 'pm_status/__main__.py epic-close'"
(cd "$proj" && uv run --quiet "$wire_py" unwire --project-root . >/dev/null) || true
if [ -e "$work/retro-before.absent" ]; then
  check "unwire removes the bmad-retrospective team file wire created (R15)" "[ ! -e '$retro_team' ]"
else
  check "unwire puts bmad-retrospective.toml back byte for byte (R15)" "cmp -s '$work/retro-before.toml' '$retro_team'"
fi
cp -a "$custom" "$work/custom-before-retro-plant"
printf '[workflow]\non_complete = "Team hook: file the retro."\n' >> "$retro_team"
cp "$retro_team" "$work/retro-planted.toml"
code=0; (cd "$proj" && uv run --quiet "$wire_py" wire --project-root . > "$work/wire-retro-planted.txt") || code=$?
check "with a team on_complete planted on bmad-retrospective, wire exits 3" "[ '$code' = 3 ]"
check "the refusal names l3io-epic-close, the team's value and ours, and leaves the team file" \
  "grep -q 'refused.*l3io-epic-close' '$work/wire-retro-planted.txt' \
     && grep -q 'Team hook: file the retro.' '$work/wire-retro-planted.txt' \
     && grep -q 'l3io wants.*epic-close' '$work/wire-retro-planted.txt' \
     && ! grep -q 'epic-close' '$retro_team'"
(cd "$proj" && uv run --quiet "$wire_py" unwire --project-root . >/dev/null) || true
check "unwire after the refusal leaves the planted team file as the team wrote it" \
  "cmp -s '$work/retro-planted.toml' '$retro_team'"
rm -rf "$custom" && cp -a "$work/custom-before-retro-plant" "$custom"
info "refusal: $(grep refused "$work/wire-retro-planted.txt" | head -n 1 | cut -c1-160)..."
# epic-close itself, from the installed copy, on the hand-written epic: it writes only our
# sidecar and state, so tickets.py reads the tree byte-identically afterwards.
retro_md="$init/tickets/epic-smoke/epic-smoke-retrospective.md"
printf -- '---\nepic: epic-smoke\ndate: 2026-11-17\nverdict: accepted\ncriteria: declared\nheadless: true\n---\n# Retro\n' > "$retro_md"
tstatus > "$work/tickets-before-close.json"
code=0
(cd "$proj" && uv run --quiet "$pm_main" epic-close --project-root . --epic-dir "$init/tickets/epic-smoke" \
   --retro-file "$retro_md" --runtime other --since "$(date -u -d '-10 min' +%Y-%m-%dT%H:%M:%SZ)" \
   --man-hours 1 --hitl-hours 0 > "$work/epic-close.txt" 2>&1) || code=$?
check "epic-close runs from the installed copy on the hand-written epic (exit 0)" "[ '$code' = 0 ]"
check "... and records the epic's actual, its closure and the verdict in l3io.toml" \
  "grep -q 'retro_verdict = \"accepted\"' '$epic_t/l3io.toml' && grep -q '^\[epic.closure\]' '$epic_t/l3io.toml' \
     && grep -q '^\[epic.actual\]' '$epic_t/l3io.toml'"
tstatus > "$work/tickets-after-close.json"
check "tickets.py status prints byte-identical JSON after epic-close" \
  "cmp -s '$work/tickets-before-close.json' '$work/tickets-after-close.json'"

echo "== only l3io-pm (Review Focus 3) =="
add_module "$pm_only" "$pkg/skills/l3io-pm" -s '*'
status="$work/pm-only-status.json"
setup "$pm_only" --status > "$status"
check "setup names l3io-doctor as an unmet requirement" \
  "jq -e 'any(.unmet_requirements[]; .requires == \"l3io-doctor\")' '$status' >/dev/null"
hint="$(jq -r '[.unmet_requirements[] | select(.requires == "l3io-doctor") | .install][0] // ""' "$status")"
info "install hint: $hint"
check "the install hint selects the skill by name (--skill l3io-doctor)" \
  "[[ '$hint' == *'--skill l3io-doctor'* ]]"
# The hint names the GitHub repository, whose main branch ships 3.x until 4.0.0. Following it
# against THIS checkout instead checks the part that is this branch's: the skills CLI finds
# l3io-doctor from the repository root, and installing it satisfies the requirement.
add_module "$pm_only" "$pkg" --skill l3io-doctor
setup "$pm_only" --status > "$status"
check "following the hint against this checkout satisfies the requirement" \
  "jq -e '.unmet_requirements == []' '$status' >/dev/null"

echo "== update check (reads main on GitHub) =="
# Informational: setup reads each record's bmod.toml from the update_source on main, which has
# none while 3.x ships there. Asserted only that the check completes and states a result.
while IFS=$'\t' read -r src folder; do
  [ -n "$src" ] || continue
  out="$(setup "$proj" --source-record "$src" "$folder" 2>/dev/null || true)"
  state="$(printf '%s' "$out" | jq -r '.state // empty' 2>/dev/null || true)"
  check "the update check for '$folder' completes with a stated result" "[ -n '$state' ]"
  info "$folder: ${state:-no result} $(printf '%s' "$out" | jq -r '.reason // .version // empty' 2>/dev/null || true)"
done < <(jq -r '.modules[] | select(.module | startswith("l3io-")) | [.update_source, .folder] | @tsv' "$report")

if [ "$fail" -eq 0 ]; then
  echo "smoke: PASS"
else
  echo "smoke: FAIL"; exit 1
fi
