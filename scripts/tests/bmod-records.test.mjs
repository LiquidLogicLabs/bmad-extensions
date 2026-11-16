// BMad v7 module records (ADR-0014) -- every skill is registered, and one version is stamped
// across every record.
//
// Schema at the pin e435a22 (skills/core-tools/bmad/scripts/setup.py): `[skill] bmod` names the
// record folder and `source` must equal that record's `update_source`
// (validate_manifests.py membership_problems); a single-skill module holds `[bmod]` and `[skill]`
// in one file; a record lists its members in `skills` unless it is the skill itself.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { parse as parseToml } from "smol-toml";
import { skillDirs } from "../lib/skill-dirs.mjs";
import { bmodFiles, stampBmodVersion, statedVersions } from "../lib/bmod-records.mjs";

const REPO = path.resolve(import.meta.dirname, "..", "..");
const PKG_VERSION = JSON.parse(fs.readFileSync(path.join(REPO, "package.json"), "utf8")).version;
const readToml = (rel) => parseToml(fs.readFileSync(path.join(REPO, rel), "utf8"));

test("every skill has a bmod.toml whose [skill] names its module's record", () => {
  const dirs = skillDirs(REPO);
  assert.ok(dirs.length > 0, "premise: skillDirs() finds skills");
  for (const dir of dirs) {
    const rel = `${dir}/bmod.toml`;
    assert.ok(fs.existsSync(path.join(REPO, rel)), `${dir} has no bmod.toml`);
    const data = readToml(rel);
    const name = path.posix.basename(dir);
    const code = dir.split("/")[1];
    if (data.bmod) {
      assert.equal(data.bmod.code, code, `${rel}: [bmod] code must be its module folder`);
      assert.equal(data.bmod.update_source,
        `github:LiquidLogicLabs/bmad-extensions/skills/${code}`, `${rel}: update_source`);
      if (name === `bmod-${code}`) {
        assert.equal(data.skill, undefined, `${rel}: a record folder is not a skill`);
      } else {
        assert.ok(data.skill, `${rel}: a single-skill module's file also holds [skill]`);
        assert.equal(fs.existsSync(path.join(REPO, `skills/${code}/bmod-${code}`)), false,
          `${rel}: module ${code} has a bmod-${code} record and a second one here`);
      }
      continue;
    }
    assert.ok(data.skill, `${rel}: holds neither [bmod] nor [skill]`);
    assert.equal(data.skill.bmod, `bmod-${code}`, `${rel}: [skill] bmod must name bmod-${code}`);
    const recordRel = `skills/${code}/bmod-${code}/bmod.toml`;
    const record = readToml(recordRel);
    assert.equal(data.skill.source, record.bmod.update_source,
      `${rel}: [skill] source must equal ${recordRel}'s update_source`);
    assert.ok(record.bmod.skills.includes(name), `${recordRel} does not list '${name}'`);
  }
});

test("every [bmod] version, and every requirement on this repo, equals package.json's", () => {
  const files = bmodFiles(REPO);
  let records = 0;
  for (const rel of files) {
    const data = readToml(rel);
    if (data.bmod) records += 1;
    for (const { where, version } of statedVersions(data)) {
      assert.equal(version, PKG_VERSION, `${rel}: ${where} is ${version}, package.json says ` +
        `${PKG_VERSION}; run node scripts/sync-bmad-versions.mjs`);
    }
  }
  assert.equal(records, 4, `expected one record per module, found ${records}`);
});

test("every record requires bmad 6.13.0 from core-tools", () => {
  for (const rel of bmodFiles(REPO)) {
    const data = readToml(rel);
    if (!data.bmod) continue;
    assert.deepEqual({ ...data.bmod.required_skills.find((r) => r.skill === "bmad") },
      { skill: "bmad", version: "6.13.0", source: "github:bmad-code-org/BMAD-METHOD/skills/core-tools" },
      `${rel}: required_skills must carry bmad`);
  }
});

// ---- stampBmodVersion ----

const RECORD = `# a comment that must survive
[bmod]
code = "acme"   # trailing comment
version = "1.0.0"
update_source = "github:LiquidLogicLabs/bmad-extensions/skills/acme"
required_skills = [
  { skill = "bmad", version = "6.13.0", source = "github:bmad-code-org/BMAD-METHOD/skills/core-tools" },
  { skill = "l3io-doctor", version = "1.0.0", source = "github:LiquidLogicLabs/bmad-extensions/skills/l3io-util" },
]

[[bmod.config_questions]]
key = "x"
prompt = "X?"
default = "{project-root}/x"

[skill]
`;

test("stamp rewrites the [bmod] version and self requirements, and nothing else", () => {
  const out = stampBmodVersion(RECORD, "2.3.4");
  const expected = RECORD
    .replace('version = "1.0.0"\n', 'version = "2.3.4"\n')
    .replace('{ skill = "l3io-doctor", version = "1.0.0"', '{ skill = "l3io-doctor", version = "2.3.4"');
  assert.equal(out, expected);
  assert.match(out, /version = "6\.13\.0"/, "a requirement on another repository keeps its version");
});

test("stamp is idempotent", () => {
  const once = stampBmodVersion(RECORD, "2.3.4");
  assert.equal(stampBmodVersion(once, "2.3.4"), once);
});

test("stamp leaves a member file with no self requirement byte-identical", () => {
  const member = '[skill]\nbmod = "bmod-acme"\nsource = "github:LiquidLogicLabs/bmad-extensions/skills/acme"\n';
  assert.equal(stampBmodVersion(member, "9.9.9"), member);
});

test("stamp does not touch a version in a table after [bmod]", () => {
  const text = '[bmod]\ncode = "a"\nversion = "1.0.0"\nupdate_source = "file:x"\n\n[other]\nversion = "5.5.5"\n';
  assert.equal(stampBmodVersion(text, "2.0.0"),
    '[bmod]\ncode = "a"\nversion = "2.0.0"\nupdate_source = "file:x"\n\n[other]\nversion = "5.5.5"\n');
});

test("stamp refuses a [bmod] with no version line", () => {
  assert.throws(() => stampBmodVersion('[bmod]\ncode = "a"\n', "2.0.0"), /exactly one 'version/);
});

test("stamp refuses a self requirement it cannot rewrite on one line", () => {
  const text = '[bmod]\ncode = "a"\nversion = "1.0.0"\nupdate_source = "file:x"\nrequired_skills = [\n' +
    '  { skill = "l3io-doctor",\n    version = "1.0.0", source = "github:LiquidLogicLabs/bmad-extensions/skills/l3io-util" },\n]\n';
  assert.throws(() => stampBmodVersion(text, "2.0.0"), /change something else|several lines|parse|Invalid/i);
});

// ---- sync-bmad-versions.mjs end to end ----

test("sync-bmad-versions.mjs stamps every bmod.toml from package.json", (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "bmod-stamp-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const put = (rel, text) => {
    fs.mkdirSync(path.dirname(path.join(dir, rel)), { recursive: true });
    fs.writeFileSync(path.join(dir, rel), text);
  };
  put("package.json", JSON.stringify({ version: "4.5.6" }));
  put(".claude-plugin/marketplace.json", JSON.stringify({ plugins: [{ name: "acme", version: "1.0.0" }] }));
  put("skills/_shared/pm_status/__main__.py", "# pm-status-version: 1.0.0\n");
  put("skills/_shared/pm_status/core/__init__.py", 'PM_STATUS_VERSION = "1.0.0"\n');
  put("skills/acme/bmod-acme/bmod.toml", RECORD);
  put("skills/acme/bmod-acme/SKILL.md", "x\n");
  const member = '[skill]\nbmod = "bmod-acme"\nsource = "github:LiquidLogicLabs/bmad-extensions/skills/acme"\n';
  put("skills/acme/acme-run/bmod.toml", member);
  put("skills/acme/acme-run/SKILL.md", "x\n");
  const r = spawnSync(process.execPath, [path.join(REPO, "scripts", "sync-bmad-versions.mjs")],
    { cwd: dir, encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
  const stamped = fs.readFileSync(path.join(dir, "skills/acme/bmod-acme/bmod.toml"), "utf8");
  assert.equal(stamped, stampBmodVersion(RECORD, "4.5.6"));
  assert.equal(fs.readFileSync(path.join(dir, "skills/acme/acme-run/bmod.toml"), "utf8"), member);
});
