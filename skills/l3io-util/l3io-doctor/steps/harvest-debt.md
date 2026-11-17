## Harvest Debt Mode

Invoked with `harvest-debt` argument. Sweeps the source tree for `bmad-defer:` deferred-shortcut
markers and proposes each new one as a candidate `bug-<slug>` ticket for v7's backlog, so
intentional simplifications stay visible instead of rotting into "later means never." **It
writes no file**: on 4.x the backlog is `{output_folder}/backlog/`, Sofia's (`bmad-agent-po`),
and a leaf there is created only by her TICKETS or REFINE procedure. The mode hands her the
candidates. All [Safety Rules](`SKILL.md` § Safety Rules) apply. Re-runnable: a marker
already in the backlog is not proposed twice.

### The deferral marker contract (the shared source of truth)

A deferral marker is a single source-code comment in this form (the comment leader varies by
language; everything after `bmad-defer:` is the payload):

```
<comment-leader> bmad-defer: <what was simplified>. ceiling: <the limit this assumes>. upgrade: <the trigger to revisit>.
```

Examples across languages (all matched):

```python
# bmad-defer: linear scan over the cache. ceiling: <500 entries. upgrade: switch to an index past that.
```
```go
// bmad-defer: in-memory rate limit. ceiling: single instance. upgrade: move to Redis when horizontally scaled.
```
```sql
-- bmad-defer: full-table count. ceiling: <100k rows. upgrade: maintain a counter table beyond that.
```

- **Recognized comment leaders** (so the sweep is language-generic): `#`, `//`, `--`, `;`, `%`,
  `/*` (C-style block open), `<!--` (HTML/XML/Markdown), `'` (VB/VBScript). The marker keyword
  `bmad-defer:` is matched **case-insensitively**.
- **Payload parsing:** the text after `bmad-defer:` up to `ceiling:` is `<what>`; the text after
  `ceiling:` up to `upgrade:` is the `<ceiling>`; the text after `upgrade:` is the `<upgrade>`
  trigger. `ceiling`/`upgrade` are optional in the text — a marker that names **no** `upgrade:`
  trigger is tagged **`no-trigger`** (these rot silently and are escalated; see severity below).
- This is the same marker the PM dev and clean-release phases write and read — keep the keyword and
  field names stable; other skills depend on this exact contract.

### Grep contract

Search the whole tree from `{project-root}`, **case-insensitive**, with line numbers, skipping
vendored/build/VCS output:

**Build the file list with `find`, then search it. Do not use `grep -r`.** The recursion is
`find`'s, never the grep implementation's:

```bash
find . -type f \
  -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/dist/*' \
  -not -path '*/build/*' -not -path '*/vendor/*' -not -path '*/.venv/*' \
  -not -path '*/target/*' -not -path '*/out/*' \
  -not -path '*/{implementation_artifacts}/*' -not -path '*/{planning_artifacts}/*' \
  -print0 > "$list"

files_searched=$(tr -dc '\0' < "$list" | wc -c)
xargs -0 --no-run-if-empty grep -niE '(#|//|--|;|%|/\*|<!--|'\'') ?bmad-defer:' < "$list"
```

`$list` comes from `mktemp` with its `trap` on the next line, per
`l3io-arch-review/scripts/standards/standards-shell.md`:

```bash
list="$(mktemp)"
trap 'rm -f "$list"' EXIT
```

**The list goes to a file rather than straight down a pipe** so the count and the search read
the same set. A first draft piped `find` into `tee >(tr -dc '\0' | wc -c >&2)`, which produced
the right number but wrote it to the process substitution's own stderr, where the pipeline's
redirect could not capture it — the count printed to the terminal and `{files_searched}` came
back empty. Running `find` twice would also work and would risk the two runs disagreeing if
the tree changed between them.

Append `-not -path '*/{dir}/*'` for each directory listed in `harvest_exclude_dirs` (resolved in Step H1).

**Why `find` and not `grep -r`, which this contract used until 3.2.4.** `grep -r`'s recursion
semantics are not the same across the implementations actually on PATH: **ugrep honours
`.gitignore` during a recursive search and GNU grep does not.** Measured on one box carrying
both, same command, one marker in a tracked directory and one in a git-ignored directory:

    GNU grep 3.12  -> both markers
    ugrep 7.8.4    -> the tracked one only

A consuming project whose org root git-ignores its six source repositories therefore swept
none of them and reported a clean tree. `find` has no notion of `.gitignore`, so the result
stops depending on which `grep` is installed. Passing ugrep's `--no-ignore` would fix that box
and reintroduce the same class, because the flag is not portable to GNU grep.

`--no-run-if-empty` is load-bearing: with no input, `xargs` runs `grep` with no file operands,
`grep` then reads **stdin**, and the sweep hangs instead of reporting zero files. The flag is a
GNU extension — on a system without it, guard the pipeline with a non-empty test instead.

Artifact directories are excluded — markers are a **source-code** convention, not an artifact one,
and a marker quoted inside a backlog description must never re-harvest itself.

**Then drop every hit whose path falls inside this skill's own installed payload** — the
directory this step file was loaded from, and any sibling mirror of it (a BMad install writes
one copy per chosen tool: `.claude/skills/l3io-doctor/`, `.agents/skills/l3io-doctor/`,
`.cline/skills/l3io-doctor/`, …). A hit in
`…/skills/l3io-doctor/steps/harvest-debt.md` is one of this file's own three syntax examples,
never project debt.

This is a **post-sweep filter, not an `--exclude-dir`, and the distinction is load-bearing.**
Excluding `.claude` and `.agents` wholesale is one line shorter and wrong: projects keep real
hooks and tooling scripts under `.claude/`, and a marker in one of those is exactly the debt
this mode exists to surface. Blinding the sweep to a whole directory trades a visible false
positive for a silent false negative, which is the worse failure for a tool whose entire job is
noticing what would otherwise be forgotten. Mangling the examples so they stop matching is worse
still — they sit in `python`/`go`/`sql` fences precisely so they can be copied, and a copied
marker that the sweep cannot find is that same silent false negative, relocated into user code.
The examples stay verbatim; the sweep stays broad; only this file's own payload is filtered.

Narrowing the exclusion to a *path* instead (`--exclude-dir=./.claude/skills/l3io-doctor`) does
not rescue the `--exclude-dir` form either: GNU grep matches `--exclude-dir` against the
directory **basename**, so a path-shaped value is **silently a no-op** — no error, no warning,
both the example and any real marker come back. Verified against GNU grep 3.12. The trap is that
some drop-in replacements (ugrep, for one) *do* honour the path form, so whoever re-litigates
this may test it on a machine whose `grep` is not GNU grep, see it work, and revert. Resolving
the filter at parse time sidesteps that whole portability surface rather than depending on it.

Without this filter the mode finds its own examples in every project that installs the skill —
three markers × two install mirrors = six phantom hits on a tree with no real debt. Dedupe does
not absorb them: H3 matches on `source: code-marker ({file}:{line})` against items already in the
backlog, and an example nobody harvested matches nothing, so it is classified `new` and offered
for filing. Reported 2026-09-29 as a Health Check defect, but the sweep is shared — Health
Check's Check 3 delegates to this contract, so it faithfully reported this mode's wrong number.
Fixing it here fixes both; fixing it in Check 3 alone would have left `/l3io-doctor
harvest-debt` still offering to write the examples into the backlog.

### Steps

**Step H1 — Load config**

Load config (as under On Activation in `SKILL.md`). Also resolve:
- `harvest_exclude_dirs` — from the `l3io-util` section; default `[]`. Additional directories to exclude from the sweep on top of the built-in exclusion list. Each entry is passed as an additional `--exclude-dir` argument in the [Grep contract](#grep-contract).

Bind `{backlog_dir}` = `{output_folder}/backlog` — v7's standalone-ticket folder. It may not
exist yet; Sofia creates it with the first ticket filed there.

**Step H2 — Sweep and parse**

Run the [Grep contract](#grep-contract). For each hit, parse one marker record:
`{file}` (path relative to `{project-root}`), `{line}`, `{what}`, `{ceiling}` (or empty),
`{upgrade}` (or empty), and `no_trigger` = true when `{upgrade}` is empty.

**Always report how many files were searched, not only how many markers were found.** Bind
`{files_searched}` to the count the contract prints, and branch on it:

- `{files_searched}` is 0 → **this is a fault, not a clean tree.** Print
  `Searched 0 files — the sweep matched nothing to search, so "no markers" means nothing here.
  Check the exclusion list and {harvest_exclude_dirs}.` and exit **without** reporting a clean
  tree.
- markers found is 0, files searched > 0 → `Searched {files_searched} files. No bmad-defer:
  markers found — clean tree, nothing to harvest.` and exit.
- otherwise → carry `{files_searched}` into the Step H4 ledger header.

**Why the count is not cosmetic.** Before it existed, "0 markers found" and "0 files searched"
printed the identical sentence. A consuming project's sweep returned six hits — all of them
this skill's own doc examples across two install mirrors — and zero real markers, while a real
marker sat in the tree the whole time; the post-sweep payload filter then dropped the six and
the mode reported a clean tree. The output looked like good news, which is the only reason it
went unnoticed. A search that examined nothing must not be able to render as a search that
found nothing.

**Step H3 — Dedupe against the existing backlog**

Read every leaf in `{backlog_dir}/` and in each epic's `tickets/` folder under
`{output_folder}` (the files named `bug-*.md`, `story-*.md`, `spike-*.md` — a candidate Sofia
moved into an epic is still harvested). A marker is **already harvested** when a leaf cites
the same file in a `code-marker ({file}:{line})` reference **and** carries the same normalised
marker text in its title or body. Normalise both sides the same way before comparing: strip
the comment leader and the `bmad-defer:` keyword, collapse internal whitespace, casefold.

**The line number is metadata, not identity.** An edit above a marker moves its line, and a
marker keyed on its line would be proposed again as new after every such edit. Path plus text
matches it wherever it now sits.

A leaf whose plan reads `done` still counts as harvested **unless** the marker is back in the
source after it was closed: that is a recurrence, and it is proposed again with
`Recurrence of {ticket}` in its Notes. Partition the swept markers:
- `existing` — matches a leaf (skip).
- `new` — matches nothing, or only a `done` leaf (a recurrence).

**Step H4 — Dry-run ledger**

Group `new` markers by file and print the ledger (this is also the report-only output — a user who
declines Step H5 still gets this):

```
DEBT HARVEST DRY RUN — bmad-defer: markers
================================================================
{file}
  L{line} — {what}
            ceiling: {ceiling | '(none)'}   upgrade: {upgrade | 'NO-TRIGGER — rots silently'}
...
================================================================
Markers found: {total}  ·  new: {new_count}  ·  already harvested: {existing_count}  ·  no-trigger: {no_trigger_count}
Backlog: {backlog_dir} (Sofia's — nothing is written here)
```

If `{new_count}` is 0: print `All {total} marker(s) already in the backlog.` and exit.

**Step H5 — Candidate tickets for Sofia**

For each `new` marker, print one candidate in the shape of v7's bug template
(`bmad-agent-po/assets/bug-template.md`), for Sofia's TICKETS (or REFINE) to file in
`{backlog_dir}/`:

```
bug-{slug}                     (slug: the marker's {what}, kebab-case, at most 6 words)
  title:     "{what}"
  severity:  P3                (P2 for a no-trigger marker — it has no escape from rotting)
  risk:      low
  parent:    none              (a standalone bug in backlog/)
  Description: {what}. Ceiling: {ceiling | none}. Upgrade: {upgrade | NONE — no revisit trigger}.
  References:
    - code-marker ({file}:{line})
```

The `code-marker ({file}:{line})` reference is the contract: `/l3io-doctor triage` reads it to
tell whether the marker is still in the source, and the next harvest reads it to dedupe.
Never invent a ceiling or upgrade the comment did not state — write `none`/`NONE`.

**Do not create the files yourself, and do not run `tickets.py`.** Ask instead:
`Hand these {new_count} candidate(s) to Sofia now? (y/n)`. On yes, invoke `bmad-agent-po`
with the candidate list as its input and the request to file them as standalone bugs in
`backlog/`; she drafts, asks the user to approve each, and commits as her procedures do. On no,
print `Report only — no tickets filed.` and leave the list on screen.

**Step H6 — Report**

```
DONE — Debt harvest complete.
  Markers swept:     {total}
  New candidates:    {new_count}  (P3: {p3_count}, P2/no-trigger: {no_trigger_count})
  Already in backlog: {existing_count}
  Handed to Sofia:   {yes | no}
```

Markers stay in the source until the developer removes them when the shortcut is upgraded;
harvest records them, it never edits source. A later run re-sweeps and dedupes, so removing a
marker simply stops it reappearing — the ticket it became is closed through Sofia like any
other, and `triage` proposes that closing once the marker is gone.

---
