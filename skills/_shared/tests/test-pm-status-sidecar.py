#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18", "tomlkit>=0.13"]
# ///
"""
Tests for pm_status's 4.x sidecars -- run with: uv run test-pm-status-sidecar.py

BMad v7 owns the work-item tree (`tickets.toml`, leaf files, plans). l3io writes only
sidecars beside it -- `l3io.toml` in a container's `tickets/` folder, `<plan-stem>.l3io.toml`
beside a plan -- and keeps project-wide data under `{output_folder}/l3io/`. These tests pin
that boundary: v7's bytes never move, nothing we create is a name `tickets.py` would read,
the state root is the main checkout's from any worktree, and concurrent writers lose nothing.

The fixture initiative follows the layout `tickets.py` reads at the pinned upstream
(`bmad-agent-po/scripts/tickets.py`, `tickets_dir` :180-192). Every CLI call runs the
script as a subprocess, so each one resolves its state root from scratch, as an installed
hook would.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "pm_status", "__main__.py")

sys.path.insert(0, os.path.dirname(HERE))
import pm_status as pm

# tickets.py's folder scan, at the pin: a leaf or plan is any `*.md` in a tickets folder
# (`load_folder`, :322), and an epic is any `epic-*` directory (`epic_folders`, :406). A
# name of ours matching either would be read as v7 data.
TICKETS_PY_MD = re.compile(r"\.md$")
TICKETS_PY_EPIC = re.compile(r"^epic-[^/]+$")

# The fake resolve_config.py prints what BMad core's prints for one --key: a JSON object
# keyed by the dotted key (core-tools/bmad/scripts/resolve_config.py, `extract_key`).
FAKE_RESOLVE_CONFIG = """\
import json, sys
print(json.dumps({"core.output_folder": "{project-root}/_bmad-output"}, indent=2))
"""

MODEL = "claude-opus-5-5"

# tickets.py move's stdout for entry 2 of epic-cart moved to epic-pricing, as recorded by
# upstream's own test (test_tickets.py, test_move_takes_the_entry_its_file_and_plan_along...).
RECORDED_MOVE = {
    "from": "epic-cart", "to": "epic-pricing", "old_id": 2, "id": 3, "ref": "1.3",
    "file": "story-ui-shell.md", "plan": "story-ui-shell-plan.md",
    "next_id": {"epic-cart": 5},
    "rewritten": [{"where": "epic-cart/tickets/tickets.toml entry 4", "after": ["1.3", 3]}],
}

_RUN_TMP = None
_PREV_TMPDIR = None
_PREV_TEMPFILE_TEMPDIR = None


def setUpModule():
    """Every temp dir of this run, and of every child that honours TMPDIR, goes under one
    private directory; tearDownModule fails the run if anything is left in it."""
    global _RUN_TMP, _PREV_TMPDIR, _PREV_TEMPFILE_TEMPDIR
    _PREV_TEMPFILE_TEMPDIR = tempfile.tempdir
    _RUN_TMP = tempfile.mkdtemp(prefix="test-pm-status-sidecar-")
    tempfile.tempdir = _RUN_TMP
    _PREV_TMPDIR = os.environ.get("TMPDIR")
    os.environ["TMPDIR"] = _RUN_TMP


def tearDownModule():
    tempfile.tempdir = _PREV_TEMPFILE_TEMPDIR
    if _PREV_TMPDIR is None:
        os.environ.pop("TMPDIR", None)
    else:
        os.environ["TMPDIR"] = _PREV_TMPDIR
    leaked = sorted(n for n in os.listdir(_RUN_TMP)
                    if not (n.startswith("uv-") and n.endswith(".lock")))
    shutil.rmtree(_RUN_TMP, ignore_errors=True)
    if leaked:
        raise AssertionError(f"temp-dir leak: {', '.join(leaked[:5])}")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def leaf(entry_id, title):
    return (f"---\nid: {entry_id}\ntracker_id: \"\"\ntype: story\ntitle: \"{title}\"\n"
            f"parent: epic-cart\ncovers: [R1]\nafter: []\n---\n\n# {title}\n")


def plan(entry_id):
    return (f"---\ntitle: 'x'\ntype: 'feature'\nticket: '{entry_id}'\n"
            f"status: 'in-progress'\n---\n\n# x\n")


class Project(unittest.TestCase):
    """A v7 project: `_bmad/scripts/resolve_config.py` and one initiative with one epic of
    three entries, each with a leaf file and a plan."""

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        write(os.path.join(self.root, "_bmad", "scripts", "resolve_config.py"),
              FAKE_RESOLVE_CONFIG)
        self.out = os.path.join(self.root, "_bmad-output")
        self.initiative = os.path.join(self.out, "initiative-checkout")
        write(os.path.join(self.initiative, "initiative-checkout.md"),
              "---\ntype: initiative\n---\n# Checkout\n")
        write(os.path.join(self.initiative, "tickets", "tickets.toml"),
              '[[epic]]\nid = 1\nslug = "epic-cart"\n')
        self.epic = os.path.join(self.initiative, "tickets", "epic-cart")
        write(os.path.join(self.epic, "epic-cart.md"),
              "---\ntype: epic\nafter: []\n---\n# epic-cart\n")
        self.tdir = os.path.join(self.epic, "tickets")
        write(os.path.join(self.tdir, "tickets.toml"),
              "# the agreed children of epic-cart\n"
              '[[entry]]\nid = 1\ntype = "story"\ntitle = "Scaffold"\n\n'
              '[[entry]]\nid = 2\ntype = "story"\ntitle = "UI shell"\nafter = [1]\n\n'
              '[[entry]]\nid = 3\ntype = "story"\ntitle = "Tracer"\nafter = [1, 2]\n')
        self.plans = {}
        for n, slug in ((1, "scaffold"), (2, "ui-shell"), (3, "tracer")):
            write(os.path.join(self.tdir, f"story-{slug}.md"), leaf(n, slug))
            p = os.path.join(self.tdir, f"story-{slug}-plan.md")
            write(p, plan(n))
            self.plans[n] = p
        self.state_root = os.path.join(self.out, "l3io")

    def run_cli(self, *argv, check=True):
        r = subprocess.run([sys.executable, SCRIPT, *argv], capture_output=True, text=True)
        if check:
            self.assertEqual(r.returncode, 0, f"{argv}\nstdout: {r.stdout}\nstderr: {r.stderr}")
        return r

    def snapshot(self):
        """Bytes of every v7-owned file in the initiative: tickets.toml, leaves, plans."""
        out = {}
        for dirpath, _dirs, files in os.walk(self.initiative):
            for f in files:
                if f == "tickets.toml" or f.endswith(".md"):
                    p = os.path.join(dirpath, f)
                    with open(p, "rb") as fh:
                        out[p] = fh.read()
        return out

    def tree(self):
        """Every path under the project, relative, files and directories."""
        out = set()
        for dirpath, dirs, files in os.walk(self.root):
            for n in dirs + files:
                out.add(os.path.relpath(os.path.join(dirpath, n), self.root))
        return out

    def every_verb(self):
        """Every verb that takes v7 addressing, once each, through the CLI."""
        r = self.root
        self.run_cli("set-estimate", "--project-root", r, "--ticket-dir", self.tdir,
                     "--entry", "2", "--elapsed-hours", "1", "--man-hours", "3",
                     "--hitl-hours", "0.5", "--tokens-k", "120")
        self.run_cli("set-actual", "--project-root", r, "--plan-file", self.plans[2],
                     "--node", "story", "--runtime", "claude", "--model", MODEL,
                     "--elapsed-hours", "1.5", "--man-hours", "4", "--hitl-hours", "0.25",
                     "--tokens-input", "10", "--tokens-output", "2",
                     "--tokens-cache-write", "1", "--tokens-cache-read", "50")
        self.run_cli("add-test-run", "--project-root", r, "--plan-file", self.plans[2],
                     "--command", "npm test", "--exit-code", "0")
        self.run_cli("verify", "--project-root", r, "--plan-file", self.plans[2],
                     "--scope", "story", "--runtime", "claude")
        self.run_cli("sidecar-reconcile", "--project-root", r,
                     "--initiative-dir", self.initiative)

    def load_toml(self, path):
        with open(path, "rb") as fh:
            return tomllib.load(fh)


class TestBoundary(Project):

    def test_tickets_toml_never_written(self):
        before = self.snapshot()
        self.every_verb()
        after = self.snapshot()
        self.assertEqual(sorted(after), sorted(before), "a v7 file appeared or vanished")
        for p, data in before.items():
            self.assertEqual(after[p], data, f"{os.path.relpath(p, self.root)} changed")

    def test_sidecar_names_are_invisible_to_tickets_py(self):
        before = self.tree()
        self.every_verb()
        created = self.tree() - before
        inside = [p for p in created
                  if os.path.join(self.root, p).startswith(self.initiative + os.sep)]
        self.assertTrue(inside, "the verbs created no sidecar at all -- the test proves nothing")
        for rel in created:
            name = os.path.basename(rel)
            self.assertIsNone(TICKETS_PY_MD.search(name), f"{rel} would be read as a leaf or plan")
            if os.path.isdir(os.path.join(self.root, rel)):
                self.assertIsNone(TICKETS_PY_EPIC.match(name), f"{rel} would be read as an epic")
        self.assertIn(os.path.relpath(os.path.join(self.tdir, "l3io.toml"), self.root), created)
        self.assertIn(os.path.relpath(os.path.join(self.tdir, "story-ui-shell-plan.l3io.toml"),
                                      self.root), created)

    def test_sidecar_layout(self):
        self.every_verb()
        entry = self.load_toml(os.path.join(self.tdir, "l3io.toml"))["entry"]["2"]["estimate"]
        self.assertEqual(list(entry)[:4], ["elapsed_hours", "man_hours", "hitl_hours", "tokens_k"])
        ticket = self.load_toml(os.path.join(self.tdir, "story-ui-shell-plan.l3io.toml"))
        self.assertEqual(list(ticket["actual"])[:5], list(pm.METRIC_FIELDS))
        self.assertEqual(ticket["actual"]["tokens_k"]["total"], 63)
        self.assertGreater(ticket["actual"]["cost"], 0)
        self.assertEqual(ticket["completion_evidence"]["test_runs"],
                         [{"command": "npm test", "exit_code": 0}])
        self.assertIs(ticket["completion_evidence"]["tests_passing"], True)
        with open(os.path.join(self.state_root, "events.jsonl"), encoding="utf-8") as fh:
            events = [json.loads(line) for line in fh]
        self.assertEqual([e["event"] for e in events], ["actual"])
        self.assertEqual(events[0]["plan"],
                         "_bmad-output/initiative-checkout/tickets/epic-cart/tickets/"
                         "story-ui-shell-plan.md")

    def test_v7_addressing_excludes_node_keys(self):
        r = self.run_cli("set-actual", "--project-root", self.root, "--plan-file",
                         self.plans[1], "--node", "story", "--story", "E001-S01-001",
                         "--man-hours", "1", check=False)
        self.assertEqual(r.returncode, 2, r.stderr)
        r = self.run_cli("set-actual", "--state-root", self.state_root, "--plan-file",
                         self.plans[1], "--node", "story", "--man-hours", "1", check=False)
        self.assertEqual(r.returncode, 2, r.stderr)
        r = self.run_cli("set-actual", "--node", "story", "--story", "E001-S01-001",
                         "--man-hours", "1", check=False)
        self.assertEqual(r.returncode, 2, "no --state-root and no --project-root")

    def test_a_missing_plan_is_not_found(self):
        r = self.run_cli("set-actual", "--project-root", self.root, "--plan-file",
                         os.path.join(self.tdir, "story-nope-plan.md"), "--node", "story",
                         "--man-hours", "1", check=False)
        self.assertEqual(r.returncode, 3, r.stderr)

    def test_set_actual_cost_is_still_refused(self):
        r = self.run_cli("set-actual", "--project-root", self.root, "--plan-file",
                         self.plans[1], "--node", "story", "--cost", "3", check=False)
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_verify_fails_an_incomplete_ticket(self):
        self.run_cli("set-actual", "--project-root", self.root, "--plan-file", self.plans[1],
                     "--node", "story", "--man-hours", "1")
        r = self.run_cli("verify", "--project-root", self.root, "--plan-file", self.plans[1],
                         "--scope", "story", check=False)
        self.assertEqual(r.returncode, 4, r.stdout)
        self.assertIn("actual.elapsed_hours absent", r.stdout)


class TestStateRoot(Project):

    def git(self, *argv, cwd=None):
        subprocess.run(["git", "-C", cwd or self.root, *argv], check=True, capture_output=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})

    def test_state_root_resolves_to_main_worktree(self):
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "fixture")
        wt = os.path.join(os.path.dirname(self.root), os.path.basename(self.root) + "-wt")
        self.addCleanup(shutil.rmtree, wt, True)
        self.git("worktree", "add", "-q", "-b", "l3io/epic-cart", wt)
        main_root = pm.nodes.project_state_root(self.root)
        self.assertEqual(main_root, self.state_root)
        self.assertEqual(pm.nodes.project_state_root(wt), main_root)
        # End to end: an actual written in the worktree lands its event in the main checkout.
        wt_plan = os.path.join(wt, os.path.relpath(self.plans[1], self.root))
        self.run_cli("set-actual", "--project-root", wt, "--plan-file", wt_plan,
                     "--node", "story", "--man-hours", "1")
        self.assertTrue(os.path.isfile(os.path.join(self.state_root, "events.jsonl")))
        self.assertFalse(os.path.exists(os.path.join(wt, "_bmad-output", "l3io")))
        self.assertTrue(os.path.isfile(wt_plan[:-3] + ".l3io.toml"),
                        "the ticket sidecar belongs beside the worktree's own plan")

    def test_no_resolve_config_is_a_usage_error(self):
        os.unlink(os.path.join(self.root, "_bmad", "scripts", "resolve_config.py"))
        r = self.run_cli("set-actual", "--project-root", self.root, "--plan-file",
                         self.plans[1], "--node", "story", "--man-hours", "1", check=False)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("resolve_config.py", r.stderr)


class TestRoundTrip(Project):

    def test_sidecar_round_trip_keeps_comments(self):
        side = os.path.join(self.tdir, "l3io.toml")
        write(side, "# l3io sidecar for epic-cart -- hand notes survive\n"
                    "[entry.1] # the scaffold\n"
                    'class = "standard" # chosen at slice time\n\n'
                    "[epic]\n"
                    "# estimate goes here at roll-up\n")
        self.run_cli("set-estimate", "--project-root", self.root, "--ticket-dir", self.tdir,
                     "--entry", "1", "--man-hours", "2")
        self.run_cli("set-estimate", "--project-root", self.root, "--ticket-dir", self.tdir,
                     "--entry", "3", "--man-hours", "5")
        with open(side, encoding="utf-8") as fh:
            text = fh.read()
        for kept in ("# l3io sidecar for epic-cart -- hand notes survive",
                     "[entry.1] # the scaffold", 'class = "standard" # chosen at slice time',
                     "# estimate goes here at roll-up"):
            self.assertIn(kept, text)
        data = self.load_toml(side)
        self.assertEqual(data["entry"]["1"]["estimate"]["man_hours"], 2.0)
        self.assertEqual(data["entry"]["3"]["estimate"]["man_hours"], 5.0)
        self.assertEqual(data["entry"]["1"]["class"], "standard")

    def test_an_unknown_entry_is_not_found(self):
        r = self.run_cli("set-estimate", "--project-root", self.root, "--ticket-dir", self.tdir,
                         "--entry", "9", "--man-hours", "1", check=False)
        self.assertEqual(r.returncode, 3, r.stderr)

    def test_hand_set_estimate_is_override(self):
        toml_path = os.path.join(self.tdir, "tickets.toml")
        with open(toml_path, encoding="utf-8") as fh:
            text = fh.read()
        text = text.replace('title = "UI shell"\n',
                            'title = "UI shell"\nestimate = 2 # the user gave one\n'
                            "l3io_man_hours = 6\n")
        write(toml_path, text)
        with open(toml_path, "rb") as fh:
            before = fh.read()
        r = self.run_cli("set-estimate", "--project-root", self.root, "--ticket-dir", self.tdir,
                         "--entry", "2", "--man-hours", "3", "--elapsed-hours", "1")
        self.assertIn("hand-set", r.stderr)
        with open(toml_path, "rb") as fh:
            self.assertEqual(fh.read(), before, "tickets.toml was written")
        eff = pm.sidecar.effective_estimate(self.tdir, "2")
        self.assertEqual(eff["source"], "tickets.toml")
        self.assertEqual(eff["hand_estimate"], 2)
        self.assertEqual(eff["values"]["man_hours"], 6)        # the override wins
        self.assertEqual(eff["values"]["elapsed_hours"], 1.0)  # ours fills what it leaves
        plain = pm.sidecar.effective_estimate(self.tdir, "1")
        self.assertEqual(plain["source"], None)


class TestConcurrency(Project):

    def _parallel(self, argvs):
        procs = [subprocess.Popen([sys.executable, SCRIPT, *a], stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True) for a in argvs]
        for p, a in zip(procs, argvs, strict=True):
            out, err = p.communicate()
            self.assertEqual(p.returncode, 0, f"{a}\n{out}\n{err}")

    def test_concurrent_set_actual_distinct_plans(self):
        plans = []
        for i in range(8):
            p = os.path.join(self.tdir, f"story-p{i}-plan.md")
            write(p, plan(10 + i))
            plans.append(p)
        self._parallel([["set-actual", "--project-root", self.root, "--plan-file", p,
                         "--node", "story", "--elapsed-hours", "1", "--man-hours", str(i + 1),
                         "--hitl-hours", "0", "--tokens-na"]
                        for i, p in enumerate(plans)])
        for i, p in enumerate(plans):
            side = self.load_toml(p[:-3] + ".l3io.toml")
            self.assertEqual(side["actual"]["man_hours"], i + 1)
        with open(os.path.join(self.state_root, "events.jsonl"), encoding="utf-8") as fh:
            events = [json.loads(line) for line in fh]
        self.assertEqual(sorted(e["plan"].rsplit("/", 1)[1] for e in events),
                         sorted(os.path.basename(p) for p in plans))

    def test_concurrent_set_estimate_one_sidecar(self):
        """Eight writers of ONE l3io.toml, each its own entry: the lock is what keeps all."""
        lines = "".join(f'[[entry]]\nid = {n}\ntype = "story"\ntitle = "t{n}"\n\n'
                        for n in range(10, 18))
        with open(os.path.join(self.tdir, "tickets.toml"), "a", encoding="utf-8") as fh:
            fh.write("\n" + lines)
        self._parallel([["set-estimate", "--project-root", self.root, "--ticket-dir",
                         self.tdir, "--entry", str(n), "--man-hours", str(n)]
                        for n in range(10, 18)])
        data = self.load_toml(os.path.join(self.tdir, "l3io.toml"))
        self.assertEqual({k: v["estimate"]["man_hours"] for k, v in data["entry"].items()},
                         {str(n): float(n) for n in range(10, 18)})


class TestReconcile(Project):
    """`tickets.py move` moves the leaf and the plan and renumbers the entry; our sidecars
    stay where they were. The tree below is what that move leaves behind."""

    def setUp(self):
        super().setUp()
        pricing = os.path.join(self.initiative, "tickets", "epic-pricing")
        write(os.path.join(pricing, "epic-pricing.md"), "---\ntype: epic\nafter: []\n---\n")
        self.dest = os.path.join(pricing, "tickets")
        write(os.path.join(self.dest, "tickets.toml"),
              '[[entry]]\nid = 1\ntype = "story"\ntitle = "Pricing contract"\n\n'
              '[[entry]]\nid = 3\ntype = "story"\ntitle = "UI shell"\n')
        # Our sidecars as they stood before the move: entry 2's estimate, its plan's actuals.
        self.run_cli("set-estimate", "--project-root", self.root, "--ticket-dir", self.tdir,
                     "--entry", "2", "--man-hours", "3")
        self.run_cli("set-estimate", "--project-root", self.root, "--ticket-dir", self.tdir,
                     "--entry", "1", "--man-hours", "1")
        self.run_cli("set-actual", "--project-root", self.root, "--plan-file", self.plans[2],
                     "--node", "story", "--man-hours", "4")
        # The move itself, as tickets.py performs it: entry 2 leaves epic-cart, the leaf and
        # plan travel, the plan's `ticket` becomes 3.
        write(os.path.join(self.tdir, "tickets.toml"),
              'next_id = 5\n\n[[entry]]\nid = 1\ntype = "story"\ntitle = "Scaffold"\n\n'
              '[[entry]]\nid = 3\ntype = "story"\ntitle = "Tracer"\nafter = [1, "1.3"]\n')
        for name in ("story-ui-shell.md", "story-ui-shell-plan.md"):
            shutil.move(os.path.join(self.tdir, name), os.path.join(self.dest, name))
        self.moved_json = os.path.join(self.root, "move.json")
        write(self.moved_json, json.dumps(RECORDED_MOVE))

    def test_reconcile_follows_move(self):
        r = self.run_cli("sidecar-reconcile", "--project-root", self.root,
                         "--initiative-dir", self.initiative, "--moved-json", self.moved_json)
        self.assertEqual(len(r.stdout.strip().splitlines()), 2, r.stdout)
        src = self.load_toml(os.path.join(self.tdir, "l3io.toml"))
        self.assertNotIn("2", src["entry"])
        self.assertEqual(src["entry"]["1"]["estimate"]["man_hours"], 1.0)
        dst = self.load_toml(os.path.join(self.dest, "l3io.toml"))
        self.assertEqual(dst["entry"]["3"]["estimate"]["man_hours"], 3.0)
        self.assertFalse(os.path.exists(os.path.join(self.tdir, "story-ui-shell-plan.l3io.toml")))
        moved = self.load_toml(os.path.join(self.dest, "story-ui-shell-plan.l3io.toml"))
        self.assertEqual(moved["actual"]["man_hours"], 4)
        # Idempotent: the same move JSON again changes nothing.
        again = self.run_cli("sidecar-reconcile", "--project-root", self.root,
                             "--initiative-dir", self.initiative, "--moved-json", self.moved_json)
        self.assertNotIn("repoint", again.stdout)
        self.assertNotIn("move ", again.stdout)

    def test_sweep_moves_an_orphaned_ticket_sidecar(self):
        r = self.run_cli("sidecar-reconcile", "--project-root", self.root,
                         "--initiative-dir", self.initiative)
        self.assertIn("story-ui-shell-plan.l3io.toml", r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "story-ui-shell-plan.l3io.toml")))
        # The entry estimate cannot be followed without the move JSON: reported, not moved.
        self.assertIn("orphan entry epic-cart 2", r.stdout)
        self.assertIn("2", self.load_toml(os.path.join(self.tdir, "l3io.toml"))["entry"])

    def test_reconcile_usage(self):
        r = self.run_cli("sidecar-reconcile", "--project-root", self.root, check=False)
        self.assertEqual(r.returncode, 2)
        write(self.moved_json, "not json")
        r = self.run_cli("sidecar-reconcile", "--project-root", self.root,
                         "--initiative-dir", self.initiative, "--moved-json", self.moved_json,
                         check=False)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
