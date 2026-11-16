#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["tomlkit>=0.13"]
# ///
"""
wire-in.py -- attach l3io entries to a team's BMad v7 customization files, and remove them.

Why this exists (ADR-0020)
--------------------------
BMad v7 resolves every customizable skill from three layers: the skill's shipped
`customize.toml`, the team's `_bmad/custom/<skill>.toml`, and the user's
`_bmad/custom/<skill>.user.toml`. A module has no layer of its own, so attaching our lenses,
facts and hooks means writing into the team's file -- a file the team also edits by hand.
This script is the one place that does it. It is round-trip safe (tomlkit), idempotent,
never overwrites a team's value, and records what it added so `unwire` removes exactly that.

Entry kinds (`assets/wire-in.toml`), and the resolver semantics each one follows
---------------------------------------------------------------------------------
The v7 resolver (`config_utils.structural_merge`) replaces scalars, appends plain arrays,
and merges arrays of tables by `code`, else `id`, when every item carries that field.

  keyed   one table appended to an array of tables (`workflow.lenses`, `agent.menu`).
          Identity is the item's `code`, else its `id` -- the resolver's own order. An item
          the team already holds under that identity wins and ours is not added. The
          identity must start with `l3io-`: an identity equal to a shipped default's would,
          from the team layer, REPLACE BMad's own entry rather than add beside it.
  list    one string appended to a plain array (`activation_steps_*`, `persistent_facts`),
          never twice.
  scalar  a single-slot string hook (`on_complete`, `tickets_after`). Set only when the key
          is absent or empty; any other team value is a refusal naming both values.

Byte-exact unwire
-----------------
The ledger (`{output_folder}/l3io/wire-in.json`) keeps, per file, the bytes it held before
our first write and the SHA-256 of what we last wrote. If the file still hashes to that,
unwire puts the old bytes back (or deletes a file we created). If the team has edited it
since, unwire removes only the entries it recorded, each only while it still equals what
we wrote, and says so. A later wire over a team-edited file voids the saved bytes, because
restoring them would discard the team's edit.

Exit codes: 0 done (or nothing to do), 3 one or more refusals -- nothing written for those
entries, everything else applied -- 2 usage, an invalid entries file, or a TOML parse error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import tomlkit
    from tomlkit.exceptions import TOMLKitError
    from tomlkit.items import AoT, Array, Table
except ImportError:  # pragma: no cover
    sys.stderr.write("error: tomlkit is required. Run this script with `uv run`.\n")
    sys.exit(2)

EXIT_OK, EXIT_USAGE, EXIT_REFUSED = 0, 2, 3
KINDS = ("keyed", "list", "scalar")
IDENTITY_FIELDS = ("code", "id")  # config_utils._KEYED_MERGE_FIELDS, in its order
OUR_PREFIX = "l3io-"
SKILL_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PATH_RE = re.compile(r"^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)+$")
LEDGER_VERSION = 1
DEFAULT_ENTRIES = Path(__file__).resolve().parent.parent / "assets" / "wire-in.toml"


class UsageError(Exception):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def plain(value: Any) -> Any:
    return value.unwrap() if hasattr(value, "unwrap") else value


# --------------------------------------------------------------------------- config


def resolve_output_folder(root: Path, override: str | None) -> Path:
    """`core.output_folder` from BMad's resolver, `{project-root}` expanded.

    v7 returns the value as written in `_bmad/config.toml`, which is the literal
    `{project-root}/_bmad-output`; taking it unexpanded would put the ledger in a directory
    named `{project-root}`. A resolver that is present but fails is fatal rather than a
    fallback: a ledger written somewhere a later unwire does not look is unrecoverable.
    """
    if override:
        value = override
    else:
        value = "{project-root}/_bmad-output"
        resolver = root / "_bmad" / "scripts" / "resolve_config.py"
        if resolver.is_file():
            proc = subprocess.run(
                [sys.executable, str(resolver), "--project-root", str(root),
                 "--key", "core.output_folder"],
                capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                raise UsageError(f"{resolver} failed (exit {proc.returncode}): "
                                 f"{proc.stderr.strip()}")
            try:
                found = json.loads(proc.stdout).get("core.output_folder")
            except json.JSONDecodeError as e:
                raise UsageError(f"{resolver} printed non-JSON: {e}") from e
            if isinstance(found, str) and found.strip():
                value = found
    value = value.replace("{project-root}", str(root))
    out = Path(value)
    return out if out.is_absolute() else root / out


def ledger_path(output_folder: Path) -> Path:
    return output_folder / "l3io" / "wire-in.json"


def load_ledger(path: Path) -> dict:
    if not path.is_file():
        return {"version": LEDGER_VERSION, "files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise UsageError(f"ledger {path} is not valid JSON: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        raise UsageError(f"ledger {path} has no `files` map")
    return data


def save_ledger(path: Path, ledger: dict) -> None:
    if not ledger["files"]:
        if path.exists():
            path.unlink()
        return
    atomic_write(path, (json.dumps(ledger, indent=2, sort_keys=True) + "\n").encode())


# --------------------------------------------------------------------------- entries


def load_entries(path: Path, include_test_only: bool) -> list[dict]:
    try:
        doc = tomlkit.parse(path.read_text(encoding="utf-8")).unwrap()
    except OSError as e:
        raise UsageError(f"cannot read entries file {path}: {e}") from e
    except (TOMLKitError, UnicodeDecodeError) as e:
        raise UsageError(f"entries file {path} is not valid TOML: {e}") from e
    raw = doc.get("entry", [])
    if not isinstance(raw, list):
        raise UsageError(f"{path}: `entry` must be an array of tables")
    seen: set[str] = set()
    entries = []
    for i, e in enumerate(raw):
        where = f"{path}: entry {i + 1}"
        if not isinstance(e, dict):
            raise UsageError(f"{where}: not a table")
        eid, skill, kind, dotted = e.get("id"), e.get("skill"), e.get("kind"), e.get("path")
        if not isinstance(eid, str) or not eid or eid in seen:
            raise UsageError(f"{where}: `id` must be a unique non-empty string")
        seen.add(eid)
        if not isinstance(skill, str) or not SKILL_RE.match(skill):
            raise UsageError(f"{where} ({eid}): `skill` must be a skill name, got {skill!r}")
        if kind not in KINDS:
            raise UsageError(f"{where} ({eid}): `kind` must be one of {', '.join(KINDS)}")
        if not isinstance(dotted, str) or not PATH_RE.match(dotted):
            raise UsageError(f"{where} ({eid}): `path` must be a dotted key such as "
                             f"`workflow.lenses`, got {dotted!r}")
        value = e.get("value")
        if kind == "keyed":
            if not isinstance(value, dict):
                raise UsageError(f"{where} ({eid}): a keyed entry's `value` is a table")
            field = next((f for f in IDENTITY_FIELDS if f in value), None)
            ident = value.get(field) if field else None
            if not isinstance(ident, str) or not ident.startswith(OUR_PREFIX):
                raise UsageError(f"{where} ({eid}): a keyed entry needs a `code` or `id` "
                                 f"starting with `{OUR_PREFIX}`, got {ident!r}")
            e = {**e, "field": field, "ident": ident}
        elif not isinstance(value, str) or not value:
            raise UsageError(f"{where} ({eid}): a {kind} entry's `value` is a non-empty string")
        if e.get("test_only") and not include_test_only:
            continue
        entries.append(e)
    return entries


# --------------------------------------------------------------------------- tree walking


def find_parent(doc, dotted: str):
    """The container holding the last key of `dotted`, or None if a segment is absent.
    Raises TypeError when a segment exists but is not a table."""
    node = doc
    for part in dotted.split(".")[:-1]:
        if part not in node:
            return None
        node = node[part]
        if not isinstance(node, (Table, dict)):
            raise TypeError(f"`{part}` is not a table")
    return node


def ensure_parent(doc, dotted: str) -> tuple[Any, list[str]]:
    """The parent table of `dotted`, creating missing tables; returns those it created."""
    node, created, prefix = doc, [], []
    for part in dotted.split(".")[:-1]:
        prefix.append(part)
        if part not in node:
            node[part] = tomlkit.table(is_super_table=True)
            created.append(".".join(prefix))
        node = node[part]
        if not isinstance(node, (Table, dict)):
            raise TypeError(f"`{'.'.join(prefix)}` is not a table")
    return node, created


def custom_rel(skill: str) -> str:
    return f"_bmad/custom/{skill}.toml"


def recorded(rec: dict | None, eid: str) -> dict | None:
    if not rec:
        return None
    return next((x for x in rec["entries"] if x["id"] == eid), None)


def apply_entry(doc, e: dict, rec: dict | None) -> tuple[str, str, dict | None]:
    """Apply one entry to `doc`. Returns (status, detail, ledger record or None)."""
    dotted, leaf, kind = e["path"], e["path"].split(".")[-1], e["kind"]
    mine = recorded(rec, e["id"])
    try:
        parent = find_parent(doc, dotted)
    except TypeError as err:
        return "refused", f"{dotted}: {err}", None
    current = parent.get(leaf) if parent is not None else None

    if kind == "keyed":
        if current is not None and not isinstance(current, (AoT, list)):
            return "refused", f"{dotted} is not an array of tables", None
        for item in current or []:
            if isinstance(item, (Table, dict)) and plain(item.get(e["field"])) == e["ident"]:
                if mine:
                    return "already", f"{dotted} {e['field']}={e['ident']}", None
                return ("yielded", (f"{dotted} already holds a team entry with "
                                    f"{e['field']}={e['ident']}; the team's wins"), None)
    elif kind == "list":
        if current is not None and not isinstance(current, (Array, list)):
            return "refused", f"{dotted} is not an array", None
        if current is not None and e["value"] in plain(current):
            if mine:
                return "already", f"{dotted} holds {e['value']!r}", None
            return "present", f"{dotted} already holds {e['value']!r} (the team's)", None
    else:
        have = plain(current) if current is not None else None
        if have == e["value"]:
            if mine:
                return "already", f"{dotted} = {e['value']!r}", None
            return "present", f"{dotted} already = {e['value']!r} (the team's)", None
        if have is not None and have != "":
            return ("refused", (f"{dotted} is already set by the team to {have!r}; l3io "
                                f"wants {e['value']!r}. A single-value hook holds one value -- "
                                f"compose the two by hand or clear the team's value, then "
                                f"re-run"), None)

    parent, created = ensure_parent(doc, dotted)
    record = {"id": e["id"], "kind": kind, "path": dotted, "created": created,
              "value": e["value"]}
    if kind == "keyed":
        if leaf not in parent:
            parent[leaf] = tomlkit.aot()
            created.append(dotted)
        table = tomlkit.table()
        for k, v in e["value"].items():
            table[k] = v
        parent[leaf].append(table)
        record.update(field=e["field"], ident=e["ident"])
    elif kind == "list":
        if leaf not in parent:
            parent[leaf] = tomlkit.array()
            created.append(dotted)
        parent[leaf].append(e["value"])
    else:
        record["prior"] = "absent" if leaf not in parent else ""
        parent[leaf] = e["value"]
    return "applied", dotted, record


# --------------------------------------------------------------------------- wire


def cmd_wire(args) -> tuple[int, list[dict]]:
    root = Path(args.project_root).resolve()
    entries = load_entries(Path(args.entries) if args.entries else DEFAULT_ENTRIES,
                           args.include_test_only)
    lpath = ledger_path(resolve_output_folder(root, args.output_folder))
    ledger = load_ledger(lpath)

    by_file: dict[str, list[dict]] = {}
    for e in entries:
        by_file.setdefault(custom_rel(e["skill"]), []).append(e)

    # Parse every target before writing any, so a parse error writes nothing at all.
    parsed = {}
    for rel in by_file:
        path = root / rel
        before = path.read_bytes() if path.is_file() else None
        try:
            doc = tomlkit.parse(before.decode("utf-8")) if before is not None else \
                tomlkit.document()
        except (TOMLKitError, UnicodeDecodeError) as err:
            raise UsageError(f"{rel}: not valid TOML, nothing written: {err}") from err
        parsed[rel] = (path, before, doc)

    results, refused, ledger_dirty = [], False, False
    for rel, file_entries in by_file.items():
        path, before, doc = parsed[rel]
        rec = ledger["files"].get(rel)
        new_records = []
        for e in file_entries:
            status, detail, record = apply_entry(doc, e, rec)
            refused |= status == "refused"
            results.append({"id": e["id"], "file": rel, "status": status, "detail": detail})
            if record:
                new_records.append(record)
        if not new_records:
            continue
        after = doc.as_string().encode("utf-8")
        atomic_write(path, after)
        before_bytes = before if before is not None else b""
        if rec is None:
            rec = {"created": before is None, "pre_wire": before_bytes.decode("utf-8"),
                   "entries": []}
            ledger["files"][rel] = rec
        elif sha256(before_bytes) != rec.get("post_wire_sha256"):
            # Edited since our last write: the saved bytes would discard that edit.
            rec["pre_wire"] = None
            rec["created"] = rec.get("created", False) or before is None
        rec["entries"] = [x for x in rec["entries"]
                          if x["id"] not in {r["id"] for r in new_records}] + new_records
        rec["post_wire_sha256"] = sha256(after)
        ledger_dirty = True
    if ledger_dirty:
        save_ledger(lpath, ledger)
    return (EXIT_REFUSED if refused else EXIT_OK), results


# --------------------------------------------------------------------------- unwire


def remove_entry(doc, r: dict) -> str:
    dotted, leaf = r["path"], r["path"].split(".")[-1]
    try:
        parent = find_parent(doc, dotted)
    except TypeError:
        parent = None
    if parent is None or leaf not in parent:
        return "gone"
    current = parent[leaf]
    if r["kind"] == "keyed":
        for i, item in enumerate(current):
            if isinstance(item, (Table, dict)) and plain(item.get(r["field"])) == r["ident"]:
                if plain(item) != r["value"]:
                    return "left (edited since wire)"
                del current[i]
                break
        else:
            return "gone"
    elif r["kind"] == "list":
        values = plain(current)
        if not isinstance(values, list) or r["value"] not in values:
            return "gone"
        del current[values.index(r["value"])]
    else:
        if plain(current) != r["value"]:
            return "left (edited since wire)"
        if r.get("prior") == "absent":
            del parent[leaf]
        else:
            parent[leaf] = ""
    for dotted_created in sorted(r.get("created", []), key=lambda p: -p.count(".")):
        try:
            holder = find_parent(doc, dotted_created)
        except TypeError:
            continue
        key = dotted_created.split(".")[-1]
        if holder is not None and key in holder and len(holder[key]) == 0:
            del holder[key]
    return "removed"


def cmd_unwire(args) -> tuple[int, list[dict]]:
    root = Path(args.project_root).resolve()
    lpath = ledger_path(resolve_output_folder(root, args.output_folder))
    ledger = load_ledger(lpath)
    results, code = [], EXIT_OK
    for rel in list(ledger["files"]):
        rec, path = ledger["files"][rel], root / rel
        if not path.is_file():
            results.append({"file": rel, "status": "gone", "detail": "file no longer exists"})
            del ledger["files"][rel]
            continue
        now = path.read_bytes()
        if sha256(now) == rec.get("post_wire_sha256") and rec.get("pre_wire") is not None:
            if rec.get("created"):
                path.unlink()
                results.append({"file": rel, "status": "deleted",
                                "detail": "created by wire and unchanged since"})
            else:
                atomic_write(path, rec["pre_wire"].encode("utf-8"))
                results.append({"file": rel, "status": "restored",
                                "detail": "unchanged since wire; pre-wire bytes restored"})
            del ledger["files"][rel]
            continue
        try:
            doc = tomlkit.parse(now.decode("utf-8"))
        except (TOMLKitError, UnicodeDecodeError) as err:
            results.append({"file": rel, "status": "error", "detail": f"not valid TOML: {err}"})
            code = EXIT_USAGE
            continue
        for r in reversed(rec["entries"]):
            results.append({"file": rel, "id": r["id"], "status": remove_entry(doc, r),
                            "detail": f"{r['path']} (file edited since wire)"})
        if rec.get("created") and len(doc) == 0:
            path.unlink()
            results.append({"file": rel, "status": "deleted",
                            "detail": "created by wire; held nothing but our entries"})
        else:
            after = doc.as_string().encode("utf-8")
            if after != now:
                atomic_write(path, after)
        del ledger["files"][rel]
    save_ledger(lpath, ledger)
    return code, results


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Attach l3io entries to, or remove them from, "
                                "a team's _bmad/custom/<skill>.toml files (ADR-0020).")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("wire", "unwire"):
        s = sub.add_parser(name)
        s.add_argument("--project-root", required=True)
        s.add_argument("--output-folder",
                       help="override core.output_folder (where the ledger lives)")
        s.add_argument("--format", choices=("text", "json"), default="text")
        if name == "wire":
            s.add_argument("--entries", help="entries file (default: assets/wire-in.toml)")
            s.add_argument("--include-test-only", action="store_true",
                           help="also apply entries marked test_only")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code, results = (cmd_wire if args.cmd == "wire" else cmd_unwire)(args)
    except UsageError as err:
        sys.stderr.write(f"error: {err}\n")
        return EXIT_USAGE
    if args.format == "json":
        print(json.dumps({"command": args.cmd, "exit": code, "results": results}, indent=2))
    else:
        if not results:
            print(f"{args.cmd}: nothing to do")
        for r in results:
            label = f"{r['file']} [{r['id']}]" if "id" in r else r["file"]
            print(f"{r['status']:<9} {label}: {r['detail']}")
    return code


if __name__ == "__main__":
    sys.exit(main())
