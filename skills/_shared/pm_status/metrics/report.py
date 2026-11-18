"""pm_status.metrics.report -- `report`: progress over a v7 initiative.

v7's `tickets.py status`, joined with our sidecars, the event log and the build spool,
rendered as a tree, markdown or JSON. The top of `metrics`: nothing in `metrics` reads it
back.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

from .. import nodes
from ..core import (
    _die_notfound,
    _die_usage,
    _now_iso,
    _parse_iso,
)
from .events import (
    DEFAULT_STALL_MINUTES,
    open_dispatches,
)
from .spend import (
    _add_totals,
    _block_totals,
    _fmt_actuals,
    _norm_spend,
)

# --------------------------------------------------------------------------- #
# the v7 source: `tickets.py status` + our sidecars + events.jsonl + the build spool
# --------------------------------------------------------------------------- #
#
# On BMad v7 the work-item tree is v7's, and its status is what `tickets.py status` prints
# for an initiative: epics in build order, every ticket with its `state`. Ours is beside it:
# a lane per epic in the initiative's `l3io.toml`, an estimate per entry and the epic roll-up
# in each epic's `l3io.toml`, an actual per ticket in `<plan-stem>.l3io.toml`. A ticket's
# sidecar is joined through its plan, whose `ticket:` frontmatter names the entry id or the
# leaf's stem, exactly as `tickets.py` joins a plan (`join_plans`).
#
# STALLS COME FROM THE SPOOL. A build's bracket is opened by `build-open` into the gitignored
# `{state_root}/.inflight/` and reaches `events.jsonl` only when `build-close` runs, so a hung
# build is visible nowhere else. Every open spool record older than `--stall-minutes` is a
# stalled build; a retired (`abandoned-*`) one is not, since a later open replaced it. Open
# `dispatch` pairs in the event log are reported beside them.
#
# Read-only unless `--out` is given.


def _v7_status(args) -> dict:
    """`tickets.py status` for the initiative: from --status-json, else v7's own script."""
    import shutil
    import subprocess

    if args.status_json:
        try:
            if args.status_json == "-":
                return json.load(sys.stdin)
            with open(args.status_json, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError) as e:
            _die_usage(f"--status-json {args.status_json}: {e}")
    script = nodes.v7_tickets_py(args.project_root)
    if not os.path.isfile(script):
        _die_usage(f"{script} is missing (bmad setup installs it with bmad-agent-po); pass "
                   "--status-json with what `tickets.py status <initiative>` prints")
    runner = (["uv", "run", "--quiet"] if shutil.which("uv") else [sys.executable])
    r = subprocess.run([*runner, script, "--project-root", args.project_root, "status",
                        os.path.abspath(args.initiative_dir)],
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        _die_usage(f"tickets.py status {args.initiative_dir} failed: "
                   f"{(r.stderr or r.stdout).strip()}")
    try:
        return json.loads(r.stdout)
    except ValueError as e:
        _die_usage(f"tickets.py status printed no JSON: {e}")
    return {}


def _toml(path: str) -> dict:
    from .. import sidecar
    return sidecar.plain(sidecar.load(path)) if os.path.isfile(path) else {}


def _plans_by_ticket(tickets_dir: str) -> dict:
    """{entry id or leaf stem: plan path} for every plan in one tickets folder."""
    from ..sidecar.verbs import plan_field
    out = {}
    if not os.path.isdir(tickets_dir):
        return out
    for name in sorted(os.listdir(tickets_dir)):
        path = os.path.join(tickets_dir, name)
        if not name.endswith(".md") or not os.path.isfile(path):
            continue
        ticket = plan_field(path, "ticket")
        if ticket:
            out[str(ticket)] = path
    return out


def _spool_stalls(state_root: str, threshold: float, now=None) -> list:
    """Open build brackets older than the threshold, oldest first (`build-open`'s spool)."""
    spool = nodes.inflight_dir(state_root)
    if not os.path.isdir(spool):
        return []
    now = now or datetime.now(UTC)
    out = []
    for name in sorted(os.listdir(spool)):
        if not name.endswith(".json") or name.startswith("abandoned-"):
            continue
        try:
            with open(os.path.join(spool, name), encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        opened = _parse_iso(rec.get("opened_at")) if isinstance(rec, dict) else None
        if opened is None:
            continue
        age = (now - opened).total_seconds() / 60.0
        if age < threshold:
            continue
        out.append({"source": "build", "agent": rec.get("agent"),
                    "plan": rec.get("plan") or None, "opened_at": rec.get("opened_at"),
                    "age_minutes": round(age, 1)})
    return sorted(out, key=lambda r: r["opened_at"])


def build_v7_model(project_root: str, initiative_dir: str, status: dict,
                   stall_minutes: float) -> dict:
    """The progress model of one v7 initiative. Writes nothing."""
    from .. import sidecar
    if not isinstance(status.get("epics"), list):
        _die_usage("report needs `tickets.py status` of an initiative (an `epics` list); "
                   "for a parent initiative, report on each of its initiatives")
    state_root = nodes.project_state_root(project_root)
    top = nodes.v7_tickets_folder(initiative_dir)
    lanes = _toml(nodes.container_sidecar(initiative_dir)).get("epic", {})
    rows = [t for t in status.get("tickets") or [] if isinstance(t, dict)]
    epics, by_plan = [], {}
    totals = {"epics": {}, "tickets": {}}
    actual_total: dict = {}
    for e in status["epics"]:
        slug = str(e.get("slug"))
        tdir = nodes.v7_tickets_folder(os.path.join(top, slug))
        ours = _toml(nodes.entry_sidecar(tdir))
        plans = _plans_by_ticket(tdir)
        tickets, counts, actual = [], {}, {}
        for t in (t for t in rows if t.get("epic") == slug):
            state = str(t.get("state") or "")
            counts[state] = counts.get(state, 0) + 1
            totals["tickets"][state] = totals["tickets"].get(state, 0) + 1
            plan = plans.get(str(t.get("id")))
            if plan is None and t.get("file"):
                plan = plans.get(str(t["file"])[:-len(".md")])
            got = (_block_totals(_toml(nodes.ticket_sidecar(plan)), "actual")
                   if plan else {})
            _add_totals(actual, got)
            row = {"ref": t.get("ref"), "id": t.get("id"), "title": t.get("title"),
                   "state": state, "status": t.get("status"),
                   "estimate": (sidecar.effective_estimate(tdir, t["id"])["values"]
                                if t.get("id") is not None else {}),
                   "actual": got,
                   "plan": os.path.relpath(plan, project_root) if plan else None}
            if t.get("blocked_reason") or state == "blocked":
                row["blocked_reason"] = str(t.get("blocked_reason") or "")
            if plan:
                by_plan[row["plan"]] = f"{slug}/{t.get('id')}"
            tickets.append(row)
        closed = _block_totals(ours.get("epic"), "actual")
        if closed:
            # epic-close's [epic.actual] is every ticket plus the closure run.
            actual = closed
        _add_totals(actual_total, actual)
        epic_status = str(e.get("status") or "")
        totals["epics"][epic_status or "open"] = totals["epics"].get(epic_status or "open",
                                                                     0) + 1
        epics.append({"slug": slug, "status": epic_status,
                      "lane": (lanes.get(slug) or {}).get("lane"),
                      "after": list(e.get("after") or []),
                      "counts": counts, "estimate": dict(ours.get("epic", {})
                                                        .get("estimate", {})),
                      "actual": actual, "tickets": tickets})
    stalled = _spool_stalls(state_root, stall_minutes)
    for s in stalled:
        s["ticket"] = by_plan.get(s["plan"])
    for d in open_dispatches(state_root, stall_minutes):
        stalled.append({"source": "dispatch", **d})
    return {"source": "v7", "generated": _now_iso(), "state_root": state_root,
            "initiative": status.get("folder") or os.path.basename(initiative_dir),
            "store": status.get("store"), "epics": epics, "totals": totals,
            "actual_total": actual_total,
            "problems": list(status.get("problems") or []),
            "stalled_dispatches": stalled}


def render_v7_tree(model: dict) -> str:
    out = [f"INITIATIVE {model['initiative']}   store={model.get('store')}",
           f"STATE {model['state_root']}", ""]
    if not model["epics"]:
        out += ["No epics found — nothing to report.", ""]
    for e in model["epics"]:
        lane = f"lane {e['lane']}" if e.get("lane") else ""
        done = sum(v for k, v in e["counts"].items() if k in ("review", "done"))
        out.append(f"{e['slug']:<24} {e['status'] or 'open':<12} {lane:<8} "
                   f"{done}/{sum(e['counts'].values())} built")
        for t in e["tickets"]:
            if t["state"] in ("done", "dropped"):
                continue
            suffix = f"  [blocked: {t['blocked_reason']}]" if t.get("blocked_reason") else ""
            out.append(f"  {t['ref']!s:<8} {t['title'] or ''!s:<28} "
                       f"{t['state']:<12}{suffix}")
        out.append("")
    out.append("Totals")
    for level in ("epics", "tickets"):
        body = "  ".join(f"{k}={v}" for k, v in sorted(model["totals"][level].items()))
        out.append(f"  {level:<9} {body or 'none'}")
    if model["actual_total"]:
        out += ["", "Spend (actual: every ticket, plus each closed epic's closure)",
                f"  {_fmt_actuals(model['actual_total'])}"]
    if model["problems"]:
        out += ["", "Problems (tickets.py)"] + [f"  {p}" for p in model["problems"]]
    if model["stalled_dispatches"]:
        out += ["", "STALLED BUILD (open past threshold):"]
        for s in model["stalled_dispatches"]:
            what = s.get("ticket") or s.get("plan") or " ".join(
                x for x in (s.get("epic"), s.get("sprint"), s.get("story")) if x)
            out.append(f"  {s.get('agent')!s:<20} {what or '':<28} "
                       f"{s['age_minutes']}m  since {s['opened_at']}"
                       + (f"  ({s['plan']})" if s.get("plan") and s.get("ticket") else ""))
    return "\n".join(line.rstrip() for line in out) + "\n"


def _estimate_cell(estimate: dict, metric: str):
    """A point estimate, or the `<metric>_low`/`_high` range `estimate-entries` writes."""
    if estimate.get(metric) is not None:
        return _norm_spend(estimate[metric])
    low, high = estimate.get(f"{metric}_low"), estimate.get(f"{metric}_high")
    if low is None or high is None:
        return _norm_spend(low if high is None else high)
    return f"{_norm_spend(low)}–{_norm_spend(high)}"


def render_v7_md(model: dict) -> str:
    out = ["# Progress Report", "",
           (f"Generated by `pm-status.py report` at {model['generated']} for the BMad v7 "
            f"initiative `{model['initiative']}`. This file is a view, not a source of "
            "truth — do not hand-edit; regenerate it."), "",
           "| Epic | Status | Lane | Built | Man-hours est. | Man-hours actual |",
           "|---|---|---|---|---|---|"]
    for e in model["epics"]:
        done = sum(v for k, v in e["counts"].items() if k in ("review", "done"))
        out.append(f"| {e['slug']} | {e['status'] or 'open'} | {e.get('lane') or ''} "
                   f"| {done}/{sum(e['counts'].values())} "
                   f"| {_estimate_cell(e['estimate'], 'man_hours')} "
                   f"| {_norm_spend(e['actual'].get('man_hours'))} |")
    out.append("")
    if model["stalled_dispatches"]:
        out += ["## Stalled builds", "", "| Agent | Ticket | Age (min) | Since |",
                "|---|---|---|---|"]
        for s in model["stalled_dispatches"]:
            out.append(f"| {s.get('agent')} | {s.get('ticket') or s.get('plan') or ''} "
                       f"| {s['age_minutes']} | {s['opened_at']} |")
        out.append("")
    return "\n".join(out) + "\n"


def _emit(args, once) -> int:
    if args.watch:
        import time
        try:
            while True:
                sys.stdout.write("\x1b[2J\x1b[H")   # clear + home
                sys.stdout.write(once())
                sys.stdout.write(f"\n[refreshing every {args.watch}s — Ctrl-C to stop]\n")
                sys.stdout.flush()
                time.sleep(args.watch)
        except KeyboardInterrupt:
            return 0

    text = once()
    if args.out:
        d = os.path.dirname(os.path.abspath(args.out)) or "."
        os.makedirs(d, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        sys.stdout.write(f"OK report {args.out} ({args.format})\n")
        return 0
    sys.stdout.write(text)
    return 0


def cmd_report(args) -> int:
    """Progress over a v7 initiative. Read-only unless --out is given, which is what lets
    read-only callers (l3io-doctor stats) share this exact code path."""
    if not args.initiative_dir:
        _die_usage("report needs --initiative-dir, the v7 initiative folder")
    if not os.path.isdir(args.initiative_dir):
        _die_notfound(f"initiative folder {args.initiative_dir}")
    stall = getattr(args, "stall_minutes", DEFAULT_STALL_MINUTES)

    def once() -> str:
        model = build_v7_model(args.project_root, args.initiative_dir, _v7_status(args),
                               stall)
        if args.format == "json":
            return json.dumps(model, indent=2, sort_keys=True) + "\n"
        return render_v7_md(model) if args.format == "md" else render_v7_tree(model)

    return _emit(args, once)
