"""pm_status.metrics.report -- the progress model and its renderers.

One builder (`build_progress_model`) consumed by every surface, the plan reader
that makes the view phase-aware, the tree/markdown renderers, `cmd_report`, and
`_write_spend` (the three-bucket breakout `show` prints, which is the same spend
model rendered per node).

The top of `metrics`: it reads `events` for dwell and dispatch state and `spend`
for attribution, and nothing in `metrics` reads it back.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

from .. import core, nodes
from ..core import (
    METRIC_FIELDS,
    STATUS_DIRS,
    STATUS_FOR_DIR,
    _die_notfound,
    _die_usage,
    _now_iso,
    _parse_iso,
)
from ..nodes import (
    _sprint_key_from_dir,
    list_sprint_dirs,
    list_story_files,
    load_node,
    sprint_file,
)
from .events import (
    DEFAULT_STALL_MINUTES,
    build_events_index,
    compute_flags,
    dwell_hours,
    open_dispatches,
)
from .spend import (
    SPEND_BUCKETS,
    _accumulate_actuals,
    _add_totals,
    _block_totals,
    _closure_totals,
    _fmt_actuals,
    _has_spend,
    _merge_spend,
    _new_spend,
    _norm_spend,
    _spend_total,
    _sprint_spend,
)


# --------------------------------------------------------------------------- #
# progress model — one builder, consumed by every renderer and every surface
# --------------------------------------------------------------------------- #
def list_all_epics(state_root: str) -> list:
    """(epic_key, dir_status) for every epic in every status folder, sorted by key.

    The directory name is authoritative for the key: 'epic-001' -> 'E001'. Reading the
    key from the file instead would let a mis-keyed file hide an epic entirely.
    """
    found = []
    for status in STATUS_DIRS:
        base = os.path.join(state_root, status)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if not name.startswith("epic-"):
                continue
            if not os.path.isdir(os.path.join(base, name)):
                continue
            suffix = name[len("epic-"):]
            if not suffix.isdigit():
                continue
            found.append((f"E{int(suffix):03d}", status))
    return sorted(found, key=lambda t: t[0])


def _build_sprint_detail(state_root: str, epic_key: str, sprint_key: str,
                         events_index: dict, now=None) -> dict:
    """One sprint and its stories.

    `detail["flags"]` holds only the sprint's OWN flags (its stuck state, and any story
    file too broken to become a node of its own). Story flags live on their story. The
    flat aggregate is assembled later by `_collect_flags` — an earlier version pushed
    descendants' flags up into the parent, which made every ancestor row report "stuck"
    whenever one story was.
    """
    flags: list = []
    sp = sprint_file(state_root, epic_key, sprint_key)
    snode = {}
    if sp is not None:
        try:
            _, loaded = load_node(sp)
            snode = loaded or {}
        except Exception as e:  # noqa: BLE001 - a bad file must not kill the report
            flags.append({"kind": "unreadable", "level": "sprint",
                          "key": f"{epic_key}/{sprint_key}", "detail": str(e)})

    s_status = str(snode.get("status", "unknown"))
    s_dwell, s_exact = dwell_hours({"key": sprint_key, "status": s_status,
                                    "updated_at": snode.get("updated_at")},
                                   events_index, now)
    flags += compute_flags("sprint", f"{epic_key}/{sprint_key}", s_status, s_dwell, s_exact)

    stories, by_status, totals = [], {}, {}
    for p in list_story_files(state_root, epic_key, sprint_key):
        try:
            _, node = load_node(p)
        except Exception as e:  # noqa: BLE001
            # No story node exists to hang this on, so it belongs to the sprint.
            flags.append({"kind": "unreadable", "level": "story",
                          "key": os.path.basename(p), "detail": str(e)})
            continue
        if node is None:
            continue
        st = str(node.get("status", "unknown"))
        key = str(node.get("key", os.path.basename(p)))
        by_status[st] = by_status.get(st, 0) + 1
        _accumulate_actuals(totals, node)
        d, ex = dwell_hours(node, events_index, now)
        story_row = {"key": key, "status": st,
                     "estimate": dict(node.get("estimate") or {}),
                     "actual": dict(node.get("actual") or {}),
                     "updated_at": node.get("updated_at"),
                     "dwell_hours": None if d is None else round(d, 2),
                     "dwell_exact": ex,
                     "flags": compute_flags("story", key, st, d, ex)}
        if st == "blocked":
            story_row["blocked_reason"] = str(node.get("blocked_reason", "") or "")
        stories.append(story_row)

    return {"key": sprint_key, "status": s_status, "story_count": len(stories),
            "by_status": by_status, "actual_totals": totals,
            "node_actual": _block_totals(snode, "actual"),
            "spend": _sprint_spend(totals, snode),
            "estimate": dict(snode.get("estimate") or {}),
            "updated_at": snode.get("updated_at"),
            "dwell_hours": None if s_dwell is None else round(s_dwell, 2),
            "dwell_exact": s_exact, "flags": flags, "stories": stories}


def _collect_flags(epic_detail: dict) -> list:
    """Flatten one epic subtree's flags for the model-level aggregate."""
    out = list(epic_detail.get("flags") or [])
    for sp in epic_detail.get("sprints") or []:
        out += list(sp.get("flags") or [])
        for st in sp.get("stories") or []:
            out += list(st.get("flags") or [])
    return out


def build_epic_detail(state_root: str, epic_key: str, dir_status: str,
                      events_index: dict, now=None) -> dict:
    """One epic subtree, enriched with dwell times, flags, and placement checks."""
    flags: list = []
    ep = nodes.epic_file(state_root, epic_key)
    y_node = None
    if ep is not None:
        try:
            _, y_node = load_node(ep)
        except Exception as e:  # noqa: BLE001
            flags.append({"kind": "unreadable", "level": "epic", "key": epic_key,
                          "detail": str(e)})
    enode = y_node or {}

    status = str(enode.get("status", "unknown"))
    expected = STATUS_FOR_DIR.get(dir_status)
    if expected and status != "unknown" and status != expected:
        flags.append({"kind": "placement", "level": "epic", "key": epic_key,
                      "detail": f"status {status!r} but sits in {dir_status}/ "
                                f"(expected {expected!r})"})

    lock = None
    raw_lock = enode.get("_lock")
    if isinstance(raw_lock, dict):
        claimed = _parse_iso(raw_lock.get("claimed_at"))
        ttl = raw_lock.get("ttl_minutes")
        stale = False
        if claimed is not None and ttl:
            try:
                age_min = ((now or datetime.now(UTC))
                           - claimed).total_seconds() / 60.0
                stale = age_min > float(ttl)
            except (TypeError, ValueError):
                stale = False
        lock = {"session_id": raw_lock.get("session_id"),
                "claimed_at": raw_lock.get("claimed_at"),
                "ttl_minutes": ttl, "stale": stale}
        if stale:
            flags.append({"kind": "stale-lock", "level": "epic", "key": epic_key,
                          "detail": f"lock claimed {raw_lock.get('claimed_at')} "
                                    f"exceeds ttl {ttl}m"})

    dwell, exact = dwell_hours({"key": epic_key, "status": status,
                                "updated_at": enode.get("updated_at")},
                               events_index, now)
    flags += compute_flags("epic", epic_key, status, dwell, exact)

    sprints, totals, by_status, story_count = [], {}, {}, 0
    spend, sprint_actual_sum = _new_spend(), {}
    for sd in list_sprint_dirs(state_root, epic_key):
        skey = _sprint_key_from_dir(sd)
        s_detail = _build_sprint_detail(state_root, epic_key, skey, events_index, now)
        sprints.append(s_detail)
        story_count += s_detail["story_count"]
        for k, v in s_detail["by_status"].items():
            by_status[k] = by_status.get(k, 0) + v
        for k, v in s_detail["actual_totals"].items():
            totals[k] = totals.get(k, 0.0) + v
        _merge_spend(spend, s_detail["spend"])
        _add_totals(sprint_actual_sum, s_detail["node_actual"])
    _add_totals(spend["closure"],
                _closure_totals(_block_totals(enode, "actual"), sprint_actual_sum))
    _add_totals(spend["orchestration"], _block_totals(enode, "orchestration"))

    return {
        "key": epic_key, "title": enode.get("title"), "status": status,
        "dir_status": dir_status, "sprint_count": len(sprints),
        "story_count": story_count, "by_status": by_status,
        "estimate": dict(enode.get("estimate") or {}),
        "actual_totals": totals, "node_actual": _block_totals(enode, "actual"),
        "spend": spend, "updated_at": enode.get("updated_at"),
        "dwell_hours": None if dwell is None else round(dwell, 2),
        "dwell_exact": exact, "lock": lock, "flags": flags, "sprints": sprints,
    }


def load_plan(plan_pointer: str):
    """Load plan phases via the stable pointer.

    `plan-output-meta.yaml` is a pointer plus summary scalars and deliberately holds no
    phases list (step-06-plan-output.md §4), so the phases come from the snapshot it
    names, resolved in the pointer's own directory. A dangling pointer yields the meta
    with empty phases rather than an error: the state hierarchy is still worth showing.
    """
    if not plan_pointer or not os.path.isfile(plan_pointer):
        return None
    try:
        _, meta = core._load(plan_pointer)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"pm-status.py: warning — could not read plan pointer: {e}\n")
        return None
    if not meta:
        return None
    meta = dict(meta)
    phases = []
    snap_name = meta.get("current_plan")
    if snap_name:
        snap = os.path.join(os.path.dirname(os.path.abspath(plan_pointer)), str(snap_name))
        if os.path.isfile(snap):
            try:
                _, snode = core._load(snap)
                phases = [dict(p) for p in ((snode or {}).get("phases") or [])]
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f"pm-status.py: warning — could not read plan "
                                 f"snapshot: {e}\n")
        else:
            sys.stderr.write(f"pm-status.py: warning — plan pointer names a missing "
                             f"snapshot: {snap_name}\n")
    return {"meta": meta, "phases": phases}


DEFAULT_REPORT_STATUSES = ("planned", "active")


def build_progress_model(state_root: str, plan=None, statuses=None,
                         include_archived: bool = False, now=None) -> dict:
    """The one model every renderer and every surface consumes.

    `statuses` selects which state folders appear in the DISPLAY lists — pass a subset of
    STATUS_DIRS, e.g. {"active"} for only what is moving. Defaults to planned + active, so
    finished work stays out of the way until asked for.

    Every epic is built regardless of the filter. Phase progress needs a true denominator:
    a bar reading "2/3 epics done" must mean the same thing whatever you chose to look at,
    so counting always sees the whole tree and only the listing narrows.

    `include_archived` is the older boolean form, kept so existing callers keep working;
    it is equivalent to adding "archived" to the default set.
    """
    if statuses is None:
        statuses = set(DEFAULT_REPORT_STATUSES)
        if include_archived:
            statuses.add("archived")
    statuses = set(statuses)
    unknown = statuses - set(STATUS_DIRS)
    if unknown:
        raise ValueError(f"unknown status folder(s): {sorted(unknown)} "
                         f"— expected a subset of {list(STATUS_DIRS)}")
    events_index = build_events_index(state_root)
    details, flags = {}, []
    totals = {"epics": {}, "sprints": {}, "stories": {}}
    spend = _new_spend()

    for epic_key, dir_status in list_all_epics(state_root):
        d = build_epic_detail(state_root, epic_key, dir_status, events_index, now)
        details[epic_key] = d
        flags += _collect_flags(d)
        # Spend, like the status counts below, is summed over EVERY epic, not only
        # the visible ones: "what has this project cost" must not change because
        # the caller narrowed the listing to `active`.
        _merge_spend(spend, d["spend"])
        totals["epics"][d["status"]] = totals["epics"].get(d["status"], 0) + 1
        for sp in d["sprints"]:
            totals["sprints"][sp["status"]] = totals["sprints"].get(sp["status"], 0) + 1
        for k, v in d["by_status"].items():
            totals["stories"][k] = totals["stories"].get(k, 0) + v

    def visible(d):
        return d["dir_status"] in statuses

    phases, claimed = [], set()
    for ph in (plan or {}).get("phases") or []:
        members = [str(k) for k in (ph.get("epics") or [])]
        claimed.update(members)
        present = [details[k] for k in members if k in details]
        phases.append({
            "phase": ph.get("phase"), "parallel": bool(ph.get("parallel")),
            "epics": members, "dependencies": list(ph.get("dependencies") or []),
            "epic_total": len(members),
            "epic_done": sum(1 for d in present if d["status"] == "done"),
            "epics_detail": [d for d in present if visible(d)],
        })

    return {
        "generated": _now_iso(),
        "state_root": os.path.abspath(state_root),
        "statuses": sorted(statuses),
        "plan": (plan or {}).get("meta"),
        "phases": phases,
        "unplanned_epics": [d for k, d in sorted(details.items())
                            if k not in claimed and visible(d)],
        "totals": totals,
        "spend": spend,
        "spend_total": _spend_total(spend),
        "flags": flags,
    }


# --------------------------------------------------------------------------- #
# renderers — thin: they consume the model and nothing else
# --------------------------------------------------------------------------- #
def _bar(done: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return "░" * width
    filled = round(width * max(0, min(done, total)) / total)
    return "█" * filled + "░" * (width - filled)


def _dwell_str(node: dict) -> str:
    h = node.get("dwell_hours")
    if h is None:
        return ""
    approx = "" if node.get("dwell_exact") else "~"
    return f"{approx}{h:.1f}h"


def _stuck_suffix(node: dict) -> str:
    return "  ⚠ stuck" if any(f["kind"] == "stuck" for f in node.get("flags") or []) else ""


def _render_epic_tree(d: dict, out: list, indent: str = "  ") -> None:
    done = d["by_status"].get("done", 0)
    out.append(f"{indent}{d['key']} {(d.get('title') or ''):<24} {d['status']:<12} "
               f"{done}/{d['story_count']} stories  {_dwell_str(d)}{_stuck_suffix(d)}")
    if d.get("lock") and d["lock"].get("stale"):
        out.append(f"{indent}  ⚠ STALE LOCK — claimed {d['lock'].get('claimed_at')} "
                   f"(ttl {d['lock'].get('ttl_minutes')}m)")
    for sp in d["sprints"]:
        s_done = sp["by_status"].get("done", 0)
        # Cosmetic wart from the design (§13): a sprint whose stories are ALL
        # blocked reads as "actively being worked" when its status is still
        # in-progress. Surface it in the header, not as a status transition.
        s_blocked = sp["by_status"].get("blocked", 0)
        header_status = sp["status"]
        if s_blocked and s_blocked == sp["story_count"] and sp["story_count"] > 0:
            header_status = f"{sp['status']} (all {s_blocked} stories blocked)"
        out.append(f"{indent}  {sp['key']:<6} {header_status:<20} "
                   f"{s_done}/{sp['story_count']}  {_dwell_str(sp)}{_stuck_suffix(sp)}")
        for st in sp["stories"]:
            if st["status"] == "done":
                continue  # counts above carry finished work; the tree shows what is live
            suffix = ""
            if st["status"] == "blocked":
                reason = st.get("blocked_reason", "")
                suffix = f"  [blocked: {reason}]" if reason else "  [blocked]"
            out.append(f"{indent}    {st['key']:<20} {st['status']:<14} "
                       f"{_dwell_str(st)}{_stuck_suffix(st)}{suffix}")


def _blocked_stories_from_model(model: dict) -> list:
    """Every currently-blocked story in the model, with its reason and location.

    Walks the model's phases + unplanned_epics rather than re-reading the tree
    from disk. Used by both render_tree and render_md so their "Blocked stories"
    sections agree on shape and content. The JSON emitter returns the whole
    model already; callers reading JSON pick the same field paths directly.
    """
    out = []
    for phase in model.get("phases") or []:
        for d in phase.get("epics_detail") or []:
            for sp in d.get("sprints") or []:
                for st in sp.get("stories") or []:
                    if st.get("status") == "blocked":
                        out.append({
                            "epic": d["key"], "sprint": sp["key"],
                            "story": st["key"],
                            "reason": st.get("blocked_reason", "")})
    for d in model.get("unplanned_epics") or []:
        for sp in d.get("sprints") or []:
            for st in sp.get("stories") or []:
                if st.get("status") == "blocked":
                    out.append({
                        "epic": d["key"], "sprint": sp["key"],
                        "story": st["key"],
                        "reason": st.get("blocked_reason", "")})
    return out


def render_tree(model: dict) -> str:
    out: list = []
    plan = model.get("plan")
    if plan:
        out.append(f"PLAN {plan.get('current_plan')}   readiness={plan.get('readiness')}"
                   f"   generated={plan.get('generated')}")
    else:
        out.append("PLAN (none — showing state only)")
    out.append(f"STATE {model['state_root']}")
    # Name the filter whenever it is not the default, so a short list is never mistaken for
    # an empty project. "only" would be a lie when every folder is shown, so word that case
    # differently.
    shown = model.get("statuses") or list(DEFAULT_REPORT_STATUSES)
    if sorted(shown) == sorted(STATUS_DIRS):
        out.append("SHOWING every status, including archived")
    elif sorted(shown) != sorted(DEFAULT_REPORT_STATUSES):
        out.append(f"SHOWING {', '.join(shown)} only "
                   f"(totals and phase counts still cover every epic)")
    out.append("")

    total_phases = len(model["phases"])
    for ph in model["phases"]:
        kind = "parallel" if ph["parallel"] else "sequential"
        out.append(f"Phase {ph['phase']}/{total_phases} ({kind})  "
                   f"{_bar(ph['epic_done'], ph['epic_total'])}  "
                   f"{ph['epic_done']}/{ph['epic_total']} epics done")
        if ph["dependencies"]:
            out.append(f"  depends on: {', '.join(str(x) for x in ph['dependencies'])}")
        if not ph["epics_detail"]:
            out.append("  (all epics in this phase are archived — pass --all to show)")
        for d in ph["epics_detail"]:
            _render_epic_tree(d, out)
        out.append("")

    if model["unplanned_epics"]:
        out.append("Not in any plan phase:" if model["phases"] else "Epics:")
        for d in model["unplanned_epics"]:
            _render_epic_tree(d, out)
        out.append("")

    if not model["phases"] and not model["unplanned_epics"]:
        out.append("No epics found — nothing to report.")
        out.append("")

    out.append("Totals")
    for level in ("epics", "sprints", "stories"):
        counts = model["totals"].get(level) or {}
        body = "  ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
        out.append(f"  {level:<9} {body}")

    spend = model.get("spend") or {}
    if _has_spend(spend):
        out.append("")
        out.append("Spend (actual, by attribution — covers every epic, not just those listed)")
        for bucket in SPEND_BUCKETS:
            out.append(f"  {bucket:<14} {_fmt_actuals(spend.get(bucket) or {})}")
        out.append(f"  {'TOTAL':<14} {_fmt_actuals(model.get('spend_total') or {})}")

    blocked = _blocked_stories_from_model(model)
    if blocked:
        out.append("")
        out.append(f"Blocked stories ({len(blocked)}):")
        for b in blocked:
            where = f"{b['epic']}/{b['sprint']}/"
            reason = b["reason"] or "(no reason recorded)"
            out.append(f"  {where}{b['story']:<20}  {reason}")

    other = [f for f in model["flags"] if f["kind"] != "stuck"]
    if other:
        out.append("")
        out.append("Anomalies")
        for f in other:
            out.append(f"  [{f['kind']}] {f.get('key')} — {f.get('detail', '')}")

    if any(f["kind"] == "stuck" and not f.get("exact") for f in model["flags"]):
        out.append("")
        out.append("~ dwell times are approximate (no event log yet — derived from "
                   "updated_at, which any field write refreshes)")
    # Column padding leaves ragged trailing spaces on rows with no dwell/flag suffix.
    return "\n".join(line.rstrip() for line in out) + "\n"


def render_md(model: dict) -> str:
    plan = model.get("plan")
    out = ["# Progress Report", "",
           (f"Generated by `pm-status.py report` at {model['generated']}. This file is a "
           "view, not a source of truth — do not hand-edit; regenerate it."), ""]
    if plan:
        out.append(f"**Plan:** `{plan.get('current_plan')}` — readiness "
                   f"`{plan.get('readiness')}`, generated {plan.get('generated')}")
    else:
        out.append("**Plan:** none found — state only.")
    out.append("")

    if model["phases"]:
        out += ["## Phases", "", "| Phase | Mode | Epics done | Members |",
                "|---|---|---|---|"]
        for ph in model["phases"]:
            mode = "parallel" if ph["parallel"] else "sequential"
            out.append(f"| {ph['phase']} | {mode} | {ph['epic_done']}/{ph['epic_total']} "
                       f"| {', '.join(ph['epics'])} |")
        out.append("")

    rows = [d for ph in model["phases"] for d in ph["epics_detail"]] + model["unplanned_epics"]
    out += ["## Epics", "", "| Epic | Title | Status | Sprints | Stories done | Dwell |",
            "|---|---|---|---|---|---|"]
    if not rows:
        out.append("| _none_ | | | | | |")
    for d in rows:
        out.append(f"| {d['key']} | {d.get('title') or ''} | {d['status']} "
                   f"| {d['sprint_count']} | {d['by_status'].get('done', 0)}/"
                   f"{d['story_count']} | {_dwell_str(d) or '—'} |")
    out.append("")

    live = [(d, sp, st) for d in rows for sp in d["sprints"] for st in sp["stories"]
            if st["status"] not in ("done", "backlog")]
    if live:
        out += ["## Stories in flight", "",
                "| Story | Epic | Sprint | Status | Dwell | Stuck |",
                "|---|---|---|---|---|---|"]
        for d, sp, st in live:
            stuck = "yes" if any(f["kind"] == "stuck" for f in st["flags"]) else ""
            out.append(f"| {st['key']} | {d['key']} | {sp['key']} | {st['status']} "
                       f"| {_dwell_str(st) or '—'} | {stuck} |")
        out.append("")

    out += ["## Totals", "", "| Level | Counts |", "|---|---|"]
    for level in ("epics", "sprints", "stories"):
        counts = model["totals"].get(level) or {}
        body = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
        out.append(f"| {level} | {body} |")
    out.append("")

    blocked = _blocked_stories_from_model(model)
    if blocked:
        out += [f"## Blocked stories ({len(blocked)})", "",
                "| Story | Epic | Sprint | Reason |", "|---|---|---|---|"]
        for b in blocked:
            reason = b["reason"] or "(no reason recorded)"
            out.append(f"| {b['story']} | {b['epic']} | {b['sprint']} | {reason} |")
        out.append("")

    spend = model.get("spend") or {}
    if _has_spend(spend):
        out += ["## Spend", "",
                ("Actual spend by attribution, over every epic in the tree (not only the "
                "epics listed above). `stories` is the sum of the leaf actuals, `closure` "
                "each level's own closure-phase residual, `orchestration` the separate "
                "orchestration block."), "",
                "| Attribution | " + " | ".join(METRIC_FIELDS) + " |",
                "|---|" + "---|" * len(METRIC_FIELDS)]
        rows = [(b, spend.get(b) or {}) for b in SPEND_BUCKETS]
        rows.append(("**total**", model.get("spend_total") or {}))
        for label, vals in rows:
            cells = " | ".join(str(_norm_spend(vals.get(m))) for m in METRIC_FIELDS)
            out.append(f"| {label} | {cells} |")
        out.append("")
    return "\n".join(out) + "\n"


def _write_spend(spend: dict) -> None:
    """The three-bucket breakout under a `show` roll-up.

    The `actuals:` line above is the CHILDREN's sum only — that is what it has
    always been, and callers parse it. Closure and orchestration are printed
    beside it rather than folded into it, because the whole point of the model is
    that the three are separately attributable (metrics-contract.md §6).
    """
    if not _has_spend(spend):
        return
    for bucket in SPEND_BUCKETS:
        vals = (spend or {}).get(bucket) or {}
        if vals:
            sys.stdout.write(f"  spend/{bucket:<14} {_fmt_actuals(vals)}\n")
    sys.stdout.write(f"  spend/{'TOTAL':<14} {_fmt_actuals(_spend_total(spend))}\n")


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
# `dispatch` pairs in the event log are reported beside them, as on the 3.x source.
#
# Read-only, like the 3.x source, unless `--out` is given.
V7_ONLY_FLAGS = (("all", "--all"), ("status", "--status"), ("plan", "--plan"))


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
        out += ["", "Spend (actual, every ticket of the initiative)",
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
                   f"| {_norm_spend(e['estimate'].get('man_hours'))} "
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


def cmd_report_v7(args) -> int:
    for dest, flag in V7_ONLY_FLAGS:
        if getattr(args, dest, None):
            _die_usage(f"{flag} reads a 3.x state tree; with --project-root the report is "
                       "over a v7 initiative")
    if not args.initiative_dir:
        _die_usage("report --project-root needs --initiative-dir, the v7 initiative folder")
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
    """Plan-aware progress report. Read-only unless --out is given, which is what lets
    read-only callers (l3io-doctor stats) share this exact code path."""
    if getattr(args, "project_root", None):
        if args.state_root:
            _die_usage("pass --state-root (a 3.x tree) or --project-root (a v7 "
                       "initiative), not both")
        return cmd_report_v7(args)
    if not args.state_root:
        _die_usage("report needs --state-root, or --project-root with --initiative-dir")
    if not os.path.isdir(args.state_root):
        _die_notfound(f"state root {args.state_root}")

    if args.all and args.status:
        _die_usage("pass --all or --status, not both")
    if args.status:
        statuses = {x.strip() for x in args.status.split(",") if x.strip()}
        unknown = statuses - set(STATUS_DIRS)
        if unknown:
            _die_usage(f"unknown --status value(s) {sorted(unknown)} "
                       f"— expected a subset of {list(STATUS_DIRS)}")
    elif args.all:
        statuses = set(STATUS_DIRS)
    else:
        statuses = set(DEFAULT_REPORT_STATUSES)

    def once() -> str:
        plan = load_plan(args.plan) if args.plan else None
        model = build_progress_model(args.state_root, plan=plan, statuses=statuses)
        stalled = open_dispatches(args.state_root,
                                  getattr(args, "stall_minutes", DEFAULT_STALL_MINUTES))
        if args.format == "json":
            model["stalled_dispatches"] = stalled
            return json.dumps(model, indent=2, sort_keys=True) + "\n"
        text = render_md(model) if args.format == "md" else render_tree(model)
        if stalled:
            lines = ["", "STALLED DISPATCH (open past threshold):"]
            for s in stalled:
                where = " ".join(x for x in (s["epic"], s["sprint"], s["story"]) if x)
                lines.append(f"  {s['agent']:<20} {where:<28} "
                             f"{s['age_minutes']}m  since {s['opened_at']}")
            text = text + "\n".join(lines) + "\n"
        return text

    return _emit(args, once)
