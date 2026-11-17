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
import { parse as parseToml } from "smol-toml";
import { buildView, checkWireIn, CUSTOMIZE_PATHS, VIEW_PREFIX, WIRE_IN_REL } from "../check-bmod.mjs";

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

// The wire-in arm (Review Focus 1 of the Phase 4 plan): a team file may set only keys the v7
// skill declares, with the type of the shipped default, or render_skill.py halts EVERY
// invocation of that skill (render_skill.py:122-128, :301-317). The arm judges each non-test
// wire-in entry against the pinned customize.toml.
const BUILD_AUTO_CUSTOMIZE = [
  "[workflow]",
  "activation_steps_prepend = []",
  'on_complete = ""',
  'review = "quick"',
  "[[workflow.quick_lenses]]",
  'id = "quick"',
  'name = "Quick"',
  'instruction = "x"',
  "",
].join("\n");

const PO_CUSTOMIZE = [
  "[agent]",
  "[[agent.menu]]",
  'code = "SL"',
  'description = "Slice"',
  'prompt = "x"',
  "",
].join("\n");

function wireIn(entries) {
  return entries.map((e) => [
    "[[entry]]",
    `id = "${e.id}"`,
    `skill = "${e.skill}"`,
    `kind = "${e.kind}"`,
    `path = "${e.path}"`,
    ...(e.test_only ? ["test_only = true"] : []),
    ...(e.kind === "keyed"
      ? ["[entry.value]", 'code = "l3io-x"', 'prompt = "y"']
      : ['value = "y"']),
    "",
  ].join("\n")).join("\n");
}

test("checkWireIn names an undeclared key (workflow.interactive on bmad-build-auto)", () => {
  const findings = checkWireIn(parseToml(wireIn([
    { id: "planted", skill: "bmad-build-auto", kind: "scalar", path: "workflow.interactive" },
  ])), { "bmad-build-auto": parseToml(BUILD_AUTO_CUSTOMIZE) });
  assert.equal(findings.length, 1, findings.join("\n"));
  assert.match(findings[0], /planted/);
  assert.match(findings[0], /workflow\.interactive/);
  assert.match(findings[0], /bmad-build-auto/);
});

test("checkWireIn judges the kind against the shipped default", () => {
  const findings = checkWireIn(parseToml(wireIn([
    { id: "ok-scalar", skill: "bmad-build-auto", kind: "scalar", path: "workflow.on_complete" },
    { id: "ok-list", skill: "bmad-build-auto", kind: "list", path: "workflow.activation_steps_prepend" },
    { id: "ok-keyed", skill: "bmad-agent-po", kind: "keyed", path: "agent.menu" },
    { id: "bad-list", skill: "bmad-build-auto", kind: "list", path: "workflow.review" },
    { id: "bad-scalar", skill: "bmad-build-auto", kind: "scalar", path: "workflow.activation_steps_prepend" },
    { id: "bad-keyed", skill: "bmad-build-auto", kind: "keyed", path: "workflow.activation_steps_prepend" },
    { id: "bad-list-of-tables", skill: "bmad-agent-po", kind: "list", path: "agent.menu" },
    { id: "skipped", skill: "bmad-build-auto", kind: "scalar", path: "workflow.nope", test_only: true },
  ])), {
    "bmad-build-auto": parseToml(BUILD_AUTO_CUSTOMIZE),
    "bmad-agent-po": parseToml(PO_CUSTOMIZE),
  });
  const named = findings.map((f) => f.match(/^([^:]+):/)[1]).sort();
  assert.deepEqual(named, ["bad-keyed", "bad-list", "bad-list-of-tables", "bad-scalar"],
    findings.join("\n"));
});

test("checkWireIn reports a skill whose customize.toml was not supplied", () => {
  const findings = checkWireIn(parseToml(wireIn([
    { id: "orphan", skill: "bmad-unknown", kind: "scalar", path: "workflow.on_complete" },
  ])), {});
  assert.equal(findings.length, 1);
  assert.match(findings[0], /bmad-unknown/);
});

test("a planted undeclared key fails the gate end to end, naming the key", (t) => {
  const repo = tree(t, {
    ...REPO_FILES,
    [WIRE_IN_REL]: wireIn([
      { id: "planted", skill: "bmad-build-auto", kind: "scalar", path: "workflow.interactive" },
    ]),
  });
  const custom = tree(t, { "bmad-build-auto/customize.toml": BUILD_AUTO_CUSTOMIZE });
  const v = standIn(t, 0);
  const r = spawnSync(process.execPath, [SCRIPT], {
    cwd: repo, encoding: "utf8",
    env: { ...process.env, CHECK_BMOD_VALIDATOR: v.script, CHECK_BMOD_CUSTOMIZE_DIR: custom },
  });
  const { root } = v.seen();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  assert.equal(r.status, 1, r.stdout + r.stderr);
  assert.match(r.stderr, /workflow\.interactive/);
});

test("the shipped wire-in entries all name skills whose customize.toml the arm can fetch", () => {
  const shipped = parseToml(fs.readFileSync(
    path.join(import.meta.dirname, "..", "..", WIRE_IN_REL), "utf8"));
  for (const e of shipped.entry.filter((x) => !x.test_only)) {
    assert.ok(CUSTOMIZE_PATHS[e.skill], `no pinned customize.toml for ${e.skill} (${e.id})`);
  }
});
