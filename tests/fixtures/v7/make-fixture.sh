#!/usr/bin/env bash
# Build a real BMad v7 project from a pinned upstream commit, for checking claims the v7
# layer design makes against a real install rather than against source reading. Plan:
# docs/superpowers/plans/2026-11-15-bmad-v7-readiness.md, Task 0.2. Results: spec §13.5.
#
# Usage: make-fixture.sh <upstream-commit> <dest-dir>
#   <dest-dir> must not exist; it is the caller's and is never removed by this script.
#
# What it does, in the order a user would:
#   1. fetches bmad-code-org/BMAD-METHOD at exactly <upstream-commit> (no branch float)
#   2. installs core-tools and method with `npx skills add`, for Claude Code AND Codex
#      (`.claude/skills` and `.agents/skills`), so the fixture is not Claude-only
#   3. runs v7's setup.py headlessly, which is what `bmad setup` drives
#
# Network: GitHub (the fetch, and setup's update check) and npm (`npx skills`). The skills
# CLI sends install telemetry unless told not to, so it runs with DO_NOT_TRACK=1.
set -euo pipefail

pin="${1:?usage: make-fixture.sh <upstream-commit> <dest-dir>}"
dest="${2:?usage: make-fixture.sh <upstream-commit> <dest-dir>}"
if [ -e "$dest" ]; then
  echo "make-fixture: $dest already exists; refusing to build into it" >&2
  exit 2
fi

src="$dest/src/upstream"
proj="$dest/proj"
mkdir -p "$src" "$proj"

git -C "$src" init -q
git -C "$src" remote add origin https://github.com/bmad-code-org/BMAD-METHOD.git
git -C "$src" fetch -q --depth 1 origin "$pin"
git -C "$src" checkout -q FETCH_HEAD

git -C "$proj" init -q
export DO_NOT_TRACK=1 DISABLE_TELEMETRY=1
for module in core-tools method; do
  (cd "$proj" && npx --yes skills add "$src/skills/$module" -s '*' \
    -a claude-code -a codex -y --copy >/dev/null)
done

(cd "$proj" && python3 .agents/skills/bmad/scripts/setup.py --project-root . \
  --skill .agents/skills/bmad --root .agents/skills --root .claude/skills) \
  > "$dest/setup.json"

echo "make-fixture: built $proj at $(git -C "$src" rev-parse --short HEAD)"
echo "make-fixture: setup report in $dest/setup.json"
