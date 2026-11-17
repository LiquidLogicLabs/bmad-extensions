#!/usr/bin/env node
// Sync canonical shared files from skills/_shared/ into each PM skill's directory.
//
// Why: BMad installs skills independently, so each skill must ship its own copy of any
// shared file. The authored source of truth is skills/_shared/; the per-skill copies are
// GENERATED — never hand-edit them.
//
// Shared files:
//   pm_status/ → scripts/ in exactly ONE skill per module: `l3io-execute` for the l3io-pm
//   module and `l3io-doctor` for the (standalone) l3io-util module. Each of those two skills
//   DECLARES the package in its bmod.toml (`[skill] scripts`, written by this script -- see
//   declaredScripts() below), and BMad v7's setup installs the declared files at
//   {project-root}/_bmad/<module-code>/scripts/pm_status/, which every skill of that module
//   calls. check:module (`checkPmStatusSingleton`) guards against a second copy reappearing
//   inside one module.
//   spec-align.py → scripts/ in l3io-execute and l3io-doctor (its health checks, triage's
//   spec pass, migrate-adrs); shared because it has two consumers (ADR-0001). l3io-execute also DECLARES it (DECLARED_EXTRAS), so v7
//   installs it at _bmad/l3io-pm/scripts/spec-align.py for the readiness check wired into
//   Sofia's validate; l3io-doctor runs its own skill copy and does not declare it
//   ac-dimensions.md → a declared fact at scripts/facts/ in l3io-execute, which Sofia's
//   persistent_facts names
//   steps/shared/step-00-activate.md → steps/ in l3io-plan and l3io-execute;
//   steps/execute/* → steps/ in l3io-execute
//   status-files.md / metrics-contract.md / calibration-model.md → references/ in PM skills
//   auto-remediation.md → references/ in l3io-execute, l3io-plan
//   config-resolution.md → references/ in EVERY l3io skill -- every skill resolves config
//   write-module-config.py / module-setup.md → scripts/ and assets/ in each standalone
//   module's HOME only (the skill itself) -- the 6.x setup procedure, still loaded by the
//   `setup`/`configure` keyword until Phase 3 replaces it with v7's bmod.toml config
//   questions. l3io-pm has no 6.x setup home.
//
// Not shared, deliberately: resolve_config.py, resolve_customization.py and memlog.py are
// installed by BMad core at {project-root}/_bmad/scripts/ and are never bundled by a skill.
// Vendoring them shipped a stale duplicate of a core script that nothing invoked.
//
// Also not shared, deliberately: test-pm-status.py and test-write-module-config.py. A consumer never runs a skill's
// shipped tests, CI runs every suite straight from skills/_shared/tests/
// (.github/workflows/checks.yml), and shipping them into every consumer's install was
// ~842 KB of dead payload — the same category this package removed when it stopped
// vendoring BMad core scripts. Do not add a test file back to any of the manifests below;
// if a script gets a test, the test's only home is skills/_shared/tests/.
//
// Usage:
//   node scripts/sync-shared-scripts.mjs           # write the per-skill payload copies
//   node scripts/sync-shared-scripts.mjs --check    # verify copies match source; nonzero exit on drift (CI)
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { parse as parseToml } from "smol-toml";
import { writeAllSync } from "./write-all-sync.mjs";
import { skillDirs, skillDirByName, strayFiles } from "./lib/skill-dirs.mjs";

const repoRoot = process.cwd();
const check = process.argv.includes("--check");
const sharedDir = path.join(repoRoot, "skills", "_shared");

// A skill named here is located through skillDirs(), so a sync group names skills, never paths
// -- the module folder a skill sits in (ADR-0021) is the layout's business, not this file's.
const skillsByName = skillDirByName(repoRoot);
function skillDir(name) {
  const rel = skillsByName.get(name);
  if (!rel) throw new Error(`sync group names '${name}', but no skill of that name exists under skills/`);
  return path.join(repoRoot, rel);
}

// pm-status is a PACKAGE (skills/_shared/pm_status/), not one file. Its delivery list is
// DERIVED by walking the source tree, never written out: a hand-kept list would silently stop
// delivering the next module added, and check:scripts only compares files it lists, so the
// shipped payload would be incomplete with nothing failing. One {src, rel} entry per .py file,
// relative paths preserved, so --dump-deliveries, PAYLOAD_TARGETS and the drift loop all keep
// working per file.
const PM_STATUS_PKG = "pm_status";
function walkPy(dir, relDir = "") {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.name !== "__pycache__")
    .sort((x, y) => (x.name < y.name ? -1 : 1))
    .flatMap((e) =>
      e.isDirectory()
        ? walkPy(path.join(dir, e.name), path.join(relDir, e.name))
        : e.name.endsWith(".py") ? [path.join(relDir, e.name)] : []);
}
function pmStatusTreeFiles() {
  return walkPy(path.join(sharedDir, PM_STATUS_PKG)).map((relPy) => ({
    src: path.join(sharedDir, PM_STATUS_PKG, relPy),
    rel: path.join("scripts", PM_STATUS_PKG, relPy),
  }));
}

// source -> relative destination under each skill dir (pmScriptDirs) or all PM skill dirs (allPmDirs)
const pmScriptFiles = pmStatusTreeFiles();

// pm-status.py only (no test suite) for a skill that invokes {pm_status} and declares it
// but is not one of the PM execution skills above. A test suite in a consumer skill's payload
// is dead weight — the same kind this package removed when it stopped vendoring BMad core
// scripts — so this group deliberately carries only the runtime script.
const pmStatusOnlyFiles = pmStatusTreeFiles();

// spec-align.py: two consumers (pm-execute, util-doctor), so shared per ADR-0001. Each runs
// its own copy via `uv run {skill-root}/scripts/spec-align.py`; its test suite stays in
// skills/_shared/tests/ like every other suite.
const specAlignFiles = [
  { src: path.join(sharedDir, "spec-align.py"), rel: path.join("scripts", "spec-align.py") },
];

// The canonical story AC dimension reference, as a declared fact: a Sofia `persistent_facts`
// entry can only name a file
// under `{project-root}/_bmad/l3io-pm/scripts/`, so REFINE writes to the dimensions the
// readiness check enforces.
const acDimensionFactFiles = [
  { src: path.join(sharedDir, "ac-dimensions.md"), rel: path.join("scripts", "facts", "ac-dimensions.md") },
];

// The auto-remediation contract: delivered to the skills carrying
// steps/shared/step-00-activate.md, whose halts it governs.
const autoRemediationFiles = [
  { src: path.join(sharedDir, "auto-remediation.md"), rel: "references/auto-remediation.md" },
];

// The agent instruction block body, shipped to each module home so install/upgrade can write
// it into the consuming project's own instruction file.
const agentInstructionFiles = [
  { src: path.join(sharedDir, "agent-instructions.md"), rel: "assets/agent-instructions.md" },
];

// Files every l3io skill ships, regardless of module: the config contract every skill
// resolves. Setup itself -- module-setup.md and the script that writes its config -- is a
// module-home concern; see moduleHomeFiles below.
const allSkillFiles = [
  { src: path.join(sharedDir, "config-resolution.md"), rel: path.join("references", "config-resolution.md") },
];

// module-setup.md and the config writer setup runs belong in each standalone module's HOME --
// the skill itself. Syncing them into every operational skill would ship
// four copies of a procedure only one of them runs.
const moduleHomeDirs = [
  "l3io-doctor", "l3io-sec-redteam", "l3io-arch-review",
].map(skillDir);

const moduleHomeFiles = [
  { src: path.join(sharedDir, "write-module-config.py"), rel: path.join("scripts", "write-module-config.py") },
  { src: path.join(sharedDir, "module-setup.md"), rel: path.join("assets", "module-setup.md") },
];

// status-files.md ALONE, for a skill that needs the state-layout contract but not the metrics
// or calibration ones. l3io-doctor is that skill: migrate-state, health-check and stats all
// decide what a correct state tree looks like, and
// six of its runtime directives -- SKILL.md:186 among them, calling it "the canonical
// contract" -- told the reader to open `references/status-files.md` in a skill that did not
// ship it. Shipping it is the fix rather than repointing, because a doctor install does not
// imply a PM install: l3io-util is its own module, and a pointer at another module's file is
// a pointer at nothing for anyone who installed only this one. Making it a sync target is
// also what makes the fix stick -- `check:scripts` now fails if the copy goes missing or
// stale, which no amount of prose would have done (repo CLAUDE.md §3).
const stateContractOnly = [
  { src: path.join(sharedDir, "status-files.md"), rel: path.join("references", "status-files.md") },
];

const pmRefFiles = [
  { src: path.join(sharedDir, "status-files.md"), rel: path.join("references", "status-files.md") },
  { src: path.join(sharedDir, "metrics-contract.md"), rel: path.join("references", "metrics-contract.md") },
  // The calibration model, split out of metrics-contract.md: pm-status.py performs all of it
  // and a normal run never reads it, so it must not sit in the contract a capture agent loads.
  { src: path.join(sharedDir, "calibration-model.md"), rel: path.join("references", "calibration-model.md") },
];

// The rule for who SHIPS a pm_status payload copy: exactly one skill per module, which is
// co-installed with every other skill in that module. A skill that merely INVOKES {pm_status}
// does not need its own copy; it calls the copy v7 installs for its module from the one that
// does (l3io-plan calls the one l3io-execute declares). l3io-doctor is its own, standalone module, so it ships one too -- see
// newUtilDoctorDirs below.
// Legacy slots kept for backward compat shape; new skills use newPmPlanDirs / newPmExecuteDirs groups below.
const pmScriptDirs = [];

// All PM skills that reference status-files.md
// Legacy slots kept for backward compat shape; new skills use newPmPlanDirs / newPmExecuteDirs groups below.
const allPmDirs = [];

// New skill directories (created in Tasks 5-9)
const newPmPlanDirs = [
  skillDir("l3io-plan"),
];
const newPmExecuteDirs = [
  skillDir("l3io-execute"),
];

// The ONE l3io-pm skill that carries and declares the pm_status package for its module.
const pmStatusShipperDirs = newPmExecuteDirs;

// Skills that invoke {pm_status} but are not part of the l3io-pm module: they need
// pm-status.py to declare for their own module, but not its test suite. Currently:
// l3io-doctor, the documented post-upgrade entry point (see docs/upgrading.md), a different,
// standalone module that cannot rely on l3io-pm being installed.
const newUtilDoctorDirs = [
  skillDir("l3io-doctor"),
];

// Every skill in the package — the four l3io modules' skills all resolve config, so all of
// them carry config-resolution.md (allSkillFiles above); the setup procedure itself is a
// module-home concern (moduleHomeFiles). Derived through skillDirs(), never hand-enumerated:
// a hand-kept list here drifts silently, and a skill missing from it is missing from the
// check:scripts comparison too.
// A v7 module record (`bmod-<code>/`, ADR-0014) carries a SKILL.md only because BMad's
// validator requires one; it redirects to `bmad setup` and resolves no config, so it is not a
// skill any shared payload is for.
const allSkillDirs = skillDirs(repoRoot)
  .map((rel) => path.join(repoRoot, rel))
  .filter((dir) => !path.basename(dir).startsWith("bmod-"));

// Shared step files: source path → relative dest path within each skill's steps/ dir
const sharedStepFiles = [
  {
    src: path.join(sharedDir, "steps", "shared", "step-00-activate.md"),
    rel: path.join("steps", "shared", "step-00-activate.md"),
  },
];

const executeStepFiles = ["step-02-resolve.md", "step-03-sync.md", "step-04-dispatch.md",
  "step-05-close.md"].map((name) => ({
  src: path.join(sharedDir, "steps", "execute", name),
  rel: path.join("steps", "execute", name),
}));

// Combined sync manifest: [{files, dirs, skipMissing}]
const syncGroups = [
  // Config contract + setup procedure + its writer script into every skill
  { files: allSkillFiles, dirs: allSkillDirs },
  // Legacy: pm-status.py into old execution skills (kept for backward compat shape; skill dirs created in Tasks 5-9)
  { files: pmScriptFiles, dirs: pmScriptDirs },
  { files: pmRefFiles, dirs: allPmDirs },
  // New: shared steps into new skills (dirs only created in Tasks 5-9; skip missing dirs)
  { files: sharedStepFiles, dirs: [...newPmPlanDirs, ...newPmExecuteDirs], skipMissing: true },
  { files: executeStepFiles, dirs: newPmExecuteDirs, skipMissing: true },
  // the pm_status package into ONE l3io-pm skill, which declares it; v7 installs it at
  // _bmad/l3io-pm/scripts/pm_status/, where l3io-plan calls it too.
  { files: pmScriptFiles, dirs: pmStatusShipperDirs, skipMissing: true },
  // status-files.md into new PM skills (plan + execute)
  { files: pmRefFiles, dirs: [...newPmPlanDirs, ...newPmExecuteDirs], skipMissing: true },
  // pm-status.py (no tests) into l3io-doctor — it invokes {pm_status} from the copy it
  // declares for l3io-util but is not a PM execution skill; see pmStatusOnlyFiles above.
  { files: pmStatusOnlyFiles, dirs: newUtilDoctorDirs },
  // status-files.md (state layout only, no metrics/calibration) into l3io-doctor --
  // see stateContractOnly above for why it ships rather than being repointed.
  { files: stateContractOnly, dirs: newUtilDoctorDirs },
  // spec-align.py into its two consumers
  { files: specAlignFiles, dirs: [...newPmExecuteDirs, ...newUtilDoctorDirs] },
  // the canonical AC dimension reference, as l3io-pm's declared fact file for Sofia's
  // persistent_facts
  { files: acDimensionFactFiles, dirs: pmStatusShipperDirs },
  // the auto-remediation contract into the skills whose halts it classifies
  { files: autoRemediationFiles, dirs: [...newPmPlanDirs, ...newPmExecuteDirs], skipMissing: true },
  // the agent instruction block body, into each module's home only
  { files: agentInstructionFiles, dirs: moduleHomeDirs },
  // The two BMad-validator-required merge scripts, into each module's home only.
  { files: moduleHomeFiles, dirs: moduleHomeDirs },
];

// Every repo-relative path this script writes, derived from syncGroups itself so
// it cannot disagree with what the loop below actually does. scripts/write-payload-
// manifest.mjs imports this: a second hand-kept list would drift from the first,
// and this file's whole purpose is detecting drift.
export const PAYLOAD_TARGETS = syncGroups.flatMap(({ files, dirs, skipMissing }) =>
  files.flatMap(({ src, rel }) =>
    !fs.existsSync(src) && skipMissing
      ? []
      : dirs.flatMap((skillDir) =>
          skipMissing && !fs.existsSync(skillDir)
            ? []
            : [path.relative(repoRoot, path.join(skillDir, rel))],
        ),
  ),
);

// Orphan detection: the drift check above compares synced copies against their sources, but
// it walks syncGroups' own dirs -- it can never notice a copy sitting in a skill NO group
// targets for that rel path. That is exactly the shape Task 11 exposed: narrowing
// moduleHomeFiles to four module homes left module-setup.md and write-module-config.py
// physically present in four other skills until something ran `git rm` on them by hand --
// skip that step and every one of check:scripts/check:docs/check:manifest/check:version/
// check:module stays green while eight dead files still ship.
//
// For every rel path any group delivers, the allowed set is the UNION of that group's `dirs`
// across every group naming the same rel -- never a hand-kept list, so a group that legitimately
// widens or narrows its own targets is picked up automatically. Any other real skill directory
// under skills/ that happens to contain a file at that rel path is an orphan: bytes this script
// does not own, but that still ship.
function findOrphans() {
  const allowedByRel = new Map(); // rel -> Set<absolute skill dir>
  for (const { files, dirs } of syncGroups) {
    for (const { rel } of files) {
      if (!allowedByRel.has(rel)) allowedByRel.set(rel, new Set());
      for (const dir of dirs) allowedByRel.get(rel).add(dir);
    }
  }

  // Every real skill directory -- not just the ones a group already names, since an orphan
  // is by definition a directory no group named for that rel path.
  const everySkillDir = skillDirs(repoRoot).map((rel) => path.join(repoRoot, rel));

  const orphans = [];
  for (const [rel, allowedDirs] of allowedByRel) {
    for (const skillDir of everySkillDir) {
      if (allowedDirs.has(skillDir)) continue;
      const candidate = path.join(skillDir, rel);
      if (fs.existsSync(candidate)) orphans.push(path.relative(repoRoot, candidate));
    }
  }
  return orphans.sort();
}

// Tree comparison, the half the per-file loop cannot see: a module deleted or renamed in
// skills/_shared/pm_status/ leaves its old copy in every destination, where it still ships.
// For every skill dir that receives the package, any .py under scripts/pm_status/ with no
// source counterpart is reported (as an orphan, so it fails --check and sync warns).
function findStalePackageFiles() {
  const source = new Set(walkPy(path.join(sharedDir, PM_STATUS_PKG)));
  const stale = [];
  const seen = new Set();
  for (const { files, dirs, skipMissing } of syncGroups) {
    if (!files.some(({ rel }) => rel.startsWith(path.join("scripts", PM_STATUS_PKG) + path.sep))) continue;
    for (const skillDir of dirs) {
      if (seen.has(skillDir) || (skipMissing && !fs.existsSync(skillDir))) continue;
      seen.add(skillDir);
      for (const relPy of walkPy(path.join(skillDir, "scripts", PM_STATUS_PKG))) {
        if (!source.has(relPy)) stale.push(path.relative(repoRoot, path.join(skillDir, "scripts", PM_STATUS_PKG, relPy)));
      }
    }
  }
  return stale.sort();
}

// The `[skill] scripts` list in each pm_status shipper's bmod.toml. BMad v7's setup installs
// exactly the declared files into `_bmad/<module-code>/scripts/` (the leading `scripts/` dropped,
// nested paths kept) and rebuilds that tree on every setup, so a module present in the payload
// but absent from the list is simply not installed, and the first import of it fails on the
// user's machine. The list is therefore GENERATED from the same source walk that delivers the
// payload: every .py of the package, POSIX paths relative to the skill root, sorted.
//
// The declarers are derived from syncGroups -- every skill a pm_status file is delivered to --
// so a module that gains a shipper declares there without an edit here.
function pmStatusShippers() {
  const pkgPrefix = path.join("scripts", PM_STATUS_PKG) + path.sep;
  const dirs = new Set();
  for (const { files, dirs: targets, skipMissing } of syncGroups) {
    if (!files.some(({ rel }) => rel.startsWith(pkgPrefix))) continue;
    for (const dir of targets) if (!(skipMissing && !fs.existsSync(dir))) dirs.add(dir);
  }
  return dirs;
}

// Every skill whose bmod.toml carries a generated list: each pm_status shipper, plus each skill
// with DECLARED_EXTRAS, which declares those alone when it ships no pm_status copy.
function pmStatusDeclarers() {
  const dirs = pmStatusShippers();
  for (const name of Object.keys(DECLARED_EXTRAS)) dirs.add(skillDir(name));
  return [...dirs].sort();
}

// Files a declarer declares beside its pm_status tree, keyed by skill name. A hook value can
// name only a path under `{project-root}/_bmad/<module>/scripts/` (in a hook, `{skill-root}` is
// the HOST's), so whatever a wire-in entry runs or reads is declared here. Each must also be
// delivered to that skill by a sync group or be the skill's own file; --check fails on one the
// payload does not contain. l3io-plan's plan-graph.py is its own (Sofia's board hook runs it),
// and l3io-plan ships no pm_status copy, so it declares that one file and nothing else.
// An entry ending in `/` declares every file under that directory of the skill, so a lens or a
// standard added there is installed without an edit here: l3io-arch-review's lenses, standards
// and design review, and l3io-sec-redteam's threat lenses, which bmad-review, the thorough code
// review and bmad-architecture load from `_bmad/<module>/scripts/` once wired.
const DECLARED_EXTRAS = {
  "l3io-execute": ["scripts/facts/ac-dimensions.md", "scripts/facts/spec-sync.md", "scripts/spec-align.py"],
  "l3io-plan": ["scripts/plan-graph.py"],
  // The 3.x -> 4.x migration engine and its readers: l3io-pm's migration-1.toml, run by
  // `bmad migrate`, invokes it at _bmad/l3io-util/scripts/, beside this module's pm_status.
  "l3io-doctor": ["scripts/migrate-engine.py", "scripts/read-l3io-flat.py", "scripts/read-per-epic.py",
                  "scripts/read-sharded.py", "scripts/read-split.py", "scripts/state-record.py"],
  "l3io-arch-review": ["scripts/lenses/", "scripts/reviewers/", "scripts/standards/"],
  "l3io-sec-redteam": ["scripts/lenses/"],
};

function walkFiles(dir, rel) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.name !== "__pycache__")
    .flatMap((e) => e.isDirectory()
      ? walkFiles(path.join(dir, e.name), `${rel}${e.name}/`)
      : [`${rel}${e.name}`]);
}

function declaredExtras(dir) {
  return (DECLARED_EXTRAS[path.basename(dir)] ?? []).flatMap((entry) => entry.endsWith("/")
    ? walkFiles(path.join(dir, ...entry.split("/")), entry)
    : [entry]);
}

function declaredScripts(dir) {
  const pkg = pmStatusShippers().has(dir)
    ? walkPy(path.join(sharedDir, PM_STATUS_PKG))
      .map((relPy) => ["scripts", PM_STATUS_PKG, ...relPy.split(path.sep)].join("/"))
    : [];
  return [...pkg, ...declaredExtras(dir)].sort();
}

// The generated form, one entry per line so a new module is a one-line diff. Written as the last
// key of the `[skill]` table; every other byte of the file is left as it was.
const SCRIPTS_LINE_RE = /^scripts = \[[^\]]*\]\n/m;
function withDeclaredScripts(text, list) {
  const block = `scripts = [\n${list.map((s) => `  ${JSON.stringify(s)},`).join("\n")}\n]\n`;
  const header = /^\[skill\][ \t]*\n/m.exec(text);
  if (!header) return `${text.replace(/\n*$/, "\n")}\n[skill]\n${block}`;
  const start = header.index + header[0].length;
  const next = /^\[/m.exec(text.slice(start));
  const end = next ? start + next.index : text.length;
  const table = text.slice(start, end).replace(SCRIPTS_LINE_RE, "");
  const keys = table.replace(/\s*$/, "");
  const gap = table.slice(keys.length + 1);   // blank lines kept before a following table
  return text.slice(0, start) + (keys ? `${keys}\n` : "") + block + gap + text.slice(end);
}

// One finding per difference, each naming the bmod.toml and the script.
function declarationFindings(dir, list) {
  const file = path.join(dir, "bmod.toml");
  const rel = path.relative(repoRoot, file).split(path.sep).join("/");
  const text = fs.readFileSync(file, "utf8");
  let got;
  try {
    got = parseToml(text).skill?.scripts;
  } catch (e) {
    return [`UNDECLARED: ${rel} does not parse as TOML: ${e.message}`];
  }
  if (!Array.isArray(got)) return [`UNDECLARED: ${rel} has no [skill] scripts list`];
  const findings = [
    ...list.filter((s) => !got.includes(s)).map((s) => `UNDECLARED: ${rel} [skill] scripts lacks ${s}`),
    ...got.filter((s) => !list.includes(s))
      .map((s) => `UNDECLARED: ${rel} [skill] scripts declares ${s}, which is neither in pm_status/ ` +
        `nor a declared extra`),
    ...list.filter((s) => !fs.existsSync(path.join(dir, ...s.split("/"))))
      .map((s) => `UNDECLARED: ${rel} [skill] scripts declares ${s}, which the payload does not contain`),
  ];
  if (findings.length === 0 && text !== withDeclaredScripts(text, list)) {
    findings.push(`UNDECLARED: ${rel} [skill] scripts is not in its generated form (order or layout)`);
  }
  return findings;
}

// Guard: importing this module (e.g. from write-payload-manifest.mjs) must not perform a
// sync. The body below only runs when this file is executed directly as the entry point.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  // `--dump-deliveries`: print who ships what, as JSON, and exit without writing anything.
  //
  // scripts/check-docs.mjs's check 24 needs the source -> (destination path, destination
  // skills) mapping, and must get it for the tree IT is checking -- which, under
  // CHECK_DOCS_ROOT, is a temp copy of the repo and not this process's cwd. Importing this
  // module would derive the mapping from the REAL repo (repoRoot is process.cwd()), and
  // re-parsing syncGroups out of this file's text would be a second, hand-written derivation
  // of the thing this file already states -- exactly the drift repo CLAUDE.md §4 forbids. So
  // the checker spawns the COPY's own sync script and reads this.
  if (process.argv.includes("--dump-deliveries")) {
    const deliveries = new Map();   // "<src rel>\0<dest rel>" -> Set<skill name>
    for (const { files, dirs, skipMissing } of syncGroups) {
      for (const { src, rel } of files) {
        if (!fs.existsSync(src)) continue;
        for (const skillDir of dirs) {
          if (skipMissing && !fs.existsSync(skillDir)) continue;
          const key = `${path.relative(repoRoot, src)}\0${rel}`;
          if (!deliveries.has(key)) deliveries.set(key, new Set());
          deliveries.get(key).add(path.basename(skillDir));
        }
      }
    }
    // Not console.log. check-docs.mjs's check 24 spawns this and JSON.parse's what comes back,
    // so a lost tail surfaces as a parse error in an unrelated gate rather than as a visible
    // truncation here. It is LOUD, not silent: the downstream package truncated the real
    // output at all 681 interior points and every one threw, and check-docs.mjs:3766 pushes a
    // failure on the parse error rather than skipping. So the risk is a gate that fails for
    // reasons unrelated to the tree -- which teaches people to re-run it -- not a scope that
    // narrows quietly. (An earlier version of this comment claimed the silent case; it was
    // reasoned, not measured, and it is wrong.)
    writeAllSync(1, JSON.stringify([...deliveries].map(([key, skills]) => {
      const [source, dest] = key.split("\0");
      return {
        source: source.split(path.sep).join("/"),
        dest: dest.split(path.sep).join("/"),
        skills: [...skills].sort(),
      };
    })) + "\n");
    process.exit(0);
  }

  let drift = 0;
  let written = 0;
  const report = [];

  for (const { files, dirs, skipMissing } of syncGroups) {
    for (const { src, rel } of files) {
      if (!fs.existsSync(src)) {
        if (skipMissing) continue;  // step files not created yet — skip
        throw new Error(`Missing canonical source: ${src}`);
      }
      const content = fs.readFileSync(src);
      const mode = fs.statSync(src).mode;
      for (const skillDir of dirs) {
        if (skipMissing && !fs.existsSync(skillDir)) continue;  // skill not created yet
        const dest = path.join(skillDir, rel);
        const exists = fs.existsSync(dest);
        const same = exists && fs.readFileSync(dest).equals(content);
        if (check) {
          if (!same) {
            drift += 1;
            report.push(`DRIFT: ${path.relative(repoRoot, dest)} does not match ${path.relative(repoRoot, src)}`);
          }
          continue;
        }
        if (same) continue;
        fs.mkdirSync(path.dirname(dest), { recursive: true });
        fs.writeFileSync(dest, content);
        fs.chmodSync(dest, mode);
        execFileSync("git", ["add", dest], { cwd: repoRoot, stdio: "ignore" });
        written += 1;
        // Written as it happens, not buffered: this arm mutates the tree, and the `git add`
        // below it can throw. A buffer flushed at the end would lose the record of what had
        // already been copied on exactly the run where you need it. Calling writeAllSync per
        // line is still safe -- the rule it enforces is "never queue", not "write once".
        writeAllSync(1, `Synced ${path.relative(repoRoot, dest)}\n`);
      }
    }
  }

  let undeclared = 0;
  for (const dir of pmStatusDeclarers()) {
    const declared = declaredScripts(dir);
    if (check) {
      const findings = declarationFindings(dir, declared);
      undeclared += findings.length;
      report.push(...findings);
      continue;
    }
    const file = path.join(dir, "bmod.toml");
    const text = fs.readFileSync(file, "utf8");
    const next = withDeclaredScripts(text, declared);
    if (next === text) continue;
    fs.writeFileSync(file, next);
    execFileSync("git", ["add", file], { cwd: repoRoot, stdio: "ignore" });
    written += 1;
    writeAllSync(1, `Declared ${declared.length} script(s) in ${path.relative(repoRoot, file)}\n`);
  }

  const orphans = [...findOrphans(), ...findStalePackageFiles()];
  for (const orphan of orphans) {
    report.push(`ORPHAN: ${orphan} exists but no sync group targets this skill for this file`);
  }
  // A copy left where no skill lives -- at a path the layout no longer uses -- is not an
  // orphan of any skill, so findOrphans() cannot see it: it only looks inside skills.
  const strays = strayFiles(repoRoot);
  for (const stray of strays) {
    report.push(`STRAY: ${stray} is under skills/ but inside no skill and no module record`);
  }

  if (check) {
    if (drift > 0 || undeclared > 0 || orphans.length > 0 || strays.length > 0) {
      if (drift > 0) {
        report.push(`\n${drift} shared-script copy/copies out of sync — run: npm run sync:scripts`);
      }
      if (undeclared > 0) {
        report.push(`\n${undeclared} difference(s) between pm_status/ and a bmod.toml's [skill] ` +
          `scripts — v7 installs only what is declared; run: npm run sync:scripts`);
      }
      if (orphans.length > 0) {
        report.push(`\n${orphans.length} orphaned shared-script copy/copies found — delete them ` +
          `(git rm) or, if the file legitimately belongs there now, add that skill to the owning ` +
          `sync group in ${path.basename(import.meta.url)}.`);
      }
      if (strays.length > 0) {
        report.push(`\n${strays.length} stray file(s) under skills/ outside every skill — a copy ` +
          `left at a path the layout no longer uses; delete it (git rm) or move it into its skill.`);
      }
      writeAllSync(2, report.join("\n") + "\n");
      process.exit(1);
    }
    report.push("Shared-script payload copies are in sync with skills/_shared/, with no orphans or strays.");
  } else {
    report.push(`Shared-script sync complete (${written} file(s) written).`);
    if (orphans.length > 0) {
      report.push(`${orphans.length} orphaned copy/copies found — sync does not delete; remove them by hand.`);
    }
    if (strays.length > 0) {
      report.push(`${strays.length} stray file(s) under skills/ outside every skill — sync does not delete; remove them by hand.`);
    }
  }
  writeAllSync(1, report.join("\n") + "\n");
}
