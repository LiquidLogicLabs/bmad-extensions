#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Tests for install.sh. Run with:
  uv run tests/l3io-doctor/test-l3io-install.py

Every case drives the real script through bash. `--dry-run` is used wherever the action
would otherwise invoke `npx`, so the tests assert the COMMANDS the script chose without a
network call.

The refusals are the other half, and they are not conveniences: an install onto a project
without BMad v7 has nothing for the modules to attach to, an upgrade with no install has
nothing to upgrade, and a clean with no payload has no manifest to decide what is safe to
delete. So each refusal gets a case, and each asserts the exit
code as well as the message, because a refusal that printed advice and exited 0 would let a
caller's `&&` chain carry on as though it had worked.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
# The repo root: install.sh is NOT payload. A first install cannot come from payload --
# there is none yet -- so the entry point that must work on an empty tree lives at the root
# and is fetchable on its own.
_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "install.sh")


class Base(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)

    def v7(self):
        """What `bmad setup` leaves to mark BMad v7 installed: its own setup script."""
        p = self.d / "_bmad" / "scripts"
        p.mkdir(parents=True, exist_ok=True)
        (p / "setup.py").write_text("# v7's setup.py\n", encoding="utf-8")

    def l3io(self):
        """An installed l3io: the doctor's skill folder, where `skills add` puts it."""
        p = self.d / ".agents" / "skills" / "l3io-doctor"
        p.mkdir(parents=True, exist_ok=True)
        (p / "SKILL.md").write_text("---\nname: l3io-doctor\n---\n", encoding="utf-8")

    def run_sh(self, *args, directory=True):
        argv = ["bash", _SCRIPT, *args]
        if directory:
            argv += ["--directory", str(self.d)]
        r = subprocess.run(argv, capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr


class TestInstall(Base):
    def test_install_adds_each_module_folder(self):
        """R1: each module installs with `npx skills add <owner>/<repo>/skills/<code>`."""
        self.v7()
        code, out, err = self.run_sh("--action", "install", "--dry-run")
        self.assertEqual(code, 0, out + err)
        for m in ("l3io-pm", "l3io-util", "l3io-sec", "l3io-arch"):
            self.assertIn(f"skills add LiquidLogicLabs/bmad-extensions/skills/{m} ", out)
        self.assertNotIn("_shared", out)
        self.assertNotIn("bmad-method", out)
        self.assertIn("bmad setup", err)
        self.assertIn("/l3io-doctor wire", err)

    def test_install_refuses_without_bmad_v7(self):
        code, _, err = self.run_sh("--action", "install", "--dry-run")
        self.assertEqual(code, 2)
        self.assertIn("BMad v7 is not installed", err)

    def test_modules_tools_and_source_are_overridable(self):
        self.v7()
        _, out, _ = self.run_sh("--action", "install", "--dry-run", "--modules", "l3io-util",
                                "--tools", "claude-code,codex", "--source", "/tmp/fork")
        self.assertIn("skills add /tmp/fork/skills/l3io-util -s * -a claude-code -a codex", out)
        self.assertNotIn("l3io-pm", out)

    def test_shared_is_never_a_module(self):
        self.v7()
        code, _, err = self.run_sh("--action", "install", "--dry-run", "--modules", "_shared")
        self.assertEqual(code, 2)
        self.assertIn("not a module", err)


class TestUpgrade(Base):
    def test_upgrade_re_adds_the_modules(self):
        self.v7()
        self.l3io()
        code, out, err = self.run_sh("--action", "upgrade", "--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertIn("skills add LiquidLogicLabs/bmad-extensions/skills/l3io-pm", out)

    def test_upgrade_refuses_when_nothing_is_installed(self):
        self.v7()
        code, _, err = self.run_sh("--action", "upgrade")
        self.assertEqual(code, 2)
        self.assertIn("no l3io install found", err)
        self.assertIn("--action install", err)

    def test_upgrade_refuses_a_bmad_6_project(self):
        self.l3io()
        code, _, err = self.run_sh("--action", "upgrade")
        self.assertEqual(code, 2)
        self.assertIn("BMad v7 only", err)


class TestClean(Base):
    def test_clean_refuses_when_nothing_is_installed(self):
        """No manifest means no way to decide what is safe to delete, and guessing is how an
        over-broad delete happens."""
        code, out, err = self.run_sh("--action", "clean")
        self.assertEqual(code, 2)
        self.assertIn("no l3io install found", err)

    def payload(self, with_helper=True):
        """A minimal installed payload: one shipped file, the manifest claiming it, and the
        clean helper itself. Built by hand because no verb of ours installs skills -- the
        installer does -- and `install.sh` is not payload, so it has to FIND the helper in
        the installed tree rather than beside itself."""
        import hashlib
        import json
        d = self.d / ".claude" / "skills" / "l3io-doctor" / "scripts"
        d.mkdir(parents=True, exist_ok=True)
        (d / "a.py").write_text("payload\n", encoding="utf-8")
        h = hashlib.sha256(b"payload\n").hexdigest()
        (d.parent / "payload-manifest.json").write_text(json.dumps(
            {"version": "3.2.4", "generated_from": "skills/_shared/",
             "files": {"scripts/a.py": h}}), encoding="utf-8")
        if with_helper:
            real = os.path.join(os.path.dirname(os.path.dirname(_HERE)),
                                "skills", "l3io-util", "l3io-doctor", "scripts", "clean-payload.py")
            shutil.copy(real, d / "clean-payload.py")

    def test_clean_is_a_dry_run_without_apply(self):
        self.payload()
        code, out, err = self.run_sh("--action", "clean")
        self.assertEqual(code, 0, out + err)
        self.assertIn("Would remove", out)
        self.assertIn("Re-run with --apply", out + err)
        self.assertTrue((self.d / ".claude/skills/l3io-doctor/scripts/a.py").exists())

    def test_the_helpers_exit_code_propagates(self):
        """`set -e` carries the helper's status out, so a caller's `&&` chain stops rather
        than treating "nothing found" as done.

        Reaching exit 4 through install.sh needs the helper present with no valid manifest
        beside it -- a half-removed payload. That is reachable and real: the manifest is
        itself removable payload, so an interrupted clean can leave exactly this shape."""
        self.payload()
        os.remove(self.d / ".claude/skills/l3io-doctor/payload-manifest.json")
        code, out, _ = self.run_sh("--action", "clean")
        self.assertEqual(code, 4)
        self.assertIn("no l3io payload found", out)

    def test_clean_says_so_when_the_helper_is_absent(self):
        """The helper is payload, so a tree whose payload is already gone has nothing to
        decide the delete with. That is a clear message, not a missing-file crash."""
        self.payload(with_helper=False)
        code, _, err = self.run_sh("--action", "clean")
        self.assertEqual(code, 2)
        self.assertIn("no clean-payload.py found", err)

    def test_clean_dry_run_names_the_helper_it_would_call(self):
        """The hash comparison lives in Python because JSON plus hashing over a derived file
        set has outgrown shell (standards-shell.md). The dispatch is still visible."""
        self.payload()
        _, out, _ = self.run_sh("--action", "clean", "--dry-run")
        self.assertIn("clean-payload.py", out)

    def test_apply_is_forwarded(self):
        self.payload()
        _, out, _ = self.run_sh("--action", "clean", "--dry-run", "--apply")
        self.assertIn("--apply", out)


class TestArguments(Base):
    def test_action_is_required_with_no_default(self):
        """There is no safe default: the right command depends on whether the project is
        already installed, and choosing wrong in either direction is destructive."""
        code, out, err = self.run_sh()
        self.assertEqual(code, 2)
        self.assertIn("--action is required", err)

    def test_an_unknown_action_is_refused(self):
        code, _, err = self.run_sh("--action", "sideways")
        self.assertEqual(code, 2)
        self.assertIn("unknown --action", err)

    def test_an_unknown_flag_is_refused_rather_than_ignored(self):
        """A silently ignored flag is how somebody believes they passed --apply."""
        code, _, err = self.run_sh("--action", "upgrade", "--wat")
        self.assertEqual(code, 2)
        self.assertIn("unknown argument", err)

    def test_a_flag_missing_its_value_is_refused(self):
        code, _, err = self.run_sh("--action", directory=False)
        self.assertEqual(code, 2)
        self.assertIn("needs a value", err)

    def test_equals_form_is_accepted(self):
        self.v7()
        code, out, err = self.run_sh("--action=install", "--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertIn("skills add", out)

    def test_a_missing_directory_is_refused(self):
        code, _, err = self.run_sh("--action", "upgrade", "--directory",
                                   str(self.d / "nope"), directory=False)
        self.assertEqual(code, 2)
        self.assertIn("does not exist", err)

    def test_help_exits_zero_and_describes_all_three_actions(self):
        code, out, _ = self.run_sh("--help", directory=False)
        self.assertEqual(code, 0)
        for word in ("install", "upgrade", "clean"):
            self.assertIn(word, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
