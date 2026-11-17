# CLAUDE.md — `scripts/`

Build, sync and release tooling for the package. Loads when working under `scripts/`.

The prohibitions themselves — never edit per-skill payload copies, never bundle a BMad core
script, never hand-edit a manifest, never move `pm-status`'s version backwards — live in the
root `CLAUDE.md`. This file carries the mechanics behind them.

Each checker's own header comment is the authoritative description of what it asserts;
`scripts/check-docs.mjs` numbers its thirty-six checks there.

**Every tool finds skills through `scripts/lib/skill-dirs.mjs`, never a `skills/*/` glob.** The
repository is laid out one folder per module (ADR-0021): `skills/<module>/<skill>/`, with
`skills/_shared/` beside them. `skillDirs()` returns every directory under `skills/` holding a
`SKILL.md`, at any depth, excluding `_shared/`; `skillDirByName()` maps a skill's name (its
basename, which is what an install flattens it to) to that directory, and refuses two skills
sharing a name. A one-level glob over `skills/` now sees four module folders and no skills at
all, and every check built on one would pass over an empty scope. `strayFiles()` is the other
half: a file under `skills/` that no skill and no module record owns — a per-skill copy left at
an old flat path — is invisible to everything that walks skills, so `check:scripts` and
`check:manifest` both fail on it by name (`STRAY:`).

**`check:bmod` is the v7 packaging gate; `check:module` keeps what it does not assert.**
`scripts/check-bmod.mjs` runs BMad's `validate_manifests.py` (ADR-0014) over a temp-dir view of
`skills/` without `_shared/` — the validator otherwise reports `skills/_shared: missing
bmod.toml`. The view is named `l3io-check-bmod-*`; a passing run removes it, a failing run keeps
it and prints its path. The validator and the three files it loads from its own directory
(`setup.py`, `knowledge.py`, `list_templates.py`) come from `scripts/fetch-bmad-tool.mjs <pin>
<path>`: raw.githubusercontent.com at a full commit SHA, each file verified against a SHA-256
recorded in that script's `KNOWN_TOOLS`, cached outside the repository
(`$BMAD_TOOL_CACHE`, else `$XDG_CACHE_HOME/l3io-bmad-tools`, else `~/.cache/l3io-bmad-tools`). A
(pin, path) with no recorded hash is refused before any network call; moving the pin means
reading the new files and recording their hashes in the same diff.

`check:bmod` has a second arm, over the doctor's `assets/wire-in.toml`: every non-test entry's
`path` must be a key the host skill's pinned `customize.toml` declares, and its `kind` must
match that key's shipped default (`scalar` a string, `list` a list of strings, `keyed` a
non-empty array of tables). v7 halts the render of the whole host skill on an undeclared or
mistyped team key (`render_skill.py:122-128`, `:301-317`), so a bad entry would break every
invocation of the user's planner or builder. The six host `customize.toml` files are fetched
through `fetch-bmad-tool.mjs` like the validator, hashes in `KNOWN_TOOLS`;
`CHECK_BMOD_CUSTOMIZE_DIR` substitutes them in the offline tests.

`check:module` has two rules. **pm-status-singleton**: one `pm_status` payload copy per module
(the folder under `skills/` a skill sits in). **help-registration**: every keyword a skill's
routing table marks `registered` is named, in backticks, in its module's `help/help.md` (alone,
or after the skill's name), and a `default` keyword's help.md names the skill. The Menu column
(`registered` · `default` · `health-check` · `not-a-capability`) is the source of truth, read
from the table; an unrecognised value fails, a missing column makes every keyword required, and a
skill with mode files under `steps/` but no table fails. The doctor's menu rows are mirrored in
`help/help.md` by hand, so this rule is what keeps them honest. The 6.x rules it used to carry —
two-location `module.yaml`, module-home payload, PluginResolver strategies, the agent roster,
`*-setup` singleton, `module-help.csv` rows and menu codes, forwarder shape — modelled an installer
v7 does not have and retired with it; they stay on `main` for 3.x.

**`smoke:install` installs the modules into a real v7 project.** `scripts/smoke-install.sh`
builds one with `tests/fixtures/v7/make-fixture.sh` at the same pin, copies it untouched for the
"only l3io-pm" case, `npx skills add`s each module folder (repeated `-a` flags) and runs v7's
`setup.py` headlessly, answering each question with its default. It asserts: every skill lands
in both tool roots; setup lists `lane_count`; no `problems`, no unmet requirement, every record
found and registered at the package version; a `lane_count` in `_bmad/custom/config.toml`
resolves; each module's declared `pm_status` (`l3io-pm`, `l3io-util`) is installed under
`_bmad/<module-code>/scripts/`, every file its `bmod.toml` lists, and `uv run` of its `__main__.py
--help` exits 0; the installed doctor's `report-version.py` finds the two copies agreeing, and
with one copy's version marker changed exits 3 with one finding naming both paths (the copy is
restored after); a hand-written initiative under the project's `core.output_folder` reads byte-identically through v7's own `tickets.py status` before and after `set-estimate`/`set-actual` with v7 addressing, with the sidecars and `{output_folder}/l3io/events.jsonl` written beside it; after the doctor's `wire`, v7's `render_skill.py` renders `bmad-build` and `bmad-build-auto` with the `build-open`/`build-close` hook commands in place, `unwire` restores both team files byte for byte, and a team `on_complete` planted first makes `wire` exit 3 and stay untouched; with Sofia wired, `spec-align.py` and `facts/ac-dimensions.md` are installed under `_bmad/l3io-pm/scripts/`, her rendered `validate-checks.md` holds our Ticket and Set checks and her session facts our fact file, and `check-pointers --story-file` and `estimate-entries --check` run from the installed paths; `plan-graph.py` is installed, her rendered `board.md` ends with our board hook and her menu lists `l3io-waves` and `l3io-lanes`, `waves` and `lanes` read the hand-written initiative's live `tickets.py status`, and `report --project-root` reads its tickets and actuals, all leaving `tickets.py status` byte-identical; after `wire`, `bmad-retrospective` renders with the `epic-close` command in its rendered `retro-document.md` On Complete, `unwire` restores its team file, a team `on_complete` planted first makes `wire` exit 3 naming both values, and `epic-close` runs from the installed copy leaving `tickets.py status` byte-identical; a 3.x runtime copy planted in `_bmad/scripts/` (the `pm-status/` package and
the older single file) is gone after setup runs again, while BMad's own `setup.py` there stays;
with only `l3io-pm`, `l3io-doctor` is an unmet requirement whose install hint selects
it with `--skill`, and following that hint against this checkout satisfies it. Setup's update
check (`--source-record`, which reads `bmod.toml` from `main` on GitHub) is reported, not judged:
it says `could-not-check` while `main` ships 3.x. It needs GitHub and npm, takes about 30 s, and
is not a CI gate.

**`smoke:install` cleans up after itself, and only after itself.** An earlier version took its
workdir from `work="${1:-$(mktemp -d)}"` and never removed it: eleven full BMad installs,
85 MB, leaked into a tmpfs `/tmp` where every byte is resident RAM. `standards-shell.md`, which
this package ships, requires the `trap` on the line after `mktemp`.

Two properties the trap deliberately keeps:

- **A workdir passed as `$1` is never removed.** It belongs to the caller; deleting it would
  be the over-broad delete that has already cost this estate a file.
- **A FAILING run keeps its tree** and prints the path. A smoke test that deletes the evidence
  at the moment you need it is hostile to the debugging it exists for. Cleanup happens on
  exit 0 only.

**A gate reports through `writeAllSync`, never `console.error`.** `console.log`/`console.error`
are asynchronous when the stream is a pipe — which is how CI and every suite here run these
scripts — and bytes still queued when `process.exit()` fires are discarded with no error
anywhere. `check-docs.mjs` shipped that for its whole life: a correct "231 documentation
problem(s)" header over 142 delivered findings, in 10 of 20 runs, intact 8/8 through a shell
pipeline, so it only ever truncated where nobody was reading. The trigger is the **number of
queued writes, not the payload size** — a single 128 KB write is intact 20/20, while a
`console.error` loop starts losing findings around 300 lines and delivers as little as 3% at
5000. `scripts/write-all-sync.mjs` has the measured curve. Two rules, both load-bearing:
assemble the whole report as one string and write it through the helper, and set
`process.exitCode` rather than calling `process.exit()`. Where a script genuinely must
terminate, the exit is fine *after* a completed `writeAllSync`, because nothing is left queued.
`scripts/tests/write-all-sync.test.mjs` enforces this, scope derived rather than listed, since
the file that needs the rule is the next one somebody writes.

**That scope is the union of two derivations, and needs to be.** Every `scripts/check-*.mjs`,
*plus* every `scripts/*.mjs` a `check:`/`test:` npm script invokes. A glob over filenames alone
missed two live gates for as long as the rule existed: `check:manifest` is
`write-payload-manifest.mjs` and `check:scripts` is `sync-shared-scripts.mjs`, both of which
report one finding per file in a loop and then exit — the manifest one emits a `STALE:` line
per drifted payload file across 8 skills, which after any `skills/_shared/steps/**` edit is
well past the 300-line onset. The npm side alone would equally miss a `check-*.mjs` that a
shell script invokes rather than npm. Both halves are
anchored separately, not just the union, because a union stays plausibly sized while one of its
derivations has quietly gone to zero.

The banned set is `console.error`, `console.warn`, and the stream API `process.stdout.write` /
`process.stderr.write` — the last of these is the same asynchronous writer under a spelling
that reads deliberate enough to look exempt. **`console.log` is deliberately not banned**: a
success line on a path that falls through to normal shutdown is flushed by the event loop
running to completion, so the hazard is the exit, not the writer. Calling `writeAllSync` once
per line is also fine — the rule is "never queue", not "write once" — and the two mutating
scripts do exactly that, so a run that throws partway still shows what it had already written.

**There is a THIRD failure shape, and the framing above does not reach it.** Everything to this
point measures the class by how much is queued. Misordering is not about quantity at all.
`run-python-suites.mjs` wrote its `=== <suite>` header and then spawned the suite with
`stdio: 'inherit'`: the child writes that fd *directly* while the parent's write is still
queued, so the header can land **after** the output it labels. Nothing is lost — it is
**misattributed**, which is worse, because a truncated report looks wrong and a mislabelled one
looks fine and gets acted on. A 20-byte header carries exactly the same exposure as a 20 KB
one, so no size threshold and no measured curve predicts it. The rule that does cover it is the
narrow one: **never hand an inherited fd to a child with your own write still queued on it.**
That header call is already on `writeAllSync` and says why at the call site; what was missing
was this paragraph. Raised by the downstream package after both our trees had documented
the class purely in terms of queue depth, which is the frame this case escapes.

## `check:types` — scoped, and the scope is the design

`scripts/check-types.mjs` runs mypy over every `.py` under `skills/_shared/pm_status/` and fails on two
classes only. Its header carries the full argument; three things to know before touching it:

- **It is not clean-file enforcement and should not become it.** 68 findings stand ungated
  today; `npm run check:types -v` prints the current tally, which moves with every extraction.
  A gate that works today beats a total one that is always one refactor away.
- **"Fail on any `[operator]` finding" is the obvious narrow cut and it does not work** — the
  package carries 4 pre-existing `[operator]` errors (`Unsupported operand types for +`), so
  that gate would fail on an unmodified tree. The cut has to be the message, `not callable`.
- **The `[name-defined]` arm is not a bonus, it is the load-bearing half.** Delete a
  `if TYPE_CHECKING` import from the module that owns the annotated code and the annotations
  resolve to `Any`, the first arm matches nothing, and the gate reports success over the exact
  bug it exists for. That arm is what turns a silent no-op into a failure.
  `scripts/tests/check-types.test.mjs` mutates both halves and asserts the inert state is
  caught; its fixtures copy the **real** package rather than a toy file, because a minimal
  repro flags the bug *with or without* the import and would have proved the gate worked when
  it did not. The mutation is applied to **every** `.py` in the copied package and fails if it
  matched nothing — mutating `__main__.py` alone silently stopped reaching the guard once the
  `TYPE_CHECKING` imports travelled out with the code they annotate.

It spawns mypy through `uv`, like every other Python entry point here, so there is no
dependency to declare and no interpreter to install. A `uv` that cannot spawn **fails** the
gate rather than skipping it — the lesson of a retired scanner gate that reported clean over
Python it had never linted.

## Dependencies

The checkers are **not** dependency-free, and have not been since
`docs/adr/0007-ci-installs-npm-dependencies.md`. `.github/workflows/checks.yml` runs `npm ci`
immediately after the toolchain setup steps and **before every gate**; a gate step added above
that install fails on `ERR_MODULE_NOT_FOUND`. Locally, run `npm ci` (or `npm install`) once
before `npm run check:*`.

Everything the checkers parse, they parse with a library — never a hand-written reader
(root `CLAUDE.md`, global rule 1, and this repo's own history with a hand-written YAML parser):

| Where | Parses | With |
|---|---|---|
| `check-module.mjs` help-registration | each skill's `SKILL.md` routing table, split on `\|` | `csv-parse` |
| `check-module.mjs` | each skill's `bmod.toml`, to find its module's record | `smol-toml` |
| `check-docs.mjs` check 17 | `.github/workflows/*.yml` and `*.yaml` | `yaml` |
| `check-docs.mjs` check 17 | each `run:` script, into argv | `mvdan-sh` |
| `check-docs.mjs` check 21 | each skill's `SKILL.md` frontmatter | `yaml` (the package BMad's installer uses) |

`mvdan-sh` is **deprecated on npm** — `npm ci` says so, and the lockfile entry carries it. It is
still the right choice here and the ADR says why, which successor was considered (`sh-syntax`,
async-only against a synchronous `check-docs.mjs`) and what would make us switch. Do not reach
for it in new code without reading that section.

**`check-docs.test.mjs`'s fixture is a *runnable* copy of the repo, and that is load-bearing.**
Check 24 derives its scope by spawning the *checked tree's own* `sync-shared-scripts.mjs
--dump-deliveries`, so the fixture needs this repo's devDependencies resolvable from it — it
symlinks `node_modules` rather than copying it. Without that link the fixture can only run a
script whose every import is a node builtin, which `sync-shared-scripts.mjs` happens to satisfy
today and is exactly the kind of thing that stops being true here, since the table above is a
standing instruction to reach for a library. The adopter package hit it when its sync script
acquired a `yaml` import: `ERR_MODULE_NOT_FOUND` surfaced as `check 24 cannot derive its scope`
across ~90 simultaneous failures, and no message anywhere named `node_modules`. A canary test
plants a library import into the copy and asserts the checker still runs, because a suite that
is green either way proves nothing about the property.

These are **devDependencies**. Nothing here ships: payload scope is a walk of every skill directory,
and `node_modules/` is neither under a skill nor tracked, so `check:manifest` cannot see them.
Every bare import in a gate script **is** mechanically asserted against `package.json` —
`check-docs.mjs`'s check 28 (`gateImportsDeclared()`, invoked from the check runner), the
follow-up ADR-0007 named. Its scope is derived: every `.mjs` under `scripts/`, recursively,
with `node:` builtins and relative paths excluded and a subpath resolved to its package
(`csv-parse/sync` -> `csv-parse`). This paragraph asserted the opposite until 2026-10-03,
which is the costlier direction of the §3 failure: a doc that claims a guard exists sends a
reader to look and they find nothing, while a doc that claims none exists tells them not to
look. It had already diverged from the root `CLAUDE.md`, which described check 28 correctly.

### Action versions across `.github/workflows/*.yml`

`checks.yml` and `reviewdog.yml` keep every shared `uses:` on the same version — verify the
current major against the upstream repo before bumping either file, rather than assuming the
other workflow's pin is still current. Two pinning rules, and they differ because the publishers
differ:

- `actions/checkout`, `actions/setup-node`, `astral-sh/setup-uv` are pinned by major tag
  (`@v7`, `@v10.2.0` respectively) *only when the publisher maintains a rolling tag* for that
  major — check with `git ls-remote https://github.com/<owner>/<repo>.git refs/tags/vN` first.
  `astral-sh/setup-uv` does not carry one (no `v10` ref exists at all), so it is pinned to the
  exact release tag instead of a major, unlike its GitHub-first-party siblings.
- Anything else — third-party, or a first-party action without a maintained major tag — is
  pinned to an exact release tag, or a commit SHA if no tag exists. Never a branch float
  (`@master`/`@main`): `reviewdog/action-detect-secrets` ran `@master` in a secret-scanning job,
  meaning whatever landed on that branch ran unreviewed on this repo's PRs; it is now
  `@v0.31.0`, the action's own latest release tag.

`actions/setup-python` is intentionally absent from `checks.yml`: every Python entry point is a
PEP-723 script (`# requires-python = ">=3.11"` in its own header) invoked through `uv run`, and
`uv` provisions a matching interpreter itself — `astral-sh/setup-uv` is the only Python
toolchain step either workflow needs. Re-check this if a future script needs a system Python
`uv` cannot provision (e.g. one requiring OS packages only `apt`/`setup-python` install).

Both workflows are meant to run clean under `nektos/act` (`/usr/local/bin/act` locally) as well
as GitHub — run `act push -W .github/workflows/checks.yml` and `act pull_request -W
.github/workflows/reviewdog.yml` after touching either file. `reviewdog.yml`'s job posts a
review to a real pull request via the GitHub API using `github.token`; under `act` there is no
real PR to review, so that job is GitHub-only by design, not a local-parity gap — a clean `act`
run there proves the container starts and the action's inputs are well-formed, not that the
review gets posted.

## Payload manifests

Each skill carries a **generated** `skills/<module>/<skill>/payload-manifest.json` — a SHA-256 for
**every file that skill ships**, keyed relative to that skill's own root. It is written by
`scripts/write-payload-manifest.mjs`, whose scope is a **walk of the skill directory**, with
three exclusions: `payload-manifest.json` (a file cannot contain its own hash), `tests/` (never
shipped as payload; no shipped skill has one today, so it is a guard rather than a live filter)
and `__pycache__/`. **Never hand-edit a manifest, and regenerate it whenever a payload file
changes** — `npm run sync:scripts` does not do it for you.

A skill is a directory with a `SKILL.md`, at any depth under `skills/` (`skillDirs()`). That is
what `npx skills add` installs, and it excludes `skills/_shared/`, which ships nothing. Every
skill has a manifest: a `SKILL.md` is payload, and `clean-payload.py` cannot see a directory
that has no manifest.

**This scope was wrong until 2026-10-10, and the way it was wrong is worth keeping.** It
imported `PAYLOAD_TARGETS` from the sync script, making the scope "files that arrived here by
being synced from `_shared/`". That was every payload file once. Then skill-local files appeared
— `SKILL.md`, `customize.toml`, skill-local `steps/` and `scripts/` — and were invisible to it.
**123 of 198 shipped files went unhashed; the manifest covered 38% of what ships.** Derived-beats-
listed was the right principle aimed at the wrong question: the scope was derived from *how a
file got here*, and that is not what "which files are ours" asks.

The consequence was not academic. `clean-payload.py` derives its delete set from this manifest
and treats anything absent as *"not ours. Not touched, not mentioned"* — so `/l3io-doctor
uninstall` silently left behind `migrate-engine.py` (which deletes a project's source layout),
`sync-state.py`, `init-sanctum.py`, every reorg script, all four forwarder directories, **and
`clean-payload.py` itself**: the file whose own docstring calls this manifest "the answer to
which files are ours" was a file the manifest did not claim.

It also **read as a guarantee**. `check:manifest` printed `Payload manifests are current` over an
edit to a file it could not see, and regenerating produced no diff — which looks like
confirmation the change was covered.

Two consequences of the fix, both intended. `check:manifest` now fails after **any** skill edit
until regenerated, including a `SKILL.md` edit, which is a workflow change every contributor
meets; the failure message names the command. And `clean-payload.py` accepts **two**
`generated_from` markers — `skills/<skill>/` and the older `skills/_shared/` — because
recognising only the new one would walk past every project installed before the change,
reporting `none-found` and removing nothing, which reads exactly like a clean uninstall.

Generation alone gates nothing: the manifests were generated once, later commits edited a
payload file, and HEAD shipped a manifest asserting a hash the file no longer had, which is
worse than no checksum because it reads as a guarantee. `npm run check:manifest` is now the gate,
in CI and in `prerelease`, and `postbump` regenerates after the payload re-sync (the bump rewrites
version strings inside payload files, so every hash moves).

## Sync and verify

`sync-shared-scripts.mjs` also **writes `[skill] scripts`** into the `bmod.toml` of every skill a
`pm_status` file is delivered to (`l3io-execute`, `l3io-doctor`): every `.py` of the package,
plus that skill's fixed `DECLARED_EXTRAS` (`l3io-execute`: `scripts/spec-align.py` and
`scripts/facts/ac-dimensions.md`, the files Sofia's readiness hooks name), POSIX paths relative
to the skill, sorted. A skill with extras and no `pm_status` copy declares its extras alone:
`l3io-plan` declares `scripts/plan-graph.py`, which Sofia's board hook runs. An extra the payload does not contain fails `--check` by name. v7's setup installs exactly that list into
`_bmad/<module-code>/scripts/`, so a module missing from it is not installed and its first
import fails on the user's machine. `--check` fails with an `UNDECLARED:` line naming the
`bmod.toml` and the script for each difference. Never hand-edit the list.

```bash
npm run sync:scripts    # regenerate payload copies from skills/_shared/ source
npm run check:scripts   # verify payload copies match source (CI also runs this)
npm run check:docs      # verify docs match the code they describe (CI + release gate)
npm run check:manifest  # verify per-skill payload-manifest.json matches the payload (CI + release gate)
npm run check:types     # scoped mypy over the pm_status package: accessor contracts only (CI)
npm run check:module    # one pm_status copy per module; every registered mode in help/help.md (CI)
npm run check:bmod      # BMad v7's validate_manifests.py at the pin, over skills/ without _shared (CI; network)
npm run smoke:install   # a real v7 install of all four modules (network; by hand, not CI)
npm run check:lock      # verify package.json and package-lock.json agree (CI + release gate)
node scripts/write-payload-manifest.mjs   # regenerate the manifests after editing a payload file
```

## Release

The `postbump` hook auto-syncs the new version into every `bmod.toml` module record — do not manually bump those files.

> **Release gate**: a `prerelease` hook refuses to release when payload copies have drifted from `skills/_shared/`, a `payload-manifest.json` is stale, or `package-lock.json` no longer matches `package.json` (runs `sync-shared-scripts.mjs --check`, `write-payload-manifest.mjs --check`, `check-docs.mjs`, `check-version.mjs`, and `npm ls --package-lock-only` for every `release:*` alias, not just `release`). `postbump` now stages with `git add -A skills/` so newly added skill files are included rather than silently dropped.

**Lock-drift is the same shape as manifest-drift, and it bit us the same way.** In 2026-09 the check-tooling devDependencies (`csv-parse`, `mvdan-sh`, `smol-toml`) were added to `package.json` and a `yaml` patch was bumped, but `package-lock.json` was never regenerated. CI's `npm ci` refused to install and every push from 2.5.2 through 3.0.1 died at that step — before any gate could run — so main was red for a week and nobody noticed until someone thought to look. `check:lock` runs `npm ls --package-lock-only --all --depth=0`, which is instantaneous, network-free, and prints `Missing: X from lock file` per drifted dep. It runs in CI as its own step *before* `npm ci` (so a red run names the drift cleanly rather than burying it under `npm ci`'s usage output) and in the release gate (so a release refuses to cut with drift, the same discipline as payload manifests). The class this closes is *the check is on CI and CI keeps dying before it reaches the check* — a green gate somewhere earlier that has to hold for the check to matter.
