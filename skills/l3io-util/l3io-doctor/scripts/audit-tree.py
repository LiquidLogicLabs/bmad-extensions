#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""
audit-tree.py -- the backlog integrity audit over BMad v7's ticket tree. Read-only.

On v7 the backlog is v7's: `{output_folder}/backlog/` leaves (`bug-<slug>.md` and the like),
each epic's `tickets/tickets.toml`, and the plans beside the leaves. l3io keeps only its
sidecars there (`l3io.toml`, `<stem>-plan.l3io.toml`). This script re-expresses the 3.x
`audit-issues` findings 1a-1l over that tree. It writes nothing: every finding carries a
repair that is a proposal -- for Sofia (`bmad-agent-po`: REFINE, or a BOARD `move` / `mark`),
or `pm-status.py sidecar-reconcile` for our own sidecars. `/l3io-doctor triage` presents them.

Findings with no v7 meaning are never emitted: 1a (two issue files), 1e (a stored key
allocator -- v7 derives `next_id` from the tree), 1g (archive placement -- v7 has none) and
1j (a resolution that disagrees with its story -- a v7 ticket's state is its plan's status).

It also reports `markers`: for each leaf in `backlog/` whose body cites a
`code-marker (<file>:<line>)`, whether that `bmad-defer:` marker is still in the source.

Usage
-----
  audit-tree.py --project-root P --output-folder O [--format {text,json}]
Exit 0 with no findings, 4 with findings (verdicts in `markers` never set the exit), 2 on a
usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

import yaml

sys.dont_write_bytecode = True

FINDINGS = ("1b", "1c", "1d", "1f", "1h", "1i", "1k", "1l")
PLAN_STATUSES = ("", "draft", "ready-for-dev", "in-progress", "in-review", "built", "done",
                 "blocked", "dropped")
LEAF_TYPES = ("story", "spike", "bug")
SEVERITIES = ("P0", "P1", "P2", "P3")
LEAF_RE = re.compile(r"^(story|spike|bug)-.+\.md$")
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---(?:\n|\Z)", re.DOTALL)
CODE_MARKER_RE = re.compile(r"code-marker \(?([^():\s]+):(\d+)\)?")
SIDECAR = "l3io.toml"
PLAN_SIDECAR_SUFFIX = "-plan.l3io.toml"
SOFIA = "Sofia (bmad-agent-po)"


def frontmatter(path: Path) -> dict:
    m = FRONTMATTER_RE.match(path.read_text(encoding="utf-8", errors="replace"))
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1) + "\n")
    except yaml.YAMLError:
        return {"_unparseable": True}
    return data if isinstance(data, dict) else {"_unparseable": True}


def norm(text) -> str:
    return " ".join(str(text).split()).casefold()


class Audit:
    def __init__(self, project_root: Path, output: Path):
        self.root = project_root
        self.output = output
        self.findings: list[dict] = []
        self.markers: list[dict] = []

    def rel(self, p: Path) -> str:
        try:
            return str(p.relative_to(self.root))
        except ValueError:
            return str(p)

    def add(self, fid, path, detail, repair):
        self.findings.append({"id": fid, "path": self.rel(path), "detail": detail,
                              "repair": repair})

    # -- the folders that hold tickets: every epic's tickets/, plus backlog/ ---------------
    def ticket_folders(self):
        backlog = self.output / "backlog"
        folders = []
        for toml in sorted(self.output.rglob("tickets/tickets.toml")):
            folder = toml.parent
            if (folder / "tickets.toml").is_file() and folder.parent.name.startswith("epic-"):
                folders.append(folder)
        if backlog.is_dir():
            folders.append(backlog)
        return folders, backlog

    def entry_ids(self, folder: Path) -> list[str] | None:
        path = folder / "tickets.toml"
        if not path.is_file():
            return None
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            return None
        return [str(e.get("id")) for e in data.get("entry", []) if isinstance(e, dict)]

    def run(self):
        if not self.output.is_dir():
            return
        folders, backlog = self.ticket_folders()
        epics = {f.parent.name for f in folders if f != backlog}
        plans_by_name: dict[str, list[Path]] = {}
        for folder in folders:
            for p in folder.glob("*-plan.md"):
                plans_by_name.setdefault(p.name, []).append(p)
        for folder in folders:
            self.folder(folder, folder == backlog, epics, plans_by_name)

    def folder(self, folder, is_backlog, epics, plans_by_name):
        entries = self.entry_ids(folder)
        if entries is not None:
            for dup in sorted({i for i in entries if entries.count(i) > 1}):
                self.add("1i", folder / "tickets.toml", f"two entries with id {dup}",
                         f"report only -- ask {SOFIA} to REFINE the breakdown so each id is "
                         f"one entry")
        leaves = {}
        for p in sorted(folder.glob("*.md")):
            if p.name.endswith("-plan.md") or not LEAF_RE.match(p.name):
                continue
            fm = frontmatter(p)
            leaves[p] = fm
            self.leaf(p, fm, is_backlog, epics)
        by_id: dict[str, list[Path]] = {}
        for p, fm in leaves.items():
            if fm.get("id") not in (None, ""):
                by_id.setdefault(str(fm["id"]), []).append(p)
        for tid, paths in sorted(by_id.items()):
            if len(paths) > 1:
                self.add("1i", paths[0], f"{len(paths)} leaves carry id {tid}: "
                         f"{', '.join(p.name for p in paths)}",
                         f"report only -- ask {SOFIA} to REFINE one of them to a new id "
                         f"(`next_id` from `tickets.py status`)")
        joined: dict[str, list[Path]] = {}
        for p in sorted(folder.glob("*-plan.md")):
            fm = frontmatter(p)
            status = str(fm.get("status") or "")
            if status not in PLAN_STATUSES:
                self.add("1f", p, f"plan status {status!r} is not one v7 knows",
                         f"report only -- ask {SOFIA} to set the status through BOARD")
            ticket = str(fm.get("ticket") or "") or p.name[:-len("-plan.md")]
            joined.setdefault(ticket, []).append(p)
            if is_backlog and status == "built":
                self.add("1c", p, f"{p.name[:-len('-plan.md')]} is built but not done",
                         f"ask {SOFIA} to BOARD `mark {ticket} done` once its owner accepts it")
        for ticket, paths in sorted(joined.items()):
            if len(paths) > 1:
                self.add("1h", paths[0], f"{len(paths)} plans join ticket {ticket}: "
                         f"{', '.join(p.name for p in paths)}",
                         "report only -- the plan a build did not write is stale; remove it "
                         "by hand after checking which one `tickets.py status` reads")
        self.sidecars(folder, entries, plans_by_name)

    def leaf(self, p, fm, is_backlog, epics):
        kind = fm.get("type")
        if fm.get("_unparseable"):
            self.add("1k", p, "frontmatter is not valid YAML",
                     f"report only -- ask {SOFIA} to REFINE the ticket")
            return
        if kind not in LEAF_TYPES:
            self.add("1k", p, f"type {kind!r} is not one of {', '.join(LEAF_TYPES)}",
                     f"report only -- ask {SOFIA} to REFINE the ticket's type")
        elif kind == "bug" and str(fm.get("severity") or "") not in SEVERITIES:
            self.add("1k", p, f"bug severity {fm.get('severity')!r} is not one of "
                     f"{', '.join(SEVERITIES)}",
                     f"report only -- ask {SOFIA} to REFINE the bug's severity")
        if not is_backlog:
            return
        parent = str(fm.get("parent") or "").strip()
        if parent in epics:
            self.add("1d", p, f"names {parent} as its parent but sits in backlog/",
                     f"ask {SOFIA} to BOARD `move {p.name} {parent}`, or clear its parent")
        self.marker(p)

    def sidecars(self, folder, entries, plans_by_name):
        side = folder / SIDECAR
        if side.is_file() and entries is not None:
            try:
                data = tomllib.loads(side.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError as e:
                self.add("1b", side, f"not valid TOML ({e})", "report only -- fix by hand")
                data = {}
            for eid in sorted((data.get("entry") or {}), key=str):
                if str(eid) not in entries:
                    self.add("1b", side, f"[entry.{eid}] names no entry of tickets.toml",
                             "report only -- an unreconciled `tickets.py move`: run "
                             "`pm-status.py sidecar-reconcile --moved-json` with the move's "
                             f"output if it was kept, else ask {SOFIA} to REPLAN, which "
                             "re-estimates")
        for s in sorted(folder.glob(f"*{PLAN_SIDECAR_SUFFIX}")):
            plan_name = s.name[:-len(".l3io.toml")] + ".md"
            if (folder / plan_name).is_file():
                continue
            heirs = plans_by_name.get(plan_name, [])
            if len(heirs) == 1:
                init = next((a for a in heirs[0].parents if (a / "tickets" / "tickets.toml")
                             .is_file() and not a.name.startswith("epic-")), None)
                where = self.rel(init) if init else "<initiative>"
                repair = (f"uv run {{pm_status}} sidecar-reconcile --project-root {{project-root}} "
                          f"--initiative-dir {where} -- moves it beside "
                          f"{self.rel(heirs[0])}")
            else:
                repair = (f"report only -- {len(heirs)} plans named {plan_name}; which one "
                          f"it belongs to is not derivable")
            self.add("1l", s, f"plan sidecar whose plan {plan_name} is gone", repair)

    def marker(self, p):
        text = p.read_text(encoding="utf-8", errors="replace")
        m = CODE_MARKER_RE.search(FRONTMATTER_RE.sub("", text, count=1))
        if not m:
            return
        rel, ticket = m.group(1), p.name[:-3]
        title = norm(str(frontmatter(p).get("title") or "").rstrip(" .;,"))
        path = self.root / rel
        if not path.is_file():
            verdict, evidence = "obsolete-candidate", f"{rel} no longer exists"
        else:
            hit = None
            with path.open(encoding="utf-8", errors="replace") as fh:
                for n, line in enumerate(fh, 1):
                    low = norm(line)
                    if "bmad-defer:" in low and title and title in low:
                        hit = n
                        break
            if hit:
                verdict, evidence = "open", f"marker present at {rel}:{hit}"
            else:
                verdict, evidence = "fixed-candidate", f"no bmad-defer: line with the title in {rel}"
        self.markers.append({"ticket": ticket, "path": self.rel(p), "verdict": verdict,
                             "evidence": evidence})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--output-folder", required=True,
                    help="core.output_folder, absolute or relative to --project-root")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    a = ap.parse_args(argv)
    root = Path(a.project_root).resolve()
    output = Path(a.output_folder)
    output = output if output.is_absolute() else root / output
    audit = Audit(root, output)
    audit.run()
    if a.format == "json":
        print(json.dumps({"output_folder": audit.rel(output), "findings": audit.findings,
                          "markers": audit.markers}, indent=2))
    else:
        for f in audit.findings:
            print(f"{f['id']}  {f['path']}: {f['detail']}\n      -> {f['repair']}")
        for m in audit.markers:
            print(f"marker  {m['ticket']}: {m['verdict']} ({m['evidence']})")
        print(f"audit-tree: {len(audit.findings)} finding(s), {len(audit.markers)} marker "
              f"verdict(s) under {audit.rel(output)}")
    return 4 if audit.findings else 0


if __name__ == "__main__":
    sys.exit(main())
