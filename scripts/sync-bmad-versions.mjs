#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { bmodFiles, stampBmodVersion } from "./lib/bmod-records.mjs";

const repoRoot = process.cwd();
const packageJsonPath = path.join(repoRoot, "package.json");
const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
const releaseVersion = packageJson.version;

// Update pm-status.py's two version declarations to the release version.
//
// This is the whole reason the script's version line was merged into the release line: the
// marker used to be hand-maintained, and a hand-maintained invariant drifts. It did, twice
// -- ten commits changed the script under 2.3.0, then another changed it under 2.4.0 -- and
// self-install, which compared versions, kept reporting a stale copy as current. One project
// sat 920 lines behind under an identical number. Nobody has to remember this now.
//
// Runs before sync-shared-scripts.mjs in postbump, so the per-skill payload copies inherit
// the new version rather than drifting from _shared.
//
// The two declarations no longer live in the same file, and neither location is written out
// here. The MARKER is `__main__.py`'s, by contract -- self-install reads it off the installed
// copy's `__main__.py` -- but the CONSTANT travels with whichever module owns it (it left for
// core/ with the first extraction). Its file is DERIVED by searching the package, so the next
// move needs no edit here; declaring it twice, or not at all, fails rather than silently
// rewriting one of two copies or none.
const pmStatusDir = path.join(repoRoot, "skills", "_shared", "pm_status");
const pmStatusMarkerPath = path.join(pmStatusDir, "__main__.py");
// Not exported: this file writes on import, so a consumer that wanted the walker would run a
// release sync to get it. check-pm-status-version.mjs carries its own eight-line copy.
function pmStatusVersionFiles(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { if (e.name !== "__pycache__") out.push(...pmStatusVersionFiles(p)); }
    else if (e.name.endsWith(".py") && /^PM_STATUS_VERSION\s*=\s*"[0-9.]+"/m.test(fs.readFileSync(p, "utf8"))) out.push(p);
  }
  return out;
}
{
  const constFiles = pmStatusVersionFiles(pmStatusDir);
  if (constFiles.length !== 1) {
    throw new Error(`Expected exactly one PM_STATUS_VERSION declaration under ${pmStatusDir}, `
      + `found ${constFiles.length}${constFiles.length ? `: ${constFiles.join(", ")}` : ""}`);
  }
  const edits = [
    [pmStatusMarkerPath, /^(#\s*pm-status-version:\s*)[0-9.]+/m, `$1${releaseVersion}`,
      /^#\s*pm-status-version:\s*[0-9.]+/m, "# pm-status-version: marker"],
    [constFiles[0], /^(PM_STATUS_VERSION\s*=\s*")[0-9.]+"/m, `$1${releaseVersion}"`,
      /^PM_STATUS_VERSION\s*=\s*"[0-9.]+"/m, "PM_STATUS_VERSION"],
  ];
  for (const [file, find, replace, verify, what] of edits) {
    const before = fs.readFileSync(file, "utf8");
    const after = before.replace(find, replace);
    if (!verify.test(after)) throw new Error(`Could not rewrite ${what} in ${file}`);
    if (after !== before) {
      fs.writeFileSync(file, after, "utf8");
      console.log(`Synced ${what} in ${path.relative(repoRoot, file)} to ${releaseVersion}`);
    }
  }
}

// Stamp every v7 module record (ADR-0014): the `[bmod]` version, and each requirement on one
// of this repository's own modules, which is pinned to the release that ships it.
// validate_manifests.py requires every record in one repository to carry one version.
let bmodCount = 0;
for (const rel of bmodFiles(repoRoot)) {
  const file = path.join(repoRoot, rel);
  const before = fs.readFileSync(file, "utf8");
  let after;
  try {
    after = stampBmodVersion(before, releaseVersion);
  } catch (e) {
    throw new Error(`Could not stamp ${rel}: ${e.message}`);
  }
  if (after !== before) {
    fs.writeFileSync(file, after, "utf8");
    console.log(`Synced version in ${rel} to ${releaseVersion}`);
    bmodCount++;
  }
}
if (bmodCount === 0) {
  console.log("No bmod.toml files needed version update");
}
