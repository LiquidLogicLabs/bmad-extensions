"""pm_status.nodes -- the node layer: the ONLY place a node key becomes a path.

Two resolvers, kept apart. The 3.x sharded tree (`find_epic_dir`,
`epic_file`/`sprint_file`/`story_file`, `resolve_node_path`, `ensure_node_path`, the node
load/save pair and the story enumerators) serves the migration's writers (`import-node`,
`import-actual`) and retires with them in Phase 6; the v7 sidecar resolvers (`entry_sidecar`,
`ticket_sidecar`, `project_state_root`, ...) are the 4.x layout.

It sits directly above `core` and below everything else: the metrics layer and the verbs
all reach state through here.

check:docs check 26 ("state paths are assembled only in pm-status.py's resolver
section") judges each authored file of the package by ITS OWN marker pair, and the pair
below is the package's only one -- it travelled here with the code it delimits. A file
carrying neither marker has its whole body judged, which is now the rule `__main__.py`
lives under: it assembles no state path at all, and must not start.

CALL STYLE ACROSS MODULES. `core._load` is reached through the MODULE OBJECT, because
the suite patches it (`patch.object(pm.core, "_load", ...)`) and a `from ..core import
_load` binding here would be a private copy the patch could never reach. The other core
names are imported by name -- none of them is a patch target.

THE SAME RULE APPLIES TO THIS MODULE'S OWN EXPORTS. `save_node` and `epic_file` are
mock.patch targets (`pm.nodes.save_node`, `pm.nodes.epic_file`), so `__main__.py` calls
them as `nodes.save_node(...)` / `nodes.epic_file(...)` and does NOT re-export them: a
`pm.save_node` binding left beside `pm.nodes.save_node` is a second thing to patch, and
the wrong one passes silently. Everything else here is re-exported into `__main__` by
name, because `pm_status.<name>` is `__main__`'s globals through the `__init__.py`
facade and the suite reads these directly. Promote a re-exported name to
module-qualified the moment the suite starts patching it.
"""
from __future__ import annotations

import contextlib
import os
import sys

from .. import core
from ..core import (
    DIR_FOR_STATUS,
    STATUS_DIRS,
    _die_notfound,
    _die_usage,
    _flock_write_or_plain,
    epic_dirname,
    epic_node_lock,
    parse_story_key,
    sprint_dirname,
)


# --------------------------------------------------------------------------- #
# Sharded layout resolution — the ONLY place that knows where nodes live on disk
# --------------------------------------------------------------------------- #
def find_epic_dir(state_root: str, epic_key: str):
    """Absolute path to the epic's directory, whichever status folder holds it."""
    name = epic_dirname(epic_key)
    for status in STATUS_DIRS:
        p = os.path.join(state_root, status, name)
        if os.path.isdir(p):
            return p
    return None


def epic_file(state_root: str, epic_key: str):
    d = find_epic_dir(state_root, epic_key)
    if d is None:
        return None
    p = os.path.join(d, "epic.yaml")
    return p if os.path.exists(p) else None


def sprint_file(state_root: str, epic_key: str, sprint_key: str):
    d = find_epic_dir(state_root, epic_key)
    if d is None:
        return None
    p = os.path.join(d, sprint_dirname(sprint_key), "sprint.yaml")
    return p if os.path.exists(p) else None


def story_file(state_root: str, story_key: str):
    epic_key, sprint_key, _ = parse_story_key(story_key)
    d = find_epic_dir(state_root, epic_key)
    if d is None:
        return None
    p = os.path.join(d, sprint_dirname(sprint_key), f"{story_key}.yaml")
    return p if os.path.exists(p) else None


def load_node(path: str):
    """Load a bare node file (no `epics:` wrapper). Returns (yaml, node|None)."""
    return core._load(path)


def save_node(y, node, path: str, use_flock: bool = False) -> None:
    _flock_write_or_plain(use_flock, y, node, path)


def check_backrefs(node, epic_key: str, sprint_key: str | None = None) -> list:
    """Compare a node's parent back-references against its resolved location.

    An ABSENT back-reference is a failure, not a pass. Sprint and story files are
    required to carry `epic:` (and stories `sprint:`) — see status-files.md §4 — and
    migrate-state adds them as a brand-new step, so "field missing entirely" is exactly
    the case this check has to catch. Epic nodes have no parent and are never passed
    here (callers skip them).
    """
    problems = []
    if node is None:
        return ["node is empty"]
    got_epic = str(node.get("epic", "")).strip()
    if not got_epic:
        problems.append(f"epic back-reference absent (expected {str(epic_key).strip()!r})")
    elif got_epic != str(epic_key).strip():
        problems.append(f"epic back-reference {got_epic!r} != path epic {epic_key!r}")
    if sprint_key is not None:
        got_sprint = str(node.get("sprint", "")).strip()
        if not got_sprint:
            problems.append(f"sprint back-reference absent (expected {str(sprint_key).strip()!r})")
        elif got_sprint != str(sprint_key).strip():
            problems.append(f"sprint back-reference {got_sprint!r} != path sprint {sprint_key!r}")
    return problems


def resolve_node_path(state_root: str, args, kind: str):
    """Resolve a node kind + keys to (path, label). Exits 3 when the node is absent."""
    if kind == "story":
        if not args.story:
            _die_usage("--story is required for a story node")
        p = story_file(state_root, args.story)
        label = f"story {args.story}"
    elif kind == "sprint":
        if not (args.epic and args.sprint):
            _die_usage("--epic and --sprint are required for a sprint node")
        p = sprint_file(state_root, args.epic, args.sprint)
        label = f"epic {args.epic} sprint {args.sprint}"
    elif kind == "epic":
        if not args.epic:
            _die_usage("--epic is required for an epic node")
        p = epic_file(state_root, args.epic)
        label = f"epic {args.epic}"
    else:
        _die_usage(f"unknown node kind: {kind}")
    if p is None:
        _die_notfound(label)
    return p, label


def ensure_node_path(state_root: str, args, kind: str, status: str):
    """Resolve a node kind + keys to (path, label), CREATING the directory when absent.

    The counterpart to resolve_node_path() for the one case that function cannot serve:
    a node that does not exist yet. It is the ONLY function that creates a state
    directory, and it lives here -- in the section that is the only place a key becomes
    a location -- on purpose. A mkdir in a subcommand body is exactly how that invariant
    breaks; check 26 in check-docs.mjs fails the build if one appears.

    A NEW epic is placed by its status, per the placement rule. An epic that already has
    a directory is left where it is. Sprints and stories require their epic's
    directory to exist and exit 3 when it does not.
    """
    if kind == "epic" and status not in DIR_FOR_STATUS:
        _die_usage(
            f"cannot place a new epic with status {status!r} -- "
            f"expected one of {sorted(DIR_FOR_STATUS)}"
        )
    if kind == "epic":
        if not args.epic:
            _die_usage("--epic is required for an epic node")
        d = find_epic_dir(state_root, args.epic)
        if d is None:
            d = os.path.join(state_root, DIR_FOR_STATUS[status], epic_dirname(args.epic))
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "epic.yaml"), f"epic {args.epic}"

    if kind == "sprint":
        if not (args.epic and args.sprint):
            _die_usage("--epic and --sprint are required for a sprint node")
        d = find_epic_dir(state_root, args.epic)
        if d is None:
            _die_notfound(f"epic {args.epic} (create it before its sprints)")
        sd = os.path.join(d, sprint_dirname(args.sprint))
        os.makedirs(sd, exist_ok=True)
        return os.path.join(sd, "sprint.yaml"), f"epic {args.epic} sprint {args.sprint}"

    if kind == "story":
        if not args.story:
            _die_usage("--story is required for a story node")
        epic_key, sprint_key, _ = parse_story_key(args.story)
        d = find_epic_dir(state_root, epic_key)
        if d is None:
            _die_notfound(f"epic {epic_key} (create it before its stories)")
        sd = os.path.join(d, sprint_dirname(sprint_key))
        os.makedirs(sd, exist_ok=True)
        return os.path.join(sd, f"{args.story}.yaml"), f"story {args.story}"

    _die_usage(f"unknown node kind: {kind}")


def _load_checked(state_root: str, args, kind: str):
    """Resolve, load, and validate back-references. Exits 3 (missing) or 4 (misplaced)."""
    path, label = resolve_node_path(state_root, args, kind)
    y, node = load_node(path)
    if node is None:
        _die_notfound(f"{label} — file {path} is empty")
    if kind == "story":
        ek, sk, _ = parse_story_key(args.story)
        problems = check_backrefs(node, ek, sk)
    elif kind == "sprint":
        problems = check_backrefs(node, args.epic)
    else:
        problems = []
    if problems:
        sys.stderr.write(f"pm-status.py: back-reference mismatch for {label}: {'; '.join(problems)}\n")
        sys.exit(4)
    return y, node, path, label


def _infer_kind(args) -> str:
    if args.story:
        return "story"
    if args.epic and args.sprint:
        return "sprint"
    if args.epic:
        return "epic"
    _die_usage("specify --story, or --epic [--sprint]")


def _epic_write_lock(args, kind, require_exists: bool = True):
    """epic_node_lock around a node verb's read-modify-write when the node is an epic; no
    lock for a sprint or story, whose files are not epic.yaml. Resolves the epic first, so
    an absent one exits 3 exactly as before with no lock file created; the verb resolves
    again inside the hold, since a directory move may land while it waits.

    require_exists=False is for import-node, whose whole purpose is the node that does not
    exist yet. It still takes the lock -- a concurrent import of the same epic must
    serialise -- it just does not demand the node be there first. Every other caller keeps
    the default, so their behaviour is unchanged.
    """
    if kind != "epic":
        return contextlib.nullcontext()
    if require_exists:
        resolve_node_path(args.state_root, args, "epic")
    return epic_node_lock(args.state_root, args.epic)


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
                   "it), or pass --state-root for a 3.x state tree")
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
# computed roll-ups — sprint/epic aggregates over per-story child files
# --------------------------------------------------------------------------- #
def list_sprint_dirs(state_root: str, epic_key: str) -> list:
    """Sorted sprint directories for an epic. Lexical sort is correct order (zero-padded)."""
    d = find_epic_dir(state_root, epic_key)
    if d is None:
        return []
    return sorted(os.path.join(d, n) for n in os.listdir(d)
                  if n.startswith("sprint-") and os.path.isdir(os.path.join(d, n)))


def _sprint_key_from_dir(sprint_dir_path: str) -> str:
    """'.../epic-001/sprint-01' -> 'S01'. Inverse of sprint_dirname for a path from
    list_sprint_dirs."""
    return "S" + os.path.basename(sprint_dir_path).split("-")[1]


def list_story_files(state_root: str, epic_key: str, sprint_key: str) -> list:
    """Sorted story files in a sprint, excluding sprint.yaml."""
    d = find_epic_dir(state_root, epic_key)
    if d is None:
        return []
    sd = os.path.join(d, sprint_dirname(sprint_key))
    if not os.path.isdir(sd):
        return []
    return sorted(os.path.join(sd, n) for n in os.listdir(sd)
                  if n.endswith(".yaml") and n != "sprint.yaml")
