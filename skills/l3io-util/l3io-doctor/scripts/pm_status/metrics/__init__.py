"""pm_status.metrics -- the measurement layer: calibration, estimates, spend, reporting.

Everything that MEASURES rather than changes state. It sits above `nodes` and below the
issue store, the status verbs and the plan operations: it reads and writes node files
through `nodes`, and nothing below it reads anything here.

A DIRECTORY rather than a single module, because `calibration` alone is ~1,280 lines and
the package's per-file budget is 1,500 — enforced since 2026-10-23 by `check:docs` check 12,
which until then was a number stated here and in the split plan and checked nowhere.
(`issues` is a directory for the same reason; this file used to claim to be the only one.)
The seven modules are a strict layering, and the order below is the import order:

    events, rates     leaves -- the event log's readers; token classes and pricing
    calibration       reads both (blocked hours exclude a metric; fresh tokens band it)
    estimates         applies calibration's ratios to rates' prices
    spend             a leaf of its own -- attribution of actuals to the three buckets
    report            the progress model: reads events for dwell, spend for attribution
    actuals_usage     writes actuals, prices through rates, appends through calibration

There is no edge in the other direction anywhere, so a cycle between two of these files is
a design error, not a plumbing problem to route around with a deferred import.

THE EVENT-LOG WRITER IS NOT HERE. `append_event`, `events_path` and `_event_keys` are in
`core`: every status write appends, including the node layer below this one, so the writer
is a primitive. `metrics.events` holds the READERS only. Do not pull the writer up.

This file imports the seven submodules and re-exports NOTHING OF THEIRS. That is
deliberate: a name re-exported here would sit beside `metrics.<mod>.<name>` as a second
binding of the same function, and `mock.patch` on one would not reach the other.
`__main__.py` re-exports what the facade needs, from the defining module, and leaves the
three patch targets out. Everything `register` wires is reached as `<submodule>.<name>`.
`set-actual` is registered by `sidecar.verbs`, which owns its v7 handler.
"""
from __future__ import annotations

from . import (  # noqa: F401 -- submodule imports, so `metrics.<mod>` resolves on the package
    actuals_usage,
    calibration,
    estimates,
    events,
    rates,
    report,
    spend,
)


# --------------------------------------------------------------------------- #
# CLI registration -- this bucket's verbs (design §3.2; the contract and the reason
# are in core's own register section).
#
# Written against the SUBMODULE OBJECTS (`actuals_usage.cmd_usage`, not a
# `from .actuals_usage import cmd_usage` at the top of this file) for the reason this
# module's docstring gives: a name re-exported here would sit beside `metrics.<mod>.<name>`
# as a second binding, and `mock.patch` on one would not reach the other. `register` is a
# function this file DEFINES, so it adds no such second binding.
# --------------------------------------------------------------------------- #
def register(sub):
    rp = sub.add_parser("report", help="progress over a v7 initiative (read-only unless --out)")
    rp.add_argument("--project-root", dest="project_root", required=True,
                    help="the v7 project root")
    rp.add_argument("--initiative-dir", dest="initiative_dir", required=True,
                    help="the v7 initiative folder")
    rp.add_argument("--status-json", dest="status_json", default="",
                    help="`tickets.py status` JSON (a file, or - for stdin) instead of "
                         "running v7's tickets.py")
    rp.add_argument("--format", choices=["tree", "json", "md"], default="tree")
    rp.add_argument("--out", default="", help="write to this file instead of stdout")
    rp.add_argument("--watch", type=int, default=0, metavar="SECS",
                    help="re-render on an interval (tree only in practice)")
    rp.add_argument("--stall-minutes", dest="stall_minutes", type=float,
                    default=events.DEFAULT_STALL_MINUTES,
                    help="flag build brackets open longer than this (default 15)")
    rp.set_defaults(func=report.cmd_report)

    dp = sub.add_parser("dispatch", help="record a subagent dispatch open/close")
    dp.add_argument("--state-root", required=True)
    dp.add_argument("--event", required=True, choices=["open", "close"])
    dp.add_argument("--agent", required=True)
    dp.add_argument("--epic", default="")
    dp.add_argument("--sprint", default="")
    dp.add_argument("--story", default="")
    dp.add_argument("--session-id", dest="session_id", default=None)
    dp.set_defaults(func=events.cmd_dispatch)

    up = sub.add_parser("usage", help="sum a session transcript's token usage, by class")
    up.add_argument("transcript", nargs="*",
                    help="transcript .jsonl file(s) or directory(ies); omit to resolve this "
                         "session's own transcript from $" + actuals_usage.CLAUDE_SESSION_ENV)
    up.add_argument("--claude-session", dest="claude_session", default="",
                    help="the Claude session id the transcript must belong to (NOT the l3io "
                         "run --session-id); defaults to $" + actuals_usage.CLAUDE_SESSION_ENV)
    up.add_argument("--state-root", default="", help="state root, to read events.jsonl")
    up.add_argument("--agent", default="", help="scope to this agent's dispatch bracket")
    up.add_argument("--epic", default="", help="scope to this epic")
    up.add_argument("--sprint", default="", help="scope to this sprint")
    up.add_argument("--story", default="", help="scope to this story")
    up.add_argument("--since", default="", help="ISO timestamp lower bound")
    up.add_argument("--until", default="", help="ISO timestamp upper bound")
    up.add_argument("--allow-unidentified", action="store_true",
                    help="sum a file that cannot be confirmed as this session's transcript")
    up.add_argument("--model", default="", help="also price the total at this model's rates")
    up.add_argument("--token-rates", dest="token_rates", default="",
                    help="JSON overrides for the rate table")
    up.add_argument("--format", choices=["text", "json"], default="text")
    up.set_defaults(func=actuals_usage.cmd_usage)

    cal = sub.add_parser("calibration", help="inspect the calibration file")
    cal.add_argument("action", choices=["show", "migrate-metrics"])
    cal.add_argument("--state-root", required=True)
    cal.add_argument("--format", choices=["text", "json"], default="text")
    cal.set_defaults(func=calibration.cmd_calibration)

    rt = sub.add_parser("rates", help="print the effective token rate table (read-only)")
    rt.add_argument("--model", default="")
    rt.add_argument("--token-rates", dest="token_rates", default="",
                    help="JSON object of per-model rate overrides")
    rt.set_defaults(func=rates.cmd_rates)
