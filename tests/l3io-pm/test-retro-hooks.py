#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18", "tomlkit>=0.13"]
# ///
"""
Tests for the epic closure l3io wires onto BMad v7's `bmad-retrospective` (plan
2026-11-17-v7-phase-4-hooks.md, Task 4.6). Run with:
  uv run tests/l3io-pm/test-retro-hooks.py

As in test-build-hooks.py, the command under test is the one `/l3io-doctor wire` writes: it is
taken out of the shipped `assets/wire-in.toml`, its slots filled as the agent following the
prose would fill them, and run in a git-initialised v7 project with l3io-pm's declared
`pm_status` where `bmad setup` installs it.

What carries the weight: the closure lands (the epic's actual, the retrospective's own spend
as the closure actual, the verdict), it writes no status, and the tree is CLEAN afterwards
apart from what the retrospective itself left -- the hook runs where the next
`bmad-build-auto` of an unattended run demands a clean tree (step-01-clarify-and-route.md:60).
"""
import importlib.util
import json
import tomllib
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("build_hooks", _HERE / "test-build-hooks.py")
bh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bh)

RETRO = "l3io-epic-close"
FILL = {"<runtime>": "claude", "<man_hours>": "1.5", "<hitl_hours>": "0"}


def retro_doc(verdict):
    return (f"---\nepic: epic-cart\ndate: 2026-11-17\nverdict: {verdict}\n"
            "criteria: declared\nheadless: true\n---\n\n# Retrospective: epic-cart\n")


class Project(bh.Project):
    """test-build-hooks' project, with the basket ticket already built and measured, and the
    retrospective's document saved in the epic folder as Phase 5 leaves it."""

    def setUp(self):
        super().setUp()
        self.epic_dir = self.tdir.parent
        self.retro = self.epic_dir / "epic-cart-retrospective.md"
        self.estimate()
        self.run_build("l3io-build-auto-open", "l3io-build-auto-close",
                       {k: v for k, v in bh.BUILD_FILL.items() if k != "<hitl_hours>"})
        self.assertEqual(self.porcelain(), "")

    def write_retro(self, verdict="accepted", commit=True):
        self.retro.write_text(retro_doc(verdict), encoding="utf-8")
        if commit:
            self.git("add", "-A")
            self.git("commit", "-q", "-m", "retrospective")

    def retro_transcript(self):
        """The session's transcript after the build: the turn that wrote the retrospective's
        skeleton, and one after it. The build's own turns are already in the file."""
        path = self.home / ".claude" / "projects" / "-tmp-proj" / f"{bh.SESSION}.jsonl"
        now = datetime.now(UTC)

        def rec(mid, when, usage, content=None):
            msg = {"id": mid, "model": bh.MODEL, "usage": usage}
            if content is not None:
                msg["content"] = content
            return json.dumps({"type": "assistant", "sessionId": bh.SESSION,
                               "timestamp": when.isoformat(), "message": msg})
        with path.open("a", encoding="utf-8") as fh:
            fh.write(rec("r1", now,
                         {"input_tokens": 700, "output_tokens": 300,
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 9000},
                         [{"type": "tool_use", "name": "Write",
                           "input": {"file_path": str(self.retro), "content": "---\n"}}]) + "\n")
            fh.write(rec("r2", now,
                         {"input_tokens": 300, "output_tokens": 700,
                          "cache_creation_input_tokens": 1000,
                          "cache_read_input_tokens": 1000}) + "\n")

    def close_cmd(self, **fill):
        e = bh.entries(RETRO)[0]
        return bh.command_of(e, {"{project-root}": str(self.root),
                                 "<epic folder>": str(self.epic_dir),
                                 "<retrospective file>": str(self.retro), **FILL, **fill})

    def side(self):
        with open(self.tdir / "l3io.toml", "rb") as fh:
            return tomllib.load(fh)


class TestRetroHook(Project):

    def test_retrospective_on_complete_closes_the_epic_and_leaves_the_tree_clean(self):
        self.write_retro()
        self.retro_transcript()
        self.sh(self.close_cmd())
        epic = self.side()["epic"]
        self.assertEqual(epic["retro_verdict"], "accepted")
        tk = epic["closure"]["tokens_k"]
        self.assertEqual((tk["input"], tk["output"], tk["cache_write"], tk["cache_read"]),
                         (1.0, 1.0, 1.0, 10.0),
                         "the build's turns, before the retrospective, were counted")
        ticket = self.sidecar()["actual"]
        self.assertEqual(epic["actual"]["man_hours"], ticket["man_hours"] + 1.5)
        self.assertEqual(epic["actual"]["tokens_k"]["total"],
                         ticket["tokens_k"]["total"] + tk["total"])
        self.assertEqual(self.porcelain(), "",
                         "epic-close left the tree dirty; the next build would HALT")
        self.assertEqual(self.git("log", "-1", "--format=%s").strip(),
                         "chore(l3io): epic close epic-cart")
        self.assertEqual(self.samples(), 1, "the epic close is not a scope sample")

    def test_the_retrospective_document_is_left_as_v7_left_it(self):
        """bmad-retrospective commits nothing of its own (retro-document.md:39); our commit
        takes l3io's files only, so an uncommitted retrospective stays the user's."""
        self.write_retro(commit=False)
        self.sh(self.close_cmd(**{"<runtime>": "other"}) + " --since "
                + (datetime.now(UTC) - timedelta(minutes=5)).isoformat())
        rel = self.retro.relative_to(self.root).as_posix()
        self.assertEqual(self.porcelain(), f"?? {rel}\n")
        shown = self.git("show", "--name-only", "--format=", "HEAD").split()
        self.assertNotIn(rel, shown)
        self.assertIn(self.tdir.joinpath("l3io.toml").relative_to(self.root).as_posix(), shown)

    def test_hook_value_names_only_the_declared_script_and_writes_no_status(self):
        e = bh.entries(RETRO)[0]
        self.assertEqual((e["skill"], e["kind"], e["path"], e.get("requires")),
                         ("bmad-retrospective", "scalar", "workflow.on_complete", "l3io-pm"))
        v = e["value"]
        self.assertNotIn("{skill-root}", v)
        self.assertIn("uv run {project-root}/_bmad/l3io-pm/scripts/pm_status/__main__.py "
                      "epic-close", v)
        self.assertNotRegex(v, r"tickets\.py\S*\s+mark\b")
        self.assertIn("mark", v)
        self.assertIn("man_hours", v)
        self.assertIn("--since", v)


if __name__ == "__main__":
    unittest.main()
