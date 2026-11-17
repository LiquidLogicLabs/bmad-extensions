#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18", "tomlkit>=0.13"]
# ///
"""
Tests for pm-status.py — run with: uv run test-pm-status.py
Exercises the value logic of set-actual/set-estimate/add-test-run/verify (through a v7
ticket, see TestLayoutResolution), adr-reserve, calibration and the estimate engine, the
events.jsonl log, notices, the agent-instructions block, and verify exit codes. The v7
sidecar addressing itself is in test-pm-status-sidecar.py.
"""
import argparse
import ast
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "pm_status", "__main__.py")

sys.path.insert(0, os.path.dirname(HERE))
import pm_status as pm

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
    _RUN_TMP = tempfile.mkdtemp(prefix="test-pm-status-")
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


class Base(unittest.TestCase):
    """Minimal fixture: a scratch dir + in-process CLI runner. No status-file
    content is assumed here — commands that need a node tree use
    TestLayoutResolution instead."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)

    def run_main(self, argv):
        """Call main() in-process; return (exit_code, stdout)."""
        buf = io.StringIO()
        code = 0
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, buf.getvalue()


class TestInvocationModes(unittest.TestCase):
    """The shipped binding runs `__main__.py` as a SCRIPT PATH, where `__package__` is empty and
    a relative import fails. Every other test here goes through `import pm_status`, which has a
    package, so none of them can see that failure."""

    def _run(self, argv, cwd=None):
        return subprocess.run(argv, capture_output=True, text=True, cwd=cwd)

    def test_runs_as_a_script_path_not_only_as_an_import(self):
        r = self._run([sys.executable, SCRIPT, "--version"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(pm.PM_STATUS_VERSION, r.stdout)

    def test_script_path_from_another_working_directory(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            r = self._run([sys.executable, SCRIPT, "--version"], cwd=elsewhere)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_script_path_when_the_directory_is_not_named_pm_status(self):
        # The installed package directory is `pm-status` (a hyphen), so the bootstrap cannot
        # find itself by importing the name `pm_status`.
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "pm-status")
            shutil.copytree(os.path.dirname(SCRIPT), dest, ignore=shutil.ignore_patterns("__pycache__"))
            r = self._run([sys.executable, os.path.join(dest, "__main__.py"), "--version"], cwd=d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(pm.PM_STATUS_VERSION, r.stdout)

    def test_prologue_is_what_lets_a_relative_import_work_as_a_script(self):
        """`__main__.py` now carries a real relative import (`from . import core`), so the tests
        above exercise the prologue too. This one does not depend on that: it plants its OWN
        relative import in a COPY (hyphen-named, like the install) and runs it as a script, so it
        keeps failing with "no known parent package" if the prologue is deleted even in a tree
        where every other relative import has been moved or removed."""
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "pm-status")
            shutil.copytree(os.path.dirname(SCRIPT), dest, ignore=shutil.ignore_patterns("__pycache__"))
            with open(os.path.join(dest, "_probe.py"), "w", encoding="utf-8") as fh:
                fh.write("PROBE = 1\n")
            main_py = os.path.join(dest, "__main__.py")
            with open(main_py, encoding="utf-8") as fh:
                lines = fh.read().split("\n")
            # After the prologue's position, anchored on a line that exists with or without it.
            #
            # DERIVED, not pinned: the first relative import in the file. The prologue's own
            # rule is "nothing relative may appear above this block", so that line is after it
            # by construction, in this tree and in every later one. It was pinned to
            # `if TYPE_CHECKING:` until the `issues` extraction moved that guard out with
            # IssueStore, and the test then died on a StopIteration -- an error on an anchor
            # rather than a failure on the behaviour, which is the shape that teaches nothing.
            at = next((i for i, ln in enumerate(lines) if ln.startswith("from . import ")), None)
            self.assertIsNotNone(
                at,
                "__main__.py has no `from . import ...` line, so there is nowhere after the "
                "prologue to plant the probe. This test must keep working in a tree where "
                "every other relative import has moved: re-anchor it on the end of the "
                "prologue (the `sys.exit(...)` that closes the bootstrap block), not on "
                "another import.")
            lines.insert(at, "from . import _probe  # noqa: F401")
            with open(main_py, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
            r = self._run([sys.executable, main_py, "--version"], cwd=d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(pm.PM_STATUS_VERSION, r.stdout)

    def test_runs_as_python_dash_m(self):
        r = self._run([sys.executable, "-m", "pm_status", "--version"],
                      cwd=os.path.dirname(os.path.dirname(SCRIPT)))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_import_still_hands_back_the_main_module_itself(self):
        # The facade must stay one module object, or mock.patch.object(pm, ...) patches a copy.
        self.assertIs(sys.modules["pm_status"], sys.modules["pm_status.__main__"])


class TestPatchTargetsAreDefinedInMain(unittest.TestCase):
    """`mock.patch.object(pm, "<name>")` must name something `__main__.py` DEFINES.

    `pm` is `__main__`'s own module object (the __init__.py alias). As code is extracted,
    `__main__.py` keeps most moved names reachable with `from .core import <name>` -- and
    that binding is a PRIVATE COPY. Patching it rebinds `__main__`'s global and reaches
    nobody: core's own callers, and every other submodule, still see core's. The patch
    silently guards nothing, with no AttributeError to notice, which is the most expensive
    shape a test can take.

    So the rule is: a patched name must be DEFINED in `__main__.py`, or the target must be
    module-qualified (`pm.core.<name>`) and its callers must call `core.<name>(...)`.

    It has fired twice, as designed. The `nodes` extraction moved `save_node` and
    `epic_file` out of `__main__.py`, this test failed naming both and where they went,
    and the repair was to repoint the two targets to `pm.nodes.<name>` AND rewrite the 30
    call sites in `__main__.py` to `nodes.<name>(...)`. Neither half alone is enough: the
    repoint without the call-style change leaves a patch that reaches nobody, and the
    guard would be green over it. The `metrics` extraction then moved three more --
    `compute_story_estimate` and `rollup_parent_estimate` to `metrics/estimates.py`,
    `dispatch_window` to `metrics/actuals_usage.py` -- and the repair was the same shape
    one level deeper: `pm.metrics.<mod>.<name>`, with `_promote_issue` calling the two
    estimate functions as `metrics.estimates.<name>(...)`.

    The `issues` extraction then moved the last bare one, `resolve_issue_core`, out of
    `__main__.py`; Task 4.9 deleted that bucket with the issues verbs.

    EVERY bare target is now gone, so this guard no longer has a known next firing. That
    makes it a regression guard rather than a countdown: the thing it now catches is a NEW
    `patch.object(pm, "<name>")` written against a name that lives in a submodule, which is
    the natural shape to write and the one that silently guards nothing.
    """

    def _top_level_names(self, path):
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        names = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
        return names

    def _pm_patch_targets(self):
        """Every `patch.object(pm..., "<name>", ...)` in THIS file, by AST, not by regex: a
        name inside a docstring or a comment is not a patch site.

        Returns (bare, qualified): `{name: lineno}` for `patch.object(pm, ...)`, and
        `{dotted: {name: lineno}}` for `patch.object(pm.core, ...)` and friends.

        BOTH are collected, and the non-empty anchor below counts BOTH, because the bare set
        is now EMPTY on a correct tree -- `resolve_issue_core` was the last one, and the
        `issues` extraction repointed it. An anchor over the bare set alone would have gone
        from "the matcher broke" to "the refactor finished" without the assertion being able
        to tell the two apart, and a guard whose own sanity check fires on success is one
        somebody deletes. Counting every `pm`-rooted patch site keeps the anchor measuring
        what it was written to measure: whether this file's AST matcher still finds patch
        sites at all.
        """
        with open(__file__, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        bare, qualified = {}, {}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "object" and len(node.args) >= 2):
                continue
            target, attr = node.args[0], node.args[1]
            if not (isinstance(attr, ast.Constant) and isinstance(attr.value, str)):
                continue
            # Flatten `pm`, `pm.core`, `pm.metrics.estimates` to a dotted string; anything
            # not rooted at the name `pm` (e.g. `patch.object(os, ...)`) is not ours.
            parts, cur = [], target
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if not (isinstance(cur, ast.Name) and cur.id == "pm"):
                continue
            dotted = ".".join(reversed(parts))
            if dotted:
                qualified.setdefault(dotted, {}).setdefault(attr.value, node.lineno)
            else:
                bare.setdefault(attr.value, node.lineno)
        return bare, qualified

    def test_every_bare_pm_patch_target_is_defined_in_main(self):
        targets, qualified = self._pm_patch_targets()
        self.assertGreater(len(targets) + sum(len(v) for v in qualified.values()), 0,
                           "found no patch.object(pm, ...) sites -- the matcher broke, and a "
                           "guard that checks an empty set reports success over nothing")

        defined_here = self._top_level_names(SCRIPT)
        pkg = os.path.dirname(SCRIPT)
        elsewhere = {}
        for dirpath, dirnames, filenames in os.walk(pkg):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in sorted(filenames):
                p = os.path.join(dirpath, fn)
                if not fn.endswith(".py") or p == SCRIPT:
                    continue
                for name in self._top_level_names(p):
                    elsewhere.setdefault(name, os.path.relpath(p, os.path.dirname(pkg)))

        problems = []
        for name, line in sorted(targets.items()):
            if name in defined_here:
                continue
            owner = elsewhere.get(name)
            # The dotted path to name in the repair is DERIVED from where the definition
            # actually is, so a module this test has never heard of still gets a usable
            # instruction instead of "<module>". Both shapes the package uses resolve:
            # pm_status/nodes/__init__.py -> nodes, and pm_status/metrics/estimates.py ->
            # metrics.estimates. A bucket that becomes a directory later therefore needs
            # no edit here.
            mod = "<module>"
            if owner:
                parts = owner.replace(os.sep, "/").split("/")
                if parts[0] == "pm_status":
                    parts = parts[1:]
                if parts and parts[-1] == "__init__.py":
                    parts = parts[:-1]
                elif parts and parts[-1].endswith(".py"):
                    parts[-1] = parts[-1][:-len(".py")]
                mod = ".".join(parts) or "<module>"
            owner = owner or "nowhere in the package"
            # The premise has to cover BOTH ways a target can be unresolved here, because
            # they look identical from this side and the instruction is the same for each.
            # It said "but __main__.py only re-exports it", which is true of a name
            # __main__.py still lists and false of one it deliberately does not carry at
            # all -- and NOT carrying it is now the convention for every patch target, so
            # the clause was wrong in exactly the case it is most often read in. A reader
            # who believes it goes looking for a re-export to delete and finds nothing.
            problems.append(
                f'{os.path.basename(__file__)}:{line} patches pm."{name}", which '
                f"__main__.py does not DEFINE -- it is defined in {owner}, and __main__.py "
                f"either re-exports it (a private copy a patch cannot reach past) or, by "
                f"the convention for patch targets, does not carry it at all. Repoint the "
                f'patch to pm.{mod}."{name}" '
                f"AND make every caller outside {mod} reach it through the module object, "
                f"or the patch rebinds a private copy and guards nothing.")
        self.assertEqual(problems, [], "\n  " + "\n  ".join(problems) if problems else "")

    def test_the_verbs_module_is_bound_on_the_facade(self):
        """`import pm_status.verbs` and `pm.verbs.<name>` must resolve, so that a patch target
        added to `verbs` fails HERE -- with the repair instructions above -- rather than as an
        ImportError at the natural spelling. This is also `verbs`' reader for the gate below."""
        self.assertIs(pm.verbs.cmd_notice, pm.verbs.cmd_notice)

    def test_every_re_export_only_name_has_a_reader(self):
        """A `# noqa: F401` on a facade import in `__main__.py` is a claim that SOMETHING reads
        that name as `pm.<name>`. Nothing checked it, so 28 of 111 names carried the comment
        with no reader behind it -- a justification that reads as true and is not.

        DERIVED, no list: every module-level relative import alias whose line carries the
        directive, against every suite file's `pm.<name>` / `getattr(pm, "<name>")` reads."""
        with open(SCRIPT, encoding="utf-8") as fh:
            text = fh.read()
        lines = text.split("\n")
        claimed = sorted({
            a.asname or a.name
            for node in ast.parse(text).body
            if isinstance(node, ast.ImportFrom) and node.level >= 1
            for a in node.names
            if "noqa: F401" in lines[a.lineno - 1]
        })
        self.assertGreater(len(claimed), 0, "found no `noqa: F401` facade imports -- the matcher broke")
        repo = os.path.dirname(os.path.dirname(HERE))
        suites = sorted(glob.glob(os.path.join(HERE, "test-*.py"))
                        + glob.glob(os.path.join(repo, "tests", "**", "test-*.py"), recursive=True))
        # A reader is an ATTRIBUTE ACCESS on `pm` (or `getattr(pm, "<name>")`) found by walking each
        # suite's AST -- never a text match. A regex over the raw text is satisfied by a comment,
        # a docstring or a string literal, which is exactly how two readerless names survived
        # the hand sweep this gate replaces.
        read = set()
        for path in suites:
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
            for node in ast.walk(tree):
                if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                        and node.value.id == "pm"):
                    read.add(node.attr)
                elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "getattr" and len(node.args) >= 2
                        and isinstance(node.args[0], ast.Name) and node.args[0].id == "pm"
                        and isinstance(node.args[1], ast.Constant)
                        and isinstance(node.args[1].value, str)):
                    read.add(node.args[1].value)
        self.assertGreater(len(read), 0, "found no pm.<name> reads in any suite -- the matcher broke")
        unread = [n for n in claimed if n not in read]
        self.assertEqual(
            unread, [],
            "re-export-only names in __main__.py that no suite reads as pm.<name>: "
            + ", ".join(unread) + ". Delete the import (a name nothing reads is dead), or, if a "
            "reader exists under another spelling, name that reader in a comment.")


class TestSubcommandRegistration(unittest.TestCase):
    """Every subcommand in EXPECTED must be registered on the parser, and nothing else.

    A REGRESSION guard, not a TDD driver: `build_parser()` already registered all 43 before
    registration was distributed across the modules, so this passed on the day it was
    written. That is the point — it was confirmed green first, so it is known to be
    measuring the parser rather than measuring nothing.

    What it exists to catch: registration lives in each module's `register(subparsers)` now
    (design §3.2, so the 4.0.0 cut deletes a directory and one import line instead of
    hand-editing a 520-line function). The new failure that shape makes possible is a
    module's `register()` call going missing from `build_parser` — a whole bucket of verbs
    vanishing from the CLI with every other test green, because every other test here calls
    its handler directly or goes through `main()` with a verb some other module registers.

    The EXPECTED tuple is pinned, deliberately. Deriving it from the modules would make the
    test compare the parser to itself: a `register()` call dropped from `build_parser` would
    drop the verb from both sides and the guard would pass. The module attribution below is
    derived (it is only used to make the failure message name the bucket), the expectation
    is not.
    """

    # The CLI surface, in registration order. Adding or removing a verb is a deliberate edit
    # here. It is spec §4.5's keep set and the 4.x sidecar verbs; the migration-only verbs
    # (import-node, import-actual) and the 3.x estimators (estimate-story, estimate-rollup,
    # whose v7 address is estimate-entries) retired with the 3.x tree in Phase 6.
    EXPECTED = (
        "notice", "report", "dispatch", "usage", "calibration", "rates", "adr-reserve",
        "sync-agent-instructions",
        "verify", "set-estimate", "set-actual", "add-test-run",
        "sidecar-reconcile", "estimate-entries", "set-lane", "build-open", "build-close",
        "epic-close",
    )
    # Spec §4.5: the keep set, the support verbs and the 4.x sidecar verbs.
    SURFACE_4_5 = frozenset({
        "calibration", "set-estimate", "set-actual",
        "add-test-run", "dispatch", "report", "adr-reserve",
        "usage", "rates", "verify", "notice", "sync-agent-instructions",
        "sidecar-reconcile", "build-open", "build-close", "estimate-entries", "set-lane",
        "epic-close",
    })
    RETIRED = (
        "import-node", "import-actual", "estimate-story", "estimate-rollup",
        "set-status", "move-epic", "reparent-story", "retire-epic", "reorg-log",
        "reorg-undo", "dump-plan", "list-epics", "list-stories", "show",
        "set-depends-on", "story-doc-init", "set-field", "set-lock", "clear-lock",
        "check-lock",
        "append-issue", "update-issue", "promote-issue", "schedule-issue", "resolve-issue",
        "repair-issue", "list-issues", "audit-issues",
    )

    def _registered(self):
        """The subcommand names `build_parser()` actually wired, from the parser object —
        never from the source text, which cannot tell a registered verb from a commented
        one."""
        parser = pm.build_parser()
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                return list(action.choices)
        self.fail("build_parser() registered no subparsers action at all")

    def _owners(self):
        """{verb: module name}, DERIVED by calling each module's own `register()` on a
        throwaway parser. Used only to make a failure name the bucket that went missing.

        Tolerant by design: a module with no `register` contributes nothing and an
        unattributed verb is reported as such, so this half can never turn a green run red
        on its own."""
        owners = {}
        for name in ("core", "instructions", "adr", "metrics", "nodes", "verbs",
                     "sidecar_verbs", "bracket", "sidecar_closure"):
            mod = getattr(pm, name, None)
            register = getattr(mod, "register", None)
            if register is None:
                continue
            probe = argparse.ArgumentParser(prog="probe")
            sub = probe.add_subparsers(dest="cmd")
            register(sub)
            for verb in sub.choices:
                owners.setdefault(verb, name)
        return owners

    def test_build_parser_registers_every_subcommand(self):
        registered = self._registered()
        owners = self._owners()
        missing = [v for v in self.EXPECTED if v not in registered]
        extra = [v for v in registered if v not in self.EXPECTED]
        detail = ""
        if missing:
            buckets = sorted({owners.get(v, "unattributed") for v in missing})
            detail = (f"\n  MISSING {len(missing)} of {len(self.EXPECTED)}: "
                      f"{', '.join(missing)}\n  Their module(s): {', '.join(buckets)} — a "
                      f"`<module>.register(sub)` call is missing from build_parser(), or the "
                      f"module stopped registering them.")
        if extra:
            detail += f"\n  UNEXPECTED: {', '.join(extra)} — add it to EXPECTED deliberately."
        self.assertEqual(
            (missing, extra), ([], []),
            f"build_parser() registers {len(registered)} subcommands, expected "
            f"{len(self.EXPECTED)}.{detail}")

    def test_the_count_is_18(self):
        """Stated as its own assertion because the number is quoted in the design spec, the
        task briefs and the surface baseline. A set comparison alone reports 'missing one'
        without ever saying what the total is supposed to be."""
        self.assertEqual(len(self._registered()), 18)
        self.assertEqual(len(set(self.EXPECTED)), 18, "EXPECTED has a duplicate")

    def test_cli_surface_after_placement_retired(self):
        """Sofia owns the work-item tree (ADR-0015), so the 3.x placement, listing, node-write
        and lock verbs are gone; none of them may come back as a subcommand."""
        registered = set(self._registered())
        self.assertEqual(sorted(registered & set(self.RETIRED)), [])
        self.assertEqual(registered, set(self.EXPECTED))

    def test_pm_status_surface_is_4_5(self):
        """Issues live in v7's backlog (Task 4.9) and the 3.x tree is read only by the
        migration (Phase 6): the CLI is exactly spec §4.5's set, and no issues, import or 3.x
        estimate verb survives."""
        registered = set(self._registered())
        self.assertEqual(sorted(registered - self.SURFACE_4_5), [])
        self.assertEqual(sorted(self.SURFACE_4_5 - registered), [])


class TestNotice(Base):
    """notice: a one-time-ever advisory pointer, keyed on --key alone. Base gives us self.d
    (scratch dir) and self.run_main(argv) -> (code, stdout).

    No session dimension: `{session_id}` (step-00-activate.md) is bound fresh per skill
    invocation and no caller of `notice` is ever a dispatched subagent that could inherit
    one from a parent, so no two `notice` calls ever share one -- a per-session key would
    never repeat, firing on every invocation instead of once. The guarantee is therefore
    "once per project, until whatever the key represents is no longer true" (here: until
    `modules.l3io-pm` is configured), not "once per session".
    """

    def notice(self, key="setup-pointer"):
        return self.run_main(["notice", "--state-root", self.d, "--key", key])

    def test_emitted_once_ever(self):
        code, out = self.notice()
        self.assertEqual(code, 0, out)
        code, out = self.notice()
        self.assertEqual(code, 1, out)
        # And it stays suppressed -- this is not a one-shot-then-forgotten guard.
        self.assertEqual(self.notice()[0], 1)

    def test_scoped_per_key(self):
        self.notice("a")
        self.assertEqual(self.notice("a")[0], 1)   # same key, second call: suppressed
        self.assertEqual(self.notice("b")[0], 0)   # different key: independent

    def test_blank_key_is_a_usage_error(self):
        self.assertEqual(self.run_main(
            ["notice", "--state-root", self.d, "--key", "  "])[0], 2)

    def test_damaged_file_does_not_block_the_caller(self):
        with open(os.path.join(self.d, ".notices.yaml"), "w", encoding="utf-8") as fh:
            fh.write("{ not: valid: yaml\n")
        self.assertEqual(self.notice()[0], 0)

    def test_write_failure_is_reported_distinctly_not_as_already_emitted(self):
        """A bad READ is tolerated (test_damaged_file_does_not_block_the_caller above), but
        a failure actually recording the notice is a real failure, not "already said" (1)
        and not silent success (0) -- a caller told 1 says nothing further, so a masked
        crash there would silently and permanently suppress the pointer."""
        os.mkdir(os.path.join(self.d, ".notices.yaml"))   # a directory where the file goes
        code, out = self.notice()
        self.assertEqual(code, 2, out)
        os.rmdir(os.path.join(self.d, ".notices.yaml"))
        # Once the obstruction is gone, the key is still genuinely unrecorded -- the earlier
        # failure must not have left a stale lock or a false "emitted" record.
        self.assertEqual(self.notice()[0], 0)


class TestConcurrentNoticeDistinctKeys(unittest.TestCase):
    """SMOKE coverage for the lost-update property (kept alongside the deterministic
    TestNoticeReadHappensAfterTheLock below, which is the assertion that must hold -- this
    test costs little and a real regression here would still be worth seeing fail).

    notice's load->check->append->save must run under ONE lock (notices_lock), mirroring
    TestConcurrentSampling/TestConcurrentAdrReservation below. Locking only the write would
    let two parallel calls each read the same pre-write `keys` list and save their own key
    into it -- a lost update, silently dropping whichever key's writer read first, the same
    collision class every sibling lock family below exists to close.

    N distinct --key values racing together: every process reads and rewrites the SAME
    growing `keys` list for the whole run, exactly the shape TestConcurrentSampling and
    TestConcurrentAdrReservation already use to make their races land reliably. This test
    pins the lost-update property; TestConcurrentNoticeSameKey below pins the OTHER property
    that matters under the key-only scope -- exclusivity on a single repeated key -- which
    needs a pre-populated ledger to race reliably (see its docstring).

    Real subprocesses, not threads: `_file_lock`'s reentrancy counter (`_NOTICES_LOCK`) is
    per-process state, so threads sharing one process would pass this test vacuously even
    with the lock removed.
    """

    N = 24

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)

    def test_concurrent_notices_for_distinct_keys_lose_none(self):
        import subprocess
        procs = [subprocess.Popen(
            [sys.executable, SCRIPT, "notice", "--state-root", self.root, "--key", f"key-{i}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for i in range(self.N)]
        codes = []
        for p in procs:
            _, err = p.communicate(timeout=120)
            codes.append(p.returncode)
        self.assertEqual(codes, [0] * self.N,
                         f"every distinct key is new, so every caller must exit 0; got {codes}")
        _, data = pm.core._load(os.path.join(self.root, ".notices.yaml"))
        recorded = set(data["keys"]) if data else set()
        expected = {f"key-{i}" for i in range(self.N)}
        self.assertEqual(recorded, expected,
                         f"lost update(s) under concurrency: missing {expected - recorded}")


class TestConcurrentNoticeSameKey(unittest.TestCase):
    """SMOKE coverage, kept alongside the deterministic TestNoticeReadHappensAfterTheLock
    below (the assertion that must hold). This test is real -- every failure it produces is a
    genuine double-emit -- but it INFERS the lock from a timing window wide enough to lose a
    race, rather than asserting the lock's ordering directly. That makes it a tuned constant,
    not a fixed property: re-review measured a smooth, continuous detection-rate curve against
    PRESEED (0/10, 1/10, 5/10, 6/10, 8/10, 8/10 at 0/40/100/250/500/1000), not a cliff, so
    whatever value ships here will eventually sit wherever 40 sits today if the critical
    section this preseed exists to lengthen ever gets cheaper (faster ruamel, a faster box, a
    cheaper loader) -- at which point this test keeps reporting OK while checking nothing.
    Exclusivity on a single repeated key is still a real property worth this smoke coverage:
    two concurrent callers (e.g. l3io-execute and l3io-plan invoked around the same time
    in an unconfigured project) racing on the SAME key must never both be told "emit it".

    An EMPTY ledger's critical section is too short-lived for process-launch jitter alone to
    ever overlap it -- confirmed empirically: a same-key race against an empty ledger never
    reproduced a double exit-0, even at N=250. Pre-seeding the ledger with many prior keys
    widens the window enough (real ruamel parse + dump work over a bigger file) for the race
    to land reliably; confirmed empirically against THIS flat `{keys: [...]}` shape: a
    500-entry preseed at N=16 detects the lock's removal in the large majority of rounds
    (measured 8/10 by re-review, 8/8 in an earlier smaller sample here) with zero false
    positives against the shipped, locked code in every round either measurement ran.
    """

    N = 16
    PRESEED = 500

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)
        y = pm._yaml()
        with open(os.path.join(self.root, ".notices.yaml"), "w", encoding="utf-8") as fh:
            y.dump({"keys": [f"prior-key-{i}" for i in range(self.PRESEED)]}, fh)

    def test_concurrent_notices_for_one_key_fire_exactly_once(self):
        import subprocess
        procs = [subprocess.Popen(
            [sys.executable, SCRIPT, "notice", "--state-root", self.root,
             "--key", "setup-pointer"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for _ in range(self.N)]
        codes = []
        for p in procs:
            p.communicate(timeout=120)
            codes.append(p.returncode)
        self.assertEqual(codes.count(0), 1,
                         f"exactly one concurrent caller must be told to emit; got {codes}")
        self.assertEqual(codes.count(1), self.N - 1,
                         f"every other caller must see 'already emitted'; got {codes}")
        _, data = pm.core._load(os.path.join(self.root, ".notices.yaml"))
        self.assertIn("setup-pointer", data["keys"])
        self.assertEqual(len(data["keys"]), self.PRESEED + 1,
                         "no lost or duplicated entries under concurrency")


class TestNoticeReadHappensAfterTheLock(Base):
    """THE assertion that must hold: notice reads the ledger AFTER acquiring the lock, not
    before. Were the read to happen first, two concurrent callers could both see "not yet
    emitted" and both be told to emit -- the exact double-emit / lost-update bug
    notices_lock exists to prevent, and the one the smoke tests above can only infer.

    This asserts that ordering DIRECTLY and in-process, with no timing of any kind: wrap
    `notices_lock` and `_load` so each records when it runs, drive the real CLI through
    run_main, and compare the recorded sequence against the one correct order. Nothing here
    depends on how long a subprocess takes to boot, on machine load, or on how wide the
    critical section happens to be -- so unlike the smoke tests, there is no constant here
    that can quietly stop discriminating on a faster or a busier machine.

    That is why this test is in-process at all. An earlier version held the lock and slept a
    fixed margin while a real `notice` subprocess raced it. Measured, that margin carried
    only 2.3-2.6x headroom over subprocess boot-to-ledger-read on an idle box (176-213 ms
    boot vs a 0.5 s margin), and under ordinary CI CPU contention boot rose to a 1231 ms
    median -- past the margin -- taking detection of a planted read-before-lock bug to 0/10
    while the test still reported OK. A timing margin here can only ever fail toward FALSE
    GREEN (flock blocks a correct implementation unconditionally, so it cannot false-red),
    which is the dangerous direction. Polling /proc/locks for the child's blocked waiter is
    the other exact answer and self-adapting, but Linux-only; this one is portable.

    The wrappers are this test's one liability -- they name internals -- so it is built to
    FAIL LOUDLY rather than pass vacuously if those internals move:

    - `mock.patch.object` raises AttributeError if `notices_lock` or `_load` is renamed
      away, so a rename ERRORS this test rather than silently unhooking it.
    - the assertion is on the EXACT sequence, never merely on the absence of a bad one. If a
      wrapper stops firing (the lock inlined, the read routed through some other helper) the
      recorded list comes back short or empty and the comparison fails. "No bad order was
      observed" over an empty list is precisely the false green this test must not be able
      to produce.
    - every `_load` call is recorded, unfiltered by path, so an extra or unexpected read
      breaks the comparison too instead of being folded into the expected one.
    """

    EXPECTED = ["lock-acquired", "read", "lock-released"]

    def test_the_ledger_read_is_recorded_between_lock_acquire_and_release(self):
        events = []
        real_lock, real_load = pm.core.notices_lock, pm.core._load

        @contextmanager
        def recording_lock(state_root):
            with real_lock(state_root):          # the real flock, really taken
                events.append("lock-acquired")
                try:
                    yield
                finally:
                    events.append("lock-released")

        def recording_load(path):
            events.append("read")
            return real_load(path)

        with mock.patch.object(pm.core, "notices_lock", recording_lock), \
                mock.patch.object(pm.core, "_load", recording_load):
            code, out = self.run_main(
                ["notice", "--state-root", self.d, "--key", "setup-pointer"])

        # A first notice on a fresh state root must emit -- if it did not, the run under
        # observation was not the read-decide-write path this test means to have watched.
        self.assertEqual(code, 0, out)
        self.assertEqual(
            events, self.EXPECTED,
            f"the ledger read must happen INSIDE the lock. Expected {self.EXPECTED}, got "
            f"{events}. A 'read' before 'lock-acquired' is the double-emit bug itself; a "
            f"missing or extra entry means a wrapper did not fire as expected and this "
            f"test is no longer asserting the property -- check whether notices_lock or "
            f"_load was renamed or bypassed in cmd_notice.")


class StateTreeBase(Base):
    """impl/state: a state root, as the project-wide verbs (adr-reserve, notice, calibration)
    take one."""

    def setUp(self):
        super().setUp()
        self.arts = os.path.join(self.d, "impl")
        self.root = os.path.join(self.arts, "state")
        os.makedirs(self.root)

    def run_all(self, argv):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue(), err.getvalue()


class TestLayoutResolution(unittest.TestCase):
    """A v7 project with one ticket, and an adapter the value-logic suites run through.

    The fixture: `_bmad-output/initiative-shop/tickets/epic-cart/tickets/` with entries 1-3
    in `tickets.toml` and a plan for entry 3 (`story-3-plan.md`). `self.root` is the
    project's state root (`{output_folder}/l3io/`), where the calibration file and the event
    log live, so a suite that reads either reads it from `self.root` as before.

    THE ADAPTER (`_v7`). These suites test what `set-actual`, `set-estimate`, `add-test-run`
    and `verify` decide about their VALUES -- token classes, runtimes, derived cost, the
    test-run derivation -- and that logic (`actual_values`, `apply_estimate`,
    `tests_passing`, `verify_node`) is the same whatever the address. The 3.x node address
    retired in Phase 6, so `_v7` rewrites a story key to the v7 address of the ticket it
    stands for: `E001-S01-<nnn>` is entry `<nnn>` of `epic-cart`, a set-estimate goes to
    `--ticket-dir/--entry` and the rest to `--plan-file`. A key with no plan names a plan
    that does not exist, so it exits 3 exactly as an absent node did. `load_node` and
    `save_node` read and write the ticket's sidecars the same way: the entry's `estimate`
    and `class` from the epic's `l3io.toml`, everything else from the plan sidecar.
    """

    STORY = "E001-S01-003"
    V7_VERBS = ("set-actual", "set-estimate", "add-test-run", "verify")

    def setUp(self):
        self.project = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.project, True)
        self.root = os.path.join(self.project, "_bmad-output", "l3io")
        os.makedirs(self.root)
        # The state root, seeded so no test pays for BMad core's resolver: nodes caches it
        # per project root, and this is the value it would resolve to.
        pm.nodes._STATE_ROOTS[self.project] = self.root
        self.addCleanup(pm.nodes._STATE_ROOTS.pop, self.project, None)
        ini = os.path.join(self.project, "_bmad-output", "initiative-shop")
        self.tdir = os.path.join(ini, "tickets", "epic-cart", "tickets")
        os.makedirs(self.tdir)
        with open(os.path.join(ini, "initiative-shop.md"), "w") as f:
            f.write("---\ntype: initiative\n---\n# Shop\n")
        with open(os.path.join(ini, "tickets", "tickets.toml"), "w") as f:
            f.write('[[epic]]\nid = 1\nslug = "epic-cart"\n')
        with open(os.path.join(self.tdir, "tickets.toml"), "w") as f:
            # Entries 1 and 2 carry a hand-set estimate, so `estimate-entries` never asks for
            # their class and the roll-up counts entry 3 alone.
            for n in (1, 2):
                f.write(f'[[entry]]\nid = {n}\ntype = "story"\ntitle = "story {n}"\n'
                        f'estimate = "1d"\n\n')
            f.write('[[entry]]\nid = 3\ntype = "story"\ntitle = "story 3"\n')
        self.plan = self.plan_for(self.STORY)
        with open(self.plan, "w") as f:
            f.write("---\ntitle: 'story 3'\nticket: 3\nstatus: in-review\n---\n\n# story 3\n")

    # -- addressing ------------------------------------------------------------------- #
    @staticmethod
    def entry_of(key: str) -> str:
        return str(int(str(key).rsplit("-", 1)[-1]))

    def plan_for(self, key: str) -> str:
        return os.path.join(self.tdir, f"story-{self.entry_of(key)}-plan.md")

    def story_file(self, key: str):
        """The plan sidecar standing in for a story node; None when the ticket has no plan."""
        plan = self.plan_for(key)
        return plan[:-len(".md")] + ".l3io.toml" if os.path.isfile(plan) else None

    def epic_node(self):
        """The epic's `[epic]` table, as a 3.x epic node was read."""
        return pm.sidecar.plain(pm.sidecar.load(self._entry_path())).get("epic", {})

    def _v7(self, argv):
        """A 3.x-addressed argv as the v7 verb takes it (see the class docstring)."""
        argv = list(argv)
        if argv and argv[0] in ("estimate-story", "estimate-rollup"):
            return self._v7_estimate(argv)
        if not argv or argv[0] not in self.V7_VERBS:
            return argv
        out, story, i = [argv[0]], None, 1
        while i < len(argv):
            a = argv[i]
            if a in ("--state-root", "--story"):
                if a == "--story":
                    story = argv[i + 1]
                i += 2
                continue
            if a in ("--no-calibrate", "--flock"):
                i += 1
                continue
            out.append(a)
            i += 1
        out += ["--project-root", self.project]
        if story is not None:
            if argv[0] == "set-estimate":
                out += ["--ticket-dir", self.tdir, "--entry", self.entry_of(story)]
            else:
                out += ["--plan-file", self.plan_for(story)]
        return out

    def _v7_estimate(self, argv):
        """estimate-story and estimate-rollup as their v7 address, `estimate-entries`: a story
        is the entry it names with its class, a roll-up is the epic of the fixture."""
        out = ["estimate-entries", "--project-root", self.project, "--ticket-dir", self.tdir]
        i, story, cls = 1, None, None
        while i < len(argv):
            a = argv[i]
            if a == "--story":
                story = argv[i + 1]
            elif a == "--classification":
                cls = argv[i + 1]
            elif a in ("--model", "--token-rates"):
                out += [a, argv[i + 1]]
            elif a in ("--sprint",):
                out += ["--sprint", argv[i + 1]]       # not an estimate-entries flag: exit 2
            i += 2 if a.startswith("--") and i + 1 < len(argv) else 1
        if story is not None:
            entry = self.entry_of(story)
            out += ["--entry", entry]
            if cls:
                out += ["--class", f"{entry}={cls}"]
        return out

    # -- reading and writing the ticket's sidecars ------------------------------------ #
    def _entry_path(self):
        return os.path.join(self.tdir, "l3io.toml")

    def load_node(self, path):
        """(None, node): the plan sidecar's tables, plus the entry's `estimate` and `class`
        (as `classification`) from the epic's l3io.toml."""
        node = pm.sidecar.plain(pm.sidecar.load(path)) if path else {}
        entry = os.path.basename(path)[len("story-"):].split("-", 1)[0] if path else None
        ours = pm.sidecar.plain(pm.sidecar.load(self._entry_path())).get("entry", {})
        mine = ours.get(entry, {})
        if "estimate" in mine:
            node["estimate"] = mine["estimate"]
        if "class" in mine:
            node["classification"] = mine["class"]
        return None, node

    def save_node(self, _y, node, path):
        """Write `node` back: `estimate` to the entry, everything else to the plan sidecar."""
        node = pm.sidecar.plain(dict(node))
        node.pop("status", None)
        node.pop("classification", None)
        est = node.pop("estimate", None)
        doc = pm.sidecar._tomlkit().document()
        for k, v in node.items():
            doc[k] = v
        pm.sidecar.save(path, doc)
        if est is not None:
            entry = os.path.basename(path)[len("story-"):].split("-", 1)[0]
            with pm.sidecar.edit(self._entry_path()) as d:
                tbl = pm.sidecar.table(d, "entry", entry, "estimate")
                for k in list(tbl):
                    del tbl[k]
                pm.sidecar.put_metrics(tbl, est)

    def ensure_story_sidecar(self, key=None):
        """The plan sidecar for `key`, created empty when absent (a node always existed)."""
        path = self.plan_for(key or self.STORY)[:-len(".md")] + ".l3io.toml"
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write("")
        return path


class TestElapsedHoursUnification(TestLayoutResolution):
    """estimate-side time_hours and actual-side elapsed_hours are one name now —
    ESTIMATE_TO_ACTUAL is gone."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_estimate_writes_elapsed_hours_not_time_hours(self):
        code, out = self.run_main(["estimate-story", "--state-root", self.root,
                                   "--story", "E001-S01-003", "--classification", "standard"])
        self.assertEqual(code, 0, out)
        _, node = self.load_node(self.story_file("E001-S01-003"))
        self.assertIn("elapsed_hours", node["estimate"])
        self.assertNotIn("time_hours", node["estimate"])

    def test_estimate_to_actual_map_is_gone(self):
        self.assertFalse(hasattr(pm, "ESTIMATE_TO_ACTUAL"))

    def test_wall_clock_metric_is_elapsed_hours(self):
        self.assertEqual(pm.WALL_CLOCK_METRICS, ("elapsed_hours",))


class TestHitlHours(TestLayoutResolution):
    """hitl_hours is the fifth metric: real, observed supervision time — distinct
    from man_hours, which stays a counterfactual developer-effort estimate."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_metric_fields_has_five_in_canonical_order(self):
        self.assertEqual(pm.METRIC_FIELDS,
                         ("elapsed_hours", "man_hours", "hitl_hours", "tokens_k", "cost"))

    def test_bands_carry_hitl_for_every_classification(self):
        for cls in pm.CLASSIFICATIONS:
            self.assertIn("hitl_hours", pm.BASE_BANDS[cls])

    def test_estimate_story_emits_hitl_hours(self):
        code, out = self.run_main(["estimate-story", "--state-root", self.root,
                                   "--story", "E001-S01-003", "--classification", "complex"])
        self.assertEqual(code, 0, out)
        _, node = self.load_node(self.story_file("E001-S01-003"))
        # complex band 0.3-1.0, midpoint 0.65, x cold-start scope 1.0 x fix 1.25
        self.assertAlmostEqual(float(node["estimate"]["hitl_hours"]), 0.81, places=2)

    def test_set_actual_accepts_hitl_hours(self):
        code, out = self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                                   "--story", "E001-S01-003", "--hitl-hours", "0.3",
                                   "--no-calibrate"])
        self.assertEqual(code, 0, out)
        _, node = self.load_node(self.story_file("E001-S01-003"))
        self.assertAlmostEqual(float(node["actual"]["hitl_hours"]), 0.3, places=2)

    def test_calibration_show_lists_hitl_hours_rows(self):
        """cmd_calibration's display loops must enumerate hitl_hours too, or a
        component that IS calibrating (see the test above) would still never
        show up in `calibration show` — same-shaped blind spot, different
        symptom."""
        code, out = self.run_main(["calibration", "show", "--state-root", self.root,
                                   "--format", "json"])
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        buckets = [c["bucket"] for c in data["components"] if c["component"] == "scope"]
        self.assertTrue(any(b.endswith("/hitl_hours") for b in buckets), buckets)
        buckets = [c["bucket"] for c in data["components"] if c["component"] == "closure"]
        self.assertTrue(any(b.endswith("/hitl_hours") for b in buckets), buckets)

    def test_calibration_show_omits_closure_cost_row(self):
        """Task 10: closure cost is derived at rollup time (tokens x rates),
        never sampled or displayed on its own — a lingering closure/cost row
        would advertise a component that can no longer activate."""
        code, out = self.run_main(["calibration", "show", "--state-root", self.root,
                                   "--format", "json"])
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        buckets = [c["bucket"] for c in data["components"] if c["component"] == "closure"]
        self.assertFalse(any(b.endswith("/cost") for b in buckets), buckets)


class TestStructuredActualTokens(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _set(self, *extra):
        return self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                              "--story", "E001-S01-003", "--no-calibrate"] + list(extra))

    def test_tokens_na_cannot_be_combined_with_explicit_counts(self):
        """The two are contradictory claims about the same field: N/A says the runtime did
        not expose token counts, and a count says it did. Silently preferring either one
        records a number the capturer did not mean."""
        code, _o = self._set("--tokens-na", "--tokens-input", "412")
        self.assertEqual(code, 2)

    def test_no_metric_at_all_is_refused(self):
        """Every existing call passes at least one metric through the helper's *extra, so
        the empty case was reachable only from the CLI. A silent no-op here would look like
        a successful capture and leave the node with no actuals."""
        code, _o = self._set()
        self.assertEqual(code, 2)

    def test_writes_classes_total_and_derived_cost(self):
        code, out = self._set("--tokens-input", "412", "--tokens-output", "34",
                              "--tokens-cache-write", "4300", "--tokens-cache-read", "253",
                              "--model", "claude-opus-5", "--runtime", "claude")
        self.assertEqual(code, 0, out)
        _, node = self.load_node(self.story_file("E001-S01-003"))
        tk = node["actual"]["tokens_k"]
        self.assertEqual(int(tk["total"]), 4999)
        self.assertEqual(int(tk["cache_write"]), 4300)
        self.assertAlmostEqual(float(node["actual"]["cost"]), 29.91, places=2)
        self.assertEqual(str(node["actual"]["model"]), "claude-opus-5")

    def test_cost_flag_is_rejected(self):
        code, out = self._set("--cost", "12.00")
        self.assertEqual(code, 2, out)

    def test_tokens_require_a_model(self):
        code, out = self._set("--tokens-input", "100")
        self.assertEqual(code, 2, out)

    def test_unknown_model_is_rejected(self):
        code, out = self._set("--tokens-input", "100", "--model", "nope")
        self.assertEqual(code, 2, out)

    def test_tokens_na_allowed_under_runtime_other(self):
        code, out = self._set("--tokens-na", "--runtime", "other")
        self.assertEqual(code, 0, out)
        _, node = self.load_node(self.story_file("E001-S01-003"))
        self.assertTrue(pm._is_na(node["actual"]["tokens_k"]))
        self.assertTrue(pm._is_na(node["actual"]["cost"]))

    def test_tokens_na_forbidden_under_runtime_claude(self):
        code, out = self._set("--tokens-na", "--runtime", "claude")
        self.assertEqual(code, 2, out)


class TestVerify(TestLayoutResolution):
    """verify on a ticket's sidecar (`verbs.verify_node`, through the v7 adapter)."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _complete(self, path, story=False):
        from ruamel.yaml.comments import CommentedMap
        y, node = self.load_node(path)
        node["status"] = "done"
        actual = CommentedMap()
        actual["elapsed_hours"] = 0.4
        actual["man_hours"] = 3
        actual["hitl_hours"] = 0.1
        actual["tokens_k"] = {"total": 120, "input": 80, "output": 30,
                               "cache_write": 6, "cache_read": 4}
        actual["cost"] = 0.71
        actual["model"] = "claude-sonnet-5"
        node["actual"] = actual
        if story:
            ce = CommentedMap()
            ce["fix_iterations"] = 0
            ce["tests_passing"] = 10
            node["completion_evidence"] = ce
        self.save_node(y, node, path)

    def test_scope_story_passes_when_complete(self):
        self._complete(self.story_file("E001-S01-003"), story=True)
        code, out = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "story", "--story", "E001-S01-003"])
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_scope_story_fails_exit_4_when_incomplete(self):
        # a sidecar with no actual block and no completion_evidence
        self.ensure_story_sidecar()
        code, out = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "story", "--story", "E001-S01-003"])
        self.assertEqual(code, 4)
        self.assertIn("actual.", out)
        self.assertIn("completion_evidence absent", out)

    def test_no_sidecar_yet_exits_3(self):
        code, _ = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "story", "--story", "E001-S01-003"])
        self.assertEqual(code, 3)

    def test_nonexistent_node_exits_3(self):
        code, _ = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "story", "--story", "E001-S01-999"])
        self.assertEqual(code, 3)


class TestVerifyDerivedCost(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _done_story(self, cost, total=4999):
        p = self.story_file("E001-S01-003")
        y, node = self.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 3.1, "man_hours": 14, "hitl_hours": 0.3,
                          "tokens_k": {"total": total, "input": 412, "output": 34,
                                       "cache_write": 4300, "cache_read": 253},
                          "cost": cost, "model": "claude-opus-5"}
        self.save_node(y, node, p)

    def test_passes_when_cost_matches_the_tokens(self):
        self._done_story(29.91)
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--runtime", "claude"])
        self.assertEqual(code, 0, out)

    def test_fails_a_hand_edited_cost(self):
        self._done_story(9.99)
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--runtime", "claude"])
        self.assertEqual(code, 4, out)
        # Pinned to the mismatch semantics, not just the word "cost" — a fixture
        # that produced any other failure mentioning "cost" would wrongly pass.
        self.assertIn("actual.cost=9.99 != derived 29.91", out)

    def test_fails_when_cost_is_off_by_exactly_one_cent(self):
        # The boundary that matters: both the stored and derived cost are
        # already rounded to cents, so the smallest genuine divergence is
        # exactly one cent. A tolerance of > 0.01 does not reliably fire on
        # that divergence — verified concretely: 30k input tokens at
        # claude-haiku-4-5 ($1.00/M) derives to exactly 0.03; a hand-edited
        # 0.02 is one cent off, and in float64 abs(0.02 - 0.03) equals
        # 0.009999999999999998, which is NOT > 0.01 (the old tolerance would
        # have let this pass) but IS > 0.005 (the new tolerance catches it).
        # This is not float noise working in our favor by luck in one
        # direction — it is the precise case the old tolerance was blind to.
        p = self.story_file("E001-S01-003")
        y, node = self.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 1.0, "man_hours": 2, "hitl_hours": 0.1,
                          "tokens_k": {"total": 30, "input": 30, "output": 0,
                                       "cache_write": 0, "cache_read": 0},
                          "cost": 0.02, "model": "claude-haiku-4-5"}
        self.save_node(y, node, p)
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--runtime", "claude"])
        self.assertEqual(code, 4, out)
        self.assertIn("actual.cost=0.02 != derived 0.03", out)

    def test_fails_when_total_is_not_the_sum(self):
        self._done_story(29.91, total=999)
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--runtime", "claude"])
        self.assertEqual(code, 4, out)
        self.assertIn("total", out)

    def test_fails_when_hitl_hours_absent(self):
        p = self.story_file("E001-S01-003")
        y, node = self.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 3.1, "man_hours": 14,
                          "tokens_k": "N/A", "cost": "N/A"}
        self.save_node(y, node, p)
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003"])
        self.assertEqual(code, 4, out)
        self.assertIn("hitl_hours", out)


class TestMixedModelActual(TestVerifyDerivedCost):
    """A run on more than one model records `by_model`, and its cost is each model's tokens
    at that model's own rates. Before this, set-actual took one --model, so a mixed run's
    recorded cost was priced entirely at one rate."""

    SPLIT = {"claude-opus-5-5": {"input": 100, "output": 10, "cache_write": 1000, "cache_read": 200},
             "claude-sonnet-5-5": {"input": 50, "output": 20, "cache_write": 500, "cache_read": 100}}

    def _ready(self):
        p = self.story_file("E001-S01-003")
        y, node = self.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        self.save_node(y, node, p)

    def _set(self, *extra):
        return self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                              "--story", "E001-S01-003", "--runtime", "claude",
                              "--elapsed-hours", "1", "--man-hours", "2", "--hitl-hours", "0.1",
                              "--no-calibrate", *extra])

    def _verify(self):
        return self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                              "--story", "E001-S01-003", "--runtime", "claude"])

    def _actual(self):
        return self.load_node(self.story_file("E001-S01-003"))[1]["actual"]

    def test_split_is_priced_per_model_and_verifies(self):
        self._ready()
        code, out = self._set("--tokens-by-model", json.dumps(self.SPLIT))
        self.assertEqual(code, 0, out)
        a = self._actual()
        # opus: (100*4 + 10*20 + 1000*5 + 200*0.20)/1000 = 5.64
        # sonnet: (50*2 + 20*10 + 500*2.5 + 100*0.10)/1000 = 1.56
        self.assertEqual(float(a["cost"]), 7.20)
        self.assertEqual(a["model"], "claude-opus-5-5", "the model carrying the most tokens")
        self.assertEqual(dict(a["tokens_k"]), {"total": 1980, "input": 150, "output": 30,
                                               "cache_write": 1500, "cache_read": 300})
        self.assertEqual(sorted(a["by_model"]), ["claude-opus-5-5", "claude-sonnet-5-5"])
        code, out = self._verify()
        self.assertEqual(code, 0, out)

    def test_verify_fails_a_hand_edited_split_cost(self):
        self._ready()
        self._set("--tokens-by-model", json.dumps(self.SPLIT))
        p = self.story_file("E001-S01-003")
        y, node = self.load_node(p)
        node["actual"]["cost"] = 9.99
        self.save_node(y, node, p)
        code, out = self._verify()
        self.assertEqual(code, 4, out)
        self.assertIn("actual.cost=9.99 != derived 7.2 for each model in by_model", out)

    def test_verify_fails_when_by_model_does_not_sum_to_tokens_k(self):
        self._ready()
        self._set("--tokens-by-model", json.dumps(self.SPLIT))
        p = self.story_file("E001-S01-003")
        y, node = self.load_node(p)
        node["actual"]["by_model"]["claude-sonnet-5-5"]["input"] = 999
        self.save_node(y, node, p)
        code, out = self._verify()
        self.assertEqual(code, 4, out)
        self.assertIn("actual.tokens_k.input=150.0 != sum of by_model (1099.0)", out)

    def test_a_single_model_recapture_drops_the_old_split(self):
        self._ready()
        self._set("--tokens-by-model", json.dumps(self.SPLIT))
        code, out = self._set("--model", "claude-opus-5-5", "--tokens-input", "1",
                              "--tokens-output", "1", "--tokens-cache-write", "1",
                              "--tokens-cache-read", "1")
        self.assertEqual(code, 0, out)
        self.assertNotIn("by_model", self._actual())
        self.assertEqual(self._verify()[0], 0)

    def test_split_refuses_model_flag_unknown_model_and_missing_class(self):
        self._ready()
        code, _ = self._set("--tokens-by-model", json.dumps(self.SPLIT), "--model", "claude-opus-5-5")
        self.assertEqual(code, 2)
        code, _ = self._set("--tokens-by-model", json.dumps(
            {"claude-nope": {"input": 1, "output": 1, "cache_write": 0, "cache_read": 0}}))
        self.assertEqual(code, 2)
        code, _ = self._set("--tokens-by-model", json.dumps(
            {"claude-opus-5-5": {"input": 1, "output": 1, "cache_write": 0}}))
        self.assertEqual(code, 2)
        self.assertNotIn("actual", self.load_node(self.story_file("E001-S01-003"))[1] or {})

    def _priced_sonnet5(self, cost):
        p = self.story_file("E001-S01-003")
        y, node = self.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 1.0, "man_hours": 2, "hitl_hours": 0.1,
                          "tokens_k": {"total": 1100, "input": 1000, "output": 100,
                                       "cache_write": 0, "cache_read": 0},
                          "cost": cost, "model": "claude-sonnet-5"}
        self.save_node(y, node, p)

    def test_an_actual_priced_before_the_sonnet5_correction_still_verifies(self):
        """claude-sonnet-5 moved from $3/$15 to $2/$10. Actuals frozen at the old card
        must not start failing verify -- RATE_HISTORY carries it."""
        self._priced_sonnet5(4.50)            # (1000*3 + 100*15)/1000
        self.assertEqual(self._verify()[0], 0)
        self._priced_sonnet5(3.00)            # (1000*2 + 100*10)/1000, the current card
        self.assertEqual(self._verify()[0], 0)

    def test_a_cost_matching_no_card_still_fails(self):
        self._priced_sonnet5(3.75)
        code, out = self._verify()
        self.assertEqual(code, 4, out)
        self.assertIn("actual.cost=3.75 != derived 3.0 for model claude-sonnet-5", out)


class TestVerifyTokenRatesWiring(TestLayoutResolution):
    """--token-rates on `verify` (Decision 1 of the task-8 brief, not in the
    original design doc): without this wiring, a project using
    modules.l3io-pm.token_rates overrides would have every node recomputed at
    DEFAULT rates and fail verification universally. This is the permanent
    covering test for that wiring — a prior version of this proof lived only
    in a throwaway script and left the wiring one refactor away from silently
    regressing with the full suite still green."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _done_story_priced_only_under_override(self):
        p = self.story_file("E001-S01-003")
        y, node = self.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        # "acme-model" does not exist in TOKEN_RATES; it is priced only by the
        # --token-rates override below (input $10/M, everything else free).
        # 100k input tokens -> 100 * 10.0 / 1000 = 1.00.
        node["actual"] = {"elapsed_hours": 1.0, "man_hours": 2, "hitl_hours": 0.1,
                          "tokens_k": {"total": 100, "input": 100, "output": 0,
                                       "cache_write": 0, "cache_read": 0},
                          "cost": 1.00, "model": "acme-model"}
        self.save_node(y, node, p)

    def test_fails_with_unknown_model_message_without_override(self):
        self._done_story_priced_only_under_override()
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003"])
        self.assertEqual(code, 4, out)
        self.assertIn("unknown model 'acme-model'", out)

    def test_passes_when_token_rates_override_supplies_the_model(self):
        self._done_story_priced_only_under_override()
        overrides = json.dumps({"acme-model": {"input": 10.0, "output": 0,
                                                "cache_write": 0, "cache_read": 0}})
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--token-rates", overrides])
        self.assertEqual(code, 0, out)


class TestCalibrationIO(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)

    def test_a_file_with_sprint_samples_loads_and_ignores_them(self):
        """ADR-0016: no sprint level in 4.x. A 3.x file carrying `closure.sprint` and
        `orchestration.sprint` still loads, shows, rolls up and records -- its sprint
        samples are kept on disk and never read."""
        with open(pm.calibration_path(self.root), "w") as f:
            f.write("version: 2\ngranularity: story\n"
                    f"{pm.CALIBRATION_METRICS_MARKER}: '2026-10-01T00:00:00Z'\n"
                    f"{pm.TOKEN_BASIS_MARKER}: '2026-10-01T00:00:00Z'\n"
                    "scope: {simple: {}, standard: {}, complex: {}}\n"
                    "fix: {simple: {}, standard: {}, complex: {}}\n"
                    "closure:\n  sprint:\n    man_hours: {samples: [9.0, 9.0, 9.0]}\n"
                    "  epic: {}\n"
                    "orchestration:\n  sprint:\n    man_hours: {samples: [3.0, 3.0, 3.0]}\n"
                    "  epic: {}\n")
        y, cal = pm.load_calibration(self.root)
        self.assertIsNone(pm.active_closure_ratio(cal, "epic", "man_hours"))
        self.assertIsNone(pm.active_orchestration_fraction(cal, "epic", "man_hours"))
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = pm.main(["calibration", "show", "--state-root", self.root])
        self.assertEqual(code, 0)
        self.assertNotIn("sprint/", buf.getvalue())
        pm.metrics.calibration.append_closure_ratios(self.root, "epic", {"man_hours": 1.5})
        _, again = pm.load_calibration(self.root)
        self.assertEqual(len(pm._component_samples(again, "closure", "epic", "man_hours")), 1)
        self.assertEqual(len(again["closure"]["sprint"]["man_hours"]["samples"]), 3)

    def test_missing_file_yields_skeleton_not_error(self):
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(cal["version"], 2)
        self.assertEqual(cal["granularity"], "story")
        self.assertIn("scope", cal)
        self.assertIn("closure", cal)
        self.assertIn("fix", cal)

    def test_granularity_persists_in_file_not_a_binding(self):
        y, cal = pm.load_calibration(self.root)
        cal["granularity"] = "sprint"
        pm.save_calibration(y, cal, self.root)
        _, again = pm.load_calibration(self.root)
        self.assertEqual(again["granularity"], "sprint")

    def test_weighted_ratio_favours_recent_samples(self):
        # oldest first; decay 0.8 means later samples dominate
        older_heavy = pm.weighted_ratio([2.0, 1.0])
        newer_heavy = pm.weighted_ratio([1.0, 2.0])
        self.assertLess(older_heavy, newer_heavy)

    def test_weighted_ratio_single_sample_is_that_sample(self):
        self.assertAlmostEqual(pm.weighted_ratio([1.4]), 1.4)

    def test_component_below_threshold_is_not_active(self):
        y, cal = pm.load_calibration(self.root)
        cal["scope"]["complex"] = {"man_hours": {"samples": [1.2, 1.3]}}
        pm.save_calibration(y, cal, self.root)
        _, cal2 = pm.load_calibration(self.root)
        self.assertIsNone(pm.active_scope_ratio(cal2, "complex", "man_hours"))

    def test_component_at_threshold_is_active(self):
        y, cal = pm.load_calibration(self.root)
        cal["scope"]["complex"] = {"man_hours": {"samples": [1.2, 1.3, 1.4]}}
        pm.save_calibration(y, cal, self.root)
        _, cal2 = pm.load_calibration(self.root)
        self.assertIsNotNone(pm.active_scope_ratio(cal2, "complex", "man_hours"))

    def test_fix_needs_both_cohorts_at_threshold(self):
        y, cal = pm.load_calibration(self.root)
        cal["fix"]["complex"] = {
            "clean": {"mean_man_hours": 7.0, "samples": 5},
            "reworked": {"mean_man_hours": 9.0, "samples": 0},
        }
        pm.save_calibration(y, cal, self.root)
        _, cal2 = pm.load_calibration(self.root)
        self.assertIsNone(pm.active_fix_factor(cal2, "complex"))

    def test_fix_active_when_both_cohorts_reach_threshold(self):
        y, cal = pm.load_calibration(self.root)
        cal["fix"]["complex"] = {
            "clean": {"mean_man_hours": 8.0, "samples": 3},
            "reworked": {"mean_man_hours": 10.0, "samples": 3},
        }
        pm.save_calibration(y, cal, self.root)
        _, cal2 = pm.load_calibration(self.root)
        self.assertAlmostEqual(pm.active_fix_factor(cal2, "complex"), 1.25)

    def test_v1_file_migrates_and_preserves_original(self):
        p = pm.calibration_path(self.root)
        with open(p, "w") as f:
            f.write("version: 1\nratio: 1.3\n")
        y, cal = pm.load_calibration(self.root)
        cal = pm.migrate_calibration(y, cal, self.root)
        self.assertEqual(cal["version"], 2)
        self.assertTrue(os.path.exists(p + ".v1"))
        # closure and fix start fresh, never seeded from the blended ratio.
        # Assert emptiness per bucket rather than comparing a CommentedMap to a
        # plain dict, which is fragile across ruamel versions.
        self.assertEqual(len(cal["closure"]["epic"]), 0)
        self.assertNotIn("sprint", cal["closure"])
        for c in ("simple", "standard", "complex"):
            self.assertEqual(len(cal["fix"][c]), 0)
        # the blended v1 ratio landed on scope, and only on scope
        self.assertGreater(len(cal["scope"]["complex"]), 0)

    def test_show_on_missing_file_exits_0(self):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(["calibration", "show", "--state-root", self.root])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 0)
        self.assertIn("cold-start", buf.getvalue().lower())


class TestCalibrationMetricsMigration(unittest.TestCase):
    """`migrate_calibration_metrics` reshapes a pre-metrics-rework calibration
    file in place, without bumping `version` (still 2 — compatibility is by
    shape-tolerant reads, never a version gate).

    Gating is by a POSITIVE MARKER (`CALIBRATION_METRICS_MARKER`,
    `metrics_migrated_at`), stamped once a real pass through the function
    finishes — even a no-op one. An earlier design inferred "not yet
    migrated" from the presence/absence of the old `cost`/`time_hours` keys;
    the coordinator rejected it because that inference has a silent blind
    spot on a non-Claude-runtime project (cost is always N/A there, so a
    file that also lacks time_hours samples would read as "already
    migrated" and never have its man_hours/fix samples quarantined — see
    test_man_hours_quarantined_even_without_cost_or_time_hours_markers,
    which falsifies that design). `man_hours` and `fix` now quarantine
    unconditionally on the one authoritative pass, no corroborating marker
    needed.

    The main "before" fixture (in setUp) is hand-authored, not built by
    running a real command: `git log -S` over this file's whole history
    turns up no commit where a calibration SCOPE/CLOSURE bucket ever used a
    literal "time_hours" key (METRIC_FIELDS already read "elapsed_hours" as
    far back as the file goes) or calibrated `cost` unconditionally without
    excluding it — the "old rules" this task migrates away from predate
    what this repo tracks. There is no real command left in this codebase
    whose output would produce that shape, so hand-authoring the fixture
    (matching the task brief's own Step-1 fixture) is the only option.
    Where a REAL write path can produce genuine data instead (the `fix`
    cohort structure has not changed shape at all, and neither has a lone
    `man_hours` sample), the tests below use it — see
    test_fix_cohort_built_via_real_writes_is_quarantined_wholesale and
    test_man_hours_written_after_the_one_time_cutover_is_never_revisited.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)
        with open(pm.calibration_path(self.root), "w") as f:
            f.write(
                "version: 2\n"
                "granularity: story\n"
                "scope:\n"
                "  complex:\n"
                "    man_hours: {samples: [1.1, 1.2, 1.3]}\n"
                "    time_hours: {samples: [0.9, 1.0, 1.1]}\n"
                "    tokens_k: {samples: [4.0, 4.5, 5.0]}\n"
                "    cost: {samples: [2.0, 2.1, 2.2]}\n"
                "closure:\n"
                "  sprint:\n"
                "    cost: {samples: [1.5]}\n"
            )

    def _migrate(self):
        y, cal = pm.load_calibration(self.root)
        log = pm.migrate_calibration_metrics(y, cal, self.root)
        pm.save_calibration(y, cal, self.root)
        return cal, log

    def test_version_is_not_bumped(self):
        cal, _ = self._migrate()
        self.assertEqual(int(cal["version"]), 2)

    def test_cost_component_is_dropped(self):
        cal, _ = self._migrate()
        self.assertNotIn("cost", cal["scope"]["complex"])
        self.assertNotIn("cost", cal["closure"]["sprint"])

    def test_man_hours_is_quarantined_not_deleted(self):
        cal, _ = self._migrate()
        self.assertNotIn("man_hours", cal["scope"]["complex"])
        self.assertEqual(cal["legacy"]["scope"]["complex"]["man_hours"]["samples"],
                         [1.1, 1.2, 1.3])

    def test_time_hours_carried_forward_under_the_new_name(self):
        cal, _ = self._migrate()
        self.assertNotIn("time_hours", cal["scope"]["complex"])
        self.assertEqual(cal["scope"]["complex"]["elapsed_hours"]["samples"],
                         [0.9, 1.0, 1.1])

    def test_tokens_carried_and_flagged_when_out_of_range(self):
        cal, log = self._migrate()
        self.assertIn("tokens_k", cal["scope"]["complex"])
        self.assertTrue(any("FLAG" in line and "tokens_k" in line for line in log))

    def test_new_components_are_seeded_empty(self):
        cal, _ = self._migrate()
        self.assertEqual(cal["orchestration"]["epic"], {})
        self.assertEqual(cal["token_mix"]["samples"], [])

    def test_pre_migration_file_reads_as_cold_start_not_an_error(self):
        """Shape-tolerant reads are what let `version` stay at 2: a read-only
        command must handle an unmigrated file without raising and without
        migrating it."""
        _, cal = pm.load_calibration(self.root)
        self.assertIsNone(pm.active_orchestration_fraction(cal, "sprint", "tokens_k"))
        self.assertEqual(pm.observed_mix(cal), pm.COLD_START_TOKEN_MIX)
        self.assertFalse(os.path.exists(pm.calibration_path(self.root) + ".pre-metrics"))

    def test_backup_written_and_migration_idempotent(self):
        self._migrate()
        self.assertTrue(os.path.exists(pm.calibration_path(self.root) + ".pre-metrics"))
        cal2, log2 = self._migrate()
        self.assertEqual(log2, [])
        self.assertEqual(cal2["scope"]["complex"]["elapsed_hours"]["samples"],
                         [0.9, 1.0, 1.1])

    def test_backup_preserves_the_exact_pre_migration_bytes(self):
        # Not just "a backup exists" — it must be the file as it stood BEFORE
        # any reshaping, taken before the drop/rename/quarantine mutations,
        # not some already-mutated snapshot.
        with open(pm.calibration_path(self.root), "rb") as f:
            original = f.read()
        self._migrate()
        with open(pm.calibration_path(self.root) + ".pre-metrics", "rb") as f:
            backed_up = f.read()
        self.assertEqual(backed_up, original)

    def test_closure_bucket_left_empty_not_removed_after_its_only_key_drops(self):
        # closure.sprint had only `cost`; dropping it must leave an empty
        # mapping behind, not delete the "sprint" bucket itself (a future
        # closure sample still needs somewhere to land under "sprint").
        cal, _ = self._migrate()
        self.assertIn("sprint", cal["closure"])
        self.assertEqual(len(cal["closure"]["sprint"]), 0)

    def test_man_hours_quarantined_even_without_cost_or_time_hours_markers(self):
        """The coordinator's motivating case: a non-Claude-runtime project
        never accumulates `cost` samples (cost is N/A there and skipped by
        calibration), and may equally have no `time_hours` samples for any
        other reason. Such a file's ONLY sign of pre-rework vintage is the
        man_hours samples themselves — no unambiguous key at all.

        This is the test that falsifies inferring "already migrated" from
        legacy-key presence/absence: that design would read "no cost, no
        time_hours" as "nothing to do" and leave old-definition man_hours
        ratios silently in force forever. Gating on a positive marker
        instead means an unmigrated file gets the full treatment regardless
        of which sample types it happens to contain.
        """
        root = os.path.join(self.d, "no-cost-no-time-state")
        os.makedirs(root)
        with open(pm.calibration_path(root), "w") as f:
            f.write(
                "version: 2\n"
                "granularity: story\n"
                "scope:\n"
                "  standard:\n"
                "    man_hours: {samples: [3.0, 3.1, 3.2]}\n"
            )
        y, cal = pm.load_calibration(root)
        log = pm.migrate_calibration_metrics(y, cal, root)
        pm.save_calibration(y, cal, root)
        self.assertTrue(any("QUARANTINE" in line and "man_hours" in line for line in log))
        self.assertNotIn("man_hours", cal["scope"]["standard"])
        self.assertEqual(cal["legacy"]["scope"]["standard"]["man_hours"]["samples"],
                         [3.0, 3.1, 3.2])

    def test_man_hours_written_after_the_one_time_cutover_is_never_revisited(self):
        """Data-safety proof, built via the REAL write path (not a
        hand-authored fixture): the migration's one authoritative pass runs
        on a project's VERY FIRST write, before that write's own sample is
        even appended — even when there is nothing yet to migrate — and
        stamps CALIBRATION_METRICS_MARKER right there. Every man_hours
        sample written by every subsequent real write to that same project,
        no matter how many, is therefore never revisited: the marker gate
        short-circuits before any bucket is even inspected again.

        This is the replacement for an earlier test of the same name's
        intent that reasoned about per-bucket "corroborating markers" — a
        mechanism the coordinator correctly rejected (see
        migrate_calibration_metrics's docstring and
        test_man_hours_quarantined_even_without_cost_or_time_hours_markers).
        The safety property survives; the mechanism producing it changed.
        """
        fresh_root = os.path.join(self.d, "fresh-state")
        os.makedirs(fresh_root)
        est = {"man_hours": 6, "elapsed_hours": 1.5, "tokens_k": 320,
               "cost": 4.80, "fix_factor": 1.25, "scope_ratio": 1.0}
        act = {"man_hours": 7, "elapsed_hours": 1.8, "tokens_k": {"total": 355},
               "cost": 5.32}

        def _node(key):
            return {"key": key, "classification": "standard",
                    "estimate": dict(est), "actual": dict(act),
                    "completion_evidence": {"fix_iterations": 0}}

        pm.record_story_sample(fresh_root, _node("E001-S01-001"))  # real write path
        _, cal = pm.load_calibration(fresh_root)
        self.assertIn(pm.CALIBRATION_METRICS_MARKER, cal)  # stamped on the very first write
        self.assertNotIn("legacy", cal)  # nothing existed yet to quarantine
        self.assertEqual(len(pm._component_samples(cal, "scope", "standard", "man_hours")), 1)

        pm.record_story_sample(fresh_root, _node("E001-S01-002"))  # a later real write
        _, cal2 = pm.load_calibration(fresh_root)
        self.assertEqual(len(pm._component_samples(cal2, "scope", "standard", "man_hours")), 2)
        self.assertNotIn("legacy", cal2)  # neither sample was ever touched

    def test_fix_cohort_built_via_real_writes_is_quarantined_wholesale(self):
        """The `fix` payload here is 100% real: built by calling
        `record_story_sample` (the actual write path) three times, on a
        FRESH root, so the `clean` cohort crosses MIN_SAMPLES exactly as a
        real project would. The first of those three writes stamps
        CALIBRATION_METRICS_MARKER (the migration's own one-time-pass
        marker) since nothing existed yet to migrate — correctly, per
        test_man_hours_written_after_the_one_time_cutover_is_never_revisited.

        To then prove `fix` DOES quarantine wholesale on a genuinely
        unmigrated file (decision: no per-metric split, no corroborating
        marker needed — see migrate_calibration_metrics's docstring), this
        strips that marker before calling migrate_calibration_metrics
        directly: no real pre-Task-11 project's calibration file could ever
        have carried a marker this task itself introduces, so stripping it
        is the accurate way to simulate genuine pre-upgrade disk state.
        Everything else here — the fix cohort itself, and the assertion
        that it moved intact — is real data from real writes, not
        hand-authored.
        """
        fresh_root = os.path.join(self.d, "fix-quarantine-state")
        os.makedirs(fresh_root)
        for i in range(3):
            node = {"key": f"E001-S01-{i:03d}", "classification": "complex",
                    "estimate": {"man_hours": 6, "elapsed_hours": 1.5, "tokens_k": 320,
                                 "cost": 4.80, "fix_factor": 1.25, "scope_ratio": 1.0},
                    "actual": {"man_hours": 7, "elapsed_hours": 1.8,
                               "tokens_k": {"total": 355}, "cost": 5.32},
                    "completion_evidence": {"fix_iterations": 0}}
            pm.record_story_sample(fresh_root, node)
        _, cal = pm.load_calibration(fresh_root)
        self.assertEqual(int(cal["fix"]["complex"]["clean"]["samples"]), 3)
        self.assertIn(pm.CALIBRATION_METRICS_MARKER, cal)  # stamped by the first of these 3 writes
        pre_mean = float(cal["fix"]["complex"]["clean"]["mean_man_hours"])

        y, cal = pm.load_calibration(fresh_root)
        del cal[pm.CALIBRATION_METRICS_MARKER]
        pm.save_calibration(y, cal, fresh_root)

        y, cal = pm.load_calibration(fresh_root)
        log = pm.migrate_calibration_metrics(y, cal, fresh_root)
        pm.save_calibration(y, cal, fresh_root)

        self.assertTrue(any("QUARANTINE" in line and "fix" in line for line in log))
        self.assertEqual(len(cal["fix"]["complex"]), 0)
        self.assertAlmostEqual(float(cal["legacy"]["fix"]["complex"]["clean"]["mean_man_hours"]),
                               pre_mean)
        self.assertEqual(int(cal["legacy"]["fix"]["complex"]["clean"]["samples"]), 3)

    def test_cli_migrate_metrics_action_reports_changes_then_zero(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = pm.main(["calibration", "migrate-metrics", "--state-root", self.root])
        self.assertEqual(code, 0)
        first = buf.getvalue()
        self.assertIn("OK calibration migrate-metrics", first)
        self.assertNotIn("(0 changes)", first)

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            code2 = pm.main(["calibration", "migrate-metrics", "--state-root", self.root])
        self.assertEqual(code2, 0)
        self.assertIn("(0 changes)", buf2.getvalue())


class TestCalibrationMetricsMigrationReadOnlySafety(TestLayoutResolution):
    """Commands that only READ the calibration file (`calibration show`, and the estimate
    `estimate-entries` computes) must never trigger the metrics migration — proved by
    comparing the calibration file's raw BYTES before and after, not merely
    checking that no exception was raised.
    """

    LEGACY_YAML = (
        "version: 2\n"
        "granularity: story\n"
        "scope:\n"
        "  complex:\n"
        "    man_hours: {samples: [1.1, 1.2, 1.3]}\n"
        "    time_hours: {samples: [0.9, 1.0, 1.1]}\n"
        "    tokens_k: {samples: [4.0, 4.5, 5.0]}\n"
        "    cost: {samples: [2.0, 2.1, 2.2]}\n"
        "closure:\n"
        "  sprint:\n"
        "    cost: {samples: [1.5]}\n"
    )

    def setUp(self):
        super().setUp()
        with open(pm.calibration_path(self.root), "w") as f:
            f.write(self.LEGACY_YAML)
        with open(pm.calibration_path(self.root), "rb") as f:
            self.before = f.read()

    def _unchanged(self):
        with open(pm.calibration_path(self.root), "rb") as f:
            after = f.read()
        self.assertEqual(after, self.before)

    def test_calibration_show_leaves_file_untouched(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = pm.main(["calibration", "show", "--state-root", self.root])
        self.assertEqual(code, 0)
        self._unchanged()

    def test_estimate_story_leaves_calibration_file_untouched(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = pm.main(self._v7(["estimate-story", "--story", self.STORY,
                                     "--classification", "complex"]))
        self.assertEqual(code, 0, buf.getvalue())
        self._unchanged()


class TestEstimateFactors(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_set_estimate_records_factors(self):
        # No --cost: cost is derived from tokens x rates and set-estimate
        # rejects it (see TestEstimateTokensAndCost.test_cost_low_flag_is_rejected).
        code, out = self.run_main(
            ["set-estimate", "--state-root", self.root, "--story", "E001-S01-003",
             "--man-hours", "6", "--elapsed-hours", "1.5", "--tokens-k", "320",
             "--fix-factor", "1.25", "--scope-ratio", "1.1"])
        self.assertEqual(code, 0, out)
        _, node = self.load_node(self.story_file("E001-S01-003"))
        self.assertAlmostEqual(float(node["estimate"]["fix_factor"]), 1.25)
        self.assertAlmostEqual(float(node["estimate"]["scope_ratio"]), 1.1)

    def test_factors_are_optional_and_absent_when_not_given(self):
        code, out = self.run_main(
            ["set-estimate", "--state-root", self.root, "--story", "E001-S01-003",
             "--man-hours", "6"])
        self.assertEqual(code, 0, out)
        _, node = self.load_node(self.story_file("E001-S01-003"))
        self.assertNotIn("fix_factor", node["estimate"])


class TestStorySampling(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)

    def _story(self, iterations, est=None, act=None):
        est = est or {"man_hours": 6, "elapsed_hours": 1.5, "tokens_k": 320,
                      "cost": 4.80, "fix_factor": 1.25, "scope_ratio": 1.0}
        # tokens_k is a mapping on actuals (Task 6) — only "total" is read by
        # the sampler, so these fixtures carry just that key.
        act = act or {"man_hours": 7, "elapsed_hours": 1.8, "tokens_k": {"total": 355},
                      "cost": 5.32}
        node = {"key": "E001-S01-003", "classification": "complex",
                "estimate": est, "actual": act}
        if iterations is not None:
            node["completion_evidence"] = {"fix_iterations": iterations}
        return node

    def test_zero_iterations_gives_exact_provenance(self):
        s = pm.derive_story_sample(self._story(0))
        self.assertEqual(s["provenance"], "exact")

    def test_reworked_story_uses_backout_provenance(self):
        s = pm.derive_story_sample(self._story(3))
        self.assertEqual(s["provenance"], "backout")

    def test_absent_iterations_uses_backout(self):
        s = pm.derive_story_sample(self._story(None))
        self.assertEqual(s["provenance"], "backout")

    def test_legacy_estimate_without_factors_is_marked(self):
        est = {"man_hours": 6, "elapsed_hours": 1.5, "tokens_k": 320, "cost": 4.80}
        s = pm.derive_story_sample(self._story(0, est=est))
        self.assertEqual(s["provenance"], "legacy")

    def test_scope_ratio_computed_correctly_for_elapsed_hours(self):
        # estimate.elapsed_hours 1.5 vs actual.elapsed_hours 1.8, fix_factor 1.25
        s = pm.derive_story_sample(self._story(0))
        self.assertAlmostEqual(s["scope_ratios"]["elapsed_hours"], 1.8 * 1.25 / 1.5)

    def test_scope_ratio_computed_correctly_for_hitl_hours(self):
        # derive_story_sample iterates METRIC_FIELDS, not a hand-restated tuple —
        # this proves hitl_hours flows through the same as every other metric.
        est = {"man_hours": 6, "hitl_hours": 0.5, "elapsed_hours": 1.5, "tokens_k": 320,
               "cost": 4.80, "fix_factor": 1.25, "scope_ratio": 1.0}
        act = {"man_hours": 7, "hitl_hours": 0.6, "elapsed_hours": 1.8,
               "tokens_k": {"total": 355}, "cost": 5.32}
        s = pm.derive_story_sample(self._story(0, est=est, act=act))
        self.assertAlmostEqual(s["scope_ratios"]["hitl_hours"], 0.6 * 1.25 / 0.5)

    def test_na_metrics_are_skipped_not_zeroed(self):
        act = {"man_hours": 7, "elapsed_hours": 1.8, "tokens_k": "N/A", "cost": "N/A"}
        s = pm.derive_story_sample(self._story(0, act=act))
        self.assertNotIn("tokens_k", s["scope_ratios"])
        self.assertNotIn("cost", s["scope_ratios"])
        self.assertIn("man_hours", s["scope_ratios"])

    def test_dollar_prefixed_cost_does_not_break_derivation(self):
        # cost values can be stored '$'-prefixed (metrics-contract.md §9). cost
        # is derived from tokens x rates now and never scope-calibrates (Task
        # 7) — but a '$'-prefixed cost sitting alongside the calibrated
        # metrics must still not crash derivation or leak into scope_ratios.
        est = {"man_hours": 6, "elapsed_hours": 1.5, "tokens_k": 320,
               "cost": "$4.80", "fix_factor": 1.25, "scope_ratio": 1.0}
        act = {"man_hours": 7, "elapsed_hours": 1.8, "tokens_k": {"total": 355},
               "cost": "$5.32"}
        s = pm.derive_story_sample(self._story(0, est=est, act=act))
        self.assertNotIn("cost", s["scope_ratios"])
        self.assertAlmostEqual(s["scope_ratios"]["elapsed_hours"], 1.8 * 1.25 / 1.5)

    def test_no_estimate_yields_no_sample(self):
        node = {"key": "E001-S01-003", "classification": "complex",
                "actual": {"man_hours": 7}}
        self.assertIsNone(pm.derive_story_sample(node))

    def test_record_appends_to_scope_and_fix_cohort(self):
        pm.record_story_sample(self.root, self._story(0))
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(pm._component_samples(cal, "scope", "complex", "man_hours")), 1)
        self.assertEqual(int(cal["fix"]["complex"]["clean"]["samples"]), 1)

    def test_record_appends_the_observed_token_mix(self):
        # A real set-actual write always carries all four classes alongside
        # `total` (tokens_block builds them together) — a fixture with only
        # `total` (the rest of this file's default) can't exercise this.
        act = {"man_hours": 7, "elapsed_hours": 1.8,
               "tokens_k": {"total": 355, "input": 100, "output": 20,
                            "cache_write": 100, "cache_read": 135},
               "cost": 5.32}
        pm.record_story_sample(self.root, self._story(0, act=act))
        _, cal = pm.load_calibration(self.root)
        samples = cal["token_mix"]["samples"]
        self.assertEqual(len(samples), 1)
        self.assertAlmostEqual(samples[0]["input"], 100 / 355, places=4)
        self.assertAlmostEqual(sum(samples[0][c] for c in pm.TOKEN_CLASSES), 1.0, places=3)

    def test_record_skips_token_mix_when_actual_lacks_a_total(self):
        # tokens_k stays a scalar (legacy pre-Task-6 shape, or N/A) — no
        # `.get`, so the mix step must not raise and must not append.
        act = {"man_hours": 7, "elapsed_hours": 1.8, "tokens_k": "N/A", "cost": "N/A"}
        pm.record_story_sample(self.root, self._story(0, act=act))
        _, cal = pm.load_calibration(self.root)
        self.assertNotIn("token_mix", cal)

    def test_reworked_story_joins_reworked_cohort(self):
        pm.record_story_sample(self.root, self._story(2))
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(int(cal["fix"]["complex"]["reworked"]["samples"]), 1)
        self.assertEqual(int(cal["fix"]["complex"].get("clean", {}).get("samples", 0)), 0)

    def test_v1_file_is_migrated_not_corrupted_on_record(self):
        p = pm.calibration_path(self.root)
        with open(p, "w") as f:
            f.write("version: 1\nratio: 1.3\n")
        with redirect_stderr(io.StringIO()):    # migration announces its steps on stderr
            pm.record_story_sample(self.root, self._story(0))
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(cal["version"], pm.CALIBRATION_SCHEMA_VERSION)
        self.assertTrue(os.path.exists(p + ".v1"))
        # The v1->v2 migration seeds scope["complex"]["man_hours"] with the
        # old blended ratio as one sample; the metrics migration (Task 11)
        # then runs in the SAME record_story_sample call, immediately after,
        # and quarantines that seed — it is exactly as pre-rework as any
        # other legacy man_hours sample, just arrived via a different
        # upgrade path. Only the fresh sample this call itself derives lands
        # in scope; the v1 seed survives, moved, under `legacy`.
        self.assertEqual(len(pm._component_samples(cal, "scope", "complex", "man_hours")), 1)
        self.assertEqual(cal["legacy"]["scope"]["complex"]["man_hours"]["samples"], [1.3])
        self.assertEqual(int(cal["fix"]["complex"]["clean"]["samples"]), 1)


class TestEstimateStory(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_cold_start_uses_band_midpoint_times_fix_prior(self):
        code, out = self.run_main(
            ["estimate-story", "--state-root", self.root, "--story", "E001-S01-003",
             "--classification", "complex"])
        self.assertEqual(code, 0, out)
        _, node = self.load_node(self.story_file("E001-S01-003"))
        est = node["estimate"]
        mid = (pm.BASE_BANDS["complex"]["man_hours"][0] +
               pm.BASE_BANDS["complex"]["man_hours"][1]) / 2
        self.assertAlmostEqual(float(est["man_hours"]),
                               round(mid * 1.0 * pm.COLD_START_FIX_FACTOR, 2))
        self.assertAlmostEqual(float(est["fix_factor"]), pm.COLD_START_FIX_FACTOR)
        # per-metric, not a single scalar: the sample derivation divides the
        # applied ratio back out and cannot reconstruct four from one
        for m in ("man_hours", "hitl_hours", "elapsed_hours", "tokens_k"):
            self.assertAlmostEqual(float(est["scope_ratios"][m]),
                                   pm.COLD_START_SCOPE_RATIO)
        # cost is derived from tokens x rates now, never scope-calibrated —
        # it must not appear among the applied ratios at all
        self.assertNotIn("cost", est["scope_ratios"])
        self.assertNotIn("scope_ratio", est)

    def test_calibrated_ratio_is_applied_once_active(self):
        y, cal = pm.load_calibration(self.root)
        cal["scope"]["complex"] = {"man_hours": {"samples": [1.5, 1.5, 1.5]}}
        pm.save_calibration(y, cal, self.root)
        self.run_main(["estimate-story", "--state-root", self.root,
                       "--story", "E001-S01-003", "--classification", "complex"])
        _, node = self.load_node(self.story_file("E001-S01-003"))
        ratios = node["estimate"]["scope_ratios"]
        self.assertAlmostEqual(float(ratios["man_hours"]), 1.5)
        # only man_hours had samples — the other three stay cold-start, which is
        # exactly why one recorded scalar cannot stand in for all four
        self.assertAlmostEqual(float(ratios["tokens_k"]), pm.COLD_START_SCOPE_RATIO)

    def test_unknown_story_exits_3(self):
        code, _ = self.run_main(
            ["estimate-story", "--state-root", self.root, "--story", "E001-S01-999",
             "--classification", "simple"])
        self.assertEqual(code, 3)

    def test_classification_is_written_to_the_node(self):
        self.run_main(["estimate-story", "--state-root", self.root,
                       "--story", "E001-S01-003", "--classification", "simple"])
        _, node = self.load_node(self.story_file("E001-S01-003"))
        self.assertEqual(node["classification"], "simple")


class TestEstimateTokensAndCost(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_split_preserves_the_total_exactly(self):
        got = pm.split_tokens(1160, pm.COLD_START_TOKEN_MIX)
        self.assertEqual(sum(got[c] for c in pm.TOKEN_CLASSES), 1160)
        self.assertEqual(got["input"], 174)
        self.assertEqual(got["cache_read"], 580)

    def test_split_absorbs_rounding_into_the_largest_class(self):
        got = pm.split_tokens(101, {"input": 0.33, "output": 0.33,
                                    "cache_write": 0.33, "cache_read": 0.01})
        self.assertEqual(sum(got[c] for c in pm.TOKEN_CLASSES), 101)

    def test_estimate_story_derives_cost_from_the_split(self):
        code, out = self.run_main(["estimate-story", "--state-root", self.root,
                                   "--story", "E001-S01-003", "--classification", "standard",
                                   "--model", "claude-opus-5"])
        self.assertEqual(code, 0, out)
        _, node = self.load_node(self.story_file("E001-S01-003"))
        est = node["estimate"]
        tk = est["tokens_k"]
        # standard band 40-100, midpoint 70, x scope 1.0 x fix 1.25 = 88 FRESH tokens.
        # The band is fresh-scale (see FRESH_TOKEN_CLASSES), so cache_read is projected
        # from the mix on top rather than carved out of the band: under the cold-start
        # mix the fresh share is 0.15+0.05+0.30 = 0.50 and cache_read is 0.50, so
        # cache_read = 88 x (0.50/0.50) = 88 and the total is 176. The total exceeding
        # the band is the point -- it used to equal it, which is what put a
        # cache-inclusive actual and a fresh band on bases ~1000x apart.
        self.assertEqual(sum(int(tk[c]) for c in pm.FRESH_TOKEN_CLASSES), 88)
        self.assertEqual(int(tk["total"]), 176)
        self.assertEqual(sum(int(tk[c]) for c in pm.TOKEN_CLASSES), 176)
        self.assertAlmostEqual(float(est["cost"]),
                               pm.cost_from_tokens(tk, "claude-opus-5"), places=2)

    def _set_estimate_rejected(self, *extra):
        """Run set-estimate addressing the sprint the way it actually resolves
        kind — via node_args (--epic/--sprint), never --node (that flag
        belongs to set-actual/verify, not set-estimate). Captures stderr so
        the assertion can tell "our rejection fired" apart from "argparse
        choked on an unrecognized flag" — both exit 2, and only the message
        text distinguishes them. This is the same class of --node mismatch
        caught in Task 4; TestEstimateTokensAndCost.test_cost_low_flag_is_rejected
        had it too until this fix."""
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                code = pm.main(self._v7(["set-estimate", "--story", self.STORY]
                                         + list(extra)))
        except SystemExit as e:
            code = e.code
        return code, err.getvalue()

    def test_cost_low_flag_is_rejected(self):
        code, err = self._set_estimate_rejected("--cost-low", "9.00")
        self.assertEqual(code, 2, err)
        self.assertIn("cost is derived from tokens x rates", err)
        self.assertNotIn("unrecognized arguments", err)

    def test_cost_high_flag_is_rejected(self):
        code, err = self._set_estimate_rejected("--cost-high", "9.00")
        self.assertEqual(code, 2, err)
        self.assertIn("cost is derived from tokens x rates", err)
        self.assertNotIn("unrecognized arguments", err)

    def test_cost_flag_is_rejected_on_set_estimate(self):
        # --cost is the story-form alias (see build_parser); exercised on the
        # sprint node too since set-estimate declares it unconditionally, not
        # only for --story.
        code, err = self._set_estimate_rejected("--cost", "9.00")
        self.assertEqual(code, 2, err)
        self.assertIn("cost is derived from tokens x rates", err)
        self.assertNotIn("unrecognized arguments", err)

    def test_observed_mix_falls_back_below_three_samples(self):
        cal = pm.new_calibration()
        self.assertEqual(pm.observed_mix(cal), pm.COLD_START_TOKEN_MIX)

    def test_observed_mix_used_at_three_samples(self):
        cal = pm.new_calibration()
        cal["token_mix"] = {"samples": [
            {"input": 0.5, "output": 0.1, "cache_write": 0.2, "cache_read": 0.2},
            {"input": 0.5, "output": 0.1, "cache_write": 0.2, "cache_read": 0.2},
            {"input": 0.5, "output": 0.1, "cache_write": 0.2, "cache_read": 0.2},
        ]}
        self.assertAlmostEqual(pm.observed_mix(cal)["input"], 0.5, places=3)

    def test_observed_mix_skips_a_non_mapping_sample(self):
        # A stray non-mapping entry -- hand-edit of the committed, shared
        # pm-calibration.yaml, a bad merge, partial corruption -- must not
        # crash observed_mix (and therefore estimate-story) with an
        # AttributeError from calling .get() on something that isn't a
        # mapping. It falls back to cold-start like every other malformed
        # shape here, same as a missing key or a non-numeric value would.
        cal = pm.new_calibration()
        cal["token_mix"] = {"samples": [
            "not-a-mapping",
            {"input": 0.5, "output": 0.1, "cache_write": 0.2, "cache_read": 0.2},
            {"input": 0.5, "output": 0.1, "cache_write": 0.2, "cache_read": 0.2},
        ]}
        # only 2 real mappings present (below MIN_SAMPLES=3 once the stray
        # scalar is excluded) -> cold-start, not a crash and not a mix
        # computed from garbage.
        self.assertEqual(pm.observed_mix(cal), pm.COLD_START_TOKEN_MIX)

    def test_estimate_story_token_rates_override_changes_the_cost(self):
        base_code, base_out = self.run_main(
            ["estimate-story", "--state-root", self.root, "--story", "E001-S01-003",
             "--classification", "standard", "--model", "claude-opus-5"])
        self.assertEqual(base_code, 0, base_out)
        _, node = self.load_node(self.story_file("E001-S01-003"))
        base_cost = float(node["estimate"]["cost"])

        override = '{"claude-opus-5": {"input": 50.0, "output": 250.0, ' \
                    '"cache_write": 62.5, "cache_read": 5.0}}'
        code, out = self.run_main(
            ["estimate-story", "--state-root", self.root, "--story", "E001-S01-003",
             "--classification", "standard", "--model", "claude-opus-5",
             "--token-rates", override])
        self.assertEqual(code, 0, out)
        _, node = self.load_node(self.story_file("E001-S01-003"))
        overridden_cost = float(node["estimate"]["cost"])
        # rates 10x'd -> cost must actually move, proving --token-rates
        # reaches cost_from_tokens rather than being parsed and dropped
        # (the exact defect class Task 3 hit)
        self.assertAlmostEqual(overridden_cost, base_cost * 10, places=1)
        self.assertGreater(overridden_cost, base_cost)

    def test_estimate_story_unknown_model_exits_nonzero(self):
        code, out = self.run_main(
            ["estimate-story", "--state-root", self.root, "--story", "E001-S01-003",
             "--classification", "standard", "--model", "not-a-real-model"])
        self.assertEqual(code, 2, out)


class TestEstimateRollup(unittest.TestCase):
    """`rollup_values`, the epic roll-up `estimate-entries` writes as `[epic].estimate`: the
    entries' sum plus the closure band, in range form, with no sprint between them
    (ADR-0016)."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        _, self.cal = pm.load_calibration(self.root)

    def _rollup(self, values):
        children = [{"estimate": {"man_hours": v, "elapsed_hours": 1, "tokens_k": 10}}
                    for v in values]
        est, counted, _ = pm.metrics.estimates.rollup_values(
            self.cal, "epic", children, pm.DEFAULT_ESTIMATE_MODEL, None)
        return est, counted

    def test_epic_rollup_sums_entries_plus_closure(self):
        est, counted = self._rollup([4, 6])
        self.assertEqual(counted, 2)
        self.assertGreaterEqual(float(est["man_hours_high"]), 10.0)
        self.assertGreater(float(est["man_hours_low"]), 10.0, "the closure band adds on top")
        self.assertLessEqual(float(est["man_hours_low"]), float(est["man_hours_high"]))

    def test_rollup_writes_range_form_not_single_values(self):
        est, _ = self._rollup([4, 6])
        self.assertIn("man_hours_low", est)
        self.assertNotIn("man_hours", est)

    def test_a_child_without_an_estimate_is_not_counted(self):
        children = [{"estimate": {"man_hours": 4}}, {"estimate": {}}]
        _, counted, _ = pm.metrics.estimates.rollup_values(
            self.cal, "epic", children, pm.DEFAULT_ESTIMATE_MODEL, None)
        self.assertEqual(counted, 1)


class TestRollupOrchestrationBand(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _story_estimate(self):
        self.run_main(["estimate-story", "--state-root", self.root,
                       "--story", "E001-S01-003", "--classification", "standard",
                       "--model", "claude-opus-5"])

    @staticmethod
    def _epic_line(out):
        return [json.loads(ln) for ln in out.splitlines() if '"epic"' in ln][-1]

    def test_warns_and_omits_band_while_unseeded(self):
        self._story_estimate()
        with redirect_stderr(io.StringIO()):
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001"])
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(self._epic_line(out)["orchestration_unestimated"]),
                         ["elapsed_hours", "hitl_hours", "man_hours", "tokens_k"])
        _, node = (None, self.epic_node())
        self.assertEqual(node["estimate"]["orchestration_ratios"]["tokens_k"], 0)

    def test_band_applied_once_active(self):
        self._story_estimate()
        with pm.calibration_lock(self.root):
            y, cal = pm.load_calibration(self.root)
            for m in ("man_hours", "hitl_hours", "elapsed_hours", "tokens_k"):
                cal["orchestration"]["epic"][m] = {"samples": [2.0, 2.0, 2.0]}
            pm.save_calibration(y, cal, self.root)
        code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                   "--epic", "E001"])
        self.assertEqual(code, 0, out)
        _, node = (None, self.epic_node())
        est = node["estimate"]
        self.assertAlmostEqual(float(est["orchestration_ratios"]["tokens_k"]), 2.0, places=2)
        # story total 176 (88 fresh + 88 projected cache_read, see
        # test_estimate_story_derives_cost_from_the_split) x
        # (1 + closure 0.10 + orchestration 2.0*0.8) = 176 * 2.70 = 475.2
        self.assertEqual(int(est["tokens_k_min"]), 475)

    def test_rollup_derives_cost_from_rolled_up_tokens(self):
        """cost is no longer banded independently (Task 10): it must be priced
        from the ALREADY-BANDED tokens_k_min/max, not from its own residual."""
        self._story_estimate()
        with redirect_stderr(io.StringIO()):    # unseeded orchestration warns; not under test here
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001"])
        self.assertEqual(code, 0, out)
        _, node = (None, self.epic_node())
        est = node["estimate"]
        _, cal = pm.load_calibration(self.root)
        mix = pm.observed_mix(cal)
        expect_low = pm.cost_from_tokens(pm.split_tokens(float(est["tokens_k_min"]), mix),
                                         "claude-opus-5")
        expect_high = pm.cost_from_tokens(pm.split_tokens(float(est["tokens_k_max"]), mix),
                                          "claude-opus-5")
        self.assertAlmostEqual(float(est["cost_low"]), expect_low, places=2)
        self.assertAlmostEqual(float(est["cost_high"]), expect_high, places=2)
        self.assertEqual(est["model"], "claude-opus-5")

    def test_model_flag_selects_rate_card(self):
        self._story_estimate()
        with redirect_stderr(io.StringIO()):    # unseeded orchestration warns; not under test here
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001",
                                       "--model", "claude-haiku-4-5"])
        self.assertEqual(code, 0, out)
        _, node = (None, self.epic_node())
        est = node["estimate"]
        self.assertEqual(est["model"], "claude-haiku-4-5")
        _, cal = pm.load_calibration(self.root)
        mix = pm.observed_mix(cal)
        expect_low = pm.cost_from_tokens(pm.split_tokens(float(est["tokens_k_min"]), mix),
                                         "claude-haiku-4-5")
        self.assertAlmostEqual(float(est["cost_low"]), expect_low, places=2)

    def test_partial_seed_still_warns_and_names_only_inactive_metrics(self):
        """RULING (Task 10 fix round 1): `not any(orch_applied.values())` only
        fires when EVERY metric is inactive. (The warning is now the roll-up line's
        `orchestration_unestimated` list in estimate-entries' output.) Orchestration calibrates per
        metric, and a metric is sampled only when every child carries a numeric
        actual for it, so a mixed runtime can activate man_hours while
        tokens_k never does — `any()` is then True and the warning would stay
        silent on exactly the metric it exists to flag. Seed only man_hours
        (the other two prior tests seed none or all four) and confirm the
        warning still fires, names the still-inactive metrics, and does not
        name the metric that actually activated."""
        self._story_estimate()
        with pm.calibration_lock(self.root):
            y, cal = pm.load_calibration(self.root)
            cal["orchestration"]["epic"]["man_hours"] = {"samples": [2.0, 2.0, 2.0]}
            pm.save_calibration(y, cal, self.root)
        with redirect_stderr(io.StringIO()):
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001"])
        self.assertEqual(code, 0, out)
        inactive = self._epic_line(out)["orchestration_unestimated"]
        self.assertIn("tokens_k", inactive)
        self.assertIn("hitl_hours", inactive)
        self.assertIn("elapsed_hours", inactive)
        self.assertNotIn("man_hours", inactive)
        _, node = (None, self.epic_node())
        est = node["estimate"]
        self.assertGreater(float(est["orchestration_ratios"]["man_hours"]), 0)
        self.assertEqual(est["orchestration_ratios"]["tokens_k"], 0)

    def test_token_rates_override_moves_the_derived_cost(self):
        """A parsed-but-unapplied flag is a defect class this branch already
        hit once (Task 3's review) — assert the override actually changes the
        priced number, not just that it's accepted without error."""
        self._story_estimate()
        with redirect_stderr(io.StringIO()):    # unseeded orchestration warns; not under test here
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001"])
        self.assertEqual(code, 0, out)
        _, node = (None, self.epic_node())
        baseline_cost = float(node["estimate"]["cost_low"])

        overrides = json.dumps({"claude-opus-5": {"input": 500.0}})
        with redirect_stderr(io.StringIO()):    # unseeded orchestration warns; not under test here
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001",
                                       "--token-rates", overrides])
        self.assertEqual(code, 0, out)
        _, node = (None, self.epic_node())
        overridden_cost = float(node["estimate"]["cost_low"])
        self.assertGreater(overridden_cost, baseline_cost)

    def test_unknown_model_exits_2(self):
        self._story_estimate()
        err = io.StringIO()
        with redirect_stderr(err):
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001",
                                       "--model", "not-a-real-model"])
        self.assertEqual(code, 2, out)
        self.assertIn("unknown model", err.getvalue().lower())


class TestConcurrentAdrReservation(unittest.TestCase):
    """adr-reserve's load->modify->save must run under ONE lock (adr_register_lock),
    mirroring TestConcurrentSampling above. Locking only the write would let two
    parallel reservations both read the same pre-write `next` and print the same
    number to two different agents -- the exact collision (0013 x2, 0014 x2) that
    made ADR numbers need a register in the first place."""

    N = 12

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)

    def test_concurrent_reservations_hand_out_every_number_exactly_once(self):
        import subprocess
        procs = [subprocess.Popen(
            [sys.executable, SCRIPT, "adr-reserve", "--state-root", self.root,
             "--epic", "E001", "--slug", f"slug-{i}",
             "--adr-dir", os.path.join(self.d, "no-adr-dir")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for i in range(1, self.N + 1)]
        # Collected from each process's OWN stdout -- not read back from the
        # register file -- because the file converging on `next: N+1` only
        # proves N writes happened; it does not prove no two callers were ever
        # HANDED the same number, which is the actual defect being guarded.
        numbers = []
        for p in procs:
            out, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err.decode())
            numbers.extend(out.decode().split())
        expected = {f"{n:04d}" for n in range(1, self.N + 1)}
        self.assertEqual(set(numbers), expected,
                         f"duplicate or skipped number across {self.N} concurrent "
                         f"reservations: got {sorted(numbers)}")
        self.assertEqual(len(numbers), self.N, "a process printed more/fewer than one line")


class TestConvergence(unittest.TestCase):
    """Multi-generation convergence — the property every single-sample test
    misses. Each case drives the real loop (estimate -> actual -> re-estimate)
    against a FIXED ground truth for enough generations that a ratio activates
    and feeds back into the next estimate.

    Pre-fix, the scope loop settled on sqrt(truth x band_mid) and the closure
    loop moved the roll-up AWAY from its own observed total. Both are asserted
    against here directly.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    TRUTH_MAN_HOURS = 24.0                     # stable ground truth, well above
    BAND_MID = 12.0                            # the complex band midpoint (8-16)

    # --- scope ------------------------------------------------------------ #
    # The loop v7 runs: estimate-entries estimates a ticket (`compute_story_estimate`),
    # build-close takes its sample (`record_story_sample` over the ticket's estimate,
    # actual and fix iterations).
    def _estimate(self, cls="complex"):
        node = {}
        pm.metrics.estimates.compute_story_estimate(self.root, node, cls,
                                                    pm.DEFAULT_ESTIMATE_MODEL, None)
        return node

    def _close(self, key, node, man_hours):
        node = dict(node, key=key, actual={"man_hours": man_hours},
                    completion_evidence={"fix_iterations": 0})
        with redirect_stderr(io.StringIO()):
            pm.record_story_sample(self.root, node)

    def _scope_generation(self, i):
        """One full turn of the loop: estimate -> fix_iterations -> actual (which samples)."""
        node = self._estimate()
        est = node["estimate"]
        self._close(f"E001-S01-{i:03d}", node, self.TRUTH_MAN_HOURS)
        return float(est["man_hours"]) / float(est["fix_factor"])

    def test_scope_estimate_converges_toward_the_ground_truth(self):
        scope_estimates = [self._scope_generation(i) for i in range(1, 13)]
        final = scope_estimates[-1]
        # the scope component (estimate net of the fix reserve) reaches truth
        self.assertAlmostEqual(final, self.TRUTH_MAN_HOURS, delta=0.05 * self.TRUTH_MAN_HOURS)
        # and it moved TOWARD it, not away
        self.assertLess(abs(final - self.TRUTH_MAN_HOURS),
                        abs(scope_estimates[0] - self.TRUTH_MAN_HOURS))

    def test_scope_does_not_settle_on_the_geometric_mean(self):
        # the pre-fix fixed point: sqrt(truth x band_mid) = sqrt(24 x 12) = 16.97
        geometric = (self.TRUTH_MAN_HOURS * self.BAND_MID) ** 0.5
        final = [self._scope_generation(i) for i in range(1, 13)][-1]
        self.assertGreater(abs(final - geometric), 2.0)

    def test_scope_ratio_reaches_truth_over_band_midpoint(self):
        for i in range(1, 13):
            self._scope_generation(i)
        _, cal = pm.load_calibration(self.root)
        ratio = pm.active_scope_ratio(cal, "complex", "man_hours")
        self.assertAlmostEqual(ratio, self.TRUTH_MAN_HOURS / self.BAND_MID, delta=0.05)

    # --- perfect estimate: no drift --------------------------------------- #
    def test_calibrated_component_does_not_drift_on_a_perfect_estimate(self):
        y, cal = pm.load_calibration(self.root)
        cal["scope"]["complex"] = {"man_hours": {"samples": [2.0, 2.0, 2.0]}}
        # This fixture simulates an ONGOING project that already has 3 real
        # calibrated samples — not a legacy import — so it must also carry
        # the migration marker: a real post-Task-11 deployment's file always
        # does after its first write, and without it the very next
        # set-actual below would (correctly, for a genuinely unmigrated
        # file) quarantine this seed as pre-rework data.
        cal[pm.CALIBRATION_METRICS_MARKER] = pm._now_iso()
        pm.save_calibration(y, cal, self.root)
        for i in range(20, 26):
            node = self._estimate()
            est = node["estimate"]
            # the estimate is exactly right: its scope half equals the truth it
            # was built from, and the story consumed no fix reserve
            actual = float(est["man_hours"]) / float(est["fix_factor"])
            self._close(f"E001-S01-{i:03d}", node, actual)
            _, cal2 = pm.load_calibration(self.root)
            self.assertAlmostEqual(pm.active_scope_ratio(cal2, "complex", "man_hours"),
                                   2.0, delta=1e-6)

    def test_backout_path_sample_is_neutral_when_actual_equals_estimate(self):
        node = {"key": "E001-S01-003", "classification": "complex",
                "completion_evidence": {"fix_iterations": 2},
                "estimate": {"man_hours": 10.0, "fix_factor": 1.25,
                             "scope_ratios": {"man_hours": 1.4}},
                "actual": {"man_hours": 10.0}}
        s = pm.derive_story_sample(node)
        self.assertAlmostEqual(s["scope_ratios"]["man_hours"], 1.4)

    # --- closure ----------------------------------------------------------- #
    CHILD_ESTIMATE = 10.0
    CHILDREN = 4
    TRUE_CLOSURE_OVERHEAD = 8.0

    # The loop v7 runs: estimate-entries rolls the entries up (`rollup_values`), epic-close
    # measures the closure and appends its ratio (`closure_ratio`, `append_closure_ratios`).
    def _children(self):
        return [{"estimate": {"man_hours": self.CHILD_ESTIMATE},
                 "actual": {"man_hours": self.CHILD_ESTIMATE}} for _ in range(self.CHILDREN)]

    def _rollup(self):
        _, cal = pm.load_calibration(self.root)
        est, _, _ = pm.metrics.estimates.rollup_values(cal, "epic", self._children(),
                                                       pm.DEFAULT_ESTIMATE_MODEL, None)
        return est

    @staticmethod
    def _mid(est):
        return (float(est["man_hours_low"]) + float(est["man_hours_high"])) / 2.0

    def _closure_generation(self, n):
        est = self._rollup()
        ratio, why = pm.metrics.calibration.closure_ratio(
            "epic", "man_hours", self.TRUE_CLOSURE_OVERHEAD, est, self._children())
        self.assertEqual(why, "")
        pm.metrics.calibration.append_closure_ratios(self.root, "epic", {"man_hours": ratio})
        return self._mid(est)

    def test_learned_closure_rollup_is_closer_to_truth_than_cold_start(self):
        truth = self.CHILDREN * self.CHILD_ESTIMATE + self.TRUE_CLOSURE_OVERHEAD  # 48
        cold_start = self._closure_generation(2)
        for n in range(3, 9):
            self._closure_generation(n)
        learned = self._mid(self._rollup())
        self.assertLess(abs(learned - truth), abs(cold_start - truth))
        self.assertAlmostEqual(learned, truth, delta=0.01 * truth)

    def test_closure_ratio_is_stable_across_generations(self):
        # every generation observes the same 8.0 of overhead, so the ratio must
        # stop moving once it is active — not oscillate around a geometric mean
        for n in range(2, 9):
            self._closure_generation(n)
        _, cal = pm.load_calibration(self.root)
        samples = [float(s) for s in
                   pm._component_samples(cal, "closure", "epic", "man_hours")]
        self.assertGreaterEqual(len(samples), 6)
        for s in samples[3:]:
            self.assertAlmostEqual(s, samples[0], delta=0.01)


class TestEvents(TestLayoutResolution):
    """events.jsonl — the append-only log the progress report and dwell time read."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, buf.getvalue()

    def read_events(self):
        p = pm.events_path(self.root)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def _set_actual(self, *extra):
        return self.run_main(["set-actual", "--story", self.STORY, "--elapsed-hours", "2",
                              "--man-hours", "3", "--tokens-input", "10",
                              "--model", "claude-sonnet-5", *extra])

    def test_set_actual_appends_actual_event(self):
        code, out = self._set_actual("--session-id", "sess-abc")
        self.assertEqual(code, 0, out)
        evs = [e for e in self.read_events() if e["event"] == "actual"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["node"], "ticket")
        self.assertEqual(evs[0]["key"], "3")
        self.assertEqual(evs[0]["session"], "sess-abc")

    def test_no_events_flag_suppresses(self):
        code, out = self._set_actual("--no-events")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.read_events(), [])

    def test_append_failure_warns_but_write_succeeds(self):
        # Plant a directory where the log file goes, so open(..., "a") must fail.
        os.makedirs(pm.events_path(self.root))
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, out = self._set_actual()
        self.assertEqual(code, 0, out)
        self.assertIn("could not append event", buf.getvalue())
        _, node = self.load_node(self.story_file(self.STORY))
        self.assertEqual(node["actual"]["man_hours"], 3)

    def test_concurrent_appends_lose_no_lines(self):
        import threading

        def worker(i):
            pm.append_event(self.root, {"event": "status", "n": i})

        ts = [threading.Thread(target=worker, args=(i,)) for i in range(40)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(len(self.read_events()), 40)


class TestDispatchEvents(Base):
    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)

    def test_open_then_close_leaves_nothing_open(self):
        code, out = self.run_main(["dispatch", "--state-root", self.root, "--event", "open",
                                   "--agent", "dev-story", "--epic", "E001", "--sprint", "S01",
                                   "--story", "E001-S01-003"])
        self.assertEqual(code, 0, out)
        code, out = self.run_main(["dispatch", "--state-root", self.root, "--event", "close",
                                   "--agent", "dev-story", "--epic", "E001", "--sprint", "S01",
                                   "--story", "E001-S01-003"])
        self.assertEqual(code, 0, out)
        self.assertEqual(pm.open_dispatches(self.root, 0), [])

    def test_unclosed_dispatch_past_threshold_is_reported(self):
        self.run_main(["dispatch", "--state-root", self.root, "--event", "open",
                       "--agent", "code-review", "--epic", "E001", "--sprint", "S01"])
        # 0-minute threshold: any open dispatch qualifies
        stalled = pm.open_dispatches(self.root, 0)
        self.assertEqual(len(stalled), 1)
        self.assertEqual(stalled[0]["agent"], "code-review")
        self.assertEqual(stalled[0]["sprint"], "S01")

    def test_threshold_excludes_young_dispatches(self):
        self.run_main(["dispatch", "--state-root", self.root, "--event", "open",
                       "--agent", "dev-story", "--epic", "E001"])
        self.assertEqual(pm.open_dispatches(self.root, 15), [])

    def _raw_event(self, **rec):
        """Append a record to events.jsonl verbatim, bypassing the write path.

        The defect below cannot be reproduced through the CLI: every close is
        canonicalised on the way in, so only a record that predates the
        canonicalisation can sit on the wrong side of the comparison. The log is
        append-only, so such records are permanent and the fixture has to be the
        historical bytes, not something the current writer can produce."""
        with open(pm.events_path(self.root), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")

    def test_close_cancels_an_open_written_before_key_canonicalisation(self):
        """3.2.4 canonicalised the five dispatch WRITE sites and left the reader
        comparing raw values, so a close could not cancel an older open.

        Pre-3.2.4 an open stored the caller's spelling: `--sprint 01` wrote '01'.
        Closes now write 'S01'. `_dispatch_identity` is (agent, epic, sprint,
        story), so '01' != 'S01' and `pending.pop` missed — the dispatch read as
        permanently stalled with no CLI route to clear it, because the canonical
        write path cannot emit a close that matches a non-canonical open.

        Measured on a consumer tree (their commit c4359268): 7 stalled dispatches,
        the 4 epic-level ones cleared because 'E0nn' is already what
        canonical_epic_key returns, and all 3 story-level ones did not."""
        self._raw_event(ts="2026-08-24T10:00:00+00:00", event="dispatch_open",
                        agent="l3io-pm-story", epic="E013", sprint="01",
                        story="E013-S01-001")
        self.assertEqual(len(pm.open_dispatches(self.root, 0)), 1)
        code, out = self.run_main(["dispatch", "--state-root", self.root, "--event", "close",
                                   "--agent", "l3io-pm-story", "--epic", "E013",
                                   "--sprint", "01", "--story", "E013-S01-001"])
        self.assertEqual(code, 0, out)
        self.assertEqual(pm.open_dispatches(self.root, 0), [])

    def test_close_cancels_an_open_whose_epic_was_stored_unpadded(self):
        """The same read-side fix over the epic axis. An open holding '13' or 'e13'
        is cancelled by a close spelled 'E013' — canonicalising on read makes every
        historical spelling comparable without rewriting the append-only log."""
        self._raw_event(ts="2026-08-24T10:00:00+00:00", event="dispatch_open",
                        agent="code-review", epic="13", sprint="S01")
        code, out = self.run_main(["dispatch", "--state-root", self.root, "--event", "close",
                                   "--agent", "code-review", "--epic", "E013",
                                   "--sprint", "S01"])
        self.assertEqual(code, 0, out)
        self.assertEqual(pm.open_dispatches(self.root, 0), [])

    def test_close_says_whether_it_cancelled_an_open(self):
        """`OK dispatch close` printed unconditionally, so a close that cancelled
        nothing was indistinguishable from one that worked. An orphan close stays
        exit 0 — legitimate on a log that may begin mid-run — but it says so."""
        self.run_main(["dispatch", "--state-root", self.root, "--event", "open",
                       "--agent", "dev-story", "--epic", "E001", "--sprint", "S01"])
        code, out = self.run_main(["dispatch", "--state-root", self.root, "--event", "close",
                                   "--agent", "dev-story", "--epic", "E001", "--sprint", "S01"])
        self.assertEqual(code, 0, out)
        self.assertIn("cancelled", out)
        code, out = self.run_main(["dispatch", "--state-root", self.root, "--event", "close",
                                   "--agent", "dev-story", "--epic", "E001", "--sprint", "S01"])
        self.assertEqual(code, 0, out)
        self.assertIn("no matching open", out)

    def test_malformed_node_key_in_a_record_does_not_crash_the_reader(self):
        """Canonicalising on read must stay total. `open_dispatches` is the read
        behind `report --watch`, and its contract is that a torn or hand-edited
        line is skipped rather than dereferenced — a raise here takes down exactly
        the stall dashboard the feature exists to provide."""
        self._raw_event(ts="2026-08-24T10:00:00+00:00", event="dispatch_open",
                        agent="a", epic="not-a-key!", sprint=["also", "not"])
        stalled = pm.open_dispatches(self.root, 0)
        self.assertEqual(len(stalled), 1)
        self.assertEqual(stalled[0]["agent"], "a")


class TestPartialTokenClasses(TestLayoutResolution):
    """I3: under runtime=claude an incomplete class set was zero-filled and then
    blessed by verify. `--tokens-output 10` alone wrote total=10 with three
    classes at 0, derived a cost from that, and verify PASSed — internally
    consistent, therefore unfalsifiable. Cache classes dominate real runs, so one
    forgotten flag understates a node by an order of magnitude."""

    def run_main(self, argv):
        buf, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(err):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue() + err.getvalue()

    def _set(self, extra):
        return self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                              "--story", "E001-S01-003", "--model", "claude-opus-5",
                              "--no-calibrate"] + extra)

    def test_claude_rejects_a_single_class(self):
        code, out = self._set(["--runtime", "claude", "--tokens-output", "10"])
        self.assertEqual(code, 2, out)
        self.assertIn("all four token classes", out)
        self.assertIn("--tokens-input", out)
        self.assertIn("--tokens-cache-write", out)
        self.assertIn("--tokens-cache-read", out)

    def test_claude_rejects_three_of_four(self):
        code, out = self._set(["--runtime", "claude", "--tokens-input", "1",
                               "--tokens-output", "2", "--tokens-cache-write", "3"])
        self.assertEqual(code, 2, out)
        self.assertIn("cache-read", out)

    def test_explicit_zero_counts_as_given(self):
        code, out = self._set(["--runtime", "claude", "--tokens-input", "10",
                               "--tokens-output", "0", "--tokens-cache-write", "0",
                               "--tokens-cache-read", "0"])
        self.assertEqual(code, 0, out)
        _, node = self.load_node(self.story_file("E001-S01-003"))
        self.assertEqual(int(node["actual"]["tokens_k"]["total"]), 10)

    def test_runtime_other_still_accepts_a_partial_set(self):
        # A runtime that exposes only some classes is exactly what --runtime
        # other is for; the strict rule must not leak into it.
        code, out = self._set(["--runtime", "other", "--tokens-output", "10"])
        self.assertEqual(code, 0, out)

    def test_nothing_is_written_when_the_partial_set_is_rejected(self):
        self._set(["--runtime", "claude", "--tokens-output", "10"])
        _, node = self.load_node(self.story_file("E001-S01-003"))
        self.assertNotIn("actual", node)


class TestVerifyRejectsScalarTokens(TestLayoutResolution):
    """I4: verify skipped the cost invariant entirely when tokens_k was a bare
    scalar (`if hasattr(tk, "get")`), so `tokens_k: 500` beside `cost: 9999.99`
    returned PASS under runtime=claude. Design §4.3 says a hand-edited cost
    cannot survive verify."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _scalar_node(self, cost=9999.99):
        p = self.story_file("E001-S01-003")
        y, node = self.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 1.0, "man_hours": 8, "hitl_hours": 0.2,
                          "tokens_k": 500, "cost": cost, "model": "claude-opus-5"}
        self.save_node(y, node, p)

    def test_scalar_tokens_fail_under_runtime_claude(self):
        self._scalar_node()
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--runtime", "claude"])
        self.assertEqual(code, 4, out)
        self.assertIn("not the per-class mapping", out)

    def test_scalar_tokens_fail_under_require_tokens(self):
        self._scalar_node()
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--require-tokens"])
        self.assertEqual(code, 4, out)

    def test_scalar_tokens_still_pass_under_runtime_other(self):
        # set-estimate writes a scalar, and a runtime with no per-class
        # visibility has nothing better — the scalar form stays legitimate here.
        self._scalar_node()
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--runtime", "other"])
        self.assertEqual(code, 0, out)

    def test_na_tokens_are_not_reported_as_a_scalar(self):
        p = self.story_file("E001-S01-003")
        y, node = self.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 1.0, "man_hours": 8, "hitl_hours": 0.2,
                          "tokens_k": "N/A", "cost": "N/A"}
        self.save_node(y, node, p)
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--runtime", "claude"])
        self.assertEqual(code, 4, out)
        self.assertNotIn("not the per-class mapping", out)
        self.assertIn("N/A", out)


class TestMalformedEventLog(Base):
    """I5/M3: open_dispatches dereferenced every valid-JSON line without an
    isinstance guard and read the file without an OSError guard, while
    build_events_index next door had both. A line containing `42` — a torn write
    on an append-only log with concurrent writers — crashed `report` with
    AttributeError and exit 1, taking down the stall dashboard itself."""

    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.d, "state")
        os.makedirs(os.path.join(self.root, "active"))

    def _append(self, raw):
        with open(pm.events_path(self.root), "a", encoding="utf-8") as fh:
            fh.write(raw + "\n")

    def test_bare_scalar_line_does_not_crash_open_dispatches(self):
        self.run_main(["dispatch", "--state-root", self.root, "--event", "open",
                       "--agent", "dev-story", "--epic", "E001", "--sprint", "S01"])
        self._append("42")
        stalled = pm.open_dispatches(self.root, 0)
        self.assertEqual(len(stalled), 1)
        self.assertEqual(stalled[0]["agent"], "dev-story")

    def test_json_list_line_is_skipped_too(self):
        self._append('["dispatch_open"]')
        self.run_main(["dispatch", "--state-root", self.root, "--event", "open",
                       "--agent", "code-review", "--epic", "E001"])
        self.assertEqual(len(pm.open_dispatches(self.root, 0)), 1)


class TestRates(Base):
    def test_cost_from_tokens_opus5(self):
        tokens = {"input": 174, "output": 58, "cache_write": 348, "cache_read": 580}
        # (174*5 + 58*25 + 348*6.25 + 580*0.50) / 1000
        self.assertAlmostEqual(pm.cost_from_tokens(tokens, "claude-opus-5"), 4.79, places=2)

    def test_same_tokens_cost_double_on_a_10_per_m_tier(self):
        tokens = {"input": 174, "output": 58, "cache_write": 348, "cache_read": 580}
        self.assertAlmostEqual(pm.cost_from_tokens(tokens, "claude-fable-5"), 9.57, places=2)

    def test_cache_write_dominates_a_cache_heavy_mix(self):
        tokens = {"input": 412, "output": 34, "cache_write": 4300, "cache_read": 253}
        self.assertAlmostEqual(pm.cost_from_tokens(tokens, "claude-opus-5"), 29.91, places=2)

    def test_unknown_model_is_a_hard_error(self):
        with self.assertRaises(KeyError):
            pm.cost_from_tokens({"input": 1}, "claude-not-a-model")

    def test_missing_class_counts_as_zero(self):
        self.assertAlmostEqual(pm.cost_from_tokens({"output": 10}, "claude-opus-5"), 0.25, places=2)

    def test_overrides_win(self):
        over = {"claude-opus-5": {"input": 1.0, "output": 1.0,
                                 "cache_write": 1.0, "cache_read": 1.0}}
        self.assertAlmostEqual(
            pm.cost_from_tokens({"input": 1000}, "claude-opus-5", over), 1.00, places=2)

    def test_rates_subcommand_prints_the_effective_table(self):
        code, out = self.run_main(["rates", "--model", "claude-opus-5"])
        self.assertEqual(code, 0, out)
        self.assertIn("cache_write", out)
        self.assertIn("6.25", out)

    def test_rates_subcommand_rejects_unknown_model(self):
        with redirect_stderr(io.StringIO()):
            code, out = self.run_main(["rates", "--model", "nope"])
        self.assertEqual(code, 2, out)

    def test_rates_lists_override_only_models(self):
        # design §5: `rates` prints the EFFECTIVE table after config overrides.
        # Listing sorted(TOKEN_RATES) alone hid exactly the models a project had
        # to add by hand (Bedrock/Vertex cards), which is when inspecting the
        # table matters most.
        over = json.dumps({"bedrock-opus": {"input": 6.0, "output": 30.0,
                                            "cache_write": 7.5, "cache_read": 0.6}})
        code, out = self.run_main(["rates", "--token-rates", over])
        self.assertEqual(code, 0, out)
        self.assertIn("bedrock-opus", out)
        self.assertIn("claude-opus-5", out)

    def test_rates_reports_a_partial_override_model_without_crashing(self):
        over = json.dumps({"partial-model": {"input": 6.0}})
        code, out = self.run_main(["rates", "--token-rates", over])
        self.assertEqual(code, 0, out)
        self.assertIn("partial-model", out)
        self.assertIn("cache_read=n/a", out)

    def test_partial_rate_card_is_a_hard_error_when_pricing(self):
        over = {"partial-model": {"input": 6.0}}
        with self.assertRaises(KeyError) as ctx:
            pm.cost_from_tokens({"input": 1, "cache_read": 1}, "partial-model", over)
        self.assertIn("cache_read", ctx.exception.args[0])


class TestFreshTokenScopeBasis(Base):
    """The scope ratio measures fresh tokens, not the cache-inclusive total.

    BASE_BANDS' tokens_k numbers are fresh-token scale (20-200k) while actuals are
    captured cache-inclusive. A real story measured 182,121k with 97.4% cache reads,
    so `actual.total / band` silently absorbed a ~1000x basis gap. The per-class
    evidence showed it was a basis error and not signal: the complex bucket read
    285.291 over five samples straddling the accounting change, standard 7.386 over
    three that did not.
    """

    def _story(self, fresh, cache_read, band_mid=140.0):
        """A closed story whose estimate came from the complex band."""
        return {
            "key": "E001-S01-001", "classification": "complex",
            "estimate": {"fix_factor": 1.0,
                         "scope_ratios": {"tokens_k": 1.0},
                         "tokens_k": {"total": band_mid}},
            "actual": {"tokens_k": {"total": fresh + cache_read,
                                    "input": fresh * 0.2, "output": fresh * 0.1,
                                    "cache_write": fresh * 0.7,
                                    "cache_read": cache_read}},
            "completion_evidence": {"fix_iterations": 0},
        }

    def test_ratio_ignores_cache_read(self):
        fresh, cache_read = 4735.0, 177386.0        # the observed 97.4% split
        sample = pm.derive_story_sample(self._story(fresh, cache_read))
        got = sample["scope_ratios"]["tokens_k"]
        self.assertAlmostEqual(got, fresh / 140.0, places=3)
        poisoned = (fresh + cache_read) / 140.0
        self.assertGreater(poisoned / got, 30,
                           "premise: the old basis was orders of magnitude larger")

    def test_cache_read_volume_does_not_move_the_ratio(self):
        """Same story, ten times the corpus. Scope is unchanged, so the ratio must be."""
        a = pm.derive_story_sample(self._story(4735.0, 177386.0))["scope_ratios"]["tokens_k"]
        b = pm.derive_story_sample(self._story(4735.0, 1773860.0))["scope_ratios"]["tokens_k"]
        self.assertAlmostEqual(a, b, places=6)

    def test_no_fresh_tokens_yields_no_scope_sample(self):
        n = self._story(0.0, 177386.0)
        sample = pm.derive_story_sample(n)
        self.assertNotIn("tokens_k", (sample or {}).get("scope_ratios", {}))


class TestTokenBasisMigration(Base):
    def _cal(self, extra=""):
        root = os.path.join(self.d, "state")
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, "pm-calibration.yaml"), "w", encoding="utf-8") as fh:
            fh.write("version: 2\nmetrics_migrated_at: '2026-01-01T00:00:00+00:00'\n"
                     "scope:\n  complex:\n    tokens_k:\n      samples: [285.291, 300.0, 270.0]\n"
                     "    man_hours:\n      samples: [1.1, 1.2, 1.3]\n"
                     "token_mix:\n  samples:\n  - {input: 0.01, output: 0.005, "
                     "cache_write: 0.011, cache_read: 0.974}\n" + extra)
        return root

    def test_purges_poisoned_tokens_k_but_keeps_everything_else(self):
        root = self._cal()
        y, cal = pm.load_calibration(root)
        log = pm.migrate_calibration_token_basis(y, cal, root)
        self.assertTrue(any("PURGE" in l for l in log), log)
        self.assertEqual(cal["scope"]["complex"]["tokens_k"]["samples"], [])
        self.assertEqual(cal["scope"]["complex"]["man_hours"]["samples"], [1.1, 1.2, 1.3],
                         "man_hours was never measured in tokens")
        self.assertEqual(len(cal["token_mix"]["samples"]), 1,
                         "token_mix is per-class fractions — basis-independent, and the "
                         "evidence for this very change")
        self.assertEqual(cal.get("version"), 2, "no schema version bump")

    def test_migration_is_one_shot(self):
        root = self._cal()
        y, cal = pm.load_calibration(root)
        pm.migrate_calibration_token_basis(y, cal, root)
        cal["scope"]["complex"]["tokens_k"]["samples"] = [1.0, 1.1, 1.2]
        self.assertEqual(pm.migrate_calibration_token_basis(y, cal, root), [])
        self.assertEqual(cal["scope"]["complex"]["tokens_k"]["samples"], [1.0, 1.1, 1.2],
                         "post-migration samples are on the new basis and must survive")

    def test_read_only_never_applies_a_pre_basis_ratio(self):
        cal = {"scope": {"complex": {"tokens_k": {"samples": [285.291, 300.0, 270.0]}}}}
        self.assertIsNone(pm.active_scope_ratio(cal, "complex", "tokens_k"),
                          "an unmigrated file must fall back to cold start, not apply 285x")
        cal[pm.TOKEN_BASIS_MARKER] = "2026-01-01T00:00:00+00:00"
        self.assertIsNotNone(pm.active_scope_ratio(cal, "complex", "tokens_k"))


class TestTranscriptUsage(Base):
    """The three traps in "read the usage fields", each reproduced.

    Two inflate and one deflates, which is why an agent that hit all three produced a
    plausible-looking wrong answer (the errors partly cancel) rather than an
    obviously broken one. Shapes here match a real transcript: 2,482 assistant records
    over 953 distinct message ids, with nested cache_creation summing to the flat field
    in every record.
    """

    def _write(self, name, records):
        p = os.path.join(self.d, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(r) + "\n" for r in records)
        return p

    def _asst(self, mid, inp, out, cw, cr, sidechain=False):
        return {"type": "assistant", "isSidechain": sidechain,
                "message": {"id": mid, "usage": {
                    "input_tokens": inp, "output_tokens": out,
                    "cache_creation_input_tokens": cw,
                    "cache_read_input_tokens": cr,
                    # the nested form carries the SAME tokens as the flat field
                    "cache_creation": {"ephemeral_5m_input_tokens": cw,
                                       "ephemeral_1h_input_tokens": 0}}}}

    def test_trap1_repeated_records_of_one_message_count_once(self):
        """A streaming message is written many times with identical id and usage."""
        recs = [self._asst("msg_a", 10, 20, 30, 40)] * 5 + [self._asst("msg_b", 1, 2, 3, 4)]
        res = pm.read_transcript_usage(self._write("t.jsonl", recs))
        self.assertEqual(res["records"], 6)
        self.assertEqual(res["unique_messages"], 2)
        self.assertEqual(res["tokens"], {"input": 11, "output": 22,
                                         "cache_write": 33, "cache_read": 44})

    def test_trap2_nested_cache_creation_is_not_added_to_the_flat_field(self):
        res = pm.read_transcript_usage(self._write("t.jsonl", [self._asst("m", 0, 0, 500, 0)]))
        self.assertEqual(res["tokens"]["cache_write"], 500,
                         "the nested mapping is the same tokens as the flat field")

    def test_trap3_sidechain_subagent_turns_are_counted(self):
        recs = [self._asst("main", 1, 1, 1, 1),
                self._asst("sub", 100, 100, 100, 100, sidechain=True)]
        res = pm.read_transcript_usage(self._write("t.jsonl", recs))
        self.assertEqual(res["sidechain_messages"], 1)
        self.assertEqual(res["tokens"]["input"], 101,
                         "dropping subagent turns is the deflating half of the error")

    def test_a_directory_sums_a_run_split_across_files(self):
        sub = os.path.join(self.d, "run")
        os.makedirs(sub)
        self._write(os.path.join("run", "a.jsonl"), [self._asst("a", 1, 1, 1, 1)])
        self._write(os.path.join("run", "b.jsonl"), [self._asst("b", 2, 2, 2, 2)])
        res = pm.read_transcript_usage(sub)
        self.assertEqual(res["files"], 2)
        self.assertEqual(res["tokens"]["input"], 3)

    def test_non_assistant_and_torn_lines_are_skipped_not_fatal(self):
        p = os.path.join(self.d, "t.jsonl")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "user", "message": {"usage": {"input_tokens": 999}}}) + "\n")
            fh.write("{not json\n")
            fh.write("42\n")
            fh.write(json.dumps(self._asst("m", 5, 0, 0, 0)) + "\n")
        res = pm.read_transcript_usage(p)
        self.assertEqual(res["tokens"]["input"], 5)

    def test_all_three_traps_together_match_a_hand_check(self):
        """The combined case: without the fixes this reads high on two axes and low on one."""
        recs = ([self._asst("m1", 10, 10, 100, 1000)] * 3 +
                [self._asst("m2", 10, 10, 100, 1000, sidechain=True)] * 2)
        res = pm.read_transcript_usage(self._write("t.jsonl", recs))
        self.assertEqual(res["tokens"], {"input": 20, "output": 20,
                                         "cache_write": 200, "cache_read": 2000})
        naive_records = 5 * 1000
        self.assertLess(res["tokens"]["cache_read"], naive_records,
                        "summing records rather than ids overstates")

    def test_usage_command_emits_pasteable_set_actual_flags(self):
        # A realistic fixture carries sessionId: the CLI checks identity before summing,
        # so a transcript without one is refused (see TestTranscriptIdentity).
        rec = self._asst("m", 1000, 2000, 3000, 4000)
        rec["sessionId"] = "SESS-1"
        rec["timestamp"] = "2026-08-01T12:00:00.000Z"
        p = self._write("t.jsonl", [rec])
        # Scoped, because the flags are withheld on an unscoped read: a session total is
        # not a node's actual (see TestTranscriptScoping).
        code, out = self.run_main(["usage", p, "--claude-session", "SESS-1",
                                   "--since", "2026-08-01T11:00:00.000Z",
                                   "--until", "2026-08-01T13:00:00.000Z",
                                   "--model", "claude-opus-5"])
        self.assertEqual(code, 0, out)
        self.assertIn("--tokens-input 1.000", out)
        self.assertIn("--tokens-cache-write 3.000", out)
        self.assertIn("cost", out)


class TestTranscriptIdentity(Base):
    """"Which transcript is mine" — the trap that produced the original bad number.

    Pointed at a task `.output` artifact rather than a session transcript, a count
    reported an output count several times below what the agent that ran the story
    reported. The cache
    figures matched closely, so nothing looked wrong: it was file choice, not arithmetic.
    A reader that can be aimed at the wrong file has not fixed that, it has moved it one
    step earlier — so identity is checked before any summing happens.
    """

    def _sess_file(self, name, sid, n=2):
        p = os.path.join(self.d, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps({
                    "type": "assistant", "sessionId": sid,
                    "message": {"id": f"m{i}", "usage": {
                        "input_tokens": 1, "output_tokens": 1,
                        "cache_creation_input_tokens": 1, "cache_read_input_tokens": 1}}}) + "\n" for i in range(n))
        return p

    def test_refuses_a_file_carrying_no_session_id(self):
        """The .output artifact shape: assistant records, plausible usage, no sessionId."""
        p = os.path.join(self.d, "task.output.jsonl")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "assistant",
                                 "message": {"id": "m", "usage": {"output_tokens": 11931}}}) + "\n")
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["usage", p, "--claude-session", "S1"])
        self.assertEqual(code, 2)
        self.assertIn("not a session transcript", buf.getvalue())

    def test_refuses_a_transcript_belonging_to_another_session(self):
        p = self._sess_file("other.jsonl", "SOMEONE-ELSE")
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["usage", p, "--claude-session", "MINE"])
        self.assertEqual(code, 2)
        self.assertIn("SOMEONE-ELSE", buf.getvalue())

    def test_refuses_a_file_mixing_sessions(self):
        p = os.path.join(self.d, "mixed.jsonl")
        with open(p, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps({"type": "assistant", "sessionId": sid,
                                     "message": {"id": sid, "usage": {"output_tokens": 1}}}) + "\n" for sid in ("A", "B"))
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["usage", p])
        self.assertEqual(code, 2)
        self.assertIn("mixes", buf.getvalue())

    def test_accepts_the_matching_session(self):
        p = self._sess_file("mine.jsonl", "MINE")
        code, out = self.run_main(["usage", p, "--claude-session", "MINE"])
        self.assertEqual(code, 0, out)
        self.assertIn("MINE", out)
        self.assertIn("identity checked", out)

    def test_refuses_to_guess_when_nothing_identifies_the_session(self):
        old = os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        try:
            buf = io.StringIO()
            with redirect_stderr(buf):
                code, _ = self.run_main(["usage"])
            self.assertEqual(code, 2)
            self.assertIn("Refusing to", buf.getvalue())
        finally:
            if old is not None:
                os.environ["CLAUDE_CODE_SESSION_ID"] = old

    def test_override_is_available_but_labels_the_result_unverified(self):
        """The escape hatch must not let the output claim provenance it never checked."""
        p = self._sess_file("other.jsonl", "SOMEONE-ELSE")
        code, out = self.run_main(["usage", p, "--claude-session", "MINE",
                                   "--allow-unidentified"])
        self.assertEqual(code, 0, out)
        self.assertIn("UNVERIFIED", out)
        self.assertIn("identity NOT checked", out)
        self.assertNotIn("session MINE ", out)

    def test_resolver_finds_a_transcript_by_session_id(self):
        paths, sid = pm.resolve_session_transcript("definitely-not-a-real-session-id")
        self.assertEqual(paths, [])
        self.assertEqual(sid, "definitely-not-a-real-session-id")


class TestTranscriptScoping(Base):
    """Identity is not scope. Both defects found in 2.4.6's reader.

    The reader resolved the right transcript and verified it, then summed all of it.
    A session file spans everything that session ever did: one observed file covered a
    whole epic lineage and totalled ~66x the sprint being closed, which as a node actual
    would have poisoned calibration for the rest of the epic. Separately, the no-argument
    path reported sidechain=0 on every run, because subagent turns are not in the parent
    file at all -- they live in <session-id>/subagents/agent-*.jsonl.
    """

    def _rec(self, mid, ts, out=10, sid="S1", side=False):
        return {"type": "assistant", "sessionId": sid, "isSidechain": side,
                "timestamp": ts,
                "message": {"id": mid, "usage": {
                    "input_tokens": 0, "output_tokens": out,
                    "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}}

    def _write(self, name, recs):
        p = os.path.join(self.d, name)
        os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(name) else None
        with open(p, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(r) + "\n" for r in recs)
        return p

    def test_window_excludes_records_outside_the_bracket(self):
        p = self._write("t.jsonl", [
            self._rec("before", "2026-08-01T10:00:00.000Z", out=1000),
            self._rec("inside", "2026-08-01T12:00:00.000Z", out=7),
            self._rec("after",  "2026-08-01T14:00:00.000Z", out=1000)])
        res = pm.read_transcript_usage(
            p, since=pm._parse_iso("2026-08-01T11:00:00.000Z"),
            until=pm._parse_iso("2026-08-01T13:00:00.000Z"))
        self.assertEqual(res["tokens"]["output"], 7)
        self.assertEqual(res["outside_window"], 2)
        self.assertTrue(res["windowed"])

    def test_unwindowed_read_sums_the_whole_session(self):
        """The defect, reproduced: without a window the total is the session, not the node."""
        p = self._write("t.jsonl", [
            self._rec("a", "2026-08-01T10:00:00.000Z", out=1000),
            self._rec("b", "2026-08-01T12:00:00.000Z", out=7)])
        res = pm.read_transcript_usage(p)
        self.assertEqual(res["tokens"]["output"], 1007)
        self.assertFalse(res["windowed"])

    def test_dispatch_window_uses_first_open_and_last_close(self):
        """A story is re-dispatched per fix iteration; all of it is that story's spend."""
        root = os.path.join(self.d, "state")
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, "events.jsonl"), "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps({"ts": ts, "event": ev, "agent": "bmad-dev-story",
                                     "epic": "E001", "story": "E001-S01-001"}) + "\n" for ev, ts in [("dispatch_open", "2026-08-01T10:00:00+00:00"),
                           ("dispatch_close", "2026-08-01T11:00:00+00:00"),
                           ("dispatch_open", "2026-08-01T12:00:00+00:00"),
                           ("dispatch_close", "2026-08-01T13:00:00+00:00")])
            fh.write(json.dumps({"ts": "2026-08-01T20:00:00+00:00", "event": "dispatch_open",
                                 "agent": "bmad-dev-story", "epic": "E001",
                                 "story": "E001-S01-999"}) + "\n")
        a, b = pm.metrics.actuals_usage.dispatch_window(root, story="E001-S01-001")
        self.assertEqual(a, pm._parse_iso("2026-08-01T10:00:00+00:00"))
        self.assertEqual(b, pm._parse_iso("2026-08-01T13:00:00+00:00"),
                         "last close, so fix iterations are included")

    def _mrec(self, mid, model, out=0, inp=0, cr=0):
        r = self._rec(mid, "2026-08-01T12:00:00.000Z", out=out)
        r["message"]["model"] = model
        r["message"]["usage"]["input_tokens"] = inp
        r["message"]["usage"]["cache_read_input_tokens"] = cr
        return r

    def test_mixed_model_run_priced_per_model(self):
        """A parent on Opus 5.5 dispatching a Sonnet 5.5 agent: each model's tokens are
        priced at its own rates, and the total differs from pricing all of it at Opus."""
        parent = self._write("S1.jsonl", [self._mrec("p", "claude-opus-5-5", out=1_000_000)])
        sub = self._write("S1/subagents/agent-a.jsonl",
                          [self._mrec("s", "claude-sonnet-5-5", out=1_000_000)])
        res = pm.read_transcript_usage([parent, sub])
        self.assertEqual(res["by_model"]["claude-opus-5-5"]["output"], 1_000_000)
        self.assertEqual(res["by_model"]["claude-sonnet-5-5"]["output"], 1_000_000)
        _lines, cost = pm.metrics.actuals_usage.price_by_model(res["by_model"], "claude-opus-5-5")
        self.assertEqual(cost, 30.00, "1M output at $20 (Opus 5.5) + 1M at $10 (Sonnet 5.5)")
        all_opus = pm.metrics.rates.cost_from_tokens(
            {c: v / 1000.0 for c, v in res["tokens"].items()}, "claude-opus-5-5")
        self.assertEqual(all_opus, 40.00)
        self.assertNotEqual(cost, all_opus)

    def test_unknown_or_absent_model_falls_back_to_the_given_model_and_says_so(self):
        p = self._write("t.jsonl", [self._mrec("a", "claude-unknown-9", out=1_000_000),
                                    self._rec("b", "2026-08-01T12:00:00.000Z", out=1_000_000)])
        res = pm.read_transcript_usage(p)
        lines, cost = pm.metrics.actuals_usage.price_by_model(res["by_model"], "claude-sonnet-5-5")
        self.assertEqual(cost, 20.00)
        text = "\n".join(lines)
        self.assertIn("no rate for 'claude-unknown-9'; priced at --model claude-sonnet-5-5", text)
        self.assertIn("no model recorded; priced at --model claude-sonnet-5-5", text)

    def test_tokenless_synthetic_records_are_not_priced_or_listed(self):
        p = self._write("t.jsonl", [self._mrec("a", "<synthetic>"),
                                    self._mrec("b", "claude-opus-5-5", out=1000)])
        lines, _ = pm.metrics.actuals_usage.price_by_model(
            pm.read_transcript_usage(p)["by_model"], "claude-opus-5-5")
        self.assertEqual(len(lines), 1)
        self.assertNotIn("synthetic", lines[0])

    def test_cli_prices_per_model_and_emits_a_split_for_set_actual(self):
        """The CLI's cost line is the per-model sum, and a mixed window's set-actual flag is
        the per-model split rather than --tokens-* priced at one model."""
        p = self._write("t.jsonl", [self._mrec("p", "claude-opus-5-5", out=1_000_000),
                                    self._mrec("s", "claude-sonnet-5-5", out=1_000_000)])
        code, out = self.run_main(["usage", p, "--allow-unidentified", "--model",
                                   "claude-opus-5-5", "--since", "2026-08-01T11:00:00Z",
                                   "--until", "2026-08-01T13:00:00Z"])
        self.assertEqual(code, 0, out)
        self.assertIn("cost 30.00 USD, each model at its own rates", out)
        self.assertIn("ran on more than one model", out)
        flag = re.search(r"--tokens-by-model '([^']+)'", out)
        self.assertIsNotNone(flag, out)
        self.assertEqual(json.loads(flag.group(1)), {
            "claude-opus-5-5": {"input": 0.0, "output": 1000.0, "cache_write": 0.0, "cache_read": 0.0},
            "claude-sonnet-5-5": {"input": 0.0, "output": 1000.0, "cache_write": 0.0, "cache_read": 0.0}})
        self.assertNotIn("--tokens-input", out)

    def test_new_model_rates_match_the_published_table(self):
        """Read from the pricing page 2026-11-16. Cache reads are 0.05x input on Opus and
        Sonnet 5.5 and 0.025x on Fable 5.2 -- not the 0.1x the older rows follow."""
        r = pm.metrics.rates.TOKEN_RATES
        self.assertEqual(r["claude-opus-5-5"], {"input": 4.00, "output": 20.00,
                                                "cache_write": 5.00, "cache_read": 0.20})
        self.assertEqual(r["claude-sonnet-5-5"], {"input": 2.00, "output": 10.00,
                                                  "cache_write": 2.50, "cache_read": 0.10})
        self.assertEqual(r["claude-fable-5-2"], {"input": 8.00, "output": 40.00,
                                                 "cache_write": 10.00, "cache_read": 0.20})
        self.assertEqual(r["claude-sonnet-5"], {"input": 2.00, "output": 10.00,
                                                "cache_write": 2.50, "cache_read": 0.20})

    def test_dispatch_window_naive_ts_is_refused_not_typeerror(self):
        """A ts with no offset beside aware ones raised TypeError comparing them. It now
        voids the bracket with a warning naming the record -- never a silently narrowed
        window built from the records that happen to remain."""
        root = os.path.join(self.d, "state")
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, "events.jsonl"), "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps({"ts": ts, "event": ev, "story": "S"}) + "\n"
                          for ev, ts in [("dispatch_open", "2026-08-01T10:00:00+00:00"),
                                         ("dispatch_open", "2026-08-01T09:00:00"),
                                         ("dispatch_close", "2026-08-01T13:00:00+00:00")])
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            got = pm.metrics.actuals_usage.dispatch_window(root, story="S")
        self.assertEqual(got, (None, None))
        self.assertIn("'2026-08-01T09:00:00' has no UTC offset", err.getvalue())

    def test_windowed_read_counts_a_naive_record_as_undated(self):
        """Same rule on the transcript side of usage: a naive record inside an aware window
        is undatable, counted as such, and never raises."""
        p = self._write("t.jsonl", [
            self._rec("a", "2026-08-01T12:00:00", out=1000),
            self._rec("b", "2026-08-01T12:00:00.000Z", out=7)])
        res = pm.read_transcript_usage(
            p, since=pm._parse_iso("2026-08-01T11:00:00.000Z"),
            until=pm._parse_iso("2026-08-01T13:00:00.000Z"))
        self.assertEqual(res["tokens"]["output"], 7)
        self.assertEqual(res["undated_skipped"], 1)

    def test_dispatch_window_ignores_other_nodes(self):
        root = os.path.join(self.d, "state")
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, "events.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": "2026-08-01T10:00:00+00:00", "event": "dispatch_open",
                                 "agent": "x", "story": "OTHER"}) + "\n")
        self.assertEqual(pm.metrics.actuals_usage.dispatch_window(root, story="MINE"), (None, None))

    def test_cli_refuses_a_node_with_no_dispatch_bracket(self):
        root = os.path.join(self.d, "state")
        os.makedirs(root, exist_ok=True)
        open(os.path.join(root, "events.jsonl"), "w").close()
        p = self._write("t.jsonl", [self._rec("m", "2026-08-01T10:00:00.000Z")])
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["usage", p, "--claude-session", "S1",
                                     "--story", "E001-S01-001", "--state-root", root])
        self.assertEqual(code, 2)
        self.assertIn("no dispatch bracket", buf.getvalue())

    def test_cli_withholds_set_actual_flags_when_unscoped(self):
        """The pasteable flags are what gets misused, so they are not offered unscoped."""
        p = self._write("t.jsonl", [self._rec("m", "2026-08-01T10:00:00.000Z")])
        code, out = self.run_main(["usage", p, "--claude-session", "S1"])
        self.assertEqual(code, 0, out)
        self.assertIn("UNSCOPED", out)
        self.assertIn("withheld", out)
        self.assertNotIn("--tokens-input", out)

    def test_cli_emits_flags_once_scoped(self):
        p = self._write("t.jsonl", [self._rec("m", "2026-08-01T12:00:00.000Z", out=42)])
        code, out = self.run_main(["usage", p, "--claude-session", "S1",
                                   "--since", "2026-08-01T11:00:00.000Z",
                                   "--until", "2026-08-01T13:00:00.000Z"])
        self.assertEqual(code, 0, out)
        self.assertIn("--tokens-output 0.042", out)
        self.assertNotIn("UNSCOPED", out)

    def test_resolver_includes_the_subagents_directory(self):
        """Subagent turns are not in the parent file — sidechain=0 was the symptom."""
        root = os.path.join(self.d, "projects")
        proj = os.path.join(root, "-some-project")
        subs = os.path.join(proj, "SESS", "subagents")
        os.makedirs(subs)
        open(os.path.join(proj, "SESS.jsonl"), "w").close()
        open(os.path.join(subs, "agent-aaa.jsonl"), "w").close()
        open(os.path.join(subs, "agent-bbb.jsonl"), "w").close()
        real = os.path.expanduser
        try:
            os.path.expanduser = lambda p: root if p == "~/.claude/projects" else real(p)
            paths, sid = pm.resolve_session_transcript("SESS")
        finally:
            os.path.expanduser = real
        self.assertEqual(sid, "SESS")
        self.assertEqual(len(paths), 3, paths)
        self.assertEqual(sum(1 for p in paths if "subagents" in p), 2)


class TestFixIterationsTyping(Base):
    """fix_iterations stored as text broke the scope-versus-fix split silently.

    A 3.x field write took the value as text and wrote it verbatim, so the field landed quoted.
    The provenance test then depended on that text parsing as an int: '0' happened to
    work, '0.0' raised ValueError and lost the whole sample, and any non-numeric text --
    an unsubstituted placeholder, an empty string -- read as provenance=backout on a
    story that needed no rework. That divides the scope ratio by a 1.25 fix factor it
    never incurred, and leaves the `clean` cohort empty so `fix` can never activate.
    """

    def test_iter_count_accepts_every_shape_that_means_zero(self):
        for v in (0, "0", 0.0, "0.0", "00", " 0 "):
            self.assertEqual(pm._iter_count(v), 0, f"{v!r} means zero iterations")

    def test_iter_count_rejects_what_is_not_a_count(self):
        for v in ("{fix_iterations}", "", None, "none", -1, 1.5, True):
            self.assertIsNone(pm._iter_count(v), f"{v!r} is not an iteration count")

    def test_float_string_no_longer_loses_the_sample(self):
        """'0.0' raised ValueError inside derive_story_sample and aborted it entirely."""
        node = {"classification": "standard",
                "estimate": {"fix_factor": 1.25, "scope_ratios": {"man_hours": 1.0},
                             "man_hours": 8.75},
                "actual": {"man_hours": 9.0},
                "completion_evidence": {"fix_iterations": "0.0"}}
        sample = pm.derive_story_sample(node)
        self.assertEqual(sample["provenance"], "exact")
        self.assertEqual(sample["fix_iterations"], 0)


    # test_set_field_stores_tests_passing_as_a_bool removed: Task 4 makes
    # completion_evidence.tests_passing derived-only. See TestTestRunEvidence
    # below for the replacement.


class TestTestRunEvidence(TestLayoutResolution):
    # TestLayoutResolution supplies the node tree but not run_main -- every class
    # extending it defines its own (see TestSetFieldTyping above). Same three lines:
    def run_main(self, argv):
        buf = io.StringIO()
        code = 0
        try:
            with redirect_stdout(buf):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, buf.getvalue()

    def test_a_recorded_run_appends_and_derives_the_boolean(self):
        self.run_main(["add-test-run", "--state-root", self.root, "--story", "E001-S01-003",
                       "--command", "npm test", "--exit-code", "0"])
        _, node = self.load_node(self.story_file("E001-S01-003"))
        runs = node["completion_evidence"]["test_runs"]
        self.assertEqual(runs[0]["command"], "npm test")
        self.assertEqual(runs[0]["exit_code"], 0)
        self.assertIs(node["completion_evidence"]["tests_passing"], True)

    def test_one_failing_run_makes_the_derived_boolean_false(self):
        for cmd, rc in (("npm test", "0"), ("pytest", "1")):
            self.run_main(["add-test-run", "--state-root", self.root, "--story", "E001-S01-003",
                           "--command", cmd, "--exit-code", rc])
        _, node = self.load_node(self.story_file("E001-S01-003"))
        self.assertIs(node["completion_evidence"]["tests_passing"], False)

    def test_a_malformed_stored_exit_code_fails_rather_than_crashes(self):
        """test_runs is hand-editable YAML; a non-numeric exit_code must derive False,
        never raise and never derive True."""
        path = self.story_file("E001-S01-003")
        y, node = self.load_node(path)
        ce = node.setdefault("completion_evidence", {})
        ce["test_runs"] = [{"command": "old flaky run", "exit_code": "flaky"}]
        self.save_node(y, node, path)

        code, out = self.run_main(["add-test-run", "--state-root", self.root,
                                   "--story", "E001-S01-003",
                                   "--command", "npm test", "--exit-code", "0"])
        self.assertEqual(code, 0, out)
        _, node = self.load_node(path)
        self.assertIs(node["completion_evidence"]["tests_passing"], False)

    def test_no_recorded_runs_leaves_tests_passing_absent(self):
        """The exact regression all(()) == True would reintroduce: a story that never
        called add-test-run must never read as tests_passing: true."""
        _, node = self.load_node(self.story_file("E001-S01-003"))
        ce = node.get("completion_evidence") or {}
        self.assertNotIn("tests_passing", ce)

    def test_a_rerun_of_the_same_command_supersedes_its_earlier_failure(self):
        """The normal fix-then-rerun cycle the step file asks for: pytest -> 1, fix,
        pytest -> 0. The derived boolean reads the LAST run of each distinct command,
        so this closes True -- and BOTH entries stay in test_runs, because the failed
        run is the evidence that made the field falsifiable."""
        for rc in ("1", "0"):
            self.run_main(["add-test-run", "--state-root", self.root,
                           "--story", "E001-S01-003",
                           "--command", "pytest", "--exit-code", rc])
        _, node = self.load_node(self.story_file("E001-S01-003"))
        ce = node["completion_evidence"]
        self.assertIs(ce["tests_passing"], True)
        self.assertEqual([(r["command"], r["exit_code"]) for r in ce["test_runs"]],
                         [("pytest", 1), ("pytest", 0)])

    def test_a_different_command_still_failing_derives_false(self):
        """Last-run-wins is per command, not global: re-running one suite green never
        speaks for a different suite whose latest run is red."""
        for cmd, rc in (("pytest", "1"), ("pytest", "0"), ("npm test", "1")):
            self.run_main(["add-test-run", "--state-root", self.root,
                           "--story", "E001-S01-003",
                           "--command", cmd, "--exit-code", rc])
        _, node = self.load_node(self.story_file("E001-S01-003"))
        ce = node["completion_evidence"]
        self.assertIs(ce["tests_passing"], False)
        self.assertEqual(len(ce["test_runs"]), 3)

    def test_negative_exit_code_is_refused(self):
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["add-test-run", "--state-root", self.root,
                                     "--story", "E001-S01-003",
                                     "--command", "npm test", "--exit-code", "-1"])
        self.assertEqual(code, 2)


class TestAdrRegister(TestLayoutResolution):
    # TestLayoutResolution supplies a project and its state root but NOT run_main.
    def run_main(self, argv):
        buf, err = io.StringIO(), io.StringIO()
        code = 0
        if argv and argv[0] == "adr-reserve" and "--adr-dir" not in argv:
            argv = [*argv, "--adr-dir", os.path.join(self.project, "no-adr-dir")]
        try:
            with redirect_stdout(buf), redirect_stderr(err):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        self.last_err = err.getvalue()
        return code, buf.getvalue()

    def test_numbers_are_unique_across_repeated_reservations(self):
        seen = []
        for slug in ("a", "b", "c"):
            code, out = self.run_main(["adr-reserve", "--state-root", self.root,
                                  "--epic", "E001", "--slug", slug])
            self.assertEqual(code, 0)
            seen.extend(out.split())
        self.assertEqual(len(set(seen)), 3, f"collision in {seen}")
        self.assertEqual(seen, ["0001", "0002", "0003"])

    def test_a_batch_reserves_a_contiguous_range(self):
        _, out = self.run_main(["adr-reserve", "--state-root", self.root, "--epic", "E001",
                           "--slug", "batch", "--count", "3"])
        self.assertEqual(out.split(), ["0001", "0002", "0003"])

    def test_in_flight_reservations_are_visible_before_any_file_exists(self):
        """A directory listing shows who FINISHED. Only a register knows who is in flight."""
        self.run_main(["adr-reserve", "--state-root", self.root, "--epic", "E001", "--slug", "x"])
        _, cal = pm.load_adr_register(self.root)
        self.assertEqual(cal["reserved"][0]["number"], 1)
        self.assertEqual(cal["reserved"][0]["slug"], "x")

    def test_malformed_reserved_field_is_refused_not_silently_repaired(self):
        """Unlike a malformed `next` (recoverable), a malformed `reserved` must
        refuse loudly: silently replacing it with [] would hide who is already
        in flight, which is the one thing this register exists to preserve."""
        with open(pm.adr_register_path(self.root), "w") as f:
            f.write("next: 1\nreserved: not-a-list\n")
        code, out = self.run_main(["adr-reserve", "--state-root", self.root,
                                   "--epic", "E001", "--slug", "x"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        err = self.last_err
        self.assertIn("reserved", err)
        self.assertIn("malformed", err)


class TestRuntimeChoices(TestLayoutResolution):
    """T-RC: runtime argparse choices include codex and copilot."""

    def run_main(self, argv):
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code
        return code, out_buf.getvalue() + err_buf.getvalue()

    def test_codex_is_a_valid_runtime_choice(self):
        # set-actual with --runtime codex but no tokens — should fail for a
        # different reason than "invalid choice", proving codex is accepted
        code, out = self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "codex",
            "--elapsed-hours", "1.0", "--man-hours", "4.0", "--hitl-hours", "0.2",
            "--no-calibrate",
        ])
        # exit 0 or 2 (usage error about tokens), never 2 with "invalid choice"
        self.assertNotIn("invalid choice", out)

    def test_copilot_is_a_valid_runtime_choice(self):
        code, out = self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "copilot",
            "--elapsed-hours", "1.0", "--man-hours", "4.0", "--hitl-hours", "0.2",
            "--no-calibrate",
        ])
        self.assertNotIn("invalid choice", out)

    def test_invalid_runtime_rejected(self):
        code, out = self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "github-copilot",
            "--elapsed-hours", "1.0",
        ])
        self.assertEqual(code, 2)
        self.assertIn("invalid choice", out)

    def test_codex_is_valid_runtime_choice_for_verify(self):
        code, out = self.run_main([
            "verify", "--state-root", self.root, "--scope", "story",
            "--story", "E001-S01-003", "--runtime", "codex",
        ])
        self.assertNotIn("invalid choice", out)

    def test_copilot_is_valid_runtime_choice_for_verify(self):
        code, out = self.run_main([
            "verify", "--state-root", self.root, "--scope", "story",
            "--story", "E001-S01-003", "--runtime", "copilot",
        ])
        self.assertNotIn("invalid choice", out)

    def test_openai_models_in_token_rates(self):
        for model in ("codex-1", "gpt-5", "gpt-5.4",
                      "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
            self.assertIn(model, pm.TOKEN_RATES, f"{model} missing from TOKEN_RATES")
            self.assertEqual(
                set(pm.TOKEN_RATES[model].keys()), set(pm.TOKEN_CLASSES),
                f"{model} missing a TOKEN_CLASSES key"
            )


class TestModelMismatch(TestLayoutResolution):
    """T-MM: model mismatch annotation in calibration show. (The set-actual and verify notes
    compared a 3.x node's estimate with its actual; a v7 ticket keeps them in two sidecars.)"""

    def run_main(self, argv):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code
        return code, out_buf.getvalue() + err_buf.getvalue()

    def test_calibration_show_warns_on_mixed_models(self):
        from ruamel.yaml import YAML as _YAML
        cal_path = os.path.join(self.root, "pm-calibration.yaml")
        cal = {
            "version": 2,
            "granularity": "story",
            "scope": {
                "standard": {
                    "elapsed_hours": {
                        "samples": [0.9, 1.1],
                        "models_seen": ["claude-opus-5", "gpt-5.6-terra"],
                    }
                }
            },
            "closure": {}, "orchestration": {}, "fix": {},
        }
        _yaml = _YAML()
        with open(cal_path, "w") as f:
            _yaml.dump(cal, f)
        code, out = self.run_main(["calibration", "--state-root", self.root, "show"])
        self.assertEqual(code, 0)
        self.assertIn("WARN", out)
        self.assertIn("mixed-model", out)


class TestCodexRuntime(TestLayoutResolution):
    """T-CX: --runtime codex enforcement in set-actual and verify."""

    def run_main(self, argv):
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code
        return code, out_buf.getvalue() + err_buf.getvalue()

    def _set(self, *extra):
        return self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "codex", "--no-calibrate",
            "--elapsed-hours", "2.0", "--man-hours", "8.0", "--hitl-hours", "0.5",
        ] + list(extra))

    def _verify(self, *extra):
        return self.run_main([
            "verify", "--state-root", self.root, "--scope", "story",
            "--story", "E001-S01-003", "--runtime", "codex",
        ] + list(extra))

    def test_tokens_na_forbidden_under_codex(self):
        code, out = self._set("--tokens-na")
        self.assertEqual(code, 2)
        self.assertIn("codex", out)

    def test_codex_requires_input_output_cache_read(self):
        # missing --tokens-cache-read
        code, out = self._set(
            "--tokens-input", "100", "--tokens-output", "20", "--model", "codex-1",
        )
        self.assertEqual(code, 2)
        self.assertIn("cache-read", out)

    def test_codex_cache_write_defaults_to_zero(self):
        # omitting --tokens-cache-write should succeed; cache_write stored as 0
        code, out = self._set(
            "--tokens-input", "100", "--tokens-output", "20",
            "--tokens-cache-read", "300", "--model", "codex-1",
        )
        self.assertEqual(code, 0, out)
        _, node = self.load_node(self.story_file("E001-S01-003"))
        tk = node["actual"]["tokens_k"]
        self.assertEqual(int(tk["cache_write"]), 0)
        self.assertEqual(int(tk["total"]), 420)  # 100+20+0+300

    def test_codex_derives_cost_from_three_classes(self):
        code, out = self._set(
            "--tokens-input", "100", "--tokens-output", "20",
            "--tokens-cache-read", "300", "--model", "codex-1",
        )
        self.assertEqual(code, 0, out)
        _, node = self.load_node(self.story_file("E001-S01-003"))
        # cost = (100*5 + 20*30 + 0*6.25 + 300*2.5) / 1000 = (500+600+0+750)/1000 = 1.85
        self.assertAlmostEqual(float(node["actual"]["cost"]), 1.85, places=2)

    def test_verify_fails_on_scalar_tokens_under_codex(self):
        # Write a node with scalar tokens_k (like TestVerifyRejectsScalarTokens does),
        # then verify under codex — scalar form must fail for codex just as for claude.
        f = self.story_file("E001-S01-003")
        y, node = self.load_node(f)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {
            "elapsed_hours": 2.0, "man_hours": 8.0, "hitl_hours": 0.5,
            "tokens_k": 420, "cost": "N/A", "model": "codex-1",
        }
        self.save_node(y, node, f)
        code, out = self._verify()
        self.assertEqual(code, 4)
        self.assertIn("not the per-class mapping", out)

    def test_verify_na_tokens_fails_under_codex(self):
        # Write tokens_k=N/A to a done node, then verify — N/A is forbidden under codex.
        f = self.story_file("E001-S01-003")
        y, node = self.load_node(f)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {
            "elapsed_hours": 2.0, "man_hours": 8.0, "hitl_hours": 0.5,
            "tokens_k": "N/A", "cost": "N/A", "model": "codex-1",
        }
        self.save_node(y, node, f)
        code, out = self._verify()
        self.assertEqual(code, 4)
        self.assertIn("N/A", out)


class TestCopilotRuntime(TestLayoutResolution):
    """T-CP: --runtime copilot enforcement in set-actual and verify."""

    def run_main(self, argv):
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                code = pm.main(self._v7(argv))
        except SystemExit as e:
            code = e.code
        return code, out_buf.getvalue() + err_buf.getvalue()

    def _set(self, *extra):
        return self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "copilot", "--no-calibrate",
            "--elapsed-hours", "2.0", "--man-hours", "8.0", "--hitl-hours", "0.5",
        ] + list(extra))

    def _verify(self):
        return self.run_main([
            "verify", "--state-root", self.root, "--scope", "story",
            "--story", "E001-S01-003", "--runtime", "copilot",
        ])

    def test_tokens_na_forbidden_under_copilot(self):
        code, out = self._set("--tokens-na")
        self.assertEqual(code, 2)
        self.assertIn("copilot", out)

    def test_copilot_requires_input_and_output(self):
        # only input, no output
        code, out = self._set("--tokens-input", "150")
        self.assertEqual(code, 2)
        self.assertIn("--tokens-output", out)

    def test_copilot_stores_scalar_total(self):
        code, out = self._set("--tokens-input", "150", "--tokens-output", "50")
        self.assertEqual(code, 0, out)
        _, node = self.load_node(self.story_file("E001-S01-003"))
        tk = node["actual"]["tokens_k"]
        # scalar, not a mapping
        self.assertFalse(hasattr(tk, "get"), f"expected scalar, got mapping: {tk}")
        self.assertEqual(int(tk), 200)  # 150 + 50

    def test_copilot_stores_cost_na(self):
        code, out = self._set("--tokens-input", "150", "--tokens-output", "50")
        self.assertEqual(code, 0, out)
        _, node = self.load_node(self.story_file("E001-S01-003"))
        self.assertTrue(pm._is_na(node["actual"]["cost"]))

    def test_copilot_model_not_required(self):
        # no --model; should succeed (cost=N/A means no pricing needed)
        code, out = self._set("--tokens-input", "150", "--tokens-output", "50")
        self.assertEqual(code, 0, out)

    def test_verify_passes_with_scalar_tokens_and_na_cost_under_copilot(self):
        # Write a complete done node with scalar tokens_k and cost=N/A, then verify
        f = self.story_file("E001-S01-003")
        y, n = self.load_node(f)
        n.setdefault("actual", {})
        n["actual"].update({
            "elapsed_hours": 2.0, "man_hours": 8.0, "hitl_hours": 0.5,
            "tokens_k": 200, "cost": "N/A",
        })
        n["status"] = "done"
        n.setdefault("completion_evidence", {})
        self.save_node(y, n, f)
        code, out = self._verify()
        self.assertEqual(code, 0, out)

    def test_verify_rejects_na_tokens_k_under_copilot(self):
        f = self.story_file("E001-S01-003")
        y, n = self.load_node(f)
        n.setdefault("actual", {})
        n["actual"].update({
            "elapsed_hours": 2.0, "man_hours": 8.0, "hitl_hours": 0.5,
            "tokens_k": "N/A", "cost": "N/A",
        })
        n["status"] = "done"
        n.setdefault("completion_evidence", {})
        self.save_node(y, n, f)
        code, _ = self._verify()
        self.assertEqual(code, 4)


class TestEstimateCores(unittest.TestCase):
    """The estimate engine's two cores, which `estimate-entries` calls: they never save and
    never exit, and a failure leaves the node it was given as it was."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_compute_story_estimate_raises_instead_of_exiting(self):
        node = {}
        with self.assertRaises(pm.PMError) as cm:
            pm.metrics.estimates.compute_story_estimate(self.root, node, "standard",
                                                        "no-such-model", None)
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(node, {}, "core must never half-write")

    def test_compute_story_estimate_fills_node_in_memory(self):
        node = {}
        applied = pm.metrics.estimates.compute_story_estimate(
            self.root, node, "simple", pm.DEFAULT_ESTIMATE_MODEL, None)
        self.assertIn("man_hours", applied)
        self.assertIn("cost", node["estimate"])
        self.assertEqual(node["classification"], "simple")
        self.assertEqual(os.listdir(self.root), [], "core must never save")

    def test_rollup_values_raises_when_nothing_to_roll_up(self):
        _, cal = pm.load_calibration(self.root)
        with self.assertRaises(pm.PMError) as cm:
            pm.metrics.estimates.rollup_values(cal, "epic", [{"estimate": {}}],
                                               pm.DEFAULT_ESTIMATE_MODEL, None)
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(cm.exception.msg, pm.metrics.estimates.NO_CHILD_ESTIMATES)

    def test_rollup_values_raises_for_an_unknown_model(self):
        _, cal = pm.load_calibration(self.root)
        with self.assertRaises(pm.PMError) as cm:
            pm.metrics.estimates.rollup_values(cal, "epic",
                                               [{"estimate": {"man_hours": 4, "tokens_k": 10}}],
                                               "no-such-model", None)
        self.assertEqual(cm.exception.code, 2)

    def test_compute_story_estimate_leaves_node_untouched_when_it_raises(self):
        node = {}
        pm.metrics.estimates.compute_story_estimate(self.root, node, "simple",
                                                    pm.DEFAULT_ESTIMATE_MODEL, None)
        before_est = json.dumps(node["estimate"], sort_keys=True, default=str)
        before_cls = node["classification"]
        with self.assertRaises(pm.PMError):
            pm.metrics.estimates.compute_story_estimate(self.root, node, "complex",
                                                        "no-such-model", None)
        self.assertEqual(json.dumps(node["estimate"], sort_keys=True, default=str), before_est,
                         "a failed estimate must not half-overwrite the previous one")
        self.assertEqual(node["classification"], before_cls)


class TestEventReadersTolerateMalformedFields(Base):
    """Every reader over `events.jsonl` documents itself as tolerating a torn line. Each
    one proves that at the RECORD level -- `json.loads` in a try, then
    `isinstance(rec, dict)` -- and the guard stops there. None of them looked inside the
    record, so a well-formed object with one malformed FIELD went straight through.

    That is not hypothetical. `_dispatch_identity` built a dict key from
    `rec["sprint"]`, and a record whose `sprint` held a list raised
    `TypeError: unhashable type` out of `pending[...]` -- crashing `report --watch`, the
    exact surface the docstring promises to protect. The record-level test existed and
    passed (`test_bare_scalar_line_does_not_crash_open_dispatches`), which is what made
    the area look covered: a guard was proven, its reach was not (CLAUDE.md §4).

    So the scope here is the READER SET, not one reader, and the planted violation
    attacks the field rather than the record. The field names are the ones each reader
    actually keys or compares on, read off the code -- `key` for the status and actuals
    indexes, `story` for the blocked-hours scan, the four node keys for dispatch.
    """

    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)

    def write(self, *recs):
        with open(pm.events_path(self.root), "w", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r) + "\n")

    # A list and a dict are the two unhashable JSON types; a nested object is what a
    # hand-edit or a half-flushed write most plausibly produces.
    BAD = ([1, 2], {"a": 1})

    def test_pending_dispatches_survives_unhashable_node_keys(self):
        """Fixed when the read-side canonicalisation landed; kept here so the whole
        reader set is covered in one place rather than one test per incident."""
        for field in ("agent", "epic", "sprint", "story"):
            for bad in self.BAD:
                with self.subTest(field=field, bad=bad):
                    rec = {"ts": "2026-01-01T00:00:00+00:00", "event": "dispatch_open",
                           "agent": "a", "epic": "E001", "sprint": "S01",
                           "story": "E001-S01-001"}
                    rec[field] = bad
                    self.write(rec)
                    self.assertEqual(len(pm.open_dispatches(self.root, 0)), 1)

    def test_total_blocked_hours_survives_an_unhashable_story(self):
        """Documented to return 0.0 rather than fail the calibration write path it
        feeds, so a malformed field must not raise either."""
        for bad in self.BAD:
            with self.subTest(bad=bad):
                self.write({"ts": "2026-01-01T00:00:00+00:00", "event": "block_close",
                            "story": bad, "duration_hours": 1.0},
                           {"ts": "2026-01-02T00:00:00+00:00", "event": "block_close",
                            "story": "E001-S01-001", "duration_hours": 2.0})
                self.assertIsInstance(
                    pm._total_blocked_hours(self.root, "E001-S01-001"), float)

    def test_an_index_drops_a_bad_key_while_a_dispatch_carries_it(self):
        """The asymmetry is deliberate and easy to "tidy" into a bug, so it is pinned.

        An index is looked up BY a real node key, so a value no node could have is not a
        key -- carrying it would add a phantom entry for nothing. A dispatch identity
        only needs an open and its close to hash alike, so carrying a malformed field
        through under its repr keeps that dispatch closeable, and DROPPING it would
        recreate the permanently-stalled state the read-side canonicalisation fixed.
        """
        self.assertIsNone(pm._indexable_key(["x"]))
        self.assertIsNone(pm._indexable_key({"x": 1}))
        self.assertIsNone(pm._indexable_key("   "))
        self.assertEqual(pm._indexable_key("  E001-S01-001 "), "E001-S01-001")
        # carried, not dropped: a str() repr is stable, so open and close still match
        self.assertEqual(pm._hashable_field(["x"]), pm._hashable_field(["x"]))
        self.assertIsNotNone(pm._hashable_field(["x"]))

        self.write({"ts": "2026-01-01T00:00:00+00:00", "event": "dispatch_open",
                    "agent": "a", "epic": ["bad"], "story": "E001-S01-009"})
        self.assertEqual(len(pm.open_dispatches(self.root, 0)), 1)
        self.write({"ts": "2026-01-01T00:00:00+00:00", "event": "dispatch_open",
                    "agent": "a", "epic": ["bad"], "story": "E001-S01-009"},
                   {"ts": "2026-01-01T00:01:00+00:00", "event": "dispatch_close",
                    "agent": "a", "epic": ["bad"], "story": "E001-S01-009"})
        self.assertEqual(pm.open_dispatches(self.root, 0), [])


class TestLockFilesIgnored(StateTreeBase):
    """Lock files, and the notices ledger, must never be committed. Every lock acquisition
    inside a state root ensures {state_root}/.gitignore carries BOTH `*.lock` and
    `.notices.yaml` -- on every
    acquisition, not only when a pattern's file is first created, so a project whose lock
    files already exist is covered on its next lock. Best-effort: a failure warns on stderr
    and never fails the verb."""

    def setUp(self):
        super().setUp()
        # Memoized per process: reset so each test sees a fresh process's behavior.
        pm._LOCK_IGNORE_CHECKED.clear()
        self.addCleanup(pm._LOCK_IGNORE_CHECKED.clear)
        self.gi = os.path.join(self.root, ".gitignore")

    def gi_bytes(self):
        with open(self.gi, "rb") as fh:
            return fh.read()

    def gi_lines(self):
        return self.gi_bytes().decode("utf-8").splitlines()

    def append(self, title, root=None):
        """One locked write under the state root: `adr-reserve` holds the register's lock."""
        adr_dir = os.path.join(self.d, "adr")
        os.makedirs(adr_dir, exist_ok=True)
        return self.run_all(["adr-reserve", "--state-root", root or self.root, "--epic", "E001",
                             "--slug", title.lower(), "--adr-dir", adr_dir])

    @property
    def lock(self):
        return pm.adr_register_path(self.root) + ".lock"

    def test_first_lock_creates_gitignore(self):
        code, _, err = self.append("A")
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.exists(self.lock), "premise: a lock was taken")
        lines = self.gi_lines()
        self.assertIn("*.lock", lines)
        self.assertIn(".notices.yaml", lines)

    def test_second_lock_leaves_bytes_unchanged(self):
        self.append("A")
        before = self.gi_bytes()
        pm._LOCK_IGNORE_CHECKED.clear()          # as a second process would see it
        self.append("B")
        self.assertEqual(self.gi_bytes(), before)

    def test_existing_gitignore_is_appended_once_never_rewritten(self):
        with open(self.gi, "wb") as fh:
            fh.write(b"# team rules\nscratch/\n*.tmp")       # no trailing newline
        self.append("A")
        self.assertEqual(self.gi_bytes(),
                         b"# team rules\nscratch/\n*.tmp\n*.lock\n.notices.yaml\n")
        pm._LOCK_IGNORE_CHECKED.clear()
        self.append("B")
        self.assertEqual(self.gi_bytes(),
                         b"# team rules\nscratch/\n*.tmp\n*.lock\n.notices.yaml\n")

    def test_existing_gitignore_with_both_lines_is_untouched(self):
        original = b"*.lock\n.notices.yaml\n# local\nnotes/\n"
        with open(self.gi, "wb") as fh:
            fh.write(original)
        self.append("A")
        self.assertEqual(self.gi_bytes(), original)

    def test_existing_gitignore_missing_one_pattern_gets_only_that_one_appended(self):
        """A consumer already on an older pm-status.py has `*.lock` alone. Upgrading must
        add the newly-required `.notices.yaml` without touching the line already there."""
        original = b"*.lock\n# local\nnotes/\n"
        with open(self.gi, "wb") as fh:
            fh.write(original)
        self.append("A")
        self.assertEqual(self.gi_bytes(), b"*.lock\n# local\nnotes/\n.notices.yaml\n")

    def test_unwritable_target_warns_and_the_verb_still_succeeds(self):
        os.mkdir(self.gi)                         # a directory where the file should be
        code, _, err = self.append("A")
        self.assertEqual(code, 0, err)
        self.assertIn(
            f"pm-status.py: warning -- could not add *.lock, .notices.yaml to {self.gi}: ",
            err)
        self.assertEqual(err.count("could not add"), 1, err)
        self.assertTrue(os.path.exists(pm.adr_register_path(self.root)),
                        "the verb's state must be written")

    def test_undecodable_gitignore_warns_and_is_left_alone(self):
        original = b"\xff\xfe not utf-8\n"
        with open(self.gi, "wb") as fh:
            fh.write(original)
        code, _, err = self.append("A")
        self.assertEqual(code, 0, err)
        self.assertIn(
            f"pm-status.py: warning -- could not add *.lock, .notices.yaml to {self.gi}: ",
            err)
        self.assertEqual(self.gi_bytes(), original)
        self.assertTrue(os.path.exists(pm.adr_register_path(self.root)))

    def test_read_only_commands_create_nothing(self):
        for argv in (["calibration", "show", "--state-root", self.root, "--format", "json"],):
            code, _, err = self.run_all(argv)
            self.assertEqual(code, 0, err)
        self.assertFalse(os.path.exists(self.gi), "a read-only command created .gitignore")
        self.assertFalse(os.path.exists(self.lock))

    # -- "rule present" must mean what git means ---------------------------------------- #
    # git splits .gitignore on "\n" only, keeps leading spaces, drops trailing spaces (and a
    # trailing "\r"), and lets a later `!*.lock` undo the rule. Each case goes through a verb.
    #
    # `before`/`after` below describe the *.lock-only expectation, as they did before
    # `.notices.yaml` existed. By default this helper pre-satisfies `.notices.yaml` in
    # `before` (appending it, and to `after` at the same offset) so each case keeps
    # exercising *.lock's parsing in isolation; the two-pattern append itself is covered
    # separately below (test_both_patterns_appended_together_from_scratch etc). Every
    # caller here only ever appends at the very end, so `after` always starts with `before`.
    def assert_after_lock(self, before, after, notices_presatisfied=True):
        assert after.startswith(before), "callers must only append, never rewrite, `before`"
        delta = after[len(before):]
        if notices_presatisfied:
            before = before + b".notices.yaml\n"
            after = before + delta
        with open(self.gi, "wb") as fh:
            fh.write(before)
        code, _, err = self.append("A")
        self.assertEqual(code, 0, err)
        self.assertNotIn("could not add", err)
        self.assertEqual(self.gi_bytes(), after)

    def test_rule_behind_a_nel_character_is_not_the_rule(self):
        nel = "foo\u0085*.lock\n".encode("utf-8")        # str.splitlines() would split here
        self.assert_after_lock(nel, nel + b"*.lock\n")

    def test_rule_with_leading_spaces_is_not_the_rule(self):
        self.assert_after_lock(b"  *.lock\n", b"  *.lock\n*.lock\n")

    def test_crlf_line_endings_are_accepted_as_the_rule(self):
        crlf = b"# rules\r\n*.lock\r\nnotes/\r\n"
        self.assert_after_lock(crlf, crlf)

    def test_only_one_trailing_cr_is_stripped(self):
        """git strips exactly one "\\r"; `*.lock\\r` (after that strip) is not the rule."""
        self.assert_after_lock(b"*.lock\r\r\n", b"*.lock\r\r\n*.lock\n")

    def test_a_leading_utf8_bom_is_skipped(self):
        """git skips a leading UTF-8 BOM, so the rule on the first line is present."""
        bom = b"\xef\xbb\xbf*.lock\n"
        self.assert_after_lock(bom, bom)

    def test_appending_after_a_bom_keeps_one_bom(self):
        self.assert_after_lock(b"\xef\xbb\xbfnotes/\n", b"\xef\xbb\xbfnotes/\n*.lock\n")

    def test_trailing_spaces_are_accepted_as_the_rule(self):
        self.assert_after_lock(b"*.lock  \n", b"*.lock  \n")

    def test_a_later_full_negation_undoes_the_rule(self):
        self.assert_after_lock(b"*.lock\n!*.lock\n", b"*.lock\n!*.lock\n*.lock\n")

    def test_a_narrower_negation_is_left_as_the_user_wrote_it(self):
        self.assert_after_lock(b"*.lock\n!keep.lock\n", b"*.lock\n!keep.lock\n")

    def test_a_narrower_negation_on_notices_is_left_as_the_user_wrote_it(self):
        """The mirror of the *.lock narrower-negation case, for the newer pattern: a
        negation that does not match `.notices.yaml` exactly must not be treated as
        undoing it, so the rule is still missing and gets (re-)appended."""
        self.assert_after_lock(
            b".notices.yaml\n!keep.notices.yaml\n",
            b".notices.yaml\n!keep.notices.yaml\n*.lock\n",
            notices_presatisfied=False)

    def test_both_patterns_appended_together_from_scratch(self):
        """A consumer state root with neither pattern yet ends up ignoring both, in one
        append, in `_GITIGNORE_PATTERNS` order."""
        self.assert_after_lock(b"# team rules\nnotes/\n",
                               b"# team rules\nnotes/\n*.lock\n.notices.yaml\n",
                               notices_presatisfied=False)

    def test_a_later_full_negation_of_notices_undoes_it_too(self):
        self.assert_after_lock(b".notices.yaml\n!.notices.yaml\n",
                               b".notices.yaml\n!.notices.yaml\n*.lock\n.notices.yaml\n",
                               notices_presatisfied=False)

    def test_read_only_gitignore_that_has_the_rule_does_not_warn(self):
        with open(self.gi, "wb") as fh:
            fh.write(b"*.lock\n.notices.yaml\n")
        os.chmod(self.gi, 0o444)
        if os.access(self.gi, os.W_OK):
            self.skipTest("chmod does not bind (running as root)")
        code, _, err = self.append("A")
        self.assertEqual(code, 0, err)
        self.assertNotIn("could not add", err)
        self.assertEqual(self.gi_bytes(), b"*.lock\n.notices.yaml\n")

    def test_explicit_state_root_gets_the_rule_before_any_epic_exists(self):
        fresh = os.path.join(self.d, "fresh", "state")
        os.makedirs(fresh)
        code, _, err = self.append("A", root=fresh)
        self.assertEqual(code, 0, err)
        with open(os.path.join(fresh, ".gitignore"), encoding="utf-8") as fh:
            self.assertIn("*.lock", fh.read().splitlines())

    # -- real git ---------------------------------------------------------------------- #
    def git(self, *args, check=True):
        import subprocess
        return subprocess.run(["git", "-C", self.d, *args], capture_output=True, text=True,
                              check=check)

    def init_repo(self):
        if shutil.which("git") is None:
            self.skipTest("git not available")
        self.d = os.path.realpath(self.d)
        self.arts = os.path.join(self.d, "impl")
        self.root = os.path.join(self.arts, "state")
        self.gi = os.path.join(self.root, ".gitignore")
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "t")
        self.git("config", "commit.gpgsign", "false")

    def test_git_sees_the_gitignore_and_no_lock_files_and_the_gate_still_passes(self):
        self.init_repo()
        self.assertEqual(self.append("A")[0], 0)
        porcelain = self.git("status", "--porcelain", "--untracked-files=all").stdout
        paths = [line[3:] for line in porcelain.splitlines()]
        self.assertIn("impl/state/.gitignore", paths)
        self.assertEqual([p for p in paths if p.endswith(".lock")], [], porcelain)
        self.assertTrue(os.path.exists(self.lock), "premise: lock files exist")
        # step-00-activate's gate: the state-root DIRECTORY must not be ignored.
        gate = self.git("check-ignore", "-q", self.root, check=False)
        self.assertEqual(gate.returncode, 1, "the state root must stay NOT ignored")


class TestLenientArgsAreStoredCanonical(unittest.TestCase):
    """Every argument the CLI accepts leniently must be STORED canonically.

    --epic and --sprint accept six spellings each ('3', '03', '003', 'E3', 'E003', 'e003')
    and all six produce the same correct key -- then the caller's spelling was written to
    disk. One epic appeared six ways in one file. --status and --story are not here because
    they are strict: they reject a non-canonical spelling rather than normalising it, so
    raw already equals canonical.

    This drives the real CLI rather than the helpers, because the defect was never in
    _norm_num -- it was four call sites that computed the normalised value, used it for the
    key, and then stored args.* anyway. A helper test would have passed throughout.
    """

    SPELLINGS = [("3", "1"), ("03", "1"), ("003", "01"),
                 ("E3", "S1"), ("E003", "S01"), ("e003", "s01")]

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        sd = os.path.join(self.root, "active", "epic-003", "sprint-01")
        os.makedirs(sd)
        with open(os.path.join(self.root, "active", "epic-003", "epic.yaml"), "w") as f:
            f.write("key: 'E003'\nstatus: in-progress\n")
        with open(os.path.join(sd, "sprint.yaml"), "w") as f:
            f.write("key: 'S01'\nepic: 'E003'\nstatus: in-progress\n")

    def cli(self, *args):
        import subprocess  # local, matching this file's idiom elsewhere
        return subprocess.run([sys.executable, SCRIPT, *args],
                              capture_output=True, text=True, check=False)

    def test_the_event_log_stores_one_spelling(self):
        """The functional half: _dispatch_identity is (agent, epic, sprint, story), so a
        close spelled differently from its open never cancels it."""
        for e, sp in self.SPELLINGS:
            self.cli("dispatch", "--state-root", self.root, "--event", "open",
                     "--agent", "ag", "--epic", e, "--sprint", sp, "--session-id", "s")
        recs = [json.loads(x) for x in
                open(os.path.join(self.root, "events.jsonl"), encoding="utf-8") if x.strip()]
        d = [r for r in recs if str(r.get("event", "")).startswith("dispatch")]
        self.assertEqual({r["epic"] for r in d}, {"E003"}, "epic spellings leaked into events")
        self.assertEqual({r["sprint"] for r in d}, {"S01"}, "sprint spellings leaked into events")

    def test_a_close_cancels_its_open_whatever_spelling_either_used(self):
        self.cli("dispatch", "--state-root", self.root, "--event", "open", "--agent", "ag",
                 "--epic", "003", "--sprint", "01", "--session-id", "s")
        self.cli("dispatch", "--state-root", self.root, "--event", "close", "--agent", "ag",
                 "--epic", "E003", "--sprint", "S01", "--session-id", "s")
        self.assertEqual(pm.open_dispatches(self.root, 0.0), [],
                         "a close spelled differently from its open left it open forever")

    def test_the_adr_register_stores_one_spelling(self):
        adr = os.path.join(self.d, "docs", "adr")
        os.makedirs(adr)
        for e, _ in self.SPELLINGS:
            self.cli("adr-reserve", "--state-root", self.root, "--epic", e,
                     "--slug", "s", "--adr-dir", adr)
        _, reg = pm.load_adr_register(self.root)
        self.assertEqual({str(x["epic"]) for x in reg.get("reserved") or []}, {"E003"})

    def test_strict_arguments_reject_rather_than_normalise(self):
        """--status and --story are deliberately NOT in the lenient set. If either ever
        starts accepting a non-canonical spelling, it joins the class above and needs the
        same storage guarantee."""
        r = self.cli("import-node", "--state-root", self.root, "--story", "E003-S01-009",
                     "--status", "DONE")
        self.assertEqual(r.returncode, 2, "--status must reject 'DONE', not normalise it")
        r = self.cli("import-node", "--state-root", self.root, "--story", "e003-s01-009",
                     "--status", "done")
        self.assertNotEqual(r.returncode, 0, "--story must reject a lowercase key")


class TestAdrReserveScansDisk(unittest.TestCase):
    """adr-reserve starts at max(register next, highest ADR on disk + 1): docs/adr (the one
    home, ADR-0005) and the old epic-*/arch home, under the register's own lock."""

    GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.impl = os.path.join(self.d, "impl")
        self.root = os.path.join(self.impl, "state")
        os.makedirs(self.root)
        self.empty = os.path.join(self.d, "no-adr-dir")

    def touch(self, *parts):
        p = os.path.join(self.d, *parts)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("# ADR\n")

    def reserve(self, *extra):
        import subprocess
        r = subprocess.run([sys.executable, SCRIPT, "adr-reserve", "--state-root", self.root,
                            "--epic", "E001", "--slug", "t", *extra],
                           capture_output=True, text=True, env={**os.environ, **self.GIT_ENV})
        return r.returncode, r.stdout.split(), r.stderr

    def test_explicit_adr_dir_is_scanned(self):
        self.touch("docs", "adr", "0010-z.md")
        code, out, err = self.reserve("--adr-dir", os.path.join(self.d, "docs", "adr"))
        self.assertEqual((code, out), (0, ["0011"]), err)
        self.assertEqual(pm.load_adr_register(self.root)[1]["next"], 12)

    def test_old_home_is_scanned(self):
        self.touch("impl", "epic-001", "arch", "adr-0004-y.md")
        code, out, err = self.reserve("--adr-dir", self.empty)
        self.assertEqual((code, out), (0, ["0005"]), err)

    def test_adr_prefixed_filenames_in_the_one_home_are_scanned(self):
        """`ADR-NNNN-slug.md` is the naming a hand-written ADR usually carries, and the
        hand-written ADR is precisely what this scan exists to catch. Against the old
        `^\\d{4}` pattern a directory of them scanned as "highest is 0" -- indistinguishable
        from an empty one -- so adr-reserve reissued numbers that were already on disk."""
        self.touch("docs", "adr", "ADR-0025-infisical.md")
        code, out, err = self.reserve("--adr-dir", os.path.join(self.d, "docs", "adr"))
        self.assertEqual((code, out), (0, ["0026"]), err)

    def test_adr_prefix_is_case_insensitive_in_both_homes(self):
        self.touch("docs", "adr", "Adr-0009-x.md")
        self.touch("impl", "epic-001", "arch", "ADR-0031-y.md")
        code, out, err = self.reserve("--adr-dir", os.path.join(self.d, "docs", "adr"))
        self.assertEqual((code, out), (0, ["0032"]), err)

    def test_widening_did_not_swallow_non_adr_filenames(self):
        """The scope half of the change: an `ADR-` prefix became optional, nothing else did.
        Without this, a bare `^.*(\\d{4})` would pass every test above and quietly take the
        highest four digits out of any filename in the directory."""
        for name in ("README.md", "0025.md", "notes-0099-x.md", "index.md"):
            self.touch("docs", "adr", name)
        code, out, err = self.reserve("--adr-dir", os.path.join(self.d, "docs", "adr"))
        self.assertEqual((code, out), (0, ["0001"]), err)

    def test_register_ahead_of_disk_wins(self):
        with open(pm.adr_register_path(self.root), "w", encoding="utf-8") as fh:
            fh.write("next: 20\nreserved: []\n")
        self.touch("docs", "adr", "0007-x.md")
        code, out, _ = self.reserve("--adr-dir", os.path.join(self.d, "docs", "adr"))
        self.assertEqual(out, ["0020"])

    def test_default_adr_dir_is_the_git_toplevel(self):
        import subprocess
        subprocess.run(["git", "init", "-q", self.d], check=True,
                       env={**os.environ, **self.GIT_ENV})
        self.touch("docs", "adr", "0007-x.md")
        code, out, err = self.reserve()
        self.assertEqual((code, out), (0, ["0008"]), err)
        self.assertNotIn("not inside a git work tree", err)

    def test_outside_git_without_adr_dir_refuses_rather_than_guessing(self):
        """The regression this guards: a warning on stderr, `0001` on stdout, exit 0.

        A caller capturing stdout -- which is the documented way to use this
        subcommand, and the only thing stopping two ADRs sharing one number --
        got a confidently wrong allocation with a success code. docs/adr/0007
        below is real and unreachable without git or --adr-dir, so the number
        that WOULD have been printed collides with a file already on disk.
        """
        self.touch("docs", "adr", "0007-x.md")      # unreachable without git or --adr-dir
        self.touch("impl", "epic-002", "arch", "adr-0002-y.md")
        code, out, err = self.reserve()
        self.assertEqual(code, 2, f"expected a refusal, got exit {code} and {out!r}")
        self.assertEqual(out, [], "a refusal must print no number at all")
        self.assertIn("--adr-dir", err, "the refusal must name what to pass")
        self.assertIn("not inside a git work tree", err)
        # And it refused BEFORE mutating: no reservation was recorded.
        self.assertFalse(os.path.exists(pm.adr_register_path(self.root)),
                         "a refused reservation must not write the register")

    def test_refusal_does_not_consume_a_number_from_an_existing_register(self):
        """The register must survive a refusal unchanged -- a burnt `next` would
        leave a permanent gap, and a recorded `reserved` entry would name an
        agent that was never handed anything."""
        with open(pm.adr_register_path(self.root), "w", encoding="utf-8") as fh:
            fh.write("next: 5\nreserved: []\n")
        before = open(pm.adr_register_path(self.root), encoding="utf-8").read()
        code, out, err = self.reserve()
        self.assertEqual((code, out), (2, []), err)
        self.assertEqual(open(pm.adr_register_path(self.root), encoding="utf-8").read(), before)

    def test_a_normal_allocation_still_returns_the_right_number(self):
        """The other direction: when it CAN scan, nothing about the allocation
        changed -- max(register next, highest on disk) + 1, exit 0, one line."""
        with open(pm.adr_register_path(self.root), "w", encoding="utf-8") as fh:
            fh.write("next: 3\nreserved: []\n")
        self.touch("docs", "adr", "0009-x.md")
        self.touch("impl", "epic-002", "arch", "adr-0002-y.md")
        code, out, err = self.reserve("--adr-dir", os.path.join(self.d, "docs", "adr"))
        self.assertEqual((code, out), (0, ["0010"]), err)
        self.assertEqual(err, "")
        self.assertEqual(pm.load_adr_register(self.root)[1]["next"], 11)

    def test_concurrent_reservations_skip_a_hand_written_adr(self):
        import subprocess
        self.touch("docs", "adr", "0003-hand.md")
        adr_dir = os.path.join(self.d, "docs", "adr")
        procs = [subprocess.Popen([sys.executable, SCRIPT, "adr-reserve", "--state-root",
                                   self.root, "--epic", "E001", "--slug", f"s{i}",
                                   "--adr-dir", adr_dir],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(8)]
        numbers = []
        for p in procs:
            out, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err.decode())
            numbers.extend(out.decode().split())
        self.assertEqual(sorted(numbers), [f"{n:04d}" for n in range(4, 12)])


class TestBlockedCalibration(Base):
    """Stage 2: a story that spent any time blocked excludes elapsed_hours from
    its calibration sample and emits WARN naming the {N.N}h in blocked. Other
    metrics stay recorded. completion_evidence.blocks_seen is incremented on
    every block_open regardless of the sample state.

    Design: docs/superpowers/specs/2026-09-25-story-lifecycle-blocked-design.md §5.
    """

    def _sample(self):
        """One story sample, as build-close takes it: an estimate made by the estimate
        engine, the build's actual, and the ticket's key. Returns stderr."""
        node = {"key": "E001-S01-002"}
        pm.metrics.estimates.compute_story_estimate(self.d, node, "standard",
                                                    pm.DEFAULT_ESTIMATE_MODEL, None)
        node["actual"] = {"elapsed_hours": 1.8, "man_hours": 7, "hitl_hours": 0.5,
                          "tokens_k": {"total": 375, "input": 300, "output": 55,
                                       "cache_write": 10, "cache_read": 10}}
        node["completion_evidence"] = {"fix_iterations": 0}
        err = io.StringIO()
        with redirect_stderr(err):
            pm.record_story_sample(self.d, node)
        return err.getvalue()

    # ---- blocks_seen counter -------------------------------------------------------

    def test_total_blocked_hours_is_zero_when_no_events(self):
        self.assertEqual(pm._total_blocked_hours(self.d, "E001-S01-002"), 0.0)

    def test_total_blocked_hours_sums_across_multiple_closes(self):
        """A story blocked-resumed-blocked-resumed contributes both durations."""
        # Craft events by hand -- realistic durations without waiting real hours.
        events = os.path.join(self.d, "events.jsonl")
        with open(events, "w") as fh:
            fh.writelines(json.dumps(rec) + "\n" for rec in [
                {"event": "block_close", "story": "E001-S01-002", "duration_hours": 2.5},
                {"event": "block_close", "story": "E001-S01-002", "duration_hours": 1.25},
                {"event": "block_close", "story": "E001-OTHER", "duration_hours": 99.0},
            ])
        self.assertEqual(pm._total_blocked_hours(self.d, "E001-S01-002"), 3.75)

    def test_total_blocked_hours_survives_torn_line(self):
        """A partially-written line in events.jsonl does not fail the calibration path."""
        events = os.path.join(self.d, "events.jsonl")
        with open(events, "w") as fh:
            fh.write(json.dumps({"event": "block_close", "story": "E001-S01-002",
                                 "duration_hours": 1.0}) + "\n")
            fh.write("{\"event\": \"block_close\", torn")
        self.assertEqual(pm._total_blocked_hours(self.d, "E001-S01-002"), 1.0)

    def test_total_blocked_hours_scoped_to_since_last_dispatch_open(self):
        """The multi-session case named in §5 amendment: a story blocked in Session 1 and
        completed cleanly in Session 2 must not get Session 2's elapsed_hours excluded.
        The scan starts at the most recent dispatch_open, so Session 1's block_close is
        outside the window."""
        events = os.path.join(self.d, "events.jsonl")
        with open(events, "w") as fh:
            # Session 1: dispatch_open, blocked, block_close, dispatch_close.
            for rec in [
                {"event": "dispatch_open", "story": "E001-S01-002"},
                {"event": "block_close", "story": "E001-S01-002", "duration_hours": 4.0},
                {"event": "dispatch_close", "story": "E001-S01-002"},
                # Session 2: dispatch_open, no blocks, clean run.
                {"event": "dispatch_open", "story": "E001-S01-002"},
            ]:
                fh.write(json.dumps(rec) + "\n")
        self.assertEqual(pm._total_blocked_hours(self.d, "E001-S01-002"), 0.0,
                         "Session 2 has no blocks; Session 1's 4h must NOT carry over")

    def test_total_blocked_hours_only_current_dispatch_cycle_counted(self):
        """The current-cycle block IS counted; the prior-cycle block is not."""
        events = os.path.join(self.d, "events.jsonl")
        with open(events, "w") as fh:
            fh.writelines(json.dumps(rec) + "\n" for rec in [
                {"event": "dispatch_open", "story": "E001-S01-002"},
                {"event": "block_close", "story": "E001-S01-002", "duration_hours": 4.0},
                {"event": "dispatch_close", "story": "E001-S01-002"},
                {"event": "dispatch_open", "story": "E001-S01-002"},
                {"event": "block_close", "story": "E001-S01-002", "duration_hours": 1.5},
            ])
        self.assertEqual(pm._total_blocked_hours(self.d, "E001-S01-002"), 1.5,
                         "only the block after the latest dispatch_open counts")

    def test_total_blocked_hours_no_dispatch_open_falls_back_to_all(self):
        """Backward-compat for stories that predate dispatch bracketing: no dispatch_open
        on record means the safety-first bias applies -- sum everything."""
        events = os.path.join(self.d, "events.jsonl")
        with open(events, "w") as fh:
            fh.write(json.dumps({"event": "block_close", "story": "E001-S01-002",
                                 "duration_hours": 2.0}) + "\n")
            fh.write(json.dumps({"event": "block_close", "story": "E001-S01-002",
                                 "duration_hours": 3.0}) + "\n")
        self.assertEqual(pm._total_blocked_hours(self.d, "E001-S01-002"), 5.0)

    def test_total_blocked_hours_dispatch_open_from_other_story_does_not_move_boundary(self):
        """The boundary is per-story: another story's dispatch_open does not reset ours."""
        events = os.path.join(self.d, "events.jsonl")
        with open(events, "w") as fh:
            for rec in [
                {"event": "dispatch_open", "story": "E001-S01-002"},
                {"event": "block_close", "story": "E001-S01-002", "duration_hours": 4.0},
                {"event": "dispatch_open", "story": "E001-S01-999"},  # unrelated story
            ]:
                fh.write(json.dumps(rec) + "\n")
        self.assertEqual(pm._total_blocked_hours(self.d, "E001-S01-002"), 4.0,
                         "the unrelated story's dispatch_open must not reset our window")

    # ---- Calibration exclusion via derive_story_sample ------------------------------

    def test_derive_story_sample_keeps_elapsed_when_blocked_hours_is_zero(self):
        """Baseline: without blocked time, elapsed_hours is one of the scope_ratios
        that derive_story_sample emits."""
        node = {
            "key": "E001-S01-001", "classification": "standard",
            "estimate": {"elapsed_hours": 2.0, "man_hours": 6.0, "hitl_hours": 1.0,
                         "tokens_k": {"input": 10, "output": 5, "cache_write": 5,
                                      "cache_read": 5, "total": 25},
                         "fix_factor": 1.0, "scope_ratios": {"elapsed_hours": 1.0}},
            "actual":   {"elapsed_hours": 2.0, "man_hours": 6.0, "hitl_hours": 1.0,
                         "tokens_k": {"input": 10, "output": 5, "cache_write": 5,
                                      "cache_read": 5, "total": 25}},
            "completion_evidence": {"fix_iterations": 0},
        }
        sample = pm.derive_story_sample(node, blocked_hours=0.0)
        self.assertIn("elapsed_hours", sample["scope_ratios"])

    def test_derive_story_sample_drops_elapsed_when_blocked_hours_positive(self):
        """The load-bearing property: blocked wall-clock includes human wait, and
        folding that into calibration would poison scope. Other metrics remain."""
        node = {
            "key": "E001-S01-001", "classification": "standard",
            "estimate": {"elapsed_hours": 2.0, "man_hours": 6.0, "hitl_hours": 1.0,
                         "tokens_k": {"input": 10, "output": 5, "cache_write": 5,
                                      "cache_read": 5, "total": 25},
                         "fix_factor": 1.0, "scope_ratios": {"elapsed_hours": 1.0}},
            "actual":   {"elapsed_hours": 12.0, "man_hours": 6.0, "hitl_hours": 1.0,
                         "tokens_k": {"input": 10, "output": 5, "cache_write": 5,
                                      "cache_read": 5, "total": 25}},
            "completion_evidence": {"fix_iterations": 0},
        }
        sample = pm.derive_story_sample(node, blocked_hours=6.5)
        self.assertNotIn("elapsed_hours", sample["scope_ratios"],
                         "elapsed_hours must be dropped when the story spent time blocked")
        for m in ("man_hours", "hitl_hours", "tokens_k"):
            self.assertIn(m, sample["scope_ratios"],
                          f"{m} must survive: blocked time does not poison it")

    def test_record_story_sample_warns_with_inline_duration(self):
        """WARN message shape checked verbatim -- operators eyeball the exclusion
        without cross-referencing the event log."""
        # Simulate: block, resume, build-close. The block_close duration lands
        # via _block_duration_since_last_open; here we plant events by hand for
        # a known duration so the WARN wording is deterministic.
        events = os.path.join(self.d, "events.jsonl")
        with open(events, "a") as fh:
            fh.write(json.dumps({"event": "block_close", "story": "E001-S01-002",
                                 "duration_hours": 6.5}) + "\n")
        err = self._sample()
        self.assertIn("WARN blocked story E001-S01-002", err)
        self.assertIn("6.5h in blocked", err)
        self.assertIn("elapsed_hours sample deferred", err)
        self.assertIn("man_hours, hitl_hours, tokens_k still recorded", err)

    def test_record_story_sample_no_warn_when_never_blocked(self):
        """A story with no blocked history writes its sample cleanly -- no WARN."""
        err = self._sample()
        self.assertNotIn("WARN blocked story", err)


class TestAgentInstructionsEngine(unittest.TestCase):
    """The marker engine for the agent instruction block (pure string transforms)."""

    BODY = "## LiquidLogicLabs Extensions (l3io)\n\nState is machine-written.\n"

    # -- find_block --
    def test_absent_returns_none(self):
        self.assertIsNone(pm.find_block("# My Project\n\nNotes.\n"))

    def test_finds_and_reports_version(self):
        text = f"<!-- l3io:begin v=3.2.6 -->\n{self.BODY}<!-- l3io:end -->\n"
        start, end, version = pm.find_block(text)
        self.assertEqual(version, "3.2.6")
        self.assertEqual(text[start:end], text.rstrip("\n"))  # the span excludes the trailing newline

    def test_crlf_file_is_found(self):
        # A Windows-authored instruction file.
        text = f"<!-- l3io:begin v=3.2.6 -->\n{self.BODY}<!-- l3io:end -->\n".replace("\n", "\r\n")
        self.assertIsNotNone(pm.find_block(text))
        # and a replace keeps the file CRLF throughout
        out, action = pm.apply_block(text, "## New\n", "3.3.0")
        self.assertEqual(action, "replaced")
        self.assertNotIn("\n", out.replace("\r\n", ""))

    def test_marker_inside_a_fenced_code_block_is_not_a_block(self):
        # Our own docs show this syntax; it must not match.
        text = ("# Docs\n\n```markdown\n<!-- l3io:begin v=1.0.0 -->\nexample\n"
                "<!-- l3io:end -->\n```\n")
        self.assertIsNone(pm.find_block(text))

    def test_two_opening_markers_raise(self):
        # A bad merge. "Between the markers" is undefined; refuse.
        text = ("<!-- l3io:begin v=1 -->\na\n<!-- l3io:end -->\n"
                "<!-- l3io:begin v=2 -->\nb\n<!-- l3io:end -->\n")
        with self.assertRaises(pm.BlockError):
            pm.find_block(text)

    def test_opening_without_closing_raises(self):
        with self.assertRaises(pm.BlockError):
            pm.find_block("<!-- l3io:begin v=1 -->\nstranded\n")

    # -- apply_block --
    def test_creates_on_empty_file(self):
        out, action = pm.apply_block("", self.BODY, "3.2.6")
        self.assertEqual(action, "created")
        self.assertIn("<!-- l3io:begin v=3.2.6 -->", out)
        self.assertIn("<!-- l3io:end -->", out)

    def test_appends_without_disturbing_existing_content(self):
        before = "# My Project\n\nUser notes.\n"
        out, action = pm.apply_block(before, self.BODY, "3.2.6")
        self.assertEqual(action, "created")
        self.assertTrue(out.startswith(before))

    def test_identical_body_is_unchanged_even_when_version_differs(self):
        # Spec 2.1: upgrade compares the BODY. A version bump alone must not rewrite
        # a file in the user's repo.
        text, _ = pm.apply_block("", self.BODY, "3.2.6")
        out, action = pm.apply_block(text, self.BODY, "9.9.9")
        self.assertEqual(action, "unchanged")
        self.assertEqual(out, text)

    def test_changed_body_is_replaced_in_place(self):
        text, _ = pm.apply_block("prefix\n", self.BODY, "3.2.6")
        out, action = pm.apply_block(text, "## New\n\nDifferent.\n", "3.3.0")
        self.assertEqual(action, "replaced")
        self.assertTrue(out.startswith("prefix\n"))
        self.assertIn("v=3.3.0", out)
        self.assertNotIn("State is machine-written", out)

    def test_content_outside_the_markers_survives_replacement(self):
        before = "TOP\n\n" + pm.apply_block("", self.BODY, "3.2.6")[0] + "\nBOTTOM\n"
        out, _ = pm.apply_block(before, "## New\n\nX.\n", "3.3.0")
        self.assertTrue(out.startswith("TOP\n\n"))
        self.assertTrue(out.rstrip().endswith("BOTTOM"))

    def test_is_idempotent(self):
        once, _ = pm.apply_block("", self.BODY, "3.2.6")
        twice, action = pm.apply_block(once, self.BODY, "3.2.6")
        self.assertEqual(action, "unchanged")
        self.assertEqual(once, twice)

    # -- remove_block --
    def test_removes_only_the_block(self):
        text = "TOP\n\n" + pm.apply_block("", self.BODY, "3.2.6")[0] + "\nBOTTOM\n"
        out, action = pm.remove_block(text)
        self.assertEqual(action, "removed")
        self.assertNotIn("l3io:begin", out)
        self.assertIn("TOP", out)
        self.assertIn("BOTTOM", out)

    def test_remove_leaves_blank_runs_elsewhere_byte_for_byte(self):
        keep = "top\n\n\n\nkeep\n```\na\n\n\n\nb\n```\n"
        text = keep + pm.apply_block("", self.BODY, "3.2.6")[0]
        out, action = pm.remove_block(text)
        self.assertEqual(action, "removed")
        self.assertEqual(out, keep)

    def test_multiline_body_in_crlf_file_has_no_bare_lf_and_is_stable(self):
        text = "# Mine\r\n"
        once, action = pm.apply_block(text, self.BODY, "3.2.6")
        self.assertEqual(action, "created")
        self.assertNotIn("\n", once.replace("\r\n", ""))
        twice, action = pm.apply_block(once, self.BODY, "3.2.6")
        self.assertEqual(action, "unchanged")
        self.assertEqual(twice, once)

    def test_four_backtick_fence_containing_three_backticks_hides_marker(self):
        text = ("````markdown\n```\n<!-- l3io:begin v=1 -->\nx\n<!-- l3io:end -->\n```\n````\n")
        self.assertIsNone(pm.find_block(text))
        out, action = pm.apply_block(text, self.BODY, "3.2.6")
        self.assertEqual(action, "created")
        self.assertIsNotNone(pm.find_block(out))

    def test_tilde_fence_is_not_closed_by_backticks(self):
        text = "~~~\n```\n<!-- l3io:begin v=1 -->\nx\n<!-- l3io:end -->\n~~~\n"
        self.assertIsNone(pm.find_block(text))

    def test_block_after_a_properly_closed_fence_is_found(self):
        text = "```\ncode\n```\n" + pm.apply_block("", self.BODY, "3.2.6")[0]
        self.assertIsNotNone(pm.find_block(text))

    def test_absent_block_is_not_an_error(self):
        out, action = pm.remove_block("# Nothing here\n")
        self.assertEqual(action, "absent")
        self.assertEqual(out, "# Nothing here\n")


class TestShippedAsset(unittest.TestCase):
    from pathlib import Path as _Path
    ASSET = _Path(__file__).resolve().parent.parent / "agent-instructions.md"

    def test_asset_exists(self):
        self.assertTrue(self.ASSET.is_file(), f"missing {self.ASSET}")

    def test_stays_under_2kb(self):
        # This block enters every agent's context in the consuming project, on every
        # invocation, forever. l3io-doctor's SKILL.md once reached 96,980 B and every
        # invocation paid for procedures it never ran; the same discipline applies harder
        # here, because this is not even our file.
        size = self.ASSET.stat().st_size
        self.assertLess(size, 2048, f"asset is {size} B; budget is 2048 B")

    def test_covers_the_six_required_points(self):
        text = self.ASSET.read_text(encoding="utf-8")
        for needle in ["pm-status.py", "never hand-edit", "conversational",
                       "actual", "calibrat", "rates"]:
            self.assertIn(needle.lower(), text.lower(), f"asset omits {needle!r}")

    def test_contains_no_flagged_invocation(self):
        # Check 31's rule, enforced at the source: no /l3io-* invocation carries a --flag.
        text = self.ASSET.read_text(encoding="utf-8")
        self.assertNotRegex(text, r"/l3io-[a-z0-9-]+[^\n`]*\s--[a-z]")


class TestAgentInstructions(unittest.TestCase):
    """The instruction-block subcommand. Covers Review Focus 4 (non-UTF-8) and 5 (locking).

    Runs the CLI as a SUBPROCESS rather than through Base.run_main: run_main returns
    (code, stdout) and does not capture stderr, and several assertions here are about the
    refusal message. The concurrency case needs real processes anyway -- the same shape
    TestConcurrentNoticeDistinctKeys already uses.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)

    def _body(self, text="## l3io\n\nBody.\n"):
        p = Path(self.d) / "body.md"
        p.write_text(text, encoding="utf-8")
        return str(p)

    def _run(self, *argv):
        import subprocess
        return subprocess.run([sys.executable, SCRIPT, "sync-agent-instructions", *argv],
                              capture_output=True, text=True)

    def test_claude_runtime_writes_claude_md(self):
        r = self._run("--runtime", "claude", "--project-root", self.d,
                      "--body-file", self._body(), "--version", "9.9.9", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("l3io:begin v=9.9.9",
                      (Path(self.d) / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_copilot_runtime_writes_its_own_file_not_claude(self):
        self._run("--runtime", "copilot", "--project-root", self.d,
                  "--body-file", self._body(), "--apply")
        self.assertTrue((Path(self.d) / ".github" / "copilot-instructions.md").is_file())
        self.assertFalse((Path(self.d) / "CLAUDE.md").exists(),
                         "must never write a file for a harness that is not running")

    # --- our block in ANOTHER harness's file ---------------------------------------- #
    # A project that changes harness, or one set up before the target was decided by
    # --runtime alone, keeps our block where the old harness read it. It carries our version
    # marker, so leaving it stale puts two disagreeing copies of our instructions in one
    # repo — and harnesses commonly read more than one of these files.

    def _stale_agents_md(self, version="1.0.0", keep="# Project rules\n\nMine.\n"):
        """AGENTS.md holding our block at `version`, under the user's own content."""
        (Path(self.d) / "AGENTS.md").write_text(keep, encoding="utf-8")
        self._run("--runtime", "other", "--project-root", self.d,
                  "--body-file", self._body("Old body.\n"), "--version", version, "--apply")
        return Path(self.d) / "AGENTS.md"

    def test_apply_refreshes_our_block_in_another_harnesses_file(self):
        agents = self._stale_agents_md()
        r = self._run("--runtime", "claude", "--project-root", self.d,
                      "--body-file", self._body("New body.\n"), "--version", "9.9.9",
                      "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = agents.read_text(encoding="utf-8")
        self.assertIn("l3io:begin v=9.9.9", text)
        self.assertIn("New body.", text)
        self.assertIn("Mine.", text, "the user's own content survives")
        self.assertIn("AGENTS.md", r.stdout, "the extra write is reported, never silent")

    def test_apply_never_CREATES_a_block_in_another_harnesses_file(self):
        """The rule that keeps the refresh above from becoming colonisation: a file with no
        block of ours is not ours to write to, whether or not it exists."""
        other = Path(self.d) / "AGENTS.md"
        other.write_text("# codex rules\n\nnothing of ours.\n", encoding="utf-8")
        before = other.read_bytes()
        self._run("--runtime", "claude", "--project-root", self.d,
                  "--body-file", self._body(), "--apply")
        self.assertEqual(other.read_bytes(), before)

    def test_apply_does_not_bring_another_harnesses_file_into_existence(self):
        self._run("--runtime", "claude", "--project-root", self.d,
                  "--body-file", self._body(), "--apply")
        self.assertFalse((Path(self.d) / "AGENTS.md").exists())

    def test_check_reports_a_stale_copy_as_exit_3_not_as_clean(self):
        """Exit 0 here is what made this invisible: the doctor's health check reported ✓
        over a repo carrying a stale block, so the upgrade looked complete."""
        self._stale_agents_md()
        self._run("--runtime", "claude", "--project-root", self.d,
                  "--body-file", self._body(), "--version", "9.9.9", "--apply")
        (Path(self.d) / "AGENTS.md").write_text(
            (Path(self.d) / "AGENTS.md").read_text(encoding="utf-8")
            .replace("v=9.9.9", "v=1.0.0"), encoding="utf-8")
        r = self._run("--runtime", "claude", "--project-root", self.d,
                      "--version", "9.9.9", "--check")
        self.assertEqual(r.returncode, 3)
        self.assertIn("AGENTS.md", r.stderr)
        self.assertIn("v=1.0.0", r.stderr)

    def test_check_is_clean_once_both_are_current(self):
        self._stale_agents_md()
        self._run("--runtime", "claude", "--project-root", self.d,
                  "--body-file", self._body(), "--version", "9.9.9", "--apply")
        r = self._run("--runtime", "claude", "--project-root", self.d,
                      "--version", "9.9.9", "--check")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_check_still_reports_absent_for_this_harness_over_a_foreign_block(self):
        """Exit 1 keeps its meaning: a block somewhere else is not a block here."""
        self._stale_agents_md()
        r = self._run("--runtime", "claude", "--project-root", self.d, "--check")
        self.assertEqual(r.returncode, 1)

    def test_remove_strips_our_block_from_every_file_that_has_one(self):
        agents = self._stale_agents_md()
        self._run("--runtime", "claude", "--project-root", self.d,
                  "--body-file", self._body(), "--apply")
        r = self._run("--runtime", "claude", "--project-root", self.d, "--remove")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("l3io:begin", agents.read_text(encoding="utf-8"))
        self.assertNotIn("l3io:begin",
                         (Path(self.d) / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertIn("Mine.", agents.read_text(encoding="utf-8"))

    def test_apply_is_idempotent(self):
        a = ("--runtime", "claude", "--project-root", self.d,
             "--body-file", self._body(), "--version", "1.0.0", "--apply")
        self._run(*a)
        first = (Path(self.d) / "CLAUDE.md").read_bytes()
        r = self._run(*a)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(first, (Path(self.d) / "CLAUDE.md").read_bytes())
        self.assertIn("unchanged", r.stdout)

    def test_remove_leaves_the_file_and_the_user_content(self):
        f = Path(self.d) / "CLAUDE.md"
        f.write_text("# Mine\n\nKeep me.\n", encoding="utf-8")
        self._run("--runtime", "claude", "--project-root", self.d,
                  "--body-file", self._body(), "--apply")
        r = self._run("--runtime", "claude", "--project-root", self.d, "--remove")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(f.is_file(), "the file must never be deleted")
        text = f.read_text(encoding="utf-8")
        self.assertIn("Keep me.", text)
        self.assertNotIn("l3io:begin", text)

    def test_round_trip_restores_the_file_byte_for_byte(self):
        f = Path(self.d) / "CLAUDE.md"
        original = "# Mine\n\nKeep me.\n"
        f.write_text(original, encoding="utf-8")
        self._run("--runtime", "claude", "--project-root", self.d,
                  "--body-file", self._body(), "--apply")
        self._run("--runtime", "claude", "--project-root", self.d, "--remove")
        self.assertEqual(f.read_text(encoding="utf-8"), original)

    def test_check_reports_absent_with_exit_1(self):
        r = self._run("--runtime", "claude", "--project-root", self.d, "--check")
        self.assertEqual(r.returncode, 1)

    def test_undecodable_file_exits_2_and_writes_nothing(self):
        # Review Focus 4. An unhandled raise here would abort an otherwise fine install.
        f = Path(self.d) / "CLAUDE.md"
        f.write_bytes(b"\xff\xfe not utf-8 \x00")
        before = f.read_bytes()
        r = self._run("--runtime", "claude", "--project-root", self.d,
                      "--body-file", self._body(), "--apply")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(f.read_bytes(), before)
        self.assertIn("utf-8", r.stderr.lower())

    def test_ambiguous_markers_exit_2_and_write_nothing(self):
        f = Path(self.d) / "CLAUDE.md"
        dup = ("<!-- l3io:begin v=1 -->\na\n<!-- l3io:end -->\n"
               "<!-- l3io:begin v=2 -->\nb\n<!-- l3io:end -->\n")
        f.write_text(dup, encoding="utf-8")
        r = self._run("--runtime", "claude", "--project-root", self.d,
                      "--body-file", self._body(), "--apply")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(f.read_text(encoding="utf-8"), dup)

    def test_concurrent_applies_do_not_duplicate_the_block(self):
        # Review Focus 5. Two skills activating at once against one project.
        import subprocess
        body = self._body()
        procs = [subprocess.Popen(
            [sys.executable, SCRIPT, "sync-agent-instructions", "--runtime", "claude",
             "--project-root", self.d, "--body-file", body, "--apply"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(4)]
        for pr in procs:
            pr.communicate()
            self.assertEqual(pr.returncode, 0)
        text = (Path(self.d) / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertEqual(text.count("l3io:begin"), 1,
                         "concurrent writes duplicated the block -- the lock must cover the "
                         "READ as well as the write")

    def _apply_claude(self):
        return self._run("--runtime", "claude", "--project-root", self.d,
                         "--body-file", self._body(), "--apply")

    def test_lock_file_is_gitignored_in_bmad(self):
        self.assertEqual(self._apply_claude().returncode, 0)
        gi = Path(self.d) / "_bmad" / ".gitignore"
        self.assertEqual(gi.read_text(encoding="utf-8").splitlines().count("*.lock"), 1)
        self.assertNotIn(".notices.yaml", gi.read_text(encoding="utf-8"))

    def test_second_run_does_not_duplicate_the_ignore_rule(self):
        self._apply_claude()
        self._apply_claude()
        gi = Path(self.d) / "_bmad" / ".gitignore"
        self.assertEqual(gi.read_text(encoding="utf-8").splitlines().count("*.lock"), 1)

    def test_existing_bmad_gitignore_is_appended_to_not_clobbered(self):
        gi = Path(self.d) / "_bmad" / ".gitignore"
        gi.parent.mkdir()
        gi.write_text("keep-me\n", encoding="utf-8")
        self._apply_claude()
        lines = gi.read_text(encoding="utf-8").splitlines()
        self.assertIn("keep-me", lines)
        self.assertEqual(lines.count("*.lock"), 1)

    def test_file_mode_is_preserved(self):
        f = Path(self.d) / "CLAUDE.md"
        f.write_text("# Mine\n", encoding="utf-8")
        os.chmod(f, 0o644)
        self.assertEqual(self._apply_claude().returncode, 0)
        self.assertEqual(os.stat(f).st_mode & 0o777, 0o644)

    def test_new_file_gets_umask_mode_not_0600(self):
        self.assertEqual(self._apply_claude().returncode, 0)
        mode = os.stat(Path(self.d) / "CLAUDE.md").st_mode & 0o777
        um = os.umask(0)
        os.umask(um)
        self.assertEqual(mode, 0o666 & ~um)

    def test_symlinked_target_stays_a_symlink_and_real_file_is_updated(self):
        real = Path(self.d) / "AGENTS.md"
        real.write_text("# Shared\n", encoding="utf-8")
        link = Path(self.d) / "CLAUDE.md"
        os.symlink("AGENTS.md", link)
        self.assertEqual(self._apply_claude().returncode, 0)
        self.assertTrue(os.path.islink(link))
        self.assertIn("l3io:begin", real.read_text(encoding="utf-8"))
        self.assertIn("# Shared", link.read_text(encoding="utf-8"))

    def test_remove_and_check_ignore_a_bad_body_file(self):
        self._apply_claude()
        bad = Path(self.d) / "bad.md"
        bad.write_bytes(b"\xff\xfe\x00")
        r = self._run("--runtime", "claude", "--project-root", self.d, "--check",
                      "--body-file", str(Path(self.d) / "missing.md"))
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self._run("--runtime", "claude", "--project-root", self.d, "--remove",
                      "--body-file", str(bad))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("l3io:begin", (Path(self.d) / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_check_writes_nothing_to_a_pristine_directory(self):
        r = self._run("--runtime", "claude", "--project-root", self.d, "--check")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(os.listdir(self.d), [])
        ghost = os.path.join(self.d, "typo", "deeper")
        r = self._run("--runtime", "claude", "--project-root", ghost, "--check")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(self.d, "typo")))

    def test_crlf_body_leaves_no_stray_cr_in_an_lf_file(self):
        body = Path(self.d) / "crlf.md"
        body.write_bytes(b"## l3io\r\n\r\nBody.\r\n")
        f = Path(self.d) / "CLAUDE.md"
        f.write_bytes(b"# Mine\n")
        r = self._run("--runtime", "claude", "--project-root", self.d,
                      "--body-file", str(body), "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(b"\r", f.read_bytes())

    def test_the_read_happens_inside_the_lock(self):
        # The subprocess test above cannot pin this: two racing "created" applies write
        # IDENTICAL text, so a lost update is invisible in the final file. Observe the order
        # instead, the way TestNoticeReadInsideLock does for notices_lock.
        events = []
        real_lock, real_isfile = pm.core.agent_instructions_lock, os.path.isfile
        real_write = pm.core._atomic_text_write
        target = os.path.join(self.d, "CLAUDE.md")

        @contextmanager
        def recording_lock(root):
            with real_lock(root):
                events.append("lock-acquired")
                try:
                    yield
                finally:
                    events.append("lock-released")

        def recording_isfile(p):
            if p == target:
                events.append("read")
            return real_isfile(p)

        def recording_write(path, text):
            events.append("write")
            return real_write(path, text)

        with mock.patch.object(pm.core, "agent_instructions_lock", recording_lock), \
                mock.patch.object(os.path, "isfile", recording_isfile), \
                mock.patch.object(pm.core, "_atomic_text_write", recording_write), \
                redirect_stdout(io.StringIO()):
            code = pm.main(["sync-agent-instructions", "--runtime", "claude",
                            "--project-root", self.d, "--body-file", self._body(), "--apply"])
        self.assertEqual(code, 0)
        self.assertEqual(events, ["lock-acquired", "read", "write", "lock-released"])


class TestNoticeIsPerHarness(unittest.TestCase):
    """A notice satisfied for one harness must not satisfy another, or a project opened
    under a second harness is never offered the block."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)

    def _notice(self, key):
        import subprocess
        return subprocess.run(
            [sys.executable, SCRIPT, "notice", "--state-root", self.d, "--key", key],
            capture_output=True, text=True).returncode

    def test_claude_and_copilot_keys_are_independent(self):
        self.assertEqual(self._notice("ai-rules-missing:claude"), 0, "first claude = emit")
        self.assertEqual(self._notice("ai-rules-missing:claude"), 1, "second claude = silent")
        self.assertEqual(self._notice("ai-rules-missing:copilot"), 0,
                         "copilot must still be offered after claude was satisfied")


SECOND = timedelta(seconds=1)


class TestTranscriptFallback(Base):
    """The fallback recovers a transcript when CLAUDE_CODE_SESSION_ID is absent. It accepts
    by ELIMINATION -- exactly one candidate spanning the node's dispatch bracket -- and
    refuses otherwise. Summing the wrong file is the failure `usage` exists to prevent.

    The dispatch bracket is written by the REAL dispatch verb, never stubbed: the window
    derivation is half of what makes a candidate verifiable, and stubbing it would leave the
    suite green over a fallback that accepts anything.
    """

    KEYS = {"agent": "dev-story", "epic": "E001", "sprint": "S01", "story": "E001-S01-003"}

    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)
        self.home = os.path.join(self.d, "home")
        self.projects = os.path.join(self.home, ".claude", "projects", "-fake")
        os.makedirs(self.projects)

    def _bracket(self):
        """Open and close a real dispatch; return (before, after) as aware datetimes that
        straddle the recorded pair."""
        before = datetime.now(UTC)
        for event in ("open", "close"):
            code, out = self.run_main(["dispatch", "--state-root", self.root,
                                       "--event", event,
                                       "--agent", self.KEYS["agent"],
                                       "--epic", self.KEYS["epic"],
                                       "--sprint", self.KEYS["sprint"],
                                       "--story", self.KEYS["story"]])
            self.assertEqual(code, 0, out)
        return before, datetime.now(UTC)

    def _transcript(self, name, records):
        """Write <name>.jsonl holding one assistant record per (session_id, datetime)."""
        lines = [json.dumps({
            "sessionId": sid, "timestamp": when.isoformat(), "type": "assistant",
            "message": {"id": f"msg-{name}-{i}",
                        "usage": {"input_tokens": 10, "output_tokens": 5,
                                  "cache_creation_input_tokens": 0,
                                  "cache_read_input_tokens": 0}}})
            for i, (sid, when) in enumerate(records)]
        p = os.path.join(self.projects, f"{name}.jsonl")
        Path(p).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def _inside(self):
        """A timestamp inside the recorded dispatch bracket, read back from the log."""
        open_ts, _close = pm.metrics.actuals_usage.dispatch_window(self.root, **self.KEYS)
        return open_ts

    def _discover(self, state_root=None):
        with mock.patch.dict(os.environ, {"HOME": self.home}):
            return pm.discover_session_transcript(state_root or self.root, dict(self.KEYS))

    def test_single_spanning_candidate_is_accepted(self):
        lo, hi = self._bracket()
        self._transcript("sess-a", [("sess-a", lo - SECOND), ("sess-a", self._inside()), ("sess-a", hi + SECOND)])
        paths, sid, why = self._discover()
        self.assertEqual(why, "")
        self.assertEqual(sid, "sess-a")
        self.assertEqual(len(paths), 1)

    def test_idle_session_spanning_the_window_with_no_record_inside_is_refused(self):
        """Open before and after the dispatch, but doing nothing during it: the span test
        alone accepts it and `usage` would print a confident zero for a stranger's file."""
        lo, hi = self._bracket()
        self._transcript("idle", [("idle", lo - SECOND), ("idle", hi + SECOND)])
        paths, sid, why = self._discover()
        self.assertEqual((paths, sid), ([], ""))
        self.assertIn("no transcript spans", why)

    def test_idle_session_does_not_make_a_real_candidate_ambiguous(self):
        lo, hi = self._bracket()
        self._transcript("idle", [("idle", lo - SECOND), ("idle", hi + SECOND)])
        self._transcript("sess-a", [("sess-a", lo - SECOND), ("sess-a", self._inside()),
                                    ("sess-a", hi + SECOND)])
        _paths, sid, why = self._discover()
        self.assertEqual((sid, why), ("sess-a", ""))

    def test_two_spanning_candidates_are_refused(self):
        lo, hi = self._bracket()
        self._transcript("sess-a", [("sess-a", lo - SECOND), ("sess-a", self._inside()), ("sess-a", hi + SECOND)])
        self._transcript("sess-b", [("sess-b", lo - SECOND), ("sess-b", self._inside()), ("sess-b", hi + SECOND)])
        paths, sid, why = self._discover()
        self.assertEqual(paths, [])
        self.assertEqual(sid, "")
        self.assertIn("refusing to choose", why)

    def test_no_spanning_candidate_is_refused(self):
        lo, _hi = self._bracket()
        self._transcript("sess-a", [("sess-a", lo - SECOND), ("sess-a", lo - SECOND)])
        paths, _sid, why = self._discover()
        self.assertEqual(paths, [])
        self.assertIn("no transcript spans", why)

    def test_candidate_starting_after_the_window_opens_is_refused_by_the_span_rule(self):
        """Has a record inside the window, so the in-window guard passes it; it still began
        after the dispatch opened, so only the span rule can refuse it.

        The window is pinned rather than read from a real bracket: events carry one-second
        timestamps, so a real open and close can land in the same second and leave no instant
        that is inside the window yet later than its start."""
        open_ts = datetime.now(UTC) - 20 * SECOND
        close_ts = open_ts + 10 * SECOND
        self._transcript("sess-a", [("sess-a", open_ts + SECOND), ("sess-a", close_ts + SECOND)])
        with mock.patch.object(pm.metrics.actuals_usage, "dispatch_window", return_value=(open_ts, close_ts)):
            paths, _sid, why = self._discover()
        self.assertEqual(paths, [])
        self.assertIn("no transcript spans", why)

    def test_file_with_two_session_ids_is_never_a_candidate(self):
        """A file holding two sessions is malformed whatever we were expecting, so it is
        rejected before its span is even considered."""
        lo, hi = self._bracket()
        self._transcript("mixed", [("sess-a", lo - SECOND), ("sess-b", hi + SECOND)])
        paths, _sid, why = self._discover()
        self.assertEqual(paths, [])
        self.assertIn("no transcript spans", why)

    def test_absent_dispatch_bracket_refuses_with_a_reason(self):
        empty = os.path.join(self.d, "empty-state")
        os.makedirs(empty)
        paths, sid, why = self._discover(state_root=empty)
        self.assertEqual(paths, [])
        self.assertEqual(sid, "")
        self.assertIn("no dispatch_open and dispatch_close", why)

    def test_a_stale_mtime_is_rejected_before_the_file_is_parsed(self):
        """Without the mtime rejection the fallback parses every transcript on the machine on
        every call, and real ones reach tens of megabytes.

        Asserted through behaviour rather than through a read counter: this file WOULD span
        the window if it were parsed, so a missing prefilter surfaces as a two-candidate
        refusal instead of a clean accept.
        """
        lo, hi = self._bracket()
        self._transcript("sess-a", [("sess-a", lo - SECOND), ("sess-a", self._inside()), ("sess-a", hi + SECOND)])
        stale = self._transcript("sess-old",
                                 [("sess-old", lo - SECOND), ("sess-old", self._inside()), ("sess-old", hi + SECOND)])
        old = (lo - timedelta(days=2)).timestamp()
        os.utime(stale, (old, old))
        paths, sid, why = self._discover()
        self.assertEqual(why, "")
        self.assertEqual(sid, "sess-a")
        self.assertEqual(len(paths), 1)

    def test_usage_verb_recovers_the_transcript_without_the_env_variable(self):
        """The wiring in cmd_usage, end to end: no env id, no path, a real bracket."""
        lo, hi = self._bracket()
        self._transcript("sess-a", [("sess-a", lo - SECOND), ("sess-a", self._inside()), ("sess-a", hi + SECOND)])
        env = {k: v for k, v in os.environ.items() if k != pm.CLAUDE_SESSION_ENV}
        env["HOME"] = self.home
        with mock.patch.dict(os.environ, env, clear=True):
            code, out = self.run_main(["usage", "--state-root", self.root,
                                       "--agent", self.KEYS["agent"],
                                       "--epic", self.KEYS["epic"],
                                       "--sprint", self.KEYS["sprint"],
                                       "--story", self.KEYS["story"]])
        self.assertEqual(code, 0, out)
        self.assertIn("session sess-a", out)
        self.assertIn("recovered by elimination", out)

    def test_usage_verb_refusal_names_why_elimination_failed(self):
        lo, hi = self._bracket()
        for n in ("sess-a", "sess-b"):
            self._transcript(n, [(n, lo - SECOND), (n, self._inside()), (n, hi + SECOND)])
        env = {k: v for k, v in os.environ.items() if k != pm.CLAUDE_SESSION_ENV}
        env["HOME"] = self.home
        err = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), redirect_stderr(err):
            code, _out = self.run_main(["usage", "--state-root", self.root,
                                        "--story", self.KEYS["story"]])
        self.assertEqual(code, 2)
        self.assertIn("refusing to choose", err.getvalue())

    def test_usage_json_with_a_node_window_serialises_the_window(self):
        """since/until are datetimes internally and must be emitted as ISO-8601 strings."""
        lo, hi = self._bracket()
        tp = self._transcript("sess-a", [("sess-a", lo - SECOND), ("sess-a", self._inside()), ("sess-a", hi + SECOND)])
        code, out = self.run_main(["usage", tp, "--claude-session", "sess-a",
                                   "--state-root", self.root,
                                   "--story", self.KEYS["story"], "--format", "json"])
        self.assertEqual(code, 0, out)
        doc = json.loads(out)
        self.assertIsInstance(doc["since"], str)
        self.assertIsInstance(doc["until"], str)
        self.assertIsNotNone(pm._parse_iso(doc["since"]))

    def test_accepted_file_survives_a_name_that_does_not_match_its_session(self):
        """The re-resolve matches by filename, so an archived or renamed transcript with a
        subagents/ sibling must still be summed: content verification outranks the name."""
        lo, hi = self._bracket()
        fp = self._transcript("renamed-copy", [("sess-a", lo - SECOND), ("sess-a", self._inside()), ("sess-a", hi + SECOND)])
        subdir = os.path.join(self.projects, "sess-a", "subagents")
        os.makedirs(subdir)
        Path(subdir, "agent-1.jsonl").write_text("{}\n", encoding="utf-8")
        paths, sid, why = self._discover()
        self.assertEqual(why, "")
        self.assertEqual(sid, "sess-a")
        self.assertEqual(paths[0], fp)
        self.assertIn(os.path.join(subdir, "agent-1.jsonl"), paths)

    def test_a_naive_timestamp_file_is_skipped_not_fatal(self):
        lo, hi = self._bracket()
        self._transcript("sess-a", [("sess-a", lo - SECOND), ("sess-a", self._inside()), ("sess-a", hi + SECOND)])
        self._transcript("stray", [("stray", datetime(2020, 1, 1)),  # noqa: DTZ001 -- naive on purpose
                                   ("stray", lo - SECOND), ("stray", hi + SECOND)])
        self._transcript("stray-only-naive", [("stray2", datetime(2099, 1, 1))])  # noqa: DTZ001 -- naive on purpose
        paths, sid, why = self._discover()
        self.assertEqual(why, "")
        self.assertEqual(sid, "sess-a")

    def test_explicit_claude_session_is_never_overridden_by_recovery(self):
        lo, hi = self._bracket()
        self._transcript("sess-a", [("sess-a", lo - SECOND), ("sess-a", self._inside()), ("sess-a", hi + SECOND)])
        env = {k: v for k, v in os.environ.items() if k != pm.CLAUDE_SESSION_ENV}
        env["HOME"] = self.home
        err = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), redirect_stderr(err):
            code, _out = self.run_main(["usage", "--claude-session", "other",
                                        "--state-root", self.root,
                                        "--story", self.KEYS["story"]])
        self.assertEqual(code, 2)
        self.assertIn("other.jsonl", err.getvalue())
        self.assertIn("--claude-session was given", err.getvalue())

    def test_in_flight_node_names_the_missing_close(self):
        code, out = self.run_main(["dispatch", "--state-root", self.root, "--event", "open",
                                   "--agent", self.KEYS["agent"], "--epic", self.KEYS["epic"],
                                   "--sprint", self.KEYS["sprint"],
                                   "--story", self.KEYS["story"]])
        self.assertEqual(code, 0, out)
        paths, _sid, why = self._discover()
        self.assertEqual(paths, [])
        self.assertIn("no dispatch_close", why)
        self.assertIn("in flight", why)


if __name__ == "__main__":
    unittest.main(verbosity=2)
