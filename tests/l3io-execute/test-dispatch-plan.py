#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18", "tomlkit>=0.13"]
# ///
"""
Tests for l3io-execute's unattended run (plan 2026-11-17-v7-phase-4-hooks.md, Task 4.7). Run
with: uv run tests/l3io-execute/test-dispatch-plan.py

`dispatch-plan.py` turns v7's own `tickets.py status` and plan-graph.py's `waves` into the
command plan the run follows; it never runs a build. `close-commit.py` commits what the run's
closing steps leave behind, so the next `bmad-build-auto` starts on a clean tree
(`step-01-clarify-and-route.md:60`).

The status JSON is the recorded `tickets.py status` of the shop initiative
(tests/l3io-plan/fixtures/v7-status-shop.json, from the pinned tickets.py): five epics, waves
[platform, docs] -> [cart] -> [search, checkout], and one gate, epic-cart, which
epic-checkout's own `after` waits on for closure.
"""
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "skills" / "l3io-pm" / "l3io-execute" / "scripts"
DISPATCH = _SCRIPTS / "dispatch-plan.py"
CLOSE_COMMIT = _SCRIPTS / "close-commit.py"
PLAN_GRAPH = _REPO / "skills" / "l3io-pm" / "l3io-plan" / "scripts" / "plan-graph.py"
PM_STATUS = _REPO / "skills" / "_shared" / "pm_status"
STEPS = _REPO / "skills" / "_shared" / "steps" / "execute"
WIRE_IN = _REPO / "skills" / "l3io-util" / "l3io-doctor" / "assets" / "wire-in.toml"
SHOP = _REPO / "tests" / "l3io-plan" / "fixtures" / "v7-status-shop.json"
PORTFOLIO = _REPO / "tests" / "l3io-plan" / "fixtures" / "v7-status-portfolio.json"

# The plan's step table, and nothing else (Task 4.7 Interfaces).
STEP_KINDS = {"sync", "checkpoint-plan", "build", "checkpoint-done", "close-epic",
              "status-done", "merge"}
# `tickets.py ... mark`: the one verb a tracker store refuses (tickets.py:1288).
MARK_RE = re.compile(r"tickets\.py\b[^\n]*\bmark\b")
NEXT_RE = re.compile(r"tickets\.py\b[^\n]*\bnext\b[^\n]*")
REVIEW_RE = re.compile(r"bmad-code-review|bmad-review\b|l3io-arch-review|fix[- ]loop|"
                       r"story[- ]prep|elaborat|arch(itecture)?[- ]gate", re.IGNORECASE)

FAKE_RESOLVE_CONFIG = """\
import json
print(json.dumps({"core.output_folder": "{project-root}/_bmad-output"}))
"""

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
ENV.pop("GIT_DIR", None)
ENV.pop("PYTHONDONTWRITEBYTECODE", None)


def steps_of(plan):
    """Every step the plan emits, in order: the run's sync, then each ticket's, then each
    epic's closing steps."""
    out = list(plan.get("sync", []))
    for wave in plan["waves"]:
        for epic in wave["epics"]:
            for t in epic["tickets"]:
                out += t["steps"]
            out += epic["close"]
    return out


class Project(unittest.TestCase):
    """A git project holding the shop initiative's folders, v7's store config when a test
    plants one, and l3io-pm's installed plan-graph.py."""

    commit_bmad = True

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="test-dispatch-plan-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "proj"
        self.init = self.root / "_bmad-output" / "shop"
        status = json.loads(SHOP.read_text(encoding="utf-8"))
        for e in status["epics"]:
            self.write(f"_bmad-output/shop/tickets/{e['slug']}/{e['slug']}.md",
                       f"---\ntype: epic\n---\n# {e['slug']}\n")
        self.write("_bmad-output/shop/shop.md", "---\ntype: initiative\n---\n# Shop\n")
        self.write("_bmad/l3io-pm/scripts/plan-graph.py", PLAN_GRAPH.read_text(encoding="utf-8"))
        self.write("_bmad/scripts/render_skill.py", "# v7's renderer\n")
        self.write("_bmad/method/scripts/tickets.py", "# v7's tickets.py\n")
        self.write("_bmad/l3io-pm/scripts/pm_status/__main__.py", "# l3io's pm_status\n")
        if not self.commit_bmad:
            self.write(".gitignore", "/_bmad/*\n!/_bmad/custom/\n")
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "fixture")
        self.status = status

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def git(self, *argv, cwd=None):
        r = subprocess.run(["git", "-C", str(cwd or self.root), *argv], capture_output=True,
                           text=True, env=ENV)
        self.assertEqual(r.returncode, 0, f"git {argv}: {r.stderr}")
        return r.stdout

    def store(self, name):
        self.write("_bmad/custom/ticketing-store-config.toml", f'[tickets]\nstore = "{name}"\n')

    def plan(self, *extra, status=None, expect=0, scope=None):
        sj = self.tmp / "status.json"
        sj.write_text(json.dumps(status or self.status), encoding="utf-8")
        argv = [sys.executable, str(DISPATCH), "--project-root", str(self.root),
                *(scope or ["--initiative", str(self.init)]), "--max-parallel", "4",
                "--status-json", str(sj), *extra]
        r = subprocess.run(argv, capture_output=True, text=True, env=ENV)
        self.assertEqual(r.returncode, expect, f"{argv}\nstdout: {r.stdout}\nstderr: {r.stderr}")
        return json.loads(r.stdout) if expect == 0 else r


class TestStore(Project):

    def test_tracker_store_never_calls_mark(self):
        """Review Focus 4: on a tracker, `mark` raises StoreRefusal (tickets.py:1288) and an
        unsynced `next` refuses too (:1002)."""
        self.store("github")
        plan = self.plan()
        self.assertEqual(plan["store"], "github")
        text = json.dumps(plan)
        self.assertIsNone(MARK_RE.search(text), "a tracker plan names tickets.py mark")
        self.assertEqual(plan["sync"][0]["kind"], "sync", "a tracker run starts with sync")
        for t in (t for w in plan["waves"] for e in w["epics"] for t in e["tickets"]):
            self.assertEqual(t["steps"][0]["kind"], "sync", f"{t['ref']} builds unsynced")
        nexts = NEXT_RE.findall(text)
        self.assertTrue(nexts, "the plan names no next command")
        for n in nexts:
            self.assertIn("--synced", n, f"an unsynced next on a tracker: {n}")
        done = [s for s in steps_of(plan) if s["kind"] == "status-done"]
        self.assertTrue(done)
        for s in done:
            self.assertEqual(s.get("store_write"), "done")
            self.assertEqual(s.get("then"), "mirror")

        # No step file of the run and no hook value carries the verb.
        for f in sorted(STEPS.glob("*.md")):
            self.assertIsNone(MARK_RE.search(f.read_text(encoding="utf-8")),
                              f"{f.name} names tickets.py mark")
        for e in tomllib.loads(WIRE_IN.read_text(encoding="utf-8"))["entry"]:
            value = e["value"] if isinstance(e["value"], str) else json.dumps(e["value"])
            self.assertIsNone(MARK_RE.search(value), f"{e['id']} names tickets.py mark")

    def test_repo_store_marks_done_and_commits(self):
        plan = self.plan()
        self.assertEqual(plan["store"], "repo")
        self.assertEqual(plan["sync"], [])
        done = [s for s in steps_of(plan) if s["kind"] == "status-done"]
        self.assertTrue(done)
        for s in done:
            self.assertRegex(s["command"], r"tickets\.py .*\bmark\b .* done$")
            self.assertIn("close-commit.py plans", s["commit"])
        for n in NEXT_RE.findall(json.dumps(plan)):
            self.assertNotIn("--synced", n)

    def test_store_rule_matches_tickets_py(self):
        """`store_name()` at the pin (tickets.py:780-793): the `[tickets] store` of
        `_bmad/custom/ticketing-store-config.toml`, `repo` when the file, the table or the key
        is absent, or the value is not a non-empty string."""
        cases = [
            (None, "repo"),
            ('[tickets]\nstore = "jira"\n', "jira"),
            ('[tickets]\nstore = ""\n', "repo"),
            ("[tickets]\nstore = 3\n", "repo"),
            ('tickets = "github"\n', "repo"),
            ('[other]\nstore = "linear"\n', "repo"),
            ('[tickets]\nfields = {}\n', "repo"),
        ]
        cfg = self.root / "_bmad" / "custom" / "ticketing-store-config.toml"
        for text, want in cases:
            with self.subTest(text=text):
                if text is None:
                    cfg.unlink(missing_ok=True)
                else:
                    self.write("_bmad/custom/ticketing-store-config.toml", text)
                self.assertEqual(self.plan()["store"], want)


class TestNoReviewPhase(Project):

    def test_execute_has_no_review_phase(self):
        """ADR-0017: review is bmad-build-auto's own, run `thorough`; the run adds no phase."""
        self.store("github")
        tracker = self.plan(status=self.with_checkpoints())
        self.write("_bmad/custom/ticketing-store-config.toml", '[tickets]\nstore = "repo"\n')
        repo = self.plan(status=self.with_checkpoints())
        kinds = {s["kind"] for p in (tracker, repo) for s in steps_of(p)}
        self.assertEqual(kinds, STEP_KINDS)
        for p in (tracker, repo):
            for s in steps_of(p):
                self.assertIn(s["kind"], STEP_KINDS)
                self.assertIsNone(REVIEW_RE.search(json.dumps(s)), f"a review phase: {s}")
                if s["kind"] in ("build", "checkpoint-plan"):
                    self.assertIn("bmad-build-auto", s["invocation"])
                    self.assertIn("thorough", s["invocation"].split())
        for f in sorted(STEPS.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            hit = re.search(r"bmad-code-review|bmad-review\b|l3io-arch-review", text)
            self.assertIsNone(hit, f"{f.name} invokes a review skill")

    def with_checkpoints(self):
        status = copy.deepcopy(self.status)
        for t in status["tickets"]:
            if t["ref"] == "1.2":
                t["plan_checkpoint"] = True
            if t["ref"] == "5.1":
                t["done_checkpoint"] = True
        return status


class TestCheckpointsAndGates(Project):

    def test_checkpoints_emitted(self):
        """Only an unattended run's orchestrator honours them (board.md:44)."""
        status = TestNoReviewPhase.with_checkpoints(self)
        plan = self.plan(status=status)
        tickets = {t["ref"]: t for w in plan["waves"] for e in w["epics"] for t in e["tickets"]}
        kinds = {ref: [s["kind"] for s in t["steps"]] for ref, t in tickets.items()}
        self.assertEqual(kinds["1.2"], ["checkpoint-plan", "build"])
        cp = tickets["1.2"]["steps"][0]
        self.assertIn("Halt after planning.", cp["invocation"])
        self.assertTrue(cp["ask"])
        self.assertEqual(kinds["5.1"], ["build", "checkpoint-done"])
        self.assertEqual(kinds["2.1"], ["build"])
        self.assertTrue(tickets["5.1"]["steps"][1]["ask"])

    def test_gates_pause_before_dependent_wave(self):
        plan = self.plan()
        self.assertEqual(plan["gates"], ["epic-cart"])
        wave_of = {e["slug"]: w["n"] for w in plan["waves"] for e in w["epics"]}
        paused = {slug: w["n"] for w in plan["waves"] for slug in w["pause_after"]}
        self.assertEqual(set(paused), {"epic-cart"})
        self.assertEqual(paused["epic-cart"], wave_of["epic-cart"])
        self.assertGreater(wave_of["epic-checkout"], paused["epic-cart"])
        # A dependency declared only in `[[epic]] after` orders the waves but pauses nothing.
        self.assertGreater(wave_of["epic-search"], wave_of["epic-platform"])
        self.assertNotIn("epic-platform", paused)

    def test_epic_closes_before_it_merges(self):
        plan = self.plan()
        for w in plan["waves"]:
            for e in w["epics"]:
                kinds = [s["kind"] for s in e["close"]]
                self.assertEqual(kinds[0], "close-epic")
                self.assertEqual(kinds[-1], "merge")
                close = e["close"][0]
                self.assertEqual(close["invocation"], f"bmad-retrospective -H {e['slug']}")
                self.assertTrue(close["retro_file"].endswith(
                    f"{e['slug']}/{e['slug']}-retrospective.md"))
                self.assertIn("close-commit.py retro", close["commit"])
                self.assertIn("close-commit.py state", e["close"][-1]["state_commit"])

    def test_built_ticket_is_not_rebuilt_but_is_marked_done(self):
        plan = self.plan()
        platform = next(e for w in plan["waves"] for e in w["epics"]
                        if e["slug"] == "epic-platform")
        self.assertEqual([t["ref"] for t in platform["tickets"]], ["1.2"])
        done = [s["ref"] for s in platform["close"] if s["kind"] == "status-done"]
        self.assertEqual(done, ["1.1", "1.2"])

    def test_max_parallel_batches_a_wave(self):
        sj = self.tmp / "status.json"
        sj.write_text(json.dumps(self.status), encoding="utf-8")
        r = subprocess.run([sys.executable, str(DISPATCH), "--project-root", str(self.root),
                            "--initiative", str(self.init), "--max-parallel", "1",
                            "--status-json", str(sj)], capture_output=True, text=True, env=ENV)
        self.assertEqual(r.returncode, 0, r.stderr)
        plan = json.loads(r.stdout)
        self.assertTrue(all(len(w["epics"]) == 1 for w in plan["waves"]))
        self.assertEqual([w["wave"] for w in plan["waves"]], [1, 1, 2, 3, 3])

    def test_single_epic_scope(self):
        epic = self.init / "tickets" / "epic-docs"
        plan = self.plan(scope=["--epic", str(epic)])
        self.assertEqual([e["slug"] for w in plan["waves"] for e in w["epics"]], ["epic-docs"])

    def test_parent_initiative_is_refused(self):
        r = self.plan(status=json.loads(PORTFOLIO.read_text(encoding="utf-8")), expect=2)
        self.assertIn("parent initiative", r.stderr)


class TestWorktrees(Project):

    def test_worktree_per_epic_when_bmad_is_committed(self):
        plan = self.plan()
        self.assertTrue(plan["parallel"]["worktrees"])
        roots = set()
        for w in plan["waves"]:
            for e in w["epics"]:
                self.assertEqual(e["branch"], f"l3io/{e['slug']}")
                self.assertTrue(e["worktree"])
                self.assertFalse(Path(e["worktree"]).is_relative_to(self.root),
                                 "a worktree inside the checkout is an untracked dir there")
                roots.add(e["worktree"])
                for t in e["tickets"]:
                    for s in t["steps"]:
                        if s["kind"] == "build":
                            self.assertIn(e["worktree"], s["invocation"])
        self.assertEqual(len(roots), 5)


class TestSerialWhenBmadIsNotCommitted(Project):
    """Task 4.7 Step 1, measured: a worktree of a project that does not commit `_bmad/` has
    no `_bmad/scripts/render_skill.py`, so `bmad-build-auto` cannot start in it."""

    commit_bmad = False

    def test_serial_without_worktrees(self):
        plan = self.plan()
        self.assertFalse(plan["parallel"]["worktrees"])
        self.assertIn("_bmad/", plan["parallel"]["reason"])
        self.assertEqual(plan["parallel"]["max"], 1)
        for w in plan["waves"]:
            self.assertEqual(len(w["epics"]), 1)
            for e in w["epics"]:
                self.assertIsNone(e["worktree"])
                self.assertEqual(e["branch"], f"l3io/{e['slug']}")
                self.assertEqual(e["root"], str(self.root))


class CloseCommit(Project):
    """`close-commit.py`, run from l3io-execute's scripts with pm_status beside it."""

    def setUp(self):
        super().setUp()
        self.write("_bmad/scripts/resolve_config.py", FAKE_RESOLVE_CONFIG)
        scripts = self.root / "_bmad" / "l3io-pm" / "scripts" / "pm_status"
        shutil.rmtree(scripts)
        shutil.copytree(PM_STATUS, scripts, ignore=shutil.ignore_patterns("__pycache__"))
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "pm_status")

    def porcelain(self, cwd=None):
        return self.git("status", "--porcelain", "--untracked-files=all", cwd=cwd)

    def close_commit(self, *argv, cwd=None, expect=0):
        r = subprocess.run([sys.executable, str(CLOSE_COMMIT), *argv], capture_output=True,
                           text=True, env=ENV, cwd=cwd or self.root)
        self.assertEqual(r.returncode, expect, f"{argv}\nstdout: {r.stdout}\nstderr: {r.stderr}")
        return r


class TestRetroCommitted(CloseCommit):

    def test_retrospective_committed_before_the_next_build(self):
        """bmad-retrospective commits nothing (retro-document.md:39), and epic-close leaves
        its document as v7 left it; an uncommitted document halts the next bmad-build-auto."""
        retro = self.write("_bmad-output/shop/tickets/epic-cart/epic-cart-retrospective.md",
                           "---\nepic: epic-cart\nverdict: accepted\nheadless: true\n---\n# R\n")
        mine = self.write("notes.txt", "the user's own work\n")
        r = self.close_commit("retro", "--project-root", str(self.root), "--retro-file",
                              str(retro))
        out = json.loads(r.stdout)
        self.assertEqual(out["verdict"], "accepted")
        self.assertEqual(out["epic"], "epic-cart")
        self.assertEqual(self.porcelain(), f"?? {mine.name}\n",
                         "only the retrospective is ours to commit")
        self.assertIn("epic-cart-retrospective.md",
                      self.git("show", "--name-only", "--format=%s", "HEAD"))
        self.assertTrue(self.git("log", "-1", "--format=%s").startswith("docs(l3io): "))

    def test_unknown_verdict_is_refused(self):
        retro = self.write("_bmad-output/shop/tickets/epic-cart/epic-cart-retrospective.md",
                           "---\nepic: epic-cart\nverdict: maybe\n---\n")
        r = self.close_commit("retro", "--project-root", str(self.root), "--retro-file",
                              str(retro), expect=2)
        self.assertIn("verdict", r.stderr)

    def test_status_done_plans_committed(self):
        plan = self.write("_bmad-output/shop/tickets/epic-cart/tickets/story-basket-plan.md",
                          "---\nticket: '1'\nstatus: built\n---\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "built")
        plan.write_text("---\nticket: '1'\nstatus: done\n---\n", encoding="utf-8")
        self.close_commit("plans", "--project-root", str(self.root), "--epic-dir",
                          str(plan.parent.parent))
        self.assertEqual(self.porcelain(), "")


class TestMainCheckoutStateCommitted(CloseCommit):
    """In a linked worktree, build-close commits only the plan sidecar: the project-wide
    state root is the main checkout's, outside the worktree. The run commits it there."""

    def test_main_checkout_left_clean(self):
        wt = self.tmp / "wt-cart"
        self.git("worktree", "add", "-q", "-b", "l3io/epic-cart", str(wt))
        tdir = wt / "_bmad-output" / "shop" / "tickets" / "epic-cart" / "tickets"
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / "tickets.toml").write_text('[[entry]]\nid = 1\ntype = "story"\n'
                                           'title = "Basket"\n', encoding="utf-8")
        plan = tdir / "story-basket-plan.md"
        plan.write_text("---\nticket: '1'\nstatus: built\n---\n", encoding="utf-8")
        self.git("add", "-A", cwd=wt)
        self.git("commit", "-q", "-m", "built", cwd=wt)
        main = wt / "_bmad" / "l3io-pm" / "scripts" / "pm_status" / "__main__.py"
        env = {**ENV, "CLAUDE_CODE_SESSION_ID": ""}
        for verb in (["build-open"], ["build-close", "--plan-file", str(plan),
                                      "--runtime", "other", "--man-hours", "1",
                                      "--hitl-hours", "0"]):
            r = subprocess.run([sys.executable, str(main), verb[0], "--project-root", str(wt),
                                "--agent", "bmad-build-auto", *verb[1:]], cwd=wt,
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.porcelain(cwd=wt), "", "the worktree is the build's to keep clean")
        self.assertIn("events.jsonl", self.porcelain(), "nothing for the run to commit")
        self.close_commit("state", "--project-root", str(self.root))
        self.assertEqual(self.porcelain(), "")
        self.assertEqual(self.git("log", "-1", "--format=%s").strip(), "chore(l3io): run state")

    def test_state_from_a_worktree_commits_nothing_there(self):
        wt = self.tmp / "wt-docs"
        self.git("worktree", "add", "-q", "-b", "l3io/epic-docs", str(wt))
        r = self.close_commit("state", "--project-root", str(wt), expect=2)
        self.assertIn("main checkout", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
