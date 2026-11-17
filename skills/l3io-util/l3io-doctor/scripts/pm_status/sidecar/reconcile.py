"""pm_status.sidecar.reconcile -- `sidecar-reconcile`: keep our sidecars with v7's tickets.

`tickets.py move` moves an entry to another folder, renumbers it there (the destination's
`next_id`), and carries its leaf file and plan along (`cmd_move`, :1509, :1633-1652). It
knows nothing of our files, so after a move:

  * the estimate sits at `[entry.<old_id>]` in the SOURCE folder's `l3io.toml`, where no
    entry has that id any more -- and since a folder's `next_id` never decreases, none
    ever will;
  * the plan's sidecar `<plan-stem>.l3io.toml` is left in the source folder, while the plan
    it belongs beside has moved.

Given the move's own JSON (`--moved-json`), this repoints `[entry.<old_id>]` to
`[entry.<id>]` in the destination's `l3io.toml` and moves the plan sidecar beside the moved
plan. Without it, it sweeps the initiative: a plan sidecar whose plan is gone is moved
beside the one same-named plan elsewhere in the initiative, and an `[entry.<id>]` whose id
is not in that folder's `tickets.toml` is REPORTED -- it cannot be followed without the move
that orphaned it. One line per action or finding, exit 0; 2 on usage; 1 when the commit
failed. Never writes a v7 file.

What it changed is committed, and nothing else, as `chore(l3io): reconcile sidecars`
(`sidecar.commit`): Sofia's replan and board hooks run it, and the next `bmad-build-auto`
refuses a dirty tree.
"""
from __future__ import annotations

import json
import os
import sys

from .. import nodes, sidecar
from ..core import _die_usage
from . import commit


def _read_moved(raw: str) -> dict:
    if raw == "-":
        text = sys.stdin.read()
    elif raw.lstrip().startswith("{"):
        text = raw
    else:
        try:
            with open(raw, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as e:
            _die_usage(f"--moved-json: cannot read {raw}: {e}")
    try:
        data = json.loads(text)
    except ValueError as e:
        _die_usage(f"--moved-json is not tickets.py move's JSON: {e}")
    missing = [k for k in ("from", "to", "old_id", "id") if not isinstance(data, dict) or k not in data]
    if missing:
        _die_usage(f"--moved-json lacks {', '.join(missing)} -- pass tickets.py move's stdout")
    return data


def _folder(initiative: str, name: str) -> str:
    f = nodes.v7_folder_by_name(initiative, name)
    if f is None:
        _die_usage(f"--moved-json names folder {name!r}, which is not under or beside "
                   f"{initiative}")
    return nodes.v7_tickets_folder(f)


def _move_file(src: str, dst: str, out: list, touched: list) -> None:
    rel = os.path.basename(src)
    if not os.path.exists(src):
        return
    if os.path.exists(dst):
        out.append(f"conflict {rel}: {dst} exists already; both left as they are")
        return
    os.replace(src, dst)
    touched += [src, dst]
    out.append(f"move {src} -> {dst}")


def _follow_move(initiative: str, moved: dict, out: list, touched: list) -> None:
    src_dir = _folder(initiative, str(moved["from"]))
    dst_dir = _folder(initiative, str(moved["to"]))
    old_id, new_id = str(moved["old_id"]), str(moved["id"])
    src_side, dst_side = nodes.entry_sidecar(src_dir), nodes.entry_sidecar(dst_dir)
    with sidecar.locked(src_dir, dst_dir):
        src_doc, dst_doc = sidecar.load(src_side), sidecar.load(dst_side)
        entry = src_doc.get("entry", {}).get(old_id)
        if entry is not None:
            if new_id in dst_doc.get("entry", {}):
                out.append(f"conflict entry {moved['to']} {new_id}: already present; "
                           f"{moved['from']} {old_id} left as it is")
            else:
                sidecar.table(dst_doc, "entry")[new_id] = entry
                del src_doc["entry"][old_id]
                sidecar.save(dst_side, dst_doc)
                sidecar.save(src_side, src_doc)
                touched += [src_side, dst_side]
                out.append(f"repoint entry {moved['from']} {old_id} -> {moved['to']} {new_id}")
        plan = moved.get("plan")
        if plan:
            src = nodes.ticket_sidecar(os.path.join(src_dir, plan))
            _move_file(src, nodes.ticket_sidecar(os.path.join(dst_dir, plan)), out, touched)


def _sweep(initiative: str, out: list, touched: list) -> None:
    folders = nodes.v7_ticket_folders(initiative)
    plans: dict[str, list] = {}
    for d in folders:
        if os.path.isdir(d):
            for name in os.listdir(d):
                if name.endswith(".md"):
                    plans.setdefault(name, []).append(d)
    for d in folders:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith(nodes.TICKET_SIDECAR_SUFFIX) or name == nodes.SIDECAR_NAME:
                continue
            side = os.path.join(d, name)
            plan = os.path.basename(nodes.plan_of_ticket_sidecar(side))
            if os.path.isfile(os.path.join(d, plan)):
                continue
            homes = plans.get(plan, [])
            if len(homes) == 1:
                with sidecar.locked(d, homes[0]):
                    _move_file(side, nodes.ticket_sidecar(os.path.join(homes[0], plan)), out,
                               touched)
            else:
                why = "no plan of that name" if not homes else f"{len(homes)} plans of that name"
                out.append(f"orphan {side}: {why} in the initiative")
        ids = set(sidecar.read_entries(os.path.join(d, "tickets.toml")))
        ours = sidecar.plain(sidecar.load(nodes.entry_sidecar(d))).get("entry", {})
        for entry_id in sorted(set(ours) - ids):
            out.append(f"orphan entry {os.path.basename(os.path.dirname(d))} {entry_id}: no "
                       "such id in tickets.toml (pass the move's JSON to follow it)")


def cmd_sidecar_reconcile(args) -> int:
    nodes.project_state_root(args.project_root)       # a v7 project, or exit 2
    initiative = os.path.abspath(args.initiative_dir)
    if not os.path.isdir(initiative):
        _die_usage(f"--initiative-dir {initiative} is not a directory")
    out: list = []
    touched: list = []
    if args.moved_json:
        _follow_move(initiative, _read_moved(args.moved_json), out, touched)
    else:
        _sweep(initiative, out, touched)
    sys.stdout.write("".join(f"{line}\n" for line in out) or "ok nothing to reconcile\n")
    err = commit.commit_paths(args.project_root, touched, "chore(l3io): reconcile sidecars")
    if err:
        sys.stderr.write(f"pm-status.py: reconciled, but the commit failed, so the tree is "
                         f"dirty: {err}\n")
        return 1
    return 0
