#!/usr/bin/env node
// Run BMad v7's own manifest validator, `validate_manifests.py`, over this repository's skills.
//
// It is the gate for the v7 packaging (ADR-0014): every skill's bmod.toml, each module's record,
// retired.toml, roster.toml, help/help.md, one version across every record, and a dry run of
// setup.py's own module discovery over the tree as it would install. It replaces the 6.x
// installer rules `check:module` used to model by hand and the `check:bmb` scanners.
//
// THE VIEW. The validator treats every folder under skills/ as a skill or a group of skills, and
// skills/_shared/ — this package's canonical sources, never installed (ADR-0021) — is neither: it
// reports `skills/_shared: missing bmod.toml`. So it runs over a copy of skills/ without
// `_shared`, built in a temp directory named `l3io-check-bmod-*`. A passing run removes it; a
// failing run KEEPS it and prints its path, so the tree the findings describe can be inspected.
//
// THE VALIDATOR is never bundled (root CLAUDE.md: never bundle a BMad core script). It is
// fetched at the pin through scripts/fetch-bmad-tool.mjs, verified by SHA-256, with the three
// files it imports from its own directory, and run through `uv` like every Python entry point
// here. CI therefore needs network for this step. A `uv` that cannot spawn fails the gate.
//
// CHECK_BMOD_VALIDATOR=<script> substitutes the validator; scripts/tests/check-bmod.test.mjs
// uses it to test the view and the cleanup offline.
//
// Usage: node scripts/check-bmod.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { fetchBmadTool, PIN } from "./fetch-bmad-tool.mjs";
import { writeAllSync } from "./write-all-sync.mjs";

export const VIEW_PREFIX = "l3io-check-bmod-";
const SHARED = "_shared";
const SKIP = new Set(["__pycache__"]);
const VALIDATOR_DIR = "skills/core-tools/bmad/scripts";
// validate_manifests.py first: it is the one that runs; the rest are what it loads beside it.
const VALIDATOR_FILES = ["validate_manifests.py", "setup.py", "knowledge.py", "list_templates.py"];

// Copy every folder under <repo>/skills/ except _shared into <viewRoot>/skills/. Returns the
// folder names copied. Copies rather than links, so the validator reads a real tree.
export function buildView(repoRoot, viewRoot) {
  const src = path.join(repoRoot, "skills");
  const tops = fs.readdirSync(src, { withFileTypes: true })
    .filter((e) => e.isDirectory() && e.name !== SHARED && !SKIP.has(e.name))
    .map((e) => e.name)
    .sort();
  if (tops.length === 0) throw new Error(`no module folder under ${src} besides ${SHARED}/`);
  for (const top of tops) {
    fs.cpSync(path.join(src, top), path.join(viewRoot, "skills", top), {
      recursive: true,
      filter: (p) => !SKIP.has(path.basename(p)),
    });
  }
  return tops;
}

async function validatorPath() {
  if (process.env.CHECK_BMOD_VALIDATOR) return path.resolve(process.env.CHECK_BMOD_VALIDATOR);
  const paths = [];
  for (const f of VALIDATOR_FILES) paths.push(await fetchBmadTool(PIN, `${VALIDATOR_DIR}/${f}`));
  return paths[0];
}

async function main() {
  const repoRoot = process.cwd();
  let validator;
  try {
    validator = await validatorPath();
  } catch (e) {
    writeAllSync(2, `check:bmod: cannot obtain validate_manifests.py at ${PIN}: ${e.message}\n`);
    return 2;
  }

  const view = fs.mkdtempSync(path.join(os.tmpdir(), VIEW_PREFIX));
  let status = 1;
  try {
    buildView(repoRoot, view);
    const r = spawnSync("uv", ["run", "--quiet", "--no-project", validator, "--project-root", view], {
      stdio: "inherit",
    });
    if (r.error) {
      writeAllSync(2, `check:bmod: cannot run uv: ${r.error.message}\n`);
      status = 2;
    } else {
      status = r.status ?? 1;
    }
  } finally {
    if (status === 0) {
      fs.rmSync(view, { recursive: true, force: true });
    } else {
      writeAllSync(2, `check:bmod: failed; the validated view is kept at ${view}\n`);
    }
  }
  return status;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = await main();
}
