#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18", "tomlkit>=0.13"]
# ///
"""
Review Focus 5 of plan 2026-11-17-v7-phase-4-hooks.md (Task 4.7): parallel epics lose no
write. Run with: uv run tests/l3io-execute/test-parallel-sidecars.py

Each epic runs in its own `git worktree`, and every worktree shares one project state root
(the main checkout's `{output_folder}/l3io/`, through `git rev-parse --git-common-dir`). Per
ticket, two processes race: one rewrites the plan's frontmatter `status` the way v7's
`tickets.py` does (`edit_frontmatter`, :1257-1280: read the bytes, then `write_bytes` -- no
lock, no rename, so a reader can see the file truncated), and one runs `build-close` on the
same plan. A barrier starts them together. Afterwards every ticket has its sidecar, the
event log holds one `dispatch_open`/`dispatch_close` pair per ticket, the calibration file
one sample per ticket, every plan parses, and the `.inflight/` spool is empty.
"""
import json
import multiprocessing
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from ruamel.yaml import YAML

_REPO = Path(__file__).resolve().parents[2]
PM_STATUS = _REPO / "skills" / "_shared" / "pm_status"
ROUNDS = 20

FAKE_RESOLVE_CONFIG = """\
import json
print(json.dumps({"core.output_folder": "{project-root}/_bmad-output"}))
"""

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
       "CLAUDE_CODE_SESSION_ID": ""}
ENV.pop("GIT_DIR", None)

ESTIMATE = ("[entry.{n}]\nclass = \"standard\"\n\n[entry.{n}.estimate]\nelapsed_hours = 1.0\n"
            "man_hours = 3.0\nhitl_hours = 0.25\n"
            "tokens_k = {{total = 100, input = 15, output = 5, cache_write = 30, "
            "cache_read = 50}}\ncost = 0.4\nmodel = \"claude-opus-5\"\nfix_factor = 1.25\n\n")

PLAN = "---\ntitle: 'Story {n}'\ntype: 'feature'\nticket: '{n}'\nstatus: '{status}'\n" \
       "review_loop_iteration: 0\n---\n\n# Story {n}\n\n" + "Body line.\n" * 200


def git(cwd, *argv):
    r = subprocess.run(["git", "-C", str(cwd), *argv], capture_output=True, text=True, env=ENV)
    if r.returncode:
        raise AssertionError(f"git {argv} in {cwd}: {r.stderr}")
    return r.stdout


def set_frontmatter_value(text, key, value):
    """tickets.py's own line edit (set_frontmatter_value): replace `key:`'s line in place."""
    head, sep, body = text[4:].partition("\n---\n")
    lines = [f"{key}: {value}" if ln.startswith(f"{key}:") else ln for ln in head.split("\n")]
    return "---\n" + "\n".join(lines) + sep + body


def edit_frontmatter(path, values):
    """tickets.py:1257-1280 as it writes: read, edit, `write_bytes` -- truncate, then write."""
    p = Path(path)
    text = p.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    for k, v in values.items():
        text = set_frontmatter_value(text, k, v)
    p.write_bytes(text.encode("utf-8"))


def _rewriter(plan, barrier):
    barrier.wait()
    for _ in range(40):
        edit_frontmatter(plan, {"status": "'built'"})


def _closer(main, wt, plan, session, barrier, out):
    barrier.wait()
    r = subprocess.run([sys.executable, str(main), "build-close", "--project-root", str(wt),
                        "--agent", "bmad-build-auto", "--plan-file", str(plan),
                        "--session-id", session, "--runtime", "other", "--man-hours", "2",
                        "--hitl-hours", "0"], capture_output=True, text=True, env=ENV)
    out.put((str(plan), r.returncode, r.stderr))


class TestParallelEpics(unittest.TestCase):

    def build(self, n_epics):
        tmp = Path(tempfile.mkdtemp(prefix="test-parallel-sidecars-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, True)
        root = tmp / "proj"
        scripts = root / "_bmad" / "l3io-pm" / "scripts"
        scripts.mkdir(parents=True)
        shutil.copytree(PM_STATUS, scripts / "pm_status",
                        ignore=shutil.ignore_patterns("__pycache__"))
        (root / "_bmad" / "scripts").mkdir(parents=True)
        (root / "_bmad" / "scripts" / "resolve_config.py").write_text(FAKE_RESOLVE_CONFIG)
        init = root / "_bmad-output" / "shop" / "tickets"
        init.mkdir(parents=True)
        slugs = [f"epic-e{i}" for i in range(1, n_epics + 1)]
        (init / "tickets.toml").write_text("".join(
            f'[[epic]]\nid = {i}\nslug = "{s}"\n\n' for i, s in enumerate(slugs, 1)))
        for s in slugs:
            tdir = init / s / "tickets"
            tdir.mkdir(parents=True)
            (init / s / f"{s}.md").write_text("---\ntype: epic\n---\n")
            (tdir / "tickets.toml").write_text("".join(
                f'[[entry]]\nid = {n}\ntype = "story"\ntitle = "Story {n}"\n\n'
                for n in range(1, ROUNDS + 1)))
            (tdir / "l3io.toml").write_text("".join(ESTIMATE.format(n=n)
                                                    for n in range(1, ROUNDS + 1)))
            for n in range(1, ROUNDS + 1):
                (tdir / f"story-{n}-plan.md").write_text(PLAN.format(n=n, status="built"))
        git(root, "init", "-q", "-b", "main")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "fixture")
        worktrees = {}
        for s in slugs:
            wt = tmp / f"wt-{s}"
            git(root, "worktree", "add", "-q", "-b", f"l3io/{s}", str(wt))
            worktrees[s] = wt
        return root, worktrees

    def run_epics(self, n_epics):
        root, worktrees = self.build(n_epics)
        main = root / "_bmad" / "l3io-pm" / "scripts" / "pm_status" / "__main__.py"
        ctx = multiprocessing.get_context("spawn")
        plans = []
        for rnd in range(1, ROUNDS + 1):
            barrier = ctx.Barrier(2 * n_epics)
            out = ctx.Queue()
            procs = []
            for s, wt in worktrees.items():
                plan = wt / "_bmad-output" / "shop" / "tickets" / s / "tickets" / \
                    f"story-{rnd}-plan.md"
                session = f"{s}-r{rnd}"
                r = subprocess.run([sys.executable, str(main), "build-open", "--project-root",
                                    str(wt), "--agent", "bmad-build-auto", "--session-id",
                                    session], capture_output=True, text=True, env=ENV)
                self.assertEqual(r.returncode, 0, r.stderr)
                plans.append(plan)
                procs.append(ctx.Process(target=_rewriter, args=(str(plan), barrier)))
                procs.append(ctx.Process(target=_closer, args=(main, wt, plan, session,
                                                              barrier, out)))
            for p in procs:
                p.start()
            for p in procs:
                p.join(120)
                self.assertEqual(p.exitcode, 0)
            for _ in range(n_epics):
                plan, code, err = out.get(timeout=5)
                self.assertEqual(code, 0, f"build-close {plan}: {err}")
        return root, worktrees, plans

    def check(self, n_epics):
        root, worktrees, plans = self.run_epics(n_epics)
        n = n_epics * ROUNDS
        for plan in plans:
            text = plan.read_text(encoding="utf-8")
            m = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
            self.assertIsNotNone(m, f"{plan} no longer parses")
            fm = YAML(typ="safe").load(m.group(1))
            self.assertEqual(str(fm["status"]), "built")
            side = plan.with_name(plan.name[:-len(".md")] + ".l3io.toml")
            self.assertTrue(side.is_file(), f"no sidecar for {plan}")
            data = tomllib.loads(side.read_text(encoding="utf-8"))
            self.assertEqual(len(data["dispatch"]), 1, side)
            self.assertIn("calibration_sampled_at", data, f"{side}: no calibration sample")

        state = root / "_bmad-output" / "l3io"
        events = [json.loads(ln) for ln in (state / "events.jsonl").read_text().splitlines()]
        brackets = {}
        for e in events:
            if e["event"] in ("dispatch_open", "dispatch_close"):
                brackets.setdefault(e["bracket"], []).append((e["event"], e.get("outcome")))
        self.assertEqual(len(brackets), n)
        for key, pair in brackets.items():
            self.assertEqual(pair, [("dispatch_open", None), ("dispatch_close", "closed")], key)

        cal = YAML(typ="safe").load((state / "pm-calibration.yaml").read_text())
        samples = cal["scope"]["standard"]["man_hours"]["samples"]
        self.assertEqual(len(samples), n)

        residue = [p.name for p in (state / ".inflight").iterdir() if p.name != ".gitignore"]
        self.assertEqual(residue, [])
        for wt in worktrees.values():
            self.assertEqual(git(wt, "status", "--porcelain", "--untracked-files=all"), "")

    def test_parallel_epics_sidecars_survive(self):
        for n_epics in (2, 4):
            with self.subTest(epics=n_epics):
                self.check(n_epics)


if __name__ == "__main__":
    unittest.main(verbosity=2)
