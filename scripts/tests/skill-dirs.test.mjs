// scripts/lib/skill-dirs.mjs — the one place a tool learns where the skills are.
//
// The layout is one folder per module (ADR-0021): a skill sits at any depth under skills/, and
// a folder with no SKILL.md is a group. Every tool derives skill locations from skillDirs(); a
// `skills/*/` glob would silently see none of them. strayFiles() is the other half: a file
// left at a path no skill owns is invisible to every tool that only walks skills, so it has to
// be looked for.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { skillDirs, skillDirByName, strayFiles } from "../lib/skill-dirs.mjs";

function tree(t, files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "l3io-skilldirs-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const rel of files) {
    const abs = path.join(root, rel);
    if (rel.endsWith("/")) { fs.mkdirSync(abs, { recursive: true }); continue; }
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    fs.writeFileSync(abs, "");
  }
  return root;
}

test("skillDirs finds skills at any depth, skips _shared and groups", (t) => {
  const root = tree(t, [
    "skills/a/x/SKILL.md",
    "skills/b/SKILL.md",
    "skills/_shared/s/SKILL.md",
    "skills/a/group/",
  ]);
  assert.deepEqual(skillDirs(root), ["skills/a/x", "skills/b"]);
});

test("skillDirs does not descend into a skill once found", (t) => {
  // A skill's own files are its payload; a SKILL.md inside one (a fixture, a template) is not
  // a second skill.
  const root = tree(t, ["skills/a/SKILL.md", "skills/a/assets/inner/SKILL.md"]);
  assert.deepEqual(skillDirs(root), ["skills/a"]);
});

test("skillDirs is sorted and POSIX whatever the walk order", (t) => {
  const root = tree(t, ["skills/z/q/SKILL.md", "skills/m/SKILL.md", "skills/a/b/c/SKILL.md"]);
  assert.deepEqual(skillDirs(root), ["skills/a/b/c", "skills/m", "skills/z/q"]);
});

test("skillDirs on a tree with no skills/ is empty, not a throw", (t) => {
  assert.deepEqual(skillDirs(tree(t, ["README.md"])), []);
});

test("skillDirByName maps each skill's basename to its directory", (t) => {
  const root = tree(t, ["skills/m/one/SKILL.md", "skills/two/SKILL.md"]);
  assert.deepEqual([...skillDirByName(root)], [["one", "skills/m/one"], ["two", "skills/two"]]);
});

test("skillDirByName refuses two skills with one name", (t) => {
  // An install flattens every module into one skills folder, so two same-named skills in
  // different modules would overwrite each other on a consumer's disk.
  const root = tree(t, ["skills/m/dup/SKILL.md", "skills/n/dup/SKILL.md"]);
  assert.throws(() => skillDirByName(root), /skills\/m\/dup.*skills\/n\/dup/);
});

test("strayFiles names a file left at a path no skill owns", (t) => {
  // The shape a re-layout leaves behind: a per-skill copy at the OLD flat path, whose
  // directory no longer has a SKILL.md, so nothing that walks skills ever sees it.
  const root = tree(t, [
    "skills/module.yaml",
    "skills/_shared/steps/a.md",
    "skills/pm/l3io-execute/SKILL.md",
    "skills/pm/l3io-execute/steps/a.md",
    "skills/pm/bmod-pm/bmod.toml",
    "skills/pm/bmod-pm/help/help.md",
    "skills/l3io-execute/steps/x.md",
    "skills/pm/notes.md",
  ]);
  assert.deepEqual(strayFiles(root), ["skills/l3io-execute/steps/x.md", "skills/pm/notes.md"]);
});

test("strayFiles ignores __pycache__ detritus", (t) => {
  const root = tree(t, ["skills/pm/__pycache__/x.pyc"]);
  assert.deepEqual(strayFiles(root), []);
});

// Review Focus 5 of the v7 Phase 2 plan, against the real gates: a per-skill copy surviving
// at the old flat path after the re-layout must fail check:scripts and check:manifest rather
// than pass over a scope that no longer reaches it.
test("check:scripts and check:manifest both fail on a stray at the old flat path", (t) => {
  const repo = path.resolve(import.meta.dirname, "..", "..");
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "l3io-skilldirs-gates-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const rel of ["scripts", "skills", "package.json"]) {
    fs.cpSync(path.join(repo, rel), path.join(root, rel), {
      recursive: true,
      filter: (src) => !src.split(path.sep).includes("__pycache__"),
    });
  }
  fs.symlinkSync(path.join(repo, "node_modules"), path.join(root, "node_modules"));
  const run = (script) => spawnSync(process.execPath, [path.join(root, "scripts", script), "--check"],
    { cwd: root, encoding: "utf8" });

  for (const script of ["sync-shared-scripts.mjs", "write-payload-manifest.mjs"]) {
    const r = run(script);
    assert.equal(r.status, 0, `${script} on the unmodified copy: ${r.stderr}`);
  }
  const stray = "skills/l3io-execute/steps/x.md";
  fs.mkdirSync(path.join(root, path.dirname(stray)), { recursive: true });
  fs.writeFileSync(path.join(root, stray), "stale\n");
  for (const script of ["sync-shared-scripts.mjs", "write-payload-manifest.mjs"]) {
    const r = run(script);
    assert.equal(r.status, 1, `${script} passed over ${stray}: ${r.stdout}`);
    assert.match(r.stderr, /STRAY: skills\/l3io-execute\/steps\/x\.md/);
  }
});
