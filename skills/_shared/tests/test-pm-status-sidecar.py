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

    def test_the_3x_node_address_is_gone(self):
        """The 3.x address retired in Phase 6: a node key or a state root is no flag of these
        verbs any more, and the v7 address is required, so each call is a usage error."""
        r = self.run_cli("set-actual", "--project-root", self.root, "--plan-file",
                         self.plans[1], "--node", "story", "--story", "E001-S01-001",
                         "--man-hours", "1", check=False)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("unrecognized arguments: --story", r.stderr)
        r = self.run_cli("set-actual", "--state-root", self.state_root, "--plan-file",
                         self.plans[1], "--node", "story", "--man-hours", "1", check=False)
        self.assertEqual(r.returncode, 2, r.stderr)
        for verb, extra in (("set-actual", ["--man-hours", "1"]),
                            ("set-estimate", ["--man-hours", "1"]),
                            ("add-test-run", ["--command", "x", "--exit-code", "0"]),
                            ("verify", [])):
            r = self.run_cli(verb, "--state-root", self.state_root, "--story", "E001-S01-001",
                             *extra, check=False)
            self.assertEqual(r.returncode, 2, f"{verb}: {r.stderr}")
            self.assertIn("required: --project-root", r.stderr, verb)

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


class TestEstimateEntries(Project):
    """`estimate-entries`: Sofia's slice, refine and replan hooks, and `l3io-plan estimate`,
    estimate a v7 epic's entries into its `l3io.toml` and roll the epic up from them."""

    CLASSES = ("--class", "1=simple", "--class", "2=standard", "--class", "3=complex")

    def est(self, *extra, tdir=None, check=True):
        r = self.run_cli("estimate-entries", "--project-root", self.root,
                         "--ticket-dir", tdir or self.tdir, *extra, check=check)
        lines = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
        return r, lines

    def side(self, tdir=None):
        return self.load_toml(os.path.join(tdir or self.tdir, "l3io.toml"))

    def written(self, lines):
        return sorted(str(x["entry"]) for x in lines if "entry" in x)

    def test_estimate_entries_writes_only_l3io_toml(self):
        before, tree = self.snapshot(), self.tree()
        _, lines = self.est(*self.CLASSES)
        after = self.snapshot()
        self.assertEqual(sorted(after), sorted(before), "a v7 file appeared or vanished")
        for p, data in before.items():
            self.assertEqual(after[p], data, f"{os.path.relpath(p, self.root)} changed")
        self.assertEqual(self.tree() - tree,
                         {os.path.relpath(os.path.join(self.tdir, "l3io.toml"), self.root)})
        self.assertEqual(self.written(lines), ["1", "2", "3"])
        entry = self.side()["entry"]
        self.assertEqual({k: v["class"] for k, v in entry.items()},
                         {"1": "simple", "2": "standard", "3": "complex"})
        for v in entry.values():
            self.assertEqual(list(v["estimate"])[:5], list(pm.METRIC_FIELDS))
            self.assertGreater(v["estimate"]["cost"], 0)
            self.assertIn("scope_ratios", v["estimate"])

    def test_check_reports_unestimated_entries_and_writes_nothing(self):
        before, tree = self.snapshot(), self.tree()
        r, _ = self.est("--check", check=False)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(len([x for x in r.stdout.splitlines() if x.startswith("entry ")]), 3)
        self.assertEqual((self.snapshot(), self.tree()), (before, tree))
        self.est(*self.CLASSES)
        r, _ = self.est("--check")
        self.assertIn("OK", r.stdout)

    def test_check_refuses_the_flags_that_write(self):
        for extra in (("--class", "1=simple"), ("--entry", "1"), ("--force",)):
            r, _ = self.est("--check", *extra, check=False)
            self.assertEqual(r.returncode, 2, extra)

    def test_changed_entry_is_reestimated_unchanged_is_not(self):
        self.est(*self.CLASSES)
        first = self.side()["entry"]
        _, lines = self.est()
        self.assertEqual(self.written(lines), [], "an unchanged entry was re-estimated")
        toml_path = os.path.join(self.tdir, "tickets.toml")
        with open(toml_path, encoding="utf-8") as fh:
            text = fh.read()
        write(toml_path, text.replace('title = "UI shell"\n',
                                      'title = "UI shell"\ndescription = "Now with a cart"\n'))
        _, lines = self.est()
        self.assertEqual(self.written(lines), ["2"])
        self.assertEqual([x["action"] for x in lines if "entry" in x], ["changed"])
        second = self.side()["entry"]
        self.assertEqual(second["1"], first["1"])
        self.assertEqual(second["3"], first["3"])
        self.assertNotEqual(second["2"]["fingerprint"], first["2"]["fingerprint"])
        # Asked for by id, an unchanged entry is re-estimated; --force does all of them.
        _, lines = self.est("--entry", "1")
        self.assertEqual(self.written(lines), ["1"])
        _, lines = self.est("--force")
        self.assertEqual(self.written(lines), ["1", "2", "3"])
        # A --class differing from the recorded one is a change; the same class is not.
        _, lines = self.est("--class", "1=complex", "--class", "2=standard")
        self.assertEqual(self.written(lines), ["1"])
        self.assertEqual(self.side()["entry"]["1"]["class"], "complex")

    def test_epic_rollup_has_no_sprint_term(self):
        _, lines = self.est(*self.CLASSES)
        data = self.side()
        epic = data["epic"]["estimate"]
        total = sum(v["estimate"]["man_hours"] for v in data["entry"].values())
        # Cold start: Σ entries x (1 + the epic closure band); no orchestration band is
        # active before three samples, and no sprint level exists to add one of its own.
        self.assertAlmostEqual(epic["man_hours_low"], round(total * 1.10, 2))
        self.assertAlmostEqual(epic["man_hours_high"], round(total * 1.25, 2))
        self.assertEqual(set(epic["closure_ratios"]), {"man_hours", "hitl_hours",
                                                       "elapsed_hours", "tokens_k"})
        with open(os.path.join(self.tdir, "l3io.toml"), encoding="utf-8") as fh:
            self.assertNotIn("sprint", fh.read())
        self.assertEqual([x.get("epic") for x in lines if "epic" in x], ["epic-cart"])
        self.assertEqual(lines[-1]["children"], 3)

    def test_reconcile_then_estimate_after_move(self):
        """A recorded `tickets.py move` of entry 3 to epic-pricing, where it becomes 7."""
        self.est(*self.CLASSES)
        before = self.side()["entry"]["3"]
        pricing = os.path.join(self.initiative, "tickets", "epic-pricing")
        write(os.path.join(pricing, "epic-pricing.md"), "---\ntype: epic\nafter: []\n---\n")
        dest = os.path.join(pricing, "tickets")
        write(os.path.join(dest, "tickets.toml"),
              'next_id = 8\n\n[[entry]]\nid = 7\ntype = "story"\ntitle = "Tracer"\n')
        write(os.path.join(self.tdir, "tickets.toml"),
              '[[entry]]\nid = 1\ntype = "story"\ntitle = "Scaffold"\n\n'
              '[[entry]]\nid = 2\ntype = "story"\ntitle = "UI shell"\nafter = [1]\n')
        for name in ("story-tracer.md", "story-tracer-plan.md"):
            shutil.move(os.path.join(self.tdir, name), os.path.join(dest, name))
        move = {"from": "epic-cart", "to": "epic-pricing", "old_id": 3, "id": 7, "ref": "2.7",
                "file": "story-tracer.md", "plan": "story-tracer-plan.md",
                "next_id": {"epic-pricing": 8}, "rewritten": []}
        self.run_cli("sidecar-reconcile", "--project-root", self.root,
                     "--initiative-dir", self.initiative, "--moved-json", json.dumps(move))
        _, lines = self.est(tdir=dest)
        self.assertEqual(self.written(lines), [], "the moved entry was re-estimated")
        self.assertEqual(self.side(dest)["entry"]["7"], before)
        _, lines = self.est()
        src = self.side()
        self.assertNotIn("3", src["entry"])
        self.assertEqual(lines[-1]["children"], 2, "the source epic still rolls up entry 3")
        self.assertEqual(self.side(dest)["epic"]["estimate"]["man_hours_low"],
                         round(before["estimate"]["man_hours"] * 1.10, 2))

    def test_hand_set_estimate_is_skipped_and_hand_set_class_is_used(self):
        toml_path = os.path.join(self.tdir, "tickets.toml")
        with open(toml_path, encoding="utf-8") as fh:
            text = fh.read()
        text = text.replace('title = "UI shell"\n', 'title = "UI shell"\nestimate = "3d"\n')
        text = text.replace('title = "Tracer"\n', 'title = "Tracer"\nl3io_class = "complex"\n')
        write(toml_path, text)
        r, lines = self.est("--class", "1=simple", "--class", "2=standard", "--force")
        self.assertEqual(self.written(lines), ["1", "3"])
        self.assertIn("entry 2", r.stderr)
        self.assertIn("hand-set", r.stderr)
        self.assertEqual(self.side()["entry"]["3"]["class"], "complex")
        self.assertNotIn("2", self.side()["entry"])

    def test_missing_class_is_refused_and_writes_nothing(self):
        r, _ = self.est("--class", "1=simple", check=False)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("--class", r.stderr)
        self.assertIn("2", r.stderr)
        self.assertIn("3", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tdir, "l3io.toml")))
        r, _ = self.est("--class", "1=huge", "--class", "2=simple", "--class", "3=simple",
                        check=False)
        self.assertEqual(r.returncode, 2, r.stderr)
        r, _ = self.est("--entry", "9", *self.CLASSES, check=False)
        self.assertEqual(r.returncode, 3, r.stderr)

    def test_estimate_entries_commits_exactly_what_it_wrote(self):
        """Sofia's hooks run between her commits and the next `bmad-build-auto`, which
        refuses a dirty tree; the verb commits its sidecar and nothing else."""
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

        def git(*argv):
            return subprocess.run(["git", "-C", self.root, *argv], check=True,
                                  capture_output=True, text=True, env=env).stdout
        git("init", "-q")
        git("add", "-A")
        git("commit", "-q", "-m", "fixture")
        write(os.path.join(self.root, "notes.txt"), "the user's own work in progress\n")
        r = subprocess.run([sys.executable, SCRIPT, "estimate-entries", "--project-root",
                            self.root, "--ticket-dir", self.tdir, *self.CLASSES],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(git("status", "--porcelain", "--untracked-files=all"),
                         "?? notes.txt\n")
        self.assertEqual(git("log", "-1", "--format=%s"), "chore(l3io): estimates epic-cart\n")
        self.assertEqual(git("show", "--name-only", "--format=", "HEAD").split(),
                         [os.path.relpath(os.path.join(self.tdir, "l3io.toml"), self.root)])
        # A run that writes nothing makes no commit.
        head = git("rev-parse", "HEAD")
        subprocess.run([sys.executable, SCRIPT, "estimate-entries", "--project-root",
                        self.root, "--ticket-dir", self.tdir], check=True,
                       capture_output=True, env=env)
        self.assertEqual(git("rev-parse", "HEAD"), head)


# --------------------------------------------------------------------------- #
# Lanes and the v7 report (Task 4.5)
# --------------------------------------------------------------------------- #
LANES_RESOLVE_CONFIG = """\
import json, sys
values = {"core.output_folder": "{project-root}/_bmad-output",
          "modules.l3io-pm.lane_count": LANE_COUNT}
keys = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--key"]
print(json.dumps({k: values[k] for k in keys if k in values and values[k] is not None}))
"""

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


class TestSetLane(Project):

    def config(self, lane_count):
        write(os.path.join(self.root, "_bmad", "scripts", "resolve_config.py"),
              LANES_RESOLVE_CONFIG.replace("LANE_COUNT", repr(lane_count)))

    def set_lane(self, lane, epic="epic-cart", check=False):
        return self.run_cli("set-lane", "--project-root", self.root, "--initiative-dir",
                            self.initiative, "--epic", epic, "--lane", str(lane), check=check)

    def git(self, *argv):
        return subprocess.run(["git", "-C", self.root, *argv], check=True,
                              capture_output=True, text=True, env=GIT_ENV).stdout

    def test_set_lane_refuses_name_and_range(self):
        self.config(3)
        before = self.snapshot()
        side = os.path.join(self.initiative, "tickets", "l3io.toml")
        for bad in ("sarah", "backend", "2.5", "-1", "0", "4", "1000"):
            r = self.set_lane(bad)
            self.assertEqual(r.returncode, 2, f"lane {bad!r} was accepted: {r.stdout}")
            self.assertFalse(os.path.exists(side), f"lane {bad!r} wrote the sidecar")
        self.assertIn("never a person", self.set_lane("sarah").stderr)
        self.assertIn("1..3", self.set_lane("4").stderr)
        self.set_lane(2, check=True)
        self.assertEqual(self.load_toml(side), {"epic": {"epic-cart": {"lane": 2}}})
        self.assertEqual(self.snapshot(), before, "set-lane wrote a v7 file")
        r = self.set_lane(1, epic="epic-nowhere")
        self.assertEqual(r.returncode, 3, r.stderr)

    def test_set_lane_refuses_while_lanes_are_off(self):
        for count in (None, 1):
            self.config(count)
            r = self.set_lane(1)
            self.assertEqual(r.returncode, 2, r.stdout)
            self.assertIn("lanes are off", r.stderr)

    def test_set_lane_keeps_the_tree_clean(self):
        self.config(2)
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "fixture")
        r = subprocess.run([sys.executable, SCRIPT, "set-lane", "--project-root", self.root,
                            "--initiative-dir", self.initiative, "--epic", "epic-cart",
                            "--lane", "2"], capture_output=True, text=True, env=GIT_ENV)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), "")
        self.assertEqual(self.git("log", "-1", "--format=%s"), "chore(l3io): lane epic-cart\n")


RECORDED_SHOP = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))),
                             "tests", "l3io-plan", "fixtures", "v7-status-shop.json")


class TestReportV7(Project):
    """`report` over a v7 initiative: the `tickets.py status` JSON recorded at the pin
    (tests/l3io-plan/fixtures/record-v7-status.sh) plus our sidecars beside the tree it
    describes, plus events.jsonl and the build spool."""

    def setUp(self):
        super().setUp()
        self.shop = os.path.join(self.out, "shop")
        write(os.path.join(self.shop, "shop.md"), "---\ntype: initiative\n---\n# Shop\n")
        write(os.path.join(self.shop, "tickets", "l3io.toml"),
              "[epic.epic-platform]\nlane = 1\n\n[epic.epic-cart]\nlane = 2\n")
        tickets = os.path.join(self.shop, "tickets")
        self.ptd = os.path.join(tickets, "epic-platform", "tickets")
        for slug in ("epic-platform", "epic-cart", "epic-search", "epic-checkout",
                     "epic-docs"):
            write(os.path.join(tickets, slug, f"{slug}.md"), "---\ntype: epic\n---\n")
            write(os.path.join(tickets, slug, "tickets", "tickets.toml"), "")
        self.sessions = os.path.join(self.ptd, "story-sessions-plan.md")
        write(self.sessions, "---\ntitle: 'Sessions'\nticket: '1'\nstatus: 'built'\n---\n")
        self.basket = os.path.join(tickets, "epic-cart", "tickets", "story-basket-plan.md")
        write(self.basket, "---\ntitle: 'Basket'\nticket: '1'\nstatus: 'in-progress'\n---\n")
        write(os.path.join(self.ptd, "l3io.toml"),
              "[entry.1]\nclass = \"standard\"\n\n[entry.1.estimate]\nelapsed_hours = 1.0\n"
              "man_hours = 6.0\nhitl_hours = 0.5\ntokens_k = 300\ncost = 4.5\n\n"
              "[epic.estimate]\nelapsed_hours = 3.0\nman_hours = 14.0\nhitl_hours = 1.0\n"
              "tokens_k = 700\ncost = 10.0\n")
        self.run_cli("set-actual", "--project-root", self.root, "--plan-file", self.sessions,
                     "--node", "story", "--runtime", "claude", "--model", MODEL,
                     "--elapsed-hours", "1.5", "--man-hours", "4", "--hitl-hours", "0.25",
                     "--tokens-input", "10", "--tokens-output", "2",
                     "--tokens-cache-write", "1", "--tokens-cache-read", "50")

    def spool(self, name, minutes_ago, plan):
        from datetime import UTC, datetime, timedelta
        opened = datetime.now(UTC) - timedelta(minutes=minutes_ago)
        write(os.path.join(self.state_root, ".inflight", name),
              json.dumps({"agent": "bmad-build-auto", "key": name[:-5],
                          "opened_at": opened.isoformat(),
                          "plan": os.path.relpath(plan, self.root)}) + "\n")

    def report(self, *extra, check=True):
        return self.run_cli("report", "--project-root", self.root, "--initiative-dir",
                            self.shop, "--status-json", RECORDED_SHOP, *extra, check=check)

    def test_report_reads_v7_tree(self):
        before = self.tree()
        model = json.loads(self.report("--format", "json").stdout)
        self.assertEqual(model["source"], "v7")
        self.assertEqual([e["slug"] for e in model["epics"]],
                         ["epic-platform", "epic-cart", "epic-search", "epic-checkout",
                          "epic-docs"])
        plat, cart = model["epics"][0], model["epics"][1]
        self.assertEqual((plat["lane"], cart["lane"], model["epics"][2]["lane"]), (1, 2, None))
        self.assertEqual(plat["estimate"]["man_hours"], 14.0)
        self.assertEqual(plat["counts"], {"review": 1, "planned": 1})
        sessions = plat["tickets"][0]
        self.assertEqual((sessions["ref"], sessions["state"]), ("1.1", "review"))
        self.assertEqual(sessions["estimate"]["man_hours"], 6.0)
        self.assertEqual(sessions["actual"]["man_hours"], 4.0)
        self.assertEqual(sessions["plan"],
                         os.path.relpath(self.sessions, self.root))
        self.assertEqual(plat["actual"]["man_hours"], 4.0)
        self.assertEqual(model["actual_total"]["man_hours"], 4.0)
        self.assertEqual(cart["tickets"][0]["state"], "in-progress")
        self.assertEqual(model["totals"]["tickets"]["planned"], 4)
        tree = self.report().stdout
        self.assertIn("epic-platform", tree)
        self.assertIn("lane 1", tree)
        self.assertEqual(self.tree(), before, "report wrote into the project")

    def test_report_stall_reads_the_open_build_bracket(self):
        """An open build bracket lives only in the gitignored spool until build-close, so
        the stall view must read the spool or it cannot see a hung build."""
        self.spool("hung.json", 40, self.basket)
        self.spool("fresh.json", 2, self.sessions)
        self.spool("abandoned-old-20260101T000000.json", 300, self.sessions)
        before = self.tree()
        model = json.loads(self.report("--format", "json", "--stall-minutes", "15").stdout)
        stalled = model["stalled_dispatches"]
        self.assertEqual(len(stalled), 1, stalled)
        self.assertEqual(stalled[0]["agent"], "bmad-build-auto")
        self.assertEqual(stalled[0]["plan"], os.path.relpath(self.basket, self.root))
        self.assertEqual(stalled[0]["ticket"], "epic-cart/1")
        self.assertGreaterEqual(stalled[0]["age_minutes"], 39)
        tree = self.report("--stall-minutes", "15").stdout
        self.assertIn("STALLED", tree)
        self.assertIn("story-basket-plan.md", tree)
        self.assertEqual(self.tree(), before, "report wrote into the project")
        none = json.loads(self.report("--format", "json", "--stall-minutes", "60").stdout)
        self.assertEqual(none["stalled_dispatches"], [])

    def test_report_v7_refuses_3x_only_flags(self):
        for extra in (("--all",), ("--status", "active"), ("--plan", "x.yaml")):
            r = self.report(*extra, check=False)
            self.assertEqual(r.returncode, 2, extra)
        r = self.run_cli("report", "--project-root", self.root, check=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--initiative-dir", r.stderr)



# --------------------------------------------------------------------------- #
# Epic closure on bmad-retrospective (Task 4.6)
# --------------------------------------------------------------------------- #
SESSION = "5e55a0d1-0000-4000-8000-0000000e71c0"


def _uv_dirs():
    """uv's cache and Python installs, captured before HOME is redirected, so the `uv run`
    of the fake resolver reuses them instead of provisioning from the network."""
    out = {}
    for key, argv in (("UV_CACHE_DIR", ["uv", "cache", "dir"]),
                      ("UV_PYTHON_INSTALL_DIR", ["uv", "python", "dir"])):
        try:
            r = subprocess.run(argv, capture_output=True, text=True, check=False)
        except OSError:
            continue
        if r.returncode == 0 and r.stdout.strip():
            out[key] = r.stdout.strip()
    return out


def retro_doc(verdict="accepted", epic="epic-cart", body_verdict="rejected"):
    """The retrospective as retro-document.md:9-21 has bmad-retrospective write it: the
    verdict in the frontmatter, and prose below that must never be read for it."""
    fm = f"epic: {epic}\ndate: 2026-11-17\n"
    if verdict is not None:
        fm += f"verdict: {verdict}\n"
    return (f"---\n{fm}criteria: declared\nheadless: true\n---\n\n# Retrospective\n\n"
            f"## Acceptance verdict\n\nverdict: {body_verdict} was considered and set aside.\n")


class TestEpicClose(Project):
    """`epic-close`: the On Complete l3io wires into `bmad-retrospective`. It rolls the epic's
    ticket actuals up, records the retrospective's own spend as the closure actual, takes one
    closure calibration sample against the epic estimate, and records the verdict -- and
    writes no status and no v7 file."""

    CLASSES = ("--class", "1=simple", "--class", "2=standard", "--class", "3=complex")

    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.root, ".home")
        os.makedirs(self.home)
        self.retro = os.path.join(self.epic, "epic-cart-retrospective.md")
        write(self.retro, retro_doc())
        self.env = {**os.environ, **_uv_dirs(), "HOME": self.home,
                    "CLAUDE_CODE_SESSION_ID": SESSION}
        self.ticket_actual(1, man="2", tokens=("10", "2", "1", "50"))
        self.ticket_actual(2, man="4", tokens=("20", "4", "2", "100"))

    def ticket_actual(self, n, man, tokens):
        i, o, w, r = tokens
        self.run_cli("set-actual", "--project-root", self.root, "--plan-file", self.plans[n],
                     "--node", "story", "--runtime", "claude", "--model", MODEL,
                     "--elapsed-hours", "1", "--man-hours", man, "--hitl-hours", "0.25",
                     "--tokens-input", i, "--tokens-output", o, "--tokens-cache-write", w,
                     "--tokens-cache-read", r)

    def estimate(self):
        self.run_cli("estimate-entries", "--project-root", self.root, "--ticket-dir",
                     self.tdir, *self.CLASSES)

    def transcript(self):
        """This session's transcript: a turn long before the retrospective, which must not
        count, then the turn that wrote the retrospective's skeleton and one after it."""
        from datetime import UTC, datetime, timedelta
        d = os.path.join(self.home, ".claude", "projects", "-tmp-proj")
        now = datetime.now(UTC)

        def rec(mid, when, usage, content=None):
            msg = {"id": mid, "model": MODEL, "usage": usage}
            if content is not None:
                msg["content"] = content
            return json.dumps({"type": "assistant", "sessionId": SESSION,
                               "timestamp": when.isoformat(), "message": msg})
        lines = [
            rec("m0", now - timedelta(hours=3),
                {"input_tokens": 999000, "output_tokens": 999000,
                 "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}),
            rec("m1", now - timedelta(minutes=30),
                {"input_tokens": 1000, "output_tokens": 2000,
                 "cache_creation_input_tokens": 3000, "cache_read_input_tokens": 40000},
                [{"type": "tool_use", "name": "Write",
                  "input": {"file_path": self.retro, "content": "---\nepic: epic-cart\n"}}]),
            rec("m2", now - timedelta(minutes=1),
                {"input_tokens": 500, "output_tokens": 500,
                 "cache_creation_input_tokens": 0, "cache_read_input_tokens": 10000}),
        ]
        write(os.path.join(d, f"{SESSION}.jsonl"), "\n".join(lines) + "\n")

    def close(self, *extra, runtime="claude", man="1.5", hitl="0", check=True):
        argv = ["epic-close", "--project-root", self.root, "--epic-dir", self.epic,
                "--retro-file", self.retro, "--runtime", runtime, "--man-hours", man,
                "--hitl-hours", hitl, *extra]
        r = subprocess.run([sys.executable, SCRIPT, *argv], capture_output=True, text=True,
                           env=self.env)
        if check:
            self.assertEqual(r.returncode, 0, f"{argv}\nstdout: {r.stdout}\nstderr: {r.stderr}")
        return r

    def epic_side(self):
        p = os.path.join(self.tdir, "l3io.toml")
        return self.load_toml(p).get("epic", {}) if os.path.exists(p) else {}

    def closure_samples(self):
        p = os.path.join(self.state_root, "pm-calibration.yaml")
        if not os.path.exists(p):
            return {}
        from ruamel.yaml import YAML
        with open(p, encoding="utf-8") as fh:
            cal = YAML(typ="safe").load(fh) or {}
        epic = (cal.get("closure") or {}).get("epic") or {}
        return {m: list(v.get("samples", [])) for m, v in epic.items()}

    def test_epic_close_rolls_up_sidecars(self):
        self.transcript()
        self.close()
        epic = self.epic_side()
        closure, actual = epic["closure"], epic["actual"]
        self.assertEqual(list(closure)[:5], list(pm.METRIC_FIELDS), closure)
        self.assertEqual(list(actual)[:5], list(pm.METRIC_FIELDS), actual)
        tk = closure["tokens_k"]
        self.assertEqual((tk["input"], tk["output"], tk["cache_write"], tk["cache_read"]),
                         (1.5, 2.5, 3.0, 50.0), "a turn before the retrospective was counted")
        self.assertEqual((closure["man_hours"], closure["hitl_hours"]), (1.5, 0))
        self.assertGreater(closure["elapsed_hours"], 0.4)
        self.assertLess(closure["elapsed_hours"], 0.6)
        self.assertGreater(closure["cost"], 0)
        # The epic is every ticket sidecar under its tickets/ folder, plus the closure.
        self.assertEqual(actual["man_hours"], 2 + 4 + 1.5)
        self.assertEqual(actual["hitl_hours"], 0.25 + 0.25 + 0)
        self.assertEqual(actual["tokens_k"]["total"], 63 + 126 + 57)
        self.assertEqual(actual["tokens_k"]["cache_read"], 50 + 100 + 50)
        tickets_cost = sum(self.load_toml(os.path.join(self.tdir, f"story-{s}-plan.l3io.toml"))
                           ["actual"]["cost"] for s in ("scaffold", "ui-shell"))
        self.assertAlmostEqual(actual["cost"], tickets_cost + closure["cost"], places=2)
        with open(os.path.join(self.state_root, "events.jsonl"), encoding="utf-8") as fh:
            events = [json.loads(x) for x in fh]
        retro = [e for e in events if e.get("agent") == "bmad-retrospective"]
        self.assertEqual([e["event"] for e in retro], ["dispatch_open", "dispatch_close"])
        self.assertTrue(all(e.get("epic") == "epic-cart" for e in retro), retro)
        # A second retrospective of the same epic adds its own spend and never re-counts the
        # first: the window starts where the last closure ended.
        self.close(man="0.5")
        again = self.epic_side()
        self.assertEqual(len(again["closure_runs"]), 2)
        self.assertEqual(again["closure"]["man_hours"], 2.0)
        self.assertEqual(again["closure"]["tokens_k"]["total"], tk["total"],
                         "the second run re-counted the first run's turns")

    def test_closure_sample_only_with_estimate(self):
        self.transcript()
        r = self.close()
        self.assertEqual(self.closure_samples(), {}, "a sample with no estimate to compare")
        self.assertIn("no closure sample", r.stderr)
        self.assertNotIn("calibration_sampled_at", self.epic_side())

        self.estimate()
        est = self.epic_side()["estimate"]
        self.close(man="1.5")
        samples = self.closure_samples()
        self.assertEqual(sorted(samples), ["elapsed_hours", "man_hours", "tokens_k"],
                         samples)   # hitl_hours is 0 here: a zero closure is never a sample
        self.assertTrue(all(len(v) == 1 for v in samples.values()), samples)
        children = sum(self.load_toml(os.path.join(self.tdir, "l3io.toml"))["entry"][str(i)]
                       ["estimate"]["man_hours"] for i in (1, 2, 3))
        expected = (est["man_hours_low"] + est["man_hours_high"]) / 2 - children
        closure = self.epic_side()["closure"]["man_hours"]
        self.assertAlmostEqual(samples["man_hours"][0], round(closure / expected, 4), places=4)
        self.assertIn("calibration_sampled_at", self.epic_side())
        self.close(man="0.5")
        self.assertEqual(self.closure_samples(), samples, "the epic was sampled twice")

    def test_rejected_verdict_takes_no_sample(self):
        self.transcript()
        self.estimate()
        write(self.retro, retro_doc(verdict="rejected", body_verdict="accepted"))
        r = self.close()
        self.assertEqual(self.closure_samples(), {})
        self.assertIn("rejected", r.stderr)
        self.assertEqual(self.epic_side()["retro_verdict"], "rejected")

    def test_epic_close_writes_no_status_and_no_tree_file(self):
        self.transcript()
        self.estimate()
        before, tree = self.snapshot(), self.tree()
        side = os.path.join(self.tdir, "l3io.toml")
        self.close()
        self.assertEqual(self.snapshot(), before, "epic-close wrote a v7 file")
        created = {os.path.join(self.root, p) for p in self.tree() - tree}
        inside = {p for p in created if p.startswith(self.initiative + os.sep)}
        self.assertEqual(inside, set(), f"epic-close created {sorted(inside)} in v7's tree")
        self.assertTrue(all(p.startswith(self.state_root) for p in created), created)
        with open(side, encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotRegex(text, r"(?m)^\s*status\s*=", "epic-close wrote a status")
        for n in (1, 2):
            ticket = self.load_toml(pm.nodes.ticket_sidecar(self.plans[n]))
            self.assertNotIn("status", ticket)

    def test_verdict_read_from_frontmatter(self):
        self.transcript()
        write(self.retro, retro_doc(verdict="accepted-with-open-items"))
        self.close()
        self.assertEqual(self.epic_side()["retro_verdict"], "accepted-with-open-items")
        side = os.path.join(self.tdir, "l3io.toml")
        def text():
            with open(side, encoding="utf-8") as fh:
                return fh.read()
        written = text()
        for bad, why in ((retro_doc(verdict=None), "verdict"),
                         (retro_doc(verdict="maybe"), "maybe"),
                         (retro_doc(epic="epic-search"), "epic-search")):
            write(self.retro, bad)
            r = self.close(check=False)
            self.assertEqual(r.returncode, 2, r.stdout)
            self.assertIn(why, r.stderr)
            self.assertEqual(text(), written,
                             "a refused close wrote the sidecar")
        r = self.run_cli("epic-close", "--project-root", self.root, "--epic-dir", self.epic,
                         "--retro-file", os.path.join(self.epic, "nope.md"), "--runtime",
                         "other", "--man-hours", "1", "--hitl-hours", "0", check=False)
        self.assertEqual(r.returncode, 3, r.stderr)

    def test_window_needs_since_where_no_transcript_can_give_it(self):
        r = self.close(runtime="other", check=False)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("--since", r.stderr)
        self.assertEqual(self.epic_side(), {})
        from datetime import UTC, datetime, timedelta
        since = (datetime.now(UTC) - timedelta(minutes=12)).isoformat()
        self.close("--since", since, runtime="other")
        closure = self.epic_side()["closure"]
        self.assertEqual(closure["tokens_k"], "N/A")
        self.assertAlmostEqual(closure["elapsed_hours"], 0.2, places=2)
        # One part of the epic with no token count makes the epic's count unknown, not a
        # partial sum that reads as the whole.
        self.assertEqual(self.epic_side()["actual"]["tokens_k"], "N/A")


class TestNoBytecode(unittest.TestCase):
    """v7 installs pm_status under `_bmad/l3io-pm/scripts/`, and a project that commits `_bmad/`
    (the only kind whose worktrees can run a build) would see a `__pycache__/` appear there on
    the first hook. `bmad-build-auto` halts on any untracked file (step-01-clarify-and-route.md
    :60), so the package writes no bytecode, as v7's own scripts do not (`render_skill.py:26`,
    `tickets.py:54`)."""

    def test_running_an_installed_copy_writes_no_bytecode(self):
        root = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        pkg = os.path.join(root, "_bmad", "l3io-pm", "scripts", "pm_status")
        shutil.copytree(os.path.dirname(SCRIPT), pkg,
                        ignore=shutil.ignore_patterns("__pycache__"))
        env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
        r = subprocess.run([sys.executable, os.path.join(pkg, "__main__.py"), "rates"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        caches = [d for d, _dirs, _files in os.walk(pkg) if os.path.basename(d) == "__pycache__"]
        self.assertEqual(caches, [])


if __name__ == "__main__":
    unittest.main()
