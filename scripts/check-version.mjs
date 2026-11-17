#!/usr/bin/env node
// pm-status.py's version, and every module record's version, must equal the package release
// version.
//
// Why pm-status.py's part exists: BMad v7 installs pm_status once per module that declares it,
// and the two copies can be set up at different times. The doctor's version report, and the
// health check's skew finding built on it, read each installed copy's version off its
// top-of-file `# pm-status-version:` marker without running it, while `--version` and `report`
// print the PM_STATUS_VERSION constant. If those two disagree, one copy answers two questions
// differently and the skew finding compares the wrong number. The version is also the
// package's: postbump writes it from package.json alongside every bmod.toml, because a
// hand-maintained version on its own release line has drifted here before.
//
// This check asserts the invariant that makes the reported version mean the package release:
//
//   marker == PM_STATUS_VERSION == package.json version
//
// It holds at every point in the cycle, not just at release -- mid-cycle all three sit at the
// last released version -- so it is checkable on any commit.
//
// Why the module-version part exists: sync-bmad-versions.mjs's postbump loop writes every module
// record's version, and a writer with no reader can drift silently -- the loop could stop
// finding files and log a success-shaped line forever. BMad's validate_manifests.py also
// requires one version across every record in a repository. Scope is derived by walking
// skills/ for every bmod.toml -- never a hand-kept list of module codes.
//
// Usage: node scripts/check-version.mjs [-v]
import fs from "node:fs";
import path from "node:path";
import { writeAllSync } from "./write-all-sync.mjs";
import { parse as parseToml } from "smol-toml";
import { bmodFiles, statedVersions } from "./lib/bmod-records.mjs";

// CHECK_VERSION_ROOT points the checker at another tree -- scripts/tests/check-version.test.mjs
// runs it against fixtures built from an empty skills/ tree.
const repoRoot = process.env.CHECK_VERSION_ROOT ? path.resolve(process.env.CHECK_VERSION_ROOT) : process.cwd();
const verbose = process.argv.includes("-v");
const failures = [];

const read = (p) => fs.readFileSync(path.join(repoRoot, p), "utf8");
const exists = (p) => fs.existsSync(path.join(repoRoot, p));

const PM = "skills/_shared/pm_status/__main__.py";
const PM_DIR = "skills/_shared/pm_status";
const PKG = "package.json";

if (!exists(PM)) {
  // Terminating on purpose: everything below reads PM. writeAllSync has already delivered the
  // message by the time it returns, so process.exit discards nothing.
  writeAllSync(2, `✗ ${PM} not found\n`);
  process.exit(1);
}
const text = read(PM);
const marker = (text.match(/^#\s*pm-status-version:\s*([0-9.]+)/m) || [])[1];

// The marker is `__main__.py`'s by contract -- the doctor reads it off each installed copy's
// `__main__.py`. The CONSTANT is not: it travels with whichever module owns it, and it left for
// core/ when core was extracted. Its file is DERIVED by searching the package rather than named
// here, so the next move needs no edit; two declarations, or none, is itself a failure, because
// a second copy is exactly the hand-maintained duplicate this check exists to prevent.
const KONST_RE = /^PM_STATUS_VERSION\s*=\s*"([0-9.]+)"/m;
function konstFiles(rel) {
  const out = [];
  for (const e of fs.readdirSync(path.join(repoRoot, rel), { withFileTypes: true })
    .sort((a, b) => a.name.localeCompare(b.name))) {
    const child = `${rel}/${e.name}`;
    if (e.isDirectory()) { if (e.name !== "__pycache__") out.push(...konstFiles(child)); }
    else if (e.name.endsWith(".py") && KONST_RE.test(read(child))) out.push(child);
  }
  return out;
}
const konstIn = konstFiles(PM_DIR);
const KONST = konstIn[0] || PM;
const konst = konstIn.length === 1 ? (read(KONST).match(KONST_RE) || [])[1] : undefined;
const pkg = JSON.parse(read(PKG)).version;

if (!marker) failures.push(`${PM}: no "# pm-status-version:" marker found`);
if (konstIn.length === 0) failures.push(`${PM_DIR}/: no PM_STATUS_VERSION constant found in any module`);
if (konstIn.length > 1) {
  failures.push(
    `${PM_DIR}/: PM_STATUS_VERSION is declared in ${konstIn.length} files (${konstIn.join(", ")})\n` +
      "      It must be declared exactly once. Two copies are two things to keep in sync, and\n" +
      "      this check cannot tell which one `--version` prints.",
  );
}

if (marker && konst && marker !== konst) {
  failures.push(
    `${PM}: marker says ${marker} but PM_STATUS_VERSION says ${konst} (in ${KONST})\n` +
      `      The doctor reads the marker off each installed copy and --version prints the\n` +
      `      constant, so these disagreeing makes one copy report two versions.`,
  );
}

if (marker && konst && marker === konst && marker !== pkg) {
  failures.push(
    `${PM}: version is ${marker} but ${PKG} says ${pkg}\n` +
      `      These share one release line. postbump writes pm-status.py's version from\n` +
      `      package.json, so a mismatch means either the script was hand-edited or a release\n` +
      `      did not complete. Do not hand-edit the version: run a release, or\n` +
      `      "node scripts/sync-bmad-versions.mjs" to bring it back in line.\n` +
      `      NEVER set it backwards -- a lowered version makes a newer copy read as older in\n` +
      `      the doctor's version report and skew finding.`,
  );
}

// Every v7 module record's `[bmod]` version, and each requirement on one of this repository's
// own modules, must equal package.json's version. sync-bmad-versions.mjs writes them at
// postbump; this is the reader that proves it did. Scope is every bmod.toml under skills/
// (bmodFiles), never a list of module codes.
let moduleChecked = 0;
for (const rel of bmodFiles(repoRoot)) {
  let data;
  try {
    data = parseToml(read(rel));
  } catch (e) {
    failures.push(`${rel}: is not valid TOML (${String(e.message).split("\n")[0]})`);
    continue;
  }
  if (data.bmod) moduleChecked += 1;
  for (const { where, version } of statedVersions(data)) {
    if (version === pkg) continue;
    failures.push(
      `${rel}: ${where} is ${version} but ${PKG} says ${pkg}\n` +
        `      postbump writes every module record's version from package.json (see\n` +
        `      sync-bmad-versions.mjs); a mismatch means a release did not complete or the\n` +
        `      file was hand-edited. Do not hand-edit it: run a release, or\n` +
        `      "node scripts/sync-bmad-versions.mjs" to bring it back in line.`,
    );
  }
}

// One buffered write, then `process.exitCode`. This reporter's line count is bounded by the
// number of module records, so it is well under the ~300 lines where the console loop starts
// losing findings -- it follows the rule anyway, because "this one is short enough" is the
// judgement that has to be re-made correctly every time someone adds a failure. See
// scripts/write-all-sync.mjs.
if (failures.length) {
  writeAllSync(2,
    `\n${failures.length} version problem(s):\n\n` +
    failures.map((f) => `  ✗ ${f}\n\n`).join(""));
  process.exitCode = 1;
} else {
  // The `else` is load-bearing, not tidying: dropping `process.exit(1)` for `process.exitCode`
  // means execution FALLS THROUGH, and a failing run would otherwise print "version check
  // passed" underneath its own failures and exit 1 -- the worst of both.
  if (verbose) {
    console.log(`  pm-status-version: ${marker} == PM_STATUS_VERSION == ${PKG}`);
    console.log(`  module-version: ${moduleChecked} module record(s) at ${pkg}`);
  }
  console.log(
    `pm-status.py version check passed: ${marker} in all three places; ` +
      `${moduleChecked} module record(s) at ${pkg}.`,
  );
}
