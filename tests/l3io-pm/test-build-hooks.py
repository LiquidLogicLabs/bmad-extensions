#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18", "tomlkit>=0.13"]
# ///
"""
Tests for the measurement hooks l3io wires into BMad v7's `bmad-build` and `bmad-build-auto`
(plan 2026-11-17-v7-phase-4-hooks.md, Task 4.2, R13). Run with:
  uv run tests/l3io-pm/test-build-hooks.py

The commands under test are the ones `/l3io-doctor wire` writes: each case reads the hook
values out of the shipped `assets/wire-in.toml`, takes the one fenced command from each, fills
its slots as the agent following the prose would, and runs it in a git-initialised v7 project.
So a hook whose command does not parse, or whose verb drifts from the CLI, fails here.

Two properties carry the weight:
  * the measurement lands -- one dispatch pair, all five actual metrics with `cost` derived,
    and one calibration sample when (and only when) the ticket was estimated beforehand;
  * the tree is CLEAN afterwards, and after the open on its own. `bmad-build-auto` refuses a
    dirty tree at its first step (step-01-clarify-and-route.md:60), so a hook that leaves one
    file behind stops the next build.

The Claude transcript is synthetic and is found the way a real one is: under
`$HOME/.claude/projects/*/<session>.jsonl`, with the session id in CLAUDE_CODE_SESSION_ID.
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
from datetime import UTC, datetime, timedelta
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PM_STATUS = _REPO / "skills" / "_shared" / "pm_status"
_WIRE_IN = _REPO / "skills" / "l3io-util" / "l3io-doctor" / "assets" / "wire-in.toml"

MODEL = "claude-opus-5-5"
SESSION = "5e55a0d1-0000-4000-8000-00000000b17d"
METRICS = ("elapsed_hours", "man_hours", "hitl_hours", "tokens_k", "cost")

FAKE_RESOLVE_CONFIG = """\
import json
print(json.dumps({"core.output_folder": "{project-root}/_bmad-output"}))
"""

FENCE_RE = re.compile(r"```(?:bash|sh)\n(.*?)\n```", re.DOTALL)
SLOT_RE = re.compile(r"<[a-z_ ]+>")


def entries(*ids):
    data = tomllib.loads(_WIRE_IN.read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in data["entry"]}
    return [by_id[i] for i in ids]


def command_of(entry, fill):
    """The one fenced command in a hook value, with `{project-root}`, `{plan_file}` and every
    `<slot>` the prose asks the agent to fill replaced. An unfilled slot fails the test."""
    blocks = FENCE_RE.findall(entry["value"])
    assert len(blocks) == 1, f"{entry['id']}: expected one fenced command, found {len(blocks)}"
    cmd = blocks[0].strip()
    for k, v in fill.items():
        cmd = cmd.replace(k, v)
    left = SLOT_RE.findall(cmd) + re.findall(r"\{[a-z_-]+\}", cmd)
    assert not left, f"{entry['id']}: unfilled slot(s) {left} in {cmd}"
    return cmd


def _uv_dirs():
    """uv's cache and Python installs, captured before HOME is redirected, so `uv run` under
    the fixture HOME reuses them instead of provisioning from the network."""
    out = {}
    for key, argv in (("UV_CACHE_DIR", ["uv", "cache", "dir"]),
                      ("UV_PYTHON_INSTALL_DIR", ["uv", "python", "dir"])):
        r = subprocess.run(argv, capture_output=True, text=True, check=False)
        if r.returncode == 0 and r.stdout.strip():
            out[key] = r.stdout.strip()
    return out


UV_DIRS = _uv_dirs()


class Project(unittest.TestCase):
    """A git-initialised v7 project: l3io-pm's declared pm_status where `bmad setup` installs
    it, one initiative with one epic of one ticket and its plan, all committed."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="test-build-hooks-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "proj"
        self.home = self.tmp / "home"
        self.home.mkdir()
        scripts = self.root / "_bmad" / "l3io-pm" / "scripts"
        scripts.mkdir(parents=True)
        shutil.copytree(_PM_STATUS, scripts / "pm_status",
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.write("_bmad/scripts/resolve_config.py", FAKE_RESOLVE_CONFIG)
        self.write(".gitignore", "__pycache__/\n")
        init = "_bmad-output/initiative-shop"
        self.write(f"{init}/initiative-shop.md", "---\ntype: initiative\n---\n# Shop\n")
        self.write(f"{init}/tickets/tickets.toml", '[[epic]]\nid = 1\nslug = "epic-cart"\n')
        self.write(f"{init}/tickets/epic-cart/epic-cart.md",
                   "---\ntype: epic\nafter: []\n---\n# Cart\n")
        self.tdir = self.root / init / "tickets" / "epic-cart" / "tickets"
        self.write(f"{init}/tickets/epic-cart/tickets/tickets.toml",
                   '[[entry]]\nid = 1\ntype = "story"\ntitle = "Basket"\n')
        self.write(f"{init}/tickets/epic-cart/tickets/story-basket.md",
                   "---\nid: 1\ntype: story\ntitle: \"Basket\"\nparent: epic-cart\n---\n# Basket\n")
        # As bmad-build leaves it before On Complete: marked built and committed (step-05).
        self.plan = self.tdir / "story-basket-plan.md"
        self.write(f"{init}/tickets/epic-cart/tickets/story-basket-plan.md",
                   "---\ntitle: 'Basket'\ntype: 'feature'\nticket: '1'\nstatus: 'built'\n"
                   "review_loop_iteration: 0\n---\n\n# Basket\n\n## Verification\n\n"
                   "- `pytest -q`\n")
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "fixture")
        self.state_root = self.root / "_bmad-output" / "l3io"

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    @property
    def env(self):
        env = {**os.environ, **UV_DIRS, "HOME": str(self.home),
               "CLAUDE_CODE_SESSION_ID": SESSION,
               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        env.pop("GIT_DIR", None)
        return env

    def git(self, *argv):
        r = subprocess.run(["git", "-C", str(self.root), *argv], capture_output=True,
                           text=True, env=self.env)
        self.assertEqual(r.returncode, 0, f"git {argv}: {r.stderr}")
        return r.stdout

    def porcelain(self):
        return self.git("status", "--porcelain", "--untracked-files=all")

    def sh(self, cmd, expect=0):
        r = subprocess.run(["bash", "-c", cmd], cwd=self.root, capture_output=True, text=True,
                           env=self.env)
        self.assertEqual(r.returncode, expect, f"{cmd}\nstdout: {r.stdout}\nstderr: {r.stderr}")
        return r

    def pm(self, *argv):
        main = self.root / "_bmad" / "l3io-pm" / "scripts" / "pm_status" / "__main__.py"
        r = subprocess.run([sys.executable, str(main), *argv], cwd=self.root,
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, f"{argv}\nstdout: {r.stdout}\nstderr: {r.stderr}")
        return r

    def estimate(self):
        """An estimate recorded before the build, as Sofia's estimation hook would, and
        committed with the rest of the planning."""
        self.pm("set-estimate", "--project-root", str(self.root), "--ticket-dir",
                str(self.tdir), "--entry", "1", "--elapsed-hours", "0.5", "--man-hours", "2",
                "--hitl-hours", "0.25", "--tokens-k", "40")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "estimate")

    def transcript(self, since):
        """Two assistant turns inside the bracket and one before it, which must not count."""
        d = self.home / ".claude" / "projects" / "-tmp-proj"
        d.mkdir(parents=True, exist_ok=True)

        def rec(mid, when, usage):
            return json.dumps({"type": "assistant", "sessionId": SESSION,
                               "timestamp": when.isoformat(),
                               "message": {"id": mid, "model": MODEL, "usage": usage}})
        before = since - timedelta(hours=1)
        inside = datetime.now(UTC)
        lines = [
            rec("m0", before, {"input_tokens": 999999, "output_tokens": 999999,
                               "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}),
            rec("m1", inside, {"input_tokens": 1000, "output_tokens": 2000,
                               "cache_creation_input_tokens": 3000,
                               "cache_read_input_tokens": 40000}),
            rec("m2", inside, {"input_tokens": 500, "output_tokens": 500,
                               "cache_creation_input_tokens": 0,
                               "cache_read_input_tokens": 10000}),
        ]
        (d / f"{SESSION}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run_build(self, open_id, close_id, fill):
        open_e, close_e = entries(open_id, close_id)
        base = {"{project-root}": str(self.root), "{plan_file}": str(self.plan)}
        self.assertEqual(self.porcelain(), "", "the fixture is not clean before the build")
        opened = datetime.now(UTC)
        self.sh(command_of(open_e, base))
        self.assertEqual(self.porcelain(), "",
                         "build-open left the tree dirty; bmad-build-auto's step 1 would HALT")
        self.transcript(opened)
        return self.sh(command_of(close_e, {**base, **fill}))

    def events(self):
        p = self.state_root / "events.jsonl"
        if not p.exists():
            return []
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]

    def sidecar(self):
        with open(self.tdir / "story-basket-plan.l3io.toml", "rb") as fh:
            return tomllib.load(fh)

    def samples(self):
        p = self.state_root / "pm-calibration.yaml"
        if not p.exists():
            return 0
        from ruamel.yaml import YAML
        cal = YAML(typ="safe").load(p.read_text(encoding="utf-8")) or {}
        counts = [len(m.get("samples", [])) for cls in (cal.get("scope") or {}).values()
                  for m in cls.values()]
        return max(counts, default=0)


BUILD_FILL = {"<runtime>": "claude", "<man_hours>": "3", "<hitl_hours>": "0.5",
              "<verification command>": "pytest -q", "<exit code>": "0"}


class TestBuildHooks(Project):

    def test_bmad_build_alone_records_actuals(self):
        self.estimate()
        self.run_build("l3io-build-open", "l3io-build-close", BUILD_FILL)

        ev = [e for e in self.events() if e.get("event", "").startswith("dispatch_")]
        self.assertEqual([e["event"] for e in ev], ["dispatch_open", "dispatch_close"], ev)
        self.assertTrue(all(e.get("agent") == "bmad-build" for e in ev), ev)

        actual = self.sidecar()["actual"]
        self.assertEqual(list(actual)[:5], list(METRICS), actual)
        tk = actual["tokens_k"]
        self.assertEqual((tk["input"], tk["output"], tk["cache_write"], tk["cache_read"]),
                         (1.5, 2.5, 3.0, 50.0), "the turn before the bracket was counted")
        self.assertEqual(actual["man_hours"], 3)
        self.assertEqual(actual["hitl_hours"], 0.5)
        self.assertGreater(actual["cost"], 0)
        self.assertEqual(actual["model"], MODEL)
        runs = self.sidecar()["completion_evidence"]["test_runs"]
        self.assertEqual([(r["command"], r["exit_code"]) for r in runs], [("pytest -q", 0)])

        self.assertEqual(self.samples(), 1)
        self.assertEqual(self.porcelain(), "",
                         "build-close left the tree dirty; the next build would HALT")
        self.assertIn("chore(l3io): actuals 1", self.git("log", "-1", "--format=%s"))
        self.assertEqual(list((self.state_root / ".inflight").glob("*.json")), [])

    def test_unestimated_ticket_records_actuals_and_no_sample(self):
        r = self.run_build("l3io-build-open", "l3io-build-close", BUILD_FILL)
        self.assertIn("man_hours", self.sidecar()["actual"])
        self.assertEqual(self.samples(), 0)
        self.assertIn("no calibration sample", r.stderr)
        self.assertEqual(self.porcelain(), "")

    def test_bmad_build_auto_records_actuals_with_zero_hitl(self):
        self.estimate()
        fill = {k: v for k, v in BUILD_FILL.items() if k != "<hitl_hours>"}
        self.run_build("l3io-build-auto-open", "l3io-build-auto-close", fill)
        actual = self.sidecar()["actual"]
        self.assertEqual(actual["hitl_hours"], 0)
        ev = [e for e in self.events() if e.get("event", "").startswith("dispatch_")]
        self.assertEqual([e.get("agent") for e in ev], ["bmad-build-auto"] * 2)
        self.assertEqual(self.samples(), 1)
        self.assertEqual(self.porcelain(), "")

    def test_close_without_open_is_exit_4_and_unmatched(self):
        close = entries("l3io-build-close")[0]
        cmd = command_of(close, {"{project-root}": str(self.root),
                                 "{plan_file}": str(self.plan), **BUILD_FILL})
        self.sh(cmd, expect=4)
        ev = [e for e in self.events() if e.get("event") == "dispatch_close"]
        self.assertEqual(len(ev), 1)
        self.assertTrue(ev[0].get("unmatched"), ev)
        self.assertEqual(self.porcelain(), "")

    def test_reopen_closes_the_stale_bracket_as_abandoned(self):
        open_e, close_e = entries("l3io-build-open", "l3io-build-close")
        base = {"{project-root}": str(self.root), "{plan_file}": str(self.plan)}
        self.sh(command_of(open_e, base))
        self.sh(command_of(open_e, base))           # the first build never reached On Complete
        self.assertEqual(self.porcelain(), "")
        self.transcript(datetime.now(UTC))
        self.sh(command_of(close_e, {**base, **BUILD_FILL}))
        closes = [e for e in self.events() if e.get("event") == "dispatch_close"]
        self.assertEqual(sorted(e.get("outcome") for e in closes), ["abandoned", "closed"])
        self.assertEqual(list((self.state_root / ".inflight").glob("*.json")), [])
        self.assertEqual(self.porcelain(), "")

    def test_hook_values_name_only_the_declared_script(self):
        for e in entries("l3io-build-open", "l3io-build-close", "l3io-build-auto-open",
                         "l3io-build-auto-close"):
            self.assertEqual(e.get("requires"), "l3io-pm", e["id"])
            self.assertNotIn("{skill-root}", e["value"], e["id"])
            self.assertIn("uv run {project-root}/_bmad/l3io-pm/scripts/pm_status/__main__.py",
                          e["value"], e["id"])
            self.assertNotRegex(e["value"], r"tickets\.py\S*\s+mark\b", e["id"])
        for e in entries("l3io-build-close", "l3io-build-auto-close"):
            self.assertIn("never", e["value"].lower())
            self.assertIn("mark", e["value"])
            self.assertIn("man_hours", e["value"])
            self.assertIn("## Verification", e["value"])


if __name__ == "__main__":
    unittest.main()
