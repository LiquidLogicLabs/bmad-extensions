#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["tomlkit>=0.13", "jinja2>=3.1"]
# ///
"""
R6, proved through BMad v7's own code. Run with:
  uv run tests/l3io-doctor/test-lenses.py

The project is built the way `bmad setup` builds one: every file a module declares under
`[skill] scripts` is copied to `_bmad/<module>/scripts/<path>`. Then the shipped
`assets/wire-in.toml` is applied by the real `wire-in.py`, and each host's customization is
merged and type-checked by v7's own `config_utils.load_customization` and `render_skill.py`
(`_check_persistent_layers`, `_resolve_customization_value`), fetched at the pin through
`scripts/fetch-bmad-tool.mjs` and SHA-256-verified. An undeclared key or a wrong type fails
here exactly as it would halt the host's render.
"""
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SKILLS = _REPO / "skills"
_WIRE = _SKILLS / "l3io-util" / "l3io-doctor" / "scripts" / "wire-in.py"
_ASSET = _SKILLS / "l3io-util" / "l3io-doctor" / "assets" / "wire-in.toml"

# Spec §5.2.
ENGINEERING = ("l3io-design-integrity", "l3io-testability", "l3io-dependency-policy",
               "l3io-observability", "l3io-stack-rules")
THREAT = ("l3io-threat-external", "l3io-threat-insider", "l3io-threat-chaos",
          "l3io-threat-abuse", "l3io-threat-design", "l3io-ai-poisoning")
ELEVEN = ENGINEERING + THREAT

HOSTS = {
    "bmad-review": "skills/core-tools/bmad-review/customize.toml",
    "bmad-code-review": "skills/method/bmad-code-review/customize.toml",
    "bmad-build": "skills/method/bmad-build/customize.toml",
    "bmad-build-auto": "skills/method/bmad-build-auto/customize.toml",
    "bmad-architecture": "skills/method/bmad-architecture/customize.toml",
    "bmad-retrospective": "skills/method/bmad-retrospective/customize.toml",
}
V7_SCRIPTS = ("skills/core-tools/bmad/scripts/config_utils.py",
              "skills/core-tools/bmad/scripts/render_skill.py")
INSTALLED = re.compile(r"\{project-root\}/(_bmad/l3io-[a-z]+/scripts/[A-Za-z0-9_./-]+)")


def fetch(rel: str) -> Path:
    pin = subprocess.run(
        ["node", "--input-type=module", "-e",
         'import { PIN } from "./scripts/fetch-bmad-tool.mjs"; console.log(PIN)'],
        cwd=_REPO, capture_output=True, text=True, check=True).stdout.strip()
    p = subprocess.run(["node", "scripts/fetch-bmad-tool.mjs", pin, rel],
                       cwd=_REPO, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"fetch-bmad-tool {rel}: {p.stderr.strip()}")
    return Path(p.stdout.strip())


def setup_install(project: Path) -> None:
    """Copy every declared script to where v7's setup installs it (setup.py:2385-2390)."""
    for bmod in sorted(_SKILLS.glob("*/*/bmod.toml")):
        module = bmod.parent.parent.name
        for rel in tomllib.loads(bmod.read_text()).get("skill", {}).get("scripts", []):
            dest = project / "_bmad" / module / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bmod.parent / rel, dest)


class R6(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        v7 = cls.tmp / "v7"
        (v7 / "scripts").mkdir(parents=True)
        for rel in V7_SCRIPTS:
            shutil.copyfile(fetch(rel), v7 / "scripts" / Path(rel).name)
        cls.skill_dirs = {}
        for host, rel in HOSTS.items():
            d = v7 / "skills" / host
            d.mkdir(parents=True)
            shutil.copyfile(fetch(rel), d / "customize.toml")
            cls.skill_dirs[host] = d
        sys.path.insert(0, str(v7 / "scripts"))
        spec = importlib.util.spec_from_file_location("render_skill", v7 / "scripts" / "render_skill.py")
        cls.render = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.render)
        import config_utils  # fetched above; on sys.path only now
        cls.config_utils = config_utils

        cls.project = cls.tmp / "proj"
        (cls.project / "_bmad" / "custom").mkdir(parents=True)
        setup_install(cls.project)
        p = subprocess.run([sys.executable, str(_WIRE), "wire", "--project-root", str(cls.project),
                            "--output-folder", str(cls.project / "_bmad-output")],
                           capture_output=True, text=True)
        cls.wire = p

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def merged(self, host: str) -> dict:
        """The host's effective [workflow], merged and type-checked as render_skill does."""
        skill_dir = self.skill_dirs[host]
        defaults = self.config_utils.load_toml(skill_dir / "customize.toml", required=True)
        self.render._check_persistent_layers(self.project, skill_dir, defaults)
        merged = self.config_utils.load_customization(self.project, skill_dir)
        team = self.config_utils.load_toml(self.project / "_bmad" / "custom" / f"{host}.toml")
        for key in team.get("workflow", {}):
            self.render._resolve_customization_value(
                merged["workflow"][key], defaults["workflow"][key], f"workflow.{key}")
        return merged["workflow"]

    def test_wire_applies_with_every_module_set_up(self):
        self.assertEqual(self.wire.returncode, 0, self.wire.stdout + self.wire.stderr)
        self.assertNotIn("skipped", self.wire.stdout)

    def test_r6_bmad_review_lists_all_eleven_codes(self):
        lenses = self.merged("bmad-review")["lenses"]
        codes = [lens["code"] for lens in lenses]
        for code in ELEVEN:
            self.assertEqual(codes.count(code), 1, code)
        self.assertIn("adversarial", codes, "BMad's own lenses survive the merge")

    def test_r6_thorough_lenses_list_all_eleven_ids(self):
        for host in ("bmad-code-review", "bmad-build", "bmad-build-auto"):
            with self.subTest(host=host):
                ids = [lens["id"] for lens in self.merged(host)["thorough_lenses"]]
                for code in ELEVEN:
                    self.assertEqual(ids.count(code), 1, f"{host}: {code}")
                self.assertIn("blind-hunter", ids)
                quick = [lens["id"] for lens in self.merged(host)["quick_lenses"]]
                self.assertFalse(any(i.startswith("l3io-") for i in quick), "quick review stays BMad's")

    def test_ai_poisoning_runs_after_external_threat(self):
        lenses = {lens["code"]: lens for lens in self.merged("bmad-review")["lenses"]}
        self.assertEqual(lenses["l3io-ai-poisoning"].get("after"), "l3io-threat-external")
        for code in ENGINEERING[3:]:
            self.assertEqual(lenses[code]["applies_to"], "code", code)
        for code in THREAT:
            self.assertTrue(lenses[code].get("when"), f"{code} carries a `when`")

    def test_r6_architecture_finalize_reviewers_include_ours(self):
        wf = self.merged("bmad-architecture")
        ours = [r for r in wf["finalize_reviewers"] if "_bmad/l3io-arch/scripts/" in r]
        self.assertEqual(len(ours), 1, wf["finalize_reviewers"])
        self.assertTrue(ours[0].startswith("file:"), ours[0])
        self.assertEqual(len(wf["finalize_reviewers"]), 3, "BMad's two reviewers survive")
        self.assertTrue(any("_bmad/l3io-arch/scripts/" in s for s in wf["external_sources"]))
        self.assertTrue(any("_bmad/l3io-arch/scripts/" in s for s in wf["doc_standards"]))
        self.assertIn("skill:bmad-review lenses=structure,prose", wf["doc_standards"])

    def test_retrospective_carries_the_spec_sync_fact(self):
        wf = self.merged("bmad-retrospective")
        self.assertTrue(any("_bmad/l3io-pm/scripts/facts/spec-sync.md" in f
                            for f in wf["persistent_facts"]), wf["persistent_facts"])
        self.assertIn("epic-close", wf["on_complete"], "Phase 4's closure hook is untouched")

    def test_every_installed_path_a_wired_value_names_exists(self):
        named = set()
        for e in tomllib.loads(_ASSET.read_text())["entry"]:
            if e.get("test_only"):
                continue
            text = e["value"] if isinstance(e["value"], str) else " ".join(e["value"].values())
            named |= set(INSTALLED.findall(text))
        self.assertTrue(any("l3io-arch" in n for n in named) and any("l3io-sec" in n for n in named))
        for rel in sorted(named):
            self.assertTrue((self.project / rel).is_file(), f"{rel} is named but bmad setup installs no such file")

    def test_lens_files_reference_only_installed_neighbours(self):
        """A lens file is loaded from _bmad/<module>/scripts/lenses/; whatever it names beside
        itself must be installed too, or the lens reads nothing."""
        for lens in sorted(self.project.glob("_bmad/l3io-*/scripts/lenses/*.md")):
            for ref in re.findall(r"`(\.\./[A-Za-z0-9_./-]+\.md)", lens.read_text()):
                self.assertTrue((lens.parent / ref).resolve().is_file(), f"{lens.name} names {ref}")
        installed = {p.stem for p in self.project.glob("_bmad/l3io-*/scripts/lenses/*.md")}
        self.assertEqual(installed, set(ELEVEN))

    def test_unwire_restores_every_team_file(self):
        p = subprocess.run([sys.executable, str(_WIRE), "unwire", "--project-root", str(self.project),
                            "--output-folder", str(self.project / "_bmad-output")],
                           capture_output=True, text=True)
        try:
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(list((self.project / "_bmad" / "custom").iterdir()), [],
                             "every team file wire created is removed")
        finally:
            again = subprocess.run([sys.executable, str(_WIRE), "wire", "--project-root", str(self.project),
                                    "--output-folder", str(self.project / "_bmad-output")],
                                   capture_output=True, text=True)
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)


if __name__ == "__main__":
    unittest.main()
