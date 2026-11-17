#!/usr/bin/env bash
# Install, upgrade, or remove this extension on a BMad v7 project.
#
# What an install is on v7
# ------------------------
# Three steps, in this order, and this script does the first: `npx skills add` of each module
# folder (`skills/<code>`) installs its skills; `bmad setup <code>` -- in your agent -- installs
# the scripts those skills declare under `_bmad/<code>/scripts/` and asks the module's
# questions; `/l3io-doctor wire` attaches l3io's hooks to BMad's own skills. `npm run
# smoke:install` runs the same sequence against a real v7 project. An upgrade is the same
# three steps again: `skills add` replaces each skill folder, setup rebuilds the declared
# scripts (and offers any migration that now applies, l3io-pm's 3.x -> 4.x included), and
# wire adds whatever entries the release added.
#
# Setup is not run here, deliberately: it asks questions (l3io-pm's `lane_count`) that are the
# user's to answer, through BMad's own `bmad setup` flow.
#
# Where this script lives, and why
# --------------------------------
# The repository ROOT, deliberately not skill payload. A first install cannot come from
# payload -- there is no payload yet -- so the one entry point that has to work on an empty
# tree must be fetchable on its own.
#
# `--action clean` compares SHA-256 hashes against each skill's `payload-manifest.json` to
# decide what is safe to delete. That is data handling that has outgrown shell by this
# package's own standard (`standards-shell.md`), so it dispatches to `clean-payload.py`, which
# IS payload: cleaning requires an install, and an install means the helper is on disk.
set -euo pipefail

SOURCE_DEFAULT="LiquidLogicLabs/bmad-extensions"
MODULES_DEFAULT="l3io-pm,l3io-util,l3io-sec,l3io-arch"
TOOLS_DEFAULT="claude-code"

# Where `skills add` puts skills; v7's setup reads `.agents/skills` first.
SKILL_ROOTS=(".agents/skills/l3io-doctor" ".claude/skills/l3io-doctor")

action=""
directory="."
apply=0
modules="$MODULES_DEFAULT"
tools="$TOOLS_DEFAULT"
source_ref="$SOURCE_DEFAULT"
dry_run_requested=0

log() { printf '%s\n' "$*" >&2; }
die() {
    printf 'l3io-install: %s\n' "$*" >&2
    exit 2
}

usage() {
    cat <<'EOF'
Usage: install.sh --action {install|upgrade|clean} [options]

Actions
  --action install   Add this package's modules to a BMad v7 project: one `npx skills add`
                     per module folder. Then, in your agent: `bmad setup <code>` for each
                     module, and `/l3io-doctor wire`. Refuses when BMad v7 is not installed.
  --action upgrade   The same `skills add` over an existing l3io install; then re-run
                     `bmad setup` (it rebuilds the declared scripts and offers any migration
                     that now applies) and `/l3io-doctor wire`. Requires an install.
  --action clean     Remove THIS extension's payload only, and nothing else. Reports what it
                     would do and changes nothing unless --apply is given. Run
                     `/l3io-doctor unwire` first. Requires an install.

Options
  --directory DIR    Project directory (default: .)
  --apply            For clean: actually delete. Without it, clean is a dry run.
  --modules LIST     Module folders, comma-separated (default: l3io-pm,l3io-util,l3io-sec,l3io-arch).
                     l3io-util is required with l3io-pm.
  --tools LIST       Agent codes for `skills add -a`, comma-separated (default: claude-code)
  --source SRC       Where the modules come from: owner/repo or a local checkout
                     (default: LiquidLogicLabs/bmad-extensions)
  -n, --dry-run      Print the commands that would run, and run nothing.
  -h, --help         This text.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --action | --directory | --modules | --tools | --source)
            [[ $# -ge 2 ]] || die "$1 needs a value"
            case "$1" in
                --action) action="$2" ;;
                --directory) directory="$2" ;;
                --modules) modules="$2" ;;
                --tools) tools="$2" ;;
                --source) source_ref="$2" ;;
            esac
            shift 2
            ;;
        --action=*) action="${1#*=}"; shift ;;
        --directory=*) directory="${1#*=}"; shift ;;
        --modules=*) modules="${1#*=}"; shift ;;
        --tools=*) tools="${1#*=}"; shift ;;
        --source=*) source_ref="${1#*=}"; shift ;;
        --apply) apply=1; shift ;;
        -n | --dry-run) dry_run_requested=1; shift ;;
        -h | --help) usage; exit 0 ;;
        *) die "unknown argument: $1 (try --help)" ;;
    esac
done

[[ -n "$action" ]] || {
    usage >&2
    die "--action is required; there is no safe default, because the right steps depend on whether this project is already installed"
}

[[ -d "$directory" ]] || die "--directory $directory does not exist"
project="$(cd "$directory" && pwd -P)"

# BMad v7 is installed when its setup script is: `bmad setup` writes `_bmad/scripts/setup.py`.
v7=0
[[ -f "$project/_bmad/scripts/setup.py" ]] && v7=1
installed=0
for root in "${SKILL_ROOTS[@]}"; do
    [[ -f "$project/$root/SKILL.md" || -f "$project/$root/payload-manifest.json" ]] && installed=1
done

run() {
    if [[ "$dry_run_requested" -eq 1 ]]; then
        printf 'would run: %s\n' "$*"
        return 0
    fi
    log "+ $*"
    "$@"
}

add_modules() {
    local m t
    local -a agents=()
    IFS=',' read -r -a tool_list <<<"$tools"
    for t in "${tool_list[@]}"; do agents+=(-a "$t"); done
    IFS=',' read -r -a module_list <<<"$modules"
    for m in "${module_list[@]}"; do
        [[ "$m" == "_shared" ]] && die "skills/_shared is source, not a module"
        (cd "$project" && run npx --yes skills add "$source_ref/skills/$m" -s '*' "${agents[@]}" -y --copy)
    done
    log ""
    log "Next, in your agent: bmad setup <code> for each module (${modules//,/, }), then /l3io-doctor wire."
}

case "$action" in
    install)
        [[ "$v7" -eq 1 ]] || die "BMad v7 is not installed at $project (looked for _bmad/scripts/setup.py) -- install BMad v7's core-tools and method and run bmad setup first; l3io 4.x runs on BMad v7 only."
        add_modules
        ;;
    upgrade)
        [[ "$installed" -eq 1 ]] || die "no l3io install found at $project (looked for ${SKILL_ROOTS[*]}) -- there is nothing to upgrade. Run --action install first."
        [[ "$v7" -eq 1 ]] || die "BMad v7 is not installed at $project (looked for _bmad/scripts/setup.py) -- l3io 4.x runs on BMad v7 only; a 3.x project stays on l3io 3.x until BMad v7 is installed."
        add_modules
        ;;
    clean)
        helper=""
        for root in "${SKILL_ROOTS[@]}"; do
            if [[ -f "$project/$root/scripts/clean-payload.py" ]]; then
                helper="$project/$root/scripts/clean-payload.py"
                break
            fi
        done
        [[ "$installed" -eq 1 || -n "$helper" ]] || die "no l3io install found at $project (looked for ${SKILL_ROOTS[*]}) -- there is no payload manifest to decide what is safe to delete, and guessing is how an over-broad delete happens."
        [[ -n "$helper" ]] || die "no clean-payload.py found under $project (looked in ${SKILL_ROOTS[*]}) -- this extension's payload is absent or already removed, so there is nothing to clean and nothing to decide it with."
        clean_args=(--project-root "$project")
        [[ "$apply" -eq 1 ]] && clean_args+=(--apply)
        if [[ "$dry_run_requested" -eq 1 ]]; then
            printf 'would run: uv run %s %s\n' "$helper" "${clean_args[*]}"
            exit 0
        fi
        # Not `exec`: the trailing advice below is part of the action's output.
        uv run "$helper" "${clean_args[@]}"
        if [[ "$apply" -eq 0 ]]; then
            log ""
            log "Nothing was changed. Re-run with --apply to delete what is listed above."
        fi
        ;;
    *) die "unknown --action: $action (expected install, upgrade, or clean)" ;;
esac
