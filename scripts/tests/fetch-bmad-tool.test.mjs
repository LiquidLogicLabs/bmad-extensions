// scripts/fetch-bmad-tool.mjs — one BMAD-METHOD file at a pinned commit, verified by a SHA-256
// recorded in the script, cached outside the repository.
//
// The network is never touched here: every test injects `fetchImpl`, and the CLI tests use
// arguments the script must refuse before it would fetch anything.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { fetchBmadTool, KNOWN_TOOLS, PIN } from "../fetch-bmad-tool.mjs";

const SCRIPT = path.join(import.meta.dirname, "..", "fetch-bmad-tool.mjs");
const FAKE_PIN = "a".repeat(40);
const FAKE_PATH = "skills/core-tools/bmad/scripts/tool.py";
const GOOD = "print('ok')\n";
const sha = (s) => createHash("sha256").update(s).digest("hex");

function cache(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "l3io-fetch-bmad-tool-test-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}

const known = { [FAKE_PIN]: { [FAKE_PATH]: sha(GOOD) } };

function serving(body, calls = []) {
  return async (url) => {
    calls.push(url);
    return { ok: true, status: 200, arrayBuffer: async () => new TextEncoder().encode(body).buffer };
  };
}

test("fetches the file at the pin, verifies it and returns its cached path", async (t) => {
  const dir = cache(t);
  const calls = [];
  const out = await fetchBmadTool(FAKE_PIN, FAKE_PATH, { cacheDir: dir, known, fetchImpl: serving(GOOD, calls) });
  assert.equal(out, path.join(dir, FAKE_PIN, FAKE_PATH));
  assert.equal(fs.readFileSync(out, "utf8"), GOOD);
  assert.deepEqual(calls, [
    `https://raw.githubusercontent.com/bmad-code-org/BMAD-METHOD/${FAKE_PIN}/${FAKE_PATH}`,
  ]);
});

test("a tampered fetch fails and leaves nothing in the cache", async (t) => {
  const dir = cache(t);
  await assert.rejects(
    fetchBmadTool(FAKE_PIN, FAKE_PATH, { cacheDir: dir, known, fetchImpl: serving("print('evil')\n") }),
    /SHA-256 mismatch/,
  );
  assert.equal(fs.existsSync(path.join(dir, FAKE_PIN, FAKE_PATH)), false);
  // No temp file left beside where it would have landed either.
  const parent = path.join(dir, FAKE_PIN, path.dirname(FAKE_PATH));
  assert.deepEqual(fs.existsSync(parent) ? fs.readdirSync(parent) : [], []);
});

test("a file with no recorded hash is refused before any network call", async (t) => {
  const dir = cache(t);
  const calls = [];
  await assert.rejects(
    fetchBmadTool(FAKE_PIN, "skills/other.py", { cacheDir: dir, known, fetchImpl: serving(GOOD, calls) }),
    /no SHA-256 recorded/,
  );
  assert.deepEqual(calls, []);
});

test("a verified cached copy is served without a network call", async (t) => {
  const dir = cache(t);
  await fetchBmadTool(FAKE_PIN, FAKE_PATH, { cacheDir: dir, known, fetchImpl: serving(GOOD) });
  const out = await fetchBmadTool(FAKE_PIN, FAKE_PATH, {
    cacheDir: dir, known, fetchImpl: async () => { throw new Error("network used"); },
  });
  assert.equal(fs.readFileSync(out, "utf8"), GOOD);
});

test("a cached copy that no longer matches its hash is fetched again", async (t) => {
  const dir = cache(t);
  const out = await fetchBmadTool(FAKE_PIN, FAKE_PATH, { cacheDir: dir, known, fetchImpl: serving(GOOD) });
  fs.writeFileSync(out, "print('edited')\n");
  const calls = [];
  await fetchBmadTool(FAKE_PIN, FAKE_PATH, { cacheDir: dir, known, fetchImpl: serving(GOOD, calls) });
  assert.equal(calls.length, 1);
  assert.equal(fs.readFileSync(out, "utf8"), GOOD);
});

test("an HTTP error is reported with its status", async (t) => {
  const dir = cache(t);
  const fetchImpl = async () => ({ ok: false, status: 404, arrayBuffer: async () => new ArrayBuffer(0) });
  await assert.rejects(fetchBmadTool(FAKE_PIN, FAKE_PATH, { cacheDir: dir, known, fetchImpl }), /HTTP 404/);
});

for (const [why, pin, rel] of [
  ["a pin that is not a full commit SHA", "main", FAKE_PATH],
  ["a path that climbs out of the repository", FAKE_PIN, "../etc/passwd"],
  ["an absolute path", FAKE_PIN, "/etc/passwd"],
]) {
  test(`refuses ${why}`, async (t) => {
    await assert.rejects(
      fetchBmadTool(pin, rel, { cacheDir: cache(t), known, fetchImpl: serving(GOOD) }),
      /refusing/,
    );
  });
}

test("every recorded hash is a SHA-256 for a full commit SHA, and the validator's imports are all recorded", () => {
  for (const [pin, files] of Object.entries(KNOWN_TOOLS)) {
    assert.match(pin, /^[0-9a-f]{40}$/);
    for (const [rel, digest] of Object.entries(files)) {
      assert.match(digest, /^[0-9a-f]{64}$/, rel);
    }
  }
  // validate_manifests.py loads setup.py and knowledge.py from its own directory, and knowledge.py
  // imports list_templates.py; a check that fetched the validator alone would fail to import.
  const dir = "skills/core-tools/bmad/scripts";
  for (const f of ["validate_manifests.py", "setup.py", "knowledge.py", "list_templates.py"]) {
    assert.ok(KNOWN_TOOLS[PIN]?.[`${dir}/${f}`], `${f} at ${PIN}`);
  }
});

test("the CLI refuses a file with no recorded hash and prints nothing on stdout", (t) => {
  const r = spawnSync(process.execPath, [SCRIPT, PIN, "README.md"], {
    encoding: "utf8", env: { ...process.env, BMAD_TOOL_CACHE: cache(t) },
  });
  assert.equal(r.status, 2, r.stderr);
  assert.equal(r.stdout, "");
  assert.match(r.stderr, /no SHA-256 recorded/);
});

test("the CLI refuses a missing argument with usage", () => {
  const r = spawnSync(process.execPath, [SCRIPT, PIN], { encoding: "utf8" });
  assert.equal(r.status, 2);
  assert.match(r.stderr, /usage: fetch-bmad-tool\.mjs <pin> <path>/);
});
