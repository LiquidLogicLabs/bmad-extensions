"""pm_status.nodes -- the resolver layer: the ONLY place an address becomes a path.

A v7 address -- a tickets folder, a plan file, an initiative folder, a project root --
becomes the path of OUR sidecar beside it (`entry_sidecar`, `ticket_sidecar`,
`container_sidecar`), and a project root becomes the project-wide state root
(`project_state_root`). The 3.x sharded-tree resolver that lived here (`find_epic_dir`,
`epic_file`/`sprint_file`/`story_file`, `ensure_node_path` and the node load/save pair)
retired with the migration-only verbs in Phase 6: the migration (`migrate-engine.py`)
reads the 3.x tree itself and writes only these sidecars.

It sits directly above `core` and below everything else.

check:docs check 26 ("state paths are assembled only in pm_status's resolver section")
judges each authored file of the package by ITS OWN marker pair, and the pair below is the
package's only one -- it travelled here with the code it delimits. A file carrying neither
marker has its whole body judged.
"""
from __future__ import annotations

import os
import sys

from ..core import _die_usage

# --------------------------------------------------------------------------- #
# State path resolution — the ONLY place an address becomes a state or sidecar path
# --------------------------------------------------------------------------- #
# 4.x sidecars beside BMad v7's ticket tree (status-files.md §12). v7 owns `tickets.toml`,
# leaf files and plans; these functions turn a v7 address -- a tickets folder, a plan file,
# an initiative folder, a project root -- into the path of OUR file beside it, and are the
# only place that does. None of them creates anything.
SIDECAR_NAME = "l3io.toml"
TICKET_SIDECAR_SUFFIX = ".l3io.toml"
V7_TICKETS = "tickets"


def v7_tickets_folder(folder: str) -> str:
    """The folder holding a container's `tickets.toml`, as `tickets.py` resolves it
    (`tickets_dir`, :180-192): `<folder>/tickets/` for an initiative or an epic, the folder
    itself for a backlog or when it already IS a `tickets/` folder."""
    folder = os.path.abspath(folder)
    if os.path.basename(folder) == V7_TICKETS or os.path.isfile(os.path.join(folder, "tickets.toml")):
        return folder
    name = os.path.basename(folder)
    if (os.path.isfile(os.path.join(folder, f"{name}.md"))
            or os.path.isdir(os.path.join(folder, V7_TICKETS))):
        return os.path.join(folder, V7_TICKETS)
    return folder


def entry_sidecar(ticket_dir: str) -> str:
    """`l3io.toml` beside an epic's `tickets.toml`: `[entry.<id>]` and `[epic]`."""
    return os.path.join(v7_tickets_folder(ticket_dir), SIDECAR_NAME)


def container_sidecar(initiative_dir: str) -> str:
    """`l3io.toml` beside an initiative's `tickets.toml`: `[epic.<slug>]`."""
    return os.path.join(v7_tickets_folder(initiative_dir), SIDECAR_NAME)


def ticket_sidecar(plan_file: str) -> str:
    """`<stem>.l3io.toml` beside the plan `<stem>.md`. Never a `.md`, so `tickets.py`'s
    folder scan (`*.md`, :322) cannot read it as a leaf or a plan."""
    plan_file = os.path.abspath(plan_file)
    if not plan_file.endswith(".md"):
        _die_usage(f"--plan-file must name a plan .md file, not {plan_file}")
    return plan_file[:-len(".md")] + TICKET_SIDECAR_SUFFIX


def plan_of_ticket_sidecar(sidecar: str) -> str:
    """The plan a ticket sidecar belongs beside -- the inverse of ticket_sidecar."""
    return sidecar[:-len(TICKET_SIDECAR_SUFFIX)] + ".md"


def v7_ticket_folders(initiative_dir: str) -> list:
    """Every tickets folder an initiative's sidecars can live in: its own and each epic's."""
    top = v7_tickets_folder(initiative_dir)
    out = [top]
    if os.path.isdir(top):
        for name in sorted(os.listdir(top)):
            p = os.path.join(top, name)
            if name.startswith("epic-") and os.path.isdir(p):
                out.append(v7_tickets_folder(p))
    return out


def v7_folder_by_name(initiative_dir: str, name: str):
    """A container named in `tickets.py move` output (`from`/`to` are folder NAMES): an epic
    of this initiative, else a sibling initiative or backlog, else an epic of a sibling
    initiative. None when nothing by that name exists."""
    top = v7_tickets_folder(initiative_dir)
    parent = os.path.dirname(os.path.abspath(initiative_dir))
    candidates = [os.path.join(top, name), os.path.join(parent, name)]
    if os.path.isdir(parent):
        candidates += [os.path.join(parent, sib, V7_TICKETS, name)
                       for sib in sorted(os.listdir(parent))]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None


_STATE_ROOTS: dict = {}


def project_state_root(project_root: str) -> str:
    """`{output_folder}/l3io/` of the MAIN checkout, from any worktree of it.

    Calibration, events, the ADR register and notices are project-wide, so every worktree
    of one clone must write the same files: a per-worktree state root would split the event
    log and the learned ratios once per epic branch. `core.output_folder` is resolved in
    `project_root` first and in the main checkout when that fails (a worktree whose `_bmad/`
    is not committed), then re-anchored on the main checkout. Exits 2 when neither resolves.
    """
    root = os.path.realpath(project_root)
    if root in _STATE_ROOTS:
        return _STATE_ROOTS[root]
    main = _main_worktree(root)
    value = _resolve_output_folder(root)
    if value is None and main != root:
        value = _resolve_output_folder(main)
    if value is None:
        _die_usage(f"cannot resolve core.output_folder for {root}: run "
                   "{project-root}/_bmad/scripts/resolve_config.py there (bmad setup installs "
                   "it)")
    out = value.replace("{project-root}", main)
    if os.path.isabs(out):
        rel = os.path.relpath(os.path.realpath(out), root)
        if rel != ".." and not rel.startswith(".." + os.sep):
            out = os.path.join(main, rel)
    else:
        out = os.path.join(main, out)
    _STATE_ROOTS[root] = os.path.join(os.path.normpath(out), "l3io")
    return _STATE_ROOTS[root]


TICKETS_PY = ("_bmad", "method", "scripts", "tickets.py")


def v7_tickets_py(project_root: str) -> str:
    """v7's `tickets.py`, where `bmad setup` installs Sofia's declared script."""
    return os.path.join(project_root, *TICKETS_PY)


INFLIGHT_DIR = ".inflight"


def inflight_dir(state_root: str) -> str:
    """The build bracket's spool under a project state root: one JSON file per open
    bracket, gitignored, so opening one never dirties the tree (`build`)."""
    return os.path.join(state_root, INFLIGHT_DIR)


# --------------------------------------------------------------------------- #
# end of the state path resolution section
# --------------------------------------------------------------------------- #


# Config helpers the resolver above calls: they read BMad core's resolver and git, and
# assemble no state path.
def _main_worktree(project_root: str) -> str:
    """The main checkout of the repository `project_root` is in: the directory holding the
    common git dir, which every linked worktree shares. Not a git work tree -> itself."""
    import subprocess

    try:
        r = subprocess.run(["git", "-C", project_root, "rev-parse", "--path-format=absolute",
                            "--git-common-dir"], capture_output=True, text=True, check=False)
    except OSError:
        return project_root
    common = r.stdout.strip()
    if r.returncode != 0 or not common:
        return project_root
    return os.path.realpath(os.path.dirname(common))


def resolve_config_key(project_root: str, key: str):
    """One dotted key through BMad core's own resolver (never a TOML read of ours: the
    layering is core's). None when the project has no resolver, it fails, or the key is
    absent."""
    import json
    import shutil
    import subprocess

    script = os.path.join(project_root, "_bmad", "scripts", "resolve_config.py")
    if not os.path.isfile(script):
        return None
    runner = (["uv", "run", "--quiet", "--no-project"] if shutil.which("uv")
              else [sys.executable])
    r = subprocess.run([*runner, script, "--project-root", project_root, "--key", key],
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout).get(key)
    except (ValueError, AttributeError):
        return None


def _resolve_output_folder(project_root: str):
    """`core.output_folder`; None when the project names no folder."""
    value = resolve_config_key(project_root, "core.output_folder")
    return value if isinstance(value, str) and value.strip() else None
