# Step 01: Classify Work Type

Run after step-00-activate. Determines `{work_type}` for all in-scope epics/stories
before any orchestration begins. `{work_type}` is carried in all subsequent step
instructions and every headless subagent prompt.

---

## Classification rules

Examine the stories in scope (those in the active epics or the epics being planned):

| Type | Condition |
|------|-----------|
| `CODE` | At least one story has implementation ACs (code changes, APIs, services, data model) |
| `DOCS` | All stories are documentation only (no code or infrastructure changes) |
| `CONFIG` | All stories are infrastructure, CI/CD, configuration, or IaC only |
| `MIXED` | Stories span more than one type (e.g. both CODE and DOCS stories in same scope) |

## Classification procedure

1. For each in-scope story (read from story files in `{implementation_artifacts}` or from
   the status file if story files are absent):
   - Read the story's `classification` field if present. Classifications are:
     - `simple`, `standard`, `complex` → these describe sizing, not type. Read the story's
       Acceptance Criteria to determine type.
   - If the story file exists, read its "Acceptance Criteria" section.
   - Assign a type: CODE, DOCS, CONFIG, or MIXED (a single story can be MIXED if its ACs
     span multiple types).

2. Aggregate across all in-scope stories:
   - All DOCS → `{work_type}` = DOCS
   - All CONFIG → `{work_type}` = CONFIG
   - Mix of CODE + anything else → `{work_type}` = MIXED
   - Any CODE (even one story) → `{work_type}` = CODE (if rest are also CODE or unclassified)
   - Unclassifiable stories (no ACs at all) → treat as CODE (conservative default)

3. Bind `{work_type}` for all subsequent steps.

3a. Bind `{ui_facing_stories}` = the set of story keys whose ACs change something a person
   directly perceives: rendered UI, CLI output a person reads, user-facing copy or error
   text, or an API response a UI consumes. The test is whether a person would notice the
   change without reading logs, and it is about the **consumer, not the layer or the format**:
   - A backend rule that changes a displayed error message IS UI-facing — a person perceives
     the effect, whichever layer implements it.
   - Output consumed only by another program (machine-read logs, flags, JSON) is NOT.
   - Infrastructure that merely *serves* a UI is not UI-facing.
   - If the story does not say whether a UI or a person consumes the output, do not guess
     about callers — apply the default below.
   - **Default: when unclear, INCLUDE the story.** A false positive costs one extra UX check
     and one business-AC requirement; a false negative silently skips review on a story a
     user can see. A story with no ACs is CODE by this step's conservative default and is
     likewise included.
   - Examples: a pipeline change that alters the failure message a developer reads in CI
     output is UI-facing; an IAM role scope change with no human-visible surface is not.
   Bind it here, once, for the same reason `{skip_phases}` is bound here once: UX review and
   the business-AC gate must not reach different answers about the same story. Do not store
   it on the state node — it is derived from a story's ACs, and a stored copy drifts the
   moment the story is enriched.

4. Compute `{skip_phases}` from the phase matrix below.

**This matrix is the single source of truth for phase gating.** No other step file computes
`{skip_phases}`. If you are about to recompute it somewhere else, that is the bug this table
exists to prevent.

**Two mechanisms, and the difference matters.** Rows marked `{skip_phases}` are skipped by
being named in that binding. Rows marked with a step file are gated by a `{work_type}` check
inside that step and never appear in `{skip_phases}` at all. Do not migrate the second kind
into the first: a malformed `{skip_phases}` string would silently disable a gate, whereas a
`{work_type}` check cannot be turned off by a typo.

**Governing principle.** A phase is skipped by `{work_type}` only when that work type means
the phase has **no subject matter at all** — true of `DOCS` alone. Everything else gates on
its own applicability signal (an installed check, UI-facing stories), never on the work type.

| Phase | CODE | DOCS | CONFIG | MIXED | Enforced by |
|---|---|---|---|---|---|
| Readiness technical-AC check | run | skip | run | run | `{work_type}` at `l3io-plan/steps/plan/step-02-readiness-check.md` |
| Story elaboration | run | run | run | run | always runs; `{work_type}` selects the dimension vocabulary |

`l3io-execute` runs no phase of this table: a v7 build's review is `bmad-build-auto`'s own,
and an epic's closure is `bmad-retrospective`'s (ADR-0017), so none of them reads
`{work_type}` or `{skip_phases}`.

Bind `{skip_phases}` = comma-separated list of the `{skip_phases}`-enforced phase names that
this `{work_type}` column marks `skip` (empty if none). Rows whose *Enforced by* is a step
file, or "always runs", are never included.

To check if a skill is installed — query the installer's module manifest, never a config
section. A module can be installed and carry no config at all, so a config lookup reports a
present module as absent and the phase silently self-skips. See
`references/config-resolution.md` §6.

For `l3io-arch-review` (module code `l3io-arch`) and `l3io-sec-redteam` (module code
`l3io-sec`), run with the module code substituted:

```bash
grep -qE "^[[:space:]]*-[[:space:]]*name:[[:space:]]*l3io-arch[[:space:]]*$" \
  {project-root}/_bmad/_config/manifest.yaml 2>/dev/null && echo "present" || echo "absent"
```

## Output

Report the classification result:

```
Work type: {work_type}
UI-facing stories: {count of {ui_facing_stories}} of {count of in-scope stories}
Skipping phases: {skip_phases or "(none)"}
Rationale: [one sentence explaining the dominant story type]
```

Then continue to the next step.
