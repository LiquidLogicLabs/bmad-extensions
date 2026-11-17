"""pm_status.sidecar -- l3io's own files beside BMad v7's ticket tree (status-files.md §12).

v7 owns the work-item tree: `tickets.toml`, leaf files and plans. l3io never writes them
(ADR-0015). What it records about that tree lives in TOML sidecars beside it -- `l3io.toml`
in a container's `tickets/` folder, `<plan-stem>.l3io.toml` beside a plan -- and this module
is how they are read and written: through `tomlkit`, so a comment or key order a person put
there survives every write, and under `flock`, so concurrent writers lose nothing.

NO PATH ASSEMBLY HERE. Which file a v7 address names is `nodes`' answer (`entry_sidecar`,
`ticket_sidecar`, `container_sidecar`, `project_state_root`), inside the resolver section
check 26 judges. This module only loads, locks and saves the path it is handed.

THE LOCK IS THE SIDECAR'S DIRECTORY. A lock file beside a sidecar would be one more
untracked file in the user's tree, and an untracked file is exactly what fails
`bmad-build-auto`'s clean-tree check. A directory can be `flock`ed directly, which serialises
every writer of every sidecar in one tickets folder and leaves nothing behind. It is not
reentrant: never hold `locked()` on a directory and call it again on the same one.

`tomlkit` is imported lazily, as `ruamel.yaml` is everywhere in this package, so a verb that
never touches a sidecar does not need it provisioned.

It also carries the CLI helpers for v7 addressing (`entry_address_args`,
`plan_address_args`), which `sidecar.verbs` and `metrics` call inside their own
`register`. They import nothing above `core`.
"""
from __future__ import annotations

import contextlib
import os
import tomllib

from .. import nodes
from ..core import METRIC_FIELDS, _atomic_text_write, _die_usage

# Keys a person may hand-set on a v7 `tickets.toml` entry that we read as an override and
# never write (spec §3.2). `estimate` is v7's own field; the prefix is required for the rest
# because `unknown`, `estimate`, `risk` and `notes` are theirs.
OVERRIDE_PREFIX = "l3io_"


def _tomlkit():
    import tomlkit

    return tomlkit


@contextlib.contextmanager
def locked(*dirs):
    """Exclusive flock on each directory, acquired in sorted order so two callers locking
    the same pair cannot deadlock. Missing directories are skipped (nothing to protect)."""
    try:
        import fcntl
    except ImportError:  # pragma: no cover - non-POSIX
        yield
        return
    fds = []
    try:
        for d in sorted({os.path.realpath(x) for x in dirs}):
            if not os.path.isdir(d):
                continue
            fd = os.open(d, os.O_RDONLY)
            fds.append(fd)
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        for fd in reversed(fds):
            with contextlib.suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def load(path: str):
    """The sidecar as a tomlkit document; an empty document when it does not exist."""
    tk = _tomlkit()
    if not os.path.exists(path):
        return tk.document()
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        return tk.parse(text)
    except Exception as e:  # noqa: BLE001 -- tomlkit raises several unrelated types
        _die_usage(f"{path} is not valid TOML: {e}")


def save(path: str, doc) -> None:
    """Atomic replace (temp file beside the target, fsync, os.replace)."""
    _atomic_text_write(path, _tomlkit().dumps(doc))


@contextlib.contextmanager
def edit(path: str):
    """Load-modify-save under the directory lock; saved only when the text changed."""
    with locked(os.path.dirname(path)):
        doc = load(path)
        before = _tomlkit().dumps(doc)
        yield doc
        if _tomlkit().dumps(doc) != before:
            save(path, doc)


def plain(v):
    """A ruamel/tomlkit value as plain Python: dicts, lists, scalars."""
    if hasattr(v, "unwrap"):
        return v.unwrap()
    if isinstance(v, dict):
        return {str(k): plain(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [plain(x) for x in v]
    return v


def table(doc, *keys):
    """The table at `keys` under `doc`, created on the way down when absent. Every table
    above the last is created as a super-table, so `[entry.3.estimate]` renders without an
    empty `[entry]` or `[entry.3]` header; tomlkit gives one a header once it holds a key."""
    tk = _tomlkit()
    cur = doc
    for i, k in enumerate(keys):
        if k not in cur:
            cur[k] = tk.table(is_super_table=i < len(keys) - 1)
        cur = cur[k]
    return cur


def put_metrics(tbl, values: dict) -> None:
    """Write `values` into a metric table, keeping the five metrics in canonical order.

    An update of keys already present is made in place, so a comment beside one survives.
    When a key is new the table is rebuilt in canonical order (the metrics first, then the
    rest as they stood), because tomlkit appends a new key at the end."""
    tk = _tomlkit()

    def item(k, v):
        v = plain(v)
        if isinstance(v, dict):
            it = tk.inline_table()
            it.update(v)
            return it
        return v

    if all(k in tbl for k in values):
        for k, v in values.items():
            tbl[k] = item(k, v)
        return
    merged = {**{k: tbl[k] for k in tbl}, **values}
    order = [m for m in METRIC_FIELDS if m in merged] + [k for k in merged if k not in METRIC_FIELDS]
    for k in list(tbl):
        del tbl[k]
    for k in order:
        tbl[k] = item(k, merged[k])


def read_entries(ticket_dir_toml: str) -> dict:
    """{str(id): entry} from a v7 `tickets.toml`, READ ONLY (stdlib tomllib). Missing -> {}."""
    if not os.path.isfile(ticket_dir_toml):
        return {}
    with open(ticket_dir_toml, "rb") as fh:
        try:
            data = tomllib.load(fh)
        except tomllib.TOMLDecodeError as e:
            _die_usage(f"{ticket_dir_toml} is not valid TOML: {e}")
    return {str(e.get("id")): e for e in data.get("entry", []) if isinstance(e, dict)}


def hand_set(entry: dict) -> dict:
    """The override keys a person set on one `tickets.toml` entry: `estimate`, and every
    `l3io_<name>` as `<name>`. Empty when there are none."""
    out = {}
    if "estimate" in entry and entry["estimate"] != "":
        out["hand_estimate"] = entry["estimate"]
    for k, v in entry.items():
        if k.startswith(OVERRIDE_PREFIX):
            out[k[len(OVERRIDE_PREFIX):]] = v
    return out


def effective_estimate(ticket_dir: str, entry_id) -> dict:
    """The estimate a reader should use for one entry.

    `{"source": "tickets.toml" | None, "hand_estimate": <raw value or None>,
      "class": <str or None>, "values": {metric: value}}`.

    Our `[entry.<id>].estimate` is the base. A hand-set `l3io_<metric>` on the entry in
    `tickets.toml` replaces that metric, and `l3io_class` the class; a bare `estimate` there
    (v7's own field, in whatever unit the user gave it) is carried verbatim as
    `hand_estimate` and marks the entry hand-estimated. `source` names `tickets.toml`
    whenever any override is present."""
    folder = nodes.v7_tickets_folder(ticket_dir)
    entry = read_entries(os.path.join(folder, "tickets.toml")).get(str(entry_id), {})
    side = plain(load(nodes.entry_sidecar(folder)))
    ours = side.get("entry", {}).get(str(entry_id), {})
    values = dict(ours.get("estimate", {}))
    over = hand_set(entry)
    for m in METRIC_FIELDS:
        if m in over:
            values[m] = over[m]
    return {
        "source": "tickets.toml" if over else None,
        "hand_estimate": over.get("hand_estimate"),
        "class": over.get("class", ours.get("class")),
        "values": values,
    }


# --------------------------------------------------------------------------- #
# CLI helpers: the v7 address flags, shared by every parser that takes one.
# --------------------------------------------------------------------------- #
def entry_address_args(sp):
    sp.add_argument("--project-root", dest="project_root", required=True,
                    help="v7 project root (state under {output_folder}/l3io/)")
    sp.add_argument("--ticket-dir", dest="ticket_dir", required=True,
                    help="v7 epic folder or its tickets/ folder")
    sp.add_argument("--entry", required=True, help="v7 tickets.toml entry id")


def plan_address_args(sp):
    sp.add_argument("--project-root", dest="project_root", required=True,
                    help="v7 project root (state under {output_folder}/l3io/)")
    sp.add_argument("--plan-file", dest="plan_file", required=True,
                    help="v7 ticket plan (<stem>-plan.md); its sidecar is <stem>-plan.l3io.toml")
