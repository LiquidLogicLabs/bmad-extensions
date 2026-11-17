# Skills and Sequence

Why each skill exists, when you reach for it, and the orders that make sense.

Five skills across four modules, all on BMad v7. The thing to understand first is that
**l3io attaches to v7's own skills rather than replacing them.** Sofia (`bmad-agent-po`) owns
the tickets, `bmad-build-auto` builds and reviews each one, and `bmad-retrospective` judges an
epic; l3io's hooks ride those skills, and you invoke few of l3io's skills directly.

## The short version

| Skill | The problem it solves | How you use it |
|---|---|---|
| `l3io-doctor` | "Is this project set up and wired, and where does it stand?" | **Run it first**, after every install and upgrade; `wire` once per project |
| `l3io-arch-review` | "Is this design sound, and is the decision recorded?" | Directly at design time and for decisions |
| `l3io-plan` | "How long will this take, in what order can it run, and who owns what?" | `estimate`, `waves`, `lanes` — also on Sofia's menu once wired |
| `l3io-execute` | "Build the planned tickets without driving each build by hand" | The unattended run — most of your runs |
| `l3io-sec-redteam` | "What would an adversary do with this?" | Directly, for adversarial reviews |

## Why each one exists

### `l3io-doctor` — the entry point

The doctor makes the project legible: with no argument it scans for every known problem,
reports findings, and proposes the fixes in order behind one confirmation. Its health check
reports when the two modules' `pm_status` copies, which `bmad setup` installs one per module,
have drifted to different versions.

It is also where l3io is attached to v7. `/l3io-doctor wire` writes l3io's hooks into the
team's `_bmad/custom/<skill>.toml` files — estimates on Sofia's ticket procedures, readiness
checks in her validate, waves and lanes on her board, measurement on every build and every
retrospective — and records exactly what it wrote, so `/l3io-doctor unwire` removes only that.
It never overwrites a team value.

Reach for it: after install, after every upgrade, whenever something looks wrong, for `wire`,
for `stats` (a progress dashboard over an initiative), and for `triage` (close backlog items
already fixed).

### `l3io-arch-review` — before you build, and whenever a decision is made

This is the only module with **no runtime dependency on the others**; it works on a project
that uses none of the rest. It applies an engineering-standards charter in three modes: design
guardrails for a new project, review of an existing design or diff, and decision support that
records an ADR. Its standards can be wired into core `bmad-architecture` and
`bmad-code-review` through `bmad-customize`, so they apply during v7's own design and review.

### `l3io-plan` — estimates, order and ownership

Shaping the plan is Sofia's: REFINE elaborates tickets, REPLAN reshapes the plan, BOARD moves
work. `l3io-plan` adds three things she does not:

- **`estimate`** — every ticket gets an estimate of all five metrics from its class and the
  project's calibration history, and each epic rolls up. Sofia's hooks run this as she writes
  tickets; the mode is for re-estimating on request. An estimate recorded before the work is the
  only thing that makes the actual recorded afterwards meaningful.
- **`waves`** — the order an initiative's epics may run in, from v7's own `after`
  declarations, and the epics whose closure a later wave waits on. Read-only.
- **`lanes`** — when several developers each work their **own clone**, which epics each owns.
  Every `flock` guards one filesystem and two clones share none, so between developers
  concurrency is mediated by `git merge`; **one epic, one lane** gives the merge nothing to
  decide in l3io's files. A lane is a **number**, never a person. Lanes stay entirely inert
  unless `bmad setup l3io-pm` recorded a `lane_count` above 1.

What lanes do **not** solve is source-file collisions. The dependency graph proves two epics
do not wait on each other; it says nothing about whether both rewrite the same module.

### `l3io-execute` — the unattended run

v7 builds one ticket per `bmad-build-auto` run. `l3io-execute` runs a whole initiative or epic:
it syncs the store, orders the epics into waves, runs one `bmad-build-auto` per ticket invoked
`thorough`, closes each epic with `bmad-retrospective`, marks its tickets `done` on an accepted
verdict, and merges the epic's branch. It adds no review or fix loop of its own — the build's
review is the review (ADR-0017).

Two properties explain the rest. First, each epic of a parallel wave runs in **its own worktree
and its own agent session** when the project commits `_bmad/`, and tickets inside an epic run
one at a time, because a build needs a clean tree. Second, it **stops where v7 says you
decide**: a ticket's checkpoints, a rejected retrospective, and an epic a later wave waits on,
which Sofia closes on your word.

Reach for it: `/l3io-execute` for the active initiative, or name an initiative or epic folder.

### `l3io-sec-redteam` — the adversary you would not think to be

Adversarial security review through five threat lenses — external attacker, malicious insider,
chaos engineer, abusive legitimate user, and a design red team — with an AI-poisoning cross-cut
where AI components are in scope.

It exists as its own module because the questions it asks are not the questions a code reviewer
asks, and asking them as an afterthought produces afterthought answers. Invoke it directly.

## What runs automatically once wired

After `/l3io-doctor wire`, these happen inside v7's skills without you asking:

| When | What runs |
|---|---|
| Sofia writes, refines or replans tickets | `estimate-entries` estimates new and changed entries (the replan hook repoints moved ones first) |
| Sofia validates | The six-dimension technical-AC and business-AC check per ticket; an "every entry has an estimate" check per set |
| Sofia's board changes | Waves and lanes are re-derived and shown |
| Every `bmad-build` or `bmad-build-auto` run | A measurement bracket opens before and closes after, recording the ticket's actuals and a calibration sample |
| Every `bmad-retrospective` | The epic's closure cost, its total actual and the verdict are recorded |

## Orders that make sense

### A new project

```
/l3io-arch-review design        → boundaries, initial ADRs, a docs skeleton
bmad setup                      → install l3io's modules into v7
/l3io-doctor wire               → attach l3io's hooks
Sofia                           → the initiative, its epics and tickets
/l3io-plan waves                → the order, and where the run will pause
/l3io-execute                   → run it
```

### A project that already has work underway

```
/l3io-doctor                    → health check first, always
/l3io-doctor stats              → where the initiative stands
/l3io-execute                   → the next waves
```

### A project coming from l3io 3.x

Read [Upgrading](upgrading.md) first: 4.x does not read a 3.x state tree.

### Any time, independently

- `/l3io-plan estimate` — re-estimate an initiative or epic
- `/l3io-plan lanes` — partition an initiative across developers with their own clones, or
  show one lane's view (silent unless setup recorded `lane_count` above 1)
- `/l3io-arch-review decision` — weigh a choice against the standards and record the ADR
- `/l3io-sec-redteam` — an ad-hoc adversarial review
- `/l3io-doctor triage` — close backlog items that are already fixed
- `/l3io-doctor stats` — a progress dashboard

## Required, optional, and what happens without each

| Module | Required? | Without it |
|---|---|---|
| `l3io-pm` | The core of the package | No unattended run, estimates or waves |
| `l3io-util` | **Required when using `l3io-pm`** | No `wire`, so no hooks; no health check or progress dashboard. `bmad setup` names it as an unmet requirement when only `l3io-pm` is installed |
| `l3io-arch` | Optional | No engineering-standards review |
| `l3io-sec` | Optional | No adversarial security review |

From BMad v7's `method` module, `l3io-execute` requires `bmad-agent-po` (Sofia),
`bmad-build-auto` and `bmad-retrospective`. `/l3io-doctor check-deps` shows what resolved in
your project.

## Which skills write state

Worth knowing before you run something on a project you care about.

| Skill | Writes state? |
|---|---|
| `l3io-execute` | v7 ticket status only through Sofia's store (`done` after an accepted verdict); merges epic branches; commits l3io's project state |
| `l3io-plan` | l3io's sidecars only — estimates and lanes, each committed |
| `l3io-doctor` | Yes, but every change is confirmed first; `wire` edits only the team's `_bmad/custom/` files |
| `l3io-arch-review` | Writes ADRs and review reports, not PM state |
| `l3io-sec-redteam` | Writes findings reports, not PM state |

Every l3io state write goes through one shared helper (`pm-status.py`), atomically and under a
lock where files are shared, and never writes a v7 file.

## Where to go next

- [Getting started](getting-started.md) — prerequisites, install, and your first run
- [l3io-pm reference](l3io-pm-reference.md) — the full lifecycle and every subcommand
- [Architecture and execution model](architecture.md) — the hooks, the sidecars and the cost
  model
