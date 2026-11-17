#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""
read-sharded.py -- read l3io 3.x's sharded state tree into records. Read-only.

The 3.x tree is `{implementation_artifacts}/state/{planned,active,archived}/epic-{nnn}/`:
`epic.yaml`, then `sprint-{nn}/sprint.yaml` and one `E{nnn}-S{nn}-{nnn}.yaml` per story,
each a bare node (status-files.md §4 in a 3.x release). The status folder an epic sits in
is placement only; the node's own `status` is the datum.

Every node becomes one record in state-record.py's shape, with each l3io-owned field it
carries (estimate, actual, completion evidence, orchestration, lane, sampling markers,
previous keys) in `extras`. Nothing is written; migrate-engine.py decides where each goes.

Usage:  read-sharded.py --dir STATE_ROOT [--format json]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "state_record", os.path.join(_HERE, "state-record.py"))
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)

STATUS_DIRS = ("planned", "active", "archived")


def _load(path: Path):
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.strip():
        return None
    try:
        node = YAML(typ="safe").load(text)
    except YAMLError:
        return None
    return node if isinstance(node, dict) else None


def epic_dirs(state_dir: Path) -> list:
    d = Path(state_dir)
    return sorted(p for s in STATUS_DIRS for p in (d / s).glob("epic-*")
                  if (p / "epic.yaml").is_file())


def is_sharded(state_dir: Path) -> bool:
    return bool(epic_dirs(state_dir))


def read(state_dir: Path) -> list:
    """Every epic, sprint and story node under `state_dir`, as records."""
    out = []
    for edir in epic_dirs(state_dir):
        epic = _load(edir / "epic.yaml")
        if epic is None:
            out.append(sr.make_record("epic", f"E{edir.name[5:]}", "unreadable", "",
                                      str(edir / "epic.yaml")))
            continue
        ekey = str(epic.get("key") or f"E{edir.name[5:]}").strip()
        out.append(sr.make_record("epic", ekey, str(epic.get("status", "backlog")),
                                  str(epic.get("title", "")), str(edir / "epic.yaml"),
                                  extras=sr.collect_extras(epic)))
        for sdir in sorted(edir.glob("sprint-*")):
            sprint = _load(sdir / "sprint.yaml")
            snum = sdir.name[len("sprint-"):]
            if sprint is not None:
                skey = str(sprint.get("key") or f"S{snum}").strip()
                out.append(sr.make_record("sprint", f"{ekey}-{skey}",
                                          str(sprint.get("status", "backlog")),
                                          str(sprint.get("title", "")),
                                          str(sdir / "sprint.yaml"),
                                          extras=sr.collect_extras(sprint)))
            for spath in sorted(sdir.glob("E*.yaml")):
                story = _load(spath)
                if story is None:
                    out.append(sr.make_record("story", spath.stem, "unreadable", "",
                                              str(spath)))
                    continue
                out.append(sr.make_record(
                    "story", str(story.get("key") or spath.stem).strip(),
                    str(story.get("status", "backlog")), str(story.get("title", "")),
                    str(spath),
                    classification=str(story.get("classification", "")).strip() or None,
                    extras=sr.collect_extras(story)))
    return sr.dedupe(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="read l3io 3.x's sharded state tree")
    parser.add_argument("--dir", required=True, help="the 3.x state root ({impl}/state)")
    parser.add_argument("--format", choices=["json"], default="json")
    args = parser.parse_args(argv)
    d = Path(args.dir)
    if not d.is_dir():
        sys.stderr.write(f"read-sharded.py: no such directory: {d}\n")
        return 1
    json.dump(read(d), sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
