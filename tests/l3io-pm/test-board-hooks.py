#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18", "tomlkit>=0.13"]
# ///
"""
Tests for the waves and lanes l3io wires onto BMad v7's Sofia board, `bmad-agent-po`
(plan 2026-11-17-v7-phase-4-hooks.md, Task 4.5). Run with:
  uv run tests/l3io-pm/test-board-hooks.py

As in test-sofia-hooks.py, each case takes the commands out of the shipped
`assets/wire-in.toml`, fills the slots the prose asks the agent to fill, and runs them in a
git-initialised v7 project with l3io-pm's declared scripts installed where `bmad setup` puts
them. Sofia's own `tickets.py status` is stood in for by the JSON recorded from it at the pin
(tests/l3io-plan/fixtures/), since that is all the commands read from it.

The board hook runs after every board operation, between Sofia's commit and the next
`bmad-build-auto`, which refuses a dirty tree. So: the reconcile it runs after a `move`
commits what it changed, and the waves and lanes views write nothing at all.
"""
import importlib.util
import json
import shutil
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("sofia_hooks", _HERE / "test-sofia-hooks.py")
sh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sh)
bh = sh.bh

_REPO = Path(__file__).resolve().parents[2]
_PLAN_GRAPH = _REPO / "skills" / "l3io-pm" / "l3io-plan" / "scripts" / "plan-graph.py"
RECORDED = _REPO / "tests" / "l3io-plan" / "fixtures"
BOARD = ("l3io-board-waves", "l3io-menu-waves", "l3io-menu-lanes")
PROMPTS = {
    "l3io-waves": "Run the l3io-plan skill in waves mode on the initiative the user names, "
                  "or the active initiative.",
    "l3io-lanes": "Run the l3io-plan skill in lanes mode on the initiative the user names, "
                  "or the active initiative.",
}


class TestBoardEntries(unittest.TestCase):

    def test_entries_attach_where_the_plan_says(self):
        by_id = {e["id"]: e for e in bh.entries(*BOARD)}
        hook = by_id["l3io-board-waves"]
        self.assertEqual((hook["skill"], hook["kind"], hook["path"], hook.get("requires")),
                         ("bmad-agent-po", "scalar", "workflow.board_after", "l3io-pm"))
        for entry_id, code in (("l3io-menu-waves", "l3io-waves"),
                               ("l3io-menu-lanes", "l3io-lanes")):
            e = by_id[entry_id]
            self.assertEqual((e["skill"], e["kind"], e["path"], e.get("requires")),
                             ("bmad-agent-po", "keyed", "agent.menu", "l3io-pm"))
            self.assertEqual(e["value"]["code"], code)
            self.assertEqual(e["value"]["prompt"], PROMPTS[code])
            self.assertNotIn("skill", e["value"], "a missing skill is offered from Sofia's source")

    def test_board_hook_reconciles_before_it_renders_and_never_marks(self):
        value = bh.entries("l3io-board-waves")[0]["value"]
        self.assertLess(value.index("sidecar-reconcile"), value.index("plan-graph.py waves"))
        self.assertLess(value.index("plan-graph.py waves"), value.index("plan-graph.py lanes"))
        self.assertNotRegex(value, r"tickets\.py\S*\s+mark\b")
        self.assertNotIn("{skill-root}", value)


class TestBoardHook(sh.SofiaProject):

    def setUp(self):
        super().setUp()
        shutil.copy2(_PLAN_GRAPH, self.root / "_bmad" / "l3io-pm" / "scripts" / "plan-graph.py")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "installed")

    def commands(self, status="shop", move=None):
        fill = {"{project-root}": str(self.root),
                "<initiative folder>": str(self.initiative),
                "<status command>": f"cat {RECORDED / f'v7-status-{status}.json'}",
                "<the move's JSON output>": json.dumps(move or {})}
        return sh.commands_of(bh.entries("l3io-board-waves")[0], fill)

    def test_waves_and_lanes_render_and_write_nothing(self):
        _reconcile, waves, lanes = self.commands()
        r = self.sh(waves)
        out = json.loads(r.stdout)
        self.assertEqual([w["epics"] for w in out["waves"]],
                         [["epic-platform", "epic-docs"], ["epic-cart"],
                          ["epic-search", "epic-checkout"]])
        self.assertEqual(out["gates"], ["epic-cart"])
        self.assertEqual(self.porcelain(), "", "the waves view wrote into the tree")
        r = self.sh(lanes)
        self.assertEqual(json.loads(r.stdout)["lanes"], [], "lanes are off: no lane is set")
        self.assertEqual(self.porcelain(), "", "the lanes view wrote into the tree")

    def test_lanes_render_from_the_initiative_sidecar(self):
        self.write(str((self.initiative / "tickets" / "l3io.toml").relative_to(self.root)),
                   "[epic.epic-platform]\nlane = 1\n\n[epic.epic-search]\nlane = 2\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "chore(l3io): lanes")
        *_rest, lanes = self.commands()
        out = json.loads(self.sh(lanes).stdout)
        self.assertEqual([x["lane"] for x in out["lanes"]], [1, 2])
        self.assertEqual(out["crossings"][0]["from"], "epic-search")
        self.assertEqual(self.porcelain(), "")

    def test_waves_on_a_parent_initiative(self):
        _reconcile, waves, _lanes = self.commands(status="portfolio")
        out = json.loads(self.sh(waves).stdout)
        self.assertEqual(out["scope"], "parent")
        self.assertEqual(out["gates"], ["shop", "ops", "growth"])

    def test_a_move_is_reconciled_on_a_clean_tree(self):
        estimate, dest, move = self.planted_move()
        reconcile, _waves, _lanes = self.commands(move=move)
        self.sh(reconcile)
        self.assertEqual(self.porcelain(), "", "the board hook left the tree dirty")
        self.assertEqual(self.last_subject(), "chore(l3io): reconcile sidecars")
        self.assertEqual(self.side(dest)["entry"]["4"], estimate)
        self.assertTrue((dest / "story-basket-plan.l3io.toml").exists())


if __name__ == "__main__":
    unittest.main()
