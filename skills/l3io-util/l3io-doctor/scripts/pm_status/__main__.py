#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18", "tomlkit>=0.13"]
# ///
# pm-status-version: 3.7.1   (machine-readable marker; the doctor reads it off each installed copy — keep at top)
"""
pm-status.py — deterministic, atomic, round-trip-safe writer of l3io's estimates, actuals
and calibration beside v7's ticket tree, and the reader behind its progress report.

Why this exists
---------------
State writes used to be free-form YAML edits the model performed between phases.
Under load or parallel execution those edits were skipped, malformed, or they
reordered/stripped the file. This script makes every write a single deterministic
operation:

  * addressing follows references/status-files.md (§12 for v7's tree),
  * writes are atomic (temp file + os.replace) so a crash never leaves a partial file,
  * ruamel round-trip load/dump preserves key order and comments so diffs stay clean,
  * `verify` is a hard read-back gate the orchestrator can branch on (exit code).

BMad standardizes on `uv run`; the PEP-723 header above lets `uv` provision
ruamel.yaml automatically. Always invoke via `uv run pm-status.py ...` — running
under `python3` directly bypasses the provisioning and fails with
ModuleNotFoundError anywhere ruamel.yaml is not already installed globally.

Subcommands
-----------
  set-actual    --project-root P  --plan-file PATH
                [--elapsed-hours H] [--man-hours H] [--hitl-hours H]
                [--tokens-input K] [--tokens-output K] [--tokens-cache-write K] [--tokens-cache-read K]
                (any --tokens-* requires --model M; under --runtime claude ALL FOUR are
                required once any is given — an explicit 0 counts; [--token-rates JSON]
                overrides its rate card; [--tokens-by-model JSON] for a run on more than
                one model; cost is DERIVED from tokens x rates — --cost is declared but
                always rejected)
                [--tokens-na]   (in place of --tokens-*; runtime=other only, forbidden under runtime=claude)
                [--runtime {claude,codex,copilot,other}] [--no-events] [--session-id ID]
                (writes [actual] in the ticket sidecar <plan-stem>.l3io.toml beside the
                plan and one `actual` event; records NO calibration sample -- build-close
                pairs an actual with the estimate made before the build)
  set-estimate  --project-root P  --ticket-dir DIR  --entry ID
                [--man-hours H] [--hitl-hours H] [--elapsed-hours H] [--tokens-k K]
                [--confidence {low,medium,high}] [--fix-factor F] [--scope-ratio R]
                (writes [entry.<id>].estimate in the epic's tickets/l3io.toml; cost is
                DERIVED — --cost/--cost-low/--cost-high are declared but always rejected;
                estimate-entries computes an estimate from the calibrated bands instead)
  add-test-run  --project-root P  --plan-file PATH  --command CMD  --exit-code N
                (appends {command, exit_code} to completion_evidence.test_runs in the ticket
                sidecar and derives completion_evidence.tests_passing as all(exit_code == 0)
                over the LAST run of each distinct command -- record failures too, a
                re-run of the same command supersedes them for the boolean only)
  usage         [TRANSCRIPT ...]  [--claude-session ID] [--state-root S]
                [--agent NAME] [--epic ID] [--sprint ID] [--story KEY]
                [--since ISO] [--until ISO] [--allow-unidentified]
                [--model M] [--token-rates JSON] [--format {text,json}]
                (sums a session transcript's token usage by class, for feeding
                set-actual; verifies the transcript's sessionId before summing
                and refuses an unconfirmed file unless --allow-unidentified;
                omit TRANSCRIPT to resolve this session's own transcript from
                $CLAUDE_CODE_SESSION_ID or --claude-session; --state-root plus
                node keys derive a --since/--until window from that node's
                dispatch bracket instead of passing one explicitly)
  verify        --project-root P  --plan-file PATH  [--scope story]
                [--require-tokens] [--runtime {claude,codex,copilot,other}] [--token-rates JSON]
                (judges a ticket sidecar's actuals and completion evidence as complete;
                the status is the plan's and v7's, so it is not judged)
  report        --project-root P  --initiative-dir D  [--status-json F]
                [--format tree|json|md] [--out F] [--watch SECS] [--stall-minutes M]
                (tickets.py status -- from F, else v7's installed tickets.py -- plus each
                epic's lane, estimates and ticket actuals from our sidecars; a build
                bracket open in the .inflight spool past --stall-minutes is a stalled
                build)
  dispatch      --state-root S  --event {open,close}  --agent NAME
                [--epic ID] [--sprint ID] [--story KEY] [--session-id ID]
                (appends a dispatch_open/dispatch_close event to events.jsonl;
                feeds report's stall detection and marks the child/orchestration
                spend boundary -- records timestamps only, never a token count)
  calibration   {show,migrate-metrics}  --state-root S  [--format {text,json}]
                (show inspects pm-calibration.yaml -- a missing file is a normal cold-start
                state, not an error; migrate-metrics applies the file's schema migrations)
  rates         [--model M] [--token-rates JSON]
                (prints the effective per-class token rate table -- shipped
                defaults merged with any --token-rates/modules.l3io-pm
                override -- so what actually prices tokens is inspectable
                without reading source or guessing; read-only)
  adr-reserve   --state-root S  --epic ID  --slug SLUG  [--count N]
                (reserves N sequential ADR numbers under a lock, before dispatch;
                prints one zero-padded number per line; see adr_register_path)
  notice        --state-root S  --key KEY
                (records a one-time-ever advisory notice in {state-root}/.notices.yaml
                under flock, keyed on KEY alone -- there is no session concept that
                outlives one skill invocation, so this is scoped to the project, not a
                session; exit 0 = not yet emitted for KEY (and now recorded), exit 1 =
                already emitted, exit 2 = usage error OR an unexpected recording failure
                (never conflated with exit 1); advisory only -- a damaged notices file
                never blocks the caller, but a failed write is reported, not silently
                treated as success)
  sidecar-reconcile  --project-root P  --initiative-dir D  [--moved-json J]
                (after `tickets.py move`: J is its stdout -- the JSON, a file holding it,
                or - for stdin. Repoints [entry.<old_id>] to [entry.<id>] in the
                destination's l3io.toml and moves <plan-stem>.l3io.toml beside the moved
                plan. Without J, sweeps D: a plan sidecar whose plan is gone is moved beside
                the one same-named plan elsewhere in D; an [entry.<id>] whose id no
                tickets.toml has is reported. One line per action; commits what it
                changed as `chore(l3io): reconcile sidecars`; exit 0, 2 on usage, 1 when
                the commit failed)
  estimate-entries  --project-root P  --ticket-dir D  [--entry ID ...]
                [--class ID=CLASS ...]  [--force]  [--check]  [--model M]
                [--token-rates JSON]
                (v7 estimation, run by Sofia's slice/refine/replan hooks and `l3io-plan
                estimate`: writes [entry.<id>] in D's l3io.toml -- class, fingerprint,
                estimated_at, and the band x calibration estimate (compute_story_estimate) -- for each
                entry that is new, whose description/verify/covers changed, whose --class
                differs, that --entry names, or every one under --force; never an entry
                with a hand-set estimate in tickets.toml. Then rolls [epic].estimate up
                as the entries' sum + the epic closure band + the orchestration band, no
                sprint term. An entry to write with no class is exit 2, nothing written.
                One JSON line per entry written and one for the epic; commits l3io.toml as
                `chore(l3io): estimates <epic>`; exit 3 for an unknown --entry, 1 when the
                commit failed. --check is Sofia's validate Set check: it writes nothing,
                prints one line per entry with no estimate of ours or by hand, and exits
                1 when there is any; it takes no --entry, --class or --force)
  set-lane      --project-root P  --initiative-dir D  --epic SLUG  --lane N
                (writes [epic.<SLUG>].lane in the initiative's l3io.toml and commits it as
                `chore(l3io): lane <SLUG>`. N is a number in 1..lane_count, never a name;
                refused while modules.l3io-pm.lane_count is unset or 1 (lanes off). Exit 2
                on usage, 3 for an epic the initiative does not list, 1 when the commit
                failed)
  build-open    --project-root P  --agent {bmad-build,bmad-build-auto}  [--plan-file F]
                [--session-id ID]
                (v7 build hook, activation_steps_prepend: opens the build's measurement
                bracket in {output_folder}/l3io/.inflight/, a spool that ignores itself, so
                no tracked or untracked file appears; a stale open under the same key or
                for the same plan is retired as abandoned)
  build-close   --project-root P  --agent {bmad-build,bmad-build-auto}  [--plan-file F]
                --runtime {claude,codex,copilot,other}  [--model M]  --man-hours H
                --hitl-hours H  [--test-run 'CMD=EXIT' ...]  [--token-rates JSON]
                [--tokens-input K --tokens-output K [--tokens-cache-read K]]
                [--session-id ID]
                (v7 build hook, on_complete: appends the dispatch_open/dispatch_close pair,
                appends the bracket to the ticket sidecar's `dispatch` list and writes
                [actual] as their sum -- tokens read from the Claude transcript over the
                bracket; typed under codex (input, output, cache-read, --model) and
                copilot (input, output), where a missing count is exit 2 before any
                write; N/A under other; cost derived -- records each --test-run,
                takes one calibration sample when the plan reads built and its entry was
                estimated beforehand, then commits each path it wrote inside the worktree
                as `chore(l3io): actuals <ticket>`. Exit 4 when no bracket was open: the
                close is recorded as unmatched)
  epic-close    --project-root P  --epic-dir D  --retro-file F
                --runtime {claude,codex,copilot,other}  [--model M]  --man-hours H
                --hitl-hours H  [--since ISO]  [--token-rates JSON]
                [--tokens-input K --tokens-output K [--tokens-cache-read K]]
                [--session-id ID]
                (v7 retrospective hook, on_complete: appends the run to the epic's
                [[epic.closure_runs]], writes [epic.closure] as their sum and [epic.actual]
                as every ticket sidecar under D/tickets/ plus the closure, reads `verdict`
                from F's frontmatter into [epic].retro_verdict, takes one closure
                calibration sample when [epic].estimate exists and the verdict is
                accepted, then commits what it wrote as `chore(l3io): epic close <slug>`.
                The window is --since, else the first turn of this Claude session that
                touched F. Writes no status. Exit 2 on usage with nothing written, 3 when
                F does not exist, 1 when the commit failed)
  sync-agent-instructions  --runtime {claude,codex,copilot,other}  --project-root P
                [--body-file F] [--version V]  (--apply | --remove | --check)
                (creates, replaces or removes the marker-wrapped l3io block in the running
                harness's instruction file, under a lock held across read and write; never
                deletes the file. A block already present in ANOTHER harness's instruction
                file is refreshed in place by --apply and stripped by --remove -- ours to
                keep current wherever it is -- but never created there. exit 1 = --check
                found no block for this harness, exit 2 = usage, an undecodable file, or
                ambiguous markers, exit 3 = --check found another harness's file holding a
                stale copy)

Addressing (status-files.md §12). Every verb that writes our sidecars takes --project-root P
and a v7 address: --ticket-dir DIR --entry ID for an entry's estimate, --plan-file PATH for a
ticket's actuals, test runs and verify. Project-wide state (events.jsonl,
pm-calibration.yaml) lives at the main checkout's {output_folder}/l3io/ from any worktree.
No v7 file (tickets.toml, leaf, plan) is ever written; a hand-set `estimate` or
`l3io_<name>` on a tickets.toml entry is read as an override. The 3.x node addressing
(--state-root with --story/--epic/--sprint), and the migration-only import-node,
import-actual, estimate-story, estimate-rollup and `calibration redrive`, retired with the
3.x tree in Phase 6: migrate-engine.py reads that tree and writes these sidecars, and
estimate-entries is the v7 address of estimate-story and estimate-rollup.

Exit codes: 0 = success/verified, 1 = notice already emitted for this key
(notice only), 2 = usage error or, for notice only, an unexpected recording failure,
3 = node not found, 4 = verification failure (missing/invalid field).
Errors go to stderr; machine output (verify summaries) goes to stdout.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys

# v7 installs this package under `_bmad/l3io-pm/scripts/`, which a project may commit; a
# `__pycache__/` written there is an untracked file, and `bmad-build-auto` refuses to start on
# any (step-01-clarify-and-route.md:60). v7's own scripts set the same flag.
sys.dont_write_bytecode = True

# --------------------------------------------------------------------------- #
# SCRIPT-PATH BOOTSTRAP. Nothing relative may appear above this block.
#
# The shipped binding runs this file as a SCRIPT (`uv run .../pm_status/__main__.py`),
# where `__package__` is empty and every relative import below raises "attempted
# relative import with no known parent package". Under `import pm_status` -- which is
# how the suite reaches it -- there IS a package and they resolve, so the suite cannot
# see that failure on its own. TestInvocationModes runs the script path for exactly
# that reason, including one test that plants a relative import into a copy of the
# package and fails if this block is gone.
#
# It loads THIS directory as a package named `pm_status` BY PATH and re-enters through
# it, so the relative imports below and the `sys.modules[__name__] = _main` facade in
# __init__.py behave exactly as they do under `import pm_status`. By path, never by
# name: an installed directory need not be named `pm_status` -- l3io 3.x installed it as
# `pm-status`, with a hyphen, which is not an importable identifier -- and a bootstrap
# that imported the name passed on a toy fixture and failed on the real install.
#
# The exit value is read back out of sys.modules rather than off the module object this
# block created: executing __init__.py REPLACES sys.modules["pm_status"] with the
# __main__ module object, and that is the one carrying `main`.
# --------------------------------------------------------------------------- #
if not __package__ and __name__ == "__main__":
    _pkg_dir = os.path.dirname(os.path.abspath(__file__))
    _spec = importlib.util.spec_from_file_location(
        "pm_status",
        os.path.join(_pkg_dir, "__init__.py"),
        submodule_search_locations=[_pkg_dir],
    )
    sys.modules["pm_status"] = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(sys.modules["pm_status"])
    sys.exit(sys.modules["pm_status"].main())

# The dependency root (`core`, see pm_status/core/__init__.py) and the node layer
# (`nodes`, see pm_status/nodes/__init__.py). Two import styles, and the difference is
# load-bearing. The names the suite mock.patches are reached through the MODULE OBJECT
# (`core._load(...)`, `core._atomic_dump(...)`): a `from .core import _load` binding here
# would be a private
# copy that a patch on core could not reach, so the test would pass while guarding
# nothing. Everything else is re-exported by name, because `pm_status.<name>` is this
# module's globals and the suite reads several hundred of them directly through the
# __init__.py facade.
#
# The split is per patch target, not per module, and a patched name is left OUT of the
# re-export lists below: a `pm._load` binding beside `pm.core._load` is a second thing to
# patch, and the wrong one passes silently. TestPatchTargetsAreDefinedInMain is
# the standing guard. `nodes` also carries check 26's resolver-section markers, so it is
# the one file in this package allowed to assemble a state path; nothing here does.
#
# `metrics` is a DIRECTORY of modules (events, rates, calibration, estimates, spend, report,
# actuals_usage -- see its __init__.py), so its patch targets are two levels down.
# `metrics.estimates.compute_story_estimate` and `metrics.actuals_usage.dispatch_window` are
# reached module-qualified and none is
# re-exported, here or by `metrics/__init__.py`. `adr` is the ADR number allocator, one verb.
# FOUR of the modules are imported for a LIVE caller: `build_parser` calls
# `<module>.register(sub)` on each of adr, instructions, metrics and verbs, so none
# of them carries a `noqa`. That is the honest state -- a `noqa`
# over a module ruff can see used is a justification that reads as true and is not -- and it
# means ruff now reports the one failure mode distributed registration introduces from this
# side: delete a `register()` call and its import goes unused and FAILS `check:lint:py`,
# before TestSubcommandRegistration is even reached.
#
# `core` and `nodes` are the exceptions and keep their own `noqa`: neither owns a verb (the
# dependency root and the node layer, not verb buckets), so nothing here calls them and they
# are bound purely for the suite's `pm.core.<name>` and `pm.nodes.<name>` patch targets. Its directive is its own, not shared, so if another
# module later loses its caller that is reported separately rather than absorbed.
#
# `sidecar` is the package's eighth module (4.x sidecars beside v7's ticket tree). Its
# `__init__` is a low layer -- `metrics` and `sidecar.verbs` import from it -- so it owns no
# `register` and is bound here as `pm.sidecar` for the suite. Its verbs live one level down
# in `sidecar.verbs`, which sits above `verbs` and `metrics` and is imported by name: its
# `register` adds `set-estimate`, `set-actual`, `add-test-run`, `verify`,
# `sidecar-reconcile` and, from `sidecar.estimate` and `sidecar.lanes`, `estimate-entries`
# and `set-lane`.
#
# `bracket` is the ninth: `build-open` and `build-close`, the measurement bracket v7's
# `bmad-build` and `bmad-build-auto` run through their hooks. It sits above `sidecar.verbs`
# and `metrics`, and nothing imports it but `build_parser` and `sidecar.closure`. It is not
# named `build/` because a consumer's `.gitignore` commonly ignores every `build/`, which
# would drop it from a committed `_bmad/`.
#
# `sidecar.closure` holds `epic-close`, the hook v7's `bmad-retrospective` runs. It sits above
# `bracket`, whose token and summing helpers it reuses, so `sidecar.verbs` cannot register it
# without a cycle; `build_parser` does, bound here as `sidecar_closure`.
from . import (
    adr,
    bracket,
    core,  # noqa: F401 -- re-export only
    instructions,
    metrics,
    nodes,  # noqa: F401 -- re-export only
    sidecar,  # noqa: F401 -- re-export only
    verbs,
)

# The instruction-block leaf, re-exported by name: nothing in the suite patches a name it
# defines. It reaches `core` as a module object itself.
from .adr import (
    load_adr_register,  # noqa: F401 -- re-export only
)
from .core import (
    _LOCK_IGNORE_CHECKED,  # noqa: F401 -- re-export only
    METRIC_FIELDS,  # noqa: F401 -- re-export only
    PM_STATUS_VERSION,
    PMError,  # noqa: F401 -- re-export only
    _hashable_field,  # noqa: F401 -- re-export only
    _indexable_key,  # noqa: F401 -- re-export only
    _is_na,  # noqa: F401 -- re-export only
    _iter_count,  # noqa: F401 -- re-export only
    _now_iso,  # noqa: F401 -- re-export only
    _parse_iso,  # noqa: F401 -- re-export only
    _yaml,  # noqa: F401 -- re-export only
    adr_register_path,  # noqa: F401 -- re-export only
    append_event,  # noqa: F401 -- re-export only
    calibration_lock,  # noqa: F401 -- re-export only
    calibration_path,  # noqa: F401 -- re-export only
    events_path,  # noqa: F401 -- re-export only
)
from .instructions import (
    BlockError,  # noqa: F401 -- re-export only
    apply_block,  # noqa: F401 -- re-export only
    find_block,  # noqa: F401 -- re-export only
    remove_block,  # noqa: F401 -- re-export only
)
from .metrics.actuals_usage import (
    CLAUDE_SESSION_ENV,  # noqa: F401 -- re-export only
    discover_session_transcript,  # noqa: F401 -- re-export only
    read_transcript_usage,  # noqa: F401 -- re-export only
    resolve_session_transcript,  # noqa: F401 -- re-export only
)
from .metrics.calibration import (
    CALIBRATION_METRICS_MARKER,  # noqa: F401 -- re-export only
    CALIBRATION_SCHEMA_VERSION,  # noqa: F401 -- re-export only
    CLASSIFICATIONS,  # noqa: F401 -- re-export only
    COLD_START_FIX_FACTOR,  # noqa: F401 -- re-export only
    COLD_START_SCOPE_RATIO,  # noqa: F401 -- re-export only
    TOKEN_BASIS_MARKER,  # noqa: F401 -- re-export only
    WALL_CLOCK_METRICS,  # noqa: F401 -- re-export only
    _component_samples,  # noqa: F401 -- re-export only
    active_closure_ratio,  # noqa: F401 -- re-export only
    active_fix_factor,  # noqa: F401 -- re-export only
    active_orchestration_fraction,  # noqa: F401 -- re-export only
    active_scope_ratio,  # noqa: F401 -- re-export only
    derive_story_sample,  # noqa: F401 -- re-export only
    load_calibration,  # noqa: F401 -- re-export only
    migrate_calibration,  # noqa: F401 -- re-export only
    migrate_calibration_metrics,  # noqa: F401 -- re-export only
    migrate_calibration_token_basis,  # noqa: F401 -- re-export only
    new_calibration,  # noqa: F401 -- re-export only
    record_story_sample,  # noqa: F401 -- re-export only
    save_calibration,  # noqa: F401 -- re-export only
    weighted_ratio,  # noqa: F401 -- re-export only
)
from .metrics.estimates import (
    BASE_BANDS,  # noqa: F401 -- re-export only
    DEFAULT_ESTIMATE_MODEL,  # noqa: F401 -- re-export only
    observed_mix,  # noqa: F401 -- re-export only
    split_tokens,  # noqa: F401 -- re-export only
)

# The measurement layer's exports, by name. The three mock.patch targets --
# `compute_story_estimate`, `rollup_parent_estimate` (metrics/estimates) and
# `dispatch_window` (metrics/actuals_usage) -- are deliberately absent, so a patch
# repointed to `pm.metrics.<mod>.<name>` without the matching call-style change here
# is a NameError rather than a patch that quietly reaches nobody.
from .metrics.events import (
    _total_blocked_hours,  # noqa: F401 -- re-export only
    open_dispatches,  # noqa: F401 -- re-export only
)
from .metrics.rates import (
    COLD_START_TOKEN_MIX,  # noqa: F401 -- re-export only
    FRESH_TOKEN_CLASSES,  # noqa: F401 -- re-export only
    TOKEN_CLASSES,  # noqa: F401 -- re-export only
    TOKEN_RATES,  # noqa: F401 -- re-export only
    cost_from_tokens,  # noqa: F401 -- re-export only
)
from .sidecar import closure as sidecar_closure
from .sidecar import verbs as sidecar_verbs


# CLI
#
# REGISTRATION IS DISTRIBUTED (design §3.2). Each module registers its OWN verbs through
# its `register(subparsers)`; this function creates the root parser and the subparsers
# object and calls them in the fixed order below. The 4.0.0 v7 cut then removes a bucket's
# verbs by deleting its directory and one line here, instead of hand-editing a 520-line
# function and hoping no neighbouring verb is caught in the edit.
#
# THE ORDER IS THE SURFACE. argparse lists subcommands in registration order, so this tuple
# decides what `pm-status.py --help` prints. It is the order of each module's FIRST verb in
# the pre-split function — verbs led, then metrics, adr, instructions — so
# the listing stays as close to the shipped one as a per-module grouping can be. Every
# individual subcommand's `--help` is byte-identical to the pre-split capture in
# `.superpowers/sdd/2026-10-23-pm-status-package-split/cli-surface-before.txt`; what the
# split necessarily changes is the ORDER of the top-level listing, because the pre-split
# function interleaved the buckets (verbs held positions 1-5, 8-11, 15-20 and 42) and no
# contiguous per-module grouping can reproduce that.
#
# `core` and `nodes` have no `register`: neither owns a verb. Neither is called here, and neither
# may grow an empty `register` to look symmetrical — an empty hook is a place for a
# verb to be registered by accident.
#
# TestSubcommandRegistration is the standing guard: it pins every name, and attributes a
# shortfall to the module whose call went missing.
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pm-status.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    verbs.register(sub)
    metrics.register(sub)
    adr.register(sub)
    instructions.register(sub)
    sidecar_verbs.register(sub)
    bracket.register(sub)
    sidecar_closure.register(sub)

    p.add_argument("--version", action="version", version=f"pm-status.py {PM_STATUS_VERSION}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
