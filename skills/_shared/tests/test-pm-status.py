#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""
Tests for pm-status.py — run with: uv run test-pm-status.py
Exercises the 3.x sharded layout resolution and key-based node addressing
(import-node/set-actual/set-estimate/verify), the issue verbs, calibration and estimates,
comment/order preservation, the events.jsonl log, and verify exit codes. The v7 sidecar
verbs are in test-pm-status-sidecar.py.
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


def _epic_locked(root, fn, *args, epic="E001"):
    """Call `fn` holding an epic's lock, as every CLI writer of an epic node does."""
    with pm.epic_node_lock(root, epic):
        return fn(*args)


def _fx_node_path(root, story=None, epic=None):
    return pm.story_file(root, story) if story else pm.nodes.epic_file(root, epic)


def _fx_set_status(root, status, story=None, epic=None):
    """Write a node's status directly: a fixture step, not a verb under test."""
    path = _fx_node_path(root, story, epic)
    y, node = pm.load_node(path)
    node["status"] = status
    _epic_locked(root, pm.core._atomic_dump, y, node, path)


def _fx_set_field(root, field, value, story=None, epic=None):
    path = _fx_node_path(root, story, epic)
    y, node = pm.load_node(path)
    cur = node
    parts = field.split(".")
    for k in parts[:-1]:
        cur = cur.setdefault(k, {})
    cur[parts[-1]] = value
    _epic_locked(root, pm.core._atomic_dump, y, node, path)


def _fx_move_epic(root, epic, to):
    """Rename an epic's directory into another status folder, as a 3.x placement did."""
    src = pm.find_epic_dir(root, epic)
    dest = os.path.join(root, to, os.path.basename(src))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    os.rename(src, dest)


def _fx_set_lock(root, epic, session_id, ttl_minutes=30):
    path = pm.nodes.epic_file(root, epic)
    y, node = pm.load_node(path)
    node["_lock"] = {"session_id": session_id, "claimed_at": pm._now_iso(),
                     "ttl_minutes": ttl_minutes}
    _epic_locked(root, pm.core._atomic_dump, y, node, path)


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

    The `issues` extraction then moved the last bare one, `resolve_issue_core`, to
    `issues/store.py`: the target is now `pm.issues.store.resolve_issue_core`, and its two
    callers outside that file -- `_resolve_story_items` (now in `verbs/__init__.py`)
    and `_normalize_one_legacy` in `issues/audit.py` -- reach it through the module object.

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
        self.assertIs(pm.verbs.cmd_import_node, pm.verbs.cmd_import_node)

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
    # here. Task 4.8 retired the placement, listing, node-write and lock verbs; the issues
    # verbs go in Task 4.9, and import-node/import-actual with the migration in Phase 6.
    EXPECTED = (
        "import-node", "verify", "set-estimate", "add-test-run", "notice",
        "set-actual", "import-actual", "report", "dispatch", "usage", "calibration",
        "estimate-story", "estimate-rollup", "rates",
        "append-issue", "resolve-issue", "update-issue", "promote-issue", "schedule-issue",
        "audit-issues", "repair-issue", "list-issues", "adr-reserve",
        "sync-agent-instructions",
        "sidecar-reconcile", "estimate-entries", "set-lane", "build-open", "build-close",
        "epic-close",
    )
    RETIRED = (
        "set-status", "move-epic", "reparent-story", "retire-epic", "reorg-log",
        "reorg-undo", "dump-plan", "list-epics", "list-stories", "show",
        "set-depends-on", "story-doc-init", "set-field", "set-lock", "clear-lock",
        "check-lock",
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
        for name in ("core", "instructions", "issues", "metrics", "nodes", "plan", "verbs",
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

    def test_the_count_is_30(self):
        """Stated as its own assertion because the number is quoted in the design spec, the
        task briefs and the surface baseline. A set comparison alone reports 'missing one'
        without ever saying what the total is supposed to be."""
        self.assertEqual(len(self._registered()), 30)
        self.assertEqual(len(set(self.EXPECTED)), 30, "EXPECTED has a duplicate")

    def test_cli_surface_after_placement_retired(self):
        """Sofia owns the work-item tree (ADR-0015), so the 3.x placement, listing, node-write
        and lock verbs are gone; none of them may come back as a subcommand."""
        registered = set(self._registered())
        self.assertEqual(sorted(registered & set(self.RETIRED)), [])
        self.assertEqual(registered, set(self.EXPECTED))


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


ISSUES_SAMPLE = """\
backlog:
- key: BL-E001-001
  epic: '001'
  sprint: '01'
  title: Existing issue
  source: adversarial (ADV-L-01)
  severity: Low
  status: backlog
"""

class TestAppendIssue(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.f = os.path.join(self.d, "sprint-status-issues.yaml")

    def run_main(self, argv):
        buf = io.StringIO()
        code = 0
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, buf.getvalue()

    def test_creates_file_if_absent(self):
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--key", "BL-E001-001", "--epic", "001",
                                   "--sprint", "01", "--title", "Rate limit",
                                   "--source", "adversarial (ADV-L-01)", "--severity", "Low"])
        self.assertEqual(code, 0, out)
        y, data = pm.core._load(self.f)
        self.assertEqual(len(data["backlog"]), 1)
        self.assertEqual(data["backlog"][0]["key"], "BL-E001-001")

    def test_appends_to_existing_list(self):
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(ISSUES_SAMPLE)
        self.run_main(["append-issue", "--file", self.f,
                       "--key", "BL-E001-002", "--epic", "001",
                       "--sprint", "", "--title", "New issue",
                       "--source", "red-team (RT-M-01)", "--severity", "Medium"])
        y, data = pm.core._load(self.f)
        self.assertEqual(len(data["backlog"]), 2)
        self.assertEqual(data["backlog"][1]["key"], "BL-E001-002")

    def _append(self, *extra):
        return self.run_main(["append-issue", "--file", self.f, "--epic", "001",
                              "--sprint", "01", "--title", "T", "--severity", "Low", *extra])

    def _item(self):
        return pm.core._load(self.f)[1]["backlog"][-1]

    # -- structured source ------------------------------------------------------------- #

    def test_structured_source_derives_the_stored_string(self):
        code, out = self._append("--source-phase", "code-review",
                                 "--source-ref", "E001-S01-005")
        self.assertEqual(code, 0, out)
        it = self._item()
        self.assertEqual(it["source"], "code-review (E001-S01-005)")
        self.assertEqual(it["source_phase"], "code-review")
        self.assertEqual(it["source_ref"], "E001-S01-005")

    def test_a_note_is_appended_after_the_parens(self):
        self._append("--source-phase", "code-review", "--source-ref", "E001-S01-005",
                     "--source-note", "unresolved after 3 fix iterations")
        it = self._item()
        self.assertEqual(it["source"],
                         "code-review (E001-S01-005) — unresolved after 3 fix iterations")
        self.assertEqual(it["source_ref"], "E001-S01-005")

    def test_a_free_text_source_stores_no_structured_fields(self):
        """Absence is what marks a legacy item, so it must stay absent."""
        self._append("--source", "hand-written note")
        it = self._item()
        self.assertEqual(it["source"], "hand-written note")
        self.assertNotIn("source_phase", it)
        self.assertNotIn("source_ref", it)

    def test_source_and_source_phase_together_are_refused(self):
        code, _ = self._append("--source", "x (y)", "--source-phase", "code-review",
                               "--source-ref", "E001-S01-005")
        self.assertEqual(code, 2)

    def test_neither_source_nor_source_phase_is_refused(self):
        self.assertEqual(self._append()[0], 2)

    def test_source_phase_without_a_ref_is_refused(self):
        self.assertEqual(self._append("--source-phase", "code-review")[0], 2)

    def test_a_note_without_a_phase_is_refused(self):
        self.assertEqual(self._append("--source", "x (y)", "--source-note", "n")[0], 2)

    def test_a_phase_with_a_space_is_refused(self):
        """The derived string must parse as `{phase} ({ref})`; a space breaks that."""
        self.assertEqual(self._append("--source-phase", "closure review",
                                      "--source-ref", "E001-S01")[0], 2)

    def test_a_ref_containing_parens_is_refused(self):
        self.assertEqual(self._append("--source-phase", "code-review",
                                      "--source-ref", "E001 (S01)")[0], 2)

    def test_every_derived_source_parses_as_phase_and_ref(self):
        """The invariant the validation exists to buy: what this writes, the readers read."""
        import re
        phase_re = re.compile(r"^([A-Za-z][\w-]*) \(([^()]+)\)")
        for phase, ref, note in [("code-review", "E001-S01-005", None),
                                 ("arch-gate", "l3io-arch-review", None),
                                 ("epic-redteam", "F-3", "and a trailing clause"),
                                 ("x", "y", None)]:
            with self.subTest(phase=phase):
                argv = ["--source-phase", phase, "--source-ref", ref]
                if note:
                    argv += ["--source-note", note]
                self.assertEqual(self._append(*argv)[0], 0)
                m = phase_re.match(self._item()["source"])
                self.assertIsNotNone(m, self._item()["source"])
                self.assertEqual((m.group(1), m.group(2)), (phase, ref))

    def test_dedupe_still_matches_a_structured_re_run(self):
        """_content_matches compares the exact source string; deriving it must not break that."""
        self._append("--source-phase", "code-review", "--source-ref", "E001-S01-005")
        n1 = len(pm.core._load(self.f)[1]["backlog"])
        code, out = self._append("--source-phase", "code-review", "--source-ref", "E001-S01-005")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(pm.core._load(self.f)[1]["backlog"]), n1,
                         "a structured re-run must be recognised as the same item")

    def test_invalid_severity_rejected(self):

        code, _ = self.run_main(["append-issue", "--file", self.f,
                                  "--key", "BL-E001-003", "--epic", "001",
                                  "--sprint", "", "--title", "T",
                                  "--source", "S", "--severity", "Trivial"])
        self.assertEqual(code, 2)

    # --- D1: key is now optional and self-allocating --------------------- #

    def test_key_is_optional(self):
        """--key is no longer required — nothing in any step file ever bound {nnn},
        so the caller must be able to omit it entirely."""
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--epic", "001", "--title", "Rate limit",
                                   "--source", "adversarial (ADV-L-01)", "--severity", "Low"])
        self.assertEqual(code, 0, out)

    def test_allocates_001_from_empty_backlog(self):
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--epic", "001", "--title", "First finding",
                                   "--source", "qa", "--severity", "Low"])
        self.assertEqual(code, 0, out)
        y, data = pm.core._load(self.f)
        self.assertEqual(data["backlog"][0]["key"], "BL-E001-001")
        self.assertIn("BL-E001-001", out)

    def test_allocates_next_after_highest_existing(self):
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write("backlog:\n"
                     "- key: BL-E001-007\n  epic: '001'\n  sprint: ''\n"
                     "  title: Prior\n  source: qa\n  severity: Low\n  status: backlog\n")
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--epic", "001", "--title", "Next finding",
                                   "--source", "qa", "--severity", "Low"])
        self.assertEqual(code, 0, out)
        y, data = pm.core._load(self.f)
        self.assertEqual(data["backlog"][-1]["key"], "BL-E001-008")

    def test_allocation_is_per_epic(self):
        self.run_main(["append-issue", "--file", self.f,
                       "--epic", "001", "--title", "E1 finding A",
                       "--source", "qa", "--severity", "Low"])
        self.run_main(["append-issue", "--file", self.f,
                       "--epic", "002", "--title", "E2 finding A",
                       "--source", "qa", "--severity", "Low"])
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--epic", "001", "--title", "E1 finding B",
                                   "--source", "qa", "--severity", "Low"])
        self.assertEqual(code, 0, out)
        y, data = pm.core._load(self.f)
        keys = [i["key"] for i in data["backlog"]]
        self.assertEqual(keys, ["BL-E001-001", "BL-E002-001", "BL-E001-002"])

    def test_allocation_ignores_malformed_existing_keys(self):
        """issues.yaml is hand-editable — a garbage key must not crash allocation."""
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write("backlog:\n"
                     "- key: BL-EXXX-yy\n  epic: '001'\n  sprint: ''\n"
                     "  title: Garbage\n  source: qa\n  severity: Low\n  status: backlog\n"
                     "- not-a-mapping-just-a-string\n"
                     "- key: BL-E001-003\n  epic: '001'\n  sprint: ''\n"
                     "  title: Valid\n  source: qa\n  severity: Low\n  status: backlog\n")
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--epic", "001", "--title", "Next finding",
                                   "--source", "qa", "--severity", "Low"])
        self.assertEqual(code, 0, out)
        y, data = pm.core._load(self.f)
        self.assertEqual(data["backlog"][-1]["key"], "BL-E001-004")

    # --- D2: explicit-key collision and content-duplicate detection ------ #

    def test_explicit_duplicate_key_exits_2(self):
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(ISSUES_SAMPLE)
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--key", "BL-E001-001", "--epic", "001",
                                   "--sprint", "01", "--title", "A different finding",
                                   "--source", "qa", "--severity", "Low"])
        self.assertEqual(code, 2)
        y, data = pm.core._load(self.f)
        self.assertEqual(len(data["backlog"]), 1, "the duplicate must not be appended")

    def test_explicit_duplicate_key_message_on_stderr(self):
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(ISSUES_SAMPLE)
        buf_out, buf_err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(buf_out), redirect_stderr(buf_err):
                code = pm.main(["append-issue", "--file", self.f,
                               "--key", "BL-E001-001", "--epic", "001",
                               "--sprint", "01", "--title", "A different finding",
                               "--source", "qa", "--severity", "Low"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 2)
        self.assertIn("Existing issue", buf_err.getvalue())
        y, data = pm.core._load(self.f)
        self.assertEqual(len(data["backlog"]), 1)

    def test_content_duplicate_is_skipped_exits_0(self):
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(ISSUES_SAMPLE)
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--epic", "001", "--sprint", "01",
                                   "--title", "  Existing   issue  ",
                                   "--source", "adversarial (ADV-L-01)", "--severity", "Low"])
        self.assertEqual(code, 0, out)
        self.assertIn("BL-E001-001", out)
        y, data = pm.core._load(self.f)
        self.assertEqual(len(data["backlog"]), 1, "no second row should be written")

    def test_content_duplicate_requires_all_four_fields(self):
        """A different source is NOT a duplicate — under-matching would lose findings."""
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(ISSUES_SAMPLE)
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--epic", "001", "--sprint", "01",
                                   "--title", "Existing issue",
                                   "--source", "red-team (RT-L-02)", "--severity", "Low"])
        self.assertEqual(code, 0, out)
        y, data = pm.core._load(self.f)
        self.assertEqual(len(data["backlog"]), 2, "different source is a distinct finding")

    def test_allow_duplicate_forces_append(self):
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(ISSUES_SAMPLE)
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--epic", "001", "--sprint", "01",
                                   "--title", "Existing issue",
                                   "--source", "adversarial (ADV-L-01)", "--severity", "Low",
                                   "--allow-duplicate"])
        self.assertEqual(code, 0, out)
        y, data = pm.core._load(self.f)
        self.assertEqual(len(data["backlog"]), 2)

    # --- D3: malformed 'backlog' field is refused, not silently repaired - #

    def _assert_malformed_backlog_refused(self, backlog_yaml_line):
        """Shared body for the {} and 'text' malformed-backlog cases: exit 2,
        a clear stderr message, and the file byte-for-byte unmodified -- a
        `backlog` that cannot say what is already recorded cannot be trusted
        to receive a new item without hiding whatever was there, mirroring
        cmd_adr_reserve's malformed-'reserved' guard."""
        content = backlog_yaml_line
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(content)
        buf_err = io.StringIO()
        try:
            with redirect_stderr(buf_err):
                code = pm.main(["append-issue", "--file", self.f,
                                "--epic", "001", "--title", "Next finding",
                                "--source", "qa", "--severity", "Low"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 2)
        err = buf_err.getvalue()
        self.assertIn("backlog", err)
        self.assertIn("malformed", err)
        with open(self.f, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), content, "file must be left unmodified on refusal")

    def test_malformed_backlog_dict_is_refused_not_silently_repaired(self):
        self._assert_malformed_backlog_refused("backlog: {}\n")

    def test_malformed_backlog_string_is_refused_not_silently_repaired(self):
        self._assert_malformed_backlog_refused("backlog: text\n")


ISSUES_FIXTURE = """\
backlog:
- key: BL-E001-001
  epic: '001'
  sprint: '01'
  title: Sprint-level issue
  source: qa
  severity: Low
  status: backlog
- key: BL-E001-002
  epic: '001'
  sprint: ''
  title: Epic-level issue
  source: arch-review
  severity: High
  status: backlog
- key: BL-E002-001
  epic: '002'
  sprint: '01'
  title: Other-epic issue
  source: red-team
  severity: Medium
  status: backlog
- key: BL-E000-001
  epic: '000'
  sprint: ''
  title: Repo-global issue
  source: adversarial
  severity: Critical
  status: backlog
"""



def _build_issue_tree(root):
    """State tree for issue-lifecycle tests. Epic/sprint nodes are hand-written
    because no verb creates them; every ISSUE is created through the real CLI.
      active/epic-001: S01 in-progress, S02 backlog
      planned/epic-005: S01 backlog
    """
    nodes = {
        "active/epic-001/epic.yaml": "key: 'E001'\ntitle: 'Foundation'\nstatus: in-progress\n",
        "active/epic-001/sprint-01/sprint.yaml":
            "key: 'S01'\nepic: 'E001'\ntitle: 'One'\nstatus: in-progress\n",
        "active/epic-001/sprint-02/sprint.yaml":
            "key: 'S02'\nepic: 'E001'\ntitle: 'Two'\nstatus: backlog\n",
        "planned/epic-005/epic.yaml": "key: 'E005'\ntitle: 'Later'\nstatus: backlog\n",
        "planned/epic-005/sprint-01/sprint.yaml":
            "key: 'S01'\nepic: 'E005'\ntitle: 'Later one'\nstatus: backlog\n",
    }
    for rel, text in nodes.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)


class IssueBase(Base):
    """impl/ is the artifacts root; impl/state the state root."""

    def setUp(self):
        super().setUp()
        self.arts = os.path.join(self.d, "impl")
        self.root = os.path.join(self.arts, "state")
        _build_issue_tree(self.root)
        self.issues = os.path.join(self.root, "issues.yaml")
        self.resolved = os.path.join(self.root, "issues-resolved.yaml")

    def run_all(self, argv):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue(), err.getvalue()

    def finish(self, story="E001-S02-001", key="BL-E001-001"):
        """Mark a story done and resolve the item it lists as fixed by it: the state a
        completed story and its resolved item are in."""
        _fx_set_status(self.root, "done", story=story)
        code, _o, err = self.run_all(["resolve-issue", "--state-root", self.root, "--key", key,
                                      "--resolution", "fixed", "--ref", story])
        self.assertEqual(code, 0, err)

    def append(self, title, epic="001", sprint="01", severity="Low",
               source="code-review (E001-S01-001)", *extra):
        return self.run_all(["append-issue", "--state-root", self.root, "--epic", epic,
                             "--sprint", sprint, "--title", title, "--source", source,
                             "--severity", severity, *extra])

    def load_open(self):
        return pm.core._load(self.issues)[1] or {}

    def load_resolved(self):
        return pm.core._load(self.resolved)[1] or {}

    def open_keys(self):
        return [str(i["key"]) for i in (self.load_open().get("backlog") or [])]

    def resolved_keys(self):
        return [str(i["key"]) for i in (self.load_resolved().get("resolved") or [])]

    def events(self, name=None):
        p = pm.events_path(self.root)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as fh:
            evs = [json.loads(l) for l in fh if l.strip()]
        return [e for e in evs if name is None or e.get("event") == name]

    def assert_invariants(self):
        """Spec §1.4 invariants 1, 5 and 6, read from the issue files as written. Call it after
        an operation that should leave a valid state -- never in a test that builds an invalid
        one on purpose. Invariant 1's key set is both files plus every key an `issue_opened`
        event recorded, so a key that vanished from both files fails as well as one in both.
        Invariant 6 uses the spec's own form, not pm-status's canonical_bl_key."""
        files = {"issues.yaml": self.open_keys(), "issues-resolved.yaml": self.resolved_keys()}
        for name, keys in files.items():
            twice = sorted({k for k in keys if keys.count(k) > 1})
            self.assertEqual(twice, [], f"invariant 5: a key appears twice in {name}")
            bad = [k for k in keys if not re.fullmatch(r"BL-E[0-9]{3}-[0-9]{3}", k)]
            self.assertEqual(bad, [], f"invariant 6: a non-canonical key in {name}")
        opened = set()
        if os.path.isfile(pm.events_path(self.root)):
            opened = {str(e["key"]) for e in self.events("issue_opened")}
        o, r = set(files["issues.yaml"]), set(files["issues-resolved.yaml"])
        wrong = sorted(k for k in o | r | opened if (k in o) == (k in r))
        self.assertEqual(wrong, [], "invariant 1: a key is in both issue files, or in neither")

    def _crash_promote_before_scheduling(self, key="BL-E001-001", epic="001", sprint="02",
                                         cls="standard", extra=()):
        """Run promote-issue with the scheduling save failing: the story node and document are
        written, the item is not yet scheduled -- the state audit-issues finding 1d describes."""
        with mock.patch.object(pm.IssueStore, "save_open", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    pm.main(["promote-issue", "--state-root", self.root, "--artifacts-root",
                             self.arts, "--key", key, "--epic", epic, "--sprint", sprint,
                             "--classification", cls, *extra])


class TestIssueAllocator(IssueBase):
    def test_hand_deleted_highest_key_is_never_reused(self):
        """The reproduced defect: after the newest item is deleted by hand, the old
        allocator ('highest surviving + 1') gave its key to an unrelated finding."""
        for t in ("A first", "B second", "C third"):
            self.assertEqual(self.append(t)[0], 0)
        y, data = pm.core._load(self.issues)
        data["backlog"] = [i for i in data["backlog"] if i["key"] != "BL-E001-003"]
        pm.core._atomic_dump(y, data, self.issues)
        code, out, err = self.append("D unrelated")
        self.assertEqual(code, 0, err)
        self.assertIn("BL-E001-004", out)
        self.assertNotIn("BL-E001-003", self.open_keys())

    def test_next_is_written_per_epic(self):
        self.append("A")
        self.append("B")
        self.append("C", epic="005", sprint="01", source="qa (Q-1)")
        nxt = self.load_open()["next"]
        self.assertEqual(int(nxt["001"]), 3)
        self.assertEqual(int(nxt["005"]), 2)

    def test_seeds_from_highest_suffix_in_both_files(self):
        for t in ("A", "B", "C", "D", "E"):
            self.append(t)
        y, data = pm.core._load(self.issues)
        del data["next"]
        pm.core._atomic_dump(y, data, self.issues)
        # a pre-existing resolved record that predates `next` (deliberately hand-built)
        with open(self.resolved, "w", encoding="utf-8") as fh:
            fh.write("resolved:\n- key: BL-E001-007\n  epic: '001'\n  title: old\n"
                     "  resolution: fixed\n")
        code, out, err = self.append("F")
        self.assertEqual(code, 0, err)
        self.assertIn("BL-E001-008", out)

    def test_hand_written_item_beyond_stale_next(self):
        self.append("A")
        y, data = pm.core._load(self.issues)
        from ruamel.yaml.comments import CommentedMap
        data["backlog"].append(CommentedMap([("key", "BL-E001-009"), ("epic", "001"),
                                             ("title", "hand"), ("status", "backlog")]))
        pm.core._atomic_dump(y, data, self.issues)
        self.assertIn("BL-E001-010", self.append("B")[1])

    def test_malformed_next_warns_and_never_goes_backwards(self):
        self.append("A")
        self.append("B")
        y, data = pm.core._load(self.issues)
        data["next"] = "garbage"
        pm.core._atomic_dump(y, data, self.issues)
        code, out, err = self.append("C")
        self.assertEqual(code, 0, err)
        self.assertIn("warning", err)
        self.assertIn("BL-E001-003", out)

    def test_explicit_key_is_canonicalized_and_raises_next(self):
        code, out, err = self.append("A", "001", "01", "Low", "qa", "--key", "BL-E1-5")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.open_keys(), ["BL-E001-005"])
        self.assertIn("BL-E001-006", self.append("B")[1])

    def test_explicit_key_epic_must_match(self):
        code, _, err = self.append("A", "001", "01", "Low", "qa", "--key", "BL-E002-001")
        self.assertEqual(code, 2)
        self.assertIn("epic", err)
        self.assertFalse(os.path.exists(self.issues))

    def test_explicit_key_that_cannot_be_canonical_is_refused(self):
        for bad in ("not-a-key", "BL-E1000-1", "BL-E001-000"):
            self.assertEqual(self.append("A", "001", "01", "Low", "qa", "--key", bad)[0], 2, bad)

    def test_explicit_key_present_in_resolved_file_is_refused(self):
        with open(self.resolved, "w", encoding="utf-8") as fh:
            fh.write("resolved:\n- key: BL-E001-004\n  epic: '001'\n  title: old\n"
                     "  resolution: fixed\n")
        code, _, err = self.append("A", "001", "01", "Low", "qa", "--key", "BL-E001-004")
        self.assertEqual(code, 2)
        self.assertIn("already exists", err)

    def test_state_root_with_mismatched_file_is_refused(self):
        code, _, err = self.run_all(["append-issue", "--state-root", self.root,
                                     "--file", os.path.join(self.d, "other.yaml"),
                                     "--epic", "001", "--title", "A", "--source", "qa",
                                     "--severity", "Low"])
        self.assertEqual(code, 2, err)

    def test_file_only_is_still_accepted(self):
        code, out, err = self.run_all(["append-issue", "--file", self.issues, "--epic", "001",
                                       "--title", "A", "--source", "qa", "--severity", "Low"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.open_keys(), ["BL-E001-001"])

    def test_neither_file_nor_state_root_is_refused(self):
        code, _, _ = self.run_all(["append-issue", "--epic", "001", "--title", "A",
                                   "--source", "qa", "--severity", "Low"])
        self.assertEqual(code, 2)

    def test_append_writes_issue_opened_event(self):
        self.append("A", "001", "01", "Medium", "qa", "--session-id", "S-1")
        ev = self.events("issue_opened")
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["key"], "BL-E001-001")
        self.assertEqual(ev[0]["session"], "S-1")
        self.assertEqual(ev[0]["cause"], "cli")
        self.assertEqual(ev[0]["severity"], "Medium")
        self.assertIn("ts", ev[0])

    def test_allocation_refuses_past_999(self):
        """A key has three digits: allocating BL-E001-1000 would mint a non-canonical key."""
        self.assertEqual(self.append("A", "001", "01", "Low", "qa", "--key", "BL-E001-999")[0], 0)
        before = _tree_snapshot(self.root)
        code, out, err = self.append("B")
        self.assertEqual(code, 2, out)
        self.assertIn("BL-E001-999", err)
        self.assertEqual(_tree_snapshot(self.root), before)


def _dump_failing_on(n):
    """Patch pm.core._atomic_dump so its n-th call raises OSError('injected') -- a crash
    between two writes. Use: `with _dump_failing_on(2): ...`. Shared by every
    crash-injection test so the injection logic exists once."""
    real, calls = pm.core._atomic_dump, {"n": 0}

    def flaky(y, data, path):
        calls["n"] += 1
        if calls["n"] == n:
            raise OSError("injected")
        return real(y, data, path)

    return mock.patch.object(pm.core, "_atomic_dump", flaky)


class TestResolveIssue(IssueBase):
    def resolve(self, key, resolution, *extra):
        return self.run_all(["resolve-issue", "--state-root", self.root, "--key", key,
                             "--resolution", resolution, *extra])

    def _promote(self, key="BL-E001-001", epic="001", sprint="02"):
        code, _o, err = self.run_all(["promote-issue", "--state-root", self.root,
                                      "--artifacts-root", self.arts, "--key", key,
                                      "--epic", epic, "--sprint", sprint,
                                      "--classification", "simple"])
        self.assertEqual(code, 0, err)

    def test_resolve_moves_the_item_whole(self):
        self.append("A", "001", "01", "Medium")
        code, out, err = self.resolve("BL-E001-001", "wontfix", "--note", "accepted risk")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.open_keys(), [])
        self.assertEqual(self.resolved_keys(), ["BL-E001-001"])
        entry = self.load_resolved()["resolved"][0]
        self.assertEqual(entry["status"], "resolved")
        self.assertEqual(entry["resolution"], "wontfix")
        self.assertEqual(entry["note"], "accepted risk")
        self.assertEqual(entry["severity"], "Medium")
        self.assertTrue(entry["resolved_at"])
        self.assert_invariants()

    def test_resolving_the_highest_then_appending_never_reuses(self):
        for t in ("A", "B", "C"):
            self.append(t)
        self.assertEqual(self.resolve("BL-E001-003", "obsolete", "--note", "gone")[0], 0)
        self.assertIn("BL-E001-004", self.append("D")[1])
        self.assert_invariants()

    def test_required_flags_refuse_and_write_nothing(self):
        self.append("A")
        with open(self.issues, encoding="utf-8") as fh:
            before = fh.read()
        for argv in (("fixed",), ("wontfix",), ("obsolete",), ("duplicate",),
                     ("fixed", "--ref", "later")):
            code, _, _ = self.resolve("BL-E001-001", *argv)
            self.assertEqual(code, 2, argv)
        with open(self.issues, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)
        self.assertFalse(os.path.exists(self.resolved))

    def test_fixed_ref_accepts_story_key_or_sha(self):
        self.append("A")
        self.append("B", "001", "02")
        self.assertEqual(self.resolve("BL-E001-001", "fixed", "--ref", "E001-S01-001")[0], 0)
        self.assertEqual(self.resolve("BL-E001-002", "fixed", "--ref", "abc1234")[0], 0)
        self.assert_invariants()

    def test_duplicate_ref_rules_forbid_chains(self):
        self.append("A")
        self.append("B", "001", "02")
        self.append("C", "001", "03")
        self.assertEqual(self.resolve("BL-E001-002", "duplicate", "--ref", "BL-E001-002")[0], 2)
        self.assertEqual(self.resolve("BL-E001-002", "duplicate", "--ref", "BL-E001-099")[0], 2)
        self.assertEqual(self.resolve("BL-E001-002", "duplicate", "--ref", "BL-E001-001")[0], 0)
        # B is now a resolved duplicate: C may not point at it
        self.assertEqual(self.resolve("BL-E001-003", "duplicate", "--ref", "BL-E001-002")[0], 2)
        self.assert_invariants()

    def test_rerun_is_idempotent(self):
        self.append("A")
        self.resolve("BL-E001-001", "obsolete", "--note", "gone")
        code, out, _ = self.resolve("BL-E001-001", "obsolete", "--note", "gone")
        self.assertEqual(code, 0)
        self.assertIn("already resolved", out)
        self.assertEqual(self.resolved_keys(), ["BL-E001-001"])
        self.assert_invariants()

    def test_unknown_key_exits_3(self):
        self.assertEqual(self.resolve("BL-E001-042", "obsolete", "--note", "x")[0], 3)

    def test_a_key_that_is_not_a_backlog_key_exits_2_not_3(self):
        """Two different answers that both mean "no such item": exit 3 is a well-formed key
        naming nothing, exit 2 is a string that is not a key at all. A caller that treats
        them alike retries a typo as though the item might appear later."""
        code, _o, err = self.resolve("NOT-A-KEY", "obsolete", "--note", "x")
        self.assertEqual(code, 2)
        self.assertIn("is not a backlog key", err)
        self.assertFalse(os.path.exists(self.resolved), "nothing written")

    def test_resolving_a_scheduled_item_by_hand_warns_that_the_story_still_claims_it(self):
        """The story's `resolves:` is not touched here, so the item is resolved while a story
        still lists it — audit finding 1c. The tail says so, and only outside the done-hook
        path, where that state is expected and transient."""
        self.append("A")
        self._promote()
        code, out, _e = self.resolve("BL-E001-001", "obsolete", "--note", "changed my mind")
        self.assertEqual(code, 0)
        self.assertIn("E001-S02-001 still lists it in resolves", out)

    def test_crash_between_writes_is_cleared_by_rerun(self):
        self.append("A")
        with _dump_failing_on(2), self.assertRaises(OSError):
            pm.main(["resolve-issue", "--state-root", self.root, "--key", "BL-E001-001",
                     "--resolution", "obsolete", "--note", "gone"])
        self.assertEqual(self.open_keys(), ["BL-E001-001"])      # premise: both files
        self.assertEqual(self.resolved_keys(), ["BL-E001-001"])
        code, out, _ = self.resolve("BL-E001-001", "obsolete", "--note", "gone")
        self.assertEqual(code, 0)
        self.assertIn("removed the stale open copy", out)
        self.assertEqual(self.open_keys(), [])
        self.assertEqual(self.resolved_keys(), ["BL-E001-001"])
        self.assert_invariants()

    def test_key_duplicated_in_open_file_is_refused(self):
        self.append("A")
        y, data = pm.core._load(self.issues)
        from ruamel.yaml.comments import CommentedMap
        data["backlog"].append(CommentedMap(data["backlog"][0]))
        pm.core._atomic_dump(y, data, self.issues)
        code, _, err = self.resolve("BL-E001-001", "obsolete", "--note", "x")
        self.assertEqual(code, 2)
        self.assertIn("1i", err)

    def test_malformed_resolved_list_is_refused(self):
        self.append("A")
        with open(self.resolved, "w", encoding="utf-8") as fh:
            fh.write("resolved: oops\n")
        self.assertEqual(self.resolve("BL-E001-001", "obsolete", "--note", "x")[0], 2)
        self.assertEqual(self.open_keys(), ["BL-E001-001"])

    def test_event_carries_resolution_and_cause(self):
        self.append("A")
        self.resolve("BL-E001-001", "fixed", "--ref", "abc1234", "--session-id", "S-9",
                     "--cause", "triage")
        ev = self.events("issue_resolved")[-1]
        self.assertEqual((ev["resolution"], ev["ref"], ev["session"], ev["cause"]),
                         ("fixed", "abc1234", "S-9", "triage"))
        self.assert_invariants()


class TestConcurrentResolveAppend(unittest.TestCase):
    """Real subprocesses: _file_lock's re-entrancy counter is per process, so
    threads would pass vacuously with the lock removed."""
    N = 6

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        _build_issue_tree(self.root)
        with redirect_stdout(io.StringIO()):
            for i in range(1, self.N + 1):
                self.assertEqual(pm.main(["append-issue", "--state-root", self.root, "--epic",
                                          "001", "--title", f"seed {i}", "--source", "qa",
                                          "--severity", "Low"]), 0)

    def test_parallel_resolves_and_appends_lose_nothing(self):
        import subprocess
        procs = [subprocess.Popen([sys.executable, SCRIPT, "resolve-issue", "--state-root",
                                   self.root, "--key", f"BL-E001-{i:03d}", "--resolution",
                                   "obsolete", "--note", "x"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(1, self.N + 1)]
        procs += [subprocess.Popen([sys.executable, SCRIPT, "append-issue", "--state-root",
                                    self.root, "--epic", "001", "--title", f"new {i}",
                                    "--source", "qa", "--severity", "Low"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                  for i in range(1, self.N + 1)]
        for p in procs:
            _, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err.decode())
        _, o = pm.core._load(os.path.join(self.root, "issues.yaml"))
        _, r = pm.core._load(os.path.join(self.root, "issues-resolved.yaml"))
        open_keys = [str(i["key"]) for i in o["backlog"]]
        res_keys = [str(i["key"]) for i in r["resolved"]]
        self.assertEqual(sorted(res_keys), [f"BL-E001-{i:03d}" for i in range(1, self.N + 1)])
        self.assertEqual(len(open_keys), self.N)
        self.assertEqual(len(set(open_keys)), self.N, "a key was allocated twice")
        self.assertFalse(set(open_keys) & set(res_keys), "a key is in both files")


class TestAppendDedupeResolved(IssueBase):
    def resolve(self, key, *argv):
        code, _, err = self.run_all(["resolve-issue", "--state-root", self.root,
                                     "--key", key, *argv])
        self.assertEqual(code, 0, err)

    # Spec §2.1: the severity rule covers all three non-fixed resolutions, not wontfix alone.
    # duplicate needs --ref naming another key (the open "Survivor", appended first as
    # BL-E001-001); wontfix and obsolete need --note.
    NON_FIXED = {"wontfix": ("--note", "risk accepted"),
                 "duplicate": ("--ref", "BL-E001-001"),
                 "obsolete": ("--note", "gone")}

    def _append_key(self, title, severity):
        code, out, err = self.append(title, "001", "01", severity)
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("OK append-issue BL-E001-"), out)
        return out.split()[2]

    def test_non_fixed_resolution_same_or_lower_severity_is_skipped(self):
        self.assertEqual(self._append_key("Survivor", "Low"), "BL-E001-001")
        for res, flags in self.NON_FIXED.items():
            with self.subTest(resolution=res):
                key = self._append_key(f"A {res}", "Medium")
                self.resolve(key, "--resolution", res, *flags)
                for sev in ("Medium", "Low"):
                    code, out, _ = self.append(f"A {res}", "001", "01", sev)
                    self.assertEqual(code, 0)
                    self.assertIn(f"skipped -- matches {key} resolved as {res} (severity Medium)",
                                  out)
        self.assertEqual(self.open_keys(), ["BL-E001-001"])

    def test_higher_severity_than_a_non_fixed_resolution_is_appended_as_reraised(self):
        self.assertEqual(self._append_key("Survivor", "Low"), "BL-E001-001")
        for res, flags in self.NON_FIXED.items():
            with self.subTest(resolution=res):
                key = self._append_key(f"A {res}", "Low")
                self.resolve(key, "--resolution", res, *flags)
                code, out, _ = self.append(f"A {res}", "001", "01", "High")
                self.assertEqual(code, 0)
                self.assertIn(f"(re-raised above {key} {res} at Low)", out)
                self.assertIn(out.split()[2], self.open_keys())

    def test_fixed_match_is_a_recurrence(self):
        self.append("A")
        self.resolve("BL-E001-001", "--resolution", "fixed", "--ref", "E001-S01-001")
        code, out, _ = self.append("A")
        self.assertIn("recurrence of BL-E001-001", out)
        self.assertEqual(self.open_keys(), ["BL-E001-002"])

    def test_newest_resolved_match_decides(self):
        self.append("A")
        self.resolve("BL-E001-001", "--resolution", "fixed", "--ref", "E001-S01-001")
        self.append("A")                                     # recurrence -> 002
        self.resolve("BL-E001-002", "--resolution", "wontfix", "--note", "stop")
        code, out, _ = self.append("A")
        self.assertIn("skipped", out)
        self.assertIn("BL-E001-002", out)

    def test_allow_duplicate_bypasses_resolved_match(self):
        self.append("A")
        self.resolve("BL-E001-001", "--resolution", "obsolete", "--note", "gone")
        self.append("A", "001", "01", "Low", "code-review (E001-S01-001)", "--allow-duplicate")
        self.assertEqual(self.open_keys(), ["BL-E001-002"])


class TestListIssues(unittest.TestCase):
    """list-issues reads state-root/issues.yaml; a missing file or a filter set
    matching nothing is success (exit 0), never an error."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.state_root = os.path.join(self.d, "state")
        os.makedirs(self.state_root, exist_ok=True)
        self.issues_file = os.path.join(self.state_root, "issues.yaml")

    def write_fixture(self):
        with open(self.issues_file, "w", encoding="utf-8") as fh:
            fh.write(ISSUES_FIXTURE)

    def run_main(self, argv):
        buf = io.StringIO()
        code = 0
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, buf.getvalue()

    def run_json(self, extra_args):
        import json
        code, out = self.run_main(["list-issues", "--state-root", self.state_root,
                                    "--format", "json"] + extra_args)
        self.assertEqual(code, 0, out)
        return json.loads(out)

    def test_no_filter_returns_everything(self):
        self.write_fixture()
        items = self.run_json([])
        self.assertEqual(len(items), 4)

    def test_epic_filter_matches_key_form(self):
        self.write_fixture()
        items = self.run_json(["--epic", "E001"])
        self.assertEqual({i["key"] for i in items}, {"BL-E001-001", "BL-E001-002"})

    def test_epic_filter_matches_zero_padded_number_form(self):
        self.write_fixture()
        items = self.run_json(["--epic", "001"])
        self.assertEqual({i["key"] for i in items}, {"BL-E001-001", "BL-E001-002"})

    def test_sprint_filter_excludes_epic_level_items(self):
        self.write_fixture()
        items = self.run_json(["--sprint", "S01"])
        self.assertEqual({i["key"] for i in items}, {"BL-E001-001", "BL-E002-001"})
        keys = {i["key"] for i in items}
        self.assertNotIn("BL-E001-002", keys)
        self.assertNotIn("BL-E000-001", keys)

    def test_sprint_filter_matches_unpadded_number_form(self):
        self.write_fixture()
        items = self.run_json(["--sprint", "1"])
        self.assertEqual({i["key"] for i in items}, {"BL-E001-001", "BL-E002-001"})

    def test_severity_filter(self):
        self.write_fixture()
        items = self.run_json(["--severity", "High"])
        self.assertEqual({i["key"] for i in items}, {"BL-E001-002"})

    def test_severity_filter_repeated_ors_values(self):
        self.write_fixture()
        items = self.run_json(["--severity", "Low", "--severity", "High"])
        self.assertEqual({i["key"] for i in items}, {"BL-E001-001", "BL-E001-002"})

    def test_combined_filters_and(self):
        self.write_fixture()
        items = self.run_json(["--epic", "001", "--severity", "Low"])
        self.assertEqual({i["key"] for i in items}, {"BL-E001-001"})

    def test_epic_and_sprint_combined_and(self):
        self.write_fixture()
        items = self.run_json(["--epic", "001", "--sprint", "01"])
        self.assertEqual({i["key"] for i in items}, {"BL-E001-001"})

    def test_missing_file_exits_0_with_empty_json(self):
        # no write_fixture() — issues.yaml does not exist
        items = self.run_json([])
        self.assertEqual(items, [])

    def test_missing_file_exits_0_with_empty_text(self):
        code, out = self.run_main(["list-issues", "--state-root", self.state_root])
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", out)

    def test_text_format_is_readable_table(self):
        self.write_fixture()
        code, out = self.run_main(["list-issues", "--state-root", self.state_root])
        self.assertEqual(code, 0)
        self.assertIn("BL-E001-001", out)
        self.assertIn("KEY", out)

    def test_format_json_emits_valid_parseable_json(self):
        self.write_fixture()
        items = self.run_json(["--epic", "E002"])
        self.assertIsInstance(items, list)
        self.assertEqual(items[0]["key"], "BL-E002-001")
        self.assertEqual(items[0]["severity"], "Medium")


class TestLayoutResolution(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        # active/epic-001/sprint-01/{sprint.yaml,E001-S01-003.yaml} + epic.yaml
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        os.makedirs(sd)
        with open(os.path.join(self.root, "active", "epic-001", "epic.yaml"), "w") as f:
            f.write("key: 'E001'\nstatus: in-progress\n")
        with open(os.path.join(sd, "sprint.yaml"), "w") as f:
            f.write("key: 'S01'\nepic: 'E001'\nstatus: in-progress\n")
        with open(os.path.join(sd, "E001-S01-003.yaml"), "w") as f:
            f.write("key: 'E001-S01-003'\nepic: 'E001'\nsprint: 'S01'\nstatus: review\n")
        # a planned epic, to prove the folder search spans all three
        os.makedirs(os.path.join(self.root, "planned", "epic-005"))
        with open(os.path.join(self.root, "planned", "epic-005", "epic.yaml"), "w") as f:
            f.write("key: 'E005'\nstatus: backlog\n")

    def test_dirname_conversions(self):
        self.assertEqual(pm.epic_dirname("E001"), "epic-001")
        self.assertEqual(pm.epic_dirname("E42"), "epic-042")
        self.assertEqual(pm.sprint_dirname("S01"), "sprint-01")
        self.assertEqual(pm.sprint_dirname("S7"), "sprint-07")

    def test_parse_story_key(self):
        self.assertEqual(pm.parse_story_key("E001-S01-003"), ("E001", "S01", "003"))

    def test_parse_story_key_rejects_malformed(self):
        with self.assertRaises(ValueError):
            pm.parse_story_key("not-a-key")

    def test_find_epic_dir_searches_all_status_folders(self):
        self.assertTrue(pm.find_epic_dir(self.root, "E001").endswith("active/epic-001"))
        self.assertTrue(pm.find_epic_dir(self.root, "E005").endswith("planned/epic-005"))
        self.assertIsNone(pm.find_epic_dir(self.root, "E999"))

    def test_node_file_resolution(self):
        self.assertTrue(pm.nodes.epic_file(self.root, "E001").endswith("active/epic-001/epic.yaml"))
        self.assertTrue(pm.sprint_file(self.root, "E001", "S01").endswith("sprint-01/sprint.yaml"))
        self.assertTrue(pm.story_file(self.root, "E001-S01-003").endswith("sprint-01/E001-S01-003.yaml"))
        self.assertIsNone(pm.story_file(self.root, "E001-S01-999"))

    def test_load_node_returns_bare_mapping(self):
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["key"], "E001-S01-003")
        self.assertNotIn("epics", node)

    def test_save_node_roundtrips(self):
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        pm.nodes.save_node(y, node, p)
        _, again = pm.load_node(p)
        self.assertEqual(again["status"], "done")

    def test_check_backrefs_detects_misplacement(self):
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(pm.check_backrefs(node, "E001", "S01"), [])
        self.assertTrue(pm.check_backrefs(node, "E002", "S01"))

    def test_check_backrefs_flags_absent_epic_backref(self):
        """A file with no `epic:` at all must FAIL, not pass. migrate-state adds these
        back-references as a brand-new step, so "absent" is precisely the case this
        check exists to catch — treating absent as OK made the migration's only
        automated gate blind to its own newest transformation."""
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nsprint: 'S01'\nstatus: review\n")
        _, node = pm.load_node(p)
        problems = pm.check_backrefs(node, "E001", "S01")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("epic back-reference absent", problems[0])

    def test_check_backrefs_flags_absent_sprint_backref(self):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nepic: 'E001'\nstatus: review\n")
        _, node = pm.load_node(p)
        problems = pm.check_backrefs(node, "E001", "S01")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("sprint back-reference absent", problems[0])

    def test_check_backrefs_flags_both_absent(self):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nstatus: review\n")
        _, node = pm.load_node(p)
        self.assertEqual(len(pm.check_backrefs(node, "E001", "S01")), 2)

    def test_check_backrefs_absent_sprint_on_sprint_node_is_not_checked(self):
        """Sprint nodes are checked with sprint_key=None (they have no `sprint:` of
        their own to verify), so only the `epic:` back-reference is required there."""
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
        self.assertEqual(pm.check_backrefs(node, "E001"), [])


class TestElapsedHoursUnification(TestLayoutResolution):
    """estimate-side time_hours and actual-side elapsed_hours are one name now —
    ESTIMATE_TO_ACTUAL is gone, and the deprecated --time-hours* CLI flags still
    write the elapsed_hours* destinations."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_estimate_writes_elapsed_hours_not_time_hours(self):
        code, out = self.run_main(["estimate-story", "--state-root", self.root,
                                   "--story", "E001-S01-003", "--classification", "standard"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertIn("elapsed_hours", node["estimate"])
        self.assertNotIn("time_hours", node["estimate"])

    def test_deprecated_time_hours_flag_still_writes_elapsed_hours(self):
        # set-estimate has no --node flag (unlike set-actual) — kind is inferred
        # from --story vs --epic[/--sprint]
        code, out = self.run_main(["set-estimate", "--state-root", self.root,
                                   "--story", "E001-S01-003",
                                   "--time-hours", "3"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(float(node["estimate"]["elapsed_hours"]), 3.0)
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
                code = pm.main(argv)
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
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        # complex band 0.3-1.0, midpoint 0.65, x cold-start scope 1.0 x fix 1.25
        self.assertAlmostEqual(float(node["estimate"]["hitl_hours"]), 0.81, places=2)

    def test_set_actual_accepts_hitl_hours(self):
        code, out = self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                                   "--story", "E001-S01-003", "--hitl-hours", "0.3",
                                   "--no-calibrate"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertAlmostEqual(float(node["actual"]["hitl_hours"]), 0.3, places=2)

    def test_set_actual_hitl_hours_produces_scope_sample(self):
        """A metric recorded on the node but never sampled can never calibrate.
        This drives the real CLI path (set-estimate then set-actual, calibration
        left ON) and reads pm-calibration.yaml back, so a regression that once
        again drops hitl_hours from derive_story_sample's metric loop fails
        here — asserting on the node alone would not have caught it."""
        code, out = self.run_main(["set-estimate", "--state-root", self.root,
                                   "--story", "E001-S01-003", "--hitl-hours", "0.5",
                                   "--fix-factor", "1.0"])
        self.assertEqual(code, 0, out)

        code, out = self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                                   "--story", "E001-S01-003", "--hitl-hours", "0.6",
                                   "--runtime", "other"])
        self.assertEqual(code, 0, out)

        _, cal = pm.load_calibration(self.root)
        # no classification was set on the fixture story -> derive_story_sample's
        # default bucket, "standard"
        samples = pm._component_samples(cal, "scope", "standard", "hitl_hours")
        self.assertEqual(len(samples), 1, cal)
        # fix_factor=1.0, no completion_evidence -> provenance "backout":
        # sample = actual x applied_ratio(1.0, none recorded) / estimate
        self.assertAlmostEqual(samples[0], 0.6 * 1.0 / 0.5, places=4)

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


class TestAtomicAndCLI(TestLayoutResolution):
    """Reuses TestLayoutResolution's tree fixture."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_no_temp_files_left(self):
        self.run_main(["set-estimate", "--state-root", self.root,
                       "--story", "E001-S01-003", "--man-hours", "2"])
        sd = os.path.dirname(pm.story_file(self.root, "E001-S01-003"))
        leftovers = [n for n in os.listdir(sd) if n.startswith(".pm-status.")]
        self.assertEqual(leftovers, [])


class TestKeyBasedAddressing(TestLayoutResolution):
    """Reuses TestLayoutResolution's tree fixture."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_missing_node_exits_3(self):
        code, _ = self.run_main(
            ["set-estimate", "--state-root", self.root, "--story", "E001-S01-999",
             "--man-hours", "1"])
        self.assertEqual(code, 3)

    def test_set_actual_writes_all_four_metrics(self):
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story", "--story", "E001-S01-003",
             "--elapsed-hours", "1.8", "--man-hours", "7", "--tokens-input", "300",
             "--tokens-output", "55", "--model", "claude-sonnet-5"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(int(node["actual"]["tokens_k"]["total"]), 355)
        self.assertEqual(node["actual"]["man_hours"], 7)

    def test_claude_runtime_still_rejects_na(self):
        code, _ = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story", "--story", "E001-S01-003",
             "--tokens-na", "--runtime", "claude"])
        self.assertEqual(code, 2)

    def test_set_estimate_story_uses_single_values(self):
        # --cost is not passed here: cost is derived from tokens x rates and
        # set-estimate rejects it outright (see TestEstimateTokensAndCost).
        code, out = self.run_main(
            ["set-estimate", "--state-root", self.root, "--story", "E001-S01-003",
             "--man-hours", "6", "--time-hours", "1.5", "--tokens-k", "320"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["estimate"]["man_hours"], 6.0)
        self.assertNotIn("man_hours_low", node["estimate"])
        self.assertNotIn("cost", node["estimate"])

    def test_backref_mismatch_exits_4(self):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nepic: 'E999'\nsprint: 'S01'\nstatus: review\n")
        code, _ = self.run_main(
            ["set-estimate", "--state-root", self.root, "--story", "E001-S01-003",
             "--man-hours", "1"])
        self.assertEqual(code, 4)


class TestStructuredActualTokens(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
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
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
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
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertTrue(pm._is_na(node["actual"]["tokens_k"]))
        self.assertTrue(pm._is_na(node["actual"]["cost"]))

    def test_tokens_na_forbidden_under_runtime_claude(self):
        code, out = self._set("--tokens-na", "--runtime", "claude")
        self.assertEqual(code, 2, out)


class TestVerify(TestLayoutResolution):
    """Reuses TestLayoutResolution's tree fixture. Covers cmd_verify against the
    --state-root interface for story/sprint scope. --scope epic is a distinct
    branch (back-reference integrity across the whole subtree, not per-node
    completion) — see TestVerifyEpicScope below."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _complete(self, path, story=False):
        from ruamel.yaml.comments import CommentedMap
        y, node = pm.load_node(path)
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
        pm.nodes.save_node(y, node, path)

    def test_scope_story_passes_when_complete(self):
        self._complete(pm.story_file(self.root, "E001-S01-003"), story=True)
        code, out = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "story", "--story", "E001-S01-003"])
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_scope_story_fails_exit_4_when_incomplete(self):
        # fixture default: status=review, no actual block, no completion_evidence
        code, out = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "story", "--story", "E001-S01-003"])
        self.assertEqual(code, 4)
        self.assertIn("status=", out)

    def test_scope_sprint_passes_when_complete(self):
        self._complete(pm.sprint_file(self.root, "E001", "S01"))
        code, out = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "sprint", "--epic", "E001", "--sprint", "S01"])
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_nonexistent_node_exits_3(self):
        code, _ = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "story", "--story", "E001-S01-999"])
        self.assertEqual(code, 3)


class TestVerifyDerivedCost(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _done_story(self, cost, total=4999):
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 3.1, "man_hours": 14, "hitl_hours": 0.3,
                          "tokens_k": {"total": total, "input": 412, "output": 34,
                                       "cache_write": 4300, "cache_read": 253},
                          "cost": cost, "model": "claude-opus-5"}
        pm.nodes.save_node(y, node, p)

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
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 1.0, "man_hours": 2, "hitl_hours": 0.1,
                          "tokens_k": {"total": 30, "input": 30, "output": 0,
                                       "cache_write": 0, "cache_read": 0},
                          "cost": 0.02, "model": "claude-haiku-4-5"}
        pm.nodes.save_node(y, node, p)
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
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 3.1, "man_hours": 14,
                          "tokens_k": "N/A", "cost": "N/A"}
        pm.nodes.save_node(y, node, p)
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
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        pm.nodes.save_node(y, node, p)

    def _set(self, *extra):
        return self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                              "--story", "E001-S01-003", "--runtime", "claude",
                              "--elapsed-hours", "1", "--man-hours", "2", "--hitl-hours", "0.1",
                              "--no-calibrate", *extra])

    def _verify(self):
        return self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                              "--story", "E001-S01-003", "--runtime", "claude"])

    def _actual(self):
        return pm.load_node(pm.story_file(self.root, "E001-S01-003"))[1]["actual"]

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
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["actual"]["cost"] = 9.99
        pm.nodes.save_node(y, node, p)
        code, out = self._verify()
        self.assertEqual(code, 4, out)
        self.assertIn("actual.cost=9.99 != derived 7.2 for each model in by_model", out)

    def test_verify_fails_when_by_model_does_not_sum_to_tokens_k(self):
        self._ready()
        self._set("--tokens-by-model", json.dumps(self.SPLIT))
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["actual"]["by_model"]["claude-sonnet-5-5"]["input"] = 999
        pm.nodes.save_node(y, node, p)
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
        self.assertNotIn("actual", pm.load_node(pm.story_file(self.root, "E001-S01-003"))[1] or {})

    def _priced_sonnet5(self, cost):
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 1.0, "man_hours": 2, "hitl_hours": 0.1,
                          "tokens_k": {"total": 1100, "input": 1000, "output": 100,
                                       "cache_write": 0, "cache_read": 0},
                          "cost": cost, "model": "claude-sonnet-5"}
        pm.nodes.save_node(y, node, p)

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
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _done_story_priced_only_under_override(self):
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        # "acme-model" does not exist in TOKEN_RATES; it is priced only by the
        # --token-rates override below (input $10/M, everything else free).
        # 100k input tokens -> 100 * 10.0 / 1000 = 1.00.
        node["actual"] = {"elapsed_hours": 1.0, "man_hours": 2, "hitl_hours": 0.1,
                          "tokens_k": {"total": 100, "input": 100, "output": 0,
                                       "cache_write": 0, "cache_read": 0},
                          "cost": 1.00, "model": "acme-model"}
        pm.nodes.save_node(y, node, p)

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


class TestVerifyEpicScope(TestLayoutResolution):
    """verify --scope epic — deferred from Task 2 (ruling R3), implemented in Task 4
    since it depends on list_sprint_dirs/list_story_files. Unlike story/sprint scope,
    this branch checks only back-reference integrity across the whole epic subtree,
    not per-node completion."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_scope_epic_passes_on_good_fixture(self):
        code, out = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "epic", "--epic", "E001"])
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_scope_epic_fails_exit_4_on_corrupted_backref(self):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nepic: 'E999'\nsprint: 'S01'\nstatus: review\n")
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                code = pm.main(
                    ["verify", "--state-root", self.root, "--scope", "epic", "--epic", "E001"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 4)
        self.assertIn("epic back-reference 'E999' != path epic 'E001'", err.getvalue())

    def test_scope_epic_nonexistent_exits_3(self):
        code, _ = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "epic", "--epic", "E999"])
        self.assertEqual(code, 3)

    def test_scope_epic_fails_exit_4_when_story_backref_absent(self):
        """migrate-state Stage E2 relies on this scope to prove Stage B actually wrote
        the `epic:`/`sprint:` back-references it introduces. A story file missing them
        entirely must fail the gate."""
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nstatus: review\n")
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                code = pm.main(
                    ["verify", "--state-root", self.root, "--scope", "epic", "--epic", "E001"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 4)
        self.assertIn("back-reference absent", err.getvalue())

    def test_scope_epic_fails_exit_4_when_sprint_backref_absent(self):
        sp = pm.sprint_file(self.root, "E001", "S01")
        with open(sp, "w") as f:
            f.write("key: 'S01'\nstatus: in-progress\n")
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                code = pm.main(
                    ["verify", "--state-root", self.root, "--scope", "epic", "--epic", "E001"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 4)
        self.assertIn("epic back-reference absent", err.getvalue())

    def test_scope_epic_reports_missing_sprint_and_corrupted_story_together(self):
        """Addition B: a sprint with no sprint.yaml must still be descended into, so a
        corrupted story co-located with the missing sprint.yaml is also reported —
        not silently skipped by the `continue` that used to follow the missing-file
        failure."""
        sd2 = os.path.join(self.root, "active", "epic-001", "sprint-02")
        os.makedirs(sd2)
        with open(os.path.join(sd2, "E001-S02-001.yaml"), "w") as f:
            f.write("key: 'E001-S02-001'\nepic: 'E999'\nsprint: 'S02'\nstatus: review\n")

        err = io.StringIO()
        try:
            with redirect_stderr(err):
                code = pm.main(
                    ["verify", "--state-root", self.root, "--scope", "epic", "--epic", "E001"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 4)
        failures = err.getvalue()
        self.assertEqual(failures.count("FAIL "), 2, failures)
        self.assertIn("sprint.yaml missing", failures)
        self.assertIn("E001-S02-001", failures)


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
    """Read-only commands (`calibration show`, `estimate-story`,
    `estimate-rollup`) must never trigger the metrics migration — proved by
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
            code = pm.main(["estimate-story", "--state-root", self.root,
                            "--story", "E001-S01-003", "--classification", "complex"])
        self.assertEqual(code, 0, buf.getvalue())
        self._unchanged()

    def test_estimate_rollup_leaves_calibration_file_untouched(self):
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        with open(os.path.join(sd, "E001-S01-003.yaml"), "w") as f:
            f.write("key: 'E001-S01-003'\nepic: 'E001'\nsprint: 'S01'\n"
                    "estimate:\n  man_hours: 4\n  elapsed_hours: 1\n"
                    "  tokens_k: 10\n  cost: 0.5\n")
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(io.StringIO()):
            code = pm.main(["estimate-rollup", "--state-root", self.root,
                            "--epic", "E001"])
        self.assertEqual(code, 0, buf.getvalue())
        self._unchanged()


class TestEstimateFactors(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_set_estimate_records_factors(self):
        # No --cost: cost is derived from tokens x rates and set-estimate
        # rejects it (see TestEstimateTokensAndCost.test_cost_low_flag_is_rejected).
        code, out = self.run_main(
            ["set-estimate", "--state-root", self.root, "--story", "E001-S01-003",
             "--man-hours", "6", "--time-hours", "1.5", "--tokens-k", "320",
             "--fix-factor", "1.25", "--scope-ratio", "1.1"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertAlmostEqual(float(node["estimate"]["fix_factor"]), 1.25)
        self.assertAlmostEqual(float(node["estimate"]["scope_ratio"]), 1.1)

    def test_factors_are_optional_and_absent_when_not_given(self):
        code, out = self.run_main(
            ["set-estimate", "--state-root", self.root, "--story", "E001-S01-003",
             "--man-hours", "6"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
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


class TestClosureSampling(TestLayoutResolution):
    def _write(self, path, mapping):
        y = pm._yaml()
        with open(path, "w") as f:
            y.dump(mapping, f)

    def _sprint_with_stories(self, story_actuals, sprint_actual, sprint_estimate=None,
                             story_estimates=None):
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        for f in os.listdir(sd):
            if f.endswith(".yaml") and f != "sprint.yaml":
                os.remove(os.path.join(sd, f))
        for i, a in enumerate(story_actuals, start=1):
            m = {"key": f"E001-S01-{i:03d}", "epic": "E001", "sprint": "S01",
                 "status": "done"}
            if a is not None:
                m["actual"] = {"man_hours": a}
            if story_estimates is not None:
                m["estimate"] = {"man_hours": story_estimates[i - 1]}
            self._write(os.path.join(sd, f"E001-S01-{i:03d}.yaml"), m)
        sm = {"key": "E001", "status": "done"}
        if sprint_actual is not None:
            sm["actual"] = {"man_hours": sprint_actual}
        if sprint_estimate is not None:
            sm["estimate"] = sprint_estimate
        self._write(os.path.join(self.root, "active", "epic-001", "epic.yaml"), sm)

    def test_residual_is_parent_minus_children(self):
        self._sprint_with_stories([3.0, 4.0], 9.0,
                                  {"man_hours_low": 1.0, "man_hours_high": 3.0})
        s, reason = pm.derive_closure_sample(self.root, "epic", "E001")
        self.assertIsNotNone(s, reason)
        self.assertAlmostEqual(s["closure_actual"]["man_hours"], 2.0)

    def test_missing_child_actual_skips_with_reason(self):
        self._sprint_with_stories([3.0, None], 9.0,
                                  {"man_hours_low": 1.0, "man_hours_high": 3.0})
        s, reason = pm.derive_closure_sample(self.root, "epic", "E001")
        self.assertIsNone(s)
        self.assertIn("actual", reason.lower())

    def test_negative_residual_skips_with_reason(self):
        self._sprint_with_stories([5.0, 5.0], 8.0,
                                  {"man_hours_low": 1.0, "man_hours_high": 3.0})
        s, reason = pm.derive_closure_sample(self.root, "epic", "E001")
        self.assertIsNone(s)
        self.assertIn("negative", reason.lower())

    def test_no_parent_actual_skips(self):
        self._sprint_with_stories([3.0, 4.0], None,
                                  {"man_hours_low": 1.0, "man_hours_high": 3.0})
        s, reason = pm.derive_closure_sample(self.root, "epic", "E001")
        self.assertIsNone(s)

    def test_record_appends_closure_sample(self):
        # children estimated 3+4=7, parent estimated 8-9 (mid 8.5) -> estimated
        # closure overhead 1.5; actual overhead 9-(3+4)=2 -> ratio 2/1.5
        self._sprint_with_stories([3.0, 4.0], 9.0,
                                  {"man_hours_low": 8.0, "man_hours_high": 9.0},
                                  story_estimates=[3.0, 4.0])
        _epic_locked(self.root, pm.record_closure_sample, self.root, "epic", "E001")
        _, cal = pm.load_calibration(self.root)
        samples = pm._component_samples(cal, "closure", "epic", "man_hours")
        self.assertEqual(len(samples), 1)
        self.assertAlmostEqual(float(samples[0]), round(2.0 / 1.5, 4))

    def test_closure_ratio_divides_by_estimated_overhead_not_whole_estimate(self):
        # THE C2 REGRESSION: dividing by the whole parent estimate midpoint (8.5)
        # would give 0.2353 and make the learned roll-up worse than cold start.
        self._sprint_with_stories([3.0, 4.0], 9.0,
                                  {"man_hours_low": 8.0, "man_hours_high": 9.0},
                                  story_estimates=[3.0, 4.0])
        s, reason = pm.derive_closure_sample(self.root, "epic", "E001")
        self.assertIsNotNone(s, reason)
        self.assertAlmostEqual(s["ratios"]["man_hours"], 2.0 / 1.5)

    def test_applied_closure_ratio_is_divided_back_out(self):
        # a parent estimate written with an active ratio carries it on the block;
        # the sample must remove it, or the loop settles on a geometric mean
        self._sprint_with_stories([3.0, 4.0], 9.0,
                                  {"man_hours_low": 8.0, "man_hours_high": 9.0,
                                   "closure_ratios": {"man_hours": 2.0}},
                                  story_estimates=[3.0, 4.0])
        s, _ = pm.derive_closure_sample(self.root, "epic", "E001")
        self.assertAlmostEqual(s["ratios"]["man_hours"], 2.0 * 2.0 / 1.5)

    def test_parent_actual_equal_to_children_sum_is_skipped_not_sampled_as_zero(self):
        """C2: the pre-fix closure step files instructed an EXACT sum of children,
        which makes the residual identically zero. `residual < 0` was guarded;
        `residual == 0` was not, so a 0.0 landed in the sample list as if it were
        a measurement. Exercise the number those step files actually produced."""
        self._sprint_with_stories([3.0, 4.0], 7.0,
                                  {"man_hours_low": 8.0, "man_hours_high": 9.0},
                                  story_estimates=[3.0, 4.0])
        s, reason = pm.derive_closure_sample(self.root, "epic", "E001")
        self.assertIsNone(s, f"a bare-sum actual must produce NO sample, got {s}")
        self.assertIn("zero residual", reason)
        _epic_locked(self.root, pm.record_closure_sample, self.root, "epic", "E001")
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(pm._component_samples(cal, "closure", "epic", "man_hours"), [])

    def test_bare_sum_of_unrepresentable_decimals_is_still_skipped(self):
        """The zero-residual guard must not be exact float equality.

        `residual = pv - total` is unrounded float arithmetic. Every other test in
        this file uses exactly-representable values (3.0 + 4.0 = 7.0), so an
        `== 0` check passes all of them while missing every real project that
        records hours in tenths. Both directions are exercised because a bare sum
        over decimals lands on either side of zero depending on the values, and
        the negative one used to be reported as a "miscount" that did not happen.
        """
        for children, parent, drift in (([0.3, 0.6], 0.9, "positive"),
                                        ([1.1, 2.2], 3.3, "negative")):
            with self.subTest(drift=drift):
                # the premise: these do NOT sum exactly, in either direction
                self.assertNotEqual(sum(children), parent)
                self._sprint_with_stories(
                    children, parent,
                    {"man_hours_low": parent + 1.0, "man_hours_high": parent + 3.0},
                    story_estimates=list(children))
                s, reason = pm.derive_closure_sample(self.root, "epic", "E001")
                self.assertIsNone(s, f"{drift} float drift produced a sample: {s}")
                self.assertIn("zero residual", reason)
                self.assertNotIn("miscounted", reason)
                _epic_locked(self.root, pm.record_closure_sample, self.root, "epic", "E001")
                _, cal = pm.load_calibration(self.root)
                self.assertEqual(
                    pm._component_samples(cal, "closure", "epic", "man_hours"), [])
                _, snode = pm.load_node(pm.nodes.epic_file(self.root, "E001"))
                self.assertNotIn(pm.CALIBRATION_MARKER, snode)

    def test_tolerance_does_not_swallow_a_genuine_small_residual(self):
        """The other half of the guard: a real closure overhead, however small,
        must still record. A tolerance wide enough to eat one is the same defect
        with a different sign."""
        self._sprint_with_stories([0.3, 0.6], 0.9001,
                                  {"man_hours_low": 1.0, "man_hours_high": 3.0},
                                  story_estimates=[0.3, 0.6])
        s, reason = pm.derive_closure_sample(self.root, "epic", "E001")
        self.assertIsNotNone(s, reason)
        self.assertAlmostEqual(s["closure_actual"]["man_hours"], 0.0001, places=7)

    def test_three_bare_sum_closes_never_train_the_ratio_to_zero(self):
        """The composite failure, not the single sample: three sprints closed with
        `actual == Σ children` used to leave `closure.sprint.man_hours` holding
        [0.0, 0.0, 0.0]. `weighted_ratio` returns 0.0 for that, 0.0 is not None,
        and `cmd_estimate_rollup` accepts it — so the closure band contributed
        nothing to every later estimate, permanently. The component must stay
        cold-start (None) instead."""
        for n in range(1, 4):
            skey = f"S{n:02d}"
            sd = os.path.join(self.root, "active", "epic-001", f"sprint-{n:02d}")
            os.makedirs(sd, exist_ok=True)
            for i in (1, 2):
                self._write(os.path.join(sd, f"E001-{skey}-{i:03d}.yaml"),
                            {"key": f"E001-{skey}-{i:03d}", "epic": "E001", "sprint": skey,
                             "status": "done", "estimate": {"man_hours": 5.0},
                             "actual": {"man_hours": 5.0}})
            self._write(os.path.join(self.root, "active", "epic-001", "epic.yaml"),
                        {"key": skey, "epic": "E001", "status": "done",
                         "estimate": {"man_hours_low": 11.0, "man_hours_high": 13.0},
                         "actual": {"man_hours": 10.0}})   # the BARE SUM
            _epic_locked(self.root, pm.record_closure_sample, self.root, "epic", "E001")
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(pm._component_samples(cal, "closure", "epic", "man_hours"), [])
        self.assertIsNone(pm.active_closure_ratio(cal, "epic", "man_hours"))

    def test_zero_estimated_overhead_skips_the_metric(self):
        # parent estimated exactly its children -> nothing to measure against
        self._sprint_with_stories([3.0, 4.0], 9.0,
                                  {"man_hours_low": 7.0, "man_hours_high": 7.0},
                                  story_estimates=[3.0, 4.0])
        s, _ = pm.derive_closure_sample(self.root, "epic", "E001")
        self.assertNotIn("man_hours", s["ratios"])
        self.assertIn("man_hours", s["skipped"])

    def test_cost_is_never_closure_sampled(self):
        # Task 10: cost is now derived from the rolled-up tokens_k range at
        # estimate-rollup time, so it must never accumulate its own closure
        # ratio — CLOSURE_RANGE_KEYS drops "cost" entirely (previously
        # test_dollar_prefixed_cost_contributes_to_closure_sample asserted the
        # opposite; a lingering cost closure sample would band a value the
        # estimate no longer bands). man_hours is present alongside the
        # dollar-prefixed cost actuals so the sample still succeeds overall —
        # this proves cost is skipped by design, not because nothing else
        # produced a residual.
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        for f in os.listdir(sd):
            if f.endswith(".yaml") and f != "sprint.yaml":
                os.remove(os.path.join(sd, f))
        self._write(os.path.join(sd, "E001-S01-001.yaml"),
                    {"key": "E001-S01-001", "epic": "E001", "sprint": "S01",
                     "status": "done", "actual": {"man_hours": 3.0, "cost": "$3.00"}})
        self._write(os.path.join(sd, "E001-S01-002.yaml"),
                    {"key": "E001-S01-002", "epic": "E001", "sprint": "S01",
                     "status": "done", "actual": {"man_hours": 4.0, "cost": "$4.00"}})
        self._write(os.path.join(self.root, "active", "epic-001", "epic.yaml"),
                    {"key": "E001", "status": "done",
                     "actual": {"man_hours": 9.0, "cost": "$9.00"},
                     "estimate": {"man_hours_low": 8.0, "man_hours_high": 9.0,
                                  "cost_low": 1.0, "cost_high": 3.0}})
        s, reason = pm.derive_closure_sample(self.root, "epic", "E001")
        self.assertIsNotNone(s, reason)
        self.assertAlmostEqual(s["closure_actual"]["man_hours"], 2.0)
        self.assertNotIn("cost", s["closure_actual"])
        self.assertNotIn("cost", s["ratios"])
        self.assertNotIn("cost", s["skipped"])
        self.assertNotIn("cost", pm.CLOSURE_RANGE_KEYS)

    def test_v1_file_is_migrated_not_corrupted_on_closure_record(self):
        # RULING B: record_closure_sample is a write path — a stale v1
        # calibration file must be migrated before a sample is appended, or
        # the sample lands in a "closure" structure v1 doesn't have.
        self._sprint_with_stories([3.0, 4.0], 9.0,
                                  {"man_hours_low": 8.0, "man_hours_high": 9.0},
                                  story_estimates=[3.0, 4.0])
        p = pm.calibration_path(self.root)
        with open(p, "w") as f:
            f.write("version: 1\nratio: 1.3\n")
        with redirect_stderr(io.StringIO()):    # migration announces its steps on stderr
            _epic_locked(self.root, pm.record_closure_sample, self.root, "epic", "E001")
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(cal["version"], pm.CALIBRATION_SCHEMA_VERSION)
        self.assertTrue(os.path.exists(p + ".v1"))
        self.assertEqual(len(pm._component_samples(cal, "closure", "epic", "man_hours")), 1)

    def test_a_stored_zero_closure_sample_is_ignored_on_read(self):
        """A file written before the write-side guard existed still holds zeros.

        A migration only repairs files someone remembers to migrate. The read
        side is what every estimate goes through, so it is where the rule has
        to hold for a file that already exists.
        """
        _, cal = pm.load_calibration(self.root)
        cal.setdefault("closure", {})["epic"] = {
            "tokens_k": {"samples": [3.7378, 0.0, 132.8062, 48.2812]},
        }
        # 0.0 must not be averaged in, and must not count toward MIN_SAMPLES.
        got = pm.active_closure_ratio(cal, "epic", "tokens_k")
        self.assertIsNotNone(got)
        self.assertAlmostEqual(
            got, pm.weighted_ratio([3.7378, 132.8062, 48.2812]), places=6)

    def test_zeros_do_not_count_toward_the_activation_threshold(self):
        _, cal = pm.load_calibration(self.root)
        cal.setdefault("closure", {})["epic"] = {
            "man_hours": {"samples": [0.0, 0.0, 0.0, 1.5]},
        }
        # Three zeros plus one real sample is one sample, not four.
        self.assertIsNone(pm.active_closure_ratio(cal, "epic", "man_hours"))

    def test_malformed_samples_are_handled_the_same_way_by_count_and_average(self):
        """bool subclasses int; a numeric string is a number everywhere else in
        this file. Whatever the filter decides, len() and the average must agree."""
        _, cal = pm.load_calibration(self.root)
        cal.setdefault("closure", {})["epic"] = {
            "man_hours": {"samples": [True, "2.0", 3.0]},
        }
        got = pm.active_closure_ratio(cal, "epic", "man_hours")
        # True is not a number; "2.0" is. Two real samples -> below MIN_SAMPLES.
        self.assertIsNone(got)


class TestClosureComposedWithOrchestration(TestLayoutResolution):
    """C1: the closure and orchestration components COMPOSED, which no test did.

    Each component was correct alone. Together they were not: since the
    orchestration band joined the roll-up, `pmid - Σ children estimate` is the
    closure band PLUS the orchestration band, while the residual it divides
    (`parent actual - Σ children actual`) is closure-only — orchestration lives
    in its own block. Every test of closure ran with the orchestration
    component inactive (fraction 0, band contributing nothing), so the extra
    term was always zero and the defect was invisible across 648 green tests.

    The numbers here are the reviewer's, measured on the shipped code: children
    summing to 20, an ACTIVE orchestration fraction of 0.5, a true closure
    overhead of 5. The sample must be 1.4286; the pre-fix code recorded 0.3704.
    """

    CHILD = 10.0          # each of two children, estimated and actualed at 10
    TRUE_CLOSURE = 5.0    # the closing level's own closure-phase spend
    ORCH_FRACTION = 0.5

    def run_main(self, argv):
        buf, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(err):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 0, buf.getvalue() + err.getvalue())
        return buf.getvalue()

    def _write(self, path, mapping):
        y = pm._yaml()
        with open(path, "w") as f:
            y.dump(mapping, f)

    def _children(self, skey="S01", n=2):
        sd = os.path.join(self.root, "active", "epic-001",
                          "sprint-" + skey.lstrip("S").zfill(2))
        os.makedirs(sd, exist_ok=True)
        for f in os.listdir(sd):
            if f.endswith(".yaml") and f != "sprint.yaml":
                os.remove(os.path.join(sd, f))
        for i in range(1, n + 1):
            self._write(os.path.join(sd, f"E001-{skey}-{i:03d}.yaml"),
                        {"key": f"E001-{skey}-{i:03d}", "epic": "E001", "sprint": skey,
                         "status": "done", "estimate": {"man_hours": self.CHILD},
                         "actual": {"man_hours": self.CHILD}})
        self._write(os.path.join(self.root, "active", "epic-001", "epic.yaml"),
                    {"key": skey, "epic": "E001", "status": "in-progress"})

    def _seed(self, orchestration=None, closure=None):
        with pm.calibration_lock(self.root):
            y, cal = pm.load_calibration(self.root)
            if orchestration is not None:
                cal["orchestration"]["epic"]["man_hours"] = {"samples": [orchestration] * 3}
            if closure is not None:
                cal["closure"]["epic"]["man_hours"] = {"samples": [closure] * 3}
            # an ongoing project's file always carries this after its first write;
            # without it the next set-actual would quarantine the seed as pre-rework
            cal[pm.CALIBRATION_METRICS_MARKER] = pm._now_iso()
            pm.save_calibration(y, cal, self.root)

    def _rollup_mid(self, skey="S01"):
        self.run_main(["estimate-rollup", "--state-root", self.root,
                       "--epic", "E001"])
        _, node = pm.load_node(pm.nodes.epic_file(self.root, "E001"))
        est = node["estimate"]
        return (float(est["man_hours_low"]) + float(est["man_hours_high"])) / 2.0

    def test_active_orchestration_band_is_not_counted_as_closure_overhead(self):
        self._children()
        self._seed(orchestration=self.ORCH_FRACTION)
        mid = self._rollup_mid()
        # 20 x (1 + 1.0x0.10 + 0.5x0.8) = 30 ... 20 x (1 + 1.0x0.25 + 0.5x1.2) = 37
        self.assertAlmostEqual(mid, 33.5, places=4)
        _, node = pm.load_node(pm.nodes.epic_file(self.root, "E001"))
        self.assertAlmostEqual(
            float(node["estimate"]["orchestration_ratios"]["man_hours"]), 0.5, places=4)

        parent_actual = 2 * self.CHILD + self.TRUE_CLOSURE      # 25
        self.run_main(["set-actual", "--state-root", self.root, "--node", "epic",
                       "--epic", "E001",
                       "--man-hours", str(parent_actual)])
        _, cal = pm.load_calibration(self.root)
        samples = pm._component_samples(cal, "closure", "epic", "man_hours")
        self.assertEqual(len(samples), 1)
        # expected closure overhead = 33.5 - 20 - 20x0.5x1.0 = 3.5  ->  5 / 3.5
        self.assertAlmostEqual(float(samples[0]), 1.4286, places=4)
        # the pre-fix denominator (33.5 - 20 = 13.5) gave 5/13.5 = 0.3704
        self.assertNotAlmostEqual(float(samples[0]), 0.3704, places=3)

    def test_learned_closure_ratio_reconciles_children_plus_closure_plus_orchestration(self):
        """Design §6.1's central claim: the roll-up IS Σ children + closure +
        orchestration. With both components active at their observed values the
        midpoint must land on 20 + 5 + 10 = 35 exactly."""
        self._children()
        self._seed(orchestration=self.ORCH_FRACTION, closure=1.4286)
        mid = self._rollup_mid()
        expected = (2 * self.CHILD) + self.TRUE_CLOSURE + (2 * self.CHILD * self.ORCH_FRACTION)
        self.assertAlmostEqual(mid, expected, places=2)

    def test_sample_is_stable_once_the_ratio_is_active(self):
        """A correct denominator makes the loop a fixed point: re-observing the
        same 5.0 of overhead against an estimate built with ratio 1.4286
        reproduces 1.4286. With the orchestration band left in the denominator
        it did not — it shrank on every generation."""
        self._children()
        self._seed(orchestration=self.ORCH_FRACTION, closure=1.4286)
        self._rollup_mid()
        self.run_main(["set-actual", "--state-root", self.root, "--node", "epic",
                       "--epic", "E001",
                       "--man-hours", str(2 * self.CHILD + self.TRUE_CLOSURE)])
        _, cal = pm.load_calibration(self.root)
        samples = pm._component_samples(cal, "closure", "epic", "man_hours")
        self.assertAlmostEqual(float(samples[-1]), 1.4286, places=3)

    def test_inactive_orchestration_leaves_the_denominator_untouched(self):
        """The guard must be a no-op when the component is cold-start, or it
        would silently change every existing closure sample."""
        self._children()
        self._seed()
        mid = self._rollup_mid()
        self.assertAlmostEqual(mid, 20 * 1.175, places=4)     # closure band only
        self.run_main(["set-actual", "--state-root", self.root, "--node", "epic",
                       "--epic", "E001",
                       "--man-hours", str(2 * self.CHILD + self.TRUE_CLOSURE)])
        _, cal = pm.load_calibration(self.root)
        samples = pm._component_samples(cal, "closure", "epic", "man_hours")
        self.assertAlmostEqual(float(samples[0]), round(5.0 / (20 * 0.175), 4), places=4)

    def test_orch_mid_tracks_the_spread_it_is_derived_from(self):
        self.assertAlmostEqual(pm.ORCH_MID,
                               (pm.ORCH_SPREAD[0] + pm.ORCH_SPREAD[1]) / 2.0)


class TestSetActualCalibrates(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _estimated_story(self):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nepic: 'E001'\nsprint: 'S01'\n"
                    "status: review\nclassification: complex\n"
                    "completion_evidence:\n  fix_iterations: 0\n"
                    "estimate:\n  man_hours: 6\n  elapsed_hours: 1.5\n"
                    "  tokens_k: 320\n  cost: 4.80\n  fix_factor: 1.25\n"
                    "  scope_ratio: 1.0\n")

    def test_actual_write_emits_a_sample(self):
        self._estimated_story()
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--elapsed-hours", "1.8",
             "--man-hours", "7", "--tokens-input", "355", "--model", "claude-sonnet-5"])
        self.assertEqual(code, 0, out)
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(pm._component_samples(cal, "scope", "complex", "man_hours")), 1)

    def test_no_calibrate_suppresses_the_sample(self):
        self._estimated_story()
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--man-hours", "7", "--no-calibrate"])
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(pm.calibration_path(self.root)))

    def test_story_without_estimate_writes_actual_and_no_sample(self):
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--man-hours", "7"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["actual"]["man_hours"], 7)

    def test_calibration_failure_does_not_fail_the_actual_write(self):
        self._estimated_story()
        # make the calibration path unwritable by putting a directory there
        os.makedirs(pm.calibration_path(self.root))
        out_buf, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out_buf), redirect_stderr(err):
                code = pm.main(
                    ["set-actual", "--state-root", self.root, "--node", "story",
                     "--story", "E001-S01-003", "--man-hours", "7"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 0, out_buf.getvalue())          # actuals are primary
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["actual"]["man_hours"], 7)
        self.assertIn("actual written, but calibration sample failed", err.getvalue())

    def test_claude_runtime_still_rejects_na(self):
        self._estimated_story()
        code, _ = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--tokens-na", "--runtime", "claude"])
        self.assertEqual(code, 2)

    def test_estimate_story_tokens_k_produces_a_real_scope_sample(self):
        """RULING (Task 10 fix round 1): `_estimated_story` above hand-writes
        estimate.tokens_k as a bare int — the same blind spot `_child_estimate_value`
        had before Task 10 fixed it, and it can only ever confirm the shape its
        author had in mind. `estimate-story` actually writes tokens_k as a
        `tokens_block` MAPPING (Tasks 6/7); `derive_story_sample` read it with
        `_num_or_none(est.get("tokens_k"))` directly, which returns None for a
        mapping, so the tokens_k scope component silently received zero samples
        in production. This drives the real CLI end to end — estimate-story then
        set-actual — the same style Task 10's own roll-up tests used to catch the
        first instance, and confirms a sample with the expected magnitude, not
        just a nonzero count."""
        code, out = self.run_main(["estimate-story", "--state-root", self.root,
                                   "--story", "E001-S01-003", "--classification", "standard",
                                   "--model", "claude-opus-5"])
        self.assertEqual(code, 0, out)
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--tokens-input", "20", "--tokens-output", "8",
             "--tokens-cache-write", "30", "--tokens-cache-read", "50",
             "--model", "claude-opus-5", "--runtime", "claude"])
        self.assertEqual(code, 0, out)
        _, cal = pm.load_calibration(self.root)
        samples = pm._component_samples(cal, "scope", "standard", "tokens_k")
        self.assertEqual(len(samples), 1, cal)
        # Both sides are FRESH (input + output + cache_write), never the total.
        # estimate fresh 88 (band mid 70 x cold-start ratio 1.0 x fix 1.25);
        # actual fresh 20+8+30 = 58 -- the 50 cache_read is excluded, because it
        # measures corpus x agent count rather than the size of this story.
        # No completion_evidence -> provenance "backout":
        #   sample = actual_fresh x applied(1.0) / estimate_fresh = 58/88
        self.assertAlmostEqual(float(samples[0]), 58.0 / 88.0, places=4)
        self.assertLess(float(samples[0]), 108.0 / 88.0,
                        "the old total-based basis is what this replaced")


class TestEstimateStory(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_cold_start_uses_band_midpoint_times_fix_prior(self):
        code, out = self.run_main(
            ["estimate-story", "--state-root", self.root, "--story", "E001-S01-003",
             "--classification", "complex"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
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
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
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
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["classification"], "simple")


class TestEstimateTokensAndCost(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
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
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
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
                code = pm.main(["set-estimate", "--state-root", self.root,
                                "--epic", "E001", "--sprint", "S01"] + list(extra))
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
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        base_cost = float(node["estimate"]["cost"])

        override = '{"claude-opus-5": {"input": 50.0, "output": 250.0, ' \
                    '"cache_write": 62.5, "cache_read": 5.0}}'
        code, out = self.run_main(
            ["estimate-story", "--state-root", self.root, "--story", "E001-S01-003",
             "--classification", "standard", "--model", "claude-opus-5",
             "--token-rates", override])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
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


class TestEstimateRollup(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _story_estimates(self, values):
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        for f in os.listdir(sd):
            if f.endswith(".yaml") and f != "sprint.yaml":
                os.remove(os.path.join(sd, f))
        for i, v in enumerate(values, start=1):
            with open(os.path.join(sd, f"E001-S01-{i:03d}.yaml"), "w") as f:
                f.write(f"key: 'E001-S01-{i:03d}'\nepic: 'E001'\nsprint: 'S01'\n"
                        f"estimate:\n  man_hours: {v}\n  elapsed_hours: 1\n"
                        f"  tokens_k: 10\n  cost: 0.5\n")

    def test_epic_rollup_sums_stories_plus_closure(self):
        """No sprint level between them (ADR-0016): the epic sums its stories directly."""
        self._story_estimates([4, 6])
        code, out = self.run_main(
            ["estimate-rollup", "--state-root", self.root, "--epic", "E001"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.nodes.epic_file(self.root, "E001"))
        est = node["estimate"]
        self.assertGreaterEqual(float(est["man_hours_high"]), 10.0)
        self.assertLessEqual(float(est["man_hours_low"]), float(est["man_hours_high"]))

    def test_rollup_writes_range_form_not_single_values(self):
        self._story_estimates([4, 6])
        self.run_main(["estimate-rollup", "--state-root", self.root,
                       "--epic", "E001"])
        _, node = pm.load_node(pm.nodes.epic_file(self.root, "E001"))
        self.assertIn("man_hours_low", node["estimate"])
        self.assertNotIn("man_hours", node["estimate"])

    def test_unknown_epic_exits_3(self):
        code, _ = self.run_main(
            ["estimate-rollup", "--state-root", self.root, "--epic", "E999"])
        self.assertEqual(code, 3)

    def test_estimate_rollup_takes_no_sprint(self):
        self._story_estimates([4, 6])
        code, _ = self.run_main(["estimate-rollup", "--state-root", self.root,
                                 "--epic", "E001", "--sprint", "S01"])
        self.assertEqual(code, 2)

    def test_epic_missed_by_the_pre_check_exits_3_and_writes_nothing(self):
        # Final review M1. find_epic_dir scans active -> planned -> archived, so a directory move
        # the other way can land mid-scan: the pre-check reads None while the epic exists.
        # That fell through to the body WITHOUT the epic lock; the body re-resolved the moved
        # epic, reached save_node, and the write guard raised a RuntimeError traceback. The
        # pre-check's answer must be final: exit 3, no traceback, nothing written.
        self._story_estimates([4, 6])
        code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                   "--epic", "E001"])
        self.assertEqual(code, 0, out)
        real_epic_file, calls = pm.nodes.epic_file, []
        self.assertIsNotNone(real_epic_file(self.root, "E001"))       # the epic does exist
        lock = pm.epic_lock_path(self.root, "E001")
        lock_before = os.path.exists(lock)
        before = _tree_snapshot(self.root)

        def pre_check_misses(state_root, epic):
            calls.append(epic)
            return None if len(calls) == 1 else real_epic_file(state_root, epic)

        err = io.StringIO()
        with mock.patch.object(pm.nodes, "epic_file", pre_check_misses):
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(err):
                    code = pm.main(["estimate-rollup", "--state-root", self.root,
                                    "--epic", "E001"])
            except SystemExit as e:
                code = e.code
            except Exception as e:                      # what the CLI shows as a traceback
                self.fail(f"estimate-rollup raised {type(e).__name__}: {e}")
        self.assertEqual(code, 3, err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())
        self.assertEqual(calls, ["E001"], "only the pre-check may resolve the epic")
        self.assertEqual(_tree_snapshot(self.root), before)
        self.assertEqual(os.path.exists(lock), lock_before, "no lock file for a missed epic")


class TestRollupOrchestrationBand(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _story_estimate(self):
        self.run_main(["estimate-story", "--state-root", self.root,
                       "--story", "E001-S01-003", "--classification", "standard",
                       "--model", "claude-opus-5"])

    def test_warns_and_omits_band_while_unseeded(self):
        self._story_estimate()
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001"])
        self.assertEqual(code, 0, out)
        self.assertIn("orchestration is unestimated", buf.getvalue())
        _, node = pm.load_node(pm.nodes.epic_file(self.root, "E001"))
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
        _, node = pm.load_node(pm.nodes.epic_file(self.root, "E001"))
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
        _, node = pm.load_node(pm.nodes.epic_file(self.root, "E001"))
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
        _, node = pm.load_node(pm.nodes.epic_file(self.root, "E001"))
        est = node["estimate"]
        self.assertEqual(est["model"], "claude-haiku-4-5")
        _, cal = pm.load_calibration(self.root)
        mix = pm.observed_mix(cal)
        expect_low = pm.cost_from_tokens(pm.split_tokens(float(est["tokens_k_min"]), mix),
                                         "claude-haiku-4-5")
        self.assertAlmostEqual(float(est["cost_low"]), expect_low, places=2)

    def test_partial_seed_still_warns_and_names_only_inactive_metrics(self):
        """RULING (Task 10 fix round 1): `not any(orch_applied.values())` only
        fires when EVERY metric is inactive. Orchestration calibrates per
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
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001"])
        self.assertEqual(code, 0, out)
        msg = buf.getvalue()
        self.assertIn("orchestration is unestimated", msg)
        self.assertIn("tokens_k", msg)
        self.assertIn("hitl_hours", msg)
        self.assertIn("elapsed_hours", msg)
        self.assertNotIn("man_hours", msg)
        _, node = pm.load_node(pm.nodes.epic_file(self.root, "E001"))
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
        _, node = pm.load_node(pm.nodes.epic_file(self.root, "E001"))
        baseline_cost = float(node["estimate"]["cost_low"])

        overrides = json.dumps({"claude-opus-5": {"input": 500.0}})
        with redirect_stderr(io.StringIO()):    # unseeded orchestration warns; not under test here
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001",
                                       "--token-rates", overrides])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.nodes.epic_file(self.root, "E001"))
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


class TestParallelClosureResidual(TestLayoutResolution):
    """A negative residual must skip THAT METRIC, never the whole sample — and
    wall-clock going negative is the expected topology under parallel execution,
    not a miscount."""

    def _write(self, path, mapping):
        y = pm._yaml()
        with open(path, "w") as f:
            y.dump(mapping, f)

    def _parallel_epic(self):
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        for f in os.listdir(sd):
            if f.endswith(".yaml") and f != "sprint.yaml":
                os.remove(os.path.join(sd, f))
        for i, (mh, eh) in enumerate([(12.0, 4.0), (12.0, 4.0)], start=1):
            self._write(os.path.join(sd, f"E001-S01-{i:03d}.yaml"),
                        {"key": f"E001-S01-{i:03d}", "epic": "E001", "sprint": "S01",
                         "status": "done",
                         "estimate": {"man_hours": 12.0, "elapsed_hours": 4.0},
                         "actual": {"man_hours": mh, "elapsed_hours": eh}})
        # two stories ran concurrently: sprint wall-clock 3.0 < children's 8.0,
        # while man-hours still add up (26 vs 24 -> 2.0 of closure overhead)
        self._write(os.path.join(self.root, "active", "epic-001", "epic.yaml"),
                    {"key": "E001", "status": "done",
                     "estimate": {"man_hours_low": 25.0, "man_hours_high": 29.0,
                                  "elapsed_hours_low": 9.0, "elapsed_hours_high": 11.0},
                     "actual": {"man_hours": 26.0, "elapsed_hours": 3.0}})

    def test_parallel_wall_clock_does_not_discard_the_man_hours_sample(self):
        self._parallel_epic()
        s, reason = pm.derive_closure_sample(self.root, "epic", "E001")
        self.assertIsNotNone(s, reason)
        self.assertAlmostEqual(s["closure_actual"]["man_hours"], 2.0)
        self.assertIn("man_hours", s["ratios"])
        self.assertNotIn("elapsed_hours", s["ratios"])

    def test_negative_wall_clock_is_not_reported_as_a_miscount(self):
        self._parallel_epic()
        s, _ = pm.derive_closure_sample(self.root, "epic", "E001")
        reason = s["skipped"]["elapsed_hours"]
        self.assertIn("parallel", reason.lower())
        self.assertNotIn("miscounted", reason.lower())

    def test_negative_man_hours_residual_still_warns_of_a_miscount(self):
        self._parallel_epic()
        self._write(os.path.join(self.root, "active", "epic-001", "epic.yaml"),
                    {"key": "E001", "status": "done",
                     "estimate": {"man_hours_low": 25.0, "man_hours_high": 29.0},
                     "actual": {"man_hours": 20.0, "elapsed_hours": 3.0}})
        s, reason = pm.derive_closure_sample(self.root, "epic", "E001")
        self.assertIsNone(s)
        self.assertIn("miscounted", reason.lower())

    def test_parallel_epic_records_the_man_hours_closure_sample(self):
        self._parallel_epic()
        note = _epic_locked(self.root, pm.record_closure_sample, self.root, "epic", "E001")
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(pm._component_samples(cal, "closure", "epic", "man_hours")), 1)
        self.assertIn("parallel", note.lower())


class TestSampleIdempotency(TestLayoutResolution):
    """A second set-actual on the same node must not append a second sample set.
    --no-calibrate exists, but relying on the caller to remember it is exactly
    the failure mode the mechanization was built to end."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _estimated_story(self):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nepic: 'E001'\nsprint: 'S01'\n"
                    "status: review\nclassification: complex\n"
                    "completion_evidence:\n  fix_iterations: 0\n"
                    "estimate:\n  man_hours: 6\n  elapsed_hours: 1.5\n"
                    "  tokens_k: 320\n  cost: 4.80\n  fix_factor: 1.25\n"
                    "  scope_ratios:\n    man_hours: 1.0\n    elapsed_hours: 1.0\n"
                    "    tokens_k: 1.0\n    cost: 1.0\n")

    def _set_actual(self):
        return self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--man-hours", "7"])

    def test_replayed_set_actual_appends_nothing(self):
        self._estimated_story()
        self._set_actual()
        code, out = self._set_actual()
        self.assertEqual(code, 0, out)
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(pm._component_samples(cal, "scope", "complex", "man_hours")), 1)
        self.assertEqual(int(cal["fix"]["complex"]["clean"]["samples"]), 1)

    def test_replay_is_reported_not_silent(self):
        self._estimated_story()
        self._set_actual()
        _, out = self._set_actual()
        self.assertIn("replay", out.lower())

    def test_first_write_stamps_the_marker(self):
        self._estimated_story()
        self._set_actual()
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertIn(pm.CALIBRATION_MARKER, node)

    def test_closure_sample_is_idempotent_too(self):
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        y = pm._yaml()
        for f in os.listdir(sd):
            if f.endswith(".yaml") and f != "sprint.yaml":
                os.remove(os.path.join(sd, f))
        for i, v in enumerate([3.0, 4.0], start=1):
            with open(os.path.join(sd, f"E001-S01-{i:03d}.yaml"), "w") as f:
                y.dump({"key": f"E001-S01-{i:03d}", "epic": "E001", "sprint": "S01",
                        "estimate": {"man_hours": v}, "actual": {"man_hours": v}}, f)
        with open(os.path.join(self.root, "active", "epic-001", "epic.yaml"), "w") as f:
            y.dump({"key": "E001", "status": "done",
                    "estimate": {"man_hours_low": 8.0, "man_hours_high": 9.0},
                    "actual": {"man_hours": 9.0}}, f)
        _epic_locked(self.root, pm.record_closure_sample, self.root, "epic", "E001")
        note = _epic_locked(self.root, pm.record_closure_sample, self.root, "epic", "E001")
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(pm._component_samples(cal, "closure", "epic", "man_hours")), 1)
        self.assertIn("replay", note.lower())


class TestConcurrentSampling(unittest.TestCase):
    """load->modify->save must run under ONE lock. Locking only the save let
    parallel appends read the same pre-append state and clobber each other —
    silently, at the DEFAULT max_parallel_subagents of 4."""

    N = 12

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        self.sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        os.makedirs(self.sd)
        with open(os.path.join(self.root, "active", "epic-001", "epic.yaml"), "w") as f:
            f.write("key: 'E001'\nstatus: in-progress\n")
        with open(os.path.join(self.sd, "sprint.yaml"), "w") as f:
            f.write("key: 'S01'\nepic: 'E001'\nstatus: in-progress\n")
        for i in range(1, self.N + 1):
            with open(os.path.join(self.sd, f"E001-S01-{i:03d}.yaml"), "w") as f:
                f.write(f"key: 'E001-S01-{i:03d}'\nepic: 'E001'\nsprint: 'S01'\n"
                        f"status: review\nclassification: complex\n"
                        f"completion_evidence:\n  fix_iterations: 0\n"
                        f"estimate:\n  man_hours: 6\n  fix_factor: 1.25\n"
                        f"  scope_ratios:\n    man_hours: 1.0\n")

    def test_concurrent_appends_lose_no_samples(self):
        import subprocess
        procs = [subprocess.Popen(
            [sys.executable, SCRIPT, "set-actual", "--state-root", self.root,
             "--node", "story", "--story", f"E001-S01-{i:03d}", "--man-hours", str(6 + i)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for i in range(1, self.N + 1)]
        for p in procs:
            out, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err.decode())
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(pm._component_samples(cal, "scope", "complex", "man_hours")),
                         self.N)
        self.assertEqual(int(cal["fix"]["complex"]["clean"]["samples"]), self.N)


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


class TestConcurrentAppendIssue(unittest.TestCase):
    """append-issue's load->allocate->modify->save must run under ONE lock
    (issues_lock), mirroring TestConcurrentAdrReservation above. Locking only the
    write would let two parallel appends both read the same pre-write highest
    number and allocate the same key to two different findings -- the same
    collision class ADR numbers hit in production (0013 x2, 0014 x2).

    Real subprocesses, not threads: `_file_lock`'s reentrancy counter (`_ISSUES_LOCK`)
    is per-process state, so threads sharing one process would pass this test
    vacuously even with the lock removed.
    """

    N = 8

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.f = os.path.join(self.d, "issues.yaml")

    def test_concurrent_appends_get_distinct_sequential_keys(self):
        import subprocess
        procs = [subprocess.Popen(
            [sys.executable, SCRIPT, "append-issue", "--file", self.f,
             "--epic", "001", "--title", f"concurrent finding {i}",
             "--source", "qa", "--severity", "Low"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for i in range(1, self.N + 1)]
        # Collected from each process's OWN stdout, same reasoning as the ADR
        # test: the file converging on N items only proves N writes happened,
        # not that no two callers were ever handed the same key.
        printed_keys = []
        for p in procs:
            out, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err.decode())
            printed_keys.extend(
                tok for tok in out.decode().split() if tok.startswith("BL-E001-"))
        expected = {f"BL-E001-{n:03d}" for n in range(1, self.N + 1)}
        self.assertEqual(set(printed_keys), expected,
                         f"duplicate or skipped key across {self.N} concurrent "
                         f"appends: got {sorted(printed_keys)}")
        self.assertEqual(len(printed_keys), self.N,
                         "a process printed more/fewer than one allocated key")

        y, data = pm.core._load(self.f)
        self.assertEqual(len(data["backlog"]), self.N)
        self.assertEqual({item["key"] for item in data["backlog"]}, expected)


class TestConvergence(TestLayoutResolution):
    """Multi-generation convergence — the property every single-sample test
    misses. Each case drives the real loop (estimate -> actual -> re-estimate)
    against a FIXED ground truth for enough generations that a ratio activates
    and feeds back into the next estimate.

    Pre-fix, the scope loop settled on sqrt(truth x band_mid) and the closure
    loop moved the roll-up AWAY from its own observed total. Both are asserted
    against here directly.
    """

    TRUTH_MAN_HOURS = 24.0                     # stable ground truth, well above
    BAND_MID = 12.0                            # the complex band midpoint (8-16)

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 0, buf.getvalue())
        return buf.getvalue()

    # --- scope ------------------------------------------------------------ #
    def _new_story(self, i):
        key = f"E001-S01-{i:03d}"
        with open(os.path.join(self.root, "active", "epic-001", "sprint-01",
                               f"{key}.yaml"), "w") as f:
            f.write(f"key: '{key}'\nepic: 'E001'\nsprint: 'S01'\nstatus: review\n")
        return key

    def _scope_generation(self, i):
        """One full turn of the loop, in the order a story's dev loop ran it:
        estimate -> fix_iterations -> actual (which samples)."""
        key = self._new_story(i)
        self.run_main(["estimate-story", "--state-root", self.root, "--story", key,
                       "--classification", "complex"])
        _, node = pm.load_node(pm.story_file(self.root, key))
        est = node["estimate"]
        _fx_set_field(self.root, "completion_evidence.fix_iterations", 0, story=key)
        self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                       "--story", key, "--man-hours", str(self.TRUTH_MAN_HOURS)])
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
            key = self._new_story(i)
            self.run_main(["estimate-story", "--state-root", self.root, "--story", key,
                           "--classification", "complex"])
            _, node = pm.load_node(pm.story_file(self.root, key))
            est = node["estimate"]
            # the estimate is exactly right: its scope half equals the truth it
            # was built from, and the story consumed no fix reserve
            actual = float(est["man_hours"]) / float(est["fix_factor"])
            _fx_set_field(self.root, "completion_evidence.fix_iterations", 0, story=key)
            self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                           "--story", key, "--man-hours", str(actual)])
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

    def _make_epic(self, n):
        """An epic whose 4 stories were each estimated exactly right, plus a closure
        overhead that is the same 8.0 every single time."""
        ekey = f"E{n:03d}"
        ed = os.path.join(self.root, "active", f"epic-{n:03d}")
        sd = os.path.join(ed, "sprint-01")
        os.makedirs(sd, exist_ok=True)
        y = pm._yaml()
        for i in range(1, self.CHILDREN + 1):
            with open(os.path.join(sd, f"{ekey}-S01-{i:03d}.yaml"), "w") as f:
                y.dump({"key": f"{ekey}-S01-{i:03d}", "epic": ekey, "sprint": "S01",
                        "status": "done",
                        "estimate": {"man_hours": self.CHILD_ESTIMATE},
                        "actual": {"man_hours": self.CHILD_ESTIMATE}}, f)
        with open(os.path.join(sd, "sprint.yaml"), "w") as f:
            y.dump({"key": "S01", "epic": ekey, "status": "in-progress"}, f)
        with open(os.path.join(ed, "epic.yaml"), "w") as f:
            y.dump({"key": ekey, "status": "in-progress"}, f)
        return ekey

    def _rollup_mid(self, ekey):
        self.run_main(["estimate-rollup", "--state-root", self.root, "--epic", ekey])
        _, node = pm.load_node(pm.nodes.epic_file(self.root, ekey))
        est = node["estimate"]
        return (float(est["man_hours_low"]) + float(est["man_hours_high"])) / 2.0

    def _closure_generation(self, n):
        ekey = self._make_epic(n)
        mid = self._rollup_mid(ekey)
        total_actual = self.CHILDREN * self.CHILD_ESTIMATE + self.TRUE_CLOSURE_OVERHEAD
        self.run_main(["set-actual", "--state-root", self.root, "--node", "epic",
                       "--epic", ekey, "--man-hours", str(total_actual)])
        return mid

    def test_learned_closure_rollup_is_closer_to_truth_than_cold_start(self):
        truth = self.CHILDREN * self.CHILD_ESTIMATE + self.TRUE_CLOSURE_OVERHEAD  # 48
        cold_start = self._closure_generation(2)
        for n in range(3, 9):
            self._closure_generation(n)
        learned = self._rollup_mid(self._make_epic(9))
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


class TestEvents(Base):
    """events.jsonl — the append-only transition log that supplies dwell time."""

    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.d, "state")
        d = os.path.join(self.root, "active", "epic-001", "sprint-01")
        os.makedirs(d)
        with open(os.path.join(self.root, "active", "epic-001", "epic.yaml"), "w") as fh:
            fh.write("key: 'E001'\ntitle: 'Foundation'\nstatus: in-progress\n")
        with open(os.path.join(d, "sprint.yaml"), "w") as fh:
            fh.write("key: 'S01'\nepic: 'E001'\nstatus: in-progress\n")
        with open(os.path.join(d, "E001-S01-001.yaml"), "w") as fh:
            fh.write("key: 'E001-S01-001'\nepic: 'E001'\nsprint: 'S01'\nstatus: in-progress\n")

    def read_events(self):
        p = pm.events_path(self.root)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def test_import_node_appends_event_with_kind_and_keys(self):
        code, _ = self.run_main(["import-node", "--state-root", self.root,
                                 "--story", "E001-S01-002", "--status", "review",
                                 "--session-id", "sess-abc"])
        self.assertEqual(code, 0)
        evs = self.read_events()
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["event"], "import")
        self.assertEqual(evs[0]["node"], "story")
        self.assertEqual(evs[0]["key"], "E001-S01-002")
        self.assertEqual(evs[0]["to"], "review")
        self.assertEqual((evs[0]["epic"], evs[0]["sprint"]), ("E001", "S01"))
        self.assertEqual(evs[0]["session"], "sess-abc")

    def test_no_events_flag_suppresses(self):
        self.run_main(["import-node", "--state-root", self.root,
                       "--story", "E001-S01-002", "--status", "review", "--no-events"])
        self.assertEqual(self.read_events(), [])

    def test_append_failure_warns_but_write_succeeds(self):
        # Plant a directory where the log file goes, so open(..., "a") must fail.
        os.makedirs(pm.events_path(self.root))
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["import-node", "--state-root", self.root,
                                     "--story", "E001-S01-002", "--status", "review"])
        self.assertEqual(code, 0)
        self.assertIn("could not append event", buf.getvalue())
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-002"))
        self.assertEqual(node["status"], "review")

    def test_set_actual_appends_actual_event(self):
        self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                       "--story", "E001-S01-001", "--elapsed-hours", "2",
                       "--man-hours", "3", "--tokens-input", "10",
                       "--model", "claude-sonnet-5", "--no-calibrate"])
        evs = [e for e in self.read_events() if e["event"] == "actual"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["key"], "E001-S01-001")

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
                code = pm.main(argv)
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
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(int(node["actual"]["tokens_k"]["total"]), 10)

    def test_runtime_other_still_accepts_a_partial_set(self):
        # A runtime that exposes only some classes is exactly what --runtime
        # other is for; the strict rule must not leak into it.
        code, out = self._set(["--runtime", "other", "--tokens-output", "10"])
        self.assertEqual(code, 0, out)

    def test_nothing_is_written_when_the_partial_set_is_rejected(self):
        self._set(["--runtime", "claude", "--tokens-output", "10"])
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
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
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _scalar_node(self, cost=9999.99):
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 1.0, "man_hours": 8, "hitl_hours": 0.2,
                          "tokens_k": 500, "cost": cost, "model": "claude-opus-5"}
        pm.nodes.save_node(y, node, p)

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
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 1.0, "man_hours": 8, "hitl_hours": 0.2,
                          "tokens_k": "N/A", "cost": "N/A"}
        pm.nodes.save_node(y, node, p)
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


class TestOrchestrationBlock(TestLayoutResolution):
    """The orchestration component: a FRACTION of children's actuals, not a
    ratio against an estimate — see pm.record_orchestration_sample's docstring
    for why. Sprint/epic only; a story's orchestration is its parent sprint's.
    """

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _story_actual(self, tokens_total):
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        node["actual"] = {"elapsed_hours": 1.0, "man_hours": 8, "hitl_hours": 0.2,
                          "tokens_k": {"total": tokens_total, "input": tokens_total,
                                       "output": 0, "cache_write": 0, "cache_read": 0},
                          "cost": pm.cost_from_tokens({"input": tokens_total},
                                                      "claude-opus-5"),
                          "model": "claude-opus-5"}
        pm.nodes.save_node(y, node, p)

    def test_orchestration_writes_to_its_own_block(self):
        code, out = self.run_main(["set-actual", "--state-root", self.root, "--node", "epic",
                                   "--epic", "E001",
                                   "--block", "orchestration",
                                   "--tokens-input", "1000", "--model", "claude-opus-5",
                                   "--elapsed-hours", "2", "--no-calibrate"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.nodes.epic_file(self.root, "E001"))
        self.assertIn("orchestration", node)
        self.assertNotIn("orchestration", node.get("actual") or {})
        self.assertEqual(int(node["orchestration"]["tokens_k"]["total"]), 1000)

    def test_orchestration_block_rejected_on_a_story(self):
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                code = pm.main(["set-actual", "--state-root", self.root, "--node", "story",
                                "--story", "E001-S01-003", "--block", "orchestration",
                                "--elapsed-hours", "1"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 2, err.getvalue())
        self.assertIn("orchestration", err.getvalue().lower())
        self.assertIn("epic", err.getvalue().lower())

    def test_fraction_sample_is_orchestration_over_children(self):
        self._story_actual(1000)
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "epic",
             "--epic", "E001", "--block", "orchestration",
             "--tokens-input", "3000", "--model", "claude-opus-5"])
        self.assertEqual(code, 0, out)
        _, cal = pm.load_calibration(self.root)
        samples = cal["orchestration"]["epic"]["tokens_k"]["samples"]
        self.assertAlmostEqual(float(samples[-1]), 3.0, places=3)

    def test_fraction_inactive_below_three_samples(self):
        cal = pm.new_calibration()
        self.assertIsNone(pm.active_orchestration_fraction(cal, "epic", "tokens_k"))

    def test_fraction_active_at_three_samples(self):
        cal = pm.new_calibration()
        cal["orchestration"]["epic"]["tokens_k"] = {"samples": [2.0, 2.0, 2.0]}
        self.assertAlmostEqual(
            pm.active_orchestration_fraction(cal, "epic", "tokens_k"), 2.0, places=3)

    def test_fraction_still_inactive_at_two_samples_boundary(self):
        # Proves activation is a strict >= MIN_SAMPLES (3), not off-by-one at 2.
        cal = pm.new_calibration()
        cal["orchestration"]["epic"]["tokens_k"] = {"samples": [2.0, 2.0]}
        self.assertIsNone(pm.active_orchestration_fraction(cal, "epic", "tokens_k"))

    def test_orchestration_never_calibrates_cost(self):
        # cost is derived from tokens x rates — a second, drift-capable
        # fraction for it would be redundant with the token fraction.
        self._story_actual(1000)
        self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "epic",
             "--epic", "E001", "--block", "orchestration",
             "--tokens-input", "3000", "--model", "claude-opus-5"])
        _, cal = pm.load_calibration(self.root)
        self.assertNotIn("cost", cal["orchestration"]["epic"])

    def test_denominator_requires_every_child_not_just_some(self):
        # A second story in the same sprint, WITHOUT an actual. A naive
        # partial-sum denominator (sum whatever children happen to have)
        # would still produce a tokens_k sample from the one story that does
        # have an actual — silently understating the true children total and
        # permanently inflating the fraction. record_orchestration_sample
        # must treat that as no sample for the metric, not a smaller one.
        self._story_actual(1000)
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        with open(os.path.join(sd, "E001-S01-004.yaml"), "w") as f:
            f.write("key: 'E001-S01-004'\nepic: 'E001'\nsprint: 'S01'\nstatus: review\n")
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "epic",
             "--epic", "E001", "--block", "orchestration",
             "--tokens-input", "3000", "--model", "claude-opus-5"])
        self.assertEqual(code, 0, out)
        self.assertIn("no orchestration sample", out.lower())
        self.assertIn("missing this metric's actual", out.lower())
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(cal["orchestration"]["epic"]), 0)

    def test_second_orchestration_call_does_not_double_count(self):
        # Assert on the calibration file's sample COUNT, not the command's
        # exit code — a replay that is silently accepted (exit 0, no new
        # sample) must read as success to the caller while still recording
        # nothing extra in the shared file.
        self._story_actual(1000)
        argv = ["set-actual", "--state-root", self.root, "--node", "epic",
                "--epic", "E001", "--block", "orchestration",
                "--tokens-input", "3000", "--model", "claude-opus-5"]
        code1, out1 = self.run_main(argv)
        self.assertEqual(code1, 0, out1)
        code2, out2 = self.run_main(list(argv))
        self.assertEqual(code2, 0, out2)
        self.assertIn("replay", out2.lower())
        _, cal = pm.load_calibration(self.root)
        samples = cal["orchestration"]["epic"]["tokens_k"]["samples"]
        self.assertEqual(len(samples), 1)

    def test_orchestration_marker_is_distinct_from_closure_marker(self):
        # The whole reason for a SEPARATE marker: an epic node carries both
        # a closure/actual sample and an orchestration sample. If they shared
        # CALIBRATION_MARKER, whichever ran first would silently suppress
        # the other. Record a closure sample first, then confirm the
        # orchestration sample still records.
        self._story_actual(1000)
        story_path = pm.story_file(self.root, "E001-S01-003")
        _, story_node = pm.load_node(story_path)
        story_node["estimate"] = {"man_hours_low": 3, "man_hours_high": 3}
        pm.nodes.save_node(pm._yaml(), story_node, story_path)
        sprint_path = pm.nodes.epic_file(self.root, "E001")
        _, sprint_node = pm.load_node(sprint_path)
        sprint_node["estimate"] = {"man_hours_low": 12, "man_hours_high": 12}
        _epic_locked(self.root, pm.nodes.save_node, pm._yaml(), sprint_node, sprint_path)
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "epic",
             "--epic", "E001", "--man-hours", "9"])
        self.assertEqual(code, 0, out)
        _, node_after_closure = pm.load_node(sprint_path)
        self.assertIn(pm.CALIBRATION_MARKER, node_after_closure)
        self.assertNotIn(pm.ORCHESTRATION_MARKER, node_after_closure)

        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "epic",
             "--epic", "E001", "--block", "orchestration",
             "--tokens-input", "3000", "--model", "claude-opus-5"])
        self.assertEqual(code, 0, out)
        self.assertNotIn("replay", out.lower())
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(cal["orchestration"]["epic"]["tokens_k"]["samples"]), 1)
        _, node_after_both = pm.load_node(sprint_path)
        self.assertIn(pm.ORCHESTRATION_MARKER, node_after_both)

    def test_epic_level_replay_guard_does_not_double_count(self):
        # A second orchestration write on the same epic must not append a second sample.
        self._story_actual(1000)
        argv = ["set-actual", "--state-root", self.root, "--node", "epic",
                "--epic", "E001", "--block", "orchestration",
                "--tokens-input", "3000", "--model", "claude-opus-5"]
        code1, out1 = self.run_main(argv)
        self.assertEqual(code1, 0, out1)
        code2, out2 = self.run_main(list(argv))
        self.assertEqual(code2, 0, out2)
        self.assertIn("replay", out2.lower())
        _, cal = pm.load_calibration(self.root)
        samples = cal["orchestration"]["epic"]["tokens_k"]["samples"]
        self.assertEqual(len(samples), 1)

    def test_calibration_show_lists_orchestration_component(self):
        y, cal = pm.load_calibration(self.root)
        cal["orchestration"]["epic"]["tokens_k"] = {"samples": [2.0, 2.0, 2.0]}
        pm.save_calibration(y, cal, self.root)
        code, out = self.run_main(["calibration", "show", "--state-root", self.root])
        self.assertEqual(code, 0, out)
        self.assertIn("orchestration", out)
        self.assertIn("epic/tokens_k", out)



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
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, buf.getvalue()

    def test_a_recorded_run_appends_and_derives_the_boolean(self):
        self.run_main(["add-test-run", "--state-root", self.root, "--story", "E001-S01-003",
                       "--command", "npm test", "--exit-code", "0"])
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        runs = node["completion_evidence"]["test_runs"]
        self.assertEqual(runs[0]["command"], "npm test")
        self.assertEqual(runs[0]["exit_code"], 0)
        self.assertIs(node["completion_evidence"]["tests_passing"], True)

    def test_one_failing_run_makes_the_derived_boolean_false(self):
        for cmd, rc in (("npm test", "0"), ("pytest", "1")):
            self.run_main(["add-test-run", "--state-root", self.root, "--story", "E001-S01-003",
                           "--command", cmd, "--exit-code", rc])
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertIs(node["completion_evidence"]["tests_passing"], False)

    def test_a_malformed_stored_exit_code_fails_rather_than_crashes(self):
        """test_runs is hand-editable YAML; a non-numeric exit_code must derive False,
        never raise and never derive True."""
        path = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(path)
        ce = node.setdefault("completion_evidence", {})
        ce["test_runs"] = [{"command": "old flaky run", "exit_code": "flaky"}]
        pm.nodes.save_node(y, node, path)

        code, out = self.run_main(["add-test-run", "--state-root", self.root,
                                   "--story", "E001-S01-003",
                                   "--command", "npm test", "--exit-code", "0"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(path)
        self.assertIs(node["completion_evidence"]["tests_passing"], False)

    def test_no_recorded_runs_leaves_tests_passing_absent(self):
        """The exact regression all(()) == True would reintroduce: a story that never
        called add-test-run must never read as tests_passing: true."""
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
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
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
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
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
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


class TestCalibrationRedrive(TestLayoutResolution):
    def _close_story(self, iters, key="E001-S01-003", actual=9.0, ts="2026-01-01T00:00:00Z"):
        p = pm.story_file(self.root, key)
        y, node = pm.load_node(p)
        node["classification"] = "standard"
        node["estimate"] = {"fix_factor": 1.25, "scope_ratios": {"man_hours": 1.0},
                            "man_hours": 8.75}
        node["actual"] = {"man_hours": actual}
        node["completion_evidence"] = {"fix_iterations": iters}
        pm.nodes.save_node(y, node, p)
        # `set-actual` appends this alongside the node write; redrive reads it back to
        # recover closure order, so a hand-built node must carry it too or the rebuild
        # correctly refuses.
        if ts is not None:
            self._actual_event(key, ts)

    def _actual_event(self, key, ts):
        epic, sprint, _ = pm.parse_story_key(key)
        pm.append_event(self.root, {"ts": ts, "event": "actual", "node": "story",
                                    "key": key, "epic": epic, "sprint": sprint})

    def _story(self, key, status="active"):
        """A second story node, in whichever status folder the test needs."""
        epic, sprint, _ = pm.parse_story_key(key)
        d = os.path.join(self.root, status, pm.epic_dirname(epic), pm.sprint_dirname(sprint))
        os.makedirs(d, exist_ok=True)
        ep = os.path.join(self.root, status, pm.epic_dirname(epic), "epic.yaml")
        if not os.path.exists(ep):
            with open(ep, "w") as fh:
                fh.write(f"key: '{epic}'\nstatus: in-progress\n")
        sp = os.path.join(d, "sprint.yaml")
        if not os.path.exists(sp):
            with open(sp, "w") as fh:
                fh.write(f"key: '{sprint}'\nepic: '{epic}'\nstatus: in-progress\n")
        with open(os.path.join(d, f"{key}.yaml"), "w") as fh:
            fh.write(f"key: '{key}'\nepic: '{epic}'\nsprint: '{sprint}'\nstatus: review\n")

    def test_redrive_repairs_a_sample_poisoned_by_the_string_bug(self):
        # A node closed under the bug: text that does not parse, read as backout.
        self._close_story("{fix_iterations}")
        poisoned = pm.derive_story_sample(pm.load_node(pm.story_file(self.root, "E001-S01-003"))[1])
        self.assertEqual(poisoned["provenance"], "backout", "premise: the bug's reading")

        # The node is corrected (as a run would now write it), then redriven.
        self._close_story(0)
        rep = pm.redrive_story_samples(self.root)
        self.assertEqual(rep["provenance"], {"exact": 1})
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(cal["fix"]["standard"]["clean"]["samples"], 1,
                         "the clean cohort fills, so fix can eventually activate")

    def test_redrive_rebuilds_rather_than_appends(self):
        self._close_story(0)
        pm.redrive_story_samples(self.root)
        rep = pm.redrive_story_samples(self.root)
        self.assertEqual(rep["sampled"], 1)
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(cal["scope"]["standard"]["man_hours"]["samples"]), 1,
                         "a second redrive must replace, never double-count")

    def test_redrive_appends_in_closure_order_not_directory_order(self):
        """The defect: samples were re-appended in tree-walk order, and weighted_ratio
        weights the LAST entry most, so a rebuild that repaired nothing re-priced every
        unstarted story. Story ...-004 sorts after ...-003 by key but closed BEFORE it,
        so closure order and directory order disagree and only one can be right."""
        self._story("E001-S01-004")
        self._close_story(0, key="E001-S01-003", actual=9.0, ts="2026-02-01T00:00:00Z")
        self._close_story(0, key="E001-S01-004", actual=18.0, ts="2026-01-01T00:00:00Z")
        pm.redrive_story_samples(self.root)
        _, cal = pm.load_calibration(self.root)
        got = cal["scope"]["standard"]["man_hours"]["samples"]
        # ...-004 closed first, so its ratio (18.0-derived) must come FIRST and weigh least.
        self.assertEqual([float(x) for x in got],
                         sorted([float(x) for x in got], reverse=True),
                         "the earlier-closed, larger-ratio sample must lead the list")
        self.assertGreater(float(got[0]), float(got[1]))

    def test_redrive_puts_an_archived_epic_before_a_later_active_one(self):
        """STATUS_DIRS is ("active", "planned", "archived"), so a tree walk visits
        archived LAST and it collects the HIGHEST recency weight — inverting the
        weighting on every project with archived work, which is the common case."""
        self._story("E013-S01-001", status="archived")
        self._close_story(0, key="E013-S01-001", actual=18.0, ts="2026-01-01T00:00:00Z")
        self._close_story(0, key="E001-S01-003", actual=9.0, ts="2026-03-01T00:00:00Z")
        pm.redrive_story_samples(self.root)
        _, cal = pm.load_calibration(self.root)
        got = [float(x) for x in cal["scope"]["standard"]["man_hours"]["samples"]]
        self.assertGreater(got[0], got[1],
                           "archived E013 closed first, so it must lead and weigh least")

    def test_redrive_refuses_when_the_event_log_is_absent(self):
        self._close_story(0, ts=None)
        with self.assertRaises(pm.PMError) as cm:
            pm.redrive_story_samples(self.root)
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("cannot establish closure order", cm.exception.msg)

    def test_redrive_refuses_on_a_partially_covered_log(self):
        """The dangerous middle state: a log exists and looks orderable, but
        `set-actual --no-events` left one story out of it."""
        self._story("E001-S01-004")
        self._close_story(0, key="E001-S01-003", ts="2026-01-01T00:00:00Z")
        self._close_story(0, key="E001-S01-004", ts=None)
        with self.assertRaises(pm.PMError) as cm:
            pm.redrive_story_samples(self.root)
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("E001-S01-004", cm.exception.msg)
        self.assertIn("1 of 2", cm.exception.msg)

    def test_a_refusal_writes_nothing_at_all(self):
        """A refusal must leave the file AND the backup untouched, or the operator loses
        the very ordering the refusal exists to protect."""
        self._close_story(0, ts="2026-01-01T00:00:00Z")
        pm.redrive_story_samples(self.root)                      # a good run first
        before = open(pm.calibration_path(self.root), encoding="utf-8").read()
        backup = pm.calibration_path(self.root) + ".pre-redrive"
        self._story("E001-S01-004")
        self._close_story(0, key="E001-S01-004", ts=None)        # now uncoverable
        had_backup = os.path.exists(backup)
        bak_before = open(backup, encoding="utf-8").read() if had_backup else None
        with self.assertRaises(pm.PMError):
            pm.redrive_story_samples(self.root)
        self.assertEqual(open(pm.calibration_path(self.root), encoding="utf-8").read(),
                         before, "calibration file must be byte-identical after a refusal")
        self.assertEqual(os.path.exists(backup), had_backup)
        if had_backup:
            self.assertEqual(open(backup, encoding="utf-8").read(), bak_before)

    def test_redrive_leaves_untouched_components_alone(self):
        self._close_story(0)
        with pm.calibration_lock(self.root):
            y, cal = pm.load_calibration(self.root)
            cal["token_mix"] = {"samples": [{"input": 0.1, "output": 0.1,
                                             "cache_write": 0.3, "cache_read": 0.5}]}
            cal["closure"] = {"sprint": {"man_hours": {"samples": [1.1]}}}
            pm.save_calibration(y, cal, self.root)
        pm.redrive_story_samples(self.root)
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(cal["token_mix"]["samples"]), 1)
        self.assertEqual(cal["closure"]["sprint"]["man_hours"]["samples"], [1.1])


class TestAdrRegister(TestLayoutResolution):
    # TestLayoutResolution supplies the node tree but NOT run_main -- every class
    # extending it defines its own (see TestSetFieldTyping above).
    def run_main(self, argv):
        buf, err = io.StringIO(), io.StringIO()
        code = 0
        if argv and argv[0] == "adr-reserve" and "--adr-dir" not in argv:
            argv = [*argv, "--adr-dir", os.path.join(self.d, "no-adr-dir")]
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
                code = pm.main(argv)
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
    """T-MM: model mismatch annotation in set-actual, verify, and calibration show."""

    def run_main(self, argv):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, out_buf.getvalue() + err_buf.getvalue()

    def _write_story_with_estimate_model(self, model: str):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write(
                f"key: 'E001-S01-003'\nepic: 'E001'\nsprint: 'S01'\nstatus: review\n"
                f"estimate:\n  model: {model}\n"
            )

    def test_set_actual_notes_model_mismatch(self):
        self._write_story_with_estimate_model("claude-opus-5")
        code, out = self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "codex", "--no-calibrate",
            "--elapsed-hours", "2.0", "--man-hours", "8.0", "--hitl-hours", "0.5",
            "--tokens-input", "100", "--tokens-output", "20", "--tokens-cache-read", "300",
            "--model", "gpt-5.6-terra",
        ])
        self.assertEqual(code, 0)
        self.assertIn("model mismatch", out)
        self.assertIn("claude-opus-5", out)
        self.assertIn("gpt-5.6-terra", out)

    def test_set_actual_no_mismatch_note_when_models_match(self):
        self._write_story_with_estimate_model("gpt-5.6-terra")
        code, out = self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "codex", "--no-calibrate",
            "--elapsed-hours", "2.0", "--man-hours", "8.0", "--hitl-hours", "0.5",
            "--tokens-input", "100", "--tokens-output", "20", "--tokens-cache-read", "300",
            "--model", "gpt-5.6-terra",
        ])
        self.assertEqual(code, 0)
        self.assertNotIn("model mismatch", out)

    def test_verify_warns_on_model_mismatch(self):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write(
                "key: 'E001-S01-003'\nepic: 'E001'\nsprint: 'S01'\nstatus: done\n"
                "estimate:\n  model: claude-opus-5\n"
                "actual:\n"
                "  elapsed_hours: 2.0\n  man_hours: 8.0\n  hitl_hours: 0.5\n"
                "  tokens_k:\n    input: 100\n    output: 20\n"
                "    cache_write: 0\n    cache_read: 300\n    total: 420\n"
                "  cost: 0.16\n  model: gpt-5.6-terra\n"
                "completion_evidence:\n  tests_passing: true\n"
            )
        code, out = self.run_main([
            "verify", "--state-root", self.root, "--scope", "story",
            "--story", "E001-S01-003", "--runtime", "codex",
        ])
        self.assertIn("WARN", out)
        self.assertIn("claude-opus-5", out)
        self.assertIn("gpt-5.6-terra", out)

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
                code = pm.main(argv)
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
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        tk = node["actual"]["tokens_k"]
        self.assertEqual(int(tk["cache_write"]), 0)
        self.assertEqual(int(tk["total"]), 420)  # 100+20+0+300

    def test_codex_derives_cost_from_three_classes(self):
        code, out = self._set(
            "--tokens-input", "100", "--tokens-output", "20",
            "--tokens-cache-read", "300", "--model", "codex-1",
        )
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        # cost = (100*5 + 20*30 + 0*6.25 + 300*2.5) / 1000 = (500+600+0+750)/1000 = 1.85
        self.assertAlmostEqual(float(node["actual"]["cost"]), 1.85, places=2)

    def test_verify_fails_on_scalar_tokens_under_codex(self):
        # Write a node with scalar tokens_k (like TestVerifyRejectsScalarTokens does),
        # then verify under codex — scalar form must fail for codex just as for claude.
        f = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(f)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {
            "elapsed_hours": 2.0, "man_hours": 8.0, "hitl_hours": 0.5,
            "tokens_k": 420, "cost": "N/A", "model": "codex-1",
        }
        pm.nodes.save_node(y, node, f)
        code, out = self._verify()
        self.assertEqual(code, 4)
        self.assertIn("not the per-class mapping", out)

    def test_verify_na_tokens_fails_under_codex(self):
        # Write tokens_k=N/A to a done node, then verify — N/A is forbidden under codex.
        f = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(f)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {
            "elapsed_hours": 2.0, "man_hours": 8.0, "hitl_hours": 0.5,
            "tokens_k": "N/A", "cost": "N/A", "model": "codex-1",
        }
        pm.nodes.save_node(y, node, f)
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
                code = pm.main(argv)
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
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        tk = node["actual"]["tokens_k"]
        # scalar, not a mapping
        self.assertFalse(hasattr(tk, "get"), f"expected scalar, got mapping: {tk}")
        self.assertEqual(int(tk), 200)  # 150 + 50

    def test_copilot_stores_cost_na(self):
        code, out = self._set("--tokens-input", "150", "--tokens-output", "50")
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertTrue(pm._is_na(node["actual"]["cost"]))

    def test_copilot_model_not_required(self):
        # no --model; should succeed (cost=N/A means no pricing needed)
        code, out = self._set("--tokens-input", "150", "--tokens-output", "50")
        self.assertEqual(code, 0, out)

    def test_verify_passes_with_scalar_tokens_and_na_cost_under_copilot(self):
        # Write a complete done node with scalar tokens_k and cost=N/A, then verify
        f = pm.story_file(self.root, "E001-S01-003")
        y, n = pm.load_node(f)
        n.setdefault("actual", {})
        n["actual"].update({
            "elapsed_hours": 2.0, "man_hours": 8.0, "hitl_hours": 0.5,
            "tokens_k": 200, "cost": "N/A",
        })
        n["status"] = "done"
        n.setdefault("completion_evidence", {})
        pm.nodes.save_node(y, n, f)
        code, out = self._verify()
        self.assertEqual(code, 0, out)

    def test_verify_rejects_na_tokens_k_under_copilot(self):
        f = pm.story_file(self.root, "E001-S01-003")
        y, n = pm.load_node(f)
        n.setdefault("actual", {})
        n["actual"].update({
            "elapsed_hours": 2.0, "man_hours": 8.0, "hitl_hours": 0.5,
            "tokens_k": "N/A", "cost": "N/A",
        })
        n["status"] = "done"
        n.setdefault("completion_evidence", {})
        pm.nodes.save_node(y, n, f)
        code, _ = self._verify()
        self.assertEqual(code, 4)


class TestUpdateIssue(IssueBase):
    def test_unknown_key_names_both_files(self):
        """Match resolve-issue: an unknown key is in neither file, and both are named."""
        code, _, err = self.update("BL-E001-042", "High")
        self.assertEqual(code, 3)
        self.assertIn("issues.yaml", err)
        self.assertIn("issues-resolved.yaml", err)

    def update(self, key, sev, *extra):
        return self.run_all(["update-issue", "--state-root", self.root, "--key", key,
                             "--severity", sev, *extra])

    def test_severity_actually_changes(self):
        """The assertion epic-closure §4's old 'promote via append-issue' never had:
        that path printed OK and changed nothing."""
        self.append("A", "001", "01", "Low")
        code, out, err = self.update("BL-E001-001", "High", "--note", "wider blast radius")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.load_open()["backlog"][0]["severity"], "High")
        ev = self.events("issue_updated")[-1]
        self.assertEqual((ev["from"], ev["to"], ev["note"]), ("Low", "High", "wider blast radius"))

    def _same_severity_noop(self, *extra):
        """Update BL-E001-001 to the severity it already has; assert no write and no event."""
        self.append("A", "001", "01", "Low")

        def read(p):
            with open(p, "rb") as fh:
                return fh.read()
        issues, events = read(self.issues), read(pm.events_path(self.root))
        code, out, err = self.update("BL-E001-001", "Low", *extra)
        self.assertEqual(code, 0, err)
        self.assertEqual(read(self.issues), issues)
        self.assertEqual(read(pm.events_path(self.root)), events)
        return out

    def test_same_severity_is_a_noop(self):
        """It used to save the file, log an issue_updated event with from == to, and print
        `severity Low -> Low`: a change record for a change that did not happen."""
        self.assertEqual(self._same_severity_noop(),
                         "OK update-issue BL-E001-001 severity Low unchanged\n")

    def test_same_severity_with_a_note_says_the_note_was_not_recorded(self):
        # Final review M5: the note lives only in the issue_updated event, which a no-op does
        # not write, so the caller's "why" was dropped with no hint that it had been.
        self.assertEqual(self._same_severity_noop("--note", "no change"),
                         "OK update-issue BL-E001-001 severity Low unchanged (note not recorded)\n")

    def test_resolved_key_exits_2_naming_resolution(self):
        self.append("A")
        self.run_all(["resolve-issue", "--state-root", self.root, "--key", "BL-E001-001",
                      "--resolution", "obsolete", "--note", "gone"])
        code, _, err = self.update("BL-E001-001", "High")
        self.assertEqual(code, 2)
        self.assertIn("obsolete", err)

    def test_unknown_key_exits_3(self):
        self.assertEqual(self.update("BL-E001-077", "High")[0], 3)

    def test_invalid_severity_is_a_usage_error(self):
        self.append("A")
        self.assertEqual(self.update("BL-E001-001", "Severe")[0], 2)

    def test_key_duplicated_in_open_file_is_refused(self):
        self.append("A")
        y, data = pm.core._load(self.issues)
        from ruamel.yaml.comments import CommentedMap
        data["backlog"].append(CommentedMap(data["backlog"][0]))
        pm.core._atomic_dump(y, data, self.issues)
        code, _, err = self.update("BL-E001-001", "High")
        self.assertEqual(code, 2)
        self.assertIn("1i", err)

    def test_key_in_both_files_is_refused_as_resolved(self):
        """Resolve's crash window leaves a key in both files; it is resolved, so an
        update must be refused, not applied to the stale open copy."""
        self.append("A", "001", "01", "Low")
        with _dump_failing_on(2), self.assertRaises(OSError):
            pm.main(["resolve-issue", "--state-root", self.root, "--key",
                     "BL-E001-001", "--resolution", "obsolete", "--note", "x"])
        self.assertEqual(self.open_keys(), ["BL-E001-001"])       # premise: both files
        code, _, err = self.update("BL-E001-001", "High")
        self.assertEqual(code, 2)
        self.assertIn("obsolete", err)
        self.assertEqual(self.load_open()["backlog"][0]["severity"], "Low")


class TestListIssuesLifecycle(IssueBase):
    def ls(self, *extra):
        code, out, err = self.run_all(["list-issues", "--state-root", self.root,
                                       "--format", "json", *extra])
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_resolved_flag_and_resolution_filter(self):
        self.append("A")
        self.append("B", "001", "02")
        self.run_all(["resolve-issue", "--state-root", self.root, "--key", "BL-E001-001",
                      "--resolution", "obsolete", "--note", "x"])
        self.assertEqual([i["key"] for i in self.ls()], ["BL-E001-002"])
        self.assertEqual([i["key"] for i in self.ls("--resolved")], ["BL-E001-001"])
        self.assertEqual(self.ls("--resolved", "--resolution", "fixed"), [])

    def test_all_returns_both_lists(self):
        self.append("A")
        self.append("B", "001", "02")
        self.run_all(["resolve-issue", "--state-root", self.root, "--key", "BL-E001-002",
                      "--resolution", "obsolete", "--note", "x"])
        data = self.ls("--all")
        self.assertEqual([i["key"] for i in data["open"]], ["BL-E001-001"])
        self.assertEqual([i["key"] for i in data["resolved"]], ["BL-E001-002"])

    def test_flag_combinations_that_make_no_sense_exit_2(self):
        for argv in (["--resolution", "fixed"], ["--resolved", "--status", "backlog"]):
            code, _, _ = self.run_all(["list-issues", "--state-root", self.root,
                                       "--format", "json", *argv])
            self.assertEqual(code, 2, argv)
        code, _, _ = self.run_all(["list-issues", "--state-root", self.root, "--all"])
        self.assertEqual(code, 2, "--all is JSON only")

    def test_origin_archived_follows_the_epic_directory(self):
        self.append("Later thing", "005", "01", "Low", "qa (Q-1)")
        self.assertFalse(self.ls()[0]["origin_archived"])
        _fx_move_epic(self.root, "E005", "archived")
        self.assertTrue(self.ls()[0]["origin_archived"])
        code, out, _ = self.run_all(["list-issues", "--state-root", self.root])
        self.assertIn("archived", out)

    def test_status_filter(self):
        self.append("A")
        y, data = pm.core._load(self.issues)      # a scheduled item (promote lands in Task 8)
        data["backlog"][0]["status"] = "scheduled"
        pm.core._atomic_dump(y, data, self.issues)
        self.append("B", "001", "02")
        self.assertEqual([i["key"] for i in self.ls("--status", "scheduled")], ["BL-E001-001"])
        self.assertEqual([i["key"] for i in self.ls("--status", "backlog")], ["BL-E001-002"])

    def test_all_on_missing_state_root_creates_nothing(self):
        ghost = os.path.join(self.d, "nope")
        code, out, _ = self.run_all(["list-issues", "--state-root", ghost, "--all",
                                     "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"open": [], "resolved": []})
        self.assertFalse(os.path.exists(ghost))

    def test_all_on_a_state_root_without_issue_files_creates_nothing(self):
        code, out, _ = self.run_all(["list-issues", "--state-root", self.root, "--all",
                                     "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"open": [], "resolved": []})
        self.assertFalse(os.path.exists(self.issues + ".lock"),
                         "a read-only command left a lock file behind")

    def test_all_refuses_a_malformed_list(self):
        with open(self.issues, "w", encoding="utf-8") as fh:
            fh.write("backlog: oops\n")
        code, _, _ = self.run_all(["list-issues", "--state-root", self.root, "--all",
                                   "--format", "json"])
        self.assertEqual(code, 2)


class TestListAllConsistency(unittest.TestCase):
    """--all reads both files under issues_lock: a concurrent resolve can never show
    a key in both lists or in neither."""
    N = 8

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        _build_issue_tree(self.root)
        for i in range(1, self.N + 1):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(pm.main(["append-issue", "--state-root", self.root, "--epic",
                                          "001", "--title", f"t{i}", "--source", "qa",
                                          "--severity", "Low"]), 0)

    def test_snapshots_are_consistent_under_concurrent_resolves(self):
        import subprocess
        procs = [subprocess.Popen([sys.executable, SCRIPT, "resolve-issue", "--state-root",
                                   self.root, "--key", f"BL-E001-{i:03d}", "--resolution",
                                   "obsolete", "--note", "x"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(1, self.N + 1)]
        snapshots = []
        for _ in range(15):
            r = subprocess.run([sys.executable, SCRIPT, "list-issues", "--state-root",
                                self.root, "--all", "--format", "json"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            snapshots.append(json.loads(r.stdout))
        for p in procs:
            p.communicate(timeout=120)
        for s in snapshots:
            o = {i["key"] for i in s["open"]}
            r = {i["key"] for i in s["resolved"]}
            self.assertFalse(o & r, "key in both lists")
            self.assertEqual(len(o | r), self.N, "a key vanished")


class TestEstimateCores(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_compute_story_estimate_raises_instead_of_exiting(self):
        path = pm.story_file(self.root, "E001-S01-003")
        with open(path, encoding="utf-8") as fh:
            before = fh.read()
        _, node = pm.load_node(path)
        with self.assertRaises(pm.PMError) as cm:
            pm.metrics.estimates.compute_story_estimate(self.root, node, "standard", "no-such-model", None)
        self.assertEqual(cm.exception.code, 2)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before, "core must never save")

    def test_compute_story_estimate_fills_node_in_memory(self):
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        applied = pm.metrics.estimates.compute_story_estimate(self.root, node, "simple", pm.DEFAULT_ESTIMATE_MODEL, None)
        self.assertIn("man_hours", applied)
        self.assertIn("cost", node["estimate"])
        self.assertEqual(node["classification"], "simple")

    def test_rollup_parent_estimate_raises_for_missing_epic(self):
        with self.assertRaises(pm.PMError) as cm:
            pm.metrics.estimates.rollup_parent_estimate(self.root, "E009", pm.DEFAULT_ESTIMATE_MODEL, None)
        self.assertEqual(cm.exception.code, 3)

    def test_rollup_parent_estimate_raises_when_nothing_to_roll_up(self):
        with self.assertRaises(pm.PMError) as cm:
            pm.metrics.estimates.rollup_parent_estimate(self.root, "E001", pm.DEFAULT_ESTIMATE_MODEL, None)
        self.assertEqual(cm.exception.code, 2)

    def test_cli_unknown_model_still_exits_2_and_writes_nothing(self):
        path = pm.story_file(self.root, "E001-S01-003")
        with open(path, encoding="utf-8") as fh:
            before = fh.read()
        code, _ = self.run_main(["estimate-story", "--state-root", self.root, "--story",
                                 "E001-S01-003", "--classification", "simple",
                                 "--model", "no-such-model"])
        self.assertEqual(code, 2)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)

    def test_compute_story_estimate_leaves_node_untouched_when_it_raises(self):
        path = pm.story_file(self.root, "E001-S01-003")
        _, node = pm.load_node(path)
        pm.metrics.estimates.compute_story_estimate(self.root, node, "simple", pm.DEFAULT_ESTIMATE_MODEL, None)
        before_est = json.dumps(node["estimate"], sort_keys=True, default=str)
        before_cls = node["classification"]
        with self.assertRaises(pm.PMError):
            pm.metrics.estimates.compute_story_estimate(self.root, node, "complex", "no-such-model", None)
        self.assertEqual(json.dumps(node["estimate"], sort_keys=True, default=str), before_est,
                         "a failed estimate must not half-overwrite the previous one")
        self.assertEqual(node["classification"], before_cls)


def _tree_snapshot(top):
    snap = {}
    for dp, _, files in os.walk(top):
        for f in files:
            if f.endswith(".lock"):
                continue
            p = os.path.join(dp, f)
            with open(p, "rb") as fh:
                snap[os.path.relpath(p, top)] = fh.read()
    return snap


def _wait_until_blocked_on(proc, lock_path, what="child", hang_guard=30.0):
    """Return once `proc` is SEEN blocked on `lock_path`'s flock; fail if it exits first.

    The verdict comes from one of two positive events, never from elapsed time:
    - `proc` appears in /proc/locks as a blocked waiter -- a `->` line carrying its pid on
      `lock_path`'s inode -- so it is honoring the lock, and this returns;
    - `proc` exits first, so it never waited and the lock was not honored: AssertionError.
    A fixed sleep can only fail when an unlocked writer happens to finish inside the window,
    so on a loaded runner it passes having checked nothing. `hang_guard` only stops a wedged
    child from hanging the suite: tripping it kills the child and fails loudly; it never
    passes a test.

    Linux-only -- decorate callers with
    `@unittest.skipUnless(os.path.exists("/proc/locks"), ...)`. A waiter's line reads
    `25: -> FLOCK  ADVISORY  WRITE <pid> <maj>:<min>:<inode> 0 EOF`; the inode is matched,
    not the device, whose numbering is filesystem-specific. Start `proc` directly (no shell
    or wrapper), so `proc.pid` is the process that takes the lock."""
    import time
    ino, pid = str(os.stat(lock_path).st_ino), str(proc.pid)
    deadline = time.monotonic() + hang_guard
    while True:
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise AssertionError(f"{what} (pid {pid}) exited {proc.returncode} without waiting "
                                 f"on {lock_path} -- the lock was not honored\n"
                                 f"stdout: {out!r}\nstderr: {err!r}")
        with open("/proc/locks", encoding="ascii", errors="replace") as fh:
            for line in fh:
                f = line.split()
                if len(f) > 6 and f[1] == "->" and f[5] == pid and f[6].rsplit(":", 1)[-1] == ino:
                    return
        if time.monotonic() > deadline:
            proc.kill()
            proc.communicate()
            raise AssertionError(f"hang guard: {what} (pid {pid}) neither exited nor blocked on "
                                 f"{lock_path} within {hang_guard}s")
        time.sleep(0.01)


class TestPromoteIssue(IssueBase):
    def promote(self, *keys, epic="001", sprint="02", cls="standard", extra=()):
        argv = ["promote-issue", "--state-root", self.root, "--artifacts-root", self.arts]
        for k in keys:
            argv += ["--key", k]
        argv += ["--epic", epic, "--sprint", sprint, "--classification", cls, *extra]
        return self.run_all(argv)

    def story(self, key="E001-S02-001"):
        return pm.load_node(pm.story_file(self.root, key))[1]

    def test_promote_creates_estimated_story_and_schedules_item(self):
        self.append("Replace linear scan", "001", "01", "Medium")
        code, out, err = self.promote("BL-E001-001")
        self.assertEqual(code, 0, err)
        self.assertIn("E001-S02-001", out)
        node = self.story()
        self.assertEqual(node["status"], "backlog")
        self.assertEqual(list(node["resolves"]), ["BL-E001-001"])
        self.assertIn("cost", node["estimate"])
        self.assertNotIn("estimate", pm.load_node(pm.sprint_file(self.root, "E001", "S02"))[1])
        self.assertIn("estimate", pm.load_node(pm.nodes.epic_file(self.root, "E001"))[1])
        item = self.load_open()["backlog"][0]
        self.assertEqual((item["status"], item["story"]), ("scheduled", "E001-S02-001"))
        with open(pm.story_doc_path(self.arts, "E001-S02-001"), encoding="utf-8") as fh:
            doc = fh.read()
        self.assertIn("## Context", doc)
        self.assertIn("- The deferred finding BL-E001-001 is resolved: Replace linear scan", doc)
        ev = self.events("issue_scheduled")
        self.assertEqual((ev[-1]["key"], ev[-1]["story"]), ("BL-E001-001", "E001-S02-001"))
        self.assertNotIn("via", ev[-1])     # repair's link carries via; promote's shape is unchanged
        self.assert_invariants()

    def test_refusals_write_nothing(self):
        self.append("A")
        cases = [
            (dict(sprint="01"), 2),                               # sprint in-progress
            (dict(extra=("--model", "no-such-model")), 2),
            (dict(extra=("--token-rates", "{")), 2),
            (dict(sprint="09"), 3),                               # sprint missing
            (dict(epic="042", sprint="01"), 3),                   # epic missing
        ]
        for kwargs, want in cases:
            before = _tree_snapshot(self.d)
            code, _, err = self.promote("BL-E001-001", **kwargs)
            self.assertEqual(code, want, (kwargs, err))
            self.assertEqual(_tree_snapshot(self.d), before, kwargs)
        before = _tree_snapshot(self.d)
        self.assertEqual(self.promote("BL-E001-999")[0], 2)                   # not open
        self.assertEqual(self.promote("BL-E001-001", "BL-E001-001x")[0], 2)   # bad key
        self.assertEqual(_tree_snapshot(self.d), before)

    def test_one_key_given_twice_is_refused_naming_what_it_would_have_skipped(self):
        """Replaces a characterisation test that pinned the previous behaviour (collapse to
        one, no --title demanded). That test failed the moment this changed, which is what it
        was for -- a user-facing contract moved loudly instead of silently.

        The message must name `--title`, because the cost of the duplicate is not the
        duplicate: it is the check the duplicate skips. The caller is usually an agent
        assembling this list from prose, so the message is read by something that can act
        on it."""
        self.append("A")
        before = _tree_snapshot(self.d)
        code, _out, err = self.promote("BL-E001-001", "BL-E001-001")
        self.assertEqual(code, 2, err)
        self.assertIn("given twice", err)
        self.assertIn("--title", err, "the message must say what the duplicate would skip")
        self.assertEqual(_tree_snapshot(self.d), before, "a refusal writes nothing")

    def test_two_distinct_keys_with_a_title_still_promote(self):
        """The refusal must not catch the case it exists to protect: two real items folded
        into one story, with the --title that makes it deliberate."""
        self.append("A")
        self.append("B")
        k1, k2 = self.open_keys()[0], self.open_keys()[1]
        code, out, err = self.promote(k1, k2, extra=("--title", "Both of them"))
        self.assertEqual(code, 0, err)
        self.assertIn("E001-S02-001", out)
        self.assertEqual(sorted(str(x) for x in self.story()["resolves"]), sorted([k1, k2]))

    def test_a_refusal_the_advisory_pass_catches_never_takes_the_epic_lock(self):
        """promote resolves its items TWICE — once before the epic lock as an advisory
        refusal, once under it as the decisive one. Deleting the advisory call leaves every
        refusal still correct, so nothing else here notices: the only observable difference
        is that the doomed call takes the epic lock on its way to failing, which contends
        with whatever is actually working that epic. `_tree_snapshot` cannot see it, because
        it skips `.lock` files by design."""
        self.append("A", "001", "01", "Low", "code-review (E001-S01-001)",
                    "--kind", "spec-change", "--ref", "deadbeef1234")
        lock = pm.epic_lock_path(self.root, "E001")
        self.assertFalse(os.path.exists(lock), "precondition: no epic lock yet")
        code, _o, err = self.promote("BL-E001-001")
        self.assertEqual(code, 2, err)
        self.assertFalse(os.path.exists(lock),
                         "the advisory pass must refuse before the epic lock is taken")

    def test_two_keys_need_a_title(self):
        self.append("A")
        self.append("B", "001", "02")
        self.assertEqual(self.promote("BL-E001-001", "BL-E001-002")[0], 2)
        code, _, err = self.promote("BL-E001-001", "BL-E001-002", extra=("--title", "Batch"))
        self.assertEqual(code, 0, err)
        self.assertEqual(list(self.story()["resolves"]), ["BL-E001-001", "BL-E001-002"])
        self.assertEqual({i["status"] for i in self.load_open()["backlog"]}, {"scheduled"})
        self.assert_invariants()

    def test_archived_epic_is_refused(self):
        self.append("Later", "005", "01", "Low", "qa (Q-1)")
        _fx_move_epic(self.root, "E005", "archived")
        before = _tree_snapshot(self.d)
        code, _, err = self.promote("BL-E005-001", epic="005", sprint="01")
        self.assertEqual(code, 2)
        self.assertIn("archived", err)
        self.assertEqual(_tree_snapshot(self.d), before)

    def test_already_scheduled_is_refused_naming_the_story(self):
        self.append("A")
        self.promote("BL-E001-001")
        code, _, err = self.promote("BL-E001-001")
        self.assertEqual(code, 2)
        self.assertIn("E001-S02-001", err)

    def test_live_foreign_lock_refuses_own_lock_allows(self):
        self.append("A")
        _fx_set_lock(self.root, "E001", "other")
        before = _tree_snapshot(self.d)
        code, _, err = self.promote("BL-E001-001")
        self.assertEqual(code, 5, err)
        self.assertIn("epic E001 is LOCKED by other", err)
        self.assertEqual(_tree_snapshot(self.d), before)          # M14(c): exit 5 writes nothing
        code, _, err = self.promote("BL-E001-001", extra=("--session-id", "other"))
        self.assertEqual(code, 0, err)

    def _set_epic_lock(self, lock_yaml):
        """Give epic E001 a hand-written `_lock` -- a deliberately built state (no verb writes
        a malformed or back-dated lock), keeping the rest of the node as the verbs left it."""
        from ruamel.yaml import YAML
        with pm.epic_node_lock(self.root, "E001"):       # every epic.yaml write holds it
            p = pm.nodes.epic_file(self.root, "E001")
            y, n = pm.load_node(p)
            n["_lock"] = YAML().load(lock_yaml)
            pm.nodes.save_node(y, n, p)

    def _lock_verdict(self):
        """`_check_lock_verdict` on E001's present `_lock`, for session `me`."""
        _, n = pm.load_node(pm.nodes.epic_file(self.root, "E001"))
        return pm.nodes._check_lock_verdict(n["_lock"], "me")[0]

    def test_foreign_lock_verdict_matches_check_lock(self):
        """For a WELL-FORMED lock, promote takes `_check_lock_verdict` (carryover 16) -- its
        TTL semantics, including ttl_minutes 0 as always stale."""
        now = pm._now_iso()
        cases = {  # name: (lock, the verdict -- pinned, so it cannot drift)
            "live":     (f"session_id: other\nclaimed_at: '{now}'\nttl_minutes: 30\n", 5),
            "stale":    (("session_id: other\nclaimed_at: '2020-01-01T00:00:00Z'\n"
                         "ttl_minutes: 1\n"), 0),
            "ttl-zero": (f"session_id: other\nclaimed_at: '{now}'\nttl_minutes: 0\n", 0),
        }
        for i, (name, (lock, verdict)) in enumerate(cases.items(), start=1):
            self.append(f"L{i}")
            self._set_epic_lock(lock)
            check = self._lock_verdict()
            self.assertEqual(check, verdict, name)
            before = _tree_snapshot(self.d)
            code, _, err = self.promote(f"BL-E001-{i:03d}")
            self.assertEqual(code, check, (name, err))
            if code == 5:
                self.assertEqual(_tree_snapshot(self.d), before, name)

    def test_unevaluable_foreign_lock_refuses_and_writes_nothing(self):
        """Ruling 24: promote is a write verb, so a foreign lock it cannot evaluate refuses
        (exit 5) -- even where `_check_lock_verdict`, a read, calls it free -- and writes nothing."""
        now = pm._now_iso()
        cases = {  # name: (lock, the verdict, pinned; None where the verdict raises)
            "not-a-mapping":   ("'just-a-string'\n", 0),
            "no-timestamp":    ("session_id: other\nttl_minutes: 30\n", 0),
            "bad-timestamp":   ("session_id: other\nclaimed_at: 'not-a-time'\nttl_minutes: 30\n", 0),
            "naive-timestamp": (("session_id: other\nclaimed_at: '2026-01-01T00:00:00'\n"
                                "ttl_minutes: 30\n"), None),
            "no-session":      (f"claimed_at: '{now}'\nttl_minutes: 30\n", 5),
            "non-integer-ttl": (f"session_id: other\nclaimed_at: '{now}'\nttl_minutes: abc\n", None),
        }
        self.append("A")
        for name, (lock, verdict) in cases.items():
            self._set_epic_lock(lock)
            if verdict is not None:
                self.assertEqual(self._lock_verdict(), verdict, name)
            before = _tree_snapshot(self.d)
            code, _, err = self.promote("BL-E001-001")
            self.assertEqual(code, 5, (name, err))
            self.assertIn("epic E001", err, name)
            self.assertIn("cannot be evaluated", err, name)
            self.assertIn("delete the _lock block", err, name)
            self.assertEqual(_tree_snapshot(self.d), before, name)
        # the refusal does not reach a lock that names THIS session
        self._set_epic_lock("session_id: me\nttl_minutes: 30\n")
        code, _, err = self.promote("BL-E001-001", extra=("--session-id", "me"))
        self.assertEqual(code, 0, err)

    def test_a_padded_holder_session_is_foreign(self):
        """Ruling F2: the holder is compared to the caller EXACTLY, as `_check_lock_verdict`
        compare it. promote used to strip a hand-edited 'me ' and read it as its own -- then
        wave an otherwise unevaluable lock through."""
        now = pm._now_iso()
        self.append("A")
        me = ("--session-id", "me")
        # well-formed and live: foreign to `me`, and the verdict agrees
        self._set_epic_lock(f"session_id: 'me '\nclaimed_at: '{now}'\nttl_minutes: 30\n")
        self.assertEqual(self._lock_verdict(), 5)
        before = _tree_snapshot(self.d)
        code, _, err = self.promote("BL-E001-001", extra=me)
        self.assertEqual(code, 5, err)
        self.assertEqual(_tree_snapshot(self.d), before)
        # no claimed_at: foreign, so unevaluable -- stripping read it as own and wrote the story
        self._set_epic_lock("session_id: 'me '\nttl_minutes: 30\n")
        before = _tree_snapshot(self.d)
        code, _, err = self.promote("BL-E001-001", extra=me)
        self.assertEqual(code, 5, err)
        self.assertIn("cannot be evaluated (claimed_at is missing or unparseable)", err)
        self.assertEqual(_tree_snapshot(self.d), before)
        # only the presence check strips: a whitespace-only holder is no session_id at all
        self._set_epic_lock(f"session_id: '  '\nclaimed_at: '{now}'\nttl_minutes: 30\n")
        before = _tree_snapshot(self.d)
        code, _, err = self.promote("BL-E001-001", extra=me)
        self.assertEqual(code, 5, err)
        self.assertIn("cannot be evaluated (no session_id)", err)
        self.assertEqual(_tree_snapshot(self.d), before)

    def test_allocation_skips_an_artifact_only_document(self):
        self.append("A")
        stories = os.path.join(self.arts, "epic-001", "sprint-02", "stories")
        os.makedirs(stories)
        with open(os.path.join(stories, "E001-S02-001.md"), "w", encoding="utf-8") as fh:
            fh.write("an unrelated story nobody bootstrapped\n")
        code, out, err = self.promote("BL-E001-001")
        self.assertEqual(code, 0, err)
        self.assertIn("E001-S02-002", out)
        with open(os.path.join(stories, "E001-S02-001.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "an unrelated story nobody bootstrapped\n")

    def test_retry_resumes_a_promote_that_stopped_before_scheduling(self):
        self.append("A")
        self._crash_promote_before_scheduling()
        self.assertEqual(list(self.story()["resolves"]), ["BL-E001-001"])    # premise
        self.assertEqual(self.load_open()["backlog"][0]["status"], "backlog")
        code, out, err = self.promote("BL-E001-001")
        self.assertEqual(code, 0, err)
        self.assertIn("resumed", out)
        self.assertIsNone(pm.story_file(self.root, "E001-S02-002"), "no second story")
        self.assertEqual(self.load_open()["backlog"][0]["story"], "E001-S02-001")
        self.assert_invariants()

    def test_promote_never_writes_an_estimate_less_node(self):
        """Spec §6.1/§7: the node and its estimate land in ONE save. If the estimate fails
        after validation, no story node may be left on disk (it would have no estimate)."""
        self.append("A")
        with mock.patch.object(pm.metrics.estimates, "compute_story_estimate",
                               side_effect=pm.PMError(2, "injected")):
            code, _, err = self.promote("BL-E001-001")
        self.assertNotEqual(code, 0)
        self.assertIn("injected", err)
        self.assertIsNone(pm.story_file(self.root, "E001-S02-001"),
                          "a story node was written before its estimate")
        item = self.load_open()["backlog"][0]
        self.assertEqual(item["status"], "backlog")
        self.assertNotIn("story", item)
        self.assertFalse(os.path.exists(pm.story_doc_path(self.arts, "E001-S02-001")))

    def test_key_in_both_files_is_refused_as_resolved(self):
        self.append("A")
        with _dump_failing_on(2), self.assertRaises(OSError):
            pm.main(["resolve-issue", "--state-root", self.root, "--key", "BL-E001-001",
                     "--resolution", "obsolete", "--note", "x"])
        before = _tree_snapshot(self.d)
        code, _, err = self.promote("BL-E001-001")
        self.assertEqual(code, 2)
        self.assertIn("already resolved", err)
        self.assertEqual(_tree_snapshot(self.d), before)

    def test_list_issues_status_scheduled_sees_a_real_promotion(self):
        self.append("A")
        self.append("B", "001", "02")
        self.promote("BL-E001-001")
        code, out, err = self.run_all(["list-issues", "--state-root", self.root,
                                       "--status", "scheduled", "--format", "json"])
        self.assertEqual(code, 0, err)
        self.assertEqual([i["key"] for i in json.loads(out)], ["BL-E001-001"])

    @unittest.skipUnless(os.path.exists("/proc/locks"), "needs /proc/locks to see a flock waiter")
    def test_concurrent_resolve_cannot_orphan_a_promoted_story(self):
        """A resolve racing a promote must never leave an estimated story listing a resolved
        item: promote holds issues_lock from its item check through scheduling."""
        # The resolve starts inside promote's first roll-up. It must be SEEN blocked on
        # issues_lock there (batch B). A fixed wait window
        # passed without checking anything whenever an unlocked resolve was merely slower than
        # the window.
        import subprocess
        self.append("A")
        real_rollup = pm.metrics.estimates.rollup_parent_estimate
        lock = pm.issues_paths(self.root)[0] + ".lock"
        procs, failures = [], []

        def racing_rollup(*a, **kw):
            try:
                if not procs:
                    p = subprocess.Popen([sys.executable, SCRIPT, "resolve-issue", "--state-root",
                                          self.root, "--key", "BL-E001-001", "--resolution",
                                          "obsolete", "--note", "raced"],
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    procs.append(p)
                    self.addCleanup(p.kill)              # reaps on failure; no-op once done
                _wait_until_blocked_on(procs[0], lock, "resolve-issue")
            except AssertionError as e:
                failures.append(e)          # re-raised below, whatever promote does with it
                raise
            return real_rollup(*a, **kw)

        with mock.patch.object(pm.metrics.estimates, "rollup_parent_estimate", racing_rollup):
            try:
                code, out, err = self.promote("BL-E001-001")
            except AssertionError:
                pass
        if failures:
            raise failures[0]
        _, rerr = procs[0].communicate(timeout=30)
        self.assertEqual(code, 0, err)
        self.assertEqual(procs[0].returncode, 0, rerr.decode())
        self.assertEqual(list(self.story()["resolves"]), ["BL-E001-001"])
        self.assertEqual(self.resolved_keys(), ["BL-E001-001"])      # the resolve ran after
        self.assertEqual(self.load_resolved()["resolved"][0].get("story"), "E001-S02-001")
        self.assert_invariants()

    def test_keys_split_across_stories_refuse_to_triage(self):
        self.append("A")
        self._crash_promote_before_scheduling()
        self.append("B", "001", "02")
        before = _tree_snapshot(self.d)
        code, _, err = self.promote("BL-E001-001", "BL-E001-002", extra=("--title", "Batch"))
        self.assertEqual(code, 2)
        self.assertIn("triage", err)
        self.assertEqual(_tree_snapshot(self.d), before)

    def test_two_live_stories_claiming_one_key_refuse_to_triage(self):
        # Spec §2.4: more than one story claims the key -> exit 2, pointing to triage (audit 1h),
        # nothing written. The second claimant is a hand-written node (a deliberately corrupt
        # state), once beside the first and once in another epic -- the walk covers every epic.
        self.append("A")
        self._crash_promote_before_scheduling()        # E001-S02-001 lists it; still backlog
        second = {"E001-S02-002": ("active", "epic-001", "sprint-02"),
                  "E005-S01-001": ("planned", "epic-005", "sprint-01")}
        for skey, where in second.items():
            p = os.path.join(self.root, *where, f"{skey}.yaml")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(f"key: '{skey}'\nepic: '{skey[:4]}'\nsprint: '{skey[5:8]}'\n"
                         f"status: backlog\nresolves: [BL-E001-001]\n")
            before = _tree_snapshot(self.d)
            code, out, err = self.promote("BL-E001-001")
            self.assertEqual(code, 2, (skey, out, err))
            self.assertIn(f"BL-E001-001 already claimed by ['E001-S02-001', '{skey}']", err)
            self.assertIn("run /l3io-doctor triage (audit-issues 1d/1h)", err)
            self.assertEqual(_tree_snapshot(self.d), before, skey)
            os.remove(p)

    def test_resume_refuses_when_the_claimant_lists_other_keys(self):
        self.append("A")
        self.append("B", "001", "02")
        self._crash_promote_before_scheduling(extra=("--key", "BL-E001-002", "--title", "Batch"))
        before = _tree_snapshot(self.d)
        code, _, err = self.promote("BL-E001-001")
        self.assertEqual(code, 2)
        self.assertIn("triage", err)
        self.assertEqual(_tree_snapshot(self.d), before)

    def test_resume_refuses_a_claimant_in_another_epic(self):
        """A retry naming a different --epic (or --sprint) must not resume a claimant
        elsewhere: its lock was never taken and its roll-up would target the wrong epic."""
        self.append("A")
        self._crash_promote_before_scheduling()                   # claimant E001-S02-001
        s3 = os.path.join(self.root, "active", "epic-001", "sprint-03", "sprint.yaml")
        os.makedirs(os.path.dirname(s3))
        with open(s3, "w", encoding="utf-8") as fh:              # a second backlog sprint
            fh.write("key: 'S03'\nepic: 'E001'\ntitle: 'Three'\nstatus: backlog\n")
        for epic, sprint in (("005", "01"), ("001", "03")):
            before = _tree_snapshot(self.d)
            code, out, err = self.promote("BL-E001-001", epic=epic, sprint=sprint)
            self.assertEqual(code, 2, (epic, sprint, out, err))
            self.assertIn("E001-S02-001", err)
            self.assertIn("--epic 001 --sprint 02", err)
            self.assertEqual(_tree_snapshot(self.d), before, (epic, sprint))
        code, out, err = self.promote("BL-E001-001")               # the named retry resumes
        self.assertEqual(code, 0, err)
        self.assertIn("(resumed)", out)
        self.assert_invariants()


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

    def test_actual_event_times_survives_an_unhashable_key(self):
        """`if k not in idx` raises on an unhashable k just as a subscript does -- a
        membership test is not the safe alternative to indexing."""
        for bad in self.BAD:
            with self.subTest(bad=bad):
                self.write({"ts": "2026-01-01T00:00:00+00:00", "event": "actual",
                            "node": "story", "key": bad},
                           {"ts": "2026-01-02T00:00:00+00:00", "event": "actual",
                            "node": "story", "key": "E001-S01-001"})
                self.assertIn("E001-S01-001", pm.actual_event_times(self.root))

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


class TestScheduleIssue(IssueBase):
    """`schedule-issue` attaches an open backlog key to a story that ALREADY EXISTS.

    Nothing could do this before. `repair-issue --action link` is gated on audit finding
    1d, which fires only when the story already names the key in `resolves` — so it
    repairs a half-finished scheduling and provably cannot create one. `promote-issue`
    only ever allocates a NEW story, so aiming it at an epic that already has the right
    story produces a second story claiming the same acceptance criteria.

    The asymmetry that made this invisible to us: stories created by `promote-issue`
    carry a populated `resolves`, and every fixture in this file created stories that
    way. A story authored in `epics.md` and imported carries `resolves: []`, which is
    the normal case for a project that plans in the artifact first — and exactly the
    case with no route to a backlog link. A consumer had 88 of 113 open items with no
    story and 28 with an unambiguous existing target.
    """

    def authored_story(self, story_key, status="backlog", resolves=None, epic_dir=None):
        """A story node as the ARTIFACT-FIRST path produces it: `resolves: []`.

        Hand-written on purpose. No verb creates a story with an empty `resolves`, so
        the real write path cannot produce this fixture — the same reason the
        pre-canonicalisation dispatch records had to be written as raw bytes. A fixture
        built only through our own current code can only ever test the states our own
        current code creates.
        """
        ek, sk, _ = pm.parse_story_key(story_key)
        d = os.path.join(self.root, epic_dir or "active", f"epic-{ek[1:]}",
                         f"sprint-{sk[1:]}")
        os.makedirs(d, exist_ok=True)
        body = [f"key: '{story_key}'", f"epic: '{ek}'", f"sprint: '{sk}'",
                "title: 'Authored in epics.md'", f"status: {status}",
                "classification: simple"]
        items = "[]" if not resolves else "[" + ", ".join(f"'{r}'" for r in resolves) + "]"
        body.append(f"resolves: {items}")
        p = os.path.join(d, f"{story_key}.yaml")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("\n".join(body) + "\n")
        return p

    def story_resolves(self, story_key):
        return [str(x) for x in (pm.load_node(pm.story_file(self.root, story_key))[1]
                                 .get("resolves") or [])]

    def schedule(self, key, story, *extra):
        return self.run_all(["schedule-issue", "--state-root", self.root,
                             "--key", key, "--story", story, *extra])

    def item(self, key):
        for i in (self.load_open().get("backlog") or []):
            if str(i["key"]) == key:
                return i
        return None

    def test_attaches_an_open_key_to_an_existing_authored_story(self):
        self.append("Marker left behind")
        k = self.open_keys()[0]
        self.authored_story("E001-S01-005")
        code, out, err = self.schedule(k, "E001-S01-005")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.story_resolves("E001-S01-005"), [k])
        it = self.item(k)
        self.assertEqual(str(it["status"]), "scheduled")
        self.assertEqual(str(it["story"]), "E001-S01-005")
        self.assertIn("scheduled_at", it)

    def test_appends_rather_than_replacing_an_existing_resolves_list(self):
        """A story may already resolve earlier items. Replacing the list would silently
        orphan them — they would still point at the story while the story stopped
        claiming them, which is audit finding 1e."""
        self.append("First")
        self.append("Second")
        k1, k2 = self.open_keys()[0], self.open_keys()[1]
        self.authored_story("E001-S01-005", resolves=[k1])
        code, out, err = self.schedule(k2, "E001-S01-005")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.story_resolves("E001-S01-005"), [k1, k2])

    def test_several_keys_in_one_call(self):
        self.append("A")
        self.append("B")
        ks = self.open_keys()[:2]
        self.authored_story("E001-S01-005")
        code, out, err = self.run_all(["schedule-issue", "--state-root", self.root,
                                       "--key", ks[0], "--key", ks[1],
                                       "--story", "E001-S01-005"])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.story_resolves("E001-S01-005"), ks)

    def test_is_idempotent_by_skip_and_says_so(self):
        """The consumer's 28-item mapping runs as a batch; they would rather re-run the
        whole thing than track which rows applied. A second run must be a no-op, not a
        refusal and not a duplicate entry in `resolves`."""
        self.append("Marker")
        k = self.open_keys()[0]
        self.authored_story("E001-S01-005")
        self.assertEqual(self.schedule(k, "E001-S01-005")[0], 0)
        code, out, err = self.schedule(k, "E001-S01-005")
        self.assertEqual(code, 0, out + err)
        self.assertIn("already", out)
        self.assertEqual(self.story_resolves("E001-S01-005"), [k])
        self.assertEqual(len(self.events("issue_scheduled")), 1)

    def test_refuses_a_story_that_does_not_exist(self):
        self.append("Marker")
        k = self.open_keys()[0]
        code, out, err = self.schedule(k, "E001-S01-404")
        self.assertEqual(code, 3, out + err)
        self.assertEqual(str(self.item(k)["status"]), "backlog")

    def test_refuses_a_done_story(self):
        """This is the failure the whole exercise started from: an item acquiring a home
        that will never be worked. A done story's acceptance criteria are already met and
        closed, so attaching an unfixed finding to it loses the finding."""
        self.append("Marker")
        k = self.open_keys()[0]
        self.authored_story("E001-S01-005", status="done")
        code, out, err = self.schedule(k, "E001-S01-005")
        self.assertEqual(code, 2, out + err)
        self.assertIn("done", (out + err))
        self.assertEqual(self.story_resolves("E001-S01-005"), [])
        self.assertEqual(str(self.item(k)["status"]), "backlog")

    def test_refuses_a_story_in_an_archived_epic(self):
        """Same failure by a different route, and the one a consumer hit by accident:
        34 open items keyed to an epic that had been archived. Status alone does not
        catch it — a story under archived/ can still read `status: backlog`."""
        self.append("Marker", epic="009")
        k = self.open_keys()[0]
        os.makedirs(os.path.join(self.root, "archived", "epic-009"), exist_ok=True)
        with open(os.path.join(self.root, "archived", "epic-009", "epic.yaml"),
                  "w", encoding="utf-8") as fh:
            fh.write("key: 'E009'\ntitle: 'Old'\nstatus: done\n")
        self.authored_story("E009-S01-002", epic_dir="archived")
        code, out, err = self.schedule(k, "E009-S01-002")
        self.assertEqual(code, 2, out + err)
        self.assertIn("archived", (out + err))
        self.assertEqual(str(self.item(k)["status"]), "backlog")

    def test_refuses_a_key_already_scheduled_to_a_different_story(self):
        """Silently moving it would rewrite a scheduling decision somebody made, and
        leave the old story's `resolves` pointing at an item it no longer owns."""
        self.append("Marker")
        k = self.open_keys()[0]
        self.authored_story("E001-S01-005")
        self.authored_story("E001-S01-006")
        self.assertEqual(self.schedule(k, "E001-S01-005")[0], 0)
        code, out, err = self.schedule(k, "E001-S01-006")
        self.assertEqual(code, 2, out + err)
        self.assertIn("E001-S01-005", (out + err))
        self.assertEqual(self.story_resolves("E001-S01-006"), [])

    def test_refuses_a_non_backlog_key(self):
        self.authored_story("E001-S01-005")
        code, out, err = self.schedule("not-a-key", "E001-S01-005")
        self.assertEqual(code, 2, out + err)

    def test_refuses_an_already_resolved_key(self):
        self.append("Marker")
        k = self.open_keys()[0]
        # --resolution fixed needs --ref (a story key or a commit SHA)
        rc, o, e = self.run_all(["resolve-issue", "--state-root", self.root, "--key", k,
                                 "--resolution", "fixed", "--ref", "E001-S01-001"])
        self.assertEqual(rc, 0, o + e)   # premise: the key really is resolved
        self.authored_story("E001-S01-005")
        code, out, err = self.schedule(k, "E001-S01-005")
        self.assertEqual(code, 2, out + err)
        self.assertIn("resolved", (out + err))

    def test_refuses_a_spec_item(self):
        """Spec items are confirmed or rejected in triage, never given a story — the
        same rule promote-issue enforces."""
        # a spec kind needs --ref (the docs(spec) SHA or the proposal path)
        rc, o, e = self.append("A spec change", "001", "01", "Low",
                               "code-review (E001-S01-001)",
                               "--kind", "spec-change", "--ref", "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0")
        self.assertEqual(rc, 0, o + e)   # premise: the spec item exists
        k = self.open_keys()[0]
        self.authored_story("E001-S01-005")
        code, out, err = self.schedule(k, "E001-S01-005")
        self.assertEqual(code, 2, out + err)

    def test_a_key_in_neither_issue_file_is_refused(self):
        """Distinct from an already-resolved key (which names its resolution) and from a
        malformed one (which is not a key at all): this is a well-formed key for an item
        that was never opened."""
        self.authored_story("E001-S01-005")
        code, _o, err = self.schedule("BL-E001-099", "E001-S01-005")
        self.assertEqual(code, 2)
        self.assertIn("is not an open backlog item", err)
        self.assertEqual(self.story_resolves("E001-S01-005"), [])

    def test_a_story_that_already_lists_the_key_is_not_appended_to_twice(self):
        """The finding-1d state: the story claims the key while the item is still backlog,
        which is what an interrupted promote leaves behind. Scheduling completes it, and the
        `resolves` entry must not be duplicated — a doubled entry is audit finding 1h."""
        self.append("First")
        k = self.open_keys()[0]
        self.authored_story("E001-S01-005", resolves=[k])
        code, out, err = self.schedule(k, "E001-S01-005")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.story_resolves("E001-S01-005"), [k], "appended twice")
        self.assertEqual(str(self.item(k).get("status")), "scheduled")

    def test_the_same_key_given_twice_is_deduped(self):
        """Characterisation, not a decision anyone recorded. Benign HERE because nothing in
        this verb keys off the number of keys — unlike promote-issue, whose `--title`
        requirement is `len(keys) > 1` and is therefore evaluated AFTER this dedup, so a
        repeated key silently skips a guard that exists to make multi-key promotion
        deliberate. Same code shape, different consequence; if that is ever made to refuse,
        decide both verbs together."""
        self.append("First")
        k = self.open_keys()[0]
        self.authored_story("E001-S01-005")
        code, out, err = self.run_all(["schedule-issue", "--state-root", self.root,
                                       "--key", k, "--key", k,
                                       "--story", "E001-S01-005"])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.story_resolves("E001-S01-005"), [k])

    def test_an_item_refusal_never_takes_the_epic_lock(self):
        """schedule-issue resolves its items twice — advisory before the epic lock, decisive
        under it. Deleting the advisory call leaves every refusal correct, so nothing else
        notices; the only observable difference is that the doomed call takes the epic lock
        on its way to failing, contending with whatever is working that epic."""
        self.append("A", "001", "01", "Low", "code-review (E001-S01-001)",
                    "--kind", "spec-change", "--ref", "deadbeef1234")
        self.authored_story("E001-S01-005")
        lock = pm.epic_lock_path(self.root, "E001")
        self.assertFalse(os.path.exists(lock), "precondition: no epic lock yet")
        code, _o, err = self.schedule(self.open_keys()[0], "E001-S01-005")
        self.assertEqual(code, 2, err)
        self.assertFalse(os.path.exists(lock),
                         "the advisory items pass must refuse before the epic lock")

    def test_a_bad_story_is_refused_before_ANY_lock_is_taken(self):
        """The SECOND advisory pass, and the only refusal in this verb that touches no lock
        at all. `_schedule_target` runs before `issues_lock` is even entered, so a story that
        does not exist is refused without opening issues.yaml. Measured with it removed: the
        call falls through, takes the issues lock, takes the epic lock, and only then fails
        at the decisive check — so BOTH are asserted here, not just the issues one.

        The item must be a plain defect. A spec-kind item is refused by `_schedulable_items`
        inside the issues lock but before the epic lock, which masks the second half of the
        effect and is how this was first mis-measured."""
        self.append("A")
        # append-issue took the issues lock itself, so its file exists from fixture setup.
        # Clear every lock: the claim is that THIS call takes none, not that none has ever
        # been taken.
        for dp, _, files in os.walk(self.d):
            for f in files:
                if f.endswith(".lock"):
                    os.remove(os.path.join(dp, f))
        code, _o, err = self.schedule(self.open_keys()[0], "E001-S01-099")
        self.assertEqual(code, 3, err)
        # Asserted as a SET, not as two named paths: naming them can only check the locks
        # this test's author thought of, and the claim is that no lock at all is taken.
        left = [f for dp, _, fs in os.walk(self.d) for f in fs if f.endswith(".lock")]
        self.assertEqual(left, [], "refused before any lock is taken")

    def test_the_event_names_how_the_scheduling_happened(self):
        """promote-issue writes no `via`, repair-link writes via=repair-link. A third
        route needs its own value or the log cannot say how an item got its story."""
        self.append("Marker")
        k = self.open_keys()[0]
        self.authored_story("E001-S01-005")
        self.assertEqual(self.schedule(k, "E001-S01-005")[0], 0)
        evs = self.events("issue_scheduled")
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].get("via"), "schedule")
        self.assertEqual(evs[0].get("story"), "E001-S01-005")

    def test_a_refusal_writes_nothing_at_all(self):
        """Every refusal is checked before the first write, as promote-issue does: a
        partial apply across two files is the one outcome with no clean recovery."""
        self.append("Marker")
        k = self.open_keys()[0]
        self.authored_story("E001-S01-005", status="done")
        before = len(self.events())
        self.assertEqual(self.schedule(k, "E001-S01-005")[0], 2)
        self.assertEqual(len(self.events()), before)
        self.assertEqual(self.story_resolves("E001-S01-005"), [])


class TestEpicWritersHoldTheEpicLock(IssueBase):
    """Every epic.yaml read-modify-write holds epic_node_lock (batch D1).

    While this test holds E001's lock, every writer of E001's epic.yaml must wait. Each one
    runs as a real subprocess, because the lock's re-entrancy counter is per process. A
    directory move that lands while they wait must not strand them: each re-resolves the epic
    under the lock and writes into the moved directory, never into a recreated ghost of the
    old one. The lock file lives outside the epic directory, which is why a move cannot
    carry it away from a waiter."""

    @unittest.skipUnless(os.path.exists("/proc/locks"), "needs /proc/locks to see a flock waiter")
    def test_every_epic_writer_waits_and_follows_a_move(self):
        import subprocess
        self.append("A")
        sr = self.root
        _fx_set_lock(sr, "E001", "me")
        for argv in (["set-estimate", "--state-root", sr, "--epic", "E001",
                      "--man-hours-low", "1", "--man-hours-high", "2"],
                     ["import-node", "--state-root", sr, "--story", "E001-S01-001",
                      "--status", "done"],
                     ["set-estimate", "--state-root", sr, "--story", "E001-S01-001",
                      "--man-hours", "2"]):
            code, _, err = self.run_all(argv)
            self.assertEqual(code, 0, err)
        writers = {
            "set-estimate": ["set-estimate", "--state-root", sr, "--epic", "001",
                             "--man-hours-low", "4", "--man-hours-high", "5"],
            "set-actual": ["set-actual", "--state-root", sr, "--node", "epic", "--epic", "001",
                           "--man-hours", "3"],
            "estimate-rollup": ["estimate-rollup", "--state-root", sr, "--epic", "001"],
            "promote-issue": ["promote-issue", "--state-root", sr, "--artifacts-root", self.arts,
                              "--key", "BL-E001-001", "--epic", "001", "--sprint", "02",
                              "--classification", "standard", "--session-id", "me"],
        }
        epic_yaml = pm.nodes.epic_file(sr, "E001")
        with open(epic_yaml, "rb") as fh:
            before = fh.read()
        procs = {}
        lock = pm.epic_lock_path(sr, "E001")
        with pm.epic_node_lock(sr, "E001"):
            for name, argv in writers.items():
                procs[name] = subprocess.Popen([sys.executable, SCRIPT, *argv],
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.addCleanup(procs[name].kill)            # reaps on failure; no-op once done
            for name, p in procs.items():   # deterministic: each seen blocked, or it exited first
                _wait_until_blocked_on(p, lock, name)
            with open(epic_yaml, "rb") as fh:
                during = fh.read()
            _fx_move_epic(sr, "E001", "planned")             # while every writer waits
        results = {n: (p.communicate(timeout=60), p.returncode) for n, p in procs.items()}
        self.assertEqual(during, before)
        for name, ((out, err), rc) in results.items():
            self.assertEqual(rc, 0, f"{name}: {out.decode()} {err.decode()}")
        self.assertFalse(os.path.exists(os.path.join(sr, "active", "epic-001")),
                         "a writer recreated the epic's old directory after the move")
        path = pm.nodes.epic_file(sr, "E001")
        self.assertTrue(path.endswith(os.path.join("planned", "epic-001", "epic.yaml")), path)
        node = pm.load_node(path)[1]
        self.assertEqual(float(node["actual"]["man_hours"]), 3.0)
        self.assertIn("estimate", node)
        self.assertTrue(os.path.exists(os.path.join(sr, "planned", "epic-001", "sprint-02",
                                                    "E001-S02-001.yaml")))


class TestEpicNodeLockScope(unittest.TestCase):
    """The epic lock's reach, attacked directly (batch D1): the rule is enforced at the one
    write chokepoint (`_atomic_dump`), so these plant writes by routes the verbs never
    take, rather than trusting the verb inventory to be complete."""

    # TestLayoutResolution's tree, without inheriting (and so re-running) its tests.
    setUp = TestLayoutResolution.setUp
    tearDown = TestLayoutResolution.tearDown

    def _touch(self, path):
        y, node = pm.load_node(path)
        node["touched"] = True
        pm.nodes.save_node(y, node, path)

    def test_an_epic_yaml_write_without_the_lock_is_refused_on_every_route(self):
        path = pm.nodes.epic_file(self.root, "E001")
        with open(path, "rb") as fh:
            before = fh.read()
        y, node = pm.load_node(path)
        routes = {"save_node": lambda: pm.nodes.save_node(y, node, path),
                  "save_node(use_flock)": lambda: pm.nodes.save_node(y, node, path, use_flock=True),
                  "_atomic_dump": lambda: pm.core._atomic_dump(y, node, path),
                  "_mark_sampled": lambda: pm._mark_sampled(node, path, y)}
        for name, route in routes.items():
            with self.assertRaises(RuntimeError, msg=name):
                route()
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), before)

    def test_another_epics_lock_does_not_cover_the_write(self):
        with pm.epic_node_lock(self.root, "E005"), self.assertRaises(RuntimeError):
            self._touch(pm.nodes.epic_file(self.root, "E001"))

    def test_the_same_epic_under_any_spelling_covers_the_write(self):
        with pm.epic_node_lock(os.path.relpath(self.root), "1"):    # relative root, bare key
            self._touch(pm.nodes.epic_file(self.root, "E001"))
        self.assertTrue(pm.load_node(pm.nodes.epic_file(self.root, "E001"))[1]["touched"])

    def test_sprint_and_story_nodes_are_not_gated(self):
        self._touch(pm.sprint_file(self.root, "E001", "S01"))
        self._touch(pm.story_file(self.root, "E001-S01-003"))

    def test_reentry_on_the_same_epic_nests_without_a_second_flock(self):
        with pm.epic_node_lock(self.root, "E001"):
            fh = pm._EPIC_NODE_LOCK["fh"]
            with pm.epic_node_lock(self.root, "001"):
                self.assertEqual(pm._EPIC_NODE_LOCK["depth"], 2)
                self.assertIs(pm._EPIC_NODE_LOCK["fh"], fh)
                self._touch(pm.nodes.epic_file(self.root, "E001"))
            self.assertEqual(pm._EPIC_NODE_LOCK["depth"], 1)
        self.assertEqual(pm._EPIC_NODE_LOCK["depth"], 0)

    def test_a_second_epics_lock_cannot_nest(self):
        # The re-entrancy counter is per lock family, so a nested second epic's lock would
        # silently skip its flock -- refused outright instead.
        with pm.epic_node_lock(self.root, "E001"):
            with self.assertRaises(RuntimeError), pm.epic_node_lock(self.root, "E005"):
                pass
            self._touch(pm.nodes.epic_file(self.root, "E001"))     # the outer hold survives
        self.assertEqual(pm._EPIC_NODE_LOCK["depth"], 0)

    def test_the_lock_file_is_outside_the_epic_directory_and_survives_a_move(self):
        lock = pm.epic_lock_path(self.root, "E001")
        with pm.epic_node_lock(self.root, "E001"):
            pass
        self.assertTrue(os.path.exists(lock))
        self.assertFalse(os.path.realpath(lock).startswith(
            os.path.realpath(pm.find_epic_dir(self.root, "E001")) + os.sep))
        _fx_move_epic(self.root, "E001", "archived")
        self.assertEqual(pm.epic_lock_path(self.root, "E001"), lock)
        self.assertTrue(os.path.exists(lock))

    def test_a_fresh_epic_lock_under_issues_or_calibration_lock_is_refused(self):
        # Lock order: epic_node_lock is taken first, never under issues_lock or
        # calibration_lock -- the reverse of promote's epic -> issues is a deadlock.
        outers = {"issues_lock": lambda: pm.issues_lock(pm.issues_paths(self.root)[0]),
                  "calibration_lock": lambda: pm.calibration_lock(self.root)}
        for name, outer in outers.items():
            with outer():
                with self.assertRaises(RuntimeError, msg=name) as cm:
                    with pm.epic_node_lock(self.root, "E001"):
                        pass
                self.assertIn("lock order", str(cm.exception), name)
            self.assertEqual(pm._EPIC_NODE_LOCK["depth"], 0, name)
            self.assertIsNone(pm._EPIC_NODE_LOCK["path"], name)

    def test_same_epic_reentry_under_issues_lock_is_allowed(self):
        # promote's shape: epic lock, then issues_lock, then the roll-up re-enters the epic.
        with pm.epic_node_lock(self.root, "E001"):
            with pm.issues_lock(pm.issues_paths(self.root)[0]):
                with pm.epic_node_lock(self.root, "001"):
                    self._touch(pm.nodes.epic_file(self.root, "E001"))

    def test_set_actual_cost_is_refused_before_the_epic_lock(self):
        # --cost is a usage error on any node, so it is refused before the epic lock: it
        # neither waits behind a holder nor creates the lock file.
        path = pm.nodes.epic_file(self.root, "E001")
        with open(path, "rb") as fh:
            before = fh.read()
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            with self.assertRaises(SystemExit) as cm:
                pm.main(["set-actual", "--state-root", self.root, "--node", "epic",
                         "--epic", "E001", "--man-hours", "1", "--cost", "5"])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("--cost is not accepted", err.getvalue())
        self.assertFalse(os.path.exists(pm.epic_lock_path(self.root, "E001")))
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), before)


class TestConcurrentPromote(unittest.TestCase):
    N = 4

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.arts = os.path.join(self.d, "impl")
        self.root = os.path.join(self.arts, "state")
        _build_issue_tree(self.root)
        for i in range(1, self.N + 1):
            with redirect_stdout(io.StringIO()):
                pm.main(["append-issue", "--state-root", self.root, "--epic", "001", "--sprint",
                         "01", "--title", f"t{i}", "--source", "qa", "--severity", "Low"])

    def test_parallel_promotes_get_distinct_stories_and_a_complete_rollup(self):
        import subprocess
        procs = [subprocess.Popen([sys.executable, SCRIPT, "promote-issue", "--state-root",
                                   self.root, "--artifacts-root", self.arts, "--key",
                                   f"BL-E001-{i:03d}", "--epic", "001", "--sprint", "02",
                                   "--classification", "simple"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(1, self.N + 1)]
        for p in procs:
            _, err = p.communicate(timeout=180)
            self.assertEqual(p.returncode, 0, err.decode())
        stories = pm.list_story_files(self.root, "E001", "S02")
        self.assertEqual(len(stories), self.N)
        after_race = dict(pm.load_node(pm.nodes.epic_file(self.root, "E001"))[1]["estimate"])
        with redirect_stderr(io.StringIO()):
            pm.metrics.estimates.rollup_parent_estimate(self.root, "E001", pm.DEFAULT_ESTIMATE_MODEL, None)
        fresh = dict(pm.load_node(pm.nodes.epic_file(self.root, "E001"))[1]["estimate"])
        self.assertEqual(after_race["man_hours_low"], fresh["man_hours_low"],
                         "the last roll-up saved during the race missed a story")


class TestAuditIssues(IssueBase):
    def audit(self):
        code, out, err = self.run_all(["audit-issues", "--state-root", self.root,
                                       "--format", "json"])
        self.assertIn(code, (0, 4), err)
        return code, json.loads(out)["findings"]

    def found(self, fid, key):
        code, findings = self.audit()
        self.assertEqual(code, 4)
        self.assertIn((fid, key), {(f["id"], f["key"]) for f in findings}, findings)

    def promote(self, key="BL-E001-001", epic="001", sprint="02"):
        code, _, err = self.run_all(["promote-issue", "--state-root", self.root,
                                     "--artifacts-root", self.arts, "--key", key, "--epic", epic,
                                     "--sprint", sprint, "--classification", "simple"])
        self.assertEqual(code, 0, err)

    def edit_story(self, key, fn):
        p = pm.story_file(self.root, key)
        y, n = pm.load_node(p)
        fn(n)
        pm.nodes.save_node(y, n, p)

    def edit_open(self, fn):
        y, data = pm.core._load(self.issues)
        fn(data)
        pm.core._atomic_dump(y, data, self.issues)

    def test_clean_lifecycle_exits_0(self):
        self.append("A")
        self.promote()
        self.finish()
        self.assertEqual(self.audit(), (0, []))

    def test_missing_state_root_is_clean(self):
        code, out, _ = self.run_all(["audit-issues", "--state-root",
                                     os.path.join(self.d, "nope")])
        self.assertEqual(code, 0)

    def test_json_format_reports_a_malformed_issue_file(self):
        """Triage T2 and health-check Check 13 parse this JSON: a malformed file must still
        yield a parseable document carrying the error, with exit 4."""
        with open(self.issues, "w", encoding="utf-8") as fh:
            fh.write("backlog: oops\n")
        code, out, err = self.run_all(["audit-issues", "--state-root", self.root,
                                       "--format", "json"])
        self.assertEqual(code, 4, err)
        doc = json.loads(out)
        self.assertEqual(doc["findings"], [])
        self.assertIn("malformed 'backlog'", doc["error"])
        code, out, err = self.run_all(["audit-issues", "--state-root", self.root])
        self.assertEqual((code, out), (4, ""))                  # text mode is unchanged
        self.assertIn("malformed 'backlog'", err)

    def test_audit_without_issue_files_leaves_no_lock_file(self):
        code, _ = self.audit()
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(self.issues + ".lock"),
                         "a read-only command left a lock file behind")

    def test_1a_key_in_both_files(self):
        self.append("A")
        with _dump_failing_on(2):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with self.assertRaises(OSError):
                    pm.main(["resolve-issue", "--state-root", self.root, "--key",
                             "BL-E001-001", "--resolution", "obsolete", "--note", "x"])
        self.found("1a", "BL-E001-001")

    def test_1b_scheduled_to_a_missing_story(self):
        self.append("A")
        self.promote()
        os.remove(pm.story_file(self.root, "E001-S02-001"))
        self.found("1b", "BL-E001-001")

    def test_1b_resolves_names_an_unknown_key(self):
        self.append("A")
        self.promote()
        self.edit_story("E001-S02-001", lambda n: n["resolves"].append("BL-E001-050"))
        self.found("1b", "BL-E001-050")

    def test_1c_done_story_with_item_still_open(self):
        self.append("A")
        self.promote()
        self.edit_story("E001-S02-001", lambda n: n.__setitem__("status", "done"))  # hook bypassed
        self.found("1c", "BL-E001-001")

    def test_1d_promote_stopped_before_scheduling(self):
        self.append("A")
        self._crash_promote_before_scheduling(cls="simple")
        self.found("1d", "BL-E001-001")

    def test_1e_stale_next(self):
        self.append("A")
        self.append("B", "001", "02")
        self.edit_open(lambda d: d["next"].__setitem__("001", 1))
        self.found("1e", "BL-E001")

    def test_1f_bad_open_status(self):
        self.append("A")
        self.edit_open(lambda d: d["backlog"][0].__setitem__("status", "weird"))
        self.found("1f", "BL-E001-001")

    def test_1g_scheduled_to_an_archived_story_that_never_finished(self):
        self.append("Later", "005", "01", "Low", "qa (Q-1)")
        self.promote("BL-E005-001", "005", "01")
        _fx_move_epic(self.root, "E005", "archived")
        self.found("1g", "BL-E005-001")

    def test_1h_two_stories_claim_one_item(self):
        self.append("A")
        self.promote()
        p = os.path.join(self.root, "active", "epic-001", "sprint-02", "E001-S02-002.yaml")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("key: 'E001-S02-002'\nepic: 'E001'\nsprint: 'S02'\nstatus: backlog\n"
                     "resolves: [BL-E001-001]\n")
        self.found("1h", "BL-E001-001")

    def test_1i_duplicate_key_in_a_file(self):
        self.append("A")
        from ruamel.yaml.comments import CommentedMap
        self.edit_open(lambda d: d["backlog"].append(CommentedMap(d["backlog"][0])))
        self.found("1i", "BL-E001-001")

    def test_1j_story_reverted_after_done(self):
        self.append("A")
        self.promote()
        self.finish()
        _fx_set_status(self.root, "in-progress", story="E001-S02-001")
        self.found("1j", "BL-E001-001")

    def rekey_story(self, old, new):
        """Leave the residue a re-key produces: the story carries `new` and records `old` in
        previous_keys, and every backlog field still names `old`. Built by hand rather than
        by a 3.x re-key, because a re-key only moved PLANNED stories and `promote`
        lands its story under active/ -- and because the residue is what matters here, not
        the operation that produced it (3.3.0-3.4.1 produced it by crashing mid-write)."""
        p = pm.story_file(self.root, old)
        y, n = pm.load_node(p)
        n["key"] = new
        n["previous_keys"] = [old]
        pm.nodes.save_node(y, n, p)
        os.rename(p, os.path.join(os.path.dirname(p), f"{new}.yaml"))

    def test_1l_a_scheduled_item_left_on_a_re_keyed_story(self):
        """A scheduled item left naming a key no story carries any more, where exactly one
        story records that key in previous_keys."""
        self.append("A")
        self.promote()
        self.rekey_story("E001-S02-001", "E001-S02-009")
        self.found("1l", "BL-E001-001")
        f = next(x for x in self.audit()[1] if x["id"] == "1l")
        self.assertEqual(f["story"], "E001-S02-009", "the finding must name the heir")
        self.assertIn("repoint", f["repair"])

    def test_1l_displaces_1b_when_the_old_key_has_an_heir(self):
        """1b's only repair is `unschedule`, which DISCARDS the scheduling. Emitting both
        would hand triage two repairs that undo each other, and the lossy one first."""
        self.append("A")
        self.promote()
        self.rekey_story("E001-S02-001", "E001-S02-009")
        self.assertNotIn(("1b", "BL-E001-001"), {(f["id"], f["key"]) for f in self.audit()[1]})

    def test_a_dangling_key_no_story_records_is_1b_only_not_1l(self):
        """A deleted story is the ordinary shape of a dangling key, not re-key residue, and
        `unschedule` is the right answer precisely because there is no key to point at
        instead. Emitting 1l as well would put a second, repairless finding on every one."""
        self.append("A")
        self.promote()
        os.remove(pm.story_file(self.root, "E001-S02-001"))
        self.assertEqual([(f["id"], f["key"]) for f in self.audit()[1]],
                         [("1b", "BL-E001-001")])

    def test_1l_ignores_a_ref_that_is_not_a_story_key(self):
        """`ref` is overloaded: a spec-change item's ref is a commit SHA or a proposal
        path, and neither is a broken story pointer."""
        self.append("A", "001", "01", "Low", "code-review", "--kind", "spec-change",
                    "--ref", "deadbeef1234")
        self.assertEqual(self.audit(), (0, []))

    def test_1l_ignores_a_key_that_still_names_a_live_story(self):
        self.append("A")
        self.promote()
        self.edit_story("E001-S02-001", lambda n: n.__setitem__("previous_keys",
                                                                ["E001-S02-001"]))
        self.assertNotIn("1l", {f["id"] for f in self.audit()[1]})

    def test_text_format_names_the_repair(self):
        self.append("A")
        self.edit_open(lambda d: d["backlog"][0].__setitem__("status", "weird"))
        code, out, _ = self.run_all(["audit-issues", "--state-root", self.root])
        self.assertEqual(code, 4)
        self.assertIn("1f", out)
        self.assertIn("repair:", out)

    def _crash_resolve_before_open_save(self, key="BL-E001-001"):
        """resolve-issue with its second write failing: the key is left in BOTH files (1a)."""
        with _dump_failing_on(2):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with self.assertRaises(OSError):
                    pm.main(["resolve-issue", "--state-root", self.root, "--key", key,
                             "--resolution", "obsolete", "--note", "x"])

    def test_a_key_in_both_files_is_audited_only_for_1a(self):
        """Ruling 8, resolved first: the stale open copy is not evaluated (here it looks 1d)."""
        self.append("A")
        self._crash_promote_before_scheduling(cls="simple")     # story lists it, item backlog
        self._crash_resolve_before_open_save()
        _, findings = self.audit()
        self.assertEqual([(f["id"], f["key"]) for f in findings], [("1a", "BL-E001-001")])

    def test_a_duplicated_key_is_reported_only_as_1i(self):
        """An ambiguous key is never evaluated through an arbitrary copy (single_open)."""
        from ruamel.yaml.comments import CommentedMap
        self.append("A")

        def dup_weird_first(d):
            c = CommentedMap(d["backlog"][0])
            c["status"] = "weird"
            d["backlog"].insert(0, c)
        self.edit_open(dup_weird_first)
        _, findings = self.audit()
        self.assertEqual([(f["id"], f["key"]) for f in findings], [("1i", "BL-E001-001")])


class TestRepairIssue(TestAuditIssues):
    """Inherits TestAuditIssues' helpers, so each corrupt state is built the same way
    the audit test proved it detectable. The inherited audit tests run again here too;
    that is harmless and keeps the fixture code in one place."""

    def repair(self, key, action, *extra):
        return self.run_all(["repair-issue", "--state-root", self.root, "--key", key,
                             "--action", action, *extra])

    def ids(self):
        return {(f["id"], f["key"]) for f in self.audit()[1]}

    def test_legacy_deferred_is_named_as_such_with_an_actionable_repair(self):
        """Pre-3.0, `deferred` WAS the resting state for a deliberate deferral. Since
        OPEN_ISSUE_STATUSES narrowed to (backlog, scheduled), every one of them became an
        undifferentiated 1f with repair "report only" -- 453 of them on a real project,
        so triage produced 453 findings and zero applicable repairs and completed having
        done nothing, with no indication the cause was a schema migration."""
        self.append("A")
        self.edit_open(lambda d: d["backlog"][0].__setitem__("status", "deferred"))
        f = [x for x in self.audit()[1] if x["id"] == "1f" and x["key"] == "BL-E001-001"]
        self.assertEqual(len(f), 1, self.audit()[1])
        self.assertIn("legacy", f[0]["detail"])
        self.assertIn("normalize-status", f[0]["repair"],
                      "a legacy status must name its repair, not say 'report only'")

    def test_normalize_status_maps_legacy_deferred_to_backlog(self):
        self.append("A")
        self.edit_open(lambda d: d["backlog"][0].__setitem__("status", "deferred"))
        code, _, err = self.repair("BL-E001-001", "normalize-status")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.load_open()["backlog"][0]["status"], "backlog")
        self.assertNotIn(("1f", "BL-E001-001"), self.ids())
        self.assert_invariants()

    def test_normalize_status_refuses_an_already_valid_status(self):
        """The gate every repair action carries: refuse unless its finding holds."""
        self.append("A")
        code, _, _ = self.repair("BL-E001-001", "normalize-status")
        self.assertEqual(code, 2)
        self.assertEqual(self.load_open()["backlog"][0]["status"], "backlog")

    def test_normalize_status_refuses_an_unknown_status(self):
        """An unrecognised status is not a known legacy value, so there is no safe
        mapping; it stays report-only rather than being guessed into backlog."""
        self.append("A")
        self.edit_open(lambda d: d["backlog"][0].__setitem__("status", "banana"))
        code, _, _ = self.repair("BL-E001-001", "normalize-status")
        self.assertEqual(code, 2)
        self.assertEqual(self.load_open()["backlog"][0]["status"], "banana")
        f = [x for x in self.audit()[1] if x["id"] == "1f"]
        self.assertIn("report only", f[0]["repair"])

    def test_all_legacy_normalizes_every_legacy_item_in_one_pass(self):
        """452 items one-at-a-time is 452 subprocesses each taking the lock, inside a
        per-item confirmation loop -- reported back from a real upgrade as impractical."""
        for t in ("A", "B", "C"):
            self.append(t)
        # All three legacy: a project with NO surviving `backlog` item, which is the only case
        # the mapping is safe for. Leaving one as `backlog` would be coexistence, and the
        # coexistence gate refuses it -- see test_normalize_refuses_when_backlog_and_deferred_COEXIST.
        self.edit_open(lambda d: [it.__setitem__("status", "deferred") for it in d["backlog"]])
        code, out, err = self.run_all(["repair-issue", "--state-root", self.root,
                                       "--action", "normalize-status", "--all-legacy"])
        self.assertEqual(code, 0, err)
        self.assertIn("3 normalized to backlog", out)
        self.assertEqual([str(i["status"]) for i in self.load_open()["backlog"]],
                         ["backlog", "backlog", "backlog"])
        self.assertEqual(len(self.events("issue_status_normalized")), 3)
        self.assert_invariants()

    def test_all_legacy_leaves_an_unrecognised_status_alone(self):
        """Batching must not sweep along a status the single-key gate would refuse."""
        self.append("A")
        self.append("B")
        self.edit_open(lambda d: [d["backlog"][0].__setitem__("status", "deferred"),
                                  d["backlog"][1].__setitem__("status", "banana")])
        code, out, err = self.run_all(["repair-issue", "--state-root", self.root,
                                       "--action", "normalize-status", "--all-legacy"])
        self.assertEqual(code, 0, err)
        self.assertIn("1 normalized to backlog", out)
        self.assertEqual([str(i["status"]) for i in self.load_open()["backlog"]],
                         ["backlog", "banana"])

    def test_all_legacy_with_nothing_to_do_is_a_clean_no_op(self):
        self.append("A")
        code, out, err = self.run_all(["repair-issue", "--state-root", self.root,
                                       "--action", "normalize-status", "--all-legacy"])
        self.assertEqual(code, 0, err)
        self.assertIn("no legacy status found", out)
        self.assertEqual(self.events("issue_status_normalized"), [])

    def test_repoint_restores_a_scheduling_a_re_key_orphaned(self):
        """Repoint is the only verb that restores this: `update-issue` changes severity
        only, `link` is gated on 1d (which does not hold -- the item is already scheduled),
        and `unschedule` drops the link rather than repairing it."""
        self.append("A")
        self.promote()
        self.rekey_story("E001-S02-001", "E001-S02-009")
        code, out, err = self.repair("BL-E001-001", "repoint")
        self.assertEqual(code, 0, err)
        self.assertIn("story E001-S02-001 -> E001-S02-009", out)
        it = self.load_open()["backlog"][0]
        self.assertEqual((str(it["story"]), str(it["status"])), ("E001-S02-009", "scheduled"),
                         "the scheduling is restored, not discarded")
        self.assertEqual(self.ids(), set(), "the repair must leave a clean audit")
        self.assertEqual(len(self.events("issue_repointed")), 1)
        self.assert_invariants()

    def test_repoint_fixes_a_stale_ref_on_a_resolved_item(self):
        """A resolved entry's `ref` is what fixed the item -- the field a re-key invalidates
        most often, because resolution outlives the story's placement."""
        self.append("A")
        self.promote()
        # A resolved item records ref = the story key. That is the field the later re-key
        # invalidates.
        self.finish()
        self.rekey_story("E001-S02-001", "E001-S02-009")
        code, out, err = self.repair("BL-E001-001", "repoint")
        self.assertEqual(code, 0, err)
        entry = self.load_resolved()["resolved"][0]
        self.assertEqual(str(entry["ref"]), "E001-S02-009")
        self.assertEqual(self.ids(), set())
        self.assert_invariants()

    def test_repoint_refuses_when_nothing_records_the_old_key(self):
        """A key no story carries is never guessed at -- that state is 1b, and its repair
        is unschedule."""
        self.append("A")
        self.promote()
        os.remove(pm.story_file(self.root, "E001-S02-001"))
        before = self.load_open()["backlog"][0]["story"]
        code, _, err = self.repair("BL-E001-001", "repoint")
        self.assertEqual(code, 2)
        self.assertIn("1l does not hold", err)
        self.assertEqual(self.load_open()["backlog"][0]["story"], before, "nothing written")

    def test_repoint_refuses_when_1l_does_not_hold(self):
        """The gate every repair action carries."""
        self.append("A")
        self.promote()
        code, _, err = self.repair("BL-E001-001", "repoint")
        self.assertEqual(code, 2)
        self.assertIn("1l does not hold", err)

    def test_repoint_refuses_an_ambiguous_old_key(self):
        """Two stories recording the same previous key cannot both be the heir, so 1l is
        report-only and the repair must refuse rather than pick the first."""
        self.append("A")
        self.promote()
        self.rekey_story("E001-S02-001", "E001-S02-009")
        p = os.path.join(self.root, "active", "epic-001", "sprint-02", "E001-S02-010.yaml")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("key: 'E001-S02-010'\nepic: 'E001'\nsprint: 'S02'\nstatus: backlog\n"
                     "previous_keys: ['E001-S02-001']\n")
        f = next(x for x in self.audit()[1] if x["id"] == "1l")
        self.assertIn("report only", f["repair"])
        code, _, err = self.repair("BL-E001-001", "repoint")
        self.assertEqual(code, 2, err)

    def _archive_epic(self, epic="001"):
        """Put the item's epic in archived/, i.e. status done."""
        # IssueBase._build_issue_tree already creates E001, and import-node is idempotent
        # by skip -- so this must MOVE the existing epic, not try to create an archived one.
        _fx_move_epic(self.root, f"E{epic}", "archived")

    def test_legacy_item_behind_an_ARCHIVED_epic_resolves_as_deferred(self):
        """The finding that made the blanket mapping wrong. `deferred` was a DISPOSITION;
        `backlog` means undecided. Behind a closed epic the mapping turned "we decided" into
        "nobody decided", and a real project's guard against closing an epic over an undecided
        finding went red. A resolution CAN hold the decision, so that is where it goes."""
        self.append("A")
        self._archive_epic("001")
        self.edit_open(lambda d: d["backlog"][0].__setitem__("status", "deferred"))
        code, out, err = self.run_all(["repair-issue", "--state-root", self.root,
                                       "--action", "normalize-status", "--all-legacy"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.open_keys(), [], "it must leave the open list")
        self.assertEqual(self.resolved_keys(), ["BL-E001-001"])
        entry = self.load_resolved()["resolved"][-1]
        self.assertEqual(str(entry["resolution"]), "deferred")
        self.assertTrue(str(entry.get("note", "")).strip(),
                        "the resolution must say why, not just assert one")

    def test_legacy_item_behind_an_OPEN_epic_becomes_backlog(self):
        """Behind an open epic the loss is harmless -- the item is open either way -- so the
        original mapping is still right and nothing is resolved."""
        self.append("A")
        if "planned" in pm.find_epic_dir(self.root, "E001"):
            _fx_move_epic(self.root, "E001", "active")
        self.edit_open(lambda d: d["backlog"][0].__setitem__("status", "deferred"))
        code, out, err = self.run_all(["repair-issue", "--state-root", self.root,
                                       "--action", "normalize-status", "--all-legacy"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.open_keys(), ["BL-E001-001"])
        self.assertEqual(str(self.load_open()["backlog"][0]["status"]), "backlog")
        self.assertEqual(self.resolved_keys(), [])

    def test_coexistence_no_longer_refuses_once_the_split_is_epic_aware(self):
        """The blanket refusal existed because the mapping could not tell the two cases
        apart. It can now, so a mixed backlog is handled rather than rejected."""
        self.append("A")
        self.append("B")
        self._archive_epic("001")
        self.edit_open(lambda d: d["backlog"][0].__setitem__("status", "deferred"))
        code, out, err = self.run_all(["repair-issue", "--state-root", self.root,
                                       "--action", "normalize-status", "--all-legacy"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.resolved_keys(), ["BL-E001-001"])
        self.assertEqual(self.open_keys(), ["BL-E001-002"])

    def test_an_item_whose_epic_has_no_state_node_is_left_alone(self):
        """No epic directory means the status cannot be established. Guessing either way is
        the error this whole change exists to avoid, so it is reported and skipped."""
        self.append("A", epic="099")          # the fixture creates no E099 node
        self.edit_open(lambda d: d["backlog"][0].__setitem__("status", "deferred"))
        code, out, err = self.run_all(["repair-issue", "--state-root", self.root,
                                       "--action", "normalize-status", "--all-legacy"])
        self.assertEqual(code, 0, err)
        self.assertEqual(str(self.load_open()["backlog"][0]["status"]), "deferred",
                         "an item whose epic status is unknown must not be rewritten")
        self.assertIn("skipped", out.lower() + err.lower())

    def test_normalize_proceeds_when_no_backlog_item_coexists(self):
        """All-legacy is the unambiguous case: nothing distinguishes them, so nothing is lost."""
        self.append("A")
        self.append("B")
        self.edit_open(lambda d: [d["backlog"][0].__setitem__("status", "deferred"),
                                  d["backlog"][1].__setitem__("status", "deferred")])
        code, out, err = self.run_all(["repair-issue", "--state-root", self.root,
                                       "--action", "normalize-status", "--all-legacy"])
        self.assertEqual(code, 0, err)
        self.assertEqual([str(i["status"]) for i in self.load_open()["backlog"]],
                         ["backlog", "backlog"])

    def test_a_scheduled_item_does_not_count_as_coexistence(self):
        """`scheduled` is a scheduling state, not the undecided resting state, so it does not
        evidence a deferred-vs-backlog distinction."""
        self.append("A")
        self.append("B")
        self.edit_open(lambda d: [d["backlog"][0].__setitem__("status", "deferred"),
                                  d["backlog"][1].__setitem__("status", "scheduled")])
        code, _, err = self.run_all(["repair-issue", "--state-root", self.root,
                                     "--action", "normalize-status", "--all-legacy"])
        self.assertEqual(code, 0, err)

    def test_all_legacy_refuses_any_other_action(self):

        self.append("A")
        code, _, err = self.run_all(["repair-issue", "--state-root", self.root,
                                     "--action", "unschedule", "--all-legacy"])
        self.assertEqual(code, 2)
        self.assertIn("normalize-status", err)

    def test_key_is_still_required_without_all_legacy(self):
        self.append("A")
        code, _, err = self.run_all(["repair-issue", "--state-root", self.root,
                                     "--action", "unschedule"])
        self.assertEqual(code, 2)
        self.assertIn("--key is required", err)

    def test_unschedule_clears_1b(self):

        self.append("A")
        self.promote()
        os.remove(pm.story_file(self.root, "E001-S02-001"))
        code, _, err = self.repair("BL-E001-001", "unschedule")
        self.assertEqual(code, 0, err)
        item = self.load_open()["backlog"][0]
        self.assertEqual(item["status"], "backlog")
        self.assertNotIn("story", item)
        self.assertNotIn(("1b", "BL-E001-001"), self.ids())
        self.assert_invariants()

    def test_unschedule_writes_an_issue_unscheduled_event(self):
        """scheduled -> backlog is a status transition, and the events are its history."""
        self.append("A")
        self.promote()
        os.remove(pm.story_file(self.root, "E001-S02-001"))
        code, _, err = self.repair("BL-E001-001", "unschedule", "--session-id", "S-5")
        self.assertEqual(code, 0, err)
        ev = self.events("issue_unscheduled")
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]["key"], ev[0]["epic"], ev[0]["story"], ev[0]["session"],
                          ev[0]["cause"]), ("BL-E001-001", "001", "E001-S02-001", "S-5", "cli"))
        self.assertIn("ts", ev[0])

    def test_unschedule_clears_1g(self):
        self.append("Later", "005", "01", "Low", "qa (Q-1)")
        self.promote("BL-E005-001", "005", "01")
        _fx_move_epic(self.root, "E005", "archived")
        self.assertEqual(self.repair("BL-E005-001", "unschedule")[0], 0)
        self.assertNotIn(("1g", "BL-E005-001"), self.ids())
        # the archived story still lists the key, but its claim is dead: no 1d, no loop
        self.assertEqual(self.audit(), (0, []))
        self.assert_invariants()

    def test_repromote_after_1g_creates_a_new_story(self):
        self.append("Later", "005", "01", "Low", "qa (Q-1)")
        self.promote("BL-E005-001", "005", "01")
        _fx_move_epic(self.root, "E005", "archived")
        self.assertEqual(self.repair("BL-E005-001", "unschedule")[0], 0)
        code, out, err = self.run_all(["promote-issue", "--state-root", self.root,
                                       "--artifacts-root", self.arts, "--key", "BL-E005-001",
                                       "--epic", "001", "--sprint", "02",
                                       "--classification", "simple"])
        self.assertEqual(code, 0, err)
        self.assertIn("-> E001-S02-001", out)
        self.assertNotIn("resumed", out)
        self.assertIsNotNone(pm.story_file(self.root, "E001-S02-001"))
        item = self.load_open()["backlog"][0]
        self.assertEqual((item["status"], item["story"]), ("scheduled", "E001-S02-001"))
        self.assertEqual(self.audit(), (0, []))      # the dead archived claim is not 1h
        self.assert_invariants()

    def test_1j_ignores_a_ref_story_that_never_listed_the_key(self):
        """resolve --ref <a story still in progress> is legitimate. That story never listed
        the key, so 1j must not fire -- and reopen must not manufacture a 1b from it."""
        self.append("A")
        self.promote()                                          # E001-S02-001 lists 001 only
        _fx_set_status(self.root, "in-progress", story="E001-S02-001")
        self.append("B", "001", "02")
        code, _, err = self.run_all(["resolve-issue", "--state-root", self.root, "--key",
                                     "BL-E001-002", "--resolution", "fixed", "--ref",
                                     "E001-S02-001"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.audit(), (0, []))
        code, _, err = self.repair("BL-E001-002", "reopen")
        self.assertEqual(code, 2)
        self.assertIn("reopen: audit finding 1j does not hold for BL-E001-002", err)
        self.assertEqual(self.resolved_keys(), ["BL-E001-002"])

    def test_link_refuses_a_key_with_a_resolved_entry(self):
        self.append("A")
        self._crash_promote_before_scheduling(cls="simple")
        self._crash_resolve_before_open_save()                  # 1a; the stale copy looks 1d
        before = _tree_snapshot(self.d)
        code, _, err = self.repair("BL-E001-001", "link", "--story", "E001-S02-001")
        self.assertEqual(code, 2)
        self.assertIn("link: BL-E001-001 is already resolved (obsolete)", err)
        self.assertIn("rerun resolve-issue", err)
        self.assertEqual(_tree_snapshot(self.d), before)

    def test_unschedule_refuses_a_key_with_a_resolved_entry(self):
        self.append("A")
        self.promote()
        self._crash_resolve_before_open_save()                  # 1a; the stale copy is scheduled
        os.remove(pm.story_file(self.root, "E001-S02-001"))     # ...and now looks 1b
        self.assertEqual([(f["id"], f["key"]) for f in self.audit()[1]],
                         [("1a", "BL-E001-001")])               # the stale copy is not 1b
        before = _tree_snapshot(self.d)
        code, _, err = self.repair("BL-E001-001", "unschedule")
        self.assertEqual(code, 2)
        self.assertIn("unschedule: BL-E001-001 is already resolved (obsolete)", err)
        self.assertIn("rerun resolve-issue", err)
        self.assertEqual(_tree_snapshot(self.d), before)
        code, _, err = self.run_all(["resolve-issue", "--state-root", self.root, "--key",
                                     "BL-E001-001", "--resolution", "obsolete", "--note", "x"])
        self.assertEqual(code, 0, err)                          # the advised repair works
        self.assertEqual(self.audit(), (0, []))
        self.assert_invariants()

    def _set_next(self, *pairs):
        from ruamel.yaml.comments import CommentedMap
        self.edit_open(lambda d: d.__setitem__("next", CommentedMap(pairs)))

    def e1(self):
        return [f for f in self.audit()[1] if f["id"] == "1e"]

    def test_audit_reports_an_unquoted_numeric_next_key_as_an_alias(self):
        """next: {1: 5} -- a hand edit with an int key -- must not crash the audit's sort. By the
        user's decision it is 1e whatever its value: allocate reads only the canonical '001'."""
        self.append("A")
        self.append("C", "005", "01", "Low", "qa (Q-1)")
        self._set_next((1, 5), ("005", 2))
        code, findings = self.audit()                   # parseable JSON: the sort did not crash
        self.assertEqual(code, 4)
        e1 = [f for f in findings if f["id"] == "1e"]
        self.assertEqual([(f["key"], f["epic"]) for f in e1], [("BL-E001", "001")], findings)
        self.assertIn("non-canonical key 1 ", e1[0]["detail"])
        self.assertIn("run repair-issue --action reseed", e1[0]["detail"])
        self.assertEqual(e1[0]["repair"], "repair-issue --action reseed")

    def test_audit_reports_every_string_next_alias_as_1e(self):
        self.append("A")
        for alias in ("1", "01", "E001"):
            self._set_next(("001", 9), (alias, 9))          # both values healthy
            e1 = self.e1()
            self.assertEqual(len(e1), 1, (alias, e1))
            self.assertIn(f"non-canonical key {alias!r} ", e1[0]["detail"])

    def test_audit_reports_a_next_beyond_the_key_space_as_1e(self):
        """Keys run 001-999, so next is at most 1000."""
        self.append("A")
        self._set_next(("001", 1000))
        self.assertEqual(self.audit(), (0, []))
        self._set_next(("001", 1001))
        e1 = self.e1()
        self.assertEqual([(f["key"], f["epic"]) for f in e1], [("BL-E001", "001")])
        self.assertIn("next['001'] = 1001 exceeds the BL key space", e1[0]["detail"])

    def test_an_alias_beyond_the_key_space_gets_the_hand_fix_repair(self):
        # Final review M7. reseed refuses any alias above 1000 (exit 2), so an alias finding
        # that still said "run repair-issue --action reseed" routed triage to a repair that
        # cannot run. Above 1000 it carries the key-space finding's hand-fix text; at 1000
        # reseed folds the alias in by max, so reseed stays its repair.
        self.append("A")
        self._set_next(("001", 2), (1, 1000))
        e1 = self.e1()
        self.assertEqual(len(e1), 1, e1)
        self.assertIn("non-canonical key 1 ", e1[0]["detail"])
        self.assertIn("run repair-issue --action reseed", e1[0]["detail"])
        self.assertEqual(e1[0]["repair"], "repair-issue --action reseed")

        self._set_next(("001", 2), (1, 1001))
        e1 = self.e1()
        alias = [f for f in e1 if "non-canonical key 1 " in f["detail"]]
        space = [f for f in e1 if "exceeds the BL key space" in f["detail"]]
        self.assertEqual((len(e1), len(alias), len(space)), (2, 1, 1), e1)
        self.assertNotIn("run repair-issue --action reseed", alias[0]["detail"])
        self.assertIn("fix it by hand", alias[0]["detail"])
        self.assertEqual(alias[0]["repair"], space[0]["repair"])
        self.assertTrue(alias[0]["repair"].startswith("report only -- fix it by hand"),
                        alias[0]["repair"])
        self.assertEqual(self.repair("BL-E001-001", "reseed")[0], 2)   # why: reseed refuses

    def test_reseed_refuses_a_value_beyond_the_key_space_and_writes_nothing(self):
        self.append("A")
        self.append("B", "001", "02")
        for pairs, named in (((("001", 1), (1, 5000)), "next[1] = 5000"),     # 1e: '001' stale
                             ((("001", 5000),), "next['001'] = 5000")):
            self._set_next(*pairs)
            before = _tree_snapshot(self.d)
            code, _, err = self.repair("BL-E001-001", "reseed")
            self.assertEqual(code, 2, (pairs, err))
            self.assertIn(named, err)
            self.assertIn("by hand", err)
            self.assertEqual(_tree_snapshot(self.d), before, pairs)

    def test_reseed_merges_every_alias_into_the_canonical_key_by_max(self):
        self.append("A")
        self.append("B", "001", "02")
        self._set_next(("001", 2), (1, 7), ("1", 4))
        code, _, err = self.repair("BL-E001-001", "reseed")
        self.assertEqual(code, 0, err)
        self.assertEqual(dict(self.load_open()["next"]), {"001": 7})
        self.assertEqual(self.audit(), (0, []))

    def test_allocate_reads_only_the_canonical_next_key(self):
        """User decision: an alias never feeds allocation -- audit and reseed deal with it."""
        self.append("A")
        self._set_next((1, 50))
        code, out, err = self.append("B", "001", "02")
        self.assertEqual(code, 0, err)
        self.assertIn("BL-E001-002", out)

    def test_reseed_drops_a_numeric_alias_so_1e_clears(self):
        self.append("A")
        self.append("B", "001", "02")
        self.append("C", "005", "01", "Low", "qa (Q-1)")
        self._set_next((1, 1), ("005", 2))
        self.found("1e", "BL-E001")
        code, _, err = self.repair("BL-E001-001", "reseed")
        self.assertEqual(code, 0, err)
        nxt = self.load_open()["next"]
        self.assertNotIn(1, nxt)
        self.assertEqual(int(nxt["001"]), 3)
        self.assertEqual(self.audit(), (0, []))

    def test_reseed_never_lowers_next_when_dropping_an_alias(self):
        self.append("A")
        self.append("B", "001", "02")
        self._set_next(("001", 50), (1, 1))
        self.found("1e", "BL-E001")
        self.assertEqual(self.repair("BL-E001-001", "reseed")[0], 0)
        self.assertEqual(dict(self.load_open()["next"]), {"001": 50})
        self.assertEqual(self.audit(), (0, []))

    def test_unschedule_refused_on_a_healthy_item(self):
        self.append("A")
        self.promote()
        with open(self.issues, encoding="utf-8") as fh:
            before = fh.read()
        code, _, err = self.repair("BL-E001-001", "unschedule")
        self.assertEqual(code, 2)
        self.assertIn("unschedule: audit finding 1b/1g does not hold for BL-E001-001", err)
        with open(self.issues, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)

    def test_link_clears_1d_and_is_refused_for_the_wrong_story(self):
        self.append("A")
        self._crash_promote_before_scheduling(cls="simple")
        code, _, err = self.repair("BL-E001-001", "link")                              # no --story
        self.assertEqual(code, 2)
        self.assertIn("--action link needs --story", err)
        code, _, err = self.repair("BL-E001-001", "link", "--story", "E001-S02-009")
        self.assertEqual(code, 2)
        self.assertIn("link: audit finding 1d does not hold for BL-E001-001 and E001-S02-009", err)
        code, _, err = self.repair("BL-E001-001", "link", "--story", "E001-S02-001")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.audit(), (0, []))
        self.assert_invariants()

    def test_link_event_says_it_came_from_repair(self):
        """link's issue_scheduled event must be distinguishable from promote's."""
        self.append("A")
        self._crash_promote_before_scheduling(cls="simple")     # no event: it stopped first
        code, _, err = self.repair("BL-E001-001", "link", "--story", "E001-S02-001")
        self.assertEqual(code, 0, err)
        ev = self.events("issue_scheduled")
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]["key"], ev[0]["story"], ev[0]["via"]),
                         ("BL-E001-001", "E001-S02-001", "repair-link"))

    def test_reseed_clears_1e(self):
        self.append("A")
        self.append("B", "001", "02")
        self.edit_open(lambda d: d["next"].__setitem__("001", 1))
        self.assertEqual(self.repair("BL-E001-001", "reseed")[0], 0)
        self.assertEqual(int(self.load_open()["next"]["001"]), 3)
        self.assertEqual(self.audit(), (0, []))
        self.assert_invariants()

    def test_reseed_rebuilds_a_malformed_map(self):
        self.append("A")
        self.edit_open(lambda d: d.__setitem__("next", "garbage"))
        self.assertEqual(self.repair("BL-E001-001", "reseed")[0], 0)
        self.assertEqual(int(self.load_open()["next"]["001"]), 2)
        self.assert_invariants()

    def test_reseed_rebuilds_a_malformed_next_for_both_epics_at_once(self):
        # A malformed `next` is rebuilt for EVERY epic with a key in either file, from one
        # reseed. Epic 005's only key is in the resolved file, so its entry has to come from
        # there.
        self.append("A")
        self.append("B", "001", "02")
        self.append("C", "005", "01", "Low", "qa (Q-1)")
        code, _, err = self.run_all(["resolve-issue", "--state-root", self.root, "--key",
                                     "BL-E005-001", "--resolution", "obsolete", "--note", "gone"])
        self.assertEqual(code, 0, err)
        self.edit_open(lambda d: d.__setitem__("next", "garbage"))
        self.assertEqual(self.ids(), {("1e", "next")})
        code, _, err = self.repair("BL-E001-001", "reseed")
        self.assertEqual(code, 0, err)
        self.assertEqual({str(e): int(v) for e, v in self.load_open()["next"].items()},
                         {"001": 3, "005": 2})
        self.assertEqual(self.audit(), (0, []))
        self.assert_invariants()

    def test_reseed_folds_each_epics_aliases_by_max_and_both_epics_end_clean(self):
        # Batch A's alias rule, across two epics. Aliases are merged by max, then removed, and
        # only the named epic's aliases (reseed is per epic). The other epic stays 1e until its
        # own reseed. Both epics then audit clean.
        self.append("A")
        self.append("B", "001", "02")
        self.append("C", "005", "01", "Low", "qa (Q-1)")
        self._set_next(("001", 2), (1, 7), ("005", 1), ("5", 4), ("E005", 3))
        self.assertEqual({f["epic"] for f in self.e1()}, {"001", "005"})       # premise
        self.assertEqual(self.repair("BL-E001-001", "reseed")[0], 0)
        self.assertEqual(dict(self.load_open()["next"]),
                         {"001": 7, "005": 1, "5": 4, "E005": 3})       # 005 not touched
        self.assertEqual({f["epic"] for f in self.e1()}, {"005"})
        self.assertEqual(self.repair("BL-E005-001", "reseed")[0], 0)
        self.assertEqual(dict(self.load_open()["next"]), {"001": 7, "005": 4})
        self.assertEqual(self.audit(), (0, []))
        self.assert_invariants()

    def test_reseed_refused_when_next_is_fine(self):
        self.append("A")
        code, _, err = self.repair("BL-E001-001", "reseed")
        self.assertEqual(code, 2)
        self.assertIn("reseed: audit finding 1e does not hold for epic 001", err)

    def test_reopen_clears_1j(self):
        self.append("A")
        self.promote()
        self.finish()
        _fx_set_status(self.root, "in-progress", story="E001-S02-001")
        code, _, err = self.repair("BL-E001-001", "reopen", "--session-id", "S-4")
        self.assertEqual(code, 0, err)
        item = self.load_open()["backlog"][0]
        self.assertEqual((item["status"], item["story"]), ("scheduled", "E001-S02-001"))
        self.assertNotIn("resolution", item)
        self.assertEqual(self.resolved_keys(), [])
        self.assertEqual(self.events("issue_reopened")[-1]["session"], "S-4")
        self.assertEqual(self.audit(), (0, []))
        self.assert_invariants()

    def test_reopen_refused_without_1j(self):
        self.append("A")
        self.run_all(["resolve-issue", "--state-root", self.root, "--key", "BL-E001-001",
                      "--resolution", "obsolete", "--note", "x"])
        code, _, err = self.repair("BL-E001-001", "reopen")
        self.assertEqual(code, 2)
        self.assertIn("reopen: audit finding 1j does not hold for BL-E001-001", err)

    def test_reopen_interrupted_after_the_open_write_completes_on_rerun(self):
        self.append("A")
        self.promote()
        self.finish()
        _fx_set_status(self.root, "in-progress", story="E001-S02-001")
        with _dump_failing_on(2):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with self.assertRaises(OSError):
                    pm.main(["repair-issue", "--state-root", self.root, "--key", "BL-E001-001",
                             "--action", "reopen"])
        self.assertEqual(self.repair("BL-E001-001", "reopen")[0], 0)
        self.assertEqual(self.open_keys(), ["BL-E001-001"], "no duplicate open copy")
        self.assertEqual(self.resolved_keys(), [])
        self.assert_invariants()


class TestUnreadableStoryNode(IssueBase):
    """Ruling F1: a story node the walk cannot read is a refusal naming the file, never a
    traceback. promote-issue and repair-issue exit 2 before any write; audit-issues reports it
    through its existing error channel (exit 4; JSON {"findings": [], "error": MSG})."""

    def setUp(self):
        super().setUp()
        self.append("A")
        self.bad = os.path.join(self.root, "active", "epic-001", "sprint-01", "E001-S01-001.yaml")

    def write_story(self, path, text):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def promote(self):
        return self.run_all(["promote-issue", "--state-root", self.root, "--artifacts-root",
                             self.arts, "--key", "BL-E001-001", "--epic", "001", "--sprint", "02",
                             "--classification", "simple"])

    def break_story(self):
        self.write_story(self.bad, "key: 'E001-S01-001'\nresolves: [BL-E001-001\n")

    def test_promote_refuses_an_unparseable_story_node_and_writes_nothing(self):
        self.break_story()
        before = _tree_snapshot(self.d)
        code, out, err = self.promote()
        self.assertEqual(code, 2, (out, err))
        self.assertIn(f"{self.bad} does not parse:", err)
        self.assertIn("-- fix the file by hand", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(_tree_snapshot(self.d), before)

    def test_repair_refuses_an_unparseable_story_node_and_writes_nothing(self):
        self.edit_next_stale()
        self.break_story()
        before = _tree_snapshot(self.d)
        code, out, err = self.run_all(["repair-issue", "--state-root", self.root, "--key",
                                       "BL-E001-001", "--action", "reseed"])
        self.assertEqual(code, 2, (out, err))
        self.assertIn(f"{self.bad} does not parse:", err)
        self.assertEqual(_tree_snapshot(self.d), before)

    def edit_next_stale(self):
        """A real 1e, so reseed would otherwise act: the refusal is the walk's, not the gate's."""
        y, data = pm.core._load(self.issues)
        data["next"]["001"] = 1
        pm.core._atomic_dump(y, data, self.issues)

    def test_audit_reports_an_unparseable_story_node_through_its_error_channel(self):
        self.break_story()
        code, out, err = self.run_all(["audit-issues", "--state-root", self.root,
                                       "--format", "json"])
        self.assertEqual(code, 4, err)
        doc = json.loads(out)
        self.assertEqual(doc["findings"], [])
        self.assertIn(f"{self.bad} does not parse:", doc["error"])
        code, out, err = self.run_all(["audit-issues", "--state-root", self.root])
        self.assertEqual((code, out), (4, ""))
        self.assertIn(f"{self.bad} does not parse:", err)

    # Ruling F4: a node that loads but is not a mapping, or is not valid UTF-8, is refused
    # exactly as a parse error is. name: (file bytes, the reason the refusal must give)
    UNREADABLE = {
        "list":        (b"- key: 'E001-S01-001'\n- resolves: [BL-E001-001]\n", "is not a mapping"),
        "scalar":      (b"just some text\n", "is not a mapping"),
        "invalid-utf8": (b"key: 'E001-S01-001'\ntitle: '\xff\xfe'\n", "is not valid UTF-8"),
    }

    def test_every_unreadable_shape_is_refused_by_every_walking_verb(self):
        for name, (raw, reason) in self.UNREADABLE.items():
            with self.subTest(name):
                self._refused_by_every_walking_verb(name, raw, reason)

    def _refused_by_every_walking_verb(self, name, raw, reason):
        with open(self.bad, "wb") as fh:
            fh.write(raw)
        want = f"{self.bad} {reason}"
        before = _tree_snapshot(self.d)
        code, out, err = self.promote()
        self.assertEqual(code, 2, (name, out, err))
        self.assertIn(want, err, name)
        self.assertIn("-- fix the file by hand", err, name)
        self.assertNotIn("Traceback", err, name)
        self.assertEqual(_tree_snapshot(self.d), before, name)
        self.edit_next_stale()                      # a real 1e: the refusal is the walk's
        before = _tree_snapshot(self.d)
        code, out, err = self.run_all(["repair-issue", "--state-root", self.root, "--key",
                                       "BL-E001-001", "--action", "reseed"])
        self.assertEqual(code, 2, (name, out, err))
        self.assertIn(want, err, name)
        self.assertEqual(_tree_snapshot(self.d), before, name)
        code, out, err = self.run_all(["audit-issues", "--state-root", self.root,
                                       "--format", "json"])
        self.assertEqual(code, 4, (name, err))
        doc = json.loads(out)
        self.assertEqual(doc["findings"], [], name)
        self.assertIn(want, doc["error"], name)

    def test_promote_refuses_a_claimant_with_a_malformed_key(self):
        """The resume path parses the claimant's key: a malformed one raised ValueError."""
        claimant = os.path.join(self.root, "active", "epic-001", "sprint-02", "E001-S02-001.yaml")
        self.write_story(claimant, "key: 'E001-S02'\nepic: 'E001'\nsprint: 'S02'\n"
                                   "status: backlog\nresolves: [BL-E001-001]\n")
        before = _tree_snapshot(self.d)
        code, out, err = self.promote()
        self.assertEqual(code, 2, (out, err))
        self.assertIn(f"story node {claimant} has a malformed key 'E001-S02' -- fix it by hand, "
                      f"then rerun", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(_tree_snapshot(self.d), before)


class TestIssueInvariants(IssueBase):
    # IssueBase.assert_invariants is only worth calling if it can fail. Each case builds, on
    # purpose, one state that a spec §1.4 invariant forbids, and requires the helper to reject
    # it under that invariant's name.

    def _fresh(self):
        shutil.rmtree(self.root)
        _build_issue_tree(self.root)
        for t in ("A", "B"):
            code, _, err = self.append(t)
            self.assertEqual(code, 0, err)
        self.assert_invariants()                                    # premise: a clean state

    def _edit_open(self, fn):
        y, data = pm.core._load(self.issues)
        fn(data)
        pm.core._atomic_dump(y, data, self.issues)

    def test_assert_invariants_rejects_each_forbidden_state(self):
        from ruamel.yaml.comments import CommentedMap

        def in_both_files():            # a resolve that crashed between its two writes
            with _dump_failing_on(2), redirect_stdout(io.StringIO()), \
                    redirect_stderr(io.StringIO()), self.assertRaises(OSError):
                pm.main(["resolve-issue", "--state-root", self.root, "--key", "BL-E001-001",
                         "--resolution", "obsolete", "--note", "x"])

        def non_canonical(d):
            d["backlog"].append(CommentedMap([("key", "BL-E1-9"), ("epic", "001"),
                                              ("title", "hand"), ("status", "backlog")]))

        cases = [
            ("invariant 1", in_both_files),
            ("invariant 1", lambda: self._edit_open(lambda d: d["backlog"].pop(0))),   # in neither
            ("invariant 5", lambda: self._edit_open(
                lambda d: d["backlog"].append(CommentedMap(d["backlog"][0])))),
            ("invariant 6", lambda: self._edit_open(non_canonical)),
        ]
        for i, (invariant, corrupt) in enumerate(cases):
            with self.subTest(case=i, invariant=invariant):
                self._fresh()
                corrupt()
                with self.assertRaises(AssertionError) as cm:
                    self.assert_invariants()
                self.assertIn(invariant + ":", str(cm.exception))


class TestEventWriteFailure(IssueBase):
    # Spec §6.1 "Events": a failing event write never fails the verb. Here events.jsonl is a
    # directory, so append_event's open() raises inside its catch-all. Each issue verb must
    # still exit 0 and write its state, and must say on stderr that the event was lost.

    def break_events(self):
        p = pm.events_path(self.root)
        if os.path.exists(p):
            os.remove(p)
        os.mkdir(p)
        return p

    def assert_event_lost(self, err, path):
        self.assertIn("pm-status.py: warning — could not append event: ", err)
        self.assertIn(repr(path), err)

    def promote(self):
        code, _, err = self.run_all(["promote-issue", "--state-root", self.root,
                                     "--artifacts-root", self.arts, "--key", "BL-E001-001",
                                     "--epic", "001", "--sprint", "02",
                                     "--classification", "simple"])
        return code, err

    def test_resolve_issue_still_resolves(self):
        self.append("A")
        p = self.break_events()
        code, out, err = self.run_all(["resolve-issue", "--state-root", self.root, "--key",
                                       "BL-E001-001", "--resolution", "obsolete", "--note", "x"])
        self.assertEqual(code, 0, err)
        self.assertEqual((self.open_keys(), self.resolved_keys()), ([], ["BL-E001-001"]))
        self.assert_event_lost(err, p)
        self.assert_invariants()

    def test_update_issue_still_updates(self):
        self.append("A", "001", "01", "Low")
        p = self.break_events()
        code, out, err = self.run_all(["update-issue", "--state-root", self.root, "--key",
                                       "BL-E001-001", "--severity", "High"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.load_open()["backlog"][0]["severity"], "High")
        self.assert_event_lost(err, p)
        self.assert_invariants()

    def test_promote_issue_still_promotes(self):
        self.append("A")
        p = self.break_events()
        code, err = self.promote()
        self.assertEqual(code, 0, err)
        node = pm.load_node(pm.story_file(self.root, "E001-S02-001"))[1]
        self.assertEqual(list(node["resolves"]), ["BL-E001-001"])
        self.assertIn("estimate", node)
        item = self.load_open()["backlog"][0]
        self.assertEqual((item["status"], item["story"]), ("scheduled", "E001-S02-001"))
        self.assert_event_lost(err, p)
        self.assert_invariants()

    def test_repair_issue_still_repairs(self):
        self.append("A")
        code, err = self.promote()
        self.assertEqual(code, 0, err)
        os.remove(pm.story_file(self.root, "E001-S02-001"))       # 1b: the story is gone
        p = self.break_events()
        code, out, err = self.run_all(["repair-issue", "--state-root", self.root, "--key",
                                       "BL-E001-001", "--action", "unschedule"])
        self.assertEqual(code, 0, err)
        item = self.load_open()["backlog"][0]
        self.assertEqual(item["status"], "backlog")
        self.assertNotIn("story", item)
        self.assert_event_lost(err, p)
        self.assert_invariants()


class TestLockFilesIgnored(IssueBase):
    """Lock files, and the notices ledger, must never be committed. Every lock acquisition
    inside a state root ensures {state_root}/.gitignore carries BOTH `*.lock` and
    `.notices.yaml` (a bare `append-issue --file` outside one is skipped) -- on every
    acquisition, not only when a pattern's file is first created, so a project whose lock
    files already exist is covered on its next lock. Best-effort: a failure warns on stderr
    and never fails the verb."""

    STORY = "E001-S01-001"

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

    def write_story(self):
        p = os.path.join(self.root, "active", "epic-001", "sprint-01", f"{self.STORY}.yaml")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(f"key: '{self.STORY}'\nepic: 'E001'\nsprint: 'S01'\nstatus: in-progress\n")
        return p

    def add_test_run(self):
        return self.run_all(["add-test-run", "--state-root", self.root, "--story", self.STORY,
                             "--command", "pytest -q", "--exit-code", "0"])

    def test_first_lock_creates_gitignore(self):
        code, _, err = self.append("A")
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.exists(self.issues + ".lock"), "premise: a lock was taken")
        lines = self.gi_lines()
        self.assertIn("*.lock", lines)
        self.assertIn(".notices.yaml", lines)

    def test_epic_lock_creates_gitignore(self):
        code, _, err = self.run_all(["set-estimate", "--state-root", self.root, "--epic", "E001",
                                     "--man-hours-low", "1", "--man-hours-high", "2"])
        self.assertEqual(code, 0, err)
        lines = self.gi_lines()
        self.assertIn("*.lock", lines)
        self.assertIn(".notices.yaml", lines)

    def test_second_lock_leaves_bytes_unchanged(self):
        self.append("A")
        before = self.gi_bytes()
        pm._LOCK_IGNORE_CHECKED.clear()          # as a second process would see it
        code, _, err = self.run_all(["set-estimate", "--state-root", self.root, "--epic", "E001",
                                     "--man-hours-low", "1", "--man-hours-high", "2"])
        self.assertEqual(code, 0, err)
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
        self.assertEqual(self.open_keys(), ["BL-E001-001"], "the verb's state must be written")

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
        self.assertEqual(self.open_keys(), ["BL-E001-001"])

    def test_add_test_run_sidecar_ignores_at_the_state_root_only(self):
        story = self.write_story()
        code, _, err = self.add_test_run()
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.exists(story + ".lock"), "premise: the sidecar was taken")
        lines = self.gi_lines()
        self.assertIn("*.lock", lines)
        self.assertIn(".notices.yaml", lines)
        for d in (os.path.dirname(story), os.path.join(self.root, "active", "epic-001"),
                  os.path.join(self.root, "active")):
            self.assertFalse(os.path.exists(os.path.join(d, ".gitignore")),
                             f"a .gitignore was created inside {d}")

    def test_read_only_commands_on_a_root_without_issue_files_create_nothing(self):
        for argv in (["list-issues", "--state-root", self.root, "--all", "--format", "json"],
                     ["audit-issues", "--state-root", self.root]):
            code, _, err = self.run_all(argv)
            self.assertEqual(code, 0, err)
        self.assertFalse(os.path.exists(self.gi), "a read-only command created .gitignore")
        self.assertFalse(os.path.exists(self.issues + ".lock"))

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

    # -- never outside a state root ------------------------------------------------------ #
    def append_file(self, path):
        return self.run_all(["append-issue", "--file", path, "--epic", "001", "--sprint", "01",
                             "--title", "A", "--source", "code-review (E001-S01-001)",
                             "--severity", "Low"])

    def test_bare_file_outside_a_state_root_writes_no_gitignore(self):
        """`append-issue --file X` with no --state-root: X's directory might be the repo root,
        where `*.lock` would silently ignore uv.lock/yarn.lock/Cargo.lock repo-wide."""
        bare = os.path.join(self.d, "repo-root")
        os.makedirs(bare)
        issues = os.path.join(bare, "issues.yaml")
        code, _, err = self.append_file(issues)
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.exists(issues + ".lock"), "premise: the issues lock was taken")
        self.assertFalse(os.path.exists(os.path.join(bare, ".gitignore")))

    def test_bare_file_inside_a_state_root_still_gets_the_rule(self):
        code, _, err = self.append_file(self.issues)          # self.root has status folders
        self.assertEqual(code, 0, err)
        self.assertIn("*.lock", self.gi_lines())

    def test_explicit_state_root_gets_the_rule_before_any_epic_exists(self):
        fresh = os.path.join(self.d, "fresh", "state")
        os.makedirs(fresh)
        code, _, err = self.run_all(["append-issue", "--state-root", fresh, "--epic", "001",
                                     "--sprint", "01", "--title", "A", "--source",
                                     "code-review (E001-S01-001)", "--severity", "Low"])
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
        self.issues = os.path.join(self.root, "issues.yaml")
        self.gi = os.path.join(self.root, ".gitignore")
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "t")
        self.git("config", "commit.gpgsign", "false")

    def test_git_sees_the_gitignore_and_no_lock_files_and_the_gate_still_passes(self):
        self.init_repo()
        self.write_story()
        self.assertEqual(self.append("A")[0], 0)
        self.assertEqual(self.add_test_run()[0], 0)
        porcelain = self.git("status", "--porcelain", "--untracked-files=all").stdout
        paths = [line[3:] for line in porcelain.splitlines()]
        self.assertIn("impl/state/.gitignore", paths)
        self.assertEqual([p for p in paths if p.endswith(".lock")], [], porcelain)
        self.assertTrue(os.path.exists(self.issues + ".lock"), "premise: lock files exist")
        # step-00-activate's gate: the state-root DIRECTORY must not be ignored.
        gate = self.git("check-ignore", "-q", self.root, check=False)
        self.assertEqual(gate.returncode, 1, "the state root must stay NOT ignored")


class TestIssueKinds(IssueBase):
    """append-issue --kind/--ref, list-issues --kind, promote refusal, audit 1k."""

    SHA = "3f9c2a1"

    def spec_item(self, kind="spec-change", ref=None, title="Spec change: order API"):
        ref = self.SHA if ref is None else ref
        return self.append(title, "001", "", "Medium", "spec-sync (AD-1)",
                           "--kind", kind, "--ref", ref, "--description", "Confirm or reject")

    def item(self, key="BL-E001-001"):
        return next(i for i in self.load_open()["backlog"] if str(i["key"]) == key)

    def test_kind_and_ref_round_trip(self):
        code, out, err = self.spec_item()
        self.assertEqual(code, 0, err)
        it = self.item()
        self.assertEqual(it["kind"], "spec-change")
        self.assertEqual(it["ref"], self.SHA)
        self.assert_invariants()

    def test_defect_writes_no_kind(self):
        code, _, err = self.append("Plain finding")
        self.assertEqual(code, 0, err)
        self.assertNotIn("kind", self.item())
        self.assertNotIn("ref", self.item())

    def test_spec_kind_requires_ref(self):
        code, _, err = self.append("Spec proposal: x", "001", "", "Low", "spec-sync (AD-2)",
                                   "--kind", "spec-proposal")
        self.assertEqual(code, 2)
        self.assertIn("needs --ref", err)
        self.assertEqual(self.open_keys(), [])

    def test_spec_change_ref_must_be_a_sha(self):
        code, _, err = self.spec_item(ref="not-a-sha")
        self.assertEqual(code, 2)
        self.assertIn("commit SHA", err)

    def test_spec_proposal_ref_may_be_a_path(self):
        code, _, err = self.spec_item(kind="spec-proposal",
                                      ref="impl/epic-001/epic-closure/spec-proposals/AD-2.md")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.item()["kind"], "spec-proposal")

    def test_list_issues_kind_filter(self):
        self.append("Plain finding")
        self.spec_item()
        code, out, err = self.run_all(["list-issues", "--state-root", self.root,
                                       "--kind", "spec-change", "--format", "json"])
        self.assertEqual(code, 0, err)
        self.assertEqual([i["key"] for i in json.loads(out)], ["BL-E001-002"])
        code, out, _ = self.run_all(["list-issues", "--state-root", self.root,
                                     "--kind", "defect", "--format", "json"])
        self.assertEqual([i["key"] for i in json.loads(out)], ["BL-E001-001"])

    def test_promote_refuses_spec_items(self):
        self.spec_item()
        code, _, err = self.run_all(["promote-issue", "--state-root", self.root,
                                     "--artifacts-root", self.arts, "--key", "BL-E001-001",
                                     "--epic", "001", "--sprint", "02",
                                     "--classification", "standard"])
        self.assertEqual(code, 2)
        self.assertIn("spec-change", err)
        self.assertIn("triage", err)
        self.assertEqual(self.item().get("status"), "backlog")

    def _edit_open(self, old, new):
        with open(self.issues, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn(old, text)
        with open(self.issues, "w", encoding="utf-8") as fh:
            fh.write(text.replace(old, new, 1))

    def audit(self):
        code, out, err = self.run_all(["audit-issues", "--state-root", self.root,
                                       "--format", "json"])
        return code, json.loads(out)

    def test_audit_1k_unknown_kind(self):
        self.append("Plain finding")
        # A hand edit plants what the CLI refuses to write.
        self._edit_open("status: backlog", "status: backlog\n  kind: bogus")
        code, rep = self.audit()
        self.assertEqual(code, 4)
        self.assertIn(("1k", "BL-E001-001"), {(f["id"], f["key"]) for f in rep["findings"]})

    def test_audit_1k_spec_item_without_ref(self):
        self.spec_item()
        self._edit_open(f"  ref: {self.SHA}\n", "")
        code, rep = self.audit()
        self.assertEqual(code, 4)
        hits = [f for f in rep["findings"] if f["id"] == "1k"]
        self.assertEqual(len(hits), 1)
        self.assertIn("no ref", hits[0]["detail"])

    def test_audit_clean_with_valid_spec_items(self):
        self.spec_item()
        code, rep = self.audit()
        self.assertEqual([f for f in rep["findings"] if f["id"] == "1k"], [])


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

    def test_issues_yaml_stores_one_spelling_whatever_was_typed(self):
        for i, (e, sp) in enumerate(self.SPELLINGS):
            r = self.cli("append-issue", "--state-root", self.root, "--epic", e,
                         "--sprint", sp, "--severity", "Low", "--title", f"t{i}",
                         "--source-phase", "cr", "--source-ref", f"R{i}")
            self.assertEqual(r.returncode, 0, r.stderr)
        _, data = pm.core._load(os.path.join(self.root, "issues.yaml"))
        items = data["backlog"]        # the open list's key, per IssueStore.backlog
        epics = {str(it["epic"]) for it in items}
        sprints = {str(it["sprint"]) for it in items}
        self.assertEqual(epics, {"003"}, f"six spellings stored as {epics}")
        self.assertEqual(sprints, {"01"}, f"six spellings stored as {sprints}")

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


class TestEnsureNodePath(Base):
    class _Args:
        def __init__(self, **kw):
            self.epic = kw.get("epic")
            self.sprint = kw.get("sprint")
            self.story = kw.get("story")
            self.state_root = kw.get("state_root")

    def test_dir_for_status_is_the_inverse_of_status_for_dir(self):
        for folder, status in pm.STATUS_FOR_DIR.items():
            self.assertEqual(pm.DIR_FOR_STATUS[status], folder)
        self.assertEqual(len(pm.DIR_FOR_STATUS), len(pm.STATUS_FOR_DIR))

    def test_new_epic_lands_in_the_folder_named_for_its_status(self):
        a = self._Args(epic="E001", state_root=self.d)
        path, label = pm.ensure_node_path(self.d, a, "epic", "in-progress")
        self.assertEqual(path, os.path.join(self.d, "active", "epic-001", "epic.yaml"))
        self.assertTrue(os.path.isdir(os.path.dirname(path)))
        self.assertEqual(label, "epic E001")

    def test_backlog_epic_lands_in_planned(self):
        a = self._Args(epic="E002", state_root=self.d)
        path, _ = pm.ensure_node_path(self.d, a, "epic", "backlog")
        self.assertEqual(path, os.path.join(self.d, "planned", "epic-002", "epic.yaml"))

    def test_done_epic_lands_in_archived(self):
        a = self._Args(epic="E003", state_root=self.d)
        path, _ = pm.ensure_node_path(self.d, a, "epic", "done")
        self.assertEqual(path, os.path.join(self.d, "archived", "epic-003", "epic.yaml"))

    def test_existing_epic_dir_is_reused_not_relocated(self):
        a = self._Args(epic="E001", state_root=self.d)
        pm.ensure_node_path(self.d, a, "epic", "backlog")          # creates planned/
        path, _ = pm.ensure_node_path(self.d, a, "epic", "done")   # must NOT create archived/
        self.assertEqual(path, os.path.join(self.d, "planned", "epic-001", "epic.yaml"))
        self.assertFalse(os.path.isdir(os.path.join(self.d, "archived", "epic-001")))

    def test_sprint_dir_is_created_under_its_epic(self):
        a = self._Args(epic="E001", sprint="S02", state_root=self.d)
        pm.ensure_node_path(self.d, a, "epic", "backlog")
        path, label = pm.ensure_node_path(self.d, a, "sprint", "in-progress")
        self.assertEqual(
            path, os.path.join(self.d, "planned", "epic-001", "sprint-02", "sprint.yaml"))
        self.assertTrue(os.path.isdir(os.path.dirname(path)))
        self.assertEqual(label, "epic E001 sprint S02")

    def test_story_path_is_created_under_its_sprint(self):
        a = self._Args(epic="E001", story="E001-S02-003", state_root=self.d)
        pm.ensure_node_path(self.d, a, "epic", "backlog")
        path, _ = pm.ensure_node_path(self.d, a, "story", "ready-for-dev")
        self.assertEqual(
            path,
            os.path.join(self.d, "planned", "epic-001", "sprint-02", "E001-S02-003.yaml"))

    def test_sprint_without_an_epic_dir_exits_3(self):
        a = self._Args(epic="E404", sprint="S01", state_root=self.d)
        with self.assertRaises(SystemExit) as cm:
            pm.ensure_node_path(self.d, a, "sprint", "backlog")
        self.assertEqual(cm.exception.code, 3)

    def test_unknown_status_exits_2(self):
        a = self._Args(epic="E001", state_root=self.d)
        with self.assertRaises(SystemExit) as cm:
            pm.ensure_node_path(self.d, a, "epic", "nonsense")
        self.assertEqual(cm.exception.code, 2)


class TestImportActual(Base):
    """`import-actual` is set-actual with the migration contract baked into its defaults.

    A migrated actual needs exactly three things that are easy to forget and dangerous to
    forget: runtime=other (it has no Claude provenance to claim), tokens=N/A (legacy data
    carries no four-class split, and 0 would be consumed by calibration as a real
    measurement), and no calibration sample (a bulk import must not append hundreds in one
    pass). set-actual can express all three, but only if the caller passes all three -- and a
    caller who forgets --tokens-na on runtime=claude gets a refusal, while one who forgets
    --no-calibrate silently poisons the ratios. This verb cannot be called wrongly.
    """

    def _story(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        self.run_main(["import-node", "--state-root", self.d, "--story", "E001-S01-001",
                       "--status", "done", "--title", "S"])

    def _node(self):
        return pm.load_node(pm.story_file(self.d, "E001-S01-001"))[1]

    def test_lands_an_actual_with_the_N_A_sentinel(self):
        self._story()
        code, out = self.run_main(["import-actual", "--state-root", self.d, "--node", "story",
                                   "--story", "E001-S01-001", "--man-hours", "6",
                                   "--hitl-hours", "0", "--elapsed-hours", "0"])
        self.assertEqual(code, 0, out)
        actual = self._node()["actual"]
        self.assertEqual(str(actual["man_hours"]), "6")
        self.assertEqual(str(actual["tokens_k"]), "N/A",
                         "0 would claim a measurement nobody took")

    def test_appends_no_calibration_sample(self):
        self._story()
        self.run_main(["import-actual", "--state-root", self.d, "--node", "story",
                       "--story", "E001-S01-001", "--man-hours", "6",
                       "--hitl-hours", "0", "--elapsed-hours", "0"])
        self.assertFalse(os.path.exists(pm.calibration_path(self.d)),
                         "a bulk import must not append calibration samples")

    def test_it_cannot_be_told_to_claim_claude_provenance(self):
        """The point of the verb: the dangerous options are not reachable."""
        self._story()
        code, _ = self.run_main(["import-actual", "--state-root", self.d, "--node", "story",
                                 "--story", "E001-S01-001", "--runtime", "claude",
                                 "--man-hours", "6"])
        self.assertEqual(code, 2, "--runtime must not be accepted")

    def test_it_cannot_be_told_to_calibrate(self):
        self._story()
        code, _ = self.run_main(["import-actual", "--state-root", self.d, "--node", "story",
                                 "--story", "E001-S01-001", "--calibrate",
                                 "--man-hours", "6"])
        self.assertEqual(code, 2, "--calibrate must not be accepted")

    def test_a_missing_node_exits_3(self):
        code, _ = self.run_main(["import-actual", "--state-root", self.d, "--node", "story",
                                 "--story", "E404-S01-001", "--man-hours", "6"])
        self.assertEqual(code, 3)

    def test_set_actual_is_unchanged_and_still_refuses_claude_without_tokens(self):
        """import-actual must not have loosened set-actual."""
        self._story()
        code, _ = self.run_main(["set-actual", "--state-root", self.d, "--node", "story",
                                 "--story", "E001-S01-001", "--runtime", "claude",
                                 "--man-hours", "6", "--tokens-na"])
        self.assertEqual(code, 2)


class TestImportNode(Base):


    def _events(self):
        p = os.path.join(self.d, "events.jsonl")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def test_creates_an_epic_and_its_directory(self):
        code, out = self.run_main([
            "import-node", "--state-root", self.d, "--epic", "E001",
            "--status", "backlog", "--title", "First epic"])
        self.assertEqual(code, 0, out)
        path = os.path.join(self.d, "planned", "epic-001", "epic.yaml")
        self.assertTrue(os.path.exists(path))
        _, node = pm.load_node(path)
        self.assertEqual(node["key"], "E001")
        self.assertEqual(node["status"], "backlog")
        self.assertEqual(node["title"], "First epic")

    def test_creates_a_sprint_with_its_epic_backreference(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        code, out = self.run_main([
            "import-node", "--state-root", self.d, "--epic", "E001", "--sprint", "S01",
            "--status", "in-progress", "--title", "Sprint one"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(
            os.path.join(self.d, "planned", "epic-001", "sprint-01", "sprint.yaml"))
        self.assertEqual(node["epic"], "E001")
        self.assertEqual(node["key"], "S01")

    def test_creates_a_story_with_both_backreferences(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        code, out = self.run_main([
            "import-node", "--state-root", self.d, "--story", "E001-S01-002",
            "--status", "done", "--title", "A story", "--classification", "feature"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(
            os.path.join(self.d, "planned", "epic-001", "sprint-01", "E001-S01-002.yaml"))
        self.assertEqual(node["epic"], "E001")
        self.assertEqual(node["sprint"], "S01")
        self.assertEqual(node["classification"], "feature")

    def test_the_new_node_passes_check_backrefs(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        self.run_main(["import-node", "--state-root", self.d, "--story", "E001-S01-002",
                       "--status", "done", "--title", "S"])
        code, out = self.run_main([
            "set-estimate", "--state-root", self.d, "--story", "E001-S01-002",
            "--man-hours", "1"])
        self.assertEqual(code, 0, out)

    def test_origin_is_written_when_given_and_absent_otherwise(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E002",
                       "--status", "backlog", "--title", "E2",
                       "--origin", "inferred", "--origin-note", "from transitions"])
        _, plain = pm.load_node(os.path.join(self.d, "planned", "epic-001", "epic.yaml"))
        _, marked = pm.load_node(os.path.join(self.d, "planned", "epic-002", "epic.yaml"))
        self.assertNotIn("origin", plain)
        self.assertEqual(marked["origin"], "inferred")
        self.assertEqual(marked["origin_note"], "from transitions")

    def test_invalid_status_for_kind_exits_2(self):
        code, _ = self.run_main([
            "import-node", "--state-root", self.d, "--epic", "E001",
            "--status", "ready-for-dev", "--title", "E"])
        self.assertEqual(code, 2)

    def test_sprint_without_its_epic_exits_3(self):
        code, _ = self.run_main([
            "import-node", "--state-root", self.d, "--epic", "E404", "--sprint", "S01",
            "--status", "backlog", "--title", "orphan"])
        self.assertEqual(code, 3)

    def test_existing_node_is_skipped_not_overwritten(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "Original"])
        code, out = self.run_main([
            "import-node", "--state-root", self.d, "--epic", "E001",
            "--status", "done", "--title", "Clobber"])
        self.assertEqual(code, 0, out)
        self.assertIn("SKIP", out)
        _, node = pm.load_node(os.path.join(self.d, "planned", "epic-001", "epic.yaml"))
        self.assertEqual(node["title"], "Original")
        self.assertEqual(node["status"], "backlog")

    def test_an_event_is_appended(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        evs = [e for e in self._events() if e.get("event") == "import"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["to"], "backlog")
        self.assertIsNone(evs[0]["from"])

    def test_no_events_flag_suppresses_the_append(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E", "--no-events"])
        self.assertEqual([e for e in self._events() if e.get("event") == "import"], [])

    def test_a_skip_appends_no_event(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        self.assertEqual(len([e for e in self._events() if e.get("event") == "import"]), 1)

    def test_import_node_story_blocked_without_reason_exits_2(self):
        """A migration source that reports a story at status: blocked without a reason
        is a broken source shape -- name it at the boundary rather than land silent."""
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main([
                "import-node", "--state-root", self.d, "--story", "E001-S01-002",
                "--status", "blocked", "--title", "S"])
        self.assertEqual(code, 2)
        self.assertIn("--status blocked requires --reason", buf.getvalue())

    def test_import_node_story_blocked_writes_blocked_reason(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        code, out = self.run_main([
            "import-node", "--state-root", self.d, "--story", "E001-S01-002",
            "--status", "blocked", "--title", "S", "--reason", "external decision X"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(
            os.path.join(self.d, "planned", "epic-001", "sprint-01", "E001-S01-002.yaml"))
        self.assertEqual(node.get("blocked_reason"), "external decision X")

    def test_import_node_story_blocked_emits_a_block_open_event(self):
        """A paired block_open is emitted, so the event log carries the block the way a
        block recorded live would."""
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        self.run_main([
            "import-node", "--state-root", self.d, "--story", "E001-S01-002",
            "--status", "blocked", "--title", "S", "--reason", "wait"])
        opens = [e for e in self._events() if e.get("event") == "block_open"]
        self.assertEqual(len(opens), 1)
        self.assertEqual(opens[0]["story"], "E001-S01-002")
        self.assertEqual(opens[0]["reason"], "wait")

    def test_import_node_reason_on_non_blocked_status_exits_2(self):
        """--reason is only valid with --status blocked on a story import."""
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main([
                "import-node", "--state-root", self.d, "--story", "E001-S01-002",
                "--status", "done", "--title", "S", "--reason", "why"])
        self.assertEqual(code, 2)
        self.assertIn("--reason is only valid with --status blocked", buf.getvalue())

    def test_import_node_reason_on_sprint_or_epic_exits_2(self):
        """--reason is a story-only flag; sprint/epic status sets have no blocked."""
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main([
                "import-node", "--state-root", self.d, "--epic", "E001",
                "--status", "backlog", "--title", "E", "--reason", "spurious"])
        self.assertEqual(code, 2)
        self.assertIn("story-only", buf.getvalue())

    def test_import_node_blocked_does_not_bump_blocks_seen(self):
        """The counter records OUR events, not the source's history. import-node
        predates our history for a migrated node -- the counter starts at 0."""
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        self.run_main([
            "import-node", "--state-root", self.d, "--story", "E001-S01-002",
            "--status", "blocked", "--title", "S", "--reason", "wait"])
        _, node = pm.load_node(
            os.path.join(self.d, "planned", "epic-001", "sprint-01", "E001-S01-002.yaml"))
        ce = node.get("completion_evidence") or {}
        self.assertNotIn("blocks_seen", ce)


class TestBlockedCalibration(Base):
    """Stage 2: a story that spent any time blocked excludes elapsed_hours from
    its calibration sample and emits WARN naming the {N.N}h in blocked. Other
    metrics stay recorded. completion_evidence.blocks_seen is incremented on
    every block_open regardless of the sample state.

    Design: docs/superpowers/specs/2026-09-25-story-lifecycle-blocked-design.md §5.
    """

    def _seed(self, status="in-progress"):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "e"])
        self.run_main(["import-node", "--state-root", self.d,
                       "--story", "E001-S01-002",
                       "--status", status, "--title", "s"])

    def _add_estimate(self, story="E001-S01-002"):
        # A story sample requires estimate + actual. estimate-story with a
        # classification is enough to seed both estimate and the fix_factor.
        self.run_main(["estimate-story", "--state-root", self.d,
                       "--story", story, "--classification", "standard"])

    def _run_capturing_stderr(self, argv):
        err = io.StringIO()
        out = io.StringIO()
        code = 0
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue(), err.getvalue()

    # ---- blocks_seen counter -------------------------------------------------------

    def test_blocks_seen_absent_by_default(self):
        self._seed()
        _, node = pm.load_node(pm.story_file(self.d, "E001-S01-002"))
        self.assertNotIn("blocks_seen", (node.get("completion_evidence") or {}))

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
        self._seed()
        self._add_estimate()
        # Simulate: block, resume, set-actual. The block_close duration lands
        # via _block_duration_since_last_open; here we plant events by hand for
        # a known duration so the WARN wording is deterministic.
        events = os.path.join(self.d, "events.jsonl")
        with open(events, "a") as fh:
            fh.write(json.dumps({"event": "block_close", "story": "E001-S01-002",
                                 "duration_hours": 6.5}) + "\n")
        code, _out, err = self._run_capturing_stderr([
            "set-actual", "--state-root", self.d, "--node", "story",
            "--story", "E001-S01-002",
            "--elapsed-hours", "1.8", "--man-hours", "7", "--hitl-hours", "0.5",
            "--tokens-input", "300", "--tokens-output", "55",
            "--tokens-cache-write", "10", "--tokens-cache-read", "10",
            "--model", "claude-sonnet-5", "--runtime", "claude"])
        self.assertEqual(code, 0, err)
        self.assertIn("WARN blocked story E001-S01-002", err)
        self.assertIn("6.5h in blocked", err)
        self.assertIn("elapsed_hours sample deferred", err)
        self.assertIn("man_hours, hitl_hours, tokens_k still recorded", err)

    def test_record_story_sample_no_warn_when_never_blocked(self):
        """A story with no blocked history writes its sample cleanly -- no WARN."""
        self._seed()
        self._add_estimate()
        code, _out, err = self._run_capturing_stderr([
            "set-actual", "--state-root", self.d, "--node", "story",
            "--story", "E001-S01-002",
            "--elapsed-hours", "1.8", "--man-hours", "7", "--hitl-hours", "0.5",
            "--tokens-input", "300", "--tokens-output", "55",
            "--tokens-cache-write", "10", "--tokens-cache-read", "10",
            "--model", "claude-sonnet-5", "--runtime", "claude"])
        self.assertEqual(code, 0, err)
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


class TestStoryKeyAllocator(unittest.TestCase):
    """`_next_story_key` is a high-water allocator, not a scan of the disk.

    The bug it closes only becomes reachable when a story can MOVE: deriving from the disk
    alone makes a vacated number reusable, and a reused key silently retargets that key's
    remote issue in an issue mirror's mapping to different work, with nothing erroring.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.sr = os.path.join(self.d, "state")
        self.ar = os.path.join(self.d, "artifacts")
        self.sprint_dir = os.path.join(self.sr, "planned", "epic-001", "sprint-01")
        os.makedirs(self.sprint_dir)
        self.sfile = os.path.join(self.sprint_dir, "sprint.yaml")

    def _sprint(self, text="key: 'S01'\nepic: 'E001'\nstatus: backlog\n"):
        with open(self.sfile, "w", encoding="utf-8") as fh:
            fh.write(text)

    def _story(self, n):
        with open(os.path.join(self.sprint_dir, f"E001-S01-{n:03d}.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(f"key: 'E001-S01-{n:03d}'\nepic: 'E001'\nsprint: 'S01'\n")

    def _next(self):
        return pm._next_story_key(self.sr, self.ar, "E001", "S01")

    def _stored_next(self):
        _, node = pm.load_node(self.sfile)
        return node.get("next")

    def test_a_vacated_key_is_never_reissued(self):
        # THE BUG. Allocate 001 and 002, then delete 002 the way a re-parent would, and
        # allocate again. The disk-only allocator returned 002 here.
        self._sprint()
        self.assertEqual(self._next(), "E001-S01-001")
        self._story(1)
        self.assertEqual(self._next(), "E001-S01-002")
        self._story(2)
        os.unlink(os.path.join(self.sprint_dir, "E001-S01-002.yaml"))
        self.assertEqual(self._next(), "E001-S01-003",
                         "a vacated key must never be reissued -- a reused key silently "
                         "retargets its remote issue to different work")

    def test_absent_next_behaves_exactly_as_before(self):
        # Every project today has no `next`. There must be no migration.
        self._sprint()
        self._story(1)
        self._story(2)
        self.assertEqual(self._next(), "E001-S01-003")

    def test_a_too_low_next_cannot_cause_a_reuse(self):
        # Self-healing: the disk floor still applies, which is why this needs no audit
        # finding and no reseed verb, unlike the allocator it is modelled on.
        self._sprint("key: 'S01'\nepic: 'E001'\nstatus: backlog\nnext: 2\n")
        self._story(1)
        self._story(2)
        self._story(3)
        self.assertEqual(self._next(), "E001-S01-004")

    def test_an_unparseable_next_falls_back_to_the_disk_floor(self):
        self._sprint("key: 'S01'\nepic: 'E001'\nstatus: backlog\nnext: not-a-number\n")
        self._story(1)
        self.assertEqual(self._next(), "E001-S01-002")

    def test_a_high_next_is_honoured_and_wastes_rather_than_reuses(self):
        self._sprint("key: 'S01'\nepic: 'E001'\nstatus: backlog\nnext: 50\n")
        self._story(1)
        self.assertEqual(self._next(), "E001-S01-050")

    def test_next_never_decreases_across_allocations(self):
        self._sprint()
        seen = []
        for _ in range(4):
            seen.append(int(self._next().rsplit("-", 1)[1]))
            self._story(seen[-1])
        self.assertEqual(seen, sorted(seen), "allocations must be monotonic")
        self.assertEqual(len(set(seen)), len(seen), "an allocation was repeated")
        self.assertGreater(self._stored_next(), seen[-1])

    def test_an_artifact_document_without_a_state_node_still_owns_its_key(self):
        # Pre-existing behaviour that must survive: the artifacts stories/ dir is part of the
        # disk floor, so a document with no state node is not overwritten.
        self._sprint()
        sd = os.path.join(self.ar, "epic-001", "sprint-01", "stories")
        os.makedirs(sd)
        with open(os.path.join(sd, "E001-S01-007-some-slug.md"), "w", encoding="utf-8") as fh:
            fh.write("# story\n")
        self.assertEqual(self._next(), "E001-S01-008")

    def test_an_unslugged_artifact_document_also_counts(self):
        self._sprint()
        sd = os.path.join(self.ar, "epic-001", "sprint-01", "stories")
        os.makedirs(sd)
        with open(os.path.join(sd, "E001-S01-004.md"), "w", encoding="utf-8") as fh:
            fh.write("# story\n")
        self.assertEqual(self._next(), "E001-S01-005")

    def test_a_non_story_file_in_the_stories_dir_is_ignored(self):
        # The widened regex must not start counting arbitrary files.
        self._sprint()
        sd = os.path.join(self.ar, "epic-001", "sprint-01", "stories")
        os.makedirs(sd)
        for junk in ("README.md", "E001-S01-9.md", "notes.yaml"):
            with open(os.path.join(sd, junk), "w", encoding="utf-8") as fh:
                fh.write("x\n")
        self.assertEqual(self._next(), "E001-S01-001")

    def test_a_missing_sprint_node_still_allocates(self):
        # bootstrap-state can create stories before a sprint node exists; allocation must not
        # require one, it just cannot persist a high-water in that case.
        self._story(3)
        self.assertEqual(self._next(), "E001-S01-004")


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
