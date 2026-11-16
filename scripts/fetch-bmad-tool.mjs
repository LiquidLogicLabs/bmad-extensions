#!/usr/bin/env node
// Fetch one file from bmad-code-org/BMAD-METHOD at a pinned commit, for a gate that needs a
// BMad core tool (validate_manifests.py) without this package bundling it. Prints the cached
// file's absolute path on stdout.
//
// Usage: node scripts/fetch-bmad-tool.mjs <pin> <path>
//   <pin>   a full 40-hex commit SHA (a branch or tag can move under us; a commit cannot)
//   <path>  the file's path inside BMAD-METHOD, e.g. skills/core-tools/bmad/scripts/setup.py
//
// Every file is verified against a SHA-256 recorded below in KNOWN_TOOLS, so a tampered or
// corrupted fetch fails instead of running. A (pin, path) with no recorded hash is refused before
// any network call: adding a file, or moving the pin, means fetching it once by hand, reading it,
// and recording its hash here in the same diff that starts using it.
//
// The cache sits OUTSIDE the repository — `$BMAD_TOOL_CACHE`, else `$XDG_CACHE_HOME/l3io-bmad-tools`,
// else `~/.cache/l3io-bmad-tools` — at `<cache>/<pin>/<path>`, so files fetched from one
// directory land beside each other (validate_manifests.py loads setup.py and knowledge.py from
// its own directory). A cached copy is re-verified on every use and re-fetched if it no longer
// matches. Nothing fetched is ever written under this repository, so nothing fetched can be
// committed or shipped.
//
// Exit: 0 success, 1 fetch or verification failure, 2 usage or a refused (pin, path).
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import { pathToFileURL } from "node:url";
import { writeAllSync } from "./write-all-sync.mjs";

// The BMAD-METHOD commit this package's v7 work is pinned to (Phase 2 plan, Global Constraints).
export const PIN = "e435a22574fe55722841086e5566420178b98df3";

const SCRIPTS = "skills/core-tools/bmad/scripts";
export const KNOWN_TOOLS = {
  [PIN]: {
    [`${SCRIPTS}/validate_manifests.py`]: "87e77c81555068c783e6c8b0a160c4868a51cf770bbb238e7c6f931e41fa9444",
    [`${SCRIPTS}/setup.py`]: "8607707c686978bd24bf509d9e0eb9534fb5bb58c6df6a1a4929e9878321d13f",
    [`${SCRIPTS}/knowledge.py`]: "89b8d223dfdd1ef1e99e1b4367a58d31bf0c43bebcc738c8bc7455249bf55caa",
    [`${SCRIPTS}/list_templates.py`]: "71da9423c2977fd803d5bda91b415f265c7d96f980ef73ffc50eb8dbbdba320b",
  },
};

const RAW_BASE = "https://raw.githubusercontent.com/bmad-code-org/BMAD-METHOD";

export function defaultCacheDir(env = process.env) {
  if (env.BMAD_TOOL_CACHE) return path.resolve(env.BMAD_TOOL_CACHE);
  const base = env.XDG_CACHE_HOME || path.join(os.homedir(), ".cache");
  return path.join(base, "l3io-bmad-tools");
}

class Refusal extends Error {}

const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");

export async function fetchBmadTool(pin, rel, {
  cacheDir = defaultCacheDir(),
  known = KNOWN_TOOLS,
  fetchImpl = globalThis.fetch,
} = {}) {
  if (!/^[0-9a-f]{40}$/.test(pin ?? "")) {
    throw new Refusal(`refusing pin '${pin}': a full 40-hex commit SHA is required, never a branch or tag`);
  }
  const posix = path.posix.normalize(rel ?? "");
  if (!rel || path.posix.isAbsolute(rel) || posix.startsWith("..") || posix !== rel) {
    throw new Refusal(`refusing path '${rel}': it must be a normalised path inside BMAD-METHOD`);
  }
  const want = known[pin]?.[rel];
  if (!want) {
    throw new Refusal(`no SHA-256 recorded for ${rel} at ${pin} in scripts/fetch-bmad-tool.mjs ` +
      `(KNOWN_TOOLS) — read the file at that commit and record its hash before using it`);
  }

  const dest = path.join(cacheDir, pin, ...rel.split("/"));
  if (fs.existsSync(dest) && sha256(fs.readFileSync(dest)) === want) return dest;

  const url = `${RAW_BASE}/${pin}/${rel}`;
  const res = await fetchImpl(url);
  if (!res.ok) throw new Error(`fetching ${url}: HTTP ${res.status}`);
  const body = Buffer.from(await res.arrayBuffer());
  const got = sha256(body);
  if (got !== want) {
    throw new Error(`SHA-256 mismatch for ${url}: expected ${want}, got ${got} — not cached, not run`);
  }
  // Write beside the destination and rename, so an interrupted run never leaves a partial file
  // where a later run would find it.
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  const tmp = `${dest}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, body);
  fs.renameSync(tmp, dest);
  return dest;
}

async function main(argv) {
  const [pin, rel] = argv;
  if (!pin || !rel) {
    writeAllSync(2, "usage: fetch-bmad-tool.mjs <pin> <path>\n");
    return 2;
  }
  try {
    const out = await fetchBmadTool(pin, rel);
    writeAllSync(1, `${out}\n`);
    return 0;
  } catch (e) {
    writeAllSync(2, `fetch-bmad-tool: ${e.message}\n`);
    return e instanceof Refusal ? 2 : 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = await main(process.argv.slice(2));
}
