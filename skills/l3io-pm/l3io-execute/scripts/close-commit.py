#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18", "tomlkit>=0.13"]
# ///
"""close-commit.py -- commit what an unattended run's closing steps leave behind.

`bmad-build-auto` refuses to start on a dirty tree and finishes on a clean one
(step-01-clarify-and-route.md:60, step-04-review.md:171-174). Three writes of the run's
closing steps are nobody else's to commit, and each is committed here, path by path, so a
user's own work in the tree is never swept into one of these commits:

    close-commit.py retro --project-root R --retro-file F
        The retrospective's document. `bmad-retrospective` commits nothing
        (retro-document.md:39) and `epic-close` leaves the document as v7 left it, so the
        run commits it before any further build. Prints {"epic", "verdict", "committed"}:
        the verdict is the document's frontmatter, the only machine-readable one
        (retro-document.md:9-21). Exit 2 on a missing or unknown verdict.

    close-commit.py plans --project-root R --epic-dir D
        Every `*-plan.md` under the epic that `tickets.py mark <ref> done` changed. `mark`
        writes only the plan and leaves committing to its caller (board.md, Status).

    close-commit.py state --project-root R
        The project-wide state root (`{output_folder}/l3io/`) of the MAIN checkout. A build
        in a linked worktree commits its ticket's sidecar there, but the events log and the
        calibration file live in the main checkout, outside it. Exit 2 when R is a linked
        worktree: those files are not inside it.

Everything is committed through pm_status's own commit helper, and the state root is
resolved by pm_status's resolver, never assembled here. Exit 1 when a commit fails (a user's
commit hook, say): the tree is then dirty, and the message says so.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALLED = ("_bmad", "l3io-pm", "scripts")
VERDICTS = ("accepted", "accepted-with-open-items", "rejected")


def die(msg: str, code: int = 2) -> None:
    sys.stderr.write(f"close-commit.py: {msg}\n")
    sys.exit(code)


def pm_status(project_root: str):
    """The installed pm_status (`bmad setup l3io-pm`), else the payload copy beside this
    script: the same release line either way."""
    installed = os.path.join(project_root, *INSTALLED)
    where = installed if os.path.isfile(os.path.join(installed, "pm_status", "__init__.py")) \
        else HERE
    sys.path.insert(0, where)
    from pm_status import nodes
    from pm_status.sidecar import commit, verbs
    return nodes, commit, verbs


def finish(err: str, what: str) -> int:
    if err:
        die(f"{what}, but the commit failed, so the tree is dirty: {err}", 1)
    return 0


def cmd_retro(args) -> int:
    _nodes, commit, verbs = pm_status(args.project_root)
    retro = os.path.realpath(args.retro_file)
    if not os.path.isfile(retro):
        die(f"{retro} does not exist: bmad-retrospective saves it at "
            "<epic folder>/epic-<slug>-retrospective.md")
    verdict = verbs.plan_field(retro, "verdict")
    if verdict not in VERDICTS:
        die(f"{retro}: verdict {verdict!r} is not one of {', '.join(VERDICTS)}")
    epic = verbs.plan_field(retro, "epic") or os.path.basename(os.path.dirname(retro))
    before = _head(args.project_root)
    err = commit.commit_paths(args.project_root, [retro], f"docs(l3io): {epic} retrospective")
    sys.stdout.write(json.dumps({"epic": epic, "verdict": verdict,
                                 "committed": _head(args.project_root) != before}) + "\n")
    return finish(err, "the verdict was read")


def cmd_plans(args) -> int:
    _nodes, commit, _verbs = pm_status(args.project_root)
    epic_dir = os.path.realpath(args.epic_dir)
    plans = []
    for dirpath, _dirs, files in os.walk(epic_dir):
        plans += [os.path.join(dirpath, f) for f in files if f.endswith("-plan.md")]
    err = commit.commit_paths(args.project_root, sorted(plans),
                              f"chore(l3io): {os.path.basename(epic_dir)} done")
    return finish(err, "the plans were marked")


def cmd_state(args) -> int:
    nodes, commit, _verbs = pm_status(args.project_root)
    root = os.path.realpath(args.project_root)
    top = commit.toplevel(root)
    if top is None:
        return 0
    common = subprocess.run(["git", "-C", root, "rev-parse", "--path-format=absolute",
                             "--git-common-dir"], capture_output=True, text=True, check=False)
    main = os.path.dirname(os.path.realpath(common.stdout.strip()))
    if main != top:
        die(f"{root} is a linked worktree; the project state lives in the main checkout, "
            f"{main}: run this there")
    state_root = nodes.project_state_root(root)
    paths = []
    for dirpath, _dirs, files in os.walk(state_root):
        paths += [os.path.join(dirpath, f) for f in files]
    err = commit.commit_paths(root, sorted(paths), "chore(l3io): run state")
    return finish(err, "the run's state was recorded")


def _head(root: str) -> str:
    r = subprocess.run(["git", "-C", root, "rev-parse", "-q", "--verify", "HEAD"],
                       capture_output=True, text=True, check=False)
    return r.stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="commit what the run's closing steps leave")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("retro", help="the retrospective's document; prints its verdict")
    p.add_argument("--project-root", required=True)
    p.add_argument("--retro-file", required=True)
    p.set_defaults(func=cmd_retro)
    p = sub.add_parser("plans", help="the epic's plans `tickets.py mark` changed")
    p.add_argument("--project-root", required=True)
    p.add_argument("--epic-dir", required=True)
    p.set_defaults(func=cmd_plans)
    p = sub.add_parser("state", help="the main checkout's project state root")
    p.add_argument("--project-root", required=True)
    p.set_defaults(func=cmd_state)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
