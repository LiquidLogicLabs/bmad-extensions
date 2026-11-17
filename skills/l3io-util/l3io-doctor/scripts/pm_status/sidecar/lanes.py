"""pm_status.sidecar.lanes -- `set-lane`: which lane owns a v7 epic.

A lane partitions planned work across developers who each work their own clone. It lives on
the epic and nowhere else (one epic is one lane), as `[epic.<slug>].lane` in the initiative's
`l3io.toml` beside its `tickets.toml`; v7's tree is never written (ADR-0015).

A LANE IS A NUMBER, 1..lane_count. A word cannot be screened -- `backend` and `sarah` are the
same shape -- so a lane is a slot, never a person; who works a lane lives in each developer's
gitignored config. `lane_count` is `modules.l3io-pm.lane_count`, asked at setup and read
through BMad core's resolver. Absent or 1 means lanes are off, and while they are off this
verb refuses: a lane written then would make a single-developer project stop being inert.

What it wrote is committed (`sidecar.commit`) as `chore(l3io): lane <slug>`, so the next
`bmad-build-auto` still starts on a clean tree. Exit 0; 2 on usage (a bad lane, lanes off);
3 for an epic the initiative does not list; 1 when the commit failed.
"""
from __future__ import annotations

import os
import sys
import tomllib

from .. import nodes, sidecar
from ..core import _die_notfound, _die_usage
from . import commit

LANE_COUNT_KEY = "modules.l3io-pm.lane_count"
LANE_MAX = 999


def lane_count(project_root: str) -> int:
    """The configured lane count; 1 when it is absent or not a whole number."""
    raw = nodes.resolve_config_key(project_root, LANE_COUNT_KEY)
    if isinstance(raw, bool):
        return 1
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return 1


def _epic_slugs(initiative_dir: str) -> set:
    """Every epic the initiative names: its `[[epic]]` slugs and its `epic-*` folders. Read
    only, with the stdlib reader, as `tickets.py` itself reads it."""
    folder = nodes.v7_tickets_folder(initiative_dir)
    slugs = set()
    toml = os.path.join(folder, "tickets.toml")
    if os.path.isfile(toml):
        with open(toml, "rb") as fh:
            try:
                data = tomllib.load(fh)
            except tomllib.TOMLDecodeError as e:
                _die_usage(f"{toml} is not valid TOML: {e}")
        slugs |= {str(e.get("slug")) for e in data.get("epic", []) if isinstance(e, dict)}
    if os.path.isdir(folder):
        slugs |= {n for n in os.listdir(folder)
                  if n.startswith("epic-") and os.path.isdir(os.path.join(folder, n))}
    return slugs


def cmd_set_lane(args) -> int:
    raw = str(args.lane).strip()
    if not raw.isdigit() or not 1 <= int(raw) <= LANE_MAX:
        _die_usage(f"lane {args.lane!r} is not a lane number. A lane is a slot in a "
                   "partition -- 1, 2, 3 -- never a person: who works a lane is recorded "
                   "in the gitignored user config, so a name cannot reach the repository. "
                   "A word cannot be screened (`backend` and `sarah` are the same shape), "
                   "so a lane is a number")
    lane = int(raw)
    count = lane_count(args.project_root)
    if count < 2:
        _die_usage(f"lanes are off for this project ({LANE_COUNT_KEY} is "
                   f"{'unset' if count == 1 else count}); `bmad setup l3io-pm` asks for it")
    if lane > count:
        _die_usage(f"lane {lane} is outside 1..{count} ({LANE_COUNT_KEY} is {count})")
    if args.epic not in _epic_slugs(args.initiative_dir):
        _die_notfound(f"epic {args.epic} in initiative {args.initiative_dir}")
    path = nodes.container_sidecar(args.initiative_dir)
    with sidecar.edit(path) as doc:
        tbl = sidecar.table(doc, "epic", args.epic)
        changed = tbl.get("lane") != lane
        tbl["lane"] = lane
    sys.stdout.write(f"OK set-lane {args.epic} lane {lane}\n")
    if changed:
        err = commit.commit_paths(args.project_root, [path], f"chore(l3io): lane {args.epic}")
        if err:
            sys.stderr.write(f"pm-status.py: lane written, but the commit failed, so the "
                             f"tree is dirty: {err}\n")
            return 1
    return 0


def register(sub):
    sl = sub.add_parser("set-lane",
                        help="assign a v7 epic to a lane (1..lane_count) in the initiative's "
                             "l3io.toml")
    sl.add_argument("--project-root", dest="project_root", required=True)
    sl.add_argument("--initiative-dir", dest="initiative_dir", required=True,
                    help="the v7 initiative folder (holding <name>.md and tickets/)")
    sl.add_argument("--epic", required=True, help="the epic's slug, e.g. epic-cart")
    sl.add_argument("--lane", required=True, help="a lane number, 1..lane_count")
    sl.set_defaults(func=cmd_set_lane)
