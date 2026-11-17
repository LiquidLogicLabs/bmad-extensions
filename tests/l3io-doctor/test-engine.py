#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18", "tomlkit>=0.13"]
# ///
"""Tests for migrate-engine.py, l3io 3.x -> 4.x on BMad v7 -- run with: uv run test-engine.py

Each test builds a project the way `bmad migrate` leaves it after method's own migration-1:
a v7 initiative under `_bmad-output/` (tickets.toml, epic folders, plans for stories past
backlog) beside the untouched l3io source, then runs the engine over it. The initiative
follows the layout `tickets.py` reads at the pinned upstream (`tickets_dir`, `load_folder`,
`join_plans`: tickets.py:280-400 at e435a22).
"""
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FIXTURES = Path(HERE) / "fixtures"
SCRIPTS = os.path.join(REPO, "skills", "l3io-util", "l3io-doctor", "scripts")
MIGRATION = os.path.join(REPO, "skills", "l3io-pm", "bmod-l3io-pm", "migration-1.toml")


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


eng = _load("migrate_engine", "migrate-engine.py")

FAKE_RESOLVE_CONFIG = """\
import json, sys
key = sys.argv[sys.argv.index("--key") + 1] if "--key" in sys.argv else ""
values = {"core.output_folder": "{project-root}/_bmad-output"}
print(json.dumps({key: values[key]} if key in values else {}))
"""

# Where each fixture lands in a project: the artifact folder, or the project root.
ART = "_bmad-output/implementation-artifacts"
FIXTURE_DEST = {"sharded": ART, "l3io-flat": ART, "split": ART, "bmad-flat": ART,
                "per-epic": ".", "v6-shim": "."}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def plan_md(entry_id, status):
    return f"---\ntitle: 'x'\ntype: 'feature'\nticket: '{entry_id}'\nstatus: '{status}'\n---\n\n# x\n"


def fetch(rel: str) -> Path:
    """A v7 file at the pin, through scripts/fetch-bmad-tool.mjs (SHA-256 verified)."""
    pin = subprocess.run(
        ["node", "--input-type=module", "-e",
         'import { PIN } from "./scripts/fetch-bmad-tool.mjs"; console.log(PIN)'],
        cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    p = subprocess.run(["node", "scripts/fetch-bmad-tool.mjs", pin, rel],
                       cwd=REPO, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"fetch-bmad-tool {rel}: {p.stderr.strip()}")
    return Path(p.stdout.strip())


class Project(unittest.TestCase):
    """A project root holding a fixture's source and, unless `v7=False`, the initiative
    method's migration-1 would have written for it."""

    ENTRIES = [(1, "Password login", "done"), (2, "Session cookies", "in-review"),
               (3, "Google provider", None)]

    def make(self, fixture, v7=True, entries=None, plans=True):
        self.root = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        write(os.path.join(self.root, "_bmad", "scripts", "resolve_config.py"),
              FAKE_RESOLVE_CONFIG)
        dest = os.path.join(self.root, FIXTURE_DEST[fixture])
        os.makedirs(dest, exist_ok=True)
        shutil.copytree(FIXTURES / fixture, dest, dirs_exist_ok=True)
        self.art = os.path.join(self.root, ART)
        self.out = os.path.join(self.root, "_bmad-output")
        self.state_root = os.path.join(self.out, "l3io")
        if v7:
            self.initiative(entries or self.ENTRIES, plans)
        return self

    def initiative(self, entries, plans=True):
        ini = os.path.join(self.out, "initiative-shop")
        self.ini = ini
        write(os.path.join(ini, "initiative-shop.md"), "---\ntype: initiative\n---\n# Shop\n")
        write(os.path.join(ini, "tickets", "tickets.toml"),
              '[[epic]]\nid = 1\nslug = "epic-authentication"\ntitle = "Authentication"\n\n'
              '[[epic]]\nid = 2\nslug = "epic-reporting"\ntitle = "Reporting"\n')
        self.epic = os.path.join(ini, "tickets", "epic-authentication")
        write(os.path.join(self.epic, "epic-authentication.md"),
              "---\ntype: epic\ntitle: Authentication\n---\n# Authentication\n")
        toml = "".join(f'[[entry]]\nid = {i}\ntype = "story"\ntitle = "{t}"\n'
                       f'description = "{t} works"\nverify = "a test"\n\n'
                       for i, t, _ in entries)
        write(os.path.join(self.epic, "tickets", "tickets.toml"), toml)
        if plans:
            for i, t, status in entries:
                if status:
                    slug = t.lower().replace(" ", "-")
                    write(os.path.join(self.epic, "tickets", f"story-{slug}-plan.md"),
                          plan_md(i, status))
        write(os.path.join(ini, "tickets", "epic-reporting", "epic-reporting.md"),
              "---\ntype: epic\ntitle: Reporting\n---\n# Reporting\n")

    def run_engine(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = eng.main(["--project-root", self.root, *argv])
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue(), err.getvalue()

    def sidecar(self, *parts):
        with open(os.path.join(*parts), "rb") as fh:
            return tomllib.load(fh)

    def entry_sidecar(self):
        return self.sidecar(self.epic, "tickets", "l3io.toml")

    def source_files(self):
        return sorted(str(p.relative_to(self.root)) for p in Path(self.root).rglob("*")
                      if p.is_file() and "_bmad-output/l3io" not in str(p)
                      and "initiative-shop" not in str(p))


class TestFixtureCorpus(unittest.TestCase):
    def test_every_source_layout_has_a_fixture(self):
        """One fixture per source layout the engine reads, plus the BMad-schema flat file
        (not ours: method's) and the leftover-shim project. A deleted fixture fails here."""
        on_disk = {p.name for p in FIXTURES.iterdir() if p.is_dir()}
        self.assertEqual(on_disk, set(eng.LAYOUTS) | {"bmad-flat", "v6-shim"})


class TestMigrationFile(unittest.TestCase):
    """`bmad migrate` lists a file only when its [migration] table carries every field
    (knowledge.py MIGRATION_FIELDS and `checklist`, :66-68, :446-455 at e435a22)."""

    def setUp(self):
        with open(MIGRATION, "rb") as fh:
            self.m = tomllib.load(fh)["migration"]

    def test_required_fields(self):
        for k in ("module", "from", "to", "title", "summary", "detect", "guide"):
            self.assertTrue(str(self.m.get(k, "")).strip(), k)
        self.assertTrue(self.m["checklist"])
        self.assertEqual((self.m["module"], self.m["from"], self.m["to"]), ("l3io-pm", "3", "4"))

    def test_guide_invokes_the_engine(self):
        self.assertIn("_bmad/l3io-util/scripts/migrate-engine.py", self.m["guide"])
        for step in ("--detect", "--plan", "--apply"):
            self.assertIn(step, self.m["guide"])

    def test_checklist_verifies_every_moved_datum(self):
        text = " ".join(self.m["checklist"])
        for datum in ("calibration", "events", "ADR register", "estimate", "actual",
                      "source", "shim"):
            self.assertIn(datum, text)


class TestWaitsForMethod(Project):
    def test_l3io_migration_waits_for_method(self):
        """Review Focus 3. knowledge.py lists migrations sorted by (module, number)
        (:128), so `l3io-pm`'s is offered BEFORE `method`'s; only detect can order them.
        Without v7's initiative layout, detect does not match and --apply writes nothing."""
        self.make("sharded", v7=False)
        before = self.source_files()
        code, out, _ = self.run_engine("--detect")
        self.assertEqual(code, 1, out)
        found = json.loads(out)
        self.assertFalse(found["applies"])
        self.assertIn("method", found["reason"])
        self.assertEqual(found["layouts"], ["sharded"])
        code, _, err = self.run_engine("--apply")
        self.assertNotEqual(code, 0)
        self.assertIn("method", err)
        self.assertFalse(os.path.exists(self.state_root))
        self.assertEqual(self.source_files(), before)
        # Method's migration then runs: the initiative appears, and ours applies.
        self.initiative(self.ENTRIES)
        code, out, _ = self.run_engine("--detect")
        self.assertEqual(code, 0, out)
        self.assertTrue(json.loads(out)["applies"])

    def test_method_migration_still_in_draft_holds_ours(self):
        self.make("sharded")
        write(os.path.join(self.out, "migration-v6-v7", "migration-v6-v7.md"),
              "---\ntype: migration\nstatus: draft\n---\n")
        code, out, _ = self.run_engine("--detect")
        self.assertEqual(code, 1)
        self.assertIn("draft", json.loads(out)["reason"])

    def test_bmad_migrate_lists_ours_before_methods(self):
        """Measured with v7's own lister at the pin (knowledge.py, fetched and SHA-256
        verified): both files are valid migrations, and `migrations` is sorted by module
        name, so `l3io-pm` precedes `method`. That ordering is why detect must wait."""
        tools = {rel: fetch(rel) for rel in (
            "skills/core-tools/bmad/scripts/knowledge.py",
            "skills/core-tools/bmad/scripts/list_templates.py",
            "skills/method/bmod-method/migration-1.toml")}
        skills = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, skills, True)
        shutil.copytree(os.path.dirname(MIGRATION), skills / "bmod-l3io-pm")
        (skills / "bmod-method").mkdir()
        (skills / "bmod-method" / "bmod.toml").write_text(
            '[bmod]\ncode = "method"\nversion = "6.13.0"\n', encoding="utf-8")
        shutil.copyfile(tools["skills/method/bmod-method/migration-1.toml"],
                        skills / "bmod-method" / "migration-1.toml")
        bin_dir = skills.parent / (skills.name + "-bin")
        bin_dir.mkdir()
        self.addCleanup(shutil.rmtree, bin_dir, True)
        for rel, path in tools.items():
            if rel.endswith(".py"):
                shutil.copyfile(path, bin_dir / Path(rel).name)
        p = subprocess.run([sys.executable, str(bin_dir / "knowledge.py"), "--root", str(skills)],
                           capture_output=True, text=True, check=True)
        found = json.loads(p.stdout)
        listed = [(m["module"], m["from"], m["to"]) for m in found["migrations"]]
        self.assertEqual(listed, [("l3io-pm", "3", "4"), ("method", "6", "7")])
        self.assertEqual([x for x in found["problems"] if x.get("kind") == "migration"], [])

    def test_detect_prose_requires_the_initiative_layout(self):
        with open(MIGRATION, "rb") as fh:
            detect = tomllib.load(fh)["migration"]["detect"]
        for signal in ("initiative-", "tickets/tickets.toml", "migration-v6-v7"):
            self.assertIn(signal, detect)

    def test_a_bmad_schema_flat_file_is_not_ours(self):
        self.make("bmad-flat")
        code, out, _ = self.run_engine("--detect")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["layouts"], [])


class TestShardedMigration(Project):
    def test_migration_preserves_calibration_events_adr_register(self):
        self.make("sharded")
        src = os.path.join(self.art, "state")
        code, out, err = self.run_engine("--apply")
        self.assertEqual(code, 0, out + err)
        for name in ("pm-calibration.yaml", "adr-register.yaml", "reorg-log.yaml",
                     "events.jsonl"):
            with open(os.path.join(src, name), "rb") as a, \
                 open(os.path.join(self.state_root, name), "rb") as b:
                self.assertEqual(a.read(), b.read(), name)

    def test_events_union_with_a_log_v7_already_started(self):
        self.make("sharded")
        v7_line = '{"ts": "2026-11-17T00:00:00Z", "event": "dispatch_open"}\n'
        write(os.path.join(self.state_root, "events.jsonl"), v7_line)
        code, out, err = self.run_engine("--apply")
        self.assertEqual(code, 0, out + err)
        with open(os.path.join(self.state_root, "events.jsonl")) as fh:
            lines = fh.read().splitlines()
        with open(os.path.join(self.art, "state", "events.jsonl")) as fh:
            source = fh.read().splitlines()
        self.assertEqual(lines[:len(source)], source)
        self.assertEqual(lines[-1], v7_line.strip())

    def test_a_differing_calibration_file_refuses(self):
        self.make("sharded")
        write(os.path.join(self.state_root, "pm-calibration.yaml"), "version: 2\n")
        code, _, err = self.run_engine("--apply")
        self.assertEqual(code, 1)
        self.assertIn("pm-calibration.yaml", err)
        with open(os.path.join(self.state_root, "pm-calibration.yaml")) as fh:
            self.assertEqual(fh.read(), "version: 2\n")

    def test_estimates_actuals_and_evidence_land_in_the_sidecars(self):
        self.make("sharded")
        code, out, err = self.run_engine("--apply")
        self.assertEqual(code, 0, out + err)
        side = self.entry_sidecar()
        e1 = side["entry"]["1"]
        self.assertEqual(e1["class"], "standard")
        self.assertEqual(e1["migrated_from"], "E001-S01-001")
        self.assertEqual(e1["estimate"]["man_hours"], 4)
        self.assertEqual(e1["estimate"]["tokens_k"]["total"], 200)
        self.assertEqual(e1["estimate"]["cost"], 0.8)
        self.assertTrue(e1["fingerprint"].startswith("sha256:"))
        self.assertEqual(side["entry"]["2"]["previous_keys"], ["E007-S02-004"])
        self.assertEqual(side["entry"]["3"]["class"], "complex")
        self.assertEqual(side["epic"]["estimate"]["man_hours_high"], 16)
        self.assertEqual(side["epic"]["actual"]["tokens_k"]["cache_read"], 360)
        self.assertEqual(side["epic"]["orchestration"]["hitl_hours"], 0.1)
        self.assertEqual(side["sprint"]["S01"]["actual"]["man_hours"], 8)
        ticket = self.sidecar(self.epic, "tickets", "story-password-login-plan.l3io.toml")
        self.assertEqual(ticket["actual"]["man_hours"], 5)
        self.assertEqual(ticket["actual"]["runtime"], "claude")
        self.assertEqual(ticket["fix_iterations"], 1)
        self.assertEqual(len(ticket["completion_evidence"]["test_runs"]), 2)
        self.assertTrue(ticket["completion_evidence"]["tests_passing"])
        self.assertEqual(ticket["calibration_sampled_at"], "2026-08-16T21:00:00Z")
        lanes = self.sidecar(self.ini, "tickets", "l3io.toml")
        self.assertEqual(lanes["epic"]["epic-authentication"]["lane"], 2)

    def test_no_v7_file_is_written(self):
        """ADR-0015: tickets.toml, leaves, plans and container files are v7's."""
        self.make("sharded")
        v7 = {p: p.read_bytes() for p in Path(self.ini).rglob("*")
              if p.is_file() and not p.name.endswith("l3io.toml")}
        code, out, err = self.run_engine("--apply")
        self.assertEqual(code, 0, out + err)
        after = {p: p.read_bytes() for p in Path(self.ini).rglob("*")
                 if p.is_file() and not p.name.endswith("l3io.toml")}
        self.assertEqual(v7, after)

    def test_apply_is_idempotent(self):
        self.make("sharded")
        self.assertEqual(self.run_engine("--apply")[0], 0)
        first = self.entry_sidecar()
        code, out, err = self.run_engine("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(first, self.entry_sidecar())

    def test_an_estimate_v7_already_holds_is_never_overwritten(self):
        self.make("sharded")
        write(os.path.join(self.epic, "tickets", "l3io.toml"),
              '[entry.1]\nclass = "simple"\n\n[entry.1.estimate]\nman_hours = 1\n')
        code, _, err = self.run_engine("--apply")
        self.assertEqual(code, 1)
        self.assertIn("entry.1", err)
        self.assertEqual(self.entry_sidecar()["entry"]["1"]["estimate"], {"man_hours": 1})


class TestMappingGate(Project):
    def test_an_ambiguous_title_refuses_with_a_report(self):
        entries = [(1, "Password login", "done"), (2, "Password login", None),
                   (3, "Session cookies", "in-review"), (4, "Google provider", None)]
        self.make("sharded", entries=entries)
        code, _, err = self.run_engine("--apply")
        self.assertEqual(code, 1)
        self.assertIn("E001-S01-001", err)
        self.assertIn("more than one", err)
        self.assertFalse(os.path.exists(self.state_root))

    def test_a_map_file_resolves_the_ambiguity(self):
        entries = [(1, "Password login", "done"), (2, "Password login", None),
                   (3, "Session cookies", "in-review"), (4, "Google provider", None)]
        self.make("sharded", entries=entries)
        mp = os.path.join(self.root, "map.json")
        write(mp, json.dumps({"E001-S01-001": "epic-authentication/1"}))
        code, out, err = self.run_engine("--apply", "--map", mp)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.entry_sidecar()["entry"]["1"]["migrated_from"], "E001-S01-001")

    def test_v6_key_maps_before_titles(self):
        self.make("sharded", entries=[(1, "Renamed login", "done"),
                                      (2, "Session cookies", "in-review"),
                                      (3, "Google provider", None)])
        toml = os.path.join(self.epic, "tickets", "tickets.toml")
        with open(toml) as fh:
            text = fh.read()
        write(toml, text.replace('title = "Renamed login"\n',
                                 'title = "Renamed login"\nv6_key = "E001-S01-001"\n', 1))
        code, out, err = self.run_engine("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.entry_sidecar()["entry"]["1"]["migrated_from"], "E001-S01-001")

    def test_actuals_with_no_plan_refuse_and_name_v7s_writer(self):
        """A plan is v7's (ADR-0015): the gate names `tickets.py mark`, never writes one."""
        self.make("sharded", plans=False)
        code, _, err = self.run_engine("--apply")
        self.assertEqual(code, 1)
        self.assertIn("tickets.py", err)
        self.assertIn("mark", err)
        self.assertIn("1 done", err)
        self.assertFalse(list(Path(self.epic, "tickets").glob("*-plan.md")))


class TestSourceKept(Project):
    def test_source_kept_until_verify(self):
        self.make("sharded")
        before = self.source_files()
        real = eng.verify
        eng.verify = lambda plan, ctx: ["entry.1: estimate on disk differs"]
        try:
            code, _, err = self.run_engine("--apply", "--dispose")
        finally:
            eng.verify = real
        self.assertEqual(code, 1)
        self.assertIn("source untouched", err)
        self.assertEqual(self.source_files(), before)
        # Verified without --dispose: still kept.
        self.assertEqual(self.run_engine("--apply")[0], 0)
        self.assertEqual(self.source_files(), before)
        # Verified with --dispose: renamed aside, never deleted.
        code, out, err = self.run_engine("--apply", "--dispose")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(os.path.exists(os.path.join(self.art, "state")))
        self.assertTrue(os.path.isfile(os.path.join(
            self.art, "state.legacy", "active", "epic-001", "epic.yaml")))
        code, out, _ = self.run_engine("--detect")
        self.assertEqual(json.loads(out)["layouts"], [])


class TestEachSourceLayout(Project):
    def test_sharded(self):
        self.make("sharded")
        code, out, err = self.run_engine("--plan", "--format", "json")
        self.assertEqual(code, 0, out + err)
        plan = json.loads(out)
        self.assertEqual(plan["layouts"], ["sharded"])
        self.assertEqual(plan["refusals"], [])

    def test_l3io_flat(self):
        self.make("l3io-flat", entries=[(1, "Password login", "done"),
                                        (2, "Session cookies", "in-review"),
                                        (3, "Google provider", "ready-for-dev")])
        code, out, err = self.run_engine("--apply")
        self.assertEqual(code, 0, out + err)
        side = self.entry_sidecar()
        self.assertEqual(side["entry"]["3"]["estimate"], {"man_hours": 5, "tokens_k": 40})
        self.assertNotIn("class", side["entry"]["3"])
        ticket = self.sidecar(self.epic, "tickets", "story-google-provider-plan.l3io.toml")
        self.assertEqual(ticket["actual"], {"man_hours": 6})
        self.assertIn("classification 'feature'", out)

    def test_split(self):
        self.make("split")
        code, out, err = self.run_engine("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.entry_sidecar()["entry"]["1"]["estimate"],
                         {"man_hours": 3, "tokens_k": 50})

    def test_per_epic(self):
        self.make("per-epic")
        code, out, err = self.run_engine("--apply", "--dispose")
        self.assertEqual(code, 0, out + err)
        ticket = self.sidecar(self.epic, "tickets", "story-password-login-plan.l3io.toml")
        self.assertEqual(ticket["actual"], {"elapsed_hours": 1.5, "man_hours": 5})
        self.assertTrue(os.path.isdir(os.path.join(self.root, "_bmad", "state.legacy")))

    def test_flat_file_method_archived(self):
        """Method's migration moves sprint-status.yaml to `archive-v6/` unchanged
        (migration-1.toml:151); the engine reads it there."""
        self.make("l3io-flat", entries=[(1, "Password login", "done"),
                                        (2, "Session cookies", "in-review"),
                                        (3, "Google provider", "ready-for-dev")])
        os.makedirs(os.path.join(self.ini, "archive-v6"))
        shutil.move(os.path.join(self.art, "sprint-status.yaml"),
                    os.path.join(self.ini, "archive-v6", "sprint-status.yaml"))
        code, out, err = self.run_engine("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.entry_sidecar()["entry"]["3"]["estimate"]["man_hours"], 5)

    def test_leftover_v6_shim_is_reported_and_left_alone(self):
        """Review Focus 2: v7 does not retire bmad-create-story, so setup never offers to
        remove it (spec §13.5). The plan names it; the migration never deletes it."""
        self.make("v6-shim")
        shim = os.path.join(self.root, ".claude", "skills", "bmad-create-story", "SKILL.md")
        code, out, err = self.run_engine("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertIn("bmad-create-story", out)
        self.assertTrue(os.path.isfile(shim))


if __name__ == "__main__":
    unittest.main()
