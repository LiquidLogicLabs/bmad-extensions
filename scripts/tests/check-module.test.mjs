// Tests for scripts/check-module.mjs.
// Run: npm run test:scripts
// Each test runs the REAL checker (via CHECK_MODULE_ROOT) against a fixture built from an
// empty skills/ tree, laid out one folder per module (ADR-0021).
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CHECK = path.join(REPO, "scripts", "check-module.mjs");

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "l3io-check-module-"));
  fs.mkdirSync(path.join(dir, "skills"), { recursive: true });
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}

function run(root, args = []) {
  return spawnSync(process.execPath, [CHECK, ...args], {
    cwd: REPO,
    env: { ...process.env, CHECK_MODULE_ROOT: root },
    encoding: "utf8",
  });
}

function write(root, rel, text) {
  const p = path.join(root, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, text);
}

// A skill at skills/<code>/<name>/, with a SKILL.md unless the test writes its own.
function skill(root, code, name, files = {}) {
  const dir = `skills/${code}/${name}`;
  if (!files["SKILL.md"]) write(root, `${dir}/SKILL.md`, `---\nname: ${name}\n---\n`);
  for (const [rel, text] of Object.entries(files)) write(root, `${dir}/${rel}`, text);
  return dir;
}

test("check:module fails over a tree with no skills rather than passing over nothing", (t) => {
  const r = run(fixture(t));
  assert.equal(r.status, 1);
  assert.match(r.stderr, /no skill/);
});

// ---- rule 1 (pm-status-singleton) ----

test("check:module rejects a second pm-status.py payload within one module", (t) => {
  const root = fixture(t);
  skill(root, "pm", "a", { "scripts/pm-status.py": "# x\n" });
  skill(root, "pm", "b", { "scripts/pm-status.py": "# x\n" });
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /pm-status\.py appears 2 times for module 'pm'/);
});

test("check:module rejects a second pm-status payload in the package layout", (t) => {
  const root = fixture(t);
  skill(root, "pm", "a", { "scripts/pm_status/__main__.py": "# x\n" });
  skill(root, "pm", "b", { "scripts/pm_status/__main__.py": "# x\n" });
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /pm-status\.py appears 2 times for module 'pm'/);
});

test("check:module passes one pm-status payload in each of two modules", (t) => {
  const root = fixture(t);
  skill(root, "pm", "a", { "scripts/pm_status/__main__.py": "# x\n" });
  skill(root, "pm", "b");
  skill(root, "util", "doctor", { "scripts/pm_status/__main__.py": "# x\n" });
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// scripts/CLAUDE.md makes each checker's own header the authoritative description of what it
// asserts, so both of rule 1's prose sites must name every payload shape it checks. Derived from
// the declaration, so adding a third shape fails until both descriptions name it.
test("check:module's rule 1 prose names every payload shape PM_STATUS_PAYLOADS checks", () => {
  const src = fs.readFileSync(CHECK, "utf8");
  const decl = src.match(/const PM_STATUS_PAYLOADS = (\[[^\]]*\])/);
  assert.ok(decl, "PM_STATUS_PAYLOADS must stay a readable array literal");
  const paths = JSON.parse(decl[1].replace(/'/g, '"'));
  assert.ok(paths.length >= 2, `premise: more than one payload shape (${paths.join()})`);
  const slice = (from, to) => {
    const a = src.indexOf(from), b = src.indexOf(to);
    assert.ok(a > -1 && b > a, `cannot locate the prose between "${from}" and "${to}"`);
    return src.slice(a, b);
  };
  const sites = {
    "the numbered header entry": slice("//   1. pm-status-singleton", "//   2. help-registration"),
    "the section comment": slice("// 1. pm-status-singleton:", "const PM_STATUS_PAYLOADS"),
  };
  for (const [where, text] of Object.entries(sites)) {
    for (const p of paths) assert.ok(text.includes(p), `${where} must name '${p}'`);
  }
});

// ---- rule 2 (help-registration) ----
//
// Every keyword a routing table marks `registered` must be named in the module's help/help.md,
// and a `default` keyword needs help.md to name the skill. The exclusion set is read from the
// table's own Menu column, and the rule's scope is attacked as hard as the rule.

const BMOD = '[bmod]\ncode = "util"\n\n[skill]\nbmod = "util"\n';

function keywordSkill(root, rows, { menuColumn = true, table = true, help = null, bmod = BMOD } = {}) {
  const header = menuColumn
    ? "| Keyword | Load | Menu | Notes |\n|---|---|---|---|\n"
    : "| Keyword | Load | Notes |\n|---|---|---|\n";
  const body = rows.map((r) => (menuColumn
    ? `| \`${r.keyword}\` | \`${r.load}\` | ${r.menu} | note |\n`
    : `| \`${r.keyword}\` | \`${r.load}\` | note |\n`)).join("");
  const files = {
    "SKILL.md": `---\nname: doctor\n---\n\n**Recognized keywords** — match and load:\n\n` +
      (table ? header + body : "") + "\n**Everything else** → the default.\n",
  };
  if (bmod !== null) files["bmod.toml"] = bmod;
  if (help !== null) files["help/help.md"] = help;
  for (const r of rows) files[r.load] = `# ${r.keyword}\n`;
  return skill(root, "util", "doctor", files);
}

const HELP = "# util\n\nOne skill, `doctor`.\n\n| Mode | For |\n|---|---|\n| `stats` | the dashboard |\n";

test("check:module rejects a registered keyword help.md does not name", (t) => {
  const root = fixture(t);
  keywordSkill(root, [
    { keyword: "stats", load: "steps/stats.md", menu: "registered" },
    { keyword: "brand-new-mode", load: "steps/brand-new-mode.md", menu: "registered" },
  ], { help: HELP });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /brand-new-mode/);
  assert.doesNotMatch(r.stderr, /`stats`/);
});

test("check:module passes a table whose registered and default keywords are all in help.md", (t) => {
  const root = fixture(t);
  keywordSkill(root, [
    { keyword: "check", load: "steps/health-check.md", menu: "default" },
    { keyword: "stats", load: "steps/stats.md", menu: "registered" },
    { keyword: "migrate-state", load: "steps/migrate-state.md", menu: "health-check" },
    { keyword: "setup", load: "steps/setup.md", menu: "not-a-capability" },
  ], { help: HELP });
  const r = run(root, ["-v"]);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /2 of them expecting a help\/help\.md entry/);
});

test("check:module accepts a mode named after its skill, as a multi-skill module's help.md writes it", (t) => {
  const root = fixture(t);
  keywordSkill(root, [{ keyword: "reorg", load: "steps/reorg.md", menu: "registered" }],
    { help: "# util\n\n- \"rebalance\" → `doctor reorg`.\n" });
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

test("check:module rejects a default keyword when help.md never names the skill", (t) => {
  const root = fixture(t);
  keywordSkill(root, [{ keyword: "check", load: "steps/health-check.md", menu: "default" }],
    { help: "# util\n\nNothing here.\n" });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /`check`.*never names `doctor`/);
});

test("check:module rejects a registered keyword when the module has no help.md", (t) => {
  const root = fixture(t);
  keywordSkill(root, [{ keyword: "stats", load: "steps/stats.md", menu: "registered" }]);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /no help\/help\.md/);
});

test("check:module reads a multi-skill module's help.md from its bmod-<code> record", (t) => {
  const root = fixture(t);
  skill(root, "pm", "bmod-pm", { "bmod.toml": '[bmod]\ncode = "pm"\n', "help/help.md": "`plan estimate`\n" });
  skill(root, "pm", "plan", {
    "SKILL.md": "---\nname: plan\n---\n\n| Keyword | Load | Menu |\n|---|---|---|\n" +
      "| `estimate` | `steps/e.md` | registered |\n| `lanes` | `steps/l.md` | registered |\n",
    "bmod.toml": '[skill]\nbmod = "pm"\n',
  });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /`lanes`.*bmod-pm\/help\/help\.md/);
  assert.doesNotMatch(r.stderr, /`estimate`/);
});

// SCOPE ATTACK 1: an unrecognised Menu value fails rather than quietly excluding.
test("check:module rejects an unrecognised Menu value in a keyword table", (t) => {
  const root = fixture(t);
  keywordSkill(root, [{ keyword: "stats", load: "steps/stats.md", menu: "healthcheck" }], { help: HELP });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /healthcheck/);
});

// SCOPE ATTACK 2: deleting the Menu column makes the rule stricter, never weaker.
test("check:module requires help.md to name every keyword when the table has no Menu column", (t) => {
  const root = fixture(t);
  keywordSkill(root, [{ keyword: "progress", load: "steps/mode-progress.md" }], { menuColumn: false, help: HELP });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /progress/);
});

test("check:module passes a skill with no keyword table and no modes", (t) => {
  const root = fixture(t);
  skill(root, "solo", "solo", { "SKILL.md": "---\nname: solo\n---\n\nOne mode, no table.\n" });
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// SCOPE ATTACK 3, the vacuity test: removing the table must fail, anchored on the mode files.
test("check:module rejects a skill whose mode files exist but whose keyword table was removed", (t) => {
  const root = fixture(t);
  keywordSkill(root, [
    { keyword: "stats", load: "steps/stats.md", menu: "registered" },
    { keyword: "triage", load: "steps/triage.md", menu: "health-check" },
  ], { table: false, help: HELP });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /no keyword table/);
  assert.match(r.stderr, /steps\/stats\.md/);
});

test("check:module rejects a Recognized-keywords section with no table under it", (t) => {
  const root = fixture(t);
  skill(root, "solo", "solo", { "SKILL.md": "# solo\n\n**Recognized keywords** — match and load:\n\nnone yet.\n" });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /no keyword table/);
});

// ---- the real tree ----

test("the real repository passes check:module, and the help rule judges real keywords", (t) => {
  const r = spawnSync(process.execPath, [CHECK, "-v"], { cwd: REPO, encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
  const m = r.stdout.match(/(\d+) of them expecting a help\/help\.md entry/);
  assert.ok(m && Number(m[1]) > 0, `the rule must judge something on the real tree: ${r.stdout}`);
});
