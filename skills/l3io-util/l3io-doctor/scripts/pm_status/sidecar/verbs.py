"""pm_status.sidecar.verbs -- set-estimate, set-actual, add-test-run and verify on v7's tree.

The four verbs keep their 3.x node addressing (`--state-root` plus `--story`/`--epic`/
`--sprint`) and gain v7 addressing beside it: `--project-root` in place of `--state-root`,
then `--ticket-dir DIR --entry ID` for an estimate or `--plan-file PATH` for an actual, a
test run or a verify. `route` picks the handler after parsing; the 3.x handlers are
untouched, so every existing caller runs exactly as before.

What each v7 verb writes (status-files.md §12):

  set-estimate  `[entry.<id>].estimate` in the epic's `l3io.toml`
  set-actual    `[actual]` in `<plan-stem>.l3io.toml`, plus one `actual` event in
                `{state_root}/events.jsonl`
  add-test-run  `completion_evidence.test_runs` / `tests_passing` in the same sidecar
  verify        nothing; judges that sidecar as 3.x verify judges a story node, except
                the status, which is the plan's and v7's to write

`set-actual` on a ticket records NO calibration sample. A sample compares an actual with
the estimate made before the work, and that pairing (plan file -> entry -> estimate) is
the build bracket's to make (`build-close`), not this verb's.

It sits above `verbs` and `metrics`, whose value logic it reuses (`apply_estimate`,
`tests_passing`, `verify_node`, `actual_values`), and nothing below imports it.
"""
from __future__ import annotations

import os
import re
import sys

from .. import metrics, nodes, sidecar, verbs
from ..core import _die_notfound, _die_usage, _now_iso, append_event
from . import reconcile

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---(?:\n|\Z)", re.DOTALL)

def route(args):
    """The handler for a parsed command line: the v7 one when any v7 address flag is
    given, else the 3.x one. Mixing the two addressing schemes is a usage error, and so is
    giving neither a state root nor a project root."""
    spec = _V7.get(args.cmd)
    if spec is None:
        return args.func
    if not sidecar.is_v7(args):
        if not getattr(args, "state_root", None):
            _die_usage(f"{args.cmd} needs --state-root (3.x state tree) or --project-root "
                       "with a v7 address (--plan-file, or --ticket-dir and --entry)")
        if args.cmd == "add-test-run" and not args.story:
            _die_usage("add-test-run --state-root needs --story")
        return args.func
    mixed = [f"--{d.replace('_', '-')}" for d in ("state_root", "story", "epic", "sprint")
             if getattr(args, d, None)]
    if mixed:
        _die_usage(f"{', '.join(mixed)} cannot be combined with v7 addressing "
                   "(--project-root, --plan-file, --ticket-dir, --entry)")
    if not args.project_root:
        _die_usage(f"{args.cmd} with a v7 address needs --project-root")
    kind, handler = spec
    if kind == "entry" and not (args.ticket_dir and args.entry):
        _die_usage(f"{args.cmd} --project-root needs --ticket-dir and --entry")
    if kind == "plan" and not args.plan_file:
        _die_usage(f"{args.cmd} --project-root needs --plan-file")
    return handler


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
    ranged = [f for f in ("man_hours_low", "man_hours_high", "hitl_hours_low", "hitl_hours_high",
                          "elapsed_hours_low", "elapsed_hours_high", "tokens_k_max")
              if getattr(args, f, None) is not None]
    if ranged:
        _die_usage("a ticket entry takes single values (--man-hours, --hitl-hours, "
                   "--elapsed-hours, --tokens-k), not "
                   + ", ".join("--" + f.replace("_", "-") for f in ranged))
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
        verbs.apply_estimate(est, args, "story")
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
    if args.node != "story" or args.block != "actual":
        _die_usage("a v7 ticket's actual is --node story --block actual; an epic's is "
                   "written at its closure")
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
    if args.scope != "story":
        _die_usage("a v7 ticket is verified with --scope story")
    plan, path = _plan_or_die(args.plan_file)
    nodes.project_state_root(args.project_root)
    if not os.path.isfile(path):
        _die_notfound(f"ticket sidecar {path} (no actual recorded yet)")
    node = sidecar.plain(sidecar.load(path))
    return verbs.verify_node(args, node, f"ticket {os.path.basename(plan)}", "story",
                             judge_status=False)


# The v7 handler per subcommand, and which address it takes.
_V7 = {
    "set-estimate": ("entry", _set_estimate),
    "set-actual": ("plan", _set_actual),
    "add-test-run": ("plan", _add_test_run),
    "verify": ("plan", _verify),
}


def register(sub):
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
