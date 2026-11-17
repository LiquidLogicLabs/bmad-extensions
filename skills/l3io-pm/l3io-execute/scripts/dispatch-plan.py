#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""dispatch-plan.py -- the command plan of one unattended l3io-execute run. Read-only.

    dispatch-plan.py --project-root P (--initiative D | --epic D) --max-parallel N
                     [--status-json F] [--waves-json F] [--base BRANCH]

It reads what v7 already knows -- the store a project uses, `tickets.py status` for the
initiative, and the waves l3io-plan's `plan-graph.py waves` derives from it -- and prints one
JSON object saying which `bmad-build-auto` runs happen in which order, where each epic is
closed, and where the run stops for the user. It never runs a build, writes nothing, and
calls no tracker: the orchestrator executes the plan step by step
(`steps/execute/step-04-dispatch.md`, `step-05-close.md`).

    {"store", "scope", "initiative", "base", "parallel": {"worktrees", "max", "reason"},
     "next", "sync": [...],
     "waves": [{"n", "wave", "epics": [{"slug", "folder", "root", "worktree", "branch",
                                       "tickets": [{"ref", "steps": [...]}],
                                       "close": [...]}],
                "pause_after": [...]}],
     "gates": [...], "skipped": [{"epic", "ref", "reason"}]}

Each step is one of seven kinds, and no other exists (ADR-0017: review is
`bmad-build-auto`'s own, run `thorough`; the run adds no review, fix loop or story prep):

    sync             tracker only: Sofia's Tracker-sync procedure (board.md), then `next --synced`
    checkpoint-plan  the ticket sets `plan_checkpoint`: build with "Halt after planning.", ask
    build            `bmad-build-auto thorough <ref> <folder>`
    checkpoint-done  the ticket sets `done_checkpoint`: ask after `built`
    close-epic       `bmad-retrospective -H <slug>`, then commit its document
    status-done      repo: `tickets.py mark <ref> done`, then commit the plan;
                     tracker: the store's `write` to done, then `mirror` (never `mark`,
                     which a tracker store refuses, tickets.py:1288)
    merge            commit the main checkout's project state, then merge the epic branch

The store is read exactly as `tickets.py`'s `store_name()` reads it (:780-793). A worktree per
epic is planned only when git tracks the `_bmad/` files a build needs: a worktree is a
checkout of the commit, so a project that does not commit `_bmad/` gets a worktree in which
`bmad-build-auto` cannot even render. Such a project runs its epics one at a time, each on
its own branch in the main checkout.

Exit 0, or 2 on usage (including a parent initiative: run each child initiative).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_CONFIG = ("_bmad", "custom", "ticketing-store-config.toml")
TICKETS_PY = ("_bmad", "method", "scripts", "tickets.py")
PLAN_GRAPH = ("_bmad", "l3io-pm", "scripts", "plan-graph.py")
# What a build in a worktree runs from that worktree's own `_bmad/`: v7's renderer (SKILL.md
# of every v7 skill), Sofia's tickets.py (`mark`, `find`) and our hooks' pm_status.
WORKTREE_NEEDS = (("_bmad", "scripts", "render_skill.py"), TICKETS_PY,
                  ("_bmad", "l3io-pm", "scripts", "pm_status", "__main__.py"))
SKIPPED_STATES = ("done", "dropped")


def die(msg: str) -> None:
    sys.stderr.write(f"dispatch-plan.py: {msg}\n")
    sys.exit(2)


def store_name(project_root: str) -> str:
    """`tickets.py`'s `store_config`/`store_name` at the pin (:780-793)."""
    path = os.path.join(project_root, *STORE_CONFIG)
    if not os.path.isfile(path):
        return "repo"
    with open(path, "rb") as fh:
        tickets = tomllib.load(fh).get("tickets", {})
    store = tickets.get("store", "repo") if isinstance(tickets, dict) else "repo"
    return store if isinstance(store, str) and store else "repo"


def git(root: str, *argv) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", root, *argv], capture_output=True, text=True,
                          check=False)


def in_git(root: str) -> bool:
    return git(root, "rev-parse", "--show-toplevel").returncode == 0


def worktrees_runnable(root: str) -> tuple:
    """(True, why) when every file a build needs is committed, so a worktree carries it."""
    if not in_git(root):
        return False, "the project is not a git repository, so there are no worktrees"
    missing = [os.path.join(*p) for p in WORKTREE_NEEDS
               if git(root, "ls-files", "--error-unmatch", "--", os.path.join(*p)).returncode]
    if missing:
        verb = "is" if len(missing) == 1 else "are"
        return False, (f"{', '.join(missing)} {verb} not committed, so a git worktree has no "
                       "runnable _bmad/; epics run one at a time in the main checkout")
    return True, "_bmad/ is committed, so each epic runs in its own git worktree"


def run_json(argv: list, stdin: str | None = None) -> dict:
    r = subprocess.run(argv, input=stdin, capture_output=True, text=True, check=False)
    if r.returncode:
        die(f"{' '.join(argv)} exited {r.returncode}: {r.stderr.strip() or r.stdout.strip()}")
    return json.loads(r.stdout)


def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def uv(script: str) -> list:
    return ["uv", "run", "--quiet", script]


def ticket_order(rows: list) -> list:
    """An epic's tickets in build order: entry order, each after its sibling prerequisites."""
    by_id = {str(t["id"]): t for t in rows}
    out, seen = [], set()

    def visit(t, path=()):
        key = str(t["id"])
        if key in seen or key in path:
            return
        for a in t.get("after", []):
            dep = by_id.get(str(a))
            if dep is not None:
                visit(dep, path + (key,))
        seen.add(key)
        out.append(t)

    for t in rows:
        visit(t)
    return out


def batches(epics: list, size: int) -> list:
    return [epics[i:i + size] for i in range(0, len(epics), size)] or [[]]


def main() -> int:
    ap = argparse.ArgumentParser(description="the command plan of one l3io-execute run")
    ap.add_argument("--project-root", required=True)
    scope = ap.add_mutually_exclusive_group(required=True)
    scope.add_argument("--initiative", help="an initiative folder")
    scope.add_argument("--epic", help="one epic folder, <initiative>/tickets/epic-<slug>")
    ap.add_argument("--max-parallel", type=int, required=True)
    ap.add_argument("--status-json", help="tickets.py status output (default: run it)")
    ap.add_argument("--waves-json", help="plan-graph.py waves output (default: run it)")
    ap.add_argument("--base", help="the branch epics merge into (default: the current one)")
    args = ap.parse_args()
    if args.max_parallel < 1:
        die("--max-parallel must be at least 1")

    root = os.path.realpath(args.project_root)
    only = None
    if args.epic:
        epic_dir = os.path.realpath(args.epic)
        only = os.path.basename(epic_dir)
        initiative = os.path.dirname(os.path.dirname(epic_dir))
    else:
        initiative = os.path.realpath(args.initiative)
    store = store_name(root)
    tickets_py = os.path.join(root, *TICKETS_PY)
    synced = ["--synced"] if store != "repo" else []

    status = (read_json(args.status_json) if args.status_json else
              run_json([*uv(tickets_py), "--project-root", root, "status", initiative]))
    if "initiatives" in status:
        die(f"{initiative} is a parent initiative; run each child initiative in turn, in the "
            "order `plan-graph.py waves` gives them")
    if args.waves_json:
        waves = read_json(args.waves_json)
    else:
        waves = run_json([*uv(os.path.join(root, *PLAN_GRAPH)), "waves", "--status-json", "-"],
                         stdin=json.dumps(status))

    parallel_ok, why = worktrees_runnable(root)
    git_ok = in_git(root)
    width = args.max_parallel if parallel_ok else 1
    base = args.base or (git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
                         if git_ok else None)
    close_commit = os.path.join(HERE, "close-commit.py")
    rel_init = os.path.relpath(initiative, root)

    def next_cmd(at: str) -> str:
        return " ".join([*uv(os.path.join(at, *TICKETS_PY)), "--project-root", at, "next",
                         *synced, os.path.join(at, rel_init)])

    def sync_step(at: str, ref: str | None = None) -> dict:
        step = {"kind": "sync", "procedure": "bmad-agent-po references/board.md, Tracker sync",
                "next": next_cmd(at)}
        if ref is not None:
            step.update(ref=ref, start="in-progress")
        return step

    rows_by_epic = {}
    for t in status.get("tickets", []):
        rows_by_epic.setdefault(t["epic"], []).append(t)

    skipped, out_waves, gates = [], [], list(waves.get("gates", []))
    order = [(w["n"], w["epics"]) for w in waves.get("waves", [])]
    if only is not None:
        order = [(1, [only])]
        gates = []
    n = 0
    for wave_n, slugs in order:
        planned = []
        for slug in slugs:
            rows = [t for t in rows_by_epic.get(slug, []) if t["state"] not in SKIPPED_STATES]
            if not rows:
                skipped.append({"epic": slug, "ref": None,
                                "reason": "no ticket left to build or mark done"})
                continue
            worktree = (os.path.join(os.path.dirname(root),
                                     f"{os.path.basename(root)}-l3io-{slug}")
                        if parallel_ok else None)
            at = worktree or root
            folder = os.path.join(at, rel_init)
            epic_folder = os.path.join(folder, "tickets", slug)
            tickets, done_refs = [], []
            for t in ticket_order(rows):
                ref = str(t["ref"])
                if t.get("status") == "blocked" or t.get("blocked_at"):
                    skipped.append({"epic": slug, "ref": ref,
                                    "reason": f"blocked: {t.get('blocked_reason') or 'no reason'}"})
                    continue
                if t.get("refine") and not t.get("refined"):
                    skipped.append({"epic": slug, "ref": ref,
                                    "reason": "needs refining in Sofia's REFINE first"})
                    continue
                done_refs.append(ref)
                if t["state"] == "review":
                    continue                     # built already: closed, never rebuilt
                build = f"bmad-build-auto thorough {ref} {folder}"
                steps = [sync_step(at, ref)] if store != "repo" else []
                if t.get("plan_checkpoint"):
                    steps.append({"kind": "checkpoint-plan", "ref": ref,
                                  "invocation": f"{build} Halt after planning.",
                                  "ask": f"The plan for {ref} is written. Build it as planned?"})
                steps.append({"kind": "build", "ref": ref, "invocation": build})
                if t.get("done_checkpoint"):
                    steps.append({"kind": "checkpoint-done", "ref": ref,
                                  "ask": f"{ref} is built. Accept it before the run goes on?"})
                tickets.append({"ref": ref, "steps": steps})
            retro = os.path.join(epic_folder, f"{slug}-retrospective.md")
            close = [{"kind": "close-epic", "invocation": f"bmad-retrospective -H {slug}",
                      "retro_file": retro,
                      "commit": " ".join([*uv(close_commit), "retro", "--project-root", at,
                                          "--retro-file", retro])}]
            plans_commit = " ".join([*uv(close_commit), "plans", "--project-root", at,
                                     "--epic-dir", epic_folder])
            for ref in done_refs:
                if store == "repo":
                    close.append({"kind": "status-done", "ref": ref,
                                  "command": " ".join([*uv(os.path.join(at, *TICKETS_PY)),
                                                       "--project-root", at, "mark", folder,
                                                       ref, "done"]),
                                  "commit": plans_commit})
                else:
                    close.append({"kind": "status-done", "ref": ref, "store_write": "done",
                                  "then": "mirror", "next": next_cmd(at)})
            if git_ok:
                close.append({"kind": "merge", "branch": f"l3io/{slug}", "into": base,
                              "worktree": worktree,
                              "state_commit": " ".join([*uv(close_commit), "state",
                                                        "--project-root", root])})
            planned.append({"slug": slug, "folder": epic_folder, "root": at,
                            "worktree": worktree,
                            "branch": f"l3io/{slug}" if git_ok else None,
                            "tickets": tickets, "close": close})
        for group in batches(planned, width):
            if not group:
                continue
            n += 1
            out_waves.append({"n": n, "wave": wave_n, "epics": group, "pause_after": []})
        if out_waves and out_waves[-1]["wave"] == wave_n:
            out_waves[-1]["pause_after"] = [s for s in slugs if s in gates
                                            and any(e["slug"] == s for e in planned)]

    plan = {"store": store, "scope": "epic" if only else "initiative",
            "initiative": initiative, "base": base,
            "parallel": {"worktrees": parallel_ok, "max": width, "reason": why},
            "next": next_cmd(root),
            "sync": [sync_step(root)] if store != "repo" else [],
            "waves": out_waves, "gates": gates, "skipped": skipped}
    sys.stdout.write(json.dumps(plan, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
