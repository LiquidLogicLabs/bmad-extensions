#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18", "tomlkit>=0.13"]
# ///
"""
Tests for the readiness checks l3io wires into BMad v7's Sofia, `bmad-agent-po`
(plan 2026-11-17-v7-phase-4-hooks.md, Task 4.4). Run with:
  uv run tests/l3io-pm/test-readiness-checks.py

Our checks are entries in Sofia's `workflow.checks.ticket` and `workflow.checks.set` lists,
which render inside the sections her validate subagents run (validate-checks.md:30-47), plus a
`persistent_facts` file so REFINE writes to the dimensions the check enforces. As in
test-sofia-hooks.py, each case takes the commands out of the shipped `assets/wire-in.toml`,
fills the slots the prose asks the agent to fill, and runs them in a git-initialised v7 project
with l3io-pm's declared scripts installed where `bmad setup` puts them.

Two properties carry the weight:
  * every path a hook value names is one `bmad setup` installs: under
    `{project-root}/_bmad/l3io-pm/scripts/`, and declared in l3io-execute's bmod.toml. In a hook,
    `{skill-root}` is Sofia's root, so nothing else is reachable from a static string;
  * a check only reads. A validate run sits between Sofia's commit and the next
    `bmad-build-auto`, which refuses a dirty tree, so the tree is unchanged afterwards.
"""
import importlib.util
import json
import re
import shutil
import tomllib
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("sofia_hooks", _HERE / "test-sofia-hooks.py")
sh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sh)
bh = sh.bh

_REPO = Path(__file__).resolve().parents[2]
_SHARED = _REPO / "skills" / "_shared"
_EXECUTE = _REPO / "skills" / "l3io-pm" / "l3io-execute"
READINESS = ("l3io-check-technical-ac", "l3io-check-estimate-present", "l3io-fact-ac-dimensions")
FACT = "file:{project-root}/_bmad/l3io-pm/scripts/facts/ac-dimensions.md"
INSTALLED = "{project-root}/_bmad/l3io-pm/scripts/"
BMAD_PATH_RE = re.compile(r"_bmad/[^\s`'\")]+")

DIMS = ("Interface contracts", "Error and edge case handling", "Observability requirements",
        "Security considerations", "Testability approach", "Existing-library check")


def declared():
    return tomllib.loads((_EXECUTE / "bmod.toml").read_text(encoding="utf-8"))["skill"]["scripts"]


def leaf(epic_rel, technical=True):
    """A refined v7 story whose every dimension points at its epic's own file."""
    front = ('---\nid: 1\ntype: story\ntitle: "Basket"\nparent: epic-cart\nrefined: true\n'
             "hitl: false\nrisk: low\n---\n\n# Basket\n\n## Description\n\nA basket.\n\n")
    business = ("## Business acceptance criteria\n\n### Outcome\n\nShoppers keep a basket.\n"
                f"Spec: {epic_rel}#outcome\n\n### Non-goals\n\nNo wish list.\n\n")
    if not technical:
        return front + business + "## Requirements\n\nVerify: reload keeps the basket.\n"
    tac = "## Technical acceptance criteria\n\n" + "".join(
        f"### {d}\n\nContent for {d}.\nSpec: {epic_rel}#outcome\n\n" for d in DIMS)
    return front + business + tac


class TestReadinessEntries(unittest.TestCase):

    def test_entries_attach_where_the_plan_says(self):
        by_id = {e["id"]: e for e in bh.entries(*READINESS)}
        want = {"l3io-check-technical-ac": ("list", "workflow.checks.ticket"),
                "l3io-check-estimate-present": ("list", "workflow.checks.set"),
                "l3io-fact-ac-dimensions": ("list", "agent.persistent_facts")}
        for entry_id, (kind, path) in want.items():
            e = by_id[entry_id]
            self.assertEqual((e["skill"], e["kind"], e["path"], e.get("requires")),
                             ("bmad-agent-po", kind, path, "l3io-pm"), entry_id)
        self.assertEqual(by_id["l3io-fact-ac-dimensions"]["value"], FACT)
        data = tomllib.loads(bh._WIRE_IN.read_text(encoding="utf-8"))
        self.assertNotIn("workflow.validate_after", {e["path"] for e in data["entry"]},
                         "readiness attaches to the checks lists, never validate_after")

    def test_checks_text_names_only_declared_paths(self):
        decl = set(declared())
        data = tomllib.loads(bh._WIRE_IN.read_text(encoding="utf-8"))
        ours = [e for e in data["entry"] if e.get("requires") == "l3io-pm"]
        self.assertTrue({e["id"] for e in ours} >= set(READINESS))
        for e in ours:
            text = json.dumps(e["value"])
            self.assertNotIn("{skill-root}", text, e["id"])
            paths = BMAD_PATH_RE.findall(text)
            if e["id"] in READINESS:
                self.assertTrue(paths, f"{e['id']} names no installed path")
            for p in paths:
                self.assertTrue(p.startswith("_bmad/l3io-pm/scripts/"), f"{e['id']}: {p}")
                rel = "scripts/" + p.removeprefix("_bmad/l3io-pm/scripts/")
                self.assertIn(rel, decl, f"{e['id']} names {p}, which l3io-execute does not "
                                         f"declare, so bmad setup never installs it")
        for e in bh.entries(*READINESS[:2]):
            for cmd in sh.FENCE_RE.findall(e["value"]):
                self.assertTrue(cmd.startswith("uv run " + INSTALLED), cmd)
            self.assertNotRegex(e["value"], r"tickets\.py\S*\s+mark\b", e["id"])

    def test_the_fact_file_is_the_canonical_reference(self):
        self.assertEqual((_EXECUTE / "scripts" / "facts" / "ac-dimensions.md").read_bytes(),
                         (_SHARED / "ac-dimensions.md").read_bytes())


class TestReadinessChecks(sh.SofiaProject):

    def setUp(self):
        super().setUp()
        scripts = self.root / "_bmad" / "l3io-pm" / "scripts"
        shutil.copy2(_SHARED / "spec-align.py", scripts / "spec-align.py")
        (scripts / "facts").mkdir()
        shutil.copy2(_SHARED / "ac-dimensions.md", scripts / "facts" / "ac-dimensions.md")
        self.epic_file = self.epic / "epic-cart.md"
        self.write(str(self.epic_file.relative_to(self.root)),
                   "---\ntype: epic\nafter: []\n---\n# Cart\n\n## Outcome\n\nShoppers keep a "
                   "basket.\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "installed")
        self.leaf = self.tdir / "story-basket.md"

    def commit_leaf(self, text):
        self.write(str(self.leaf.relative_to(self.root)), text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "refine 1")

    def ticket_check(self):
        (cmd,) = sh.commands_of(bh.entries("l3io-check-technical-ac")[0], {
            "{project-root}": str(self.root), "<leaf file>": str(self.leaf),
            "<work type>": "CODE"})
        return cmd

    def set_check(self):
        (cmd,) = sh.commands_of(bh.entries("l3io-check-estimate-present")[0], {
            "{project-root}": str(self.root), "<epic folder>": str(self.epic)})
        return cmd

    def test_ticket_check_passes_a_ready_leaf_and_writes_nothing(self):
        self.commit_leaf(leaf(str(self.epic_file.relative_to(self.root))))
        r = self.sh(self.ticket_check())
        self.assertIn("OK check-pointers", r.stdout)
        self.assertEqual(self.porcelain(), "", "the ticket check wrote into the tree")

    def test_ticket_check_finds_a_thin_leaf_and_writes_nothing(self):
        self.commit_leaf(leaf(str(self.epic_file.relative_to(self.root)), technical=False))
        r = self.sh(self.ticket_check(), expect=2)
        self.assertIn("story-basket.md", r.stderr)
        self.assertIn("Technical acceptance criteria", r.stderr)
        self.assertEqual(self.porcelain(), "", "the ticket check wrote into the tree")

    def test_ticket_check_finds_a_dangling_pointer(self):
        rel = str(self.epic_file.relative_to(self.root))
        self.commit_leaf(leaf(rel).replace(f"{rel}#outcome", f"{rel}#gone", 1))
        r = self.sh(self.ticket_check(), expect=2)
        self.assertIn("has no anchor #gone", r.stderr)

    def test_set_check_names_unestimated_entries_and_writes_nothing(self):
        r = self.sh(self.set_check(), expect=1)
        self.assertIn("1 (Basket)", r.stdout)
        self.assertEqual(self.porcelain(), "", "the set check wrote into the tree")
        self.assertFalse((self.tdir / "l3io.toml").exists())
        (estimate,) = sh.commands_of(bh.entries("l3io-estimate-on-slice")[0], {
            "{project-root}": str(self.root), "<epic folder>": str(self.epic)})
        self.sh(f"{estimate} --class 1=standard")
        r = self.sh(self.set_check())
        self.assertIn("OK", r.stdout)
        self.assertEqual(self.porcelain(), "", "the set check wrote into the tree")

    def test_set_check_counts_a_hand_set_estimate(self):
        self.write(str((self.tdir / "tickets.toml").relative_to(self.root)),
                   '[[entry]]\nid = 1\ntype = "story"\ntitle = "Basket"\nestimate = "2d"\n')
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "hand estimate")
        self.sh(self.set_check())
        self.assertEqual(self.porcelain(), "")


if __name__ == "__main__":
    unittest.main()
