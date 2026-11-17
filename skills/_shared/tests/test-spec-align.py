#!/usr/bin/env python3
# A suite declares the dependencies of the script it drives, so `uv run <this file>`
# works with no flags. They used to be passed as `--with` on the CI command line only,
# which made the suite unrunnable as written anywhere else: running it directly gave
# spurious failures that looked like real defects. It also made the CI step unshareable,
# so the workflow had to name every suite by hand.
# /// script
# requires-python = ">=3.11"
# dependencies = ["markdown-it-py>=3", "mdit-py-plugins>=0.4", "ruamel.yaml>=0.18", "unidiff>=0.7", "tenacity>=8"]
# ///
"""
Tests for spec-align.py. Run with:
  uv run -q --with 'markdown-it-py>=3' --with 'mdit-py-plugins>=0.4' --with 'ruamel.yaml>=0.18' \
    --with 'unidiff>=0.7' --with 'tenacity>=8' python3 skills/_shared/tests/test-spec-align.py
Every case drives the real CLI in a subprocess. Git behaviour runs in a real temporary repo;
backlog items are created only through the real pm-status.py CLI.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

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
    _RUN_TMP = tempfile.mkdtemp(prefix="test-spec-align-")
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


HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "spec-align.py")
PM = os.path.join(os.path.dirname(HERE), "pm_status", "__main__.py")
GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
PLAN = "_bmad-output/planning-artifacts"
IMPL = "_bmad-output/implementation-artifacts"
ARCH_REL = f"{PLAN}/architecture.md"
# Line numbers matter to the range assertions below:
#  1 # Architecture          5 ## Data model        9 ## Order API        17 ## Data model
# 21 ### Auth: v2 (beta)    23 last line. Sections: architecture L1-23, data-model L5-8,
# order-api L9-16, data-model-1 L17-23, auth-v2-beta L21-23.
ARCH = """# Architecture

Intro paragraph. Second sentence.

## Data model

Orders live in Postgres, one row per order. Items are JSON.

## Order API

POST /orders accepts a body.

```
# not a heading
```

## Data model

Duplicate title section.

### Auth: v2 (beta)

OIDC via the gateway.
"""


class Project(unittest.TestCase):
    """A scratch project: planning + implementation artifacts, optionally a git repo."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.planning = os.path.join(self.root, PLAN)
        self.impl = os.path.join(self.root, IMPL)
        self.state = os.path.join(self.impl, "state")
        os.makedirs(self.planning)
        os.makedirs(self.state)

    def path(self, rel):
        return os.path.join(self.root, rel)

    def write(self, rel, text):
        p = self.path(rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if isinstance(text, bytes):
            with open(p, "wb") as fh:
                fh.write(text)
        else:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(text)
        return p

    def read(self, rel):
        with open(self.path(rel), encoding="utf-8") as fh:
            return fh.read()

    def sa(self, *args, spec_paths=None, planning=None, pm_status=None):
        g = ["--project-root", self.root, "--planning-root", planning or self.planning,
             "--impl-root", self.impl, "--state-root", self.state, "--pm-status",
             pm_status or PM]
        if spec_paths is not None:
            g += ["--spec-paths", json.dumps(spec_paths)]
        return subprocess.run([sys.executable, SCRIPT, *g, *args], capture_output=True,
                              text=True, env={**os.environ, **GIT_ENV}, cwd=self.root)

    def pm(self, *args):
        return subprocess.run([sys.executable, PM, *args], capture_output=True, text=True,
                              env={**os.environ, **GIT_ENV})

    def git(self, *args, check=True):
        r = subprocess.run(["git", "-C", self.root, *args], capture_output=True, text=True,
                           env={**os.environ, **GIT_ENV})
        if check and r.returncode != 0:
            raise AssertionError(f"git {' '.join(args)}: {r.stderr}")
        return r.stdout

    def init_git(self):
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")

    def index(self):
        return self.read(f"{IMPL}/spec/spec-index.md")


class TestBuild(Project):
    def test_indexes_headings_anchors_ranges_and_summaries(self):
        self.write(ARCH_REL, ARCH)
        r = self.sa("build")
        self.assertEqual(r.returncode, 0, r.stderr)
        idx = self.index()
        self.assertTrue(idx.startswith("# Spec index — generated by spec-align.py; do not edit\n"))
        self.assertIn(f"## architecture · {ARCH_REL}", idx)
        self.assertIn(f"- {ARCH_REL}#architecture — Architecture: Intro paragraph. (L1–23)", idx)
        self.assertIn(f"- {ARCH_REL}#data-model — Data model: Orders live in Postgres, one row "
                      f"per order. (L5–8)", idx)
        self.assertIn(f"- {ARCH_REL}#order-api — Order API: POST /orders accepts a body. (L9–16)",
                      idx)
        self.assertIn(f"- {ARCH_REL}#data-model-1 — Data model: Duplicate title section. (L17–23)",
                      idx)
        self.assertIn(f"- {ARCH_REL}#auth-v2-beta — Auth: v2 (beta): OIDC via the gateway. "
                      f"(L21–23)", idx)
        self.assertNotIn("not-a-heading", idx)
        self.assertRegex(idx.splitlines()[1],
                         r"^# inputs-sha256: [0-9a-f]{64}  ·  bytes: [\d,]+  ·  specs: 1  ·  "
                         r"sections: 5$")
        self.assertEqual(idx.splitlines()[2], "# spec-paths: []")

    def test_setext_heading_and_deep_headings_not_listed(self):
        self.write(f"{PLAN}/system-design.md",
                   "Setext\n======\n\nBody.\n\n#### Deep\n\nToo deep.\n")
        self.assertEqual(self.sa("build").returncode, 0)
        idx = self.index()
        self.assertIn(f"{PLAN}/system-design.md#setext — Setext: Body.", idx)
        self.assertNotIn("#deep", idx)

    def test_kinds_and_precedence(self):
        self.write(f"{PLAN}/ux-spec.md", "# UX\n\nScreens.\n")
        self.write(f"{PLAN}/prd.md", "# PRD\n\nGoals.\n")
        self.write(f"{PLAN}/epics.md", "# Epics\n\nList.\n")
        self.write(f"{PLAN}/notes.md", "# Notes\n\nNot a spec.\n")
        self.assertEqual(self.sa("build").returncode, 0)
        idx = self.index()
        self.assertIn(f"## ux · {PLAN}/ux-spec.md", idx)
        self.assertIn(f"## prd · {PLAN}/prd.md", idx)
        self.assertIn(f"## epics · {PLAN}/epics.md", idx)
        self.assertNotIn("notes.md", idx)

    def test_yaml_frontmatter_is_not_indexed_as_a_section(self):
        # BMad 6.12.1 writes `status: draft` frontmatter into epics.md. In Markdown, a line
        # followed by `---` is a SETEXT h2, so the frontmatter parsed as a heading and the
        # index grew a phantom `#status-draft` section pointing at the YAML block. Pre-existing,
        # but 6.12.1 made it reach every project that runs the planning skill.
        self.write(f"{PLAN}/epics.md",
                   "---\nstatus: draft\nowner: me\n---\n\n# Epics\n\n## Real\n\nText.\n")
        self.assertEqual(self.sa("build").returncode, 0)
        idx = self.index()
        self.assertNotIn("#status-draft", idx)
        self.assertNotIn("#owner-me", idx)
        # The real headings still resolve, and their line numbers still point at the real
        # lines -- the frontmatter is blanked in place, never removed, so nothing shifts.
        self.assertIn(f"{PLAN}/epics.md#epics", idx)
        self.assertIn(f"{PLAN}/epics.md#real", idx)
        self.assertRegex(idx, r"epics\.md#real — Real: Text\. \(L8")

    def test_frontmatter_delimiter_mid_document_is_left_alone(self):
        # Only a block at the very top is frontmatter. A `---` rule later in the document is
        # a thematic break, and the line above it IS a legitimate setext heading.
        self.write(f"{PLAN}/epics.md", "# Epics\n\nIntro.\n\nA Real Setext Heading\n---\n\nText.\n")
        self.assertEqual(self.sa("build").returncode, 0)
        self.assertIn("#a-real-setext-heading", self.index())

    def test_sharded_directory_is_indexed_whole(self):
        self.write(f"{PLAN}/prd/index.md", "# PRD\n\nOverview.\n")
        self.write(f"{PLAN}/prd/goals.md", "# Goals\n\nShip it.\n")
        self.assertEqual(self.sa("build").returncode, 0)
        idx = self.index()
        self.assertIn(f"## prd · {PLAN}/prd/goals.md", idx)
        self.assertIn(f"{PLAN}/prd/goals.md#goals — Goals: Ship it.", idx)

    def test_same_title_in_two_files_is_unsuffixed_in_each(self):
        self.write(ARCH_REL, ARCH)
        self.write(f"{PLAN}/tech-design.md", "# Tech\n\n## Data model\n\nSecond file.\n")
        self.assertEqual(self.sa("build").returncode, 0)
        self.assertIn(f"{PLAN}/tech-design.md#data-model — ", self.index())

    def test_non_utf8_spec_is_skipped_not_fatal(self):
        self.write(ARCH_REL, ARCH)
        self.write(f"{PLAN}/architecture-legacy.md", b"# Old\n\xff\xfe\n")
        r = self.sa("build")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"- skipped: {PLAN}/architecture-legacy.md (not UTF-8)", self.index())

    def test_empty_project(self):
        r = self.sa("build")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no spec docs found", self.index())

    def test_if_stale_leaves_a_fresh_index_untouched(self):
        self.write(ARCH_REL, ARCH)
        self.assertEqual(self.sa("build").returncode, 0)
        p = self.path(f"{IMPL}/spec/spec-index.md")
        before = os.stat(p).st_mtime_ns
        time.sleep(0.02)
        r = self.sa("build", "--if-stale")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("fresh", r.stdout)
        self.assertEqual(os.stat(p).st_mtime_ns, before)
        self.write(ARCH_REL, ARCH + "\n## Events\n\nKafka.\n")
        self.assertEqual(self.sa("build", "--if-stale").returncode, 0)
        self.assertIn("#events", self.index())

    def test_check_reports_stale_and_writes_nothing(self):
        self.write(ARCH_REL, ARCH)
        r = self.sa("build", "--check")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(os.path.exists(self.path(f"{IMPL}/spec/spec-index.md")))
        self.sa("build")
        self.assertEqual(self.sa("build", "--check").returncode, 0)

    def test_spec_paths_override_is_recorded_and_reused(self):
        self.write(ARCH_REL, ARCH)
        self.write("docs/architecture.md", "# Arch\n\n## Events\n\nKafka.\n")
        r = self.sa("build", spec_paths=["docs/*.md"])
        self.assertEqual(r.returncode, 0, r.stderr)
        idx = self.index()
        self.assertIn("docs/architecture.md#events", idx)
        self.assertNotIn(ARCH_REL, idx)
        self.assertEqual(idx.splitlines()[2], '# spec-paths: ["docs/*.md"]')
        # A caller without --spec-paths (doctor) reuses the recorded list: still fresh.
        self.assertEqual(self.sa("build", "--check").returncode, 0)
        # An explicit empty list means discovery again: stale.
        self.assertEqual(self.sa("build", "--check", spec_paths=[]).returncode, 1)

    def test_bad_spec_paths_json_is_refused(self):
        r = subprocess.run([sys.executable, SCRIPT, "--project-root", self.root, "--impl-root",
                            self.impl, "--spec-paths", "{not json", "build"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--spec-paths", r.stderr)

    def test_empty_and_whitespace_spec_paths_behave_like_an_empty_list_but_malformed_still_fails(self):
        # An orchestrator that renders "no override" as an empty string rather than the
        # documented `[]`/`[...]` JSON must not turn every build/check-pointers into a hard
        # failure -- empty or whitespace-only means "no override, discover normally", exactly
        # like an explicit `[]`. The leniency this adds must not spill over into genuinely
        # malformed input, which still has to exit 2.
        self.write(ARCH_REL, ARCH)

        def build_with(spec_paths):
            return subprocess.run(
                [sys.executable, SCRIPT, "--project-root", self.root, "--planning-root",
                 self.planning, "--impl-root", self.impl, "--spec-paths", spec_paths, "build"],
                capture_output=True, text=True)

        r_list = build_with("[]")
        self.assertEqual(r_list.returncode, 0, r_list.stderr)
        idx_from_list = self.index()
        self.assertIn(ARCH_REL, idx_from_list)
        self.assertEqual(idx_from_list.splitlines()[2], "# spec-paths: []")

        r_empty = build_with("")
        self.assertEqual(r_empty.returncode, 0, r_empty.stderr)
        self.assertEqual(self.index(), idx_from_list)

        r_whitespace = build_with("   \t  ")
        self.assertEqual(r_whitespace.returncode, 0, r_whitespace.stderr)
        self.assertEqual(self.index(), idx_from_list)

        r_bad = build_with("not-json")
        self.assertEqual(r_bad.returncode, 2)
        self.assertIn("--spec-paths", r_bad.stderr)

    def test_index_never_indexes_itself(self):
        self.write("_bmad-output/architecture.md", ARCH)
        parent = os.path.join(self.root, "_bmad-output")
        self.assertEqual(self.sa("build", planning=parent).returncode, 0)
        self.assertEqual(self.sa("build", planning=parent).returncode, 0)
        self.assertNotIn("spec-index.md", self.index())

    def test_size_warning(self):
        body = "".join(f"## Section {i}\n\nThis sentence pads the index entry to a realistic "
                       f"length for the size warning.\n\n" for i in range(400))
        self.write(ARCH_REL, "# Big\n\n" + body)
        r = self.sa("build")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WARN spec index is", r.stderr)


DIMS = ["Interface contracts", "Error and edge case handling", "Observability requirements",
        "Security considerations", "Testability approach", "Existing-library check"]


def story(dims, head="# E001-S01-001: A story\n\nSome prose.\n"):
    parts = [head, "## Technical acceptance criteria\n"]
    for name in DIMS:
        if name in dims:
            parts.append(f"### {name}\n\n{dims[name]}\n")
    parts.append("## Files in scope\n\n- `src/a.py` — the module\n")
    return "\n".join(parts)


def full_story(**overrides):
    dims = {d: f"Content for {d}.\nSpec: {ARCH_REL}#data-model" for d in DIMS}
    for k, v in overrides.items():
        dims[k.replace("_", " ")] = v
    return story(dims)


BUSINESS_DIMS = ["Outcome", "Non-goals"]


def business_block(dims):
    parts = ["## Business acceptance criteria\n"]
    for name in BUSINESS_DIMS:
        if name in dims:
            parts.append(f"### {name}\n\n{dims[name]}\n")
    return "\n".join(parts)


def full_business(**overrides):
    dims = {"Outcome": f"Support can trace a deploy.\nSpec: {ARCH_REL}#data-model",
            "Non-goals": "Does not migrate the legacy jobs."}
    for k, v in overrides.items():
        dims[k.replace("_", "-")] = v
    return business_block(dims)


def story_with_business(business=None, **tac_overrides):
    """Business section above the technical one, as the contract requires."""
    head = "# E001-S01-001: A story\n\nSome prose.\n"
    body = full_story(**tac_overrides)
    bus = full_business() if business is None else business
    return body.replace(head, head + "\n" + bus + "\n", 1)


STORY_REL = f"{IMPL}/epic-001/sprint-01/stories/E001-S01-001.md"


class TestPointers(Project):
    def setUp(self):
        super().setUp()
        self.write(ARCH_REL, ARCH)

    def check(self, text, rel=STORY_REL):
        self.write(rel, text)
        return self.sa("check-pointers", "--story", self.path(rel))

    def test_complete_story_passes(self):
        r = self.check(full_story())
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_dimension_blocks(self):
        dims = {d: f"x\nSpec: {ARCH_REL}#data-model" for d in DIMS if d != DIMS[2]}
        r = self.check(story(dims))
        self.assertEqual(r.returncode, 2)
        self.assertIn("Observability requirements: missing dimension", r.stderr)

    def test_not_applicable_dimension_needs_no_pointer(self):
        r = self.check(full_story(Security_considerations="N/A — internal batch job, no input."))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_applicable_dimension_without_pointer_blocks(self):
        r = self.check(full_story(Testability_approach="Unit tests at the service boundary."))
        self.assertEqual(r.returncode, 2)
        self.assertIn("Testability approach: no Spec: line", r.stderr)

    def test_spec_none_with_reason_passes(self):
        r = self.check(full_story(
            Observability_requirements="Log each order.\nSpec: none — no observability section"))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_spec_none_without_reason_blocks(self):
        r = self.check(full_story(Observability_requirements="Log it.\nSpec: none"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("needs a reason", r.stderr)

    def test_spec_none_plus_pointer_blocks(self):
        r = self.check(full_story(Observability_requirements=(
            f"Log it.\nSpec: none — nothing\nSpec: {ARCH_REL}#data-model")))
        self.assertEqual(r.returncode, 2)
        self.assertIn("must be the only Spec: line", r.stderr)

    def test_several_pointers_on_one_dimension_pass(self):
        r = self.check(full_story(Interface_contracts=(
            f"POST /orders.\nSpec: {ARCH_REL}#order-api\n- Spec: {ARCH_REL}#data-model-1")))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_unknown_path_and_anchor_block(self):
        r = self.check(full_story(Interface_contracts=(
            "x\nSpec: docs/nowhere.md#a\nSpec: " + ARCH_REL + "#no-such-anchor")))
        self.assertEqual(r.returncode, 2)
        self.assertIn("docs/nowhere.md is not in the spec index", r.stderr)
        self.assertIn("has no anchor #no-such-anchor", r.stderr)

    def test_spec_line_inside_a_fence_does_not_count(self):
        r = self.check(full_story(Interface_contracts=(
            f"Example:\n\n```\nSpec: {ARCH_REL}#data-model\n```\n")))
        self.assertEqual(r.returncode, 2)
        self.assertIn("Interface contracts: no Spec: line", r.stderr)

    def test_pre_provenance_blocks_story_mode(self):
        r = self.check("# Old story\n\nInterface: POST /x.\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("pre-provenance", r.stderr)

    def test_all_mode_informs_on_pre_provenance_and_reports_broken(self):
        self.write(STORY_REL, "# Old story\n\nNo ACs.\n")
        r = self.sa("check-pointers", "--all")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("INFO pre-provenance", r.stdout)
        self.write(f"{IMPL}/epic-001/sprint-02/stories/E001-S02-001.md",
                   full_story(Interface_contracts=f"x\nSpec: {ARCH_REL}#gone"))
        r = self.sa("check-pointers", "--all")
        self.assertEqual(r.returncode, 1)
        self.assertIn("E001-S02-001.md", r.stderr)

    def test_sections_dedupes_and_prints_ranges(self):
        a = self.write(STORY_REL, full_story(Interface_contracts=f"x\nSpec: {ARCH_REL}#order-api"))
        b = self.write(f"{IMPL}/epic-001/sprint-01/stories/E001-S01-002.md", full_story())
        r = self.sa("sections", "--stories", a, b)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), [f"{ARCH_REL}#data-model L5–8",
                                                 f"{ARCH_REL}#order-api L9–16"])


class TestBusinessParsing(Project):
    def setUp(self):
        super().setUp()
        self.write(ARCH_REL, ARCH)

    def check(self, text, rel=STORY_REL):
        self.write(rel, text)
        return self.sa("check-pointers", "--story", self.path(rel))

    def test_business_section_is_parsed_and_passes(self):
        r = self.check(story_with_business())
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_business_section_absent_is_still_valid(self):
        r = self.check(full_story())
        self.assertEqual(r.returncode, 0, r.stderr)


class TestBusinessGate(Project):
    def setUp(self):
        super().setUp()
        self.write(ARCH_REL, ARCH)

    def check(self, text, *extra, rel=STORY_REL):
        self.write(rel, text)
        return self.sa("check-pointers", "--story", self.path(rel), *extra)

    def test_technical_dimension_under_business_h2_does_not_satisfy_technical_gate(self):
        # Hand-built: business_block() would drop a name outside BUSINESS_DIMS.
        misplaced = (
            "## Business acceptance criteria\n\n"
            f"### Outcome\n\nSupport can trace a deploy.\nSpec: {ARCH_REL}#data-model\n\n"
            "### Non-goals\n\nDoes not migrate the legacy jobs.\n\n"
            f"### Existing-library check\n\nUse the platform.\nSpec: {ARCH_REL}#data-model\n")
        dims = {d: f"Content for {d}.\nSpec: {ARCH_REL}#data-model"
                for d in DIMS if d != "Existing-library check"}
        head = "# E001-S01-001: A story\n\nSome prose.\n"
        text = story(dims).replace(head, head + "\n" + misplaced + "\n", 1)
        self.assertEqual(text.count("### Existing-library check"), 1)
        r = self.check(text)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("Existing-library check", r.stderr)

    def test_absent_business_is_advisory_by_default(self):
        r = self.check(full_story())
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_absent_business_blocks_when_required(self):
        r = self.check(full_story(), "--business", "required")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no '## Business acceptance criteria' section", r.stderr)

    def test_absent_business_warns_when_advisory(self):
        r = self.check(full_story(), "--business", "advisory")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("INFO ", r.stderr)
        self.assertIn("no '## Business acceptance criteria'", r.stderr)

    def test_complete_business_passes_when_required(self):
        r = self.check(story_with_business(), "--business", "required")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_business_dimension_blocks_when_required(self):
        r = self.check(story_with_business(business=business_block({"Outcome": "x\nSpec: none — no spec yet"})),
                       "--business", "required")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Non-goals: missing dimension", r.stderr)

    def test_empty_business_section_blocks_when_required(self):
        r = self.check(story_with_business(business="## Business acceptance criteria\n"),
                       "--business", "required")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Outcome: missing dimension", r.stderr)

    def test_outcome_needs_a_pointer(self):
        r = self.check(story_with_business(business=full_business(Outcome="Faster deploys.")),
                       "--business", "required")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Outcome: no Spec: line", r.stderr)

    def test_non_goals_needs_no_pointer(self):
        r = self.check(story_with_business(), "--business", "required")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_non_goals_accepts_not_applicable(self):
        r = self.check(story_with_business(business=full_business(Non_goals="N/A — scope is a single file.")),
                       "--business", "required")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_business_spec_line_inside_a_fence_does_not_count(self):
        r = self.check(story_with_business(business=full_business(
            Outcome=f"Example:\n\n```\nSpec: {ARCH_REL}#data-model\n```\n")), "--business", "required")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Outcome: no Spec: line", r.stderr)

    def test_business_present_without_tac_is_still_pre_provenance(self):
        text = "# E001-S01-001: A story\n\n" + full_business() + "\n"
        r = self.check(text, "--business", "required")
        self.assertEqual(r.returncode, 2)
        self.assertIn("pre-provenance", r.stderr)

    def test_all_mode_pre_business_is_reported_as_info(self):
        self.write(STORY_REL, full_story())
        r = self.sa("check-pointers", "--all")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("INFO pre-business", r.stdout)

    def test_all_mode_with_business_required_still_exits_zero(self):
        self.write(STORY_REL, full_story())
        r = self.sa("check-pointers", "--all", "--business", "required")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("INFO pre-business", r.stdout)


# -- v7 leaves (check-pointers --story-file) ------------------------------------------------ #
# A BMad v7 leaf is a ticket file in Sofia's tree: YAML frontmatter with its `type`, then the
# ticket body. The specs it points at are the tickets above it and their sources and
# companions, which live beside the tree rather than under a planning folder, so a pointer
# resolves against any markdown file under the project root unless --planning-root or
# --spec-paths narrows the catalog. The business-AC policy is read from the project's own
# config (modules.l3io-pm.business_ac_required) instead of being passed in.

V7_EPIC = "_bmad-output/initiative-shop/tickets/epic-cart"
V7_EPIC_FILE = f"{V7_EPIC}/epic-cart.md"
V7_LEAF_REL = f"{V7_EPIC}/tickets/story-basket.md"
V7_EPIC_TEXT = ("---\ntype: epic\nafter: []\n---\n\n# Cart\n\n## Outcome\n\nShoppers keep a "
                "basket.\n\n## Requirements\n\nR1 (prd FR-2): a basket survives a reload.\n")
V7_FRONT = ('---\nid: 1\ntype: {type}\ntitle: "Basket"\nparent: epic-cart\n'
            "refined: true\nhitl: false\nrisk: low\n---\n\n")

FAKE_RESOLVE_CONFIG = """\
import json, sys
values = json.loads({values!r})
keys = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a in ("--key", "-k")]
print(json.dumps({{k: values[k] for k in keys if k in values}}))
"""


def v7_leaf(business=None, kind="story", **tac):
    """A refined v7 story: frontmatter, then both AC sections pointing at its epic's file."""
    tac = {k: v for k, v in tac.items()}
    dims = {d: f"Content for {d}.\nSpec: {V7_EPIC_FILE}#requirements" for d in DIMS}
    for k, v in tac.items():
        dims[k.replace("_", " ")] = v
    head = "# Basket\n\n## Description\n\nA basket that survives a reload.\n"
    body = story(dims, head=head)
    bus = (business_block({"Outcome": f"Shoppers keep a basket.\nSpec: {V7_EPIC_FILE}#outcome",
                           "Non-goals": "No saved-for-later list."})
           if business is None else business)
    return V7_FRONT.format(type=kind) + body.replace(head, head + "\n" + bus + "\n", 1)


class TestV7Leaf(Project):
    def setUp(self):
        super().setUp()
        self.write(ARCH_REL, ARCH)
        self.write(V7_EPIC_FILE, V7_EPIC_TEXT)

    def config(self, **values):
        """BMad core's resolver, as `bmad setup` installs it, answering from `values`."""
        self.write("_bmad/scripts/resolve_config.py",
                   FAKE_RESOLVE_CONFIG.format(values=json.dumps(values)))

    def sa7(self, text, *extra, rel=V7_LEAF_REL, globals_=()):
        self.write(rel, text)
        return subprocess.run([sys.executable, SCRIPT, "--project-root", self.root, *globals_,
                               "check-pointers", "--story-file", self.path(rel), *extra],
                              capture_output=True, text=True,
                              env={**os.environ, **GIT_ENV}, cwd=self.root)

    def test_check_pointers_on_v7_leaf(self):
        with self.subTest("resolving: the epic's own file and an architecture section"):
            r = self.sa7(v7_leaf(Interface_contracts=(
                f"POST /basket.\nSpec: {V7_EPIC_FILE}#requirements\nSpec: {ARCH_REL}#order-api")))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("OK check-pointers", r.stdout)
        with self.subTest("unresolving: an anchor the epic file does not have"):
            r = self.sa7(v7_leaf(Interface_contracts=f"x\nSpec: {V7_EPIC_FILE}#no-such-anchor"))
            self.assertEqual(r.returncode, 2)
            self.assertIn(f"{V7_EPIC_FILE} has no anchor #no-such-anchor", r.stderr)
            self.assertIn("story-basket.md", r.stderr)
        with self.subTest("unresolving: a file that does not exist"):
            r = self.sa7(v7_leaf(Interface_contracts="x\nSpec: docs/nowhere.md#a"))
            self.assertEqual(r.returncode, 2)
            self.assertIn("docs/nowhere.md does not exist under the project root", r.stderr)
        with self.subTest("Spec: none -- reason"):
            r = self.sa7(v7_leaf(
                Observability_requirements="Log each basket.\nSpec: none — no observability spec"))
            self.assertEqual(r.returncode, 0, r.stderr)
        with self.subTest("Spec: none with no reason"):
            r = self.sa7(v7_leaf(Observability_requirements="Log it.\nSpec: none"))
            self.assertEqual(r.returncode, 2)
            self.assertIn("needs a reason", r.stderr)

    def test_missing_dimension_and_thin_leaf_block(self):
        dims = {d: f"x\nSpec: {V7_EPIC_FILE}#requirements" for d in DIMS if d != DIMS[5]}
        text = V7_FRONT.format(type="story") + story(dims)
        r = self.sa7(text, "--business", "advisory")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Existing-library check: missing dimension", r.stderr)
        r = self.sa7(V7_FRONT.format(type="story") + "# Basket\n\n## Requirements\n\n"
                     "Verify: reload keeps the basket.\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("pre-provenance", r.stderr)

    def test_frontmatter_is_not_read_as_a_heading(self):
        r = self.sa7(v7_leaf())
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_container_is_refused(self):
        r = self.sa7(v7_leaf(kind="epic"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("container", r.stderr)

    def test_a_pointer_outside_the_project_does_not_resolve(self):
        outside = os.path.join(os.path.dirname(self.root), "outside.md")
        with open(outside, "w", encoding="utf-8") as fh:
            fh.write("# Out\n\n## Here\n\nx\n")
        self.addCleanup(os.remove, outside)
        r = self.sa7(v7_leaf(Interface_contracts="x\nSpec: ../outside.md#here"))
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_planning_root_narrows_the_catalog(self):
        r = self.sa7(v7_leaf(), globals_=("--planning-root", self.planning))
        self.assertEqual(r.returncode, 2)
        self.assertIn(f"{V7_EPIC_FILE} is not in the spec index", r.stderr)

    def test_business_policy_defaults_to_code_and_mixed(self):
        no_business = v7_leaf(business="")
        with self.subTest("no resolver installed: the default, and a CODE ticket requires it"):
            r = self.sa7(no_business)
            self.assertEqual(r.returncode, 2)
            self.assertIn("no '## Business acceptance criteria' section", r.stderr)
        with self.subTest("a DOCS ticket under the default is advisory"):
            r = self.sa7(no_business, "--work-type", "DOCS")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("INFO ", r.stderr)

    def test_business_policy_reads_the_project_config(self):
        no_business = v7_leaf(business="")
        self.config(**{"modules.l3io-pm.business_ac_required": " docs , config "})
        with self.subTest("CODE is not in the configured set"):
            r = self.sa7(no_business)
            self.assertEqual(r.returncode, 0, r.stderr)
        with self.subTest("CONFIG is, case and whitespace ignored"):
            r = self.sa7(no_business, "--work-type", "CONFIG")
            self.assertEqual(r.returncode, 2)
            self.assertIn("Business acceptance criteria", r.stderr)
        with self.subTest("an explicit --business wins over the config"):
            r = self.sa7(no_business, "--work-type", "CONFIG", "--business", "advisory")
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_business_policy_with_an_unknown_work_type_halts(self):
        self.config(**{"modules.l3io-pm.business_ac_required": "CODE,BOGUS"})
        r = self.sa7(v7_leaf())
        self.assertEqual(r.returncode, 2)
        self.assertIn("BOGUS", r.stderr)
        self.assertIn("CODE, DOCS, CONFIG, MIXED", r.stderr)

    def test_work_type_belongs_to_story_file_only(self):
        self.write(STORY_REL, full_story())
        r = self.sa("check-pointers", "--story", self.path(STORY_REL), "--work-type", "DOCS")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--work-type", r.stderr)

    def test_the_check_writes_nothing(self):
        self.config(**{"modules.l3io-pm.business_ac_required": "CODE"})
        self.write(V7_LEAF_REL, v7_leaf())

        def snapshot():
            out = {}
            for d, dirs, files in os.walk(self.root):
                dirs[:] = [x for x in dirs if x != "__pycache__"]
                for f in files:
                    p = os.path.join(d, f)
                    with open(p, "rb") as fh:
                        out[os.path.relpath(p, self.root)] = fh.read()
            return out
        before = snapshot()
        for text in (v7_leaf(), v7_leaf(business=""), v7_leaf(Interface_contracts="x")):
            self.sa7(text)
            self.write(V7_LEAF_REL, v7_leaf())
        self.assertEqual(snapshot(), before)


REVIEW = """# Arch drift review

2 sentences of summary.

## Findings table

| # | Severity | Principle | Location | Finding | Remediation |
|---|----------|-----------|----------|---------|-------------|
| AD-1 | MAJOR | Core §1 | `src/a.py:1` | Orders bypass the repository | route via repo |
| AD-2 | MINOR | Core §7 | `src/b.py:2` | Naming | rename |
| AD-3 | BLOCKER | Core §2 | `src/c.py:3` | PRD says soft delete | use soft delete |
"""
EPIC_REVIEW_REL = f"{IMPL}/epic-003/epic-closure/arch-drift-review.md"
PRD_REL = f"{PLAN}/prd.md"
PRD = "# PRD\n\n## Deletion\n\nOrders are soft-deleted.\n"


class TestDispositions(Project):
    def setUp(self):
        super().setUp()
        self.write(ARCH_REL, ARCH)
        self.write(PRD_REL, PRD)
        self.review = self.write(EPIC_REVIEW_REL, REVIEW)

    def disp(self, fid, disposition, *extra):
        return self.sa("disposition", "--review", self.review, "--finding", fid,
                       "--disposition", disposition, *extra)

    def load(self):
        from ruamel.yaml import YAML
        with open(self.path(f"{IMPL}/epic-003/epic-closure/drift-dispositions.yaml"),
                  encoding="utf-8") as fh:
            return YAML(typ="safe").load(fh)

    def test_resolved_in_code_is_recorded(self):
        r = self.disp("AD-1", "resolved-in-code")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.load()
        self.assertEqual(d["review"], EPIC_REVIEW_REL)
        self.assertEqual(d["findings"]["AD-1"]["severity"], "MAJOR")
        self.assertEqual(d["findings"]["AD-1"]["title"], "Orders bypass the repository")
        self.assertEqual(d["findings"]["AD-1"]["disposition"], "resolved-in-code")
        self.assertIsNone(d["findings"]["AD-1"]["commit"])

    def test_unknown_finding_is_refused(self):
        r = self.disp("AD-9", "resolved-in-code")
        self.assertEqual(r.returncode, 2)
        self.assertIn("AD-9 is not in the findings table", r.stderr)

    def test_spec_updated_on_architecture(self):
        r = self.disp("AD-1", "spec-updated", "--spec", f"{ARCH_REL}#order-api")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.load()["findings"]["AD-1"]["spec"], f"{ARCH_REL}#order-api")

    def test_spec_updated_on_a_prd_is_refused(self):
        r = self.disp("AD-3", "spec-updated", "--spec", f"{PRD_REL}#deletion")
        self.assertEqual(r.returncode, 2)
        self.assertIn("record spec-proposal instead", r.stderr)

    def test_spec_proposal_on_a_prd(self):
        r = self.disp("AD-3", "spec-proposal", "--spec", f"{PRD_REL}#deletion")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_spec_dispositions_need_a_resolving_pointer(self):
        r = self.disp("AD-1", "spec-updated")
        self.assertEqual(r.returncode, 2)
        r = self.disp("AD-1", "spec-updated", "--spec", f"{ARCH_REL}#nope")
        self.assertEqual(r.returncode, 2)
        self.assertIn("has no anchor #nope", r.stderr)

    def test_adr_justified_needs_an_existing_adr(self):
        r = self.disp("AD-1", "adr-justified", "--adr", "docs/adr/0009-x.md")
        self.assertEqual(r.returncode, 2)
        self.write("docs/adr/0009-x.md", "# ADR-0009: x\n")
        r = self.disp("AD-1", "adr-justified", "--adr", "docs/adr/0009-x.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.load()["findings"]["AD-1"]["adr"], "docs/adr/0009-x.md")

    def test_switch_off_refuses_spec_dispositions(self):
        r = self.disp("AD-1", "spec-updated", "--spec", f"{ARCH_REL}#order-api",
                      "--spec-alignment", "false")
        self.assertEqual(r.returncode, 2)
        self.assertIn("spec_alignment is off", r.stderr)
        r = self.disp("AD-1", "resolved-in-code", "--spec-alignment", "false")
        self.assertEqual(r.returncode, 0, r.stderr)

    def check(self, expect):
        return self.sa("check-dispositions", "--review", self.review, "--expect", expect)

    def test_check_passes_when_every_blocking_finding_has_one(self):
        self.disp("AD-1", "resolved-in-code")
        self.disp("AD-3", "spec-proposal", "--spec", f"{PRD_REL}#deletion")
        r = self.check("DONE — Blocker: 1, Major: 1, Minor: 1")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_check_blocks_a_blocking_finding_without_one(self):
        self.disp("AD-1", "resolved-in-code")
        r = self.check("Blocker: 1, Major: 1, Minor: 1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("AD-3 (BLOCKER) has no disposition", r.stderr)

    def test_check_blocks_a_count_mismatch(self):
        self.disp("AD-1", "resolved-in-code")
        self.disp("AD-3", "resolved-in-code")
        r = self.check("Blocker: 0, Major: 1, Minor: 1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Blocker: 1, Major: 1, Minor: 1", r.stderr)

    def test_a_review_in_the_wrong_shape_cannot_pass_silently(self):
        self.write(EPIC_REVIEW_REL, "# Review\n\n- AD-1 MAJOR: something\n")
        r = self.check("Blocker: 0, Major: 1, Minor: 0")
        self.assertEqual(r.returncode, 2)
        self.assertIn("parsed Blocker: 0, Major: 0, Minor: 0", r.stderr)

    def test_sprint_ids_are_sprint_qualified(self):
        rel = f"{IMPL}/epic-003/sprint-02/closure/arch-drift-review.md"
        review = self.write(rel, REVIEW.replace("AD-1", "SD-02-1").replace("AD-2", "SD-02-2")
                            .replace("AD-3", "SD-02-3"))
        r = self.sa("disposition", "--review", review, "--finding", "SD-02-1",
                    "--disposition", "resolved-in-code")
        self.assertEqual(r.returncode, 0, r.stderr)


def adr(num, slug, epic="E003", status="Accepted", departs="n/a"):
    return (f"# ADR-{num:04d}: {slug}\n\n- **Status:** {status}\n- **Date:** 2026-09-11\n"
            f"- **Epic:** {epic}\n- **Departs from spec:** {departs}\n\n## Context\n\nx\n")


class TestAdrs(Project):
    def setUp(self):
        super().setUp()
        self.write(ARCH_REL, ARCH)
        self.write("docs/adr/0001-order-api.md",
                   adr(1, "order-api", departs=f"{ARCH_REL}#order-api"))
        self.write("docs/adr/0002-global.md", adr(2, "global", epic="n/a"))
        self.write("docs/adr/0003-draft.md",
                   adr(3, "draft", status="Proposed", departs=f"{ARCH_REL}#data-model"))
        self.write(f"{IMPL}/epic-003/arch/adr-0005-legacy.md", adr(5, "legacy"))
        self.write(f"{IMPL}/epic-003/arch/arch-gate-review.md", "# Gate\n")

    def test_lists_an_epics_adrs_from_both_homes(self):
        r = self.sa("adrs", "--epic", "E003")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), ["docs/adr/0001-order-api.md",
                                                 "docs/adr/0003-draft.md",
                                                 f"{IMPL}/epic-003/arch/adr-0005-legacy.md"])
        self.assertIn("old ADR home", r.stderr)
        self.assertIn("migrate-adrs", r.stderr)

    def test_an_adr_prefixed_filename_in_the_one_home_is_listed(self):
        """`docs/adr/` holds hand-written ADRs, and `ADR-NNNN-slug.md` is how they are
        usually named. Against the old `^\\d{4}` pattern every one of them was invisible to
        `adrs`, `check-links` and the migration planner alike -- reported as "no ADRs"
        rather than as a naming the reader could not parse."""
        self.write("docs/adr/ADR-0007-prefixed.md", adr(7, "prefixed"))
        r = self.sa("adrs", "--epic", "E003", "--format", "json")
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = json.loads(r.stdout)
        self.assertIn(7, [x["number"] for x in rows])
        self.assertEqual([x["home"] for x in rows if x["number"] == 7], ["docs"])

    def test_a_non_adr_filename_in_the_one_home_is_still_skipped(self):
        """The scope half: the `ADR-` prefix became optional, nothing else did."""
        self.write("docs/adr/README.md", "# How we write ADRs\n")
        self.write("docs/adr/notes-0099-scratch.md", adr(99, "scratch"))
        r = self.sa("adrs", "--epic", "E003", "--format", "json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([x["number"] for x in json.loads(r.stdout)], [1, 3, 5])

    def test_accepts_the_bare_epic_number(self):
        r = self.sa("adrs", "--epic", "3", "--format", "json")
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = json.loads(r.stdout)
        self.assertEqual([x["number"] for x in rows], [1, 3, 5])
        self.assertEqual(rows[0]["departs"], f"{ARCH_REL}#order-api")
        self.assertEqual(rows[2]["home"], "legacy")

    def test_check_links_reports_an_unlinked_departure(self):
        r = self.sa("check-links")
        self.assertEqual(r.returncode, 1)
        self.assertIn("0001-order-api.md", r.stdout)
        self.assertIn("section does not link the ADR", r.stdout)
        self.assertNotIn("0003-draft", r.stdout)            # Proposed: not a departure yet

    def test_check_links_passes_once_the_section_links_it(self):
        self.write(ARCH_REL, ARCH.replace(
            "POST /orders accepts a body.",
            "POST /orders accepts a body. See [ADR-0001](../../docs/adr/0001-order-api.md)."))
        r = self.sa("check-links", "--epic", "E003")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_check_links_reports_a_dangling_pointer(self):
        self.write("docs/adr/0004-gone.md", adr(4, "gone", departs=f"{ARCH_REL}#removed"))
        r = self.sa("check-links")
        self.assertEqual(r.returncode, 1)
        self.assertIn("0004-gone.md", r.stdout)
        self.assertIn("pointer does not resolve", r.stdout)

    def test_check_links_refuses_an_unparseable_epic(self):
        r = self.sa("check-links", "--epic", "not-an-epic")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not-an-epic", r.stderr)


class TestLease(Project):
    def lease(self, *args):
        return self.sa("lease", *args)

    def test_acquire_then_contend(self):
        self.assertEqual(self.lease("acquire", "--owner", "E001", "--wait-minutes", "0")
                         .returncode, 0)
        r = self.lease("acquire", "--owner", "E002", "--wait-minutes", "0")
        self.assertEqual(r.returncode, 5)
        self.assertIn("held by E001", r.stderr)
        self.assertEqual(self.lease("acquire", "--owner", "E001", "--wait-minutes", "0")
                         .returncode, 0)                      # the owner may refresh

    def test_expired_lease_is_taken_over_and_logged(self):
        self.lease("acquire", "--owner", "E001", "--ttl-minutes", "0", "--wait-minutes", "0")
        r = self.lease("acquire", "--owner", "E002", "--wait-minutes", "0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("E001", r.stderr)
        self.assertIn("taking it over", r.stderr)

    def test_release_rules(self):
        self.assertEqual(self.lease("release", "--owner", "E001").returncode, 0)   # free: no-op
        self.lease("acquire", "--owner", "E001", "--wait-minutes", "0")
        r = self.lease("release", "--owner", "E002")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.lease("release", "--owner", "E001").returncode, 0)
        self.assertEqual(self.lease("acquire", "--owner", "E002", "--wait-minutes", "0")
                         .returncode, 0)

    def test_lease_file_lives_in_the_state_root(self):
        self.lease("acquire", "--owner", "E001", "--wait-minutes", "0")
        with open(os.path.join(self.state, "spec-sync.lock"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["owner"], "E001")

    def test_real_processes_contending_get_exactly_one_winner(self):
        g = ["--project-root", self.root, "--impl-root", self.impl, "--state-root", self.state]
        procs = [subprocess.Popen([sys.executable, SCRIPT, *g, "lease", "acquire", "--owner",
                                   f"E{i:03d}", "--wait-minutes", "0"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(1, 7)]
        codes = [p.wait(timeout=120) for p in procs]
        for p in procs:
            p.stdout.close()
            p.stderr.close()
        self.assertEqual(sorted(codes), [0, 5, 5, 5, 5, 5])

    def test_a_waiter_gets_the_lease_when_the_holder_releases(self):
        self.lease("acquire", "--owner", "E001", "--wait-minutes", "0")
        g = ["--project-root", self.root, "--impl-root", self.impl, "--state-root", self.state]
        waiter = subprocess.Popen([sys.executable, SCRIPT, *g, "lease", "acquire", "--owner",
                                   "E002", "--wait-minutes", "0.5", "--poll-seconds", "0.1"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(0.6)
        self.assertEqual(self.lease("release", "--owner", "E001").returncode, 0)
        out, err = waiter.communicate(timeout=120)
        self.assertEqual(waiter.returncode, 0, err.decode())


class TestMigrateAdrs(Project):
    def setUp(self):
        super().setUp()
        self.write("docs/adr/0003-stack.md", adr(3, "stack", epic="n/a"))
        self.write(f"{IMPL}/epic-001/arch/adr-0003-auth.md",
                   "# ADR-0003: auth\n\n- **Status:** Accepted\n\n## Context\n\nx\n")
        self.write(f"{IMPL}/epic-001/arch/adr-0004-cache.md",
                   "# ADR-0004: cache\n\n- **Status:** Accepted\n\n## Context\n\ny\n")
        self.s1 = f"{IMPL}/epic-001/sprint-01/stories/E001-S01-001.md"
        self.s2 = f"{IMPL}/epic-002/sprint-01/stories/E002-S01-001.md"
        self.write(self.s1, f"# S\n\nPer ADR-0003 and {IMPL}/epic-001/arch/adr-0004-cache.md.\n")
        self.write(self.s2, "# S\n\nPer ADR-0003 (the stack).\n")
        self.init_git()

    def run_json(self, *args):
        r = self.sa("migrate-adrs", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_plan_is_read_only(self):
        out = self.run_json("--plan")
        moves = {m["from"]: m for m in out["moves"]}
        self.assertTrue(moves[f"{IMPL}/epic-001/arch/adr-0003-auth.md"]["collision"])
        self.assertEqual(moves[f"{IMPL}/epic-001/arch/adr-0004-cache.md"]["to"],
                         "docs/adr/0004-cache.md")
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_apply_moves_renumbers_rewrites_and_commits(self):
        out = self.run_json("--apply")
        self.assertEqual(self.git("log", "-1", "--format=%s").strip(),
                         "docs(adr): migrate epic ADRs to docs/adr")
        self.assertEqual(out["commit"], self.git("rev-parse", "HEAD").strip())
        # no collision: moved, Epic line added, exact path reference rewritten
        cache = self.read("docs/adr/0004-cache.md")
        self.assertIn("- **Epic:** E001", cache)
        self.assertIn("docs/adr/0004-cache.md", self.read(self.s1))
        # collision: docs/adr keeps 0003; the epic ADR gets a fresh number (disk max 4 -> 5)
        auth = self.read("docs/adr/0005-auth.md")
        self.assertTrue(auth.startswith("# ADR-0005: auth"))
        self.assertIn("ADR-0005", self.read(self.s1))           # inside epic-001: rewritten
        self.assertIn("ADR-0003", self.read(self.s2))           # elsewhere: left alone...
        self.assertIn(self.s2, {r["file"] for r in out["review"]})   # ...and listed
        self.assertFalse(os.path.exists(self.path(f"{IMPL}/epic-001/arch/adr-0003-auth.md")))
        tracked = self.git("ls-files", "docs/adr").split()
        self.assertEqual(sorted(tracked), ["docs/adr/0003-stack.md", "docs/adr/0004-cache.md",
                                           "docs/adr/0005-auth.md"])
        self.assertEqual(self.git("status", "--porcelain", "--",
                                  "docs", f"{IMPL}/epic-001", f"{IMPL}/epic-002").strip(), "")

    def test_same_number_AND_slug_is_a_duplicate_not_a_collision(self):
        """An epic ADR already migrated is a LEFTOVER, not a competing decision.

        Renumbering it mints a stale duplicate under a fresh number. Observed on a real
        project (houserules, 2026-09-25): all 14 legacy ADRs were same-number-same-slug
        duplicates, and --apply would have invented ADRs 36-49 for them, then rewritten the
        epic artifacts to cite the invented numbers. DOC_ADR_RE matched the slug with `.+`
        but never captured it, so the collision test compared numbers only.
        """
        self.write("docs/adr/0009-cache-policy.md", adr(9, "cache-policy", epic="E003"))
        self.write(f"{IMPL}/epic-003/arch/adr-0009-cache-policy.md",
                   "# ADR-0009: cache-policy\n\n- **Status:** Accepted\n\n## Context\n\nstale\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "duplicate fixture")
        mv = {m["from"]: m for m in self.run_json("--plan")["moves"]}[
            f"{IMPL}/epic-003/arch/adr-0009-cache-policy.md"]
        self.assertTrue(mv["duplicate"], "same number AND slug must classify as duplicate")
        self.assertFalse(mv["collision"], "a duplicate must never be renumbered")
        self.assertIsNone(mv["to"])

    def test_same_number_DIFFERENT_slug_is_still_a_collision(self):
        """The genuine competing-decision case must keep renumbering."""
        mv = {m["from"]: m for m in self.run_json("--plan")["moves"]}[
            f"{IMPL}/epic-001/arch/adr-0003-auth.md"]
        self.assertTrue(mv["collision"])
        self.assertFalse(mv["duplicate"])

    def test_apply_leaves_a_duplicate_in_place_and_reports_it(self):
        """--apply must not move, renumber, or delete a duplicate: it reports it."""
        self.write("docs/adr/0009-cache-policy.md", adr(9, "cache-policy", epic="E003"))
        dup_rel = f"{IMPL}/epic-003/arch/adr-0009-cache-policy.md"
        self.write(dup_rel,
                   "# ADR-0009: cache-policy\n\n- **Status:** Accepted\n\n## Context\n\nstale\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "duplicate fixture")
        out = self.run_json("--apply")
        self.assertTrue(os.path.exists(self.path(dup_rel)),
                        "the duplicate must stay where it is")
        self.assertIn(dup_rel, {d["from"] for d in out["duplicates"]})
        self.assertFalse(os.path.exists(self.path("docs/adr/0010-cache-policy.md")),
                         "no fresh number may be minted for a duplicate")
        self.assertEqual(self.read("docs/adr/0009-cache-policy.md"),
                         adr(9, "cache-policy", epic="E003"),
                         "the canonical docs/adr copy must be untouched")

    def test_nothing_to_move(self):
        self.git("rm", "-q", "-r", f"{IMPL}/epic-001/arch")
        self.git("commit", "-q", "-m", "no legacy")
        out = self.run_json("--apply")
        self.assertEqual((out["moves"], out["commit"]), ([], None))

    def test_register_lag_is_reported(self):
        with open(os.path.join(self.state, "adr-register.yaml"), "w", encoding="utf-8") as fh:
            fh.write("next: 2\nreserved: []\n")
        reg = self.run_json("--plan")["register"]
        self.assertEqual(reg, {"next": 2, "highest_on_disk": 4, "lagging": True})

    def test_collision_between_two_legacy_adrs_in_different_epics_gets_distinct_numbers(self):
        # ADR-0005's most careful scenario: two legacy ADRs in different epics share a number.
        # The first one seen keeps it; the second collides and must be reserved a fresh one,
        # and that renumber must stay scoped to its own epic tree (never the other epic's).
        self.write(f"{IMPL}/epic-005/arch/adr-0007-first.md", adr(7, "first", epic="E005"))
        self.write(f"{IMPL}/epic-006/arch/adr-0007-second.md", adr(7, "second", epic="E006"))
        s5 = f"{IMPL}/epic-005/sprint-01/stories/E005-S01-001.md"
        s6 = f"{IMPL}/epic-006/sprint-01/stories/E006-S01-001.md"
        self.write(s5, "# S\n\nPer ADR-0007.\n")
        self.write(s6, "# S\n\nPer ADR-0007.\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "two legacy ADRs sharing a number")
        out = self.run_json("--apply")
        moved = {m["epic"]: m for m in out["moves"] if m["slug"] in ("first", "second")}
        self.assertFalse(moved["E005"]["collision"])              # first seen: keeps 0007
        self.assertTrue(moved["E006"]["collision"])                # second seen: reserved fresh
        self.assertEqual(moved["E005"]["to"], "docs/adr/0007-first.md")
        n6 = moved["E006"]["renumbered_to"]
        self.assertNotEqual(n6, 7)
        self.assertIn(f"ADR-{n6:04d}", self.read(s6))               # its own story: rewritten
        self.assertNotIn(f"ADR-{n6:04d}", self.read(s5))            # the other epic: untouched
        self.assertIn("ADR-0007", self.read(s5))                    # E005's own number: unchanged
        tracked = set(self.git("ls-files", "docs/adr").split())
        self.assertIn("docs/adr/0007-first.md", tracked)
        self.assertIn(moved["E006"]["to"], tracked)

    def test_add_epic_line_inserts_after_title_when_no_status_line(self):
        self.write(f"{IMPL}/epic-007/arch/adr-0009-nostat.md",
                   "# ADR-0009: nostat\n\n## Context\n\nno status line here\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "legacy ADR without a Status line")
        out = self.run_json("--apply")
        [mv] = [m for m in out["moves"] if m["slug"] == "nostat"]
        body = self.read(mv["to"])
        self.assertTrue(body.startswith("# ADR-0009: nostat\n\n- **Epic:** E007\n"))

    def test_apply_refuses_when_the_touched_paths_are_already_dirty(self):
        self.write(f"{IMPL}/epic-001/arch/stray.md", "stray uncommitted change\n")
        before = self.git("status", "--porcelain")
        r = self.sa("migrate-adrs", "--apply")
        self.assertEqual(r.returncode, 2)
        self.assertIn("uncommitted", r.stderr.lower())
        self.assertFalse(os.path.exists(self.path("docs/adr/0004-cache.md")))   # nothing moved
        self.assertEqual(self.git("status", "--porcelain"), before)             # tree unchanged

    def test_apply_refuses_when_a_non_source_epic_reference_is_dirty(self):
        # A story outside every source epic can still reference the moved ADR's old path (the
        # loop's path_re.sub runs over every *.md under the implementation root, not just the
        # source epics), so the pre-flight must check it individually, not assume it clean.
        ref = f"{IMPL}/epic-003/sprint-01/stories/E003-S01-001.md"
        self.write(ref, f"# S\n\nSee {IMPL}/epic-001/arch/adr-0004-cache.md for context.\n")
        before = self.git("status", "--porcelain")
        r = self.sa("migrate-adrs", "--apply")
        self.assertEqual(r.returncode, 2)
        self.assertIn("uncommitted", r.stderr.lower())
        self.assertFalse(os.path.exists(self.path("docs/adr/0004-cache.md")))   # nothing moved
        self.assertEqual(self.git("status", "--porcelain"), before)             # tree unchanged

    def test_apply_reports_touched_paths_when_the_commit_fails(self):
        """The move loop succeeds, every ADR is moved and rewritten, and only the final
        commit fails. What this guards is the touched-path report: a half-applied migration
        that does not say what it touched leaves a human to find the moved files by hand.

        THE COMMIT IS FAILED DETERMINISTICALLY, by a `pre-commit` hook that exits 1. Two
        earlier versions planted `.git/index.lock` from a background thread and raced the
        subprocess, which failed in CI two different ways within three days: landing while
        git held the lock corrupted the index so the generic `git commit failed` branch fired
        instead of "stayed locked", and landing not at all let the commit SUCCEED, so the
        test saw returncode 0. A gate that fails for a reason unrelated to its subject is
        worse than no gate, and relaxing the assertion twice was treating the symptom.

        A hook is exact: `git mv` and `git add` do not run hooks, so the move loop is
        untouched and only `git commit` fails — which is precisely the state this test wants
        and the thread was approximating.
        """
        hooks = self.path(".git/hooks")
        os.makedirs(hooks, exist_ok=True)
        hook = os.path.join(hooks, "pre-commit")
        with open(hook, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\nexit 1\n")
        os.chmod(hook, 0o755)
        self.addCleanup(lambda: os.path.exists(hook) and os.remove(hook))

        r = self.sa("migrate-adrs", "--apply")
        self.assertEqual(r.returncode, 2, r.stderr)

        # THE CONTRACT: every path already touched is named, so a human can inspect or
        # revert exactly those rather than hunting for them.
        self.assertIn("paths already moved or rewritten in this run", r.stderr)
        self.assertIn("docs/adr/0004-cache.md", r.stderr)
        self.assertIn("git commit failed", r.stderr)


if __name__ == "__main__":
    unittest.main()
