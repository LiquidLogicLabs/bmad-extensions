#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18", "tomlkit>=0.13"]
# ///
"""
Tests for the estimation hooks l3io wires into BMad v7's Sofia, `bmad-agent-po`
(plan 2026-11-17-v7-phase-4-hooks.md, Task 4.3). Run with:
  uv run tests/l3io-pm/test-sofia-hooks.py

As in test-build-hooks.py, each case reads the hook values out of the shipped
`assets/wire-in.toml`, fills the slots the prose asks the agent to fill, and runs the fenced
commands in a git-initialised v7 project with l3io-pm's declared `pm_status` installed where
`bmad setup` puts it. The property that carries the weight: after every hook the tree is
CLEAN, because Sofia's hooks run between her own commit and the next `bmad-build-auto`, which
refuses a dirty tree (step-01-clarify-and-route.md:60).
"""
import importlib.util
import json
import re
import shutil
import tomllib
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("build_hooks", _HERE / "test-build-hooks.py")
bh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bh)

FENCE_RE = bh.FENCE_RE
SLOT_RE = bh.SLOT_RE
SOFIA = ("l3io-estimate-on-slice", "l3io-estimate-on-refine", "l3io-reestimate-on-replan",
         "l3io-menu-estimate")
MENU_PROMPT = ("Run the l3io-plan skill in estimate mode on the folder the user names, "
               "or the active initiative.")


def commands_of(entry, fill):
    """Every fenced command in a hook value, slots filled; an unfilled slot fails."""
    out = []
    for block in FENCE_RE.findall(entry["value"]):
        cmd = block.strip()
        for k, v in fill.items():
            cmd = cmd.replace(k, v)
        left = SLOT_RE.findall(cmd) + re.findall(r"\{[a-z_-]+\}", cmd)
        assert not left, f"{entry['id']}: unfilled slot(s) {left} in {cmd}"
        out.append(cmd)
    return out


class SofiaProject(bh.Project):

    def setUp(self):
        super().setUp()
        self.initiative = self.root / "_bmad-output" / "initiative-shop"
        self.epic = self.initiative / "tickets" / "epic-cart"

    def side(self, tdir=None):
        p = (tdir or self.tdir) / "l3io.toml"
        return tomllib.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def last_subject(self):
        return self.git("log", "-1", "--format=%s").strip()

    def planted_move(self):
        """Entry 1 of epic-cart estimated, built (its plan sidecar committed), then moved to
        epic-pricing as entry 4 the way `tickets.py move` leaves the tree, committed as Sofia
        does. Returns (the estimate, the destination tickets folder, move's JSON)."""
        (slice_cmd,) = commands_of(bh.entries("l3io-estimate-on-slice")[0],
                                   {"{project-root}": str(self.root),
                                    "<epic folder>": str(self.epic)})
        self.sh(f"{slice_cmd} --class 1=standard")
        estimate = self.side()["entry"]["1"]
        # The build's own sidecar beside the plan, committed as build-close commits it.
        (self.tdir / "story-basket-plan.l3io.toml").write_text(
            "fix_iterations = 0\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "chore(l3io): actuals 1")
        pricing = self.initiative / "tickets" / "epic-pricing"
        self.write(str((pricing / "epic-pricing.md").relative_to(self.root)),
                   "---\ntype: epic\nafter: []\n---\n# Pricing\n")
        dest = pricing / "tickets"
        self.write(str((dest / "tickets.toml").relative_to(self.root)),
                   'next_id = 5\n\n[[entry]]\nid = 4\ntype = "story"\ntitle = "Basket"\n')
        self.write(str((self.tdir / "tickets.toml").relative_to(self.root)), "next_id = 2\n")
        for name in ("story-basket.md", "story-basket-plan.md"):
            shutil.move(str(self.tdir / name), str(dest / name))
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "board: move 1 to epic-pricing")
        move = {"from": "epic-cart", "to": "epic-pricing", "old_id": 1, "id": 4, "ref": "2.4",
                "file": "story-basket.md", "plan": "story-basket-plan.md",
                "next_id": {"epic-pricing": 5}, "rewritten": []}
        return estimate, dest, move


class TestSofiaHooks(SofiaProject):

    def test_hook_values_name_only_the_declared_script(self):
        for e in bh.entries(*SOFIA):
            self.assertEqual(e.get("requires"), "l3io-pm", e["id"])
            self.assertEqual(e["skill"], "bmad-agent-po", e["id"])
            text = json.dumps(e["value"])
            self.assertNotIn("{skill-root}", text, e["id"])
            self.assertNotRegex(text, r"tickets\.py\S*\s+mark\b", e["id"])
        for e in bh.entries(*SOFIA[:3]):
            self.assertEqual(e["kind"], "scalar")
            for cmd in FENCE_RE.findall(e["value"]):
                self.assertTrue(cmd.startswith(
                    "uv run {project-root}/_bmad/l3io-pm/scripts/pm_status/__main__.py "), cmd)
        menu = bh.entries("l3io-menu-estimate")[0]
        self.assertEqual((menu["kind"], menu["path"]), ("keyed", "agent.menu"))
        self.assertEqual(menu["value"]["code"], "l3io-estimate")
        self.assertEqual(menu["value"]["prompt"], MENU_PROMPT)
        self.assertNotIn("skill", menu["value"], "a missing skill is offered from Sofia's source")
        replan = bh.entries("l3io-reestimate-on-replan")[0]["value"]
        self.assertLess(replan.index("sidecar-reconcile"), replan.index("estimate-entries"),
                        "replan must repoint the sidecars before it re-estimates")

    def test_slice_hook_asks_for_classes_then_estimates_on_a_clean_tree(self):
        (cmd,) = commands_of(bh.entries("l3io-estimate-on-slice")[0],
                             {"{project-root}": str(self.root), "<epic folder>": str(self.epic)})
        r = self.sh(cmd, expect=2)
        self.assertIn("1 (Basket)", r.stderr)
        self.assertEqual(self.porcelain(), "", "a refused run left the tree dirty")
        self.assertEqual(self.side(), {})
        self.sh(f"{cmd} --class 1=standard")
        self.assertEqual(self.side()["entry"]["1"]["class"], "standard")
        self.assertIn("estimate", self.side()["epic"])
        self.assertEqual(self.porcelain(), "",
                         "the slice hook left the tree dirty; the next build would HALT")
        self.assertEqual(self.last_subject(), "chore(l3io): estimates epic-cart")

    def test_refine_hook_reestimates_its_entry(self):
        (slice_cmd,) = commands_of(bh.entries("l3io-estimate-on-slice")[0],
                                   {"{project-root}": str(self.root),
                                    "<epic folder>": str(self.epic)})
        self.sh(f"{slice_cmd} --class 1=standard")
        first = self.side()["entry"]["1"]["estimated_at"]
        (cmd,) = commands_of(bh.entries("l3io-estimate-on-refine")[0],
                             {"{project-root}": str(self.root), "<epic folder>": str(self.epic),
                              "<id>": "1"})
        r = self.sh(f"{cmd} --class 1=complex")
        self.assertEqual([json.loads(x).get("action") for x in r.stdout.splitlines()
                          if '"entry"' in x], ["reclassified"])
        self.assertEqual(self.side()["entry"]["1"]["class"], "complex")
        self.assertGreaterEqual(self.side()["entry"]["1"]["estimated_at"], first)
        self.assertEqual(self.porcelain(), "")

    def test_replan_hook_follows_a_move_on_a_clean_tree(self):
        estimate, dest, move = self.planted_move()
        pricing = dest.parent

        replan = bh.entries("l3io-reestimate-on-replan")[0]
        reconcile, reestimate = commands_of(replan, {
            "{project-root}": str(self.root), "<initiative folder>": str(self.initiative),
            "<epic folder>": "EPIC"})
        self.sh(f"{reconcile} --moved-json '{json.dumps(move)}'")
        self.assertEqual(self.porcelain(), "", "sidecar-reconcile left the tree dirty")
        self.assertEqual(self.last_subject(), "chore(l3io): reconcile sidecars")
        for folder in (pricing, self.epic):
            self.sh(reestimate.replace("EPIC", str(folder)))
        self.assertEqual(self.porcelain(), "", "the replan hook left the tree dirty")
        self.assertEqual(self.side(dest)["entry"]["4"], estimate)
        self.assertNotIn("1", self.side().get("entry", {}))
        self.assertNotIn("estimate", self.side().get("epic", {}),
                         "an epic with no entries left kept its old roll-up")
        self.assertTrue((dest / "story-basket-plan.l3io.toml").exists())
        self.assertFalse((self.tdir / "story-basket-plan.l3io.toml").exists())
        self.assertEqual(self.git("ls-files", str(self.tdir / "story-basket-plan.l3io.toml")),
                         "", "the moved sidecar's old path is still tracked")


if __name__ == "__main__":
    unittest.main()
