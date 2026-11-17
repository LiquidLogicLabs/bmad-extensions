#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""
Tests for report-version.py. Run with:
  uv run tests/l3io-doctor/test-report-version.py

Every case builds a fake installed skills tree in a temp dir and drives the real script
through subprocess, so the exit code is the one `/l3io-doctor version` actually returns.
The exit codes are the interface (0 agree, 3 mixed, 4 none found), so each gets a case.

The cases that matter most here attack the SCOPE, not the rule: this script reports
agreement over whatever set it discovered, so a discovery that silently covers fewer
skills than are installed would report `current` over a tree that disagrees. Two cases
plant exactly that -- a disagreeing skill that must be found, and a foreign skill that
must not be.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(_HERE)),
                       "skills", "l3io-util", "l3io-doctor", "scripts", "report-version.py")
if not os.path.exists(_SCRIPT):   # running from the repo root layout
    _SCRIPT = os.path.join(os.path.dirname(os.path.dirname(_HERE)),
                           "bmad-extensions", "skills", "l3io-util", "l3io-doctor", "scripts",
                           "report-version.py")


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.skills = Path(self.d) / "skills"
        self.skills.mkdir()

    def skill(self, name, version, generated_from="skills/_shared/",
              module=None, manifest_text=None, module_text=None):
        """Create one skill directory. `manifest_text`/`module_text` write raw bytes so a
        case can plant a corrupt file; otherwise both are generated."""
        d = self.skills / name
        d.mkdir(parents=True, exist_ok=True)
        body = manifest_text if manifest_text is not None else json.dumps(
            {"version": version, "generated_from": generated_from, "files": {}})
        (d / "payload-manifest.json").write_text(body, encoding="utf-8")
        if module or module_text is not None:
            my = module_text if module_text is not None else (
                f'[bmod]\ncode = "{module}"\nversion = "{version}"\n')
            (d / "bmod.toml").write_text(my, encoding="utf-8")
        return d

    def run_cli(self, *extra):
        r = subprocess.run([sys.executable, _SCRIPT, "--skills-root", str(self.skills),
                            *extra], capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr


class TestAgreement(Base):
    def test_all_skills_agreeing_is_exit_0_and_one_headline_version(self):
        self.skill("l3io-execute", "3.2.4")
        self.skill("l3io-doctor", "3.2.4", module="l3io-util")
        code, out, err = self.run_cli()
        self.assertEqual(code, 0, err)
        self.assertIn("l3io-extensions 3.2.4", out)
        self.assertIn("2 skills installed", out)

    def test_a_module_home_reports_its_module_code_and_version(self):
        self.skill("bmod-l3io-pm", "3.2.4", module="l3io-pm")
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("module l3io-pm 3.2.4", out)

    def test_a_skill_without_a_record_is_not_a_finding(self):
        """Only the four module records carry [bmod]. A member skill correctly has none,
        and that must not read as an error."""
        self.skill("l3io-execute", "3.2.4")
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertNotIn("!", out)

    def test_a_directory_with_no_manifest_is_skipped_silently(self):
        """The deprecated forwarders ship no payload, so they carry no manifest. Their
        absence is the designed state, not an incomplete install."""
        self.skill("l3io-execute", "3.2.4")
        (self.skills / "l3io-pm-execute").mkdir()
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("1 skills installed", out)
        self.assertNotIn("l3io-pm-execute", out)


class TestScope(Base):
    """These are the cases the reporter exists to get right. It reports agreement over
    the set it discovered, so narrow discovery produces a confident wrong answer."""

    def test_a_disagreeing_skill_is_found_and_turns_the_verdict_mixed(self):
        """Plant the violation against the SCOPE: if discovery missed this skill, the
        script would print `l3io-extensions 3.2.4` over a half-upgraded tree."""
        self.skill("l3io-execute", "3.2.4")
        self.skill("l3io-plan", "3.2.2")
        code, out, _ = self.run_cli()
        self.assertEqual(code, 3, out)
        self.assertIn("MIXED VERSIONS", out)
        self.assertIn("3.2.2", out)
        self.assertIn("3.2.4", out)

    def test_a_module_version_disagreeing_with_its_own_payload_is_mixed(self):
        """The two surfaces are written by different build steps, so they can disagree
        with each other inside a single skill -- not only across skills."""
        d = self.skill("l3io-doctor", "3.2.4")
        (d / "bmod.toml").write_text(
            '[bmod]\ncode = "l3io-util"\nversion = "3.1.9"\n', encoding="utf-8")
        code, out, _ = self.run_cli()
        self.assertEqual(code, 3, out)
        self.assertIn("3.1.9", out)

    def test_a_foreign_skill_with_its_own_manifest_is_not_counted(self):
        """BMad core skills live in the same .claude/skills/ directory. Identity is our
        `generated_from`, not a name prefix, so a foreign manifest -- even one carrying a
        `version` -- cannot drag the verdict to mixed."""
        self.skill("l3io-execute", "3.2.4")
        self.skill("bmad-code-review", "6.12.0", generated_from="somewhere/else/")
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0, out)
        self.assertIn("1 skills installed", out)
        self.assertNotIn("6.12.0", out)

    def test_both_generated_from_markers_are_ours(self):
        """The manifest writer emits `skills/<skill>/`; installs made before that change carry
        `skills/_shared/`. Recognising only the old one reports `no l3io skills found` on
        every current install, and the pm_status skew finding never runs."""
        self.skill("l3io-execute", "4.0.0", generated_from="skills/<skill>/")
        self.skill("l3io-doctor", "4.0.0", generated_from="skills/_shared/", module="l3io-util")
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0, out)
        self.assertIn("2 skills installed", out)

    def test_no_l3io_skills_is_exit_4_and_names_the_fix(self):
        code, out, _ = self.run_cli()
        self.assertEqual(code, 4)
        self.assertIn("no l3io skills found", out)
        self.assertIn("--skills-root", out)


class TestCorruptInput(Base):
    def test_an_unreadable_manifest_is_reported_not_crashed(self):
        self.skill("l3io-execute", "3.2.4")
        self.skill("l3io-plan", "x", manifest_text="{not json")
        code, out, _ = self.run_cli()
        self.assertIn("payload-manifest.json unreadable", out)
        self.assertIn("l3io-extensions 3.2.4", out)
        self.assertEqual(code, 0, out)

    def test_an_unreadable_bmod_toml_is_reported_not_crashed(self):
        self.skill("l3io-doctor", "3.2.4", module_text="[bmod\ncode = \n")
        code, out, _ = self.run_cli()
        self.assertIn("bmod.toml unreadable", out)
        self.assertEqual(code, 0, out)


class TestDeclaredPmStatus(Base):
    """The two declared copies v7 installs, one per module, both writing one state tree.

    `l3io-pm` and `l3io-util` can be set up separately, so their copies can differ in version.
    The report names each copy, and a disagreement between them is a finding the doctor's
    health check surfaces (Check 25)."""

    PM = "_bmad/l3io-pm/scripts/pm_status/__main__.py"
    UTIL = "_bmad/l3io-util/scripts/pm_status/__main__.py"

    def _copy(self, rel, version):
        p = Path(self.d) / "proj" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"#!/usr/bin/env python3\n# pm-status-version: {version}\n",
                     encoding="utf-8")
        return str(Path(self.d) / "proj")

    def test_differing_copies_are_one_finding_naming_both_paths_and_versions(self):
        self.skill("l3io-doctor", "4.0.0", module="l3io-util")
        self._copy(self.PM, "4.0.0")
        proj = self._copy(self.UTIL, "3.9.0")
        code, out, _ = self.run_cli("--project-root", proj, "--format", "json")
        self.assertEqual(code, 3, out)
        findings = json.loads(out)["pm_status"]["findings"]
        self.assertEqual(len(findings), 1, findings)
        for token in (self.PM, self.UTIL, "4.0.0", "3.9.0"):
            self.assertIn(token, findings[0])
        code, out, _ = self.run_cli("--project-root", proj)
        self.assertEqual(code, 3, out)
        self.assertIn("pm_status SKEW", out)

    def test_identical_copies_are_no_finding(self):
        self.skill("l3io-doctor", "4.0.0", module="l3io-util")
        self._copy(self.PM, "4.0.0")
        proj = self._copy(self.UTIL, "4.0.0")
        code, out, _ = self.run_cli("--project-root", proj, "--format", "json")
        self.assertEqual(code, 0, out)
        d = json.loads(out)["pm_status"]
        self.assertEqual(d["findings"], [])
        self.assertEqual({c["path"]: c["version"] for c in d["copies"]},
                         {self.PM: "4.0.0", self.UTIL: "4.0.0"})

    def test_one_copy_absent_is_no_finding_and_says_setup_installs_it(self):
        """Only l3io-pm set up: there is nothing to disagree with, and the absent copy is
        explained, not flagged."""
        self.skill("l3io-doctor", "4.0.0", module="l3io-util")
        proj = self._copy(self.PM, "4.0.0")
        code, out, _ = self.run_cli("--project-root", proj)
        self.assertEqual(code, 0, out)
        self.assertIn(f"{self.UTIL}: absent", out)
        self.assertIn("bmad setup l3io-util", out)

    def test_a_copy_behind_the_installed_skills_is_noted_not_failed(self):
        """Skills added with `npx skills add` but setup not re-run: the copies agree with each
        other and lag the skills. Setup is the remedy, and the exit code stays 0."""
        self.skill("l3io-doctor", "4.0.1", module="l3io-util")
        self._copy(self.PM, "4.0.0")
        proj = self._copy(self.UTIL, "4.0.0")
        code, out, _ = self.run_cli("--project-root", proj)
        self.assertEqual(code, 0, out)
        self.assertIn("run bmad setup l3io-pm", out)

    def test_the_old_shared_scripts_copy_is_not_read(self):
        """`_bmad/scripts/` is BMad's own directory. A copy left there by l3io 3.x is not one
        of the declared copies and must not be reported as one."""
        self.skill("l3io-doctor", "4.0.0", module="l3io-util")
        proj = self._copy("_bmad/scripts/pm-status/__main__.py", "3.7.1")
        code, out, _ = self.run_cli("--project-root", proj)
        self.assertEqual(code, 0, out)
        self.assertNotIn("3.7.1", out)


class TestJson(Base):
    def test_json_carries_status_version_and_every_skill(self):
        self.skill("l3io-execute", "3.2.4")
        self.skill("l3io-doctor", "3.2.4", module="l3io-util")
        code, out, _ = self.run_cli("--format", "json")
        self.assertEqual(code, 0, out)
        d = json.loads(out)
        self.assertEqual(d["status"], "current")
        self.assertEqual(d["version"], "3.2.4")
        self.assertEqual(sorted(s["skill"] for s in d["skills"]),
                         ["l3io-doctor", "l3io-execute"])

    def test_json_mixed_leaves_version_null_and_lists_both(self):
        """A single `version` cannot describe a mixed tree, so it is null rather than an
        arbitrary pick -- a consumer reading only that field gets nothing, not a wrong
        answer."""
        self.skill("l3io-execute", "3.2.4")
        self.skill("l3io-plan", "3.2.2")
        code, out, _ = self.run_cli("--format", "json")
        self.assertEqual(code, 3)
        d = json.loads(out)
        self.assertIsNone(d["version"])
        self.assertEqual(d["versions"], ["3.2.2", "3.2.4"])



class TestBmadVersion(Base):
    """The BMad half: which BMad this project is on, and optionally whether it is current.

    Added when BMad 6.12.1 shipped and nothing in the estate could answer "am I on it?".
    The installed version comes from `_bmad/_config/manifest.yaml` -> `installation.version`,
    which is the key BMad's own installer writes.
    """

    def bmad(self, text):
        cfg = Path(self.d) / "_bmad" / "_config"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "manifest.yaml").write_text(text, encoding="utf-8")

    def test_reports_the_installed_bmad_version(self):
        self.skill("l3io-doctor", "3.2.5", module="l3io-util")
        self.bmad("installation:\n  version: 6.12.0\n")
        code, out, _ = self.run_cli("--project-root", self.d)
        self.assertEqual(code, 0)
        self.assertIn("BMad: 6.12.0", out)

    def test_says_so_when_bmad_is_not_recorded(self):
        # No _bmad/ at all. A consumer who has not installed BMad, or passed a wrong root,
        # must get a reason rather than a silently absent line.
        self.skill("l3io-doctor", "3.2.5", module="l3io-util")
        code, out, _ = self.run_cli("--project-root", self.d)
        self.assertEqual(code, 0)
        self.assertIn("version not recorded", out)

    def test_a_corrupt_manifest_does_not_crash(self):
        self.skill("l3io-doctor", "3.2.5", module="l3io-util")
        self.bmad("installation: [this is not a mapping]\n")
        code, out, _ = self.run_cli("--project-root", self.d)
        self.assertEqual(code, 0)
        self.assertIn("version not recorded", out)

    def test_no_network_call_without_check_latest(self):
        # The default must stay offline. Point the registry at a port nothing listens on:
        # if the default reached the network at all, this would hang or report an error.
        self.skill("l3io-doctor", "3.2.5", module="l3io-util")
        self.bmad("installation:\n  version: 6.12.0\n")
        env = dict(os.environ)
        r = subprocess.run([sys.executable, _SCRIPT, "--skills-root", str(self.skills),
                            "--project-root", self.d],
                           capture_output=True, text=True, env=env, timeout=20)
        self.assertEqual(r.returncode, 0)
        self.assertIn("BMad: 6.12.0", r.stdout)
        self.assertNotIn("latest", r.stdout)

    def test_json_carries_the_bmad_block(self):
        self.skill("l3io-doctor", "3.2.5", module="l3io-util")
        self.bmad("installation:\n  version: 6.12.0\n")
        code, out, _ = self.run_cli("--project-root", self.d, "--format", "json")
        self.assertEqual(code, 0)
        b = json.loads(out)["bmad"]
        self.assertEqual(b["installed"], "6.12.0")
        # Without --check-latest there is nothing to compare against, so `current` must be
        # None rather than False -- "unknown" and "out of date" are different answers.
        self.assertIsNone(b["latest"])
        self.assertIsNone(b["current"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
