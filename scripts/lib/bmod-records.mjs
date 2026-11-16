// BMad v7 module records (ADR-0014): the `bmod.toml` files under skills/, and the one rewrite
// this repository performs on them -- stamping the release version.
//
// Schema, from BMad's own parser at the pin e435a22 (skills/core-tools/bmad/scripts/setup.py):
// a file holds `[bmod]`, `[skill]`, or both (parse_bmod_file). `[bmod]` carries `code`,
// `version` and `update_source` (parse_bmod_table); `[skill]` in a member file carries `bmod`
// (the record folder's name) and `source` (parse_skill_table). Requirements are plain names or
// `{ skill, version, source }` tables (parse_requirements).
//
// The stamp is line-based, the same approach as upstream's `stamp_text`
// (validate_manifests.py): a TOML writer would normalise quoting, spacing and comments in a
// file people edit by hand, so only the value inside the version string changes, and the
// result is re-parsed to prove nothing else moved.
import fs from "node:fs";
import path from "node:path";
import { isDeepStrictEqual } from "node:util";
import { parse as parseToml } from "smol-toml";

export const MANIFEST_NAME = "bmod.toml";
// Every module in this repository is distributed from here (plan, Global Constraints), and a
// requirement on one of them is pinned to the release that ships it. A requirement naming any
// other source keeps the version its author wrote.
export const REPO_SOURCE_PREFIX = "github:LiquidLogicLabs/bmad-extensions/";

const DEFAULT_ROOT = path.resolve(import.meta.dirname, "..", "..");
const IGNORED_DIRS = new Set(["__pycache__", "node_modules", "_shared"]);

const TABLE_HEADER = /^[ \t]*\[\[?[^[\]\n]+\]\]?[ \t]*(?:#[^\n]*)?\r?\n?$/;
const BMOD_HEADER = /^[ \t]*\[[ \t]*bmod[ \t]*\][ \t]*(?:#[^\n]*)?\r?\n?$/;
const VERSION_LINE = /^([ \t]*version[ \t]*=[ \t]*)"[^"\n]*"([ \t]*(?:#[^\n]*)?\r?\n?)$/;
// One inline requirement table on its own line, naming a source in this repository.
const SELF_REQUIREMENT = new RegExp(
  String.raw`^[ \t]*\{[^\n]*source[ \t]*=[ \t]*"` +
  REPO_SOURCE_PREFIX.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&") + String.raw`[^\n]*\}`,
);
const INLINE_VERSION = /(\bversion[ \t]*=[ \t]*)"[^"\n]*"/;

// Every bmod.toml under skills/, repo-relative and sorted. skills/_shared/ ships nothing.
export function bmodFiles(root = DEFAULT_ROOT) {
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
        if (!IGNORED_DIRS.has(e.name)) walk(`${rel}/${e.name}`);
      } else if (e.name === MANIFEST_NAME) {
        out.push(`${rel}/${e.name}`);
      }
    }
  };
  walk("skills");
  return out.sort();
}

function lines(text) {
  return text.match(/[^\n]*\n|[^\n]+$/g) ?? [];
}

// smol-toml's tables are not plain objects, so a deep comparison would see the prototype.
function plain(data) {
  return JSON.parse(JSON.stringify(data));
}

function isSelfRequirement(entry) {
  return entry && typeof entry === "object" && typeof entry.source === "string" &&
    entry.source.startsWith(REPO_SOURCE_PREFIX) && typeof entry.version === "string";
}

// What a correct stamp produces, computed on the parsed data rather than the text.
function expected(data, version) {
  const out = plain(data);
  if (out.bmod) out.bmod.version = version;
  for (const table of [out.bmod, out.skill]) {
    if (!table) continue;
    for (const field of ["required_skills", "recommended_skills"]) {
      for (const entry of Array.isArray(table[field]) ? table[field] : []) {
        if (isSelfRequirement(entry)) entry.version = version;
      }
    }
  }
  return out;
}

// The file with the [bmod] `version` and every requirement on this repository's own modules
// set to `version`. Throws when that cannot be done by rewriting those values alone.
export function stampBmodVersion(original, version) {
  const ls = lines(original);
  const headers = ls.flatMap((l, i) => (BMOD_HEADER.test(l) ? [i] : []));
  if (headers.length > 1) {
    throw new Error(`expected at most one '[bmod]' table header line, found ${headers.length}`);
  }
  if (headers.length === 1) {
    const start = headers[0] + 1;
    let end = ls.findIndex((l, i) => i >= start && TABLE_HEADER.test(l));
    if (end === -1) end = ls.length;
    const hits = [];
    for (let i = start; i < end; i += 1) if (VERSION_LINE.test(ls[i])) hits.push(i);
    if (hits.length !== 1) {
      throw new Error(`expected exactly one 'version = "..."' line inside [bmod], found ${hits.length}`);
    }
    ls[hits[0]] = ls[hits[0]].replace(VERSION_LINE, `$1"${version}"$2`);
  }
  for (let i = 0; i < ls.length; i += 1) {
    if (SELF_REQUIREMENT.test(ls[i])) ls[i] = ls[i].replace(INLINE_VERSION, `$1"${version}"`);
  }
  const stamped = ls.join("");
  if (!isDeepStrictEqual(plain(parseToml(stamped)), expected(parseToml(original), version))) {
    throw new Error(
      "rewriting the version lines would change something else, or missed a requirement on " +
      "this repository written across several lines; keep each such requirement on one line",
    );
  }
  return stamped;
}

// Every version a record states that must equal the release: its [bmod] version and each
// requirement on this repository's own modules. [{ where, version }].
export function statedVersions(data) {
  const out = [];
  if (data.bmod && "version" in data.bmod) out.push({ where: "[bmod] version", version: data.bmod.version });
  for (const [name, table] of [["bmod", data.bmod], ["skill", data.skill]]) {
    if (!table) continue;
    for (const field of ["required_skills", "recommended_skills"]) {
      for (const entry of Array.isArray(table[field]) ? table[field] : []) {
        if (isSelfRequirement(entry)) {
          out.push({ where: `${name}.${field} '${entry.skill}'`, version: entry.version });
        }
      }
    }
  }
  return out;
}
