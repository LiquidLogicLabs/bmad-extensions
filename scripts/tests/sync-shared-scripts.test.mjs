// scripts/sync-shared-scripts.mjs — the `[skill] scripts` list it generates.
//
// BMad v7 installs exactly the files a skill's bmod.toml declares under `[skill] scripts` into
// `_bmad/<module>/scripts/`. A module added to pm_status/ but missing from that list installs a
// package without it, and the first import of it fails on a user's machine. The list is
// therefore generated from the payload tree, and `--check` fails on any difference.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { parse as parseToml } from "smol-toml";

const repo = path.resolve(import.meta.dirname, "..", "..");
const DECLARERS = ["skills/l3io-pm/l3io-execute", "skills/l3io-util/l3io-doctor"];
// Files beside the pm_status tree that a declarer also declares: a hook value can name only a
// path under `_bmad/<module>/scripts/`, so whatever a hook runs or reads must be declared.
const EXTRAS = {
  "skills/l3io-pm/l3io-execute": ["scripts/facts/ac-dimensions.md", "scripts/facts/spec-sync.md",
    "scripts/spec-align.py"],
  // l3io-pm's migration-1.toml (`bmad migrate`) runs the 3.x -> 4.x engine from here.
  "skills/l3io-util/l3io-doctor": ["scripts/migrate-engine.py", "scripts/read-l3io-flat.py",
    "scripts/read-per-epic.py", "scripts/read-sharded.py", "scripts/read-split.py",
    "scripts/state-record.py"],
};
// A skill that ships no pm_status copy and still declares a file a hook names: it declares
// that file alone, never the package it does not carry.
// l3io-arch-review and l3io-sec-redteam declare whole directories (their lenses, standards and
// design review), so their expected list is every file under those directories on disk.
const filesUnder = (skill, ...dirs) => dirs.flatMap((d) =>
  fs.readdirSync(path.join(repo, skill, d), { recursive: true })
    .filter((f) => fs.statSync(path.join(repo, skill, d, f)).isFile())
    .map((f) => `${d}/${f.split(path.sep).join("/")}`));
const EXTRAS_ONLY = {
  "skills/l3io-pm/l3io-plan": ["scripts/plan-graph.py"],
  "skills/l3io-arch/l3io-arch-review":
    filesUnder("skills/l3io-arch/l3io-arch-review", "scripts/lenses", "scripts/reviewers", "scripts/standards"),
  "skills/l3io-sec/l3io-sec-redteam": filesUnder("skills/l3io-sec/l3io-sec-redteam", "scripts/lenses"),
};

// A runnable copy: sync `git add`s what it writes, so the copy is a work tree of its own.
function copyRepo(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "l3io-sync-scripts-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const rel of ["scripts", "skills", "package.json"]) {
    fs.cpSync(path.join(repo, rel), path.join(root, rel), {
      recursive: true,
      filter: (src) => !src.split(path.sep).includes("__pycache__"),
    });
  }
  fs.symlinkSync(path.join(repo, "node_modules"), path.join(root, "node_modules"));
  spawnSync("git", ["init", "-q"], { cwd: root });
  return root;
}

const sync = (root, ...args) => spawnSync(process.execPath,
  [path.join(root, "scripts", "sync-shared-scripts.mjs"), ...args], { cwd: root, encoding: "utf8" });

const declared = (root, skill) =>
  parseToml(fs.readFileSync(path.join(root, skill, "bmod.toml"), "utf8")).skill?.scripts;

test("each pm_status shipper declares every .py of its payload copy and its extras, sorted", () => {
  for (const skill of DECLARERS) {
    const pkg = path.join(repo, skill, "scripts", "pm_status");
    const onDisk = fs.readdirSync(pkg, { recursive: true })
      .map((p) => p.split(path.sep).join("/"))
      .filter((p) => p.endsWith(".py") && !p.includes("__pycache__"))
      .map((p) => `scripts/pm_status/${p}`);
    assert.ok(onDisk.includes("scripts/pm_status/__main__.py"), `${skill}: walk found no entry point`);
    for (const extra of EXTRAS[skill]) {
      assert.ok(fs.existsSync(path.join(repo, skill, extra)), `${skill}: ${extra} is not in the payload`);
    }
    assert.deepEqual(declared(repo, skill), [...onDisk, ...EXTRAS[skill]].sort(), `${skill}/bmod.toml`);
  }
});

test("a declared directory declares every file in it: one added there fails --check until synced", (t) => {
  const root = copyRepo(t);
  const skill = "skills/l3io-sec/l3io-sec-redteam";
  assert.ok(EXTRAS_ONLY[skill].length >= 6, "the six threat lenses are declared");
  assert.ok(!declared(root, skill).includes("scripts/write-module-config.py"),
    "a script outside a declared directory is not declared");
  const lens = "scripts/lenses/l3io-threat-new.md";
  fs.writeFileSync(path.join(root, skill, lens), "# new lens\n");
  const r = sync(root, "--check");
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, new RegExp(`UNDECLARED: ${skill}/bmod\\.toml \\[skill\\] scripts lacks ${lens}`));
  assert.equal(sync(root).status, 0);
  assert.ok(declared(root, skill).includes(lens), "sync declares it");
  assert.equal(sync(root, "--check").status, 0);
});

test("declared extras are generated: one missing from the payload or the list fails --check, naming it", (t) => {
  const root = copyRepo(t);
  const skill = DECLARERS[0];
  const fact = "scripts/facts/ac-dimensions.md";

  fs.rmSync(path.join(root, skill, fact));
  const gone = sync(root, "--check");
  assert.equal(gone.status, 1, gone.stdout);
  assert.match(gone.stderr, new RegExp(
    `UNDECLARED: ${skill}/bmod\\.toml \\[skill\\] scripts declares ${fact}, which the payload does not contain`));
  assert.equal(sync(root).status, 0, "sync restores the payload copy");

  const bmod = path.join(root, skill, "bmod.toml");
  fs.writeFileSync(bmod, fs.readFileSync(bmod, "utf8").replace(`  "${fact}",\n`, ""));
  assert.ok(!declared(root, skill).includes(fact), "the planted removal took");
  const undeclared = sync(root, "--check");
  assert.equal(undeclared.status, 1, undeclared.stdout);
  assert.match(undeclared.stderr, new RegExp(
    `UNDECLARED: ${skill}/bmod\\.toml \\[skill\\] scripts lacks ${fact}`));

  assert.equal(sync(root).status, 0);
  assert.ok(declared(root, skill).includes(fact), "sync declares it again");
  const again = sync(root, "--check");
  assert.equal(again.status, 0, again.stderr);
});

test("a skill with extras and no pm_status copy declares exactly its extras", () => {
  for (const [skill, extras] of Object.entries(EXTRAS_ONLY)) {
    assert.ok(!fs.existsSync(path.join(repo, skill, "scripts", "pm_status")), `${skill} ships pm_status`);
    for (const extra of extras) {
      assert.ok(fs.existsSync(path.join(repo, skill, extra)), `${skill}: ${extra} is not in the payload`);
    }
    assert.deepEqual(declared(repo, skill), [...extras].sort(), `${skill}/bmod.toml`);
  }
});

test("no other skill declares scripts: only a pm_status shipper or a listed extra does", () => {
  const out = spawnSync("git", ["ls-files", "skills/**/bmod.toml"], { cwd: repo, encoding: "utf8" });
  for (const rel of out.stdout.split("\n").filter(Boolean)) {
    if (DECLARERS.includes(path.dirname(rel)) || path.dirname(rel) in EXTRAS_ONLY) continue;
    assert.equal(declared(repo, path.dirname(rel)), undefined, `${rel} declares scripts`);
  }
});

test("a module added to pm_status/ and not declared fails --check, naming it and the bmod.toml", (t) => {
  const root = copyRepo(t);
  assert.equal(sync(root, "--check").status, 0, "the unmodified copy is in sync");

  // Planted in the source AND in both payload copies, so the payload itself is in sync and the
  // only thing left to report is the declaration.
  for (const dir of ["skills/_shared/pm_status", ...DECLARERS.map((s) => `${s}/scripts/pm_status`)]) {
    fs.writeFileSync(path.join(root, dir, "new_mod.py"), "X = 1\n");
  }
  const r = sync(root, "--check");
  assert.equal(r.status, 1, r.stdout);
  assert.doesNotMatch(r.stderr, /DRIFT:/, "the payload copies were planted too");
  for (const skill of DECLARERS) {
    assert.match(r.stderr, new RegExp(
      `UNDECLARED: ${skill}/bmod\\.toml \\[skill\\] scripts lacks scripts/pm_status/new_mod\\.py`));
  }

  const w = sync(root);
  assert.equal(w.status, 0, w.stderr);
  for (const skill of DECLARERS) {
    assert.ok(declared(root, skill).includes("scripts/pm_status/new_mod.py"), `${skill} after sync`);
  }
  const again = sync(root, "--check");
  assert.equal(again.status, 0, again.stderr);
});

test("a declared entry with no file behind it fails --check too", (t) => {
  const root = copyRepo(t);
  const bmod = path.join(root, DECLARERS[0], "bmod.toml");
  fs.writeFileSync(bmod, fs.readFileSync(bmod, "utf8")
    .replace('"scripts/pm_status/__main__.py",', '"scripts/pm_status/__main__.py",\n  "scripts/pm_status/gone.py",'));
  const r = sync(root, "--check");
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /UNDECLARED: skills\/l3io-pm\/l3io-execute\/bmod\.toml \[skill\] scripts declares scripts\/pm_status\/gone\.py/);
});

test("sync keeps the rest of the bmod.toml byte for byte", (t) => {
  const root = copyRepo(t);
  const bmod = path.join(root, DECLARERS[1], "bmod.toml");
  const before = fs.readFileSync(bmod, "utf8");
  fs.writeFileSync(path.join(root, "skills/_shared/pm_status/new_mod.py"), "X = 1\n");
  assert.equal(sync(root).status, 0);
  const after = fs.readFileSync(bmod, "utf8");
  const strip = (s) => s.replace(/^scripts = \[[^\]]*\]\n/m, "");
  assert.equal(strip(after), strip(before));
});
