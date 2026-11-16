// Where the skills are. Every tool that needs skill locations derives them here, never from a
// `skills/*/` glob.
//
// The repository is laid out one folder per module (ADR-0021): `skills/<code>/<skill>/`, with
// `skills/_shared/` beside them as the canonical source tree that ships nothing. A skill is a
// directory holding a SKILL.md, at any depth; a directory without one is a group and is walked
// through. The walk stops at a skill, because everything beneath it is that skill's payload.
//
// A multi-skill module's record (`bmod-<code>/`, ADR-0014) carries a SKILL.md, because BMad's
// validator requires one, so it is found here like a skill; tools that ship shared payload
// exclude it by its `bmod-` prefix. strayFiles() also treats a folder holding `bmod.toml`, or a
// `bmod-<code>/` folder holding only `retired.toml`, as an owner.
import fs from "node:fs";
import path from "node:path";

const DEFAULT_ROOT = path.resolve(import.meta.dirname, "..", "..");
const SHARED = "_shared";
const IGNORED_DIRS = new Set(["__pycache__", "node_modules"]);

function walk(root, rel, out) {
  const abs = path.join(root, rel);
  let entries;
  try {
    entries = fs.readdirSync(abs, { withFileTypes: true });
  } catch {
    return;
  }
  if (entries.some((e) => e.isFile() && e.name === "SKILL.md")) {
    out.push(rel);
    return;
  }
  for (const e of entries) {
    if (!e.isDirectory() || IGNORED_DIRS.has(e.name)) continue;
    if (rel === "skills" && e.name === SHARED) continue;
    walk(root, `${rel}/${e.name}`, out);
  }
}

// Every skill directory, repo-relative, POSIX separators, sorted.
export function skillDirs(root = DEFAULT_ROOT) {
  const out = [];
  walk(root, "skills", out);
  return out.sort();
}

// basename -> repo-relative skill directory. An install flattens every module into one skills
// folder, so a skill's name is its basename and two skills sharing one would collide there.
export function skillDirByName(root = DEFAULT_ROOT) {
  const map = new Map();
  for (const dir of skillDirs(root)) {
    const name = path.posix.basename(dir);
    if (map.has(name)) {
      throw new Error(`two skills are named '${name}': ${map.get(name)} and ${dir} — an ` +
        `install flattens modules into one skills folder, so one would overwrite the other`);
    }
    map.set(name, dir);
  }
  return map;
}

// Every file under skills/ that no skill and no module record owns, repo-relative and sorted.
// Files directly in skills/ and everything under skills/_shared/ are owned by the repository
// rather than a module.
export function strayFiles(root = DEFAULT_ROOT) {
  const stray = [];
  const visit = (rel) => {
    let entries;
    try {
      entries = fs.readdirSync(path.join(root, rel), { withFileTypes: true });
    } catch {
      return;
    }
    if (entries.some((e) => e.isFile() && (e.name === "SKILL.md" || e.name === "bmod.toml"))) return;
    if (path.posix.basename(rel).startsWith("bmod-") &&
        entries.some((e) => e.isFile() && e.name === "retired.toml")) return;
    for (const e of entries) {
      if (e.isDirectory()) {
        if (IGNORED_DIRS.has(e.name) || (rel === "skills" && e.name === SHARED)) continue;
        visit(`${rel}/${e.name}`);
      } else if (rel !== "skills") {
        stray.push(`${rel}/${e.name}`);
      }
    }
  };
  visit("skills");
  return stray.sort();
}
