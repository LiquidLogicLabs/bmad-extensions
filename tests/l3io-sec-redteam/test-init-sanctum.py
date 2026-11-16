#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Unit tests for init-sanctum.py."""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).parent.parent.parent / "skills" / "l3io-sec" / "l3io-sec-redteam" / "scripts" / "init-sanctum.py"
_spec = importlib.util.spec_from_file_location("init_sanctum", _SCRIPT)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


# -- temp-dir leak guard ---------------------------------------------------------------- #
# setUpModule points tempfile.tempdir (this test process) AND the TMPDIR environment variable
# (inherited by every subprocess it spawns) at one private run directory; tearDownModule fails
# the run if anything is left in it, then removes it and restores both to their prior values.
# Covered: every tempfile.mkdtemp()/mkstemp()/NamedTemporaryFile() made by this process or by
# a child that honours TMPDIR. Not covered: a child that writes to a hard-coded directory. The
# one name it ignores is `uv-*.lock`, which `uv run` leaves in TMPDIR by design
# (test-write-module-config spawns `uv run`). Fixtures without cleanup once left 60,936
# directories in /tmp and exhausted its inodes. Set in setUpModule, not at import, so a child
# process that re-imports this module never creates a run directory it would not remove.
_RUN_TMP = None
_PREV_TMPDIR = None             # the TMPDIR environment variable, or None
_PREV_TEMPFILE_TEMPDIR = None   # tempfile.tempdir as it was before setUpModule


def setUpModule():
    global _RUN_TMP, _PREV_TMPDIR, _PREV_TEMPFILE_TEMPDIR
    _PREV_TEMPFILE_TEMPDIR = tempfile.tempdir
    _RUN_TMP = tempfile.mkdtemp(prefix="test-init-sanctum-")
    tempfile.tempdir = _RUN_TMP
    _PREV_TMPDIR = os.environ.get("TMPDIR")
    os.environ["TMPDIR"] = _RUN_TMP


def tearDownModule():
    tempfile.tempdir = _PREV_TEMPFILE_TEMPDIR
    if _PREV_TMPDIR is None:
        os.environ.pop("TMPDIR", None)
    else:
        os.environ["TMPDIR"] = _PREV_TMPDIR
    leaked = sorted(n for n in os.listdir(_RUN_TMP)
                    if not (n.startswith("uv-") and n.endswith(".lock")))
    shutil.rmtree(_RUN_TMP, ignore_errors=True)
    if leaked:
        raise AssertionError(f"temp-dir leak: {len(leaked)} entr"
                             f"{'y' if len(leaked) == 1 else 'ies'} left by tests without "
                             f"cleanup: {', '.join(leaked[:5])}")


_SKILL = _SCRIPT.parent.parent
# Config keys BMad v7's resolver does not return. A rendered sanctum must not carry one as an
# unsubstituted placeholder, and the script must not ask for one.
_V6_ONLY_KEYS = ("user_name", "communication_language", "document_output_language")


def _run_main(argv: list[str]) -> dict:
    saved_argv = sys.argv
    sys.argv = ["init-sanctum.py", *argv]
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            m.main()
    finally:
        sys.argv = saved_argv
    return json.loads(stdout.getvalue())


class TestNoConfig(unittest.TestCase):
    """The sanctum is born on BMad v7, whose core config has no user name and no language.

    These run the real templates and references from the skill, so a placeholder added to any
    of them later is caught here rather than in a user's BOND.md.
    """

    def test_no_rendered_file_carries_a_v6_only_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            result = _run_main([str(project_root), str(_SKILL), "--json"])
            self.assertEqual(result["status"], "created")
            self.assertEqual(result["warnings"], [])
            sanctum = project_root / "_bmad" / "memory" / m.SKILL_NAME
            rendered = sorted(sanctum.rglob("*.md"))
            self.assertTrue(rendered, "the sanctum rendered no markdown at all")
            for path in rendered:
                text = path.read_text()
                for key in _V6_ONLY_KEYS:
                    self.assertNotIn("{" + key + "}", text, f"{path.name} carries {{{key}}}")

    def test_no_skill_source_names_a_v6_only_key(self):
        sources = [*sorted((_SKILL / "assets").glob("*-template.md")),
                   _SKILL / "references" / "first-breath.md", _SCRIPT]
        for path in sources:
            text = path.read_text()
            for key in _V6_ONLY_KEYS:
                self.assertNotIn(key, text, f"{path.name} names {key}")

    def test_the_name_and_language_flags_are_gone(self):
        for flag in ("--user-name", "--communication-language"):
            with tempfile.TemporaryDirectory() as tmp, \
                    contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as caught:
                _run_main([tmp, str(_SKILL), "--json", flag, "x"])
            self.assertEqual(caught.exception.code, 2, flag)

    def test_the_config_resolver_is_not_run(self):
        """Nothing the sanctum renders comes from config, so resolving it would be dead work."""
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            marker = project_root / "resolver-ran"
            resolver = project_root / "_bmad" / "scripts" / "resolve_config.py"
            resolver.parent.mkdir(parents=True)
            resolver.write_text("from pathlib import Path\n"
                                f"Path({str(marker)!r}).write_text('ran')\n"
                                "print('{}')\n")
            _run_main([str(project_root), str(_SKILL), "--json"])
            self.assertFalse(marker.exists(), "init-sanctum.py ran the config resolver")


class TestParseFrontmatter(unittest.TestCase):
    def test_extracts_fields(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("---\nname: test-cap\ncode: TC\ndescription: A test capability\n---\n\n# Body\n")
            path = Path(f.name)
            self.addCleanup(path.unlink, missing_ok=True)
        result = m.parse_frontmatter(path)
        self.assertEqual(result["name"], "test-cap")
        self.assertEqual(result["code"], "TC")

    def test_no_frontmatter_returns_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# No frontmatter here\n")
            path = Path(f.name)
            self.addCleanup(path.unlink, missing_ok=True)
        result = m.parse_frontmatter(path)
        self.assertEqual(result, {})


class TestSubstituteVars(unittest.TestCase):
    def test_replaces_placeholders(self):
        result = m.substitute_vars("At {project_root}, born {birth_date}", {"project_root": "/p", "birth_date": "2026-01-01"})
        self.assertEqual(result, "At /p, born 2026-01-01")

    def test_unknown_placeholder_left_intact(self):
        result = m.substitute_vars("Hello {unknown}", {"birth_date": "2026-01-01"})
        self.assertIn("{unknown}", result)


class TestGenerateCapabilitiesMd(unittest.TestCase):
    def test_generates_table_rows(self):
        caps = [{"code": "SM", "name": "Scope Mapping", "description": "Maps attack surface", "source": "references/scope-mapping.md"}]
        output = m.generate_capabilities_md(caps)
        self.assertIn("SM", output)
        self.assertIn("Scope Mapping", output)
        self.assertIn("WebSearch", output)


class TestDiscoverCapabilities(unittest.TestCase):
    def test_discovers_capability_with_frontmatter(self):
        with tempfile.TemporaryDirectory() as d:
            cap = Path(d) / "scope-mapping.md"
            cap.write_text("---\nname: scope-mapping\ncode: SM\ndescription: Maps attack surface\n---\n\n# Body\n")
            result = m.discover_capabilities(Path(d), "./references")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["code"], "SM")

    def test_ignores_files_without_code(self):
        with tempfile.TemporaryDirectory() as d:
            cap = Path(d) / "notes.md"
            cap.write_text("---\nname: notes\n---\n\n# Body\n")
            result = m.discover_capabilities(Path(d), "./references")
        self.assertEqual(len(result), 0)


class TestSanctumCreation(unittest.TestCase):
    def test_creates_sanctum_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            skill_path = Path(tmp) / "skill"

            # Minimal skill structure
            (skill_path / "assets").mkdir(parents=True)
            (skill_path / "references").mkdir()

            # Stub template carrying a placeholder, to verify substitution happens
            (skill_path / "assets" / "INDEX-template.md").write_text("# Index\n{birth_date}\n")

            # A capability reference file, to verify copy_references runs for real
            (skill_path / "references" / "scope-mapping.md").write_text(
                "---\nname: scope-mapping\ncode: SM\ndescription: Maps attack surface\n---\n\n# Body\n"
            )

            (project_root / "_bmad").mkdir(parents=True)

            sanctum = project_root / "_bmad" / "memory" / m.SKILL_NAME
            self.assertFalse(sanctum.exists(), "sanctum must not exist before main() runs")

            # Patch TEMPLATE_FILES for this test (the fixture only stubs INDEX)
            original = m.TEMPLATE_FILES
            m.TEMPLATE_FILES = ["INDEX-template.md"]
            saved_argv = sys.argv
            sys.argv = ["init-sanctum.py", str(project_root), str(skill_path), "--json"]
            stdout = io.StringIO()
            try:
                with contextlib.redirect_stdout(stdout):
                    m.main()
            finally:
                m.TEMPLATE_FILES = original
                sys.argv = saved_argv

            # main() reports the run it actually performed
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["status"], "created")
            self.assertEqual(result["warnings"], [])
            self.assertIn("INDEX.md", result["created"])
            self.assertIn("references/scope-mapping.md", result["created"])

            # The sanctum now exists on disk, with the subdirectories First Breath promises
            self.assertTrue(sanctum.is_dir())
            self.assertTrue((sanctum / "sessions").is_dir())
            self.assertTrue((sanctum / "research-cache").is_dir())

            # The template landed and its placeholder was substituted
            index_content = (sanctum / "INDEX.md").read_text()
            self.assertNotIn("{birth_date}", index_content)
            self.assertRegex(index_content, r"\d{4}-\d{2}-\d{2}")

            # The reference file was copied into the sanctum, unmodified
            self.assertEqual(
                (sanctum / "references" / "scope-mapping.md").read_text(),
                (skill_path / "references" / "scope-mapping.md").read_text(),
            )


if __name__ == "__main__":
    unittest.main()
