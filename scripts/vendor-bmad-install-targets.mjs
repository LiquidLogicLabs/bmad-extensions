#!/usr/bin/env node
// Vendors BMad 6.x's per-platform skill install directories into
// skills/l3io-doctor/assets/bmad-install-targets.json, which bmad-deps.py reads to know where
// a 6.x install put its skills for each tool recorded in _bmad/_config/manifest.yaml `ides:`.
//
// Usage: node scripts/vendor-bmad-install-targets.mjs <platform-codes.yaml> <tag>
//   e.g. gh api 'repos/bmad-code-org/BMAD-METHOD/contents/tools/installer/ide/platform-codes.yaml?ref=v6.12.4' \
//          --jq .content | base64 -d > /tmp/pc.yaml
//        node scripts/vendor-bmad-install-targets.mjs /tmp/pc.yaml v6.12.4
//
// Vendored rather than fetched: bmad-deps.py runs offline inside a consuming project, and the
// table is 6.x's (l3io 3.x targets BMad 6.x only). Re-run it when the baseline pin moves.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import YAML from "yaml";

const [src, tag] = process.argv.slice(2);
if (!src || !tag) {
  console.log("usage: vendor-bmad-install-targets.mjs <platform-codes.yaml> <tag>");
  process.exitCode = 2;
} else {
  const platforms = YAML.parse(fs.readFileSync(src, "utf8")).platforms;
  const out = {
    _source: `bmad-code-org/BMAD-METHOD tools/installer/ide/platform-codes.yaml at ${tag}`,
    _regenerate: "node scripts/vendor-bmad-install-targets.mjs <platform-codes.yaml> <tag>",
    platforms: {},
  };
  for (const [code, p] of Object.entries(platforms)) {
    const i = p.installer || {};
    out.platforms[code] = { target_dir: i.target_dir ?? null, global_target_dir: i.global_target_dir ?? null };
  }
  const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
  const dest = path.join(root, "skills/l3io-doctor/assets/bmad-install-targets.json");
  fs.writeFileSync(dest, JSON.stringify(out, null, 2) + "\n");
  console.log(`wrote ${Object.keys(out.platforms).length} platforms to ${path.relative(root, dest)}`);
}
