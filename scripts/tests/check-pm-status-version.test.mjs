// Tests for scripts/check-pm-status-version.mjs.
// Run: npm run test:scripts
// Each test runs the REAL checker (via CHECK_VERSION_ROOT) against a fixture built from an
// EMPTY tree -- unlike check-docs.test.mjs's fixture(t), this does not copy the repo, because
// these tests construct pm-status.py / package.json / module records from nothing rather than
// mutating real ones.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CHECK = path.join(REPO, "scripts", "check-pm-status-version.mjs");

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "check-version-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}

function run(root, args = []) {
  return spawnSync(process.execPath, [CHECK, ...args], {
    cwd: REPO,
    env: { ...process.env, CHECK_VERSION_ROOT: root },
    encoding: "utf8",
  });
}

function write(root, rel, text) {
  const p = path.join(root, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, text);
}

function writePkg(root, version) {
  write(root, "package.json", JSON.stringify({ name: "fixture", version }));
}

function writePmStatus(root, version) {
  write(root, "skills/_shared/pm_status/__main__.py",
    `# pm-status-version: ${version}\nPM_STATUS_VERSION = "${version}"\n`);
}

// A v7 module record: a `[bmod]` table in `skills/<dir>/bmod.toml` (ADR-0014).
function writeRecord(root, dir, code, version, extra = "") {
  write(root, `skills/${dir}/SKILL.md`, "");
  write(root, `skills/${dir}/bmod.toml`,
    `[bmod]\ncode = "${code}"\nversion = "${version}"\nupdate_source = "file:x"\n${extra}`);
}

test("a consistent tree at one version passes", (t) => {
  const root = fixture(t);
  writePkg(root, "1.2.3");
  writePmStatus(root, "1.2.3");
  writeRecord(root, "solo/solo", "solo", "1.2.3");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
  assert.match(r.stdout, /1 module record\(s\) at 1\.2\.3/);
});

test("a module record at the wrong version is caught", (t) => {
  const root = fixture(t);
  writePkg(root, "1.2.3");
  writePmStatus(root, "1.2.3");
  writeRecord(root, "solo/solo", "solo", "1.2.2");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /skills\/solo\/solo\/bmod\.toml: \[bmod\] version is 1\.2\.2 but package\.json says 1\.2\.3/);
});

test("a requirement on this repository's own module at the wrong version is caught", (t) => {
  const root = fixture(t);
  writePkg(root, "1.2.3");
  writePmStatus(root, "1.2.3");
  writeRecord(root, "pm/bmod-pm", "pm", "1.2.3", 'required_skills = [\n' +
    '  { skill = "l3io-doctor", version = "1.0.0", source = "github:LiquidLogicLabs/bmad-extensions/skills/l3io-util" },\n]\n');
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /bmod\.required_skills 'l3io-doctor' is 1\.0\.0/);
});

test("a requirement on another repository keeps its own version", (t) => {
  const root = fixture(t);
  writePkg(root, "1.2.3");
  writePmStatus(root, "1.2.3");
  writeRecord(root, "pm/bmod-pm", "pm", "1.2.3", 'required_skills = [\n' +
    '  { skill = "bmad", version = "6.13.0", source = "github:bmad-code-org/BMAD-METHOD/skills/core-tools" },\n]\n');
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("multiple module records at the release version all pass together", (t) => {
  const root = fixture(t);
  writePkg(root, "2.0.0");
  writePmStatus(root, "2.0.0");
  writeRecord(root, "a/bmod-a", "a", "2.0.0");
  writeRecord(root, "b/b", "b", "2.0.0");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
  assert.match(r.stdout, /2 module record\(s\)/);
});

test("_shared is never treated as a module record", (t) => {
  const root = fixture(t);
  writePkg(root, "1.0.0");
  writePmStatus(root, "1.0.0");
  write(root, "skills/_shared/bmod.toml", '[bmod]\ncode = "x"\nversion = "0.0.1"\nupdate_source = "file:x"\n');
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("no module records at all still passes on pm-status.py's own invariant", (t) => {
  const root = fixture(t);
  writePkg(root, "1.0.0");
  writePmStatus(root, "1.0.0");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
  assert.match(r.stdout, /0 module record\(s\)/);
});

test("pm-status.py marker/constant disagreement is still caught alongside module checks", (t) => {
  const root = fixture(t);
  writePkg(root, "1.0.0");
  write(root, "skills/_shared/pm_status/__main__.py",
    '# pm-status-version: 1.0.0\nPM_STATUS_VERSION = "0.9.9"\n');
  writeRecord(root, "solo/solo", "solo", "1.0.0");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /marker says 1\.0\.0 but PM_STATUS_VERSION says 0\.9\.9/);
});
