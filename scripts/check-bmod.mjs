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
// THE WIRE-IN ARM. `/l3io-doctor wire` writes l3io's hooks into a team's
// `_bmad/custom/<skill>.toml` (ADR-0020). v7 halts the render of the WHOLE host skill when a
// team file sets a key the skill does not declare (render_skill.py:122-128), or sets it with
// a type other than the shipped default's (:301-317), so one bad entry would break every
// invocation of the user's planner or builder. Every non-test entry in the doctor's
// `assets/wire-in.toml` is therefore judged against the host's customize.toml at the pin
// (fetched and SHA-256-verified like the validator): its `path` must be declared, and its
// kind must match the default -- `scalar` a string, `list` a list of strings, `keyed` a
// non-empty array of tables.
//
// CHECK_BMOD_VALIDATOR=<script> substitutes the validator, and CHECK_BMOD_CUSTOMIZE_DIR=<dir>
// (holding `<skill>/customize.toml`) the fetched defaults; scripts/tests/check-bmod.test.mjs
// uses both to test the view, the cleanup and the wire-in arm offline.
//
// Usage: node scripts/check-bmod.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { parse as parseToml } from "smol-toml";
import { fetchBmadTool, PIN } from "./fetch-bmad-tool.mjs";
import { writeAllSync } from "./write-all-sync.mjs";

export const VIEW_PREFIX = "l3io-check-bmod-";
const SHARED = "_shared";
const SKIP = new Set(["__pycache__"]);
const VALIDATOR_DIR = "skills/core-tools/bmad/scripts";
// validate_manifests.py first: it is the one that runs; the rest are what it loads beside it.
const VALIDATOR_FILES = ["validate_manifests.py", "setup.py", "knowledge.py", "list_templates.py"];

export const WIRE_IN_REL = "skills/l3io-util/l3io-doctor/assets/wire-in.toml";

// Where each host skill's shipped customize.toml lives in BMAD-METHOD.
export const CUSTOMIZE_PATHS = {
  "bmad-agent-po": "skills/method/bmad-agent-po/customize.toml",
  "bmad-build": "skills/method/bmad-build/customize.toml",
  "bmad-build-auto": "skills/method/bmad-build-auto/customize.toml",
  "bmad-retrospective": "skills/method/bmad-retrospective/customize.toml",
  "bmad-review": "skills/core-tools/bmad-review/customize.toml",
  "bmad-code-review": "skills/method/bmad-code-review/customize.toml",
};

function lookup(table, dotted) {
  let node = table;
  for (const part of dotted.split(".")) {
    if (node === null || typeof node !== "object" || Array.isArray(node) || !(part in node)) {
      return { found: false };
    }
    node = node[part];
  }
  return { found: true, value: node };
}

const isTable = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

// The kind of entry a shipped default accepts, as render_skill.py's
// _resolve_customization_value types it, or null for a default no wire-in kind can set.
function kindOf(value) {
  if (typeof value === "string") return "scalar";
  if (Array.isArray(value)) {
    if (value.length > 0 && value.every(isTable)) return "keyed";
    return "list";
  }
  return null;
}

// Findings for every non-test wire-in entry: one string each, starting with the entry id.
// `customize` maps a skill name to its parsed customize.toml.
export function checkWireIn(wireIn, customize) {
  const findings = [];
  for (const e of wireIn.entry ?? []) {
    if (e.test_only) continue;
    const defaults = customize[e.skill];
    if (!defaults) {
      findings.push(`${e.id}: no pinned customize.toml for skill ${e.skill} to judge it against`);
      continue;
    }
    const { found, value } = lookup(defaults, e.path);
    if (!found) {
      findings.push(`${e.id}: ${e.skill} does not declare ${e.path}; a team file setting it halts ` +
        `every render of ${e.skill} (render_skill.py:122-128)`);
      continue;
    }
    const want = kindOf(value);
    if (want !== e.kind) {
      findings.push(`${e.id}: ${e.skill}'s ${e.path} takes a ${want ?? "non-string value"}, ` +
        `not a ${e.kind} entry; the render would halt on its type (render_skill.py:301-317)`);
    }
  }
  return findings;
}

async function customizeFor(skills) {
  const out = {};
  const dir = process.env.CHECK_BMOD_CUSTOMIZE_DIR;
  for (const skill of skills) {
    let file;
    if (dir) {
      file = path.join(path.resolve(dir), skill, "customize.toml");
      if (!fs.existsSync(file)) continue;
    } else {
      if (!CUSTOMIZE_PATHS[skill]) continue;
      file = await fetchBmadTool(PIN, CUSTOMIZE_PATHS[skill]);
    }
    out[skill] = parseToml(fs.readFileSync(file, "utf8"));
  }
  return out;
}

// The wire-in arm over the checked tree. [] when the tree carries no wire-in.toml.
async function wireInFindings(repoRoot) {
  const file = path.join(repoRoot, WIRE_IN_REL);
  if (!fs.existsSync(file)) return [];
  const wireIn = parseToml(fs.readFileSync(file, "utf8"));
  const skills = [...new Set((wireIn.entry ?? []).filter((e) => !e.test_only).map((e) => e.skill))];
  return checkWireIn(wireIn, await customizeFor(skills));
}

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

  let wireIn;
  try {
    wireIn = await wireInFindings(repoRoot);
  } catch (e) {
    writeAllSync(2, `check:bmod: cannot judge ${WIRE_IN_REL}: ${e.message}\n`);
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
    if (wireIn.length > 0) {
      writeAllSync(2, `check:bmod: ${wireIn.length} wire-in entr${wireIn.length === 1 ? "y" : "ies"} ` +
        `the host skill would refuse:\n${wireIn.map((f) => `  ${f}`).join("\n")}\n`);
      if (status === 0) status = 1;
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
