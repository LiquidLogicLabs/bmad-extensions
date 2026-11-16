#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["tomlkit>=0.13"]
# ///
"""
Tests for wire-in.py. Run with:
  uv run tests/l3io-doctor/test-wire-in.py

Every case builds a project in a temp dir and drives the real script through subprocess,
so the exit code and the bytes on disk are the ones `/l3io-doctor wire` produces. The team
files are written as raw text, never through tomlkit, so a byte comparison measures what
the script did rather than what a serializer would have done. Each fixture first asserts
that what it planted is really there, so a case cannot pass over a fixture that silently
held nothing.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "skills" / "l3io-util" / "l3io-doctor" / "scripts" / "wire-in.py"
_ASSET = _REPO / "skills" / "l3io-util" / "l3io-doctor" / "assets" / "wire-in.toml"

# A team file with comments, a trailing comment, keys in no particular order, a hand-added
# lens, and a scalar hook sitting between two tables.
TEAM_REVIEW = """\
# Team overrides for bmad-review. Hand-edited; keep the comments.
[workflow]
reader_type = "engineers"   # not the default
# guidance before facts, on purpose
review_guidance = ["Prefer small diffs."]

[[workflow.lenses]]
# our in-house lens
instruction = "Check the licence headers."
code = "licence-headers"
name = "Licence headers"
"""

ENTRIES = """\
[[entry]]
id = "lens"
skill = "bmad-review"
kind = "keyed"
path = "workflow.lenses"
[entry.value]
code = "l3io-test-lens"
name = "l3io test lens"
instruction = "Look."

[[entry]]
id = "fact"
skill = "bmad-review"
kind = "list"
path = "workflow.persistent_facts"
value = "file:{project-root}/docs/l3io-facts.md"

[[entry]]
id = "hook"
skill = "bmad-build"
kind = "scalar"
path = "workflow.on_complete"
value = "Run the l3io capture."
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "_bmad" / "custom").mkdir(parents=True)
        self.out = self.root / "_bmad-output"
        self.entries = self.root / "entries.toml"
        self.entries.write_text(ENTRIES, encoding="utf-8")

    def team(self, skill, text):
        path = self.root / "_bmad" / "custom" / f"{skill}.toml"
        path.write_bytes(text.encode("utf-8"))
        self.assertEqual(path.read_bytes(), text.encode("utf-8"))
        return path

    def run_cli(self, cmd, *extra, entries=True):
        argv = [sys.executable, str(_SCRIPT), cmd, "--project-root", str(self.root),
                "--output-folder", str(self.out)]
        if cmd == "wire" and entries:
            argv += ["--entries", str(self.entries)]
        p = subprocess.run(argv + list(extra), capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr

    @property
    def ledger(self):
        return self.out / "l3io" / "wire-in.json"

    def snapshot(self):
        custom = self.root / "_bmad" / "custom"
        return {p.name: p.read_bytes() for p in sorted(custom.iterdir())}


class TestWireIn(Base):
    def test_wire_in_is_idempotent(self):
        review = self.team("bmad-review", TEAM_REVIEW)
        code, out, err = self.run_cli("wire")
        self.assertEqual(code, 0, out + err)
        first, ledger = self.snapshot(), self.ledger.read_bytes()
        self.assertIn("l3io-test-lens", review.read_text())
        self.assertIn("Run the l3io capture.", (review.parent / "bmad-build.toml").read_text())

        code, out, err = self.run_cli("wire")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.snapshot(), first)
        self.assertEqual(self.ledger.read_bytes(), ledger)
        self.assertEqual(review.read_text().count("l3io-test-lens"), 1)
        self.assertNotIn("applied", out)

    def test_unwire_restores_bytes(self):
        self.team("bmad-review", TEAM_REVIEW)
        build = self.team("bmad-build", '# build overrides\n[workflow]\non_complete = ""\n')
        before = self.snapshot()
        code, out, err = self.run_cli("wire")
        self.assertEqual(code, 0, out + err)
        self.assertNotEqual(self.snapshot(), before, "wire changed nothing to undo")
        self.assertIn('on_complete = "Run the l3io capture."', build.read_text())

        code, out, err = self.run_cli("unwire")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.ledger.exists())

    def test_wire_in_refuses_nonempty_string_hook(self):
        build = self.team("bmad-build", '[workflow]\non_complete = "Run the team script."\n')
        before = build.read_bytes()
        code, out, err = self.run_cli("wire")
        self.assertEqual(code, 3, out + err)
        line = next(x for x in out.splitlines() if x.startswith("refused"))
        for needle in ("_bmad/custom/bmad-build.toml", "workflow.on_complete",
                       "Run the team script.", "Run the l3io capture."):
            self.assertIn(needle, line)
        self.assertEqual(build.read_bytes(), before)
        ledger = json.loads(self.ledger.read_text())
        self.assertNotIn("_bmad/custom/bmad-build.toml", ledger["files"])
        # The refusal is per entry: the others still landed.
        self.assertIn("l3io-test-lens",
                      (build.parent / "bmad-review.toml").read_text())

    def test_wire_in_preserves_team_comments(self):
        review = self.team("bmad-review", TEAM_REVIEW)
        code, out, err = self.run_cli("wire")
        self.assertEqual(code, 0, out + err)
        text = review.read_text()
        for line in TEAM_REVIEW.splitlines():
            self.assertIn(line, text)
        self.assertTrue(text.startswith(TEAM_REVIEW.split("\n[[workflow.lenses]]")[0]))
        lenses = tomllib.loads(text)["workflow"]["lenses"]
        self.assertEqual([x["code"] for x in lenses], ["licence-headers", "l3io-test-lens"])

    def test_unwire_never_removes_a_team_entry(self):
        review = self.team("bmad-review", TEAM_REVIEW)
        code, out, err = self.run_cli("wire")
        self.assertEqual(code, 0, out + err)
        # A team edit after wire: the saved bytes are now stale, so unwire must go entry
        # by entry and keep both the hand-added lens and the new one.
        text = review.read_text() + (
            '\n[[workflow.lenses]]\ncode = "team-later"\ninstruction = "Added after wire."\n')
        review.write_text(text)
        self.assertEqual(len(tomllib.loads(review.read_text())["workflow"]["lenses"]), 3)

        code, out, err = self.run_cli("unwire")
        self.assertEqual(code, 0, out + err)
        data = tomllib.loads(review.read_text())
        self.assertEqual([x["code"] for x in data["workflow"]["lenses"]],
                         ["licence-headers", "team-later"])
        self.assertNotIn("persistent_facts", data["workflow"])
        self.assertIn("# our in-house lens", review.read_text())

    def test_keyed_entry_yields_to_team_entry_with_same_code(self):
        team = TEAM_REVIEW + (
            '\n[[workflow.lenses]]\ncode = "l3io-test-lens"\ninstruction = "Team version."\n')
        review = self.team("bmad-review", team)
        code, out, err = self.run_cli("wire")
        self.assertEqual(code, 0, out + err)
        lenses = tomllib.loads(review.read_text())["workflow"]["lenses"]
        ours = [x for x in lenses if x["code"] == "l3io-test-lens"]
        self.assertEqual(ours, [{"code": "l3io-test-lens", "instruction": "Team version."}])
        self.assertIn("yielded", out)
        recorded = json.loads(self.ledger.read_text())["files"]["_bmad/custom/bmad-review.toml"]
        self.assertNotIn("lens", [r["id"] for r in recorded["entries"]])

        code, out, err = self.run_cli("unwire")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(review.read_bytes(), team.encode("utf-8"))


class TestWireInEdges(Base):
    def test_created_file_is_deleted_by_unwire(self):
        review = self.root / "_bmad" / "custom" / "bmad-review.toml"
        self.assertFalse(review.exists())
        code, out, err = self.run_cli("wire")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(review.exists())
        code, out, err = self.run_cli("unwire")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(review.exists())
        self.assertFalse((review.parent / "bmad-build.toml").exists())

    def test_created_file_with_team_additions_survives_unwire(self):
        code, out, err = self.run_cli("wire")
        self.assertEqual(code, 0, out + err)
        build = self.root / "_bmad" / "custom" / "bmad-build.toml"
        build.write_text(build.read_text() + 'review = "thorough"\n')
        code, out, err = self.run_cli("unwire")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(tomllib.loads(build.read_text()), {"workflow": {"review": "thorough"}})

    def test_parse_error_writes_nothing(self):
        self.team("bmad-build", "[workflow\n")
        code, out, err = self.run_cli("wire")
        self.assertEqual(code, 2, out + err)
        self.assertIn("bmad-build.toml", err)
        self.assertFalse((self.root / "_bmad" / "custom" / "bmad-review.toml").exists())
        self.assertFalse(self.ledger.exists())

    def test_keyed_identity_must_carry_our_prefix(self):
        self.entries.write_text(ENTRIES.replace('"l3io-test-lens"', '"adversarial"'))
        code, out, err = self.run_cli("wire")
        self.assertEqual(code, 2, out + err)
        self.assertIn("l3io-", err)

    def test_shipped_entries_are_test_only_and_valid(self):
        self.assertTrue(all(e.get("test_only") for e in
                            tomllib.loads(_ASSET.read_text())["entry"]))
        code, out, err = self.run_cli("wire", entries=False)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.snapshot(), {})
        code, out, err = self.run_cli("wire", "--include-test-only", entries=False)
        self.assertEqual(code, 0, out + err)
        self.assertIn("l3io-wire-in-self-test",
                      (self.root / "_bmad" / "custom" / "bmad-review.toml").read_text())

    def test_output_folder_expands_project_root(self):
        scripts = self.root / "_bmad" / "scripts"
        scripts.mkdir()
        (scripts / "resolve_config.py").write_text(
            "import json\nprint(json.dumps("
            "{'core.output_folder': '{project-root}/custom-out'}))\n")
        argv = [sys.executable, str(_SCRIPT), "wire", "--project-root", str(self.root),
                "--entries", str(self.entries)]
        p = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue((self.root / "custom-out" / "l3io" / "wire-in.json").is_file())
        self.assertFalse(any("{project-root}" in str(x) for x in self.root.rglob("*")))


if __name__ == "__main__":
    unittest.main()
