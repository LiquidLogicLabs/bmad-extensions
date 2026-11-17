"""pm_status.sidecar.estimate -- `estimate-entries`: estimates for a v7 epic's entries.

Sofia's slice, refine and replan hooks and `l3io-plan estimate` run this over one epic's
tickets folder. For each entry it writes `[entry.<id>]` in that folder's `l3io.toml`:
`class`, `fingerprint`, `estimated_at` and the `estimate` table, computed exactly as
`estimate-story` computes a 3.x story's (`metrics.estimates.compute_story_estimate`: the
class's band x the calibrated scope ratio x the fix factor, cost priced from the tokens).
Then it rolls `[epic].estimate` up as the entries' sum plus the epic closure band and the
orchestration band (`metrics.estimates.rollup_values`). There is no sprint between an epic
and its entries on v7, so there is no sprint term (ADR-0016). The roll-up is recomputed on
every run, so an entry moved out or dropped leaves it, and an epic with no estimated entry
left loses its `[epic].estimate`.

WHICH ENTRIES. An entry is (re-)estimated when it has no estimate of ours yet, when its
fingerprint -- a hash of its `description`, `verify` and `covers` in `tickets.toml` -- differs
from the one recorded, when `--class` gives it a class other than its recorded one, when it
is named by `--entry`, or for every entry under `--force`. An entry that carries a hand-set
estimate (v7's own `estimate`, or any `l3io_<metric>`) is never written: a person's estimate
is the estimate. A hand-set `l3io_class` is used as the class.

THE CLASS IS A JUDGEMENT; everything after it is arithmetic. An entry to be written with no
class given, recorded or hand-set is refused, with every such entry named and nothing
written, so the caller can classify them and run again.

It reads `tickets.toml` directly and read-only, as `set-estimate` does, rather than through
`tickets.py status`: the status rows carry neither `description` nor `verify`, which the
fingerprint needs. It never writes a v7 file. What it wrote is committed (`sidecar.commit`)
as `chore(l3io): estimates <epic>`, because the hooks that run it sit between Sofia's commit
and the next `bmad-build-auto`, which refuses a dirty tree.

Output: one JSON line per entry written, then one for the epic's roll-up. Exit 0; 2 on
usage (a missing or unknown class included); 3 for an `--entry` the folder does not list;
1 when the commit failed.

`--check` is the readiness check wired into Sofia's validate (`workflow.checks.set`): it
writes nothing, prints one line per entry with neither an estimate of ours nor a hand-set
one, and exits 1 when there is any, 0 when every entry is estimated.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

from .. import nodes, sidecar
from ..core import METRIC_FIELDS, PMError, _die_notfound, _die_usage, _now_iso
from ..metrics import estimates
from ..metrics.calibration import load_calibration
from ..metrics.rates import rate_overrides
from . import commit

CLASSES = tuple(estimates.BASE_BANDS)


def fingerprint(entry: dict) -> str:
    """What an entry asks for, as a stable hash: its description, verification and covers."""
    basis = {"description": str(entry.get("description", "")),
             "verify": str(entry.get("verify", "")),
             "covers": [str(c) for c in entry.get("covers", [])]}
    blob = json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _hand_set_estimate(entry: dict) -> list:
    """The hand-set estimate keys on a `tickets.toml` entry; `l3io_class` is not one."""
    over = sidecar.hand_set(entry)
    return sorted(k for k in over if k == "hand_estimate" or k in METRIC_FIELDS)


def _parse_classes(raw: list) -> dict:
    out = {}
    for item in raw or []:
        entry_id, sep, cls = item.partition("=")
        if not sep or not entry_id.strip():
            _die_usage(f"--class takes ID=CLASS, got {item!r}")
        if cls.strip() not in CLASSES:
            _die_usage(f"--class {item!r}: the class must be one of {', '.join(CLASSES)}")
        out[entry_id.strip()] = cls.strip()
    return out


def _plan(entries: dict, ours: dict, given: dict, named: set, force: bool) -> tuple:
    """([(id, class, action)] to write, [(id, why)] skipped, [ids] needing a class)."""
    todo, skipped, unclassed = [], [], []
    for entry_id, entry in entries.items():
        hand = _hand_set_estimate(entry)
        if hand:
            skipped.append((entry_id, f"hand-set {', '.join(hand)} in tickets.toml"))
            continue
        mine = ours.get(entry_id, {})
        recorded = mine.get("class")
        cls = given.get(entry_id) or sidecar.hand_set(entry).get("class") or recorded
        if not mine.get("estimate"):
            action = "new"
        elif mine.get("fingerprint") != fingerprint(entry):
            action = "changed"
        elif cls != recorded:
            action = "reclassified"
        elif entry_id in named:
            action = "requested"
        elif force:
            action = "forced"
        else:
            continue
        if cls not in CLASSES:
            unclassed.append(entry_id)
            continue
        todo.append((entry_id, cls, action))
    return todo, skipped, unclassed


def _epic_name(folder: str) -> str:
    return (os.path.basename(os.path.dirname(folder))
            if os.path.basename(folder) == nodes.V7_TICKETS else os.path.basename(folder))


def _check(folder: str, entries: dict) -> int:
    """`--check`: the entries with no estimate, one line each; reads, never writes."""
    ours = sidecar.plain(sidecar.load(nodes.entry_sidecar(folder))).get("entry", {})
    missing = [i for i, e in entries.items()
               if not _hand_set_estimate(e) and not ours.get(i, {}).get("estimate")]
    for entry_id in missing:
        sys.stdout.write(f"entry {entry_id} ({entries[entry_id].get('title', '')!s}): "
                         f"no estimate\n")
    if missing:
        return 1
    sys.stdout.write(f"OK every entry of {_epic_name(folder)} is estimated ({len(entries)})\n")
    return 0


def cmd_estimate_entries(args) -> int:
    folder = nodes.v7_tickets_folder(args.ticket_dir)
    toml = os.path.join(folder, "tickets.toml")
    if not os.path.isfile(toml):
        _die_usage(f"--ticket-dir: {toml} does not exist")
    entries = sidecar.read_entries(toml)
    if args.check:
        if args.entry or args.classes or args.force:
            _die_usage("--check writes nothing, so it takes no --entry, --class or --force")
        return _check(folder, entries)
    state_root = nodes.project_state_root(args.project_root)
    named = {str(e) for e in args.entry or []}
    for entry_id in sorted(named - set(entries)):
        _die_notfound(f"entry {entry_id} in {toml}")
    given = _parse_classes(args.classes)
    path = nodes.entry_sidecar(folder)
    model = args.model or estimates.DEFAULT_ESTIMATE_MODEL
    overrides = rate_overrides(args)
    epic = _epic_name(folder)
    out, rollup = [], None
    with sidecar.locked(folder):
        doc = sidecar.load(path)
        before = sidecar._tomlkit().dumps(doc)
        ours = sidecar.plain(doc).get("entry", {})
        todo, skipped, unclassed = _plan(entries, ours, given, named, args.force)
        if unclassed:
            _die_usage(f"{len(unclassed)} entr{'y' if len(unclassed) == 1 else 'ies'} of {epic} "
                       f"need a class: pass --class ID=CLASS ({', '.join(CLASSES)}) for "
                       + ", ".join(f"{i} ({entries[i].get('title', '')!s})" for i in unclassed)
                       + ". Nothing was written.")
        for entry_id, cls, action in todo:
            node: dict = {}
            try:
                estimates.compute_story_estimate(state_root, node, cls, model, overrides)
            except PMError as e:
                _die_usage(e.msg)
            tbl = sidecar.table(doc, "entry", entry_id)
            tbl["class"] = cls
            tbl["fingerprint"] = fingerprint(entries[entry_id])
            tbl["estimated_at"] = _now_iso()
            est_tbl = sidecar.table(doc, "entry", entry_id, "estimate")
            for k in list(est_tbl):
                del est_tbl[k]
            sidecar.put_metrics(est_tbl, sidecar.plain(node["estimate"]))
            out.append({"entry": entry_id, "class": cls, "action": action,
                        "estimate": sidecar.plain(node["estimate"])})
        children = [{"estimate": _effective(doc, entries, i)} for i in entries]
        _, cal = load_calibration(state_root)
        try:
            est, counted, inactive = estimates.rollup_values(cal, "epic", children, model,
                                                             overrides)
        except PMError as e:
            if e.msg != estimates.NO_CHILD_ESTIMATES:
                _die_usage(e.msg)
            est = None
        if est is not None:
            tbl = sidecar.table(doc, "epic", "estimate")
            fresh = sidecar.plain(est)
            if sidecar.plain(tbl) != fresh:
                for k in list(tbl):
                    del tbl[k]
                sidecar.put_metrics(tbl, fresh)
            rollup = {"epic": epic, "children": counted, "estimate": fresh,
                      "orchestration_unestimated": inactive}
        elif "estimate" in doc.get("epic", {}):
            # Every entry left (moved or dropped): a roll-up of them would be stale.
            del doc["epic"]["estimate"]
            if not doc["epic"]:
                del doc["epic"]
            rollup = {"epic": epic, "children": 0, "estimate": None}
        changed = sidecar._tomlkit().dumps(doc) != before
        if changed:
            sidecar.save(path, doc)
    for entry_id, why in skipped:
        sys.stderr.write(f"pm-status.py: entry {entry_id} not estimated: {why}\n")
    for line in out + ([rollup] if rollup else []):
        sys.stdout.write(json.dumps(line, sort_keys=True) + "\n")
    if changed:
        err = commit.commit_paths(args.project_root, [path], f"chore(l3io): estimates {epic}")
        if err:
            sys.stderr.write(f"pm-status.py: estimates written, but the commit failed, so the "
                             f"tree is dirty: {err}\n")
            return 1
    return 0


def _effective(doc, entries: dict, entry_id: str) -> dict:
    """One entry's estimate as the roll-up counts it: ours, with any hand-set
    `l3io_<metric>` in `tickets.toml` in place of our value for that metric."""
    values = dict(sidecar.plain(doc).get("entry", {}).get(entry_id, {}).get("estimate", {}))
    over = sidecar.hand_set(entries.get(entry_id, {}))
    for m in METRIC_FIELDS:
        if m in over:
            values[m] = over[m]
    return values


def register(sub):
    ee = sub.add_parser("estimate-entries",
                        help="estimate a v7 epic's tickets.toml entries into its l3io.toml, "
                             "then roll the epic up")
    ee.add_argument("--project-root", dest="project_root", required=True)
    ee.add_argument("--ticket-dir", dest="ticket_dir", required=True,
                    help="the v7 epic folder, or its tickets/ folder")
    ee.add_argument("--entry", action="append", default=[], metavar="ID",
                    help="re-estimate this entry even when unchanged; repeatable")
    ee.add_argument("--class", dest="classes", action="append", default=[],
                    metavar="ID=CLASS",
                    help=f"an entry's class ({', '.join(CLASSES)}); required for an entry "
                         "with none recorded; repeatable")
    ee.add_argument("--force", action="store_true",
                    help="re-estimate every entry without a hand-set estimate")
    ee.add_argument("--check", action="store_true",
                    help="write nothing; list the entries with no estimate (exit 1 if any)")
    ee.add_argument("--model", default="",
                    help="model the token estimate is priced at "
                         "(modules.l3io-pm.default_model)")
    ee.add_argument("--token-rates", dest="token_rates", default="",
                    help="JSON object of per-model rate overrides")
    ee.set_defaults(func=cmd_estimate_entries)
