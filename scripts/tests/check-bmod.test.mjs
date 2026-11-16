// scripts/check-bmod.mjs — runs BMad's validate_manifests.py over a view of skills/ that leaves
// out skills/_shared/, which the validator would otherwise report as a skill missing bmod.toml.
//
// The real validator needs the network to fetch; these tests substitute a stand-in through
// CHECK_BMOD_VALIDATOR so the view and the cleanup rules are tested offline.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { buildView, VIEW_PREFIX } from "../check-bmod.mjs";

const SCRIPT = path.join(import.meta.dirname, "..", "check-bmod.mjs");

function tree(t, files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "l3io-check-bmod-test-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const [rel, text] of Object.entries(files)) {
    const abs = path.join(root, rel);
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    fs.writeFileSync(abs, text);
  }
  return root;
}

const REPO_FILES = {
  "skills/_shared/x.md": "shared\n",
  "skills/_shared/tests/test-x.py": "",
  "skills/m1/s1/SKILL.md": "---\nname: s1\n---\n",
  "skills/m1/s1/bmod.toml": "[skill]\n",
  "skills/m1/s1/__pycache__/a.pyc": "",
  "skills/m2/s2/SKILL.md": "---\nname: s2\n---\n",
};

test("buildView copies every module folder and leaves out _shared and __pycache__", (t) => {
  const repo = tree(t, REPO_FILES);
  const view = fs.mkdtempSync(path.join(os.tmpdir(), "l3io-check-bmod-test-view-"));
  t.after(() => fs.rmSync(view, { recursive: true, force: true }));
  assert.deepEqual(buildView(repo, view), ["m1", "m2"]);
  assert.equal(fs.existsSync(path.join(view, "skills", "_shared")), false);
  assert.equal(fs.readFileSync(path.join(view, "skills/m1/s1/bmod.toml"), "utf8"), "[skill]\n");
  assert.ok(fs.existsSync(path.join(view, "skills/m2/s2/SKILL.md")));
  assert.equal(fs.existsSync(path.join(view, "skills/m1/s1/__pycache__")), false);
});

test("buildView refuses a tree with nothing but _shared", (t) => {
  const repo = tree(t, { "skills/_shared/x.md": "" });
  const view = fs.mkdtempSync(path.join(os.tmpdir(), "l3io-check-bmod-test-view-"));
  t.after(() => fs.rmSync(view, { recursive: true, force: true }));
  assert.throws(() => buildView(repo, view), /no module folder/);
});

// A stand-in validator: records the --project-root it was given and what that view held, then
// exits with the code the test asks for.
function standIn(t, exitCode) {
  const dir = tree(t, {});
  const record = path.join(dir, "seen.json");
  const script = path.join(dir, "validator.py");
  fs.writeFileSync(script, [
    "# /// script",
    '# requires-python = ">=3.11"',
    "# ///",
    "import json, os, sys",
    "root = sys.argv[sys.argv.index('--project-root') + 1]",
    `json.dump({'root': root, 'top': sorted(os.listdir(os.path.join(root, 'skills')))}, open(${JSON.stringify(record)}, 'w'))`,
    `print('stand-in says', ${exitCode}, file=sys.stderr)`,
    `sys.exit(${exitCode})`,
    "",
  ].join("\n"));
  return { script, seen: () => JSON.parse(fs.readFileSync(record, "utf8")) };
}

function run(repo, validator) {
  return spawnSync(process.execPath, [SCRIPT], {
    cwd: repo, encoding: "utf8",
    env: { ...process.env, CHECK_BMOD_VALIDATOR: validator },
  });
}

test("a passing run validates the view without _shared and removes it", (t) => {
  const repo = tree(t, REPO_FILES);
  const v = standIn(t, 0);
  const r = run(repo, v.script);
  assert.equal(r.status, 0, r.stderr);
  const seen = v.seen();
  assert.deepEqual(seen.top, ["m1", "m2"]);
  assert.ok(path.basename(seen.root).startsWith(VIEW_PREFIX), seen.root);
  assert.equal(fs.existsSync(seen.root), false, "a passing run removes its view");
});

test("a failing run keeps its view, names it, and passes the validator's exit through", (t) => {
  const repo = tree(t, REPO_FILES);
  const v = standIn(t, 1);
  const r = run(repo, v.script);
  const { root } = v.seen();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  assert.equal(r.status, 1);
  assert.match(r.stderr, /stand-in says 1/);
  assert.ok(fs.existsSync(root), "a failing run keeps its view");
  assert.ok(r.stderr.includes(root), `the kept view is named: ${r.stderr}`);
});
