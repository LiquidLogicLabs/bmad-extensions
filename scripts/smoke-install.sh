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

# Review Focus 4, the half that holds: a 3.x answer in _bmad/custom/config.toml still resolves.
# (Setup asks again regardless -- plan Task 2.3's note; the migration copies the answer across.)
printf '\n[modules.l3io-pm]\nlane_count = "3"\n' >> "$proj/_bmad/custom/config.toml"
check "a lane_count in _bmad/custom/config.toml resolves through v7's merge" \
  "(cd '$proj' && uv run --quiet --no-project _bmad/scripts/resolve_config.py --project-root . \
     --key modules.l3io-pm.lane_count) | jq -e '.\"modules.l3io-pm.lane_count\" == \"3\"' >/dev/null"

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
