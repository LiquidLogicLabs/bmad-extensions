# l3io lens: per-stack rules (`l3io-stack-rules`)

A review lens from l3io's engineering standards (module `l3io-arch`), run inside BMad's own
review: `bmad-review` and the thorough review of `bmad-code-review`, `bmad-build` and
`bmad-build-auto`. This file is the lens's whole method. The rules it applies live in the
standards files beside it, `../standards/`, which are the single source of truth: cite them,
never restate or invent a rule. Universal principles are the other lenses'; this one applies only the overlays.

## Scope

- A diff: review the changed hunks and what they directly reach. A finding about code the diff
  did not touch is out of scope unless the change makes it newly wrong.
- Anything else (a file, a design, a plan, a ticket, a spec): the whole content is the scope.
- Read the files this lens names below before you review. If one is unreadable, report that
  exact failure as your only output and stop.

## Method

Detect the stacks the content touches, and read the matching overlay in `../standards/`:

| Content | Overlay |
|---|---|
| `pyproject.toml`, `uv.lock`, `poetry.lock`, `*.py` | `standards-python.md` |
| `package.json`, `*.js`, `*.ts` | `standards-nodejs.md` |
| `*.csproj`, `*.sln`, `*.cs` | `standards-dotnet.md` |
| `.github/workflows/*` | `standards-github-actions.md` |
| `Dockerfile*`, compose files | `standards-docker.md` |
| `*.ps1`, `*.psm1` | `standards-powershell.md` |
| `*.sh`, `*.bash`, shell blocks in CI | `standards-shell.md` |

Walk each loaded overlay's **Review checklist** and its sections' **Review** bullets against
the content. Typical findings: an unpinned or floating version, a lockfile missing or not used
in CI, an action pinned below its latest major, a base image not pinned by digest, build tooling
in a final image, a script without strict mode, an unquoted expansion, a temp file without a
`trap`. When no overlay matches, return an empty list and name the stacks you saw.

## Findings

Return the host review's canonical fields for each finding, and nothing else:

- `location` — file:line-range for code, section for a document
- `trigger_condition` — the problem, in one line
- `guard_snippet` — the concrete fix
- `potential_consequence` — what goes wrong if it ships as it is
- `principle` — the overlay and section, e.g. `Docker: Base images`

No severity, priority or ranking: the host review triages. An empty list is a valid result,
but say which overlays you loaded, in one line, when you return none.
