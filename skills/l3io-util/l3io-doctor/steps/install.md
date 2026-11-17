# upgrade — update this extension, or remove its payload

Invoked with `upgrade`, `install`, or `uninstall`. **The upgrade path re-adds the modules and
re-runs BMad's setup; the clean path deletes files.** Nothing runs without confirmation, and
the clean path reports in full before it changes anything.

On BMad v7 an install is three steps, and an upgrade is the same three again: `npx skills add`
of each module folder (`skills/<code>` of this package) installs its skills; `bmad setup
<code>` installs the scripts they declare under `_bmad/<code>/scripts/` and asks the module's
questions; `/l3io-doctor wire` attaches l3io's hooks to BMad's own skills. `npm run
smoke:install` runs this sequence against a real v7 project. The repository also ships a
standalone `install.sh` at its root for a FIRST install — that one cannot live here, because
a first install has no payload to run from.

## 1. Decide the action

Ask if the request is ambiguous. Map it:

| The user wants | Do this |
|---|---|
| to update to the current release | the upgrade in §2 |
| to remove this extension but keep BMad and their project | the clean in §3 |
| to set up a project with no l3io at all | **stop** — point them at `install.sh --action install` in the repository root, or the install steps in the README. A first install cannot run from payload that is not there yet. |
| any of these on a project without BMad v7 (`{project-root}/_bmad/scripts/setup.py` absent) | **stop** — l3io 4.x runs on BMad v7 only; a BMad 6.x project stays on l3io 3.x. |

## 2. Upgrade

**2.1 Re-add the modules.** For each l3io module installed here (`l3io-pm`, `l3io-util`, and
`l3io-sec`/`l3io-arch` when their skills are present), from the project root, once per agent
the project uses (`-a claude-code`, `-a codex`, …; repeat the flag):

```bash
npx --yes skills add LiquidLogicLabs/bmad-extensions/skills/<code> -s '*' -a claude-code -y --copy
```

`skills add` replaces each skill folder. It installs none of the scripts a skill declares.

**2.2 Set them up.** Tell the user to run `bmad setup` (or `bmad setup <code>` per module) in
their agent: it rebuilds each module's declared scripts under `_bmad/<code>/scripts/`, keeps
the answers already given, and offers every migration that now applies — l3io-pm's 3.x → 4.x
`migration-1` among them, once method's own has run. This skill does not run setup itself:
its questions are the user's to answer.

**2.3 Re-wire.** Run the `wire` mode (`steps/wire.md`). It is idempotent and adds only the
entries this release added.

Show the commands, ask `Run these? (y/N)`, then run 2.1 and 2.3 and hand 2.2 to the user.

### 2.4 Refresh the agent instruction block

The upgrade may have changed the block body. Refresh it in the running harness's instruction
file by following `assets/module-setup.md` §6 — it binds `{pm_status}`, `{runtime}` and
`{file}`, runs `--check`, asks for confirmation when `{file}` exists without markers, and only
then runs `--apply`. Do not run `--apply` outside that procedure: on a file with no markers it
appends to a document the user wrote. When the body is unchanged `--apply` writes nothing.

Exit 2 from it means ambiguous markers or invalid UTF-8; report it and continue — a
documentation block must never fail an upgrade that otherwise succeeded.

## 3. Clean — unwire, remove the instruction block, then this extension's payload

### 3.0 Unwire first

Run the `unwire` mode (`steps/unwire.md`) before anything else: once the payload is gone, the
team's `_bmad/custom/<skill>.toml` files would still name hooks whose scripts no longer exist.

### 3.1 Remove the agent instruction block first

Bind `{pm_status}` = `{project-root}/_bmad/l3io-util/scripts/pm_status/__main__.py`, and `{runtime}` = exactly one
of `claude`, `codex`, `copilot` or `other`, chosen by the detection procedure in
`l3io-execute/steps/shared/step-00-activate.md`. A guessed runtime targets the wrong
harness's file.

The block is **not payload** — it lives in a user-owned file and is not covered by the
SHA-256 comparison below, so the payload sweep cannot see it. It goes first so that a
failure in the sweep cannot leave a block behind describing an extension that is half gone.
Remove it by its markers:

```bash
uv run {pm_status} sync-agent-instructions --runtime {runtime} \
  --project-root {project-root} --remove
```

This never deletes the file, only the block. A file left empty is left empty. If
`pm-status.py` is already gone, report that the block was left in place and name its
`l3io:begin`/`l3io:end` markers so the user can delete it by hand.

### 3.2 Remove the payload

```bash
uv run {skill-root}/scripts/clean-payload.py --project-root {project-root}
```

Read-only as written. It lists every file it would delete, every file it is **keeping**
because that file's hash does not match what we shipped — meaning somebody edited it — and
every `__pycache__` directory it would prune (bytecode the interpreter wrote for our own
files, which is in no manifest and would otherwise keep the whole installed tree standing
after a "successful" uninstall). Relay all three lists in full; the second is the one that
needs a human decision.

Only after the user has seen that list and confirmed:

```bash
uv run {skill-root}/scripts/clean-payload.py --project-root {project-root} --apply
```

Exit codes: `0` done · `2` usage error · `4` no payload found.

## 4. After an upgrade, migrate the data

**`skills add` refreshes skills. It does not migrate project data.** A project upgrading from
l3io 3.x carries its estimates, actuals, calibration, events and ADR register in the 3.x
layout until `bmad migrate` runs l3io-pm's `migration-1` (after method's own). So after a
successful upgrade, tell the user to run `/l3io-doctor` — the health check's Check 20 says
whether that migration is pending. `docs/upgrading.md` carries the full procedure and the
per-version notes.

Report the installed version afterwards with the `version` mode, so the upgrade is confirmed
rather than assumed.

## Notes

- The clean never touches project state: neither `{output_folder}/l3io/**`, the sidecars
  beside v7's tree, nor a 3.x `{implementation_artifacts}/state/**` appears in a payload
  manifest, so the derived delete scope excludes them by construction.
- The clean also removes the `pm_status` copy l3io 3.x kept in BMad's own `_bmad/scripts/`
  directory, if one is still there, file by file, each only when it matches a shipped copy.
  Nothing in 4.x runs it.
  It does not touch `{project-root}/_bmad/<module-code>/scripts/`: that tree is v7's, rebuilt by `bmad setup`.
