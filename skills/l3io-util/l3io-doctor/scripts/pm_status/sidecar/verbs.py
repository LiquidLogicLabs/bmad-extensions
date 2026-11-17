"""pm_status.sidecar.verbs -- set-estimate, set-actual, add-test-run and verify on v7's tree.

Each verb takes `--project-root` and a v7 address: `--ticket-dir DIR --entry ID` for an
estimate, `--plan-file PATH` for an actual, a test run or a verify. The 3.x node addressing
(`--state-root` with `--story`/`--epic`/`--sprint`) retired with the 3.x tree in Phase 6;
the migration (`migrate-engine.py`) reads that tree and writes these sidecars.

What each v7 verb writes (status-files.md §12):

  set-estimate  `[entry.<id>].estimate` in the epic's `l3io.toml`
  set-actual    `[actual]` in `<plan-stem>.l3io.toml`, plus one `actual` event in
                `{state_root}/events.jsonl`
  add-test-run  `completion_evidence.test_runs` / `tests_passing` in the same sidecar
  verify        nothing; judges that sidecar's actuals and completion evidence
                (`verbs.verify_node`), except the status, which is the plan's and v7's

`set-actual` on a ticket records NO calibration sample. A sample compares an actual with
the estimate made before the work, and that pairing (plan file -> entry -> estimate) is
the build bracket's to make (`build-close`), not this verb's.

It sits above `verbs` and `metrics`, whose value logic it reuses (`apply_estimate`,
`tests_passing`, `verify_node`, `actual_values`), and nothing below imports it.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

from .. import metrics, nodes, sidecar, verbs
from ..core import _die_notfound, _die_usage, _now_iso, append_event
from ..sidecar import entry_address_args, plan_address_args
from . import estimate, lanes, reconcile

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---(?:\n|\Z)", re.DOTALL)

def plan_rel(plan: str, project_root: str) -> str:
    """A plan's path relative to the project root, as event payloads carry it."""
    return os.path.relpath(plan, os.path.realpath(project_root)).replace(os.sep, "/")


def write_ticket_actual(path: str, provided: dict) -> None:
    """`[actual]` in a ticket sidecar, the five metrics in canonical order. A re-capture not
    split per model drops an earlier split, which verify would otherwise sum against
    a tokens_k it no longer describes."""
    with sidecar.edit(path) as doc:
        tbl = sidecar.table(doc, "actual")
        if "tokens_k" in provided and "by_model" not in provided and "by_model" in tbl:
            del tbl["by_model"]
        sidecar.put_metrics(tbl, provided)


def record_test_run(path: str, command: str, exit_code: int) -> bool:
    """Append one run to `completion_evidence.test_runs` and re-derive `tests_passing`
    from the last run of each distinct command. Returns the derived value."""
    tk = sidecar._tomlkit()
    with sidecar.edit(path) as doc:
        ce = sidecar.table(doc, "completion_evidence")
        if "test_runs" not in ce:
            ce["test_runs"] = tk.aot()
        run = tk.table()
        run["command"] = command
        run["exit_code"] = int(exit_code)
        ce["test_runs"].append(run)
        ce["tests_passing"] = verbs.tests_passing(sidecar.plain(ce["test_runs"]))
        return bool(ce["tests_passing"])


def _plan_or_die(plan_file: str) -> tuple:
    """(absolute plan path, its sidecar path); exit 3 when the plan does not exist."""
    sidecar_path = nodes.ticket_sidecar(plan_file)
    plan = nodes.plan_of_ticket_sidecar(sidecar_path)
    if not os.path.isfile(plan):
        _die_notfound(f"plan {plan}")
    return plan, sidecar_path


def plan_field(plan: str, name: str):
    """One scalar from a plan's frontmatter, quotes stripped; None when absent."""
    with open(plan, encoding="utf-8-sig") as fh:
        m = _FRONTMATTER_RE.match(fh.read())
    if not m:
        return None
    line = re.search(rf"^{re.escape(name)}:\s*['\"]?([^'\"#\n]*?)['\"]?\s*(?:#.*)?$",
                     m.group(1), re.MULTILINE)
    return line.group(1).strip() if line else None


def _ticket_of(plan: str) -> str:
    """The plan's `ticket:` frontmatter value (the entry id), else the plan's stem."""
    stem = os.path.basename(plan)[:-len(".md")]
    return plan_field(plan, "ticket") or stem


def _set_estimate(args) -> int:
    if args.cost is not None or args.cost_low is not None or args.cost_high is not None:
        _die_usage("cost is derived from tokens x rates and cannot be set directly — "
                   "fix the token counts or modules.l3io-pm.token_rates instead")
    nodes.project_state_root(args.project_root)       # a v7 project, or exit 2
    folder = nodes.v7_tickets_folder(args.ticket_dir)
    entries = sidecar.read_entries(os.path.join(folder, "tickets.toml"))
    entry_id = str(args.entry)
    if entry_id not in entries:
        _die_notfound(f"entry {entry_id} in {os.path.join(folder, 'tickets.toml')}")
    path = nodes.entry_sidecar(folder)
    with sidecar.edit(path) as doc:
        est_tbl = sidecar.table(doc, "entry", entry_id, "estimate")
        est = sidecar.plain(est_tbl)
        verbs.apply_estimate(est, args)
        sidecar.put_metrics(est_tbl, est)
    over = sidecar.hand_set(entries[entry_id])
    if over:
        sys.stderr.write(f"pm-status.py: note — entry {entry_id} carries a hand-set "
                         f"{', '.join(sorted(over))} in tickets.toml, which overrides this "
                         "estimate when read; tickets.toml is left as it is\n")
    sys.stdout.write(f"OK set-estimate entry {entry_id} ({path})\n")
    return 0


def _set_actual(args) -> int:
    if args.cost is not None:
        _die_usage("--cost is not accepted: cost is derived from tokens x rates. "
                   "Fix the token counts or modules.l3io-pm.token_rates instead.")
    plan, path = _plan_or_die(args.plan_file)
    state_root = nodes.project_state_root(args.project_root)
    provided = metrics.actuals_usage.actual_values(args)
    write_ticket_actual(path, provided)
    if not args.no_events:
        append_event(state_root, {"ts": _now_iso(), "event": "actual", "from": None,
                                  "to": None, "session": args.session_id, "node": "ticket",
                                  "key": _ticket_of(plan),
                                  "plan": plan_rel(plan, args.project_root)})
    sys.stdout.write(f"OK set-actual ticket {os.path.basename(plan)} {sorted(provided)} "
                     "[no calibration sample: build-close pairs actuals with estimates]\n")
    return 0


def _add_test_run(args) -> int:
    if args.exit_code < 0:
        sys.stderr.write("ERROR --exit-code must be >= 0\n")
        return 2
    plan, path = _plan_or_die(args.plan_file)
    nodes.project_state_root(args.project_root)
    passing = record_test_run(path, args.command, args.exit_code)
    sys.stdout.write(f"OK {os.path.basename(plan)} test run recorded "
                     f"({args.command} -> {args.exit_code}); tests_passing={passing}\n")
    return 0


def _verify(args) -> int:
    plan, path = _plan_or_die(args.plan_file)
    nodes.project_state_root(args.project_root)
    if not os.path.isfile(path):
        _die_notfound(f"ticket sidecar {path} (no actual recorded yet)")
    node = sidecar.plain(sidecar.load(path))
    return verbs.verify_node(args, node, f"ticket {os.path.basename(plan)}", "story",
                             judge_status=False)


def register(sub):
    v = sub.add_parser("verify", help="read-back gate on a ticket's sidecar; nonzero exit "
                                      "on any gap")
    plan_address_args(v)
    v.add_argument("--scope", choices=["story"], default="story",
                   help="a v7 ticket is judged as a story (the only scope left)")
    v.add_argument("--require-tokens", action="store_true")
    v.add_argument("--runtime", choices=["claude", "codex", "copilot", "other"], default="other")
    v.add_argument("--token-rates", dest="token_rates", default="",
                   help="JSON object of per-model rate overrides")
    v.set_defaults(func=_verify)

    se = sub.add_parser("set-estimate", help="write [entry.<id>].estimate in an epic's "
                                             "l3io.toml")
    entry_address_args(se)
    se.add_argument("--man-hours", dest="man_hours")
    se.add_argument("--hitl-hours", dest="hitl_hours",
                    help="human attention actually spent supervising (hours)")
    se.add_argument("--elapsed-hours", dest="elapsed_hours")
    se.add_argument("--tokens-k", dest="tokens_k")
    # --cost / --cost-low / --cost-high are declared but SUPPRESSed and rejected in
    # _set_estimate: cost is derived from tokens x rates, never input, and a declared flag
    # turns that into a clear usage error instead of argparse's "unrecognized arguments".
    se.add_argument("--cost", dest="cost", help=argparse.SUPPRESS)
    se.add_argument("--cost-low", dest="cost_low", help=argparse.SUPPRESS)
    se.add_argument("--cost-high", dest="cost_high", help=argparse.SUPPRESS)
    se.add_argument("--confidence", choices=["low", "medium", "high"])
    se.add_argument("--fix-factor", dest="fix_factor",
                    help="fix multiplier applied; required for the scope/fix split")
    se.add_argument("--scope-ratio", dest="scope_ratio",
                    help="calibrated scope ratio applied (1.0 when cold-start)")
    se.set_defaults(func=_set_estimate)

    a = sub.add_parser("set-actual", help="write a ticket's validated actual block")
    plan_address_args(a)
    a.add_argument("--node", choices=["story"], default="story",
                   help="a v7 ticket's actual is a story's (the only node left)")
    a.add_argument("--elapsed-hours", dest="elapsed_hours")
    a.add_argument("--man-hours", dest="man_hours")
    a.add_argument("--hitl-hours", dest="hitl_hours",
                   help="human attention actually spent supervising (hours)")
    a.add_argument("--tokens-input", dest="tokens_input")
    a.add_argument("--tokens-output", dest="tokens_output")
    a.add_argument("--tokens-cache-write", dest="tokens_cache_write")
    a.add_argument("--tokens-cache-read", dest="tokens_cache_read")
    a.add_argument("--tokens-na", dest="tokens_na", action="store_true",
                   help="record tokens/cost as N/A (runtime=other only)")
    a.add_argument("--model", default="", help="model id that priced these tokens")
    a.add_argument("--tokens-by-model", dest="tokens_by_model", default=None,
                   help="JSON {model: {input, output, cache_write, cache_read}} in thousands: "
                        "a run on more than one model, each priced at its own rates "
                        "(replaces --tokens-* and --model)")
    a.add_argument("--token-rates", dest="token_rates", default="",
                   help="JSON object of per-model rate overrides")
    a.add_argument("--cost", default=None, help=argparse.SUPPRESS)
    a.add_argument("--runtime", choices=["claude", "codex", "copilot", "other"], default="other")
    a.add_argument("--no-events", dest="no_events", action="store_true",
                   help="skip the events.jsonl append for this call")
    a.add_argument("--session-id", dest="session_id", default=None,
                   help="recorded in the event payload; null when omitted")
    a.set_defaults(func=_set_actual)

    a = sub.add_parser("add-test-run", help="record one executed test command and its exit code")
    plan_address_args(a)
    a.add_argument("--command", required=True, help="the test command actually executed")
    a.add_argument("--exit-code", dest="exit_code", type=int, required=True)
    a.set_defaults(func=_add_test_run)

    rc = sub.add_parser("sidecar-reconcile",
                        help="repoint l3io sidecars after tickets.py move, or sweep for "
                             "orphans")
    rc.add_argument("--project-root", dest="project_root", required=True)
    rc.add_argument("--initiative-dir", dest="initiative_dir", required=True,
                    help="the v7 initiative folder (holding <name>.md and tickets/)")
    rc.add_argument("--moved-json", dest="moved_json", default="",
                    help="tickets.py move's stdout: the JSON itself, a file holding it, or - "
                         "for stdin; omit to sweep for orphans")
    rc.set_defaults(func=reconcile.cmd_sidecar_reconcile)
    estimate.register(sub)
    lanes.register(sub)
