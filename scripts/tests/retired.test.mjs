// retired.toml — the skills a module no longer ships.
//
// v7's `bmad setup` reads a module record's `retired.toml` and offers to delete every skill it
// names that is still installed. A name listed there that this repository still ships would be
// offered for deletion on every setup, straight after being installed. BMad's own
// `validate_manifests.py` (`retired_problems`) rejects that; these tests enforce the same rule
// here so it holds before that gate is wired in.
//
// Schema (setup.py `read_retired_file`/`parse_renamed`/`parse_skill_names` at the pin
// e435a22): top-level `renamed`, a list of `{ from, to }` tables, and `removed`, a list of
// skill names; both optional; a name is retired at most once across the two.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { parse as parseToml } from "smol-toml";
import { skillDirs } from "../lib/skill-dirs.mjs";

const REPO = path.resolve(import.meta.dirname, "..", "..");
// setup.py's SKILL_NAME.
const SKILL_NAME = /^[A-Za-z0-9][A-Za-z0-9_-]*$/;

function retiredFiles(root) {
  const out = [];
  const walk = (rel) => {
    let entries;
    try {
      entries = fs.readdirSync(path.join(root, rel), { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      if (e.isDirectory()) {
        if (e.name === "node_modules" || e.name === "__pycache__") continue;
        walk(`${rel}/${e.name}`);
      } else if (e.name === "retired.toml") {
        out.push(`${rel}/${e.name}`);
      }
    }
  };
  walk("skills");
  return out.sort();
}

// Mirrors read_retired_file: throws where BMad's runtime parser would.
function parseRetired(text, file) {
  const data = parseToml(text);
  const renamed = [];
  if (data.renamed !== undefined) {
    if (!Array.isArray(data.renamed)) throw new Error(`${file}: 'renamed' must be a list of tables`);
    data.renamed.forEach((entry, i) => {
      if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
        throw new Error(`${file}: renamed[${i}] must be a table`);
      }
      for (const key of ["from", "to"]) {
        if (typeof entry[key] !== "string" || !SKILL_NAME.test(entry[key])) {
          throw new Error(`${file}: renamed[${i}].${key} must be a skill name`);
        }
      }
      if (entry.from === entry.to) throw new Error(`${file}: renamed[${i}] renames to itself`);
      renamed.push({ from: entry.from, to: entry.to });
    });
  }
  const removed = data.removed ?? [];
  if (!Array.isArray(removed)) throw new Error(`${file}: 'removed' must be a list of skill names`);
  for (const name of removed) {
    if (typeof name !== "string" || !SKILL_NAME.test(name)) {
      throw new Error(`${file}: 'removed' has unsafe skill name ${JSON.stringify(name)}`);
    }
  }
  const all = [...renamed.map((r) => r.from), ...removed];
  const repeated = all.find((n, i) => all.indexOf(n) !== i);
  if (repeated) throw new Error(`${file}: retires '${repeated}' more than once`);
  return { renamed, removed };
}

// Every way the retired lists disagree with what the tree ships.
function retiredProblems(root) {
  const shipped = new Set(skillDirs(root).map((d) => path.posix.basename(d)));
  const problems = [];
  for (const file of retiredFiles(root)) {
    const { renamed, removed } = parseRetired(fs.readFileSync(path.join(root, file), "utf8"), file);
    for (const old of [...renamed.map((r) => r.from), ...removed]) {
      if (shipped.has(old)) problems.push(`${file}: retires '${old}', which still ships`);
    }
    for (const r of renamed) {
      if (!shipped.has(r.to)) problems.push(`${file}: renames '${r.from}' to '${r.to}', which is not shipped`);
    }
  }
  return problems;
}

function tree(t, files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "l3io-retired-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const [rel, body] of Object.entries(files)) {
    const abs = path.join(root, rel);
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    fs.writeFileSync(abs, body);
  }
  return root;
}

test("test_retired_names_never_shipped", () => {
  const files = retiredFiles(REPO);
  // An empty discovery would pass every assertion below over nothing.
  assert.ok(files.includes("skills/l3io-pm/bmod-l3io-pm/retired.toml"),
    `expected l3io-pm's retired.toml; found ${JSON.stringify(files)}`);
  assert.deepEqual(retiredProblems(REPO), []);
});

test("l3io-pm retires exactly the names v7 replaces", () => {
  const file = "skills/l3io-pm/bmod-l3io-pm/retired.toml";
  const parsed = parseRetired(fs.readFileSync(path.join(REPO, file), "utf8"), file);
  assert.deepEqual(parsed.renamed, [
    { from: "l3io-pm-execute", to: "l3io-execute" },
    { from: "l3io-pm-plan", to: "l3io-plan" },
  ]);
  assert.deepEqual([...parsed.removed].sort(),
    ["l3io-help", "l3io-pm-help", "l3io-pm-sync", "l3io-setup", "l3io-sync"]);
});

test("a removed name that still ships is reported", (t) => {
  const root = tree(t, {
    "skills/m/keep/SKILL.md": "",
    "skills/m/bmod-m/retired.toml": 'removed = ["keep"]\n',
  });
  assert.deepEqual(retiredProblems(root), ["skills/m/bmod-m/retired.toml: retires 'keep', which still ships"]);
});

test("a renamed old name that still ships is reported", (t) => {
  const root = tree(t, {
    "skills/m/old/SKILL.md": "",
    "skills/m/new/SKILL.md": "",
    "skills/m/bmod-m/retired.toml": 'renamed = [{ from = "old", to = "new" }]\n',
  });
  assert.deepEqual(retiredProblems(root), ["skills/m/bmod-m/retired.toml: retires 'old', which still ships"]);
});

test("a rename to a skill that is not shipped is reported", (t) => {
  const root = tree(t, {
    "skills/m/bmod-m/retired.toml": 'renamed = [{ from = "old", to = "gone" }]\n',
  });
  assert.deepEqual(retiredProblems(root),
    ["skills/m/bmod-m/retired.toml: renames 'old' to 'gone', which is not shipped"]);
});

test("a file BMad's parser would reject is rejected", (t) => {
  for (const body of [
    'removed = "x"\n',
    'renamed = ["x"]\n',
    'renamed = [{ from = "a" }]\n',
    'renamed = [{ from = "a", to = "a" }]\n',
    'removed = ["../x"]\n',
    'removed = ["a"]\nrenamed = [{ from = "a", to = "b" }]\n',
    "removed = [\n",
  ]) {
    const root = tree(t, { "skills/m/bmod-m/retired.toml": body });
    assert.throws(() => retiredProblems(root), undefined, body);
  }
});
