#!/usr/bin/env node
// Module-structure facts that BMad v7's own validator does not assert.
//
// `check:bmod` runs `validate_manifests.py` at the pin and owns the v7 packaging contract:
// bmod.toml, module records, retired.toml, roster.toml, help/help.md being present, one version.
// This checker keeps the two rules that are about THIS package rather than BMad's format:
//
//   1. pm-status-singleton  at most one pm-status payload copy per module, counting EITHER
//                           shipped layout -- the flat `scripts/pm-status.py` of 3.5.x and
//                           earlier, or the package's `scripts/pm_status/__main__.py`
//                           (`PM_STATUS_PAYLOADS`). One runtime copy per project (ADR-0001)
//                           needs one payload copy per module; naming only the flat file would
//                           describe a gate that went inert when the package landed.
//   2. help-registration    every mode keyword a skill's SKILL.md routing table marks
//                           `registered` is named, in backticks, in its module's
//                           `help/help.md` (alone, or after the skill's name), and a keyword marked `default` is served
//                           by a help.md that names the skill. help.md is what v7's `bmad`
//                           skill recommends from; a mode it does not list is invisible there.
//                           The exclusion set (`health-check`, `not-a-capability`) is read
//                           from the table's own Menu column, never kept here, and an
//                           unrecognised value fails rather than exempting.
//
// The 6.x installer rules this file used to carry -- the two-location module.yaml, module-home
// payload and placement, PluginResolver strategies, the module.yaml agent roster, `*-setup`
// singleton, module-help.csv rows and menu codes, forwarder shape -- modelled an installer v7
// does not have, and retired with it (ADR-0014). 3.x keeps them on `main`.
//
// A skill's module is the folder under skills/ it sits in (ADR-0021: `skills/<code>/<skill>/`).
// A module's help.md sits beside its record: the `bmod.toml` under skills/<code>/ that carries a
// `[bmod]` table -- `bmod-<code>/` for a multi-skill module, the one skill for a single-skill
// module. Everything is derived from the tree; nothing names a module or a skill.
//
// Parsing: the routing table is split with `csv-parse` on `|` with quoting disabled, help.md the
// same way, and bmod.toml with `smol-toml`.
//
// Usage:
//   node scripts/check-module.mjs        # report and exit nonzero on any failure (CI)
//   node scripts/check-module.mjs -v     # also print what passed
import fs from "node:fs";
import path from "node:path";
import { parse as parseCsv } from "csv-parse/sync";
import { parse as parseToml } from "smol-toml";
import { writeAllSync } from "./write-all-sync.mjs";
import { skillDirByName } from "./lib/skill-dirs.mjs";

// CHECK_MODULE_ROOT points the checker at another tree -- scripts/tests/check-module.test.mjs
// runs it against fixtures built from an empty skills/ tree.
const repoRoot = process.env.CHECK_MODULE_ROOT ? path.resolve(process.env.CHECK_MODULE_ROOT) : process.cwd();
const verbose = process.argv.includes("-v") || process.argv.includes("--verbose");
const failures = [];

const read = (p) => fs.readFileSync(path.join(repoRoot, p), "utf8");
const exists = (p) => fs.existsSync(path.join(repoRoot, p));

const SKILL_REL = skillDirByName(repoRoot);
const skillRel = (name) => SKILL_REL.get(name);
const moduleOf = (name) => skillRel(name).split("/")[1];

// The help/help.md of every module whose record is found, by module folder.
function moduleHelp() {
  const out = new Map();
  for (const [name, rel] of SKILL_REL) {
    if (!exists(`${rel}/bmod.toml`)) continue;
    let doc;
    try {
      doc = parseToml(read(`${rel}/bmod.toml`));
    } catch (e) {
      failures.push(`${rel}/bmod.toml: is not valid TOML (${String(e.message).split("\n")[0]})`);
      continue;
    }
    if (doc.bmod && typeof doc.bmod === "object") out.set(moduleOf(name), `${rel}/help/help.md`);
  }
  return out;
}

// ---------------------------------------------------------------------------
// 1. pm-status-singleton: at most one pm-status payload copy per module, where "a copy" is
// EITHER entry in `PM_STATUS_PAYLOADS` below -- the flat `scripts/pm-status.py` that shipped
// through 3.5.x, or the package's `scripts/pm_status/__main__.py`. pm-status used to ship four
// times, three of them inside l3io-pm, all identical bytes for one runtime; a sync-group edit
// could bring that back with every other gate green.
const PM_STATUS_PAYLOADS = ["scripts/pm-status.py", "scripts/pm_status/__main__.py"];
function checkPmStatusSingleton() {
  const byModule = new Map();
  for (const name of SKILL_REL.keys()) {
    const payload = PM_STATUS_PAYLOADS.find((p) => exists(`${skillRel(name)}/${p}`));
    if (!payload) continue;
    const code = moduleOf(name);
    if (!byModule.has(code)) byModule.set(code, []);
    byModule.get(code).push(`${skillRel(name)}/${payload}`);
  }
  for (const [code, files] of byModule) {
    if (files.length > 1) {
      failures.push(
        `pm-status.py appears ${files.length} times for module '${code}': ${files.join(", ")} -- ` +
        `one runtime copy per project (ADR-0001) needs only one payload copy per module.`);
    }
  }
  if (verbose) console.log(`  pm-status-singleton: ${[...byModule.values()].flat().length} payload copy/copies`);
}

// ---------------------------------------------------------------------------
// 2. help-registration: every mode keyword a skill documents is listed in its module's
// help/help.md, or excluded, by name, in the routing table itself.
//
// Why: the routing table and help.md are two copies of one fact in two files, and v7 reads only
// the second. Under 6.x this rule compared the table to module-help.csv and found the doctor
// advertising twenty-one modes and registering one.
//
// The Menu column's values, read from the table:
//   registered       -- listed in help.md: a backticked span that is the keyword (or one of
//                       its aliases) alone, or the skill name followed by it
//   default          -- the bare invocation; help.md must name the skill in backticks
//   health-check     -- deliberately unlisted: the health check proposes it, and a menu entry
//                       would invite running a migration without the diagnosis
//   not-a-capability -- help output or module setup
// A table with no Menu column claims every keyword is registered, so deleting the column makes
// the rule stricter.
//
// SCOPE survives the table being deleted: a skill OWES a table when it carries a top-level
// `steps/<name>.md` that is not a numbered `step-NN-*.md` (a mode, root CLAUDE.md "Module
// Layout"), or a "Recognized keywords" paragraph.
//
// KNOWN GAP: one-directional. A help.md row with no routing keyword behind it is not reported,
// because help.md also describes skills (l3io-plan, l3io-execute) that document modes in prose.
const KEYWORD_HEADER = "keyword";
const MENU_HEADER = "menu";
const MENU_REGISTERED = "registered";
const MENU_DEFAULT = "default";
const MENU_VALUES = new Set([MENU_REGISTERED, MENU_DEFAULT, "health-check", "not-a-capability"]);
const RECOGNIZED_KEYWORDS_RE = /\*\*Recognized keywords\*\*/i;
const TABLE_DIVIDER_CELL_RE = /^:?-+:?$/;
const NUMBERED_STEP_RE = /^step-\d/;

// One markdown table row as trimmed cells, or null when the line is not a table row.
function pipeCells(rel, line) {
  if (!line.trimStart().startsWith("|")) return null;
  let records;
  try {
    records = parseCsv(line, {
      delimiter: "|", quote: false, escape: false, relax_column_count: true, skip_empty_lines: true, trim: false,
    });
  } catch (e) {
    failures.push(`${rel}: table row is unreadable (${String(e.message).split("\n")[0]})`);
    return null;
  }
  const cells = (records[0] ?? []).map((c) => c.trim());
  if (cells.length && cells[0] === "") cells.shift();
  if (cells.length && cells[cells.length - 1] === "") cells.pop();
  return cells;
}

// Every routing table in a SKILL.md: a header row whose first column is `Keyword`, its divider
// row, and the contiguous rows under it.
function keywordTables(rel, text) {
  const lines = text.split("\n");
  const tables = [];
  for (let i = 0; i < lines.length; i++) {
    const header = pipeCells(rel, lines[i]);
    if (!header || header.length < 2 || header[0].toLowerCase() !== KEYWORD_HEADER) continue;
    const divider = pipeCells(rel, lines[i + 1] ?? "");
    if (!divider || !divider.every((c) => TABLE_DIVIDER_CELL_RE.test(c))) continue;
    const rows = [];
    let j = i + 2;
    for (; j < lines.length; j++) {
      const cells = pipeCells(rel, lines[j]);
      if (!cells) break;
      rows.push({ cells, line: j + 1 });
    }
    tables.push({ headers: header.map((h) => h.toLowerCase()), rows, line: i + 1 });
    i = j;
  }
  return tables;
}

const backticked = (cell) => [...cell.matchAll(/`([^`]+)`/g)].map((m) => m[1].trim()).filter(Boolean);

// Every backticked span in a help.md, whitespace-collapsed. A mode is listed when one of them
// is the keyword alone (a mode table's first cell) or the skill followed by the keyword (how a
// multi-skill module's help.md writes it: `l3io-plan estimate`).
function helpSpans(rel) {
  return new Set([...read(rel).matchAll(/`([^`\n]+)`/g)].map((m) => m[1].trim().replace(/\s+/g, " ")));
}

function modeFiles(name) {
  const abs = path.join(repoRoot, skillRel(name), "steps");
  if (!fs.existsSync(abs)) return [];
  return fs.readdirSync(abs, { withFileTypes: true })
    .filter((e) => e.isFile() && e.name.endsWith(".md") && !NUMBERED_STEP_RE.test(e.name))
    .map((e) => `steps/${e.name}`)
    .sort();
}

function checkHelpRegistration(helpByModule) {
  let tableCount = 0;
  let keywordCount = 0;
  let requiredCount = 0;

  for (const name of SKILL_REL.keys()) {
    const rel = `${skillRel(name)}/SKILL.md`;
    const text = read(rel);
    const tables = keywordTables(rel, text);

    if (tables.length === 0) {
      const modes = modeFiles(name);
      if (modes.length > 0 || RECOGNIZED_KEYWORDS_RE.test(text)) {
        const why = modes.length > 0
          ? `it carries ${modes.length} mode file(s) (${modes.join(", ")})`
          : `it has a "Recognized keywords" section`;
        failures.push(
          `${rel}: no keyword table, but ${why} -- a mode is a file plus a routing row, and the ` +
          `routing table is where this check reads which keywords help/help.md must list. With ` +
          `the table gone there is nothing to check and every keyword would pass unlisted.`);
      }
      continue;
    }

    const helpRel = helpByModule.get(moduleOf(name));
    let listed = null;
    let helpText = "";
    if (helpRel && exists(helpRel)) {
      listed = helpSpans(helpRel);
      helpText = read(helpRel);
    }

    for (const table of tables) {
      tableCount += 1;
      const menuIndex = table.headers.indexOf(MENU_HEADER);
      if (table.rows.length === 0) {
        failures.push(`${rel}:${table.line}: keyword table has no rows -- it documents no keyword at all.`);
        continue;
      }
      for (const { cells, line } of table.rows) {
        const aliases = backticked(cells[0] ?? "");
        if (aliases.length === 0) {
          failures.push(`${rel}:${line}: keyword table row names no backticked keyword -- first cell: '${cells[0] ?? ""}'.`);
          continue;
        }
        keywordCount += 1;
        const menu = menuIndex === -1 ? MENU_REGISTERED : (cells[menuIndex] ?? "").trim();
        const shown = aliases.map((a) => `\`${a}\``).join(" / ");
        if (!MENU_VALUES.has(menu)) {
          failures.push(
            `${rel}:${line}: keyword ${shown} has Menu value '${menu}', which is not one of ` +
            `${[...MENU_VALUES].join(", ")} -- this column decides which keywords help/help.md ` +
            `must list, so an unrecognised value is a failure rather than a silent exclusion.`);
          continue;
        }
        if (menu !== MENU_REGISTERED && menu !== MENU_DEFAULT) continue;

        requiredCount += 1;
        if (listed === null) {
          failures.push(
            `${rel}:${line}: keyword ${shown} is marked '${menu}', but module ` +
            `'${moduleOf(name)}' has no help/help.md beside its [bmod] record` +
            `${helpRel ? ` (expected ${helpRel})` : ""} -- v7 recommends a module's skills from that file.`);
          continue;
        }
        if (menu === MENU_DEFAULT) {
          if (!helpText.includes(`\`${name}\``)) {
            failures.push(
              `${rel}:${line}: keyword ${shown} is marked '${MENU_DEFAULT}', but ${helpRel} never ` +
              `names \`${name}\` -- the bare invocation is the skill itself, so help.md must name it.`);
          }
          continue;
        }
        if (aliases.some((a) => listed.has(a) || listed.has(`${name} ${a}`))) continue;
        failures.push(
          `${rel}:${line}: keyword ${shown} is marked '${MENU_REGISTERED}', but ${helpRel} names ` +
          `it nowhere, as \`<keyword>\` or \`${name} <keyword>\` -- a mode help.md does not list is invisible to v7's ` +
          `recommendations. Add the row, or mark the keyword excluded in the Menu column and say why.`);
      }
    }
  }

  if (verbose) {
    console.log(`  help-registration: ${tableCount} keyword table(s), ${keywordCount} keyword(s), ` +
      `${requiredCount} of them expecting a help/help.md entry`);
  }
}

// ---------------------------------------------------------------------------
// An empty skill set would pass both rules over nothing.
if (SKILL_REL.size === 0) failures.push(`no skill (a directory holding SKILL.md) under ${path.join(repoRoot, "skills")}`);
checkPmStatusSingleton();
checkHelpRegistration(moduleHelp());

if (verbose) console.log(`  skills: ${SKILL_REL.size}`);

// One buffered write, then `process.exitCode` -- see scripts/write-all-sync.mjs.
if (failures.length > 0) {
  writeAllSync(2,
    `\n${failures.length} module structure problem(s):\n\n` +
    failures.map((f) => `  ✗ ${f}\n\n`).join("") +
    "These are the structural facts the module layout must hold. Fix the tree, not this check.\n");
  process.exitCode = 1;
} else {
  console.log("Module structure checks passed.");
}
