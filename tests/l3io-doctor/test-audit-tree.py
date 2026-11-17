#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Tests for audit-tree.py: the backlog integrity audit re-expressed over BMad v7's tree.

Run with: uv run tests/l3io-doctor/test-audit-tree.py
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "l3io-util" / "l3io-doctor" / "scripts" / "audit-tree.py"
_spec = importlib.util.spec_from_file_location("audit_tree", SCRIPT)
audit_tree = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit_tree)

# The 3.x findings that have no meaning on v7's tree, and why. A finding listed here must
# never be emitted; one missing from both this table and the fixtures below fails the suite.
NO_V7_MEANING = {
    "1a": "two issue files (open and resolved) that could both hold one key; a v7 ticket is "
          "one leaf, and its state lives in the one plan beside it",
    "1e": "the stored per-epic `next:` allocator; v7 derives `next_id` from the tree "
          "(`tickets.py status`), so there is no stored counter to corrupt",
    "1g": "an item scheduled to an archived story; v7 has no archive placement, a done "
          "ticket stays where it is",
    "1j": "a resolution citing a story that is no longer done; a v7 ticket's resolution is "
          "its plan's status, so there is no second record to disagree with it",
}


def leaf(kind="bug", ticket_id=None, title="x", parent="", severity="P2", extra=""):
    lines = ["---"]
    if ticket_id is not None:
        lines.append(f"id: {ticket_id}")
    if kind is not None:
        lines.append(f"type: {kind}")
    lines += [f'title: "{title}"', f"parent: {parent}", "after: []"]
    if severity is not None:
        lines.append(f"severity: {severity}")
    lines += ["---", "", f"# {title}", "", extra, ""]
    return "\n".join(lines)


def plan(ticket, status="in-progress"):
    return f"---\ntitle: 'x'\nticket: '{ticket}'\nstatus: '{status}'\n---\n\n# x\n"


class Tree(unittest.TestCase):
    """A project with one initiative, one epic `epic-cart` (entries 1 and 2), and a backlog."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.out = self.root / "out"
        self.init = self.out / "initiative-shop"
        (self.init / "tickets").mkdir(parents=True)
        (self.init / "initiative-shop.md").write_text("---\ntype: initiative\n---\n# Shop\n")
        (self.init / "tickets" / "tickets.toml").write_text(
            '[[epic]]\nid = 1\nslug = "epic-cart"\ntitle = "Cart"\n')
        self.epic = self.init / "tickets" / "epic-cart"
        (self.epic / "tickets").mkdir(parents=True)
        (self.epic / "epic-cart.md").write_text("---\ntype: epic\nafter: []\n---\n# Cart\n")
        (self.epic / "tickets" / "tickets.toml").write_text(
            '[[entry]]\nid = 1\ntype = "story"\ntitle = "Scaffold"\n\n'
            '[[entry]]\nid = 2\ntype = "story"\ntitle = "Discounts"\n')
        self.backlog = self.out / "backlog"
        self.backlog.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def run_audit(self, *extra):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = audit_tree.main(["--project-root", str(self.root), "--output-folder", "out",
                                    "--format", "json", *extra])
        return code, json.loads(buf.getvalue())

    def ids(self):
        code, out = self.run_audit()
        return code, {f["id"] for f in out["findings"]}, out

    def tk(self, name, text, folder=None):
        (folder or self.epic / "tickets").joinpath(name).write_text(text, encoding="utf-8")


class TestFindings(Tree):
    def test_a_clean_tree_has_no_findings(self):
        self.tk("story-scaffold.md", leaf("story", 1, "Scaffold", "epic-cart", None))
        self.tk("story-scaffold-plan.md", plan(1, "done"))
        self.tk("bug-total-wrong.md", leaf(), self.backlog)
        code, ids, out = self.ids()
        self.assertEqual((code, ids), (0, set()), out)

    def test_audit_tree_findings_1a_to_1l(self):
        """One fixture per finding that has a v7 meaning; the rest are in NO_V7_MEANING."""
        cases = {
            # an estimate keyed to an entry no tickets.toml holds (a move nobody reconciled)
            "1b": lambda: self.tk("l3io.toml", '[entry.9]\nclass = "standard"\n'),
            # a backlog ticket built but never closed
            "1c": lambda: (self.tk("bug-a.md", leaf(title="a"), self.backlog),
                           self.tk("bug-a-plan.md", plan("bug-a", "built"), self.backlog)),
            # a backlog ticket naming an epic as its parent, still sitting in backlog/
            "1d": lambda: self.tk("bug-b.md", leaf(title="b", parent="epic-cart"), self.backlog),
            # a plan status v7 does not know
            "1f": lambda: self.tk("story-scaffold-plan.md", plan(1, "deferred")),
            # two plans joining one ticket
            "1h": lambda: (self.tk("story-scaffold-plan.md", plan(1)),
                           self.tk("story-other-plan.md", plan(1))),
            # two leaves in one folder carrying one id
            "1i": lambda: (self.tk("story-scaffold.md", leaf("story", 1, "Scaffold", "", None)),
                           self.tk("story-again.md", leaf("story", 1, "Again", "", None))),
            # a backlog leaf of no known type, or a bug with no valid severity
            "1k": lambda: self.tk("bug-c.md", leaf(title="c", severity="Medium"), self.backlog),
            # a plan sidecar whose plan is gone, with exactly one same-named plan elsewhere
            "1l": lambda: (self.tk("story-moved-plan.l3io.toml", "[actual]\n", self.backlog),
                           self.tk("story-moved-plan.md", plan(2))),
        }
        self.assertEqual(sorted(set(cases) | set(NO_V7_MEANING)),
                         [f"1{c}" for c in "abcdefghijkl"],
                         "every finding 1a-1l has a fixture or a no-meaning entry")
        self.assertEqual(set(cases) & set(NO_V7_MEANING), set())
        for fid, plant in cases.items():
            with self.subTest(finding=fid):
                self.tearDown()
                self.setUp()
                plant()
                code, ids, out = self.ids()
                self.assertEqual(code, 4, out)
                self.assertEqual(ids, {fid}, out)
                for f in out["findings"]:
                    self.assertTrue(f["repair"], f)
                    self.assertTrue(f["path"], f)

    def test_no_finding_without_a_v7_meaning_is_ever_emitted(self):
        self.assertEqual(set(audit_tree.FINDINGS) & set(NO_V7_MEANING), set())
        self.assertEqual(sorted(set(audit_tree.FINDINGS) | set(NO_V7_MEANING)),
                         [f"1{c}" for c in "abcdefghijkl"])

    def test_1l_without_a_unique_heir_is_report_only(self):
        self.tk("story-gone-plan.l3io.toml", "[actual]\n")
        code, out = self.run_audit()
        (f,) = out["findings"]
        self.assertEqual((code, f["id"]), (4, "1l"))
        self.assertTrue(f["repair"].startswith("report only"), f)

    def test_1l_with_a_unique_heir_proposes_sidecar_reconcile(self):
        self.tk("story-moved-plan.l3io.toml", "[actual]\n", self.backlog)
        self.tk("story-moved-plan.md", plan(2))
        _, out = self.run_audit()
        self.assertIn("sidecar-reconcile", out["findings"][0]["repair"])

    def test_fixes_are_proposals_for_sofia(self):
        self.tk("bug-b.md", leaf(title="b", parent="epic-cart"), self.backlog)
        _, out = self.run_audit()
        self.assertIn("move", out["findings"][0]["repair"])
        self.assertIn("Sofia", out["findings"][0]["repair"])

    def test_no_tree_is_a_clean_exit(self):
        code, out = Tree.run_audit(self, "--output-folder", "nowhere")
        self.assertEqual((code, out["findings"]), (0, []))


class TestMarkers(Tree):
    def test_marker_evidence_on_a_backlog_bug(self):
        src = self.root / "src"
        src.mkdir()
        (src / "a.py").write_text("x = 1  # bmad-defer: linear scan. upgrade: index.\n")
        (src / "b.py").write_text("y = 2\n")
        ref = "References:\n- code-marker ({}:1)\n"
        self.tk("bug-open.md", leaf(title="linear scan", extra=ref.format("src/a.py")),
                self.backlog)
        self.tk("bug-fixed.md", leaf(title="linear scan", extra=ref.format("src/b.py")),
                self.backlog)
        self.tk("bug-gone.md", leaf(title="linear scan", extra=ref.format("src/c.py")),
                self.backlog)
        _, out = self.run_audit()
        got = {m["ticket"]: m["verdict"] for m in out["markers"]}
        self.assertEqual(got, {"bug-open": "open", "bug-fixed": "fixed-candidate",
                               "bug-gone": "obsolete-candidate"})


class TestWritesNothing(Tree):
    def _digest(self):
        h = hashlib.sha256()
        for dirpath, dirnames, filenames in sorted(os.walk(self.root)):
            dirnames.sort()
            h.update(dirpath.encode())
            for n in sorted(filenames):
                p = Path(dirpath, n)
                h.update(n.encode())
                h.update(p.read_bytes())
        return h.hexdigest()

    def test_audit_tree_writes_nothing(self):
        self.tk("l3io.toml", '[entry.9]\nclass = "standard"\n')
        self.tk("bug-b.md", leaf(title="b", parent="epic-cart"), self.backlog)
        self.tk("story-gone-plan.l3io.toml", "[actual]\n")
        before = self._digest()
        code, out = self.run_audit()
        self.assertEqual(code, 4)
        self.assertGreaterEqual(len(out["findings"]), 3)
        self.assertEqual(self._digest(), before)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            audit_tree.main(["--project-root", str(self.root), "--output-folder", "out"])
        self.assertEqual(self._digest(), before)


if __name__ == "__main__":
    unittest.main()
